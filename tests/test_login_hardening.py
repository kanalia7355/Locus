"""Login hardening tests for T-PH7-221: password strength + account lockout."""

from __future__ import annotations

import time

import pytest
from app.password_rules import LOCK_FAILURE_THRESHOLD
from fastapi import HTTPException

from tests.test_api import ORIGIN, client_for, login


def _alice_id(service) -> str:
    with service.db() as db:
        row = db.execute("SELECT id FROM users WHERE username=?", ("alice",)).fetchone()
        assert row is not None
        return row["id"]


def _throttle(service, key: str):
    with service.db() as db:
        return db.execute(
            "SELECT failures, locked_until, last_failure FROM login_throttle WHERE user_id=?",
            (key,),
        ).fetchone()


# Each case is individually listed in AC1. These passwords are constructed to fail the
# intended rule while otherwise being plausible 14+ char inputs where relevant.
WEAK_CASES = [
    ("too_short", "alice", "Abcdefgh1!jKl"),  # 13 chars, < 14
    ("repeat5", "alice", "Aaaaa1!bcdefgh"),  # same character repeated 5+ times
    ("sequence5", "alice", "Abcde1!fghijkl"),  # ASCII consecutive sequence (abcde)
    ("two_types", "alice", "acegikmoqsuwy!"),  # only lower + symbol (2 types), no sequence
    ("contains_username", "alice", "Alice-Strong-1!"),  # contains username (case-insensitive)
    ("weak_list_exact", "alice", "Valid-Password-00!"),  # exact match in weak_passwords.txt
]


@pytest.mark.parametrize("case, username, password", WEAK_CASES, ids=[c[0] for c in WEAK_CASES])
def test_password_strength_rejected_on_provision(service, case, username, password):
    weak = "Alice-Strong-1!" if case == "contains_username" else password
    # Service direct: _provision path (strength is checked before duplicate handling).
    with pytest.raises(HTTPException) as exc:
        service.provision("alice", weak)
    assert exc.value.status_code == 422
    # Also reject for a fresh username to exercise the normal provision path.
    with pytest.raises(HTTPException) as exc2:
        service.provision("freshuser1", weak if case != "contains_username" else "Freshuser1-Ok!!")
    assert exc2.value.status_code == 422


@pytest.mark.parametrize("case, username, password", WEAK_CASES, ids=[c[0] for c in WEAK_CASES])
def test_password_strength_rejected_on_rotate_api_and_service(service, case, username, password):
    # Service direct: rotate path (alice must be authenticated/rotatable)
    client = client_for(service)
    login(client, "alice", "02")
    token = client.cookies.get("locus_session")
    actor = service.authenticate(token, allow_rotation=False)

    weak = password
    if case == "contains_username":
        weak = "Alice-Strong-1!"  # contains alice

    with pytest.raises(HTTPException) as exc:
        service.rotate(actor, "Changed-password-long-01!", weak, session_token=token)
    assert exc.value.status_code == 422

    # API: /api/auth/password
    resp = client.post(
        "/api/auth/password",
        json={"current_password": "Changed-password-long-01!", "new_password": weak},
        headers=ORIGIN,
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("case, username, password", WEAK_CASES, ids=[c[0] for c in WEAK_CASES])
def test_password_strength_rejected_on_recover_api_and_service(service, case, username, password):
    weak = password
    if case == "contains_username":
        weak = "Alice-Strong-1!"

    # Service direct: recover path
    code = service.issue_recovery("alice")
    with pytest.raises(HTTPException) as exc:
        service.recover("alice", code, weak)
    assert exc.value.status_code == 422
    # Recovery code is not consumed on 422; issue a fresh one for the API call.
    code2 = service.issue_recovery("alice")

    # API: /api/auth/recovery
    client = client_for(service)
    resp = client.post(
        "/api/auth/recovery",
        json={"username": "alice", "recovery_code": code2, "new_password": weak},
        headers=ORIGIN,
    )
    assert resp.status_code == 422


def test_password_rejection_does_not_leak_secret(service, caplog):
    # Weak (5-repeat) input: must never appear in responses, logs, or audit output.
    secret = "A" + "aaaa" + "1!bcdefgh"

    # rotate service direct
    client = client_for(service)
    login(client, "alice", "02")
    token = client.cookies.get("locus_session")
    actor = service.authenticate(token)
    with caplog.at_level("DEBUG"):
        with pytest.raises(HTTPException) as exc:
            service.rotate(actor, "Changed-password-long-01!", secret, session_token=token)
    assert exc.value.status_code == 422
    assert secret not in str(exc.value.detail)
    assert str(len(secret)) not in str(exc.value.detail)  # do not leak length
    assert secret not in caplog.text

    # rotate API
    resp = client.post(
        "/api/auth/password",
        json={"current_password": "Changed-password-long-01!", "new_password": secret},
        headers=ORIGIN,
    )
    assert resp.status_code == 422
    assert secret not in resp.text
    assert secret not in caplog.text

    # recover API
    code = service.issue_recovery("alice")
    recovery_client = client_for(service)
    resp = recovery_client.post(
        "/api/auth/recovery",
        json={"username": "alice", "recovery_code": code, "new_password": secret},
        headers=ORIGIN,
    )
    assert resp.status_code == 422
    assert secret not in resp.text
    assert secret not in caplog.text

    # audit must not contain the secret
    admin = client_for(service)
    login(admin, "admin", "01")
    assert secret not in admin.get("/api/admin/audit").text


def _fail_login(client, username: str, password: str):
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers=ORIGIN,
    )
    service = client.app.state.service
    service.limits.clear()  # avoid 60s burst limiter; DB lock is under test
    return resp


def test_lockout_triggers_after_threshold_and_rejects_correct_password(service):
    client = client_for(service)
    alice_id = _alice_id(service)

    for _ in range(LOCK_FAILURE_THRESHOLD):
        service.limits.clear()
        resp = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "Synthetic-test-password-01!"},
            headers=ORIGIN,
        )
        assert resp.status_code == 401

    row = _throttle(service, alice_id)
    assert row is not None and row["failures"] >= LOCK_FAILURE_THRESHOLD
    assert row["locked_until"] > time.time()

    service.limits.clear()
    # Correct password must be rejected while locked (lock is actually in effect).
    ok = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Temporary-password-02!"},
        headers=ORIGIN,
    )
    assert ok.status_code == 401


def test_lockout_auto_expires_does_not_extend_and_does_not_lock_out_others(service):
    client = client_for(service)
    alice_id = _alice_id(service)

    # (a) auto-unlocks when locked_until is in the past
    with service.db() as db:
        db.execute(
            "INSERT OR REPLACE INTO login_throttle "
            "(user_id, failures, locked_until, last_failure) VALUES (?,?,?,?)",
            (alice_id, LOCK_FAILURE_THRESHOLD, time.time() - 10, time.time() - 20),
        )
    service.limits.clear()
    resp = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Temporary-password-02!"},
        headers=ORIGIN,
    )
    assert resp.status_code == 200

    # (b) additional failures during lock must not extend locked_until
    with service.db() as db:
        db.execute(
            "INSERT OR REPLACE INTO login_throttle "
            "(user_id, failures, locked_until, last_failure) VALUES (?,?,?,?)",
            (alice_id, LOCK_FAILURE_THRESHOLD, time.time() + 3600, time.time()),
        )
    with service.db() as db:
        original = db.execute(
            "SELECT locked_until FROM login_throttle WHERE user_id=?", (alice_id,)
        ).fetchone()["locked_until"]

    for _ in range(3):
        service.limits.clear()
        client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "Synthetic-test-password-01!"},
            headers=ORIGIN,
        )
    with service.db() as db:
        after = db.execute(
            "SELECT locked_until FROM login_throttle WHERE user_id=?", (alice_id,)
        ).fetchone()["locked_until"]
    assert after == original

    # (c) attacker failing alice must not prevent attacker's own login
    attacker = client_for(service)
    service.limits.clear()
    # alice is currently locked above; attacker keeps failing alice
    for _ in range(3):
        service.limits.clear()
        attacker.post(
            "/api/auth/login",
            json={"username": "alice", "password": "Synthetic-test-password-01!"},
            headers=ORIGIN,
        )
    service.limits.clear()
    bob_login = attacker.post(
        "/api/auth/login",
        json={"username": "bob", "password": "Temporary-password-03!"},
        headers=ORIGIN,
    )
    assert bob_login.status_code == 200


def test_successful_login_resets_failures_and_next_failure_is_first(service):
    client = client_for(service)
    alice_id = _alice_id(service)
    service.limits.clear()

    # cause some failures
    for _ in range(3):
        service.limits.clear()
        client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "Synthetic-test-password-01!"},
            headers=ORIGIN,
        )
    assert _throttle(service, alice_id)["failures"] == 3

    # successful login resets
    service.limits.clear()
    ok = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Temporary-password-02!"},
        headers=ORIGIN,
    )
    assert ok.status_code == 200
    assert _throttle(service, alice_id)["failures"] == 0

    # next failure counts as 1
    service.limits.clear()
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Synthetic-test-password-01!"},
        headers=ORIGIN,
    )
    assert _throttle(service, alice_id)["failures"] == 1


def test_locked_unknown_and_wrong_password_have_same_response(service):
    client = client_for(service)
    alice_id = _alice_id(service)

    # lock alice
    with service.db() as db:
        db.execute(
            "INSERT OR REPLACE INTO login_throttle "
            "(user_id, failures, locked_until, last_failure) VALUES (?,?,?,?)",
            (alice_id, LOCK_FAILURE_THRESHOLD, time.time() + 3600, time.time()),
        )
    service.limits.clear()

    locked = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Temporary-password-02!"},
        headers=ORIGIN,
    )
    service.limits.clear()
    wrong = client.post(
        "/api/auth/login",
        json={"username": "bob", "password": "Synthetic-test-password-01!"},
        headers=ORIGIN,
    )
    service.limits.clear()
    unknown = client.post(
        "/api/auth/login",
        json={"username": "no-such-user", "password": "Synthetic-test-password-01!"},
        headers=ORIGIN,
    )

    assert locked.status_code == wrong.status_code == unknown.status_code == 401
    assert locked.json() == wrong.json() == unknown.json()


def test_admin_unlock_requires_system_admin_and_is_audited(service):
    alice_id = _alice_id(service)
    with service.db() as db:
        bob_id = db.execute("SELECT id FROM users WHERE username=?", ("bob",)).fetchone()["id"]

    # Lock both alice and bob in the throttle table.
    with service.db() as db:
        db.execute(
            "INSERT OR REPLACE INTO login_throttle "
            "(user_id, failures, locked_until, last_failure) VALUES (?,?,?,?)",
            (alice_id, LOCK_FAILURE_THRESHOLD, time.time() + 3600, time.time()),
        )
        db.execute(
            "INSERT OR REPLACE INTO login_throttle "
            "(user_id, failures, locked_until, last_failure) VALUES (?,?,?,?)",
            (bob_id, LOCK_FAILURE_THRESHOLD, time.time() + 3600, time.time()),
        )

    # Non-admin cannot unlock.
    bob_client = client_for(service)
    # Clear bob's lock temporarily so he can log in to obtain a session, then re-lock.
    with service.db() as db:
        db.execute(
            "UPDATE login_throttle SET locked_until=0, failures=0 WHERE user_id=?",
            (bob_id,),
        )
    service.limits.clear()
    login(bob_client, "bob", "03")
    with service.db() as db:
        db.execute(
            "INSERT OR REPLACE INTO login_throttle "
            "(user_id, failures, locked_until, last_failure) VALUES (?,?,?,?)",
            (bob_id, LOCK_FAILURE_THRESHOLD, time.time() + 3600, time.time()),
        )
    resp = bob_client.put(f"/api/admin/users/{alice_id}/unlock", headers=ORIGIN)
    assert resp.status_code == 403

    # System admin can unlock and it is audited.
    admin = client_for(service)
    login(admin, "admin", "01")
    admin_principal = service.authenticate(admin.cookies.get("locus_session"))
    resp = admin.put(f"/api/admin/users/{alice_id}/unlock", headers=ORIGIN)
    assert resp.status_code == 200

    audit_entries = service.audit(admin_principal)
    assert any(
        e.get("operation") == "account.unlock" and e.get("target_id") == alice_id
        for e in audit_entries
    )

    # Unlocked -> alice can log in with correct password.
    service.limits.clear()
    relogin = client_for(service)
    ok = relogin.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Temporary-password-02!"},
        headers=ORIGIN,
    )
    assert ok.status_code == 200
