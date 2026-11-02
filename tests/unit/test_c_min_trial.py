"""Synthetic-only one-shot adapter tests: no operator auth, real CLI or provider."""

import http.client
import io
import json
import time
from types import SimpleNamespace

import pytest
from test_loop_c_min import frames, item, request, wire

from loop_engine.approval import ApprovalQueue
from loop_engine.c_min_runtime import invoke, preflight
from loop_engine.c_min_trial import (
    PLAN_HASH,
    PROMPT,
    SCHEMA,
    authorize,
    record_result,
    reserve,
    run,
    status,
)
from loop_engine.model_invocations import InvocationJournal
from loop_engine.process import ProcessResult
from loop_engine.security import SafetyError, fingerprint
from loop_engine.state_store import StateStore


def fixture(tmp_path, monkeypatch):
    state = StateStore(tmp_path / "state.db")
    work = tmp_path / ".loop/runtime/probes/c-min-single-validation"
    work.mkdir(parents=True)
    (work / "synthetic.txt").write_bytes(b"C_MIN_SYNTHETIC_ONLY\n")
    body = request()
    body["input"] = [{"role": "user", "content": PROMPT}]
    body["text"]["format"]["schema"] = SCHEMA
    state.set_metadata("c_min_auth_profile", {"synthetic": True})
    permit = {
        "purpose": "c-min-single-validation",
        "runtime": "runtime",
        "artifact": "artifact",
        "workspace": str(work.resolve()),
        "plan": PLAN_HASH,
        "input_hash": fingerprint(body["input"]),
        "profile": fingerprint({"synthetic": True}),
        "history": "a" * 64,
        "expires": time.time() + 90,
        "max_calls": 1,
        "refresh": "official-existing-secure-backend-only",
        "offline_review": "b" * 64,
    }
    state.set_metadata("c_min_trial_permit", permit)
    state.set_metadata(
        "c_min_trial_history",
        {"binding": permit["history"], "reconciled": True, "additional_slots": 1},
    )
    state.set_metadata(
        "c_min_trial_offline_review",
        {"binding": permit["offline_review"], "runtime": "runtime", "passed": True},
    )
    queue = ApprovalQueue(state)
    decision = queue.request(None, "scope", fingerprint(permit), "Synthetic fixture only")
    queue.resolve(
        [
            {
                "id": decision,
                "action": "approve",
                "target_hash": fingerprint(permit),
                "reason": "Synthetic test database, not operator approval",
            }
        ],
        "fixture",
    )
    monkeypatch.setattr("loop_engine.runtime_diagnostics.runtime_identity", lambda _: "runtime")
    return state, work, body, permit, decision


@pytest.mark.parametrize("change", ["permit", "approval", "history", "profile", "expiry", "marker"])
def test_missing_changed_authorization_stops_before_reservation(tmp_path, monkeypatch, change):
    state, work, _, permit, decision = fixture(tmp_path, monkeypatch)
    if change == "permit":
        state.set_metadata("c_min_trial_permit", None)
    elif change == "approval":
        decision = "unknown"
    elif change == "history":
        state.set_metadata("c_min_trial_history", None)
    elif change == "profile":
        state.set_metadata("c_min_auth_profile", {"changed": True})
    elif change == "expiry":
        monkeypatch.setattr("loop_engine.c_min_trial.time.time", lambda: permit["expires"] + 1)
    else:
        (work / "synthetic.txt").write_text("unapproved data")
    with pytest.raises(SafetyError):
        authorize(tmp_path, state, work, "artifact", decision)
    assert status(state)["phase"] == "absent"
    with pytest.raises(SafetyError):
        preflight(tmp_path, state, "artifact")  # Trial approval cannot unlock normal calls.


@pytest.mark.parametrize(
    "mode,versioned",
    [
        (mode, versioned)
        for mode in ("success", "input", "unknown", "disconnect", "source_changed")
        for versioned in (False, True)
    ]
    + [
        (mode, True)
        for mode in (
            "header",
            "permit_changed",
            "history_changed",
            "contract_changed",
            "path_changed",
            "peer_changed",
            "binding_changed",
        )
    ],
)
def test_shared_adapter_one_shot_complete_input_and_no_replay(
    tmp_path, monkeypatch, mode, versioned
):
    state, work, body, permit, decision = fixture(tmp_path, monkeypatch)
    if versioned:
        from test_trial_input_binding import fixture as input_fixture

        from loop_engine.trial_input_binding import VERSION

        spec, body, _ = input_fixture()
        profile = {"sid": "synthetic-sid", "home": str(tmp_path / "synthetic-home")}
        state.set_metadata("c_min_auth_profile", profile)
        permit["profile"] = fingerprint(profile)
        spec["headers"] = {"x-openai-internal-codex-responses-lite": "true"}
        spec["launch"] = {
            "runtime": "runtime",
            "artifact": "artifact",
            "workspace": str(work.resolve()),
            "profile": permit["profile"],
            "history": permit["history"],
            "model": "gpt-6.1-sol",
            "destination": "https://chatgpt.com/backend-api/codex/responses",
            "argv": ["synthetic-cli", "exec"],
            "schema": fingerprint(SCHEMA),
        }
        permit.update(input_version=VERSION, input_hash=fingerprint(spec))
        state.set_metadata("c_min_trial_input_contract", spec)
        state.set_metadata("c_min_trial_permit", permit)
        queue = ApprovalQueue(state)
        decision = queue.request(None, "scope", fingerprint(permit), "Synthetic versioned fixture")
        queue.resolve(
            [
                {
                    "id": decision,
                    "action": "approve",
                    "target_hash": fingerprint(permit),
                    "reason": "Offline synthetic test only",
                }
            ],
            "fixture",
        )

        class Arg0:
            calls = 0

            def __init__(self, *args):
                pass

            def check(self, *args):
                self.calls += 1
                return {
                    "volume": 1,
                    "index": self.calls if mode == "path_changed" else 2,
                    "created": 3,
                }

            def close(self):
                pass

        monkeypatch.setattr("loop_engine.trial_arg0.Arg0Guard", Arg0)
        if mode == "binding_changed":
            original_bind = InvocationJournal.bind_trial_input

            def corrupt(self, identifier, binding):
                original_bind(self, identifier, binding)
                with state.connect() as db:
                    db.execute(
                        "UPDATE trial_input_bindings SET document=? WHERE invocation=?",
                        (json.dumps({**binding, "request": "changed"}), identifier),
                    )

            monkeypatch.setattr(InvocationJournal, "bind_trial_input", corrupt)
    created = []
    response_item = item()
    response_item["content"][0]["text"] = json.dumps({"ok": True, "proof": "C_MIN_SYNTHETIC_OK"})
    events = frames([response_item])
    if mode == "unknown":
        events[-1][1]["response"]["unknown"] = True
    if mode == "input":
        body["input"].insert(0, {"role": "developer", "content": "unapproved source canary"})

    class Reply(io.BytesIO):
        status = 200

        def getheader(self, *_):
            return "text/event-stream"

    class HTTPS:
        sock = None

        def __init__(self, *_, **__):
            created.append("connection")

        def request(self, *_args, **_kwargs):
            assert _kwargs["body"] == json.dumps(body).encode()
            created.append("sent")
            if mode == "disconnect":
                raise OSError("synthetic lost response")

        def getresponse(self):
            return Reply(wire(events))

        def close(self):
            pass

    class Process:
        calls = 0

        def run(self, argv, cwd, **options):
            self.calls += 1
            # Even a direct adapter caller below supplies a much longer timeout;
            # the reserved permit remains the absolute authority.
            assert 0 < options["timeout"] <= 90
            options["before_resume"](123, object())
            if mode == "permit_changed":
                state.set_metadata("c_min_trial_permit", None)
            if mode == "history_changed":
                state.set_metadata("c_min_trial_history", None)
            if mode == "contract_changed":
                state.set_metadata("c_min_trial_input_contract", None)
            url = next(
                json.loads(x.split("=", 1)[1]) for x in argv if x.startswith("openai_base_url=")
            )
            port = int(url.rsplit(":", 1)[1].split("/")[0])
            client = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
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
                        **({"Unknown-Header": "unassessed"} if mode == "header" else {}),
                    },
                )
                reply = client.getresponse()
                reply.read()
            except (OSError, http.client.HTTPException):
                return ProcessResult("cancelled", None)
            finally:
                client.close()
            output = [
                {"type": "thread.started"},
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": response_item["content"][0]["text"]},
                },
                {"type": "turn.completed"},
            ]
            if mode == "source_changed":
                monkeypatch.setattr(
                    "loop_engine.runtime_diagnostics.runtime_identity", lambda _: "changed-runtime"
                )
            return ProcessResult("exit", 0, "\n".join(map(json.dumps, output)))

    monkeypatch.setattr("loop_engine.audit_transport.http.client.HTTPSConnection", HTTPS)
    monkeypatch.setattr("loop_engine.c_min_runtime.verify_profile", lambda _: None)

    def private(root, relative):
        path = root / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr("loop_engine.c_min_runtime.private_directory", private)
    monkeypatch.setattr("loop_engine.c_min_runtime.privacy_options", lambda _: [])

    # A real callable identity substitute; real kernel peer tests run separately.
    class Peer:
        calls = 0

        def bind(self, *_):
            pass

        def close(self):
            pass

        def __call__(self, _):
            return True

        def identity(self):
            self.calls += 1
            return {
                "pid": 123 if mode != "peer_changed" else self.calls,
                "creation": 456,
                "sid": "synthetic-sid",
            }

    monkeypatch.setattr("loop_engine.c_min_runtime.OwnedCliPeer", lambda _: Peer())
    boundary = SimpleNamespace(
        root=tmp_path,
        _binding=lambda _: "artifact",
        _command=lambda argv, _: argv,
        docker=SimpleNamespace(require=lambda *_: None, audit_evidence=lambda _: True),
    )
    process = Process()

    def call():
        return invoke(
            tmp_path,
            state,
            boundary,
            process,
            ["synthetic-cli", "exec"],
            PROMPT,
            work,
            SCHEMA,
            {},
            time.monotonic() + 1000,
            lambda: False,
            trial_approval=decision,
        )

    if mode == "success":
        outcome, journal, identifier = call()
        proof = record_result(state, journal, identifier, permit, outcome.stdout)
        assert proof["purpose"] == "c-min-single-validation" and proof["passed"]
        if versioned:
            assert proof["input_contract"] == permit["input_hash"]
            assert (
                proof["request_hash"]
                == __import__("hashlib").sha256(json.dumps(body).encode()).hexdigest()
            )
        assert status(state) == {
            "purpose": "c-min-single-validation",
            "phase": "completed",
            "passed": True,
        }
        journal.acknowledge(identifier)  # Idempotent acknowledgement, never a new call.
        from loop_engine.runtime_diagnostics import require_receipt

        (tmp_path / ".loop/runtime/live-runtime.json").write_text(
            json.dumps({"identity": "runtime", "passed": True, "tool_surface": proof})
        )
        with pytest.raises(SafetyError):
            require_receipt(tmp_path)  # A trial proof never activates ordinary development.
    else:
        with pytest.raises(SafetyError):
            call()
        assert not status(state)["passed"]
    blocked_before_send = {
        "input",
        "header",
        "permit_changed",
        "history_changed",
        "contract_changed",
        "path_changed",
        "peer_changed",
        "binding_changed",
    }
    assert created == ([] if mode in blocked_before_send else ["connection", "sent"])
    with pytest.raises(SafetyError):
        call()
    assert process.calls == 1
    with pytest.raises(SafetyError):
        reserve(StateStore(state.path), {**permit, "nonce": "new"}, "other")


def test_command_without_live_permit_never_reads_operator_configuration(tmp_path, monkeypatch):
    state = StateStore(tmp_path / "state.db")
    plan = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "docs/plans/C_MIN_SINGLE_CONNECTION_APPROVAL.md"
    )
    monkeypatch.setattr(
        "loop_engine.runtime_diagnostics.boundary_for",
        lambda _: pytest.fail("operator configuration must not be inspected"),
    )
    with pytest.raises(SafetyError, match="No real-connection"):
        run(tmp_path, state, plan, "absent")
    assert status(state)["phase"] == "absent"


def test_trial_role_cannot_bypass_reserved_slot(tmp_path):
    journal = InvocationJournal(StateStore(tmp_path / "state.db"))
    with pytest.raises(SafetyError):
        journal.claim(
            {
                "role": "trial",
                "schema": "trial",
                "owner_id": "forged",
                "spec": "spec",
                "binding": "artifact",
                "attempt": 1,
            },
            "artifact",
            time.time() + 10,
        )


@pytest.mark.parametrize("audit", ["current", "stale", "failed", "source", "missing"])
def test_real_workspace_and_image_audit_guards_before_profile_or_reserve(
    tmp_path, monkeypatch, audit
):
    from loop_engine.docker_boundary import DockerBoundary

    state, work, _, _, decision = fixture(tmp_path, monkeypatch)
    image = "sha256:" + "a" * 64
    docker = object.__new__(DockerBoundary)
    docker.root, docker.image_id, docker.binary = tmp_path, image, "synthetic-docker"
    docker.leases = tmp_path / "leases"
    docker.leases.mkdir()
    monkeypatch.setattr("loop_engine.docker_boundary.image_contents", lambda _: {"pin": "fixed"})
    manifests = (
        "pyproject.toml",
        "backend/requirements.lock",
        "frontend/package.json",
        "frontend/package-lock.json",
    )
    for name in manifests:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic")
    receipt = {
        "image_id": image,
        "audited": audit != "failed",
        "built_at": time.time() - (86401 if audit == "stale" else 1),
        "source_hash": fingerprint({"pin": "changed" if audit == "source" else "fixed"}),
    }
    if audit != "missing":
        (tmp_path / ".loop/runtime/qa-image.json").write_text(json.dumps(receipt))
    inspected = []

    class Inspector:
        def run(self, argv, *_args, **_kwargs):
            inspected.append(argv)
            return ProcessResult("exit", 0, image)

    monkeypatch.setattr("loop_engine.docker_boundary.ProcessRunner", Inspector)
    touched = []

    def profile(_):
        touched.append("nonsecret-profile")
        raise RuntimeError("synthetic stop after actual QA guards, before reservation")

    monkeypatch.setattr("loop_engine.c_min_runtime.verify_profile", profile)
    boundary = SimpleNamespace(_binding=lambda _: "artifact", docker=docker)
    monkeypatch.setattr("loop_engine.runtime_diagnostics.boundary_for", lambda _: boundary)
    monkeypatch.setattr("loop_engine.codex_runner.codex_binary", lambda _: "synthetic-cli")
    plan = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "docs/plans/C_MIN_SINGLE_CONNECTION_APPROVAL.md"
    )
    expected = RuntimeError if audit == "current" else (SafetyError, FileNotFoundError)
    with pytest.raises(expected):
        run(tmp_path, state, plan, decision)
    assert bool(touched) is (audit == "current")
    assert len(inspected) == 1 and status(state)["phase"] == "absent"


def test_ack_failure_cannot_publish_passed_proof_or_release_trial_slot(tmp_path, monkeypatch):
    state, _, _, permit, _ = fixture(tmp_path, monkeypatch)
    owner = reserve(state, permit, "artifact")
    journal = InvocationJournal(state)
    identifier = journal.claim(owner, "artifact", time.time() + 30)
    phases = [
        "prepared",
        "launch_reserved",
        "request_validated",
        "upstream_reserved",
        "terminal_validated",
    ]
    for before, after in zip(phases, phases[1:], strict=False):
        journal.advance(identifier, before, after)
    event = state._event

    def fail_completion(db, kind, *args):
        if kind == "model.completed":
            raise OSError("synthetic failed acknowledgement commit")
        event(db, kind, *args)

    monkeypatch.setattr(state, "_event", fail_completion)
    output = "\n".join(
        map(
            json.dumps,
            [
                {"type": "thread.started"},
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "text": '{"ok":true,"proof":"C_MIN_SYNTHETIC_OK"}',
                    },
                },
                {"type": "turn.completed"},
            ],
        )
    )
    with pytest.raises(OSError):
        record_result(state, journal, identifier, permit, output)
    assert status(state)["passed"] is False
    with state.connect() as db:
        row = db.execute("SELECT phase,document FROM c_min_trials").fetchone()
        assert row["phase"] == "validated" and json.loads(row["document"])["passed"] is False
        assert db.execute("SELECT phase FROM model_invocations").fetchone()[0] == "cli_validated"
    with pytest.raises(SafetyError):
        reserve(StateStore(state.path), permit, "artifact")
