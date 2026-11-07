"""Authenticated-peer and binding/deadline protocol tests with a synthetic model."""

import base64
import time

import pytest
from test_loop_audit_spool import findings, packet

from loop_engine.audit_packet import canonical, decode, digest
from loop_engine.audit_spool import AuditSpool
from loop_engine.audit_supervisor import AuditSupervisor
from loop_engine.security import SafetyError


class Authority:
    def __init__(self, expected):
        self.expected = expected

    def current(self, nonce):
        assert nonce == self.expected["nonce"]
        return self.expected


class Model:
    def __init__(self):
        self.calls = []
        self.on_run = lambda: None

    def review(self, value, *, timeout, cancelled):
        assert 0 < timeout <= 300
        assert not cancelled()
        self.calls.append(value)
        self.on_run()
        return findings()


def setup(tmp_path, model=None):
    expected, raw = packet()
    authority = Authority(expected)
    supervisor = AuditSupervisor(
        AuditSpool(tmp_path), authority, review_sid="review", operator_sid="operator", model=model
    )
    return expected, raw, authority, supervisor


def call(supervisor, document, peer="review", **kwargs):
    return supervisor.dispatch(
        peer, document, deadline=time.monotonic() + 10, cancelled=lambda: False, **kwargs
    )


def upload(supervisor, expected, raw):
    call(
        supervisor,
        {"operation": "reserve", "binding": expected, "packet_hash": digest(raw), "size": len(raw)},
    )
    call(
        supervisor,
        {
            "operation": "chunk",
            "binding": expected,
            "index": 0,
            "data": base64.b64encode(raw).decode(),
        },
    )


def test_model_review_chunked_result_and_exact_ack(tmp_path):
    model = Model()
    expected, raw, _, supervisor = setup(tmp_path, model)
    upload(supervisor, expected, raw)
    result = call(supervisor, {"operation": "run", "binding": expected})
    assert len(model.calls) == 1
    assert model.calls[0] == decode(raw)
    meta = call(supervisor, {"operation": "result", "binding": expected})
    assert meta["findings_hash"] == result["findings_hash"]
    chunk = call(supervisor, {"operation": "findings_chunk", "binding": expected, "index": 0})
    assert base64.b64decode(chunk["data"]) == canonical(findings())
    assert len(canonical(chunk)) < 65536
    call(
        supervisor,
        {"operation": "ack", "binding": expected, "findings_hash": result["findings_hash"]},
    )
    with pytest.raises(SafetyError):
        call(supervisor, {"operation": "run", "binding": expected})
    assert len(model.calls) == 1


@pytest.mark.parametrize("peer", ["operator", "merge", "unknown"])
def test_non_review_peer_cannot_submit_or_impersonate(tmp_path, peer):
    expected, raw, _, supervisor = setup(tmp_path)
    request = {
        "operation": "reserve",
        "binding": expected,
        "packet_hash": digest(raw),
        "size": len(raw),
    }
    with pytest.raises(SafetyError):
        call(supervisor, request, peer)
    with pytest.raises(SafetyError):
        call(supervisor, {**request, "peer": "review"}, peer)


@pytest.mark.parametrize("operation", ["publish", "provision", "merge", "shell", "login"])
def test_no_arbitrary_operation(tmp_path, operation):
    expected, _, _, supervisor = setup(tmp_path)
    with pytest.raises(SafetyError):
        call(supervisor, {"operation": operation, "binding": expected})


def test_no_fallback_model_after_durable_execution_reservation(tmp_path):
    expected, raw, _, supervisor = setup(tmp_path)
    upload(supervisor, expected, raw)
    with pytest.raises(SafetyError, match="not proven"):
        call(supervisor, {"operation": "run", "binding": expected})
    with pytest.raises(SafetyError, match="reserved"):
        call(supervisor, {"operation": "run", "binding": expected})


def test_evidence_changed_during_model_run_cannot_finish(tmp_path):
    model = Model()
    expected, raw, authority, supervisor = setup(tmp_path, model)
    upload(supervisor, expected, raw)
    model.on_run = lambda: setattr(authority, "expected", {**expected, "head": "e" * 40})
    with pytest.raises(SafetyError, match="evidence changed"):
        call(supervisor, {"operation": "run", "binding": expected})
    authority.expected = expected
    with pytest.raises(SafetyError):
        call(supervisor, {"operation": "result", "binding": expected})
    with pytest.raises(SafetyError):
        call(supervisor, {"operation": "run", "binding": expected})


@pytest.mark.parametrize(
    "deadline,cancelled",
    [(0, False), (float("nan"), False), (float("inf"), False), (1e30, False), (None, True)],
)
def test_deadline_and_cancellation_before_any_work(tmp_path, deadline, cancelled):
    expected, _, _, supervisor = setup(tmp_path)
    with pytest.raises(SafetyError):
        supervisor.dispatch(
            "review",
            {"operation": "run", "binding": expected},
            deadline=deadline or time.monotonic() + 10,
            cancelled=lambda: cancelled,
        )


def test_cancellation_after_model_prevents_result_and_reexecution(tmp_path):
    model = Model()
    expected, raw, _, supervisor = setup(tmp_path, model)
    upload(supervisor, expected, raw)
    stopped = []
    model.on_run = lambda: stopped.append(True)
    with pytest.raises(SafetyError):
        supervisor.dispatch(
            "review",
            {"operation": "run", "binding": expected},
            deadline=time.monotonic() + 10,
            cancelled=lambda: bool(stopped),
        )
    with pytest.raises(SafetyError):
        call(supervisor, {"operation": "result", "binding": expected})


def test_health_has_no_runtime_or_authentication_claim(tmp_path):
    _, _, _, supervisor = setup(tmp_path)
    assert call(supervisor, {"operation": "health"}, "operator") == {
        "role": "audit",
        "protocol": "locus-audit-packet-v1",
        "activated": False,
    }
    with pytest.raises(SafetyError):
        call(supervisor, {"operation": "health"}, "merge")
