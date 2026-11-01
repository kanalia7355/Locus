"""Mock-only Review admission/execution and retained attempt-binding tests."""

import base64
import time
from types import SimpleNamespace

import pytest
from test_loop_audit_spool import findings, packet

from loop_engine.audit_packet import canonical, digest
from loop_engine.audit_runtime import AdmittedAuthority, fixed_self_test, review_request
from loop_engine.audit_spool import AuditSpool
from loop_engine.security import SafetyError


def test_only_review_principal_can_admit_or_execute(tmp_path):
    deployment = SimpleNamespace(
        settings={"review_sid": "review", "operator_sid": "owner"}, state=tmp_path
    )
    expected, raw = packet()
    for actor in ("owner", "merge", "unknown"):
        with pytest.raises(SafetyError):
            review_request(
                deployment,
                actor,
                {
                    "operation": "reserve",
                    "binding": expected,
                    "packet_hash": digest(raw),
                    "size": len(raw),
                },
                deadline=time.monotonic() + 10,
            )
    assert not list(tmp_path.iterdir())


def test_admission_cannot_retry_same_source_by_changing_nonce_qa_or_scope(tmp_path):
    spool = AuditSpool(tmp_path)
    authority = AdmittedAuthority(spool)
    expected, raw = packet()
    authority.reserve(
        {"operation": "reserve", "binding": expected, "packet_hash": digest(raw), "size": len(raw)}
    )
    assert authority.current(expected["nonce"]) == expected
    changed = {**expected, "nonce": "d" * 64, "qa": "e" * 64, "scope": "project"}
    with pytest.raises(SafetyError):
        authority.reserve(
            {
                "operation": "reserve",
                "binding": changed,
                "packet_hash": digest(raw),
                "size": len(raw),
            }
        )
    assert AdmittedAuthority(AuditSpool(tmp_path)).current(expected["nonce"]) == expected


def test_review_packets_run_model_once_and_findings_transport_has_no_signing(tmp_path, monkeypatch):
    import loop_engine.audit_runtime as module

    calls = []

    class Model:
        def __init__(self, deployment):
            pass

        def review(self, value, *, timeout, cancelled):
            calls.append(value)
            return findings()

    monkeypatch.setattr(module, "RuntimeModel", Model)
    deployment = SimpleNamespace(
        settings={"review_sid": "review", "operator_sid": "owner"}, state=tmp_path
    )
    expected, raw = packet()

    def request(body):
        return review_request(deployment, "review", body, deadline=time.monotonic() + 10)

    request(
        {"operation": "reserve", "binding": expected, "packet_hash": digest(raw), "size": len(raw)}
    )
    request(
        {
            "operation": "chunk",
            "binding": expected,
            "index": 0,
            "data": base64.b64encode(raw).decode(),
        }
    )
    result = request({"operation": "run", "binding": expected})
    assert result["activated"] is False and len(calls) == 1
    chunk = request({"operation": "findings_chunk", "binding": expected, "index": 0})
    assert base64.b64decode(chunk["data"]) == canonical(findings())
    request({"operation": "ack", "binding": expected, "findings_hash": result["findings_hash"]})
    with pytest.raises(SafetyError):
        request({"operation": "run", "binding": expected})
    assert len(calls) == 1


def test_fixed_synthetic_model_trial_is_not_arbitrary_input_or_repeatable(tmp_path, monkeypatch):
    import loop_engine.audit_runtime as module

    calls = []

    class Model:
        def __init__(self, deployment):
            pass

        def review(self, value, *, timeout, cancelled):
            calls.append(value)
            assert "return True" in value["files"][0]["head"]
            assert value["binding"]["task_id"] == "TASK-000"
            return {
                "task_id": "TASK-000",
                "disposition": "fail",
                "findings": [
                    {
                        "severity": "high",
                        "file": "synthetic_authorization.py",
                        "finding": "guest allowed",
                        "evidence": "predicate always True",
                        "recommended_action": "deny guest",
                        "blocking": True,
                    }
                ],
            }

    monkeypatch.setattr(module, "RuntimeModel", Model)
    deployment = SimpleNamespace(state=tmp_path, identity="a" * 64)
    first = fixed_self_test(deployment, deadline=time.monotonic() + 10)
    second = fixed_self_test(deployment, deadline=time.monotonic() + 10)
    assert first["synthetic_only"] and first["bug_detected"] and not first["activated"]
    assert not first["cached"] and second["cached"] and len(calls) == 1


def test_uncertain_synthetic_model_trial_never_replays(tmp_path, monkeypatch):
    import loop_engine.audit_runtime as module

    class Model:
        def __init__(self, deployment):
            pass

        def review(self, *args, **kwargs):
            raise SafetyError("synthetic failure")

    monkeypatch.setattr(module, "RuntimeModel", Model)
    deployment = SimpleNamespace(state=tmp_path, identity="a" * 64)
    with pytest.raises(SafetyError):
        fixed_self_test(deployment, deadline=time.monotonic() + 10)
    with pytest.raises(SafetyError, match="reconciliation"):
        fixed_self_test(deployment, deadline=time.monotonic() + 10)
