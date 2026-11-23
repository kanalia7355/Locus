"""Synthetic egress-gate regressions for the Harness (T-AIC-005)."""

from __future__ import annotations

import pytest
from app.harness import Harness
from fastapi import HTTPException


class ExplodingAdapter:
    def send(self, **_kwargs):
        raise AssertionError("adapter must not be called when egress is denied")


class AdapterSpy:
    def __init__(self):
        self.calls: list[dict] = []

    def send(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


def _audit_rows(service):
    return service.conn.execute(
        "SELECT actor_id,operation,target_id,outcome FROM audit "
        "WHERE operation='harness.egress' ORDER BY at"
    ).fetchall()


def _policy(classification="public", egress_mode="local_only"):
    return {"classification_ceiling": classification, "egress_mode": egress_mode}


def test_local_only_denies_and_never_calls_adapter(service):
    spy = ExplodingAdapter()
    harness = Harness(
        get_policy=lambda _w: _policy("public", "local_only"),
        adapter=spy,
        resolve_credential=lambda _a: "sk-synthetic-01-not-a-real-key",
        audit=service._audit,
        db=service.conn,
    )
    with pytest.raises(HTTPException) as exc:
        harness.send("user-1", "ws-1", "model-a", "secret body", [], None)
    assert exc.value.status_code == 403
    assert exc.value.detail == "外部送信は許可されていません"


def test_none_classification_denied(service):
    # "none" means no classification permitted; missing/unclassified => deny.
    spy = ExplodingAdapter()
    harness = Harness(
        get_policy=lambda _w: _policy("none", "allowlisted"),
        adapter=spy,
        resolve_credential=lambda _a: "sk-synthetic-01-not-a-real-key",
        audit=service._audit,
        db=service.conn,
    )
    with pytest.raises(HTTPException) as exc:
        harness.send("user-1", "ws-1", "model-a", "body", [], None)
    assert exc.value.status_code == 403


def test_unknown_classification_and_missing_policy_denied(service):
    spy = ExplodingAdapter()
    for get_policy in [
        lambda _w: _policy("mystery", "allowlisted"),
        lambda _w: None,
    ]:
        harness = Harness(
            get_policy=get_policy,
            adapter=spy,
            resolve_credential=lambda _a: "sk-synthetic-02-not-a-real-key",
            audit=service._audit,
            db=service.conn,
        )
        with pytest.raises(HTTPException) as exc:
            harness.send("user-1", "ws-1", "model-a", "body", [], None)
        assert exc.value.status_code == 403


def test_denial_is_audited_without_body_or_credential(service):
    secret = "sk-synthetic-03-not-a-real-key"
    body = "TOP SECRET BODY MUST NOT BE AUDITED"
    harness = Harness(
        get_policy=lambda _w: _policy("public", "local_only"),
        adapter=ExplodingAdapter(),
        resolve_credential=lambda _a: secret,
        audit=service._audit,
        db=service.conn,
    )
    with pytest.raises(HTTPException):
        harness.send("user-1", "ws-audit", "model-a", body, [{"cite": body}], None)

    rows = _audit_rows(service)
    assert rows
    row = rows[-1]
    assert row["actor_id"] == "user-1"
    assert row["operation"] == "harness.egress"
    assert row["outcome"] == "denied"
    assert "ws-audit" in row["target_id"]
    assert "destination=external_model" in row["target_id"]
    assert "model=model-a" in row["target_id"]
    assert body not in row["target_id"]
    assert secret not in row["target_id"]

    raw = "\n".join(str(r) for r in service.conn.execute("SELECT * FROM audit").fetchall())
    assert body not in raw
    assert secret not in raw


def test_default_resolve_credential_denies(service):
    spy = ExplodingAdapter()
    harness = Harness(
        get_policy=lambda _w: _policy("public", "allowlisted"),
        adapter=spy,
        audit=service._audit,
        db=service.conn,
    )
    with pytest.raises(HTTPException) as exc:
        harness.send("user-1", "ws-1", "model-a", "body", [], None)
    assert exc.value.status_code == 403
    rows = _audit_rows(service)
    assert rows
    assert "reason=credential_unavailable" in rows[-1]["target_id"]


def test_allowed_case_calls_adapter_and_does_not_store_credential(service):
    secret = "sk-synthetic-04-not-a-real-key"
    spy = AdapterSpy()
    harness = Harness(
        get_policy=lambda _w: _policy("public", "allowlisted"),
        adapter=spy,
        resolve_credential=lambda _a: secret,
        audit=service._audit,
        db=service.conn,
    )
    result = harness.send("user-1", "ws-ok", "model-ok", "hello", ["c"], None)

    assert result == {"ok": True}
    assert len(spy.calls) == 1
    call = spy.calls[0]
    assert call["credential"] == secret
    assert call["actor"] == "user-1"
    assert call["workspace"] == "ws-ok"
    assert call["model"] == "model-ok"

    # Credential must not be stored on harness or adapter objects.
    assert secret not in repr(vars(harness))
    assert secret not in repr(vars(Harness))
    assert secret not in repr(vars(AdapterSpy))
    assert secret not in repr(vars(spy.__class__))

    rows = _audit_rows(service)
    assert rows
    assert rows[-1]["outcome"] == "allowed"
    assert secret not in rows[-1]["target_id"]
