"""C-min offline contracts and durable recovery; no actual login or model calls."""

import copy
import http.client
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from loop_engine.audit_transport import AuditRelay
from loop_engine.c_min_runtime import preflight
from loop_engine.model_gate import FRAME_LIMIT, ResponseGate, strict_json, validate_request
from loop_engine.model_invocations import InvocationJournal
from loop_engine.security import SafetyError
from loop_engine.state_store import StateStore

MODEL = "gpt-6.1-sol"
SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def request() -> dict[str, Any]:
    return {
        "model": MODEL,
        "store": False,
        "stream": True,
        "input": [{"role": "user", "content": "synthetic input sentinel"}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "codex_output_schema",
                "strict": True,
                "schema": SCHEMA,
            }
        },
    }


def item() -> dict[str, Any]:
    return {
        "type": "message",
        "id": "msg_one",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": '{"ok":true}', "annotations": []}],
    }


def frames(outputs: list[Any] | None = None) -> list[tuple[str, Any]]:
    outputs = outputs if outputs is not None else [item()]
    return [
        (
            "response.created",
            {
                "type": "response.created",
                "response": {
                    "id": "resp_one",
                    "object": "response",
                    "status": "in_progress",
                    "output": [],
                },
            },
        ),
        (
            "response.output_item.done",
            {"type": "response.output_item.done", "output_index": 0, "item": outputs[0]},
        ),
        (
            "response.completed",
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_one",
                    "object": "response",
                    "status": "completed",
                    "model": MODEL,
                    "output": outputs,
                },
            },
        ),
    ]


def wire(events: list[tuple[str, Any]]) -> bytes:
    return b"".join(
        ("event: " + name + "\ndata: " + json.dumps(value) + "\n\n").encode()
        for name, value in events
    )


@pytest.mark.parametrize(
    "raw",
    [
        b'{"x":1,"x":2}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'"\\ud800"',
        b"\xff",
        b"[" * 65 + b"0" + b"]" * 65,
    ],
)
def test_json_rejects_ambiguous_or_excessive_data(raw: bytes) -> None:
    with pytest.raises(SafetyError):
        strict_json(raw)


def test_request_is_preserved_and_closed() -> None:
    value = request()
    assert validate_request(json.dumps(value).encode(), MODEL, SCHEMA, set()) == value
    for field in ("previous_response_id", "conversation", "unknown", "instructions"):
        changed = {**value, field: "synthetic"}
        with pytest.raises(SafetyError):
            validate_request(json.dumps(changed).encode(), MODEL, SCHEMA, set())


@pytest.mark.parametrize(
    "kind",
    [
        "function_call",
        "custom_tool_call",
        "mcp_call",
        "computer_call",
        "code_interpreter_call",
        "web_search_call",
        "additional_tools",
    ],
)
def test_request_capability_and_history_rejected(kind: str) -> None:
    value = request()
    value["input"].append({"type": kind, "tools": [{"type": "shell"}]})
    with pytest.raises(SafetyError):
        validate_request(json.dumps(value).encode(), MODEL, SCHEMA, set())


def test_authoritative_encoded_metadata_is_not_opaque() -> None:
    value = request()
    value["client_metadata"] = {"x-codex-turn-metadata": json.dumps({"tool_namespaces": []})}
    with pytest.raises(SafetyError):
        validate_request(json.dumps(value).encode(), MODEL, SCHEMA, set())
    value["client_metadata"] = {"mcp_attribution": json.dumps({"status": "none"})}
    assert validate_request(json.dumps(value).encode(), MODEL, SCHEMA, set()) == value
    value["client_metadata"]["mcp_attribution"] = '{"status":"none","tools":[]}'
    with pytest.raises(SafetyError):
        validate_request(json.dumps(value).encode(), MODEL, SCHEMA, set())


@pytest.mark.parametrize("chunk", [1, 7, 8192])
def test_valid_fragmented_text_stream(chunk: int) -> None:
    data = wire(frames())
    gate = ResponseGate(MODEL)
    result = []
    for offset in range(0, len(data), chunk):
        result.extend(gate.feed(data[offset : offset + chunk]))
    gate.finish()
    assert b"".join(result) == data
    assert gate.completed


@pytest.mark.parametrize(
    "kind",
    [
        "function_call",
        "custom_tool_call",
        "mcp_call",
        "computer_call",
        "code_interpreter_call",
        "web_search_call",
        "agent_call",
    ],
)
@pytest.mark.parametrize("position", ["added", "done", "terminal"])
def test_no_tool_frame_is_forwardable(kind: str, position: str) -> None:
    gate = ResponseGate(MODEL)
    good = frames()
    gate.feed(wire(good[:1]))
    bad = {"type": kind, "id": "call_one", "name": "synthetic", "arguments": "sentinel"}
    if position == "terminal":
        gate.feed(wire(good[1:2]))
        event = copy.deepcopy(good[-1])
        event[1]["response"]["output"].append(bad)
    else:
        name = "response.output_item." + position
        event = (name, {"type": name, "output_index": 0, "item": bad})
    with pytest.raises(SafetyError):
        gate.feed(wire([event]))
    assert not gate.completed


@pytest.mark.parametrize("mutation", ["unknown", "duplicate", "order", "mismatch", "truncated"])
def test_protocol_changes_and_inconsistency_hold(mutation: str) -> None:
    events = frames()
    if mutation == "unknown":
        events[1][1]["item"]["new_capability"] = True
    elif mutation == "duplicate":
        events.insert(2, events[1])
    elif mutation == "order":
        events = events[1:]
    elif mutation == "mismatch":
        events[-1][1]["response"]["output"] = []
    else:
        events = events[:-1]
    with pytest.raises(SafetyError):
        gate = ResponseGate(MODEL)
        gate.feed(wire(events))
        gate.finish()


def test_frame_bound_and_post_terminal_data() -> None:
    with pytest.raises(SafetyError):
        ResponseGate(MODEL).feed(b"x" * (FRAME_LIMIT + 1))
    gate = ResponseGate(MODEL)
    gate.feed(wire(frames()))
    with pytest.raises(SafetyError):
        gate.feed(b"event: response.created\n\n")


def owner(role: str = "worker") -> dict[str, Any]:
    return {
        "role": role,
        "schema": {"worker": "proposal", "reviewer": "review", "evaluator": "evaluation"}[role],
        "owner_id": "existing-execution",
        "attempt": 1,
        "spec": "frozen-spec",
        "binding": "existing-binding",
    }


@pytest.mark.parametrize(
    "phase",
    [
        "prepared",
        "launch_reserved",
        "request_validated",
        "upstream_reserved",
        "terminal_validated",
        "cli_validated",
    ],
)
def test_crash_never_mints_new_owner_or_replays(tmp_path: Path, phase: str) -> None:
    state = StateStore(tmp_path / "state.sqlite")
    journal = InvocationJournal(state)
    call = journal.claim(owner(), "artifact", time.time() + 30)
    steps = [
        "prepared",
        "launch_reserved",
        "request_validated",
        "upstream_reserved",
        "terminal_validated",
        "cli_validated",
    ]
    for before, after in zip(steps, steps[1:], strict=False):
        if before == phase:
            break
        journal.advance(call, before, after)
    fresh = InvocationJournal(StateStore(state.path))
    for value in [owner(), {**owner(), "owner_id": "different-nonce"}]:
        with pytest.raises(SafetyError):
            fresh.claim(value, "new-artifact", time.time() + 30)
    with pytest.raises(SafetyError):
        fresh.acknowledge(call)


@pytest.mark.parametrize("role", ["worker", "reviewer", "evaluator"])
def test_ack_requires_durable_authoritative_result(tmp_path: Path, role: str) -> None:
    state = StateStore(tmp_path / "state.sqlite")
    journal = InvocationJournal(state)
    call = journal.claim(owner(role), "artifact", time.time() + 30)
    for before, after in zip(
        [
            "prepared",
            "launch_reserved",
            "request_validated",
            "upstream_reserved",
            "terminal_validated",
        ],
        [
            "launch_reserved",
            "request_validated",
            "upstream_reserved",
            "terminal_validated",
            "cli_validated",
        ],
        strict=True,
    ):
        journal.advance(call, before, after)
    with pytest.raises(SafetyError):
        journal.acknowledge(call)
    if role == "evaluator":
        with state.transaction() as db:
            db.execute(
                "INSERT INTO development_evaluations VALUES (?,?,?,?)",
                ("existing-binding", "head", "{}", time.time()),
            )
        journal.acknowledge(call)
        with pytest.raises(SafetyError):
            journal.claim(owner(role), "artifact", time.time() + 30)
    assert "synthetic input sentinel" not in state.path.read_bytes().decode("latin1")


def test_no_live_permit_does_not_load_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = StateStore(tmp_path / "state.sqlite")
    monkeypatch.setattr("loop_engine.runtime_diagnostics.runtime_identity", lambda _: "artifact")
    with pytest.raises(SafetyError, match="authorization"):
        preflight(tmp_path, state, "artifact")


def test_normal_probe_is_held_without_any_cli_or_auth_call(tmp_path: Path) -> None:
    from loop_engine.toolless_boundary import ToollessBoundary

    boundary = object.__new__(ToollessBoundary)
    evidence = boundary.probe(tmp_path)
    assert evidence["passed"] is False and evidence["surface_version"] == 3
    assert evidence["diagnostic_only"] and not evidence["no_tools"]


def test_actual_relay_filters_before_writing_and_reserves_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    malicious = frames()
    malicious[-1][1]["response"]["output"].append({"type": "function_call"})
    upstream_bytes = wire(malicious)

    class Response:
        status = 200

        def getheader(self, _: str, default: str = "") -> str:
            return "text/event-stream"

        def read1(self, _: int) -> bytes:
            nonlocal upstream_bytes
            chunk, upstream_bytes = upstream_bytes[:40], upstream_bytes[40:]
            return chunk

    class Connection:
        sock = None

        def __init__(self, host: str, **_: Any):
            assert host == "chatgpt.com"

        def request(self, method: str, path: str, **_: Any) -> None:
            calls.append(method + path)

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            pass

    monkeypatch.setattr("loop_engine.audit_transport.http.client.HTTPSConnection", Connection)
    reserved = []
    with AuditRelay(
        MODEL,
        deadline=time.monotonic() + 5,
        cancelled=lambda: False,
        forwarding=True,
        peer_authorized=lambda _: True,
        request_validator=lambda raw: validate_request(raw, MODEL, SCHEMA, set()),
        reserve_upstream=lambda: reserved.append(True),
    ) as relay:
        client = http.client.HTTPConnection("127.0.0.1", relay.server.server_port, timeout=2)
        client.request(
            "POST",
            "/responses",
            json.dumps(request()),
            headers={
                "Authorization": "Bearer synthetic-memory-only-sentinel",
                "ChatGPT-Account-ID": "synthetic-account",
                "Content-Type": "application/json",
                "X-OpenAI-Internal-Codex-Responses-Lite": "true",
            },
        )
        response = client.getresponse()
        received = response.read()
        assert b"function_call" not in received
        assert b"response.completed" not in received
        assert relay.failed and not relay.response_gate.completed
        client.close()
        second = http.client.HTTPConnection("127.0.0.1", relay.server.server_port, timeout=2)
        with pytest.raises((http.client.HTTPException, ConnectionAbortedError)) as rejected:
            second.request("POST", "/responses", json.dumps(request()))
            second.getresponse()
        if isinstance(rejected.value, ConnectionAbortedError):
            # Windows may report fail-closed TCP shutdown as WSAECONNABORTED
            # rather than HTTP RemoteDisconnected. No other socket error is accepted.
            assert sys.platform == "win32"
            assert getattr(rejected.value, "winerror", None) == 10053
        second.close()
    assert reserved == [True]
    assert calls == ["POST/backend-api/codex/responses"]
