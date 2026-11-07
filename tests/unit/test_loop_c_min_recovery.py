"""Offline real journal/relay effects at crash boundaries; no credentials or provider."""

import http.client
import json
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_loop_c_min import MODEL, SCHEMA, frames, owner, request, wire
from test_loop_foundation import task

from loop_engine.audit_transport import AuditRelay
from loop_engine.c_min_runtime import verify_profile
from loop_engine.codex_runner import CodexRunner
from loop_engine.model_gate import ResponseGate, validate_request
from loop_engine.model_invocations import InvocationJournal
from loop_engine.security import SafetyError, fingerprint
from loop_engine.state_store import StateStore
from loop_engine.windows_tcp_peer import OwnedCliPeer


@pytest.mark.parametrize(
    "header,value",
    [
        ("X-Codex-Turn-Metadata", '{"tools":[{"type":"function"}]}'),
        ("X-Codex-Turn-State", "history"),
        ("OpenAI-Beta", "unknown_tools=enabled"),
    ],
)
def test_authoritative_header_never_reaches_provider(
    monkeypatch: pytest.MonkeyPatch,
    header: str,
    value: str,
) -> None:
    created = []
    monkeypatch.setattr(
        "loop_engine.audit_transport.http.client.HTTPSConnection",
        lambda *a, **k: created.append(True),
    )
    with AuditRelay(
        MODEL,
        deadline=time.monotonic() + 3,
        cancelled=lambda: False,
        forwarding=True,
        peer_authorized=lambda _: True,
        request_validator=lambda raw: validate_request(raw, MODEL, SCHEMA, set()),
        reserve_upstream=lambda: created.append("reserved"),
    ) as relay:
        client = http.client.HTTPConnection("127.0.0.1", relay.server.server_port, timeout=2)
        with pytest.raises(http.client.HTTPException):
            client.request(
                "POST",
                "/responses",
                json.dumps(request()),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer synthetic-memory-only",
                    "ChatGPT-Account-ID": "synthetic-account",
                    "X-OpenAI-Internal-Codex-Responses-Lite": "true",
                    header: value,
                },
            )
            client.getresponse()
        client.close()
        assert relay.failed
    assert created == []


@pytest.mark.parametrize("changed", ["snapshot", "progress"])
def test_output_snapshot_and_progress_order_are_immutable(changed: str) -> None:
    events = frames()
    gate = ResponseGate(MODEL)
    gate.feed(wire(events[:1]))
    message = json.loads(json.dumps(events[1][1]["item"]))
    if changed == "progress":
        message["status"] = "in_progress"
        message["content"] = []
    added = (
        "response.output_item.added",
        {"type": "response.output_item.added", "output_index": 0, "item": message},
    )
    if changed == "snapshot":
        bad = added
    else:
        gate.feed(wire([added]))
        bad = (
            "response.in_progress",
            {
                "type": "response.in_progress",
                "response": {
                    "id": "resp_one",
                    "object": "response",
                    "status": "in_progress",
                    "output": [],
                },
            },
        )
    with pytest.raises(SafetyError):
        gate.feed(wire([bad]))


@pytest.mark.parametrize("when", ["before_commit", "after_commit", "after_send"])
def test_send_is_prevented_when_actual_reservation_commit_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    when: str,
) -> None:
    state = StateStore(tmp_path / "state.sqlite")
    journal = InvocationJournal(state)
    call = journal.claim(owner(), "artifact", time.time() + 20)
    journal.advance(call, "prepared", "launch_reserved")
    journal.advance(call, "launch_reserved", "request_validated")
    original = state.connect

    class CommitFailure:
        def __init__(self, connection: Any):
            self.connection = connection

        def __getattr__(self, key: str) -> Any:
            return getattr(self.connection, key)

        def commit(self) -> None:
            if when == "after_commit":
                self.connection.commit()
            raise OSError("synthetic abrupt termination")

    @contextmanager
    def fault() -> Any:
        with original() as db:
            yield CommitFailure(db)

    if when != "after_send":
        monkeypatch.setattr(state, "connect", fault)
    created = []

    class SentThenDisconnected:
        sock = None

        def __init__(self, *args: Any, **kwargs: Any):
            created.append("connected")

        def request(self, *args: Any, **kwargs: Any) -> None:
            created.append("provider_bytes_sent")
            raise OSError("synthetic failure after provider send")

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "loop_engine.audit_transport.http.client.HTTPSConnection",
        SentThenDisconnected if when == "after_send" else lambda *a, **k: created.append(True),
    )
    with AuditRelay(
        MODEL,
        deadline=time.monotonic() + 3,
        cancelled=lambda: False,
        forwarding=True,
        peer_authorized=lambda _: True,
        request_validator=lambda raw: validate_request(raw, MODEL, SCHEMA, set()),
        reserve_upstream=lambda: journal.advance(call, "request_validated", "upstream_reserved"),
    ) as relay:
        client = http.client.HTTPConnection("127.0.0.1", relay.server.server_port, timeout=2)
        with pytest.raises(http.client.HTTPException):
            client.request(
                "POST",
                "/responses",
                json.dumps(request()),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer synthetic-memory-only",
                    "ChatGPT-Account-ID": "synthetic-account",
                    "X-OpenAI-Internal-Codex-Responses-Lite": "true",
                },
            )
            client.getresponse()
        client.close()
        assert relay.failed
    assert created == (["connected", "provider_bytes_sent"] if when == "after_send" else [])
    monkeypatch.setattr(state, "connect", original)
    with state.connect() as db:
        phase = db.execute("SELECT phase FROM model_invocations WHERE id=?", (call,)).fetchone()[0]
    assert phase == ("upstream_reserved" if when != "before_commit" else "request_validated")
    with pytest.raises(SafetyError):
        InvocationJournal(StateStore(state.path)).claim(
            {**owner(), "owner_id": "new-run"}, "new", time.time() + 10
        )


def test_prepared_recovery_preserves_original_deadline_and_id(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.sqlite")
    journal = InvocationJournal(state)
    deadline = time.time() + 20
    identifier = journal.claim(owner(), "artifact", deadline)
    recovered = InvocationJournal(StateStore(state.path))
    assert recovered.claim(owner(), "artifact", time.time() + 100) == identifier
    with state.connect() as db:
        assert (
            db.execute(
                "SELECT deadline FROM model_invocations WHERE id=?", (identifier,)
            ).fetchone()[0]
            == deadline
        )


def test_caller_commit_rollback_cannot_ack_or_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = StateStore(tmp_path / "state.sqlite")
    state.import_plan("goal", "spec", [task(status="ready")])
    _, execution = state.claim("TASK-001", "run", 3)
    journal = InvocationJournal(state)
    call = journal.claim({**owner(), "owner_id": execution}, "artifact", time.time() + 20)
    phases = [
        "prepared",
        "launch_reserved",
        "request_validated",
        "upstream_reserved",
        "terminal_validated",
        "cli_validated",
    ]
    for before, after in zip(phases, phases[1:], strict=False):
        journal.advance(call, before, after)

    def crash(*args: Any) -> None:
        raise OSError("synthetic caller commit interruption")

    with monkeypatch.context() as patch:
        patch.setattr(state, "_event", crash)
        with pytest.raises(OSError):
            state.finish_execution(execution, "returned", {"status": "implemented"})
    with pytest.raises(SafetyError):
        journal.acknowledge(call)
    with pytest.raises(SafetyError):
        InvocationJournal(StateStore(state.path)).claim(
            {**owner(), "owner_id": "new-run"}, "artifact", time.time() + 10
        )


def test_reasoning_snapshot_cannot_change_without_supported_updates() -> None:
    gate = ResponseGate(MODEL)
    gate.feed(wire(frames()[:1]))
    value = {"type": "reasoning", "id": "r", "summary": []}
    gate.feed(
        wire(
            [
                (
                    "response.output_item.added",
                    {"type": "response.output_item.added", "output_index": 0, "item": value},
                )
            ]
        )
    )
    changed = {**value, "encrypted_content": "different"}
    with pytest.raises(SafetyError):
        gate.feed(
            wire(
                [
                    (
                        "response.output_item.done",
                        {"type": "response.output_item.done", "output_index": 0, "item": changed},
                    )
                ]
            )
        )


@pytest.mark.parametrize("role", ["worker", "reviewer"])
def test_real_caller_result_ack_and_idempotent_recovery(tmp_path: Path, role: str) -> None:
    state = StateStore(tmp_path / "state.sqlite")
    state.import_plan("synthetic goal", "spec", [task(status="ready")])
    work, execution = state.claim("TASK-001", "run", 3)
    journal = InvocationJournal(state)
    bound = {**owner(role), "owner_id": execution}
    call = journal.claim(bound, "artifact", time.time() + 30)
    steps = [
        "prepared",
        "launch_reserved",
        "request_validated",
        "upstream_reserved",
        "terminal_validated",
        "cli_validated",
    ]
    for before, after in zip(steps, steps[1:], strict=False):
        journal.advance(call, before, after)
    runner = CodexRunner(tmp_path, state=state)
    runner.pending_model = (journal, call)
    with pytest.raises(SafetyError):
        runner.acknowledge()
    if role == "worker":
        state.finish_execution(execution, "returned", {"task_id": work.id, "status": "implemented"})
    else:
        state.evidence(
            "reviews",
            work.id,
            {"task_id": work.id, "disposition": "pass", "findings": []},
            "existing-binding",
        )
    runner.acknowledge()
    InvocationJournal(StateStore(state.path)).acknowledge(call)
    with pytest.raises(SafetyError):
        journal.claim(bound, "artifact", time.time() + 20)


def test_profile_original_reparse_and_owner_fail_before_auth_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config = home / "config.toml"
    config.write_text('cli_auth_credentials_store="keyring"', encoding="utf-8")
    state = StateStore(tmp_path / "state.sqlite")
    profile = {
        "home": str(home.resolve()),
        "backend": "keyring",
        "sid": "synthetic-sid",
        "config_hash": fingerprint(config.read_text(encoding="utf-8")),
        "key_metadata": "nonsecret-header",
        "ciphertext_identity": None,
        "protection": {},
    }
    state.set_metadata("c_min_auth_profile", profile)
    monkeypatch.setenv("CODEX_HOME", str(home))
    calls = []
    monkeypatch.setattr("loop_engine.c_min_runtime.key_metadata", lambda *a, **k: calls.append(1))
    monkeypatch.setattr("loop_engine.c_min_runtime.reparse", lambda p: p == home)
    with pytest.raises(SafetyError, match="reparse"):
        verify_profile(state)
    assert calls == []
    monkeypatch.setattr("loop_engine.c_min_runtime.reparse", lambda p: False)
    monkeypatch.setattr(
        "loop_engine.c_min_runtime.Native",
        lambda: SimpleNamespace(current_sid=lambda: "synthetic-sid"),
    )
    monkeypatch.setattr(
        "loop_engine.c_min_runtime.key_metadata", lambda *a, **k: "nonsecret-header"
    )
    monkeypatch.setattr("loop_engine.c_min_runtime.file_security", lambda p: ("wrong-owner", 0, []))
    with pytest.raises(SafetyError, match="owner"):
        verify_profile(state)


@pytest.mark.parametrize("reason", ["pid", "sid", "job", "creation", "exited"])
def test_owned_peer_binding_failure_cannot_authorize(
    reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer = object.__new__(OwnedCliPeer)
    peer.pid = 123
    peer.owner = "synthetic-sid"

    def active() -> None:
        if reason in {"job", "creation", "exited"}:
            raise SafetyError("Owned CLI lifetime changed")

    monkeypatch.setattr(peer, "_require_active", active)

    def authorize(*args: Any, **kwargs: Any) -> bool:
        assert kwargs["expected_pid"] == 123
        if reason in {"pid", "sid"}:
            raise SafetyError("Kernel peer identity differs")
        return True

    monkeypatch.setattr("loop_engine.windows_tcp_peer.require_loopback_peer", authorize)
    with pytest.raises(SafetyError):
        peer(object())  # type: ignore[arg-type]
