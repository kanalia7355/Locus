"""Existing C-min relay/journal with synthetic run ownership and mock HTTPS."""

import http.client
import io
import json
import time
from types import SimpleNamespace

import pytest
from test_loop_c_min import frames, item, request, wire
from test_loop_proposals import proposal
from test_run_authorization import fixture, start, worker

from loop_engine import run_authorization as run
from loop_engine.c_min_runtime import invoke
from loop_engine.codex_runner import transport_schema
from loop_engine.model_invocations import InvocationJournal
from loop_engine.process import ProcessResult
from loop_engine.schemas import SCHEMAS, validate
from loop_engine.security import SafetyError


@pytest.mark.parametrize(
    "mode",
    [
        "success",
        "prepared_resume",
        "before_resume",
        "before_send",
        "after_send",
        "disconnect",
        "cancel",
    ],
)
def test_normal_run_adapter_seals_source_before_send_and_never_replays(tmp_path, monkeypatch, mode):
    state, _ = fixture(tmp_path, monkeypatch)
    start(tmp_path, state)
    workspace, owner = worker(tmp_path, state)
    state.set_metadata("c_min_auth_profile", {"synthetic": True})
    source = ["source"]
    monkeypatch.setattr(
        run, "files", lambda root, git, control_only: "control" if control_only else source[0]
    )
    monkeypatch.setattr("loop_engine.c_min_runtime.verify_profile", lambda state: None)
    monkeypatch.setattr("loop_engine.c_min_runtime.privacy_options", lambda root: [])

    def private(root, relative):
        path = root / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr("loop_engine.c_min_runtime.private_directory", private)

    class Peer:
        def __init__(self, *args):
            pass

        def bind(self, *args):
            pass

        def __call__(self, connection):
            return True

        def close(self):
            pass

    monkeypatch.setattr("loop_engine.c_min_runtime.OwnedCliPeer", Peer)
    schema = transport_schema(SCHEMAS["proposal"])
    body = request()
    body["text"]["format"]["schema"] = schema
    output = proposal(["backend/new.py"])
    validate("proposal", output)
    response = item()
    response["content"][0]["text"] = json.dumps(output)
    sent = []
    prior_deadline = time.time() + 5
    if mode == "prepared_resume":
        InvocationJournal(state).claim(owner, "artifact", prior_deadline)

    class Reply(io.BytesIO):
        status = 200

        def getheader(self, *args):
            return "text/event-stream"

    class HTTPS:
        sock = None

        def __init__(self, host, **kwargs):
            assert host == "chatgpt.com"

        def request(self, method, path, **kwargs):
            sent.append((method, path))
            assert kwargs["body"] == json.dumps(body).encode()
            if mode == "after_send":
                source[0] = "changed source"
            if mode == "disconnect":
                raise OSError("synthetic unknown response")

        def getresponse(self):
            return Reply(wire(frames([response])))

        def close(self):
            pass

    monkeypatch.setattr("loop_engine.audit_transport.http.client.HTTPSConnection", HTTPS)

    class Process:
        calls = 0

        def run(self, argv, cwd, **options):
            self.calls += 1
            if mode == "prepared_resume":
                assert options["timeout"] <= prior_deadline - time.time() + 0.1
            if mode == "before_resume":
                source[0] = "changed before resume"
            options["before_resume"](123, object())
            if mode == "cancel":
                state.set_metadata("control", "paused")
                assert options["cancelled"]()
                return ProcessResult("cancelled", None)
            if mode == "before_send":
                source[0] = "changed before send"
            url = next(
                json.loads(a.split("=", 1)[1]) for a in argv if a.startswith("openai_base_url=")
            )
            port = int(url.rsplit(":", 1)[1].split("/")[0])
            client = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            try:
                client.request(
                    "POST",
                    "/responses",
                    json.dumps(body),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer synthetic-only",
                        "ChatGPT-Account-ID": "synthetic-account",
                        "X-OpenAI-Internal-Codex-Responses-Lite": "true",
                    },
                )
                reply = client.getresponse()
                reply.read()
            except (OSError, http.client.HTTPException):
                return ProcessResult("cancelled", None)
            finally:
                client.close()
            return ProcessResult(
                "exit",
                0,
                "\n".join(
                    map(
                        json.dumps,
                        [
                            {
                                "type": "item.completed",
                                "item": {"type": "agent_message", "text": json.dumps(output)},
                            }
                        ],
                    )
                ),
            )

    process = Process()
    boundary = SimpleNamespace(
        _binding=lambda workspace: "artifact", command=lambda argv, workspace: argv
    )

    def call():
        return invoke(
            tmp_path,
            state,
            boundary,
            process,
            ["synthetic-cli", "exec"],
            "synthetic prompt",
            workspace,
            schema,
            owner,
            time.monotonic() + 60,
            lambda: False,
        )

    if mode in {"success", "prepared_resume"}:
        result, journal, identifier = call()
        assert result.returncode == 0
        journal.advance(identifier, "terminal_validated", "cli_validated")
        state.finish_execution(owner["owner_id"], "returned", output["result"])
        journal.acknowledge(identifier)
    else:
        with pytest.raises(SafetyError):
            call()
    assert len(sent) == (0 if mode in {"before_resume", "before_send", "cancel"} else 1)
    with pytest.raises(SafetyError):
        call()
    assert process.calls == 1
    with state.connect() as db:
        assert db.execute("SELECT count(*) FROM model_run_bindings").fetchone()[0] == 1
        phases = db.execute("SELECT phase FROM model_invocations").fetchall()
    assert [row[0] for row in phases] == [
        "completed" if mode in {"success", "prepared_resume"} else "held"
    ]
