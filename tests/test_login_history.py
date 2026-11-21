"""Login history recording and admin-only viewing (IAM-005 / IAM-016)."""

from __future__ import annotations

import time

from app.service import Service

from tests.test_api import ORIGIN, client_for, login

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login_events(service: Service) -> list[dict]:
    """Return all login_events rows as dicts, newest first."""
    with service.db() as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT id, at, user_id, username_digest, outcome, peer, user_agent "
                "FROM login_events ORDER BY at DESC"
            ).fetchall()
        ]


def _admin_login_history(client, limit: int = 200) -> list[dict]:
    return client.get("/api/admin/login-history", params={"limit": limit}, headers=ORIGIN).json()


# ========================================================================
# AC1: basic recording
# ========================================================================


def test_success_login_records_event(service: Service) -> None:
    """Success login 1回で outcome='success' の行が 1 行増える."""
    before = len(_login_events(service))
    client = client_for(service)
    login(client)  # alice / Temporary-password-02!
    after = len(_login_events(service))
    assert after == before + 1, f"Expected {before + 1} events, got {after}"
    with service.db() as db:
        row = db.execute("SELECT outcome FROM login_events ORDER BY at DESC LIMIT 1").fetchone()
    assert row is not None
    assert row["outcome"] == "success"


def test_bad_password_records_event(service: Service) -> None:
    """Bad password leaves a record (outcome='bad_password') even when 401 is returned."""
    before = len(_login_events(service))
    client = client_for(service)
    resp = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},  # pragma: allowlist secret
        headers=ORIGIN,
    )
    assert resp.status_code == 401
    after = len(_login_events(service))
    assert after == before + 1, f"Expected {before + 1} events, got {after}"
    with service.db() as db:
        row = db.execute("SELECT outcome FROM login_events ORDER BY at DESC LIMIT 1").fetchone()
    assert row is not None
    assert row["outcome"] == "bad_password"


def test_unknown_user_records_event(service: Service) -> None:
    """Unknown user ID: user_id IS NULL, outcome='unknown_user', input string not stored."""
    before = len(_login_events(service))
    client = client_for(service)
    resp = client.post(
        "/api/auth/login",
        json={"username": "no-such-user", "password": "anything"},  # pragma: allowlist secret
        headers=ORIGIN,
    )
    assert resp.status_code == 401
    after = len(_login_events(service))
    assert after == before + 1, f"Expected {before + 1} events, got {after}"
    with service.db() as db:
        row = db.execute("SELECT * FROM login_events ORDER BY at DESC LIMIT 1").fetchone()
    assert row is not None
    assert row["user_id"] is None
    assert row["outcome"] == "unknown_user"
    # The raw input username must not appear in any column.
    for col_name in row.keys():
        val = str(row[col_name])
        assert "no-such-user" not in val, f"input username found in column {col_name}: {val}"


def test_disabled_user_outcome(service: Service) -> None:
    """Disabled user login attempt records outcome='disabled'."""
    with service.db() as db:
        db.execute("UPDATE users SET enabled=0 WHERE username='alice'")
    client = client_for(service)
    resp = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Temporary-password-02!"},
        headers=ORIGIN,
    )
    assert resp.status_code == 401
    with service.db() as db:
        row = db.execute("SELECT outcome FROM login_events ORDER BY at DESC LIMIT 1").fetchone()
    assert row is not None
    assert row["outcome"] == "disabled"


def test_temp_expired_outcome(service: Service) -> None:
    """Expired temporary password records outcome='temp_expired'."""
    with service.db() as db:
        db.execute(
            "UPDATE users SET must_rotate=1, temp_expires=?, temp_used=0 WHERE username='alice'",
            (time.time() - 10,),
        )
    client = client_for(service)
    resp = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Temporary-password-02!"},
        headers=ORIGIN,
    )
    assert resp.status_code == 401
    with service.db() as db:
        row = db.execute("SELECT outcome FROM login_events ORDER BY at DESC LIMIT 1").fetchone()
    assert row is not None
    assert row["outcome"] == "temp_expired"


def test_locked_outcome(service: Service) -> None:
    """Locked account records outcome='locked' (T-PH7-221 lock)."""
    with service.db() as db:
        alice = db.execute("SELECT id FROM users WHERE username='alice'").fetchone()
        db.execute(
            "INSERT OR REPLACE INTO login_throttle "
            "(user_id, failures, locked_until, last_failure) VALUES (?,?,?,?)",
            (alice["id"], 10, time.time() + 3600, time.time()),
        )
    client = client_for(service)
    resp = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Temporary-password-02!"},
        headers=ORIGIN,
    )
    assert resp.status_code == 401
    with service.db() as db:
        row = db.execute("SELECT outcome FROM login_events ORDER BY at DESC LIMIT 1").fetchone()
    assert row is not None
    assert row["outcome"] == "locked"


# ========================================================================
# AC2: password does not leak
# ========================================================================


def test_password_string_not_leaked(service: Service, caplog) -> None:
    """A distinctive password string must not appear in login_events, admin history,
    audit response, or caplog."""
    secret = "Zebra-canyon-77!-secret"  # pragma: allowlist secret
    client = client_for(service)
    resp = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": secret},
        headers=ORIGIN,
    )
    assert resp.status_code == 401

    # DB: all rows, all columns.
    with service.db() as db:
        for row in db.execute("SELECT * FROM login_events").fetchall():
            for col_name in row.keys():
                assert secret not in str(row[col_name]), (
                    f"secret found in {col_name}: {row[col_name]}"
                )

    admin = client_for(service)
    login(admin, "admin", "01")
    admin_history = admin.get("/api/admin/login-history", headers=ORIGIN).text
    assert secret not in admin_history
    admin_audit = admin.get("/api/admin/audit", headers=ORIGIN).text
    assert secret not in admin_audit
    assert secret not in caplog.text


def test_password_length_not_leaked(service: Service) -> None:
    """Two wrong passwords of different lengths must produce rows identical in shape
    (no column/value depends on password length)."""
    client = client_for(service)
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "ShortP@ss1!"},  # pragma: allowlist secret
        headers=ORIGIN,
    )
    long_pw = "A" * 60 + "!B1longer-padding"
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": long_pw},
        headers=ORIGIN,
    )
    with service.db() as db:
        rows = db.execute(
            "SELECT id, at, user_id, username_digest, outcome, peer, user_agent "
            "FROM login_events WHERE outcome='bad_password' ORDER BY at DESC LIMIT 2"
        ).fetchall()
    assert len(rows) >= 2
    r1, r2 = dict(rows[0]), dict(rows[1])
    # id and at naturally differ; all other stored columns must be identical.
    for key in ("user_id", "username_digest", "outcome", "peer", "user_agent"):
        assert r1[key] == r2[key], (
            f"Column {key} differs between different-length password attempts: "
            f"{r1[key]!r} vs {r2[key]!r}"
        )


# ========================================================================
# AC3: non-admin cannot read
# ========================================================================


def test_non_admin_cannot_read_login_history(service: Service) -> None:
    """Regular user gets 403; unauthenticated gets 401. No self-read path exists."""
    alice = client_for(service)
    login(alice)
    resp = alice.get("/api/admin/login-history", headers=ORIGIN)
    assert resp.status_code == 403

    anon = client_for(service)
    resp = anon.get("/api/admin/login-history", headers=ORIGIN)
    assert resp.status_code == 401


# ========================================================================
# AC4: attack pattern visible
# ========================================================================


def test_attack_pattern_visible(service: Service) -> None:
    """Admin response must reveal: consecutive failure count, same peer across
    multiple accounts, and success immediately after failures."""
    client = client_for(service)
    # 5 failures on alice
    for _ in range(5):
        client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong-pass"},  # pragma: allowlist secret
            headers=ORIGIN,
        )
    # 3 failures on bob from same connection
    for _ in range(3):
        client.post(
            "/api/auth/login",
            json={"username": "bob", "password": "wrong-pass"},  # pragma: allowlist secret
            headers=ORIGIN,
        )
    # Success on bob
    client.post(
        "/api/auth/login",
        json={"username": "bob", "password": "Temporary-password-03!"},
        headers=ORIGIN,
    )

    admin = client_for(service)
    login(admin, "admin", "01")
    history = _admin_login_history(admin)

    # 1) Consecutive failure count is discernible.
    bad_password_events = [e for e in history if e["outcome"] == "bad_password"]
    assert len(bad_password_events) >= 8

    # 2) Same peer tried multiple accounts.
    peers_by_user: dict[str | None, set[str]] = {}
    for e in history:
        peers_by_user.setdefault(e["username"], set()).add(e["peer"])
    users_with_failures = {e["username"] for e in history if e["outcome"] == "bad_password"}
    assert "alice" in users_with_failures
    assert "bob" in users_with_failures
    # At least one peer appears for both alice and bob failure events.
    alice_peers = {e["peer"] for e in history if e["username"] == "alice"}
    bob_peers = {e["peer"] for e in history if e["username"] == "bob"}
    assert alice_peers & bob_peers, "same peer should appear across multiple accounts"

    # 3) Success immediately after failures is discernible.
    # History is newest-first; find bob's success and confirm earlier bad_passwords exist.
    success_events = [e for e in history if e["outcome"] == "success"]
    assert any(e["username"] == "bob" for e in success_events)
    bob_success_at = max(e["at"] for e in success_events if e["username"] == "bob")
    bob_failures_before = [
        e for e in history if e["username"] == "bob" and e["outcome"] == "bad_password"
    ]
    assert bob_failures_before
    assert any(e["at"] < bob_success_at for e in bob_failures_before)


# ========================================================================
# AC5: retention limit
# ========================================================================


def test_retention_prunes_old_rows(service: Service, monkeypatch) -> None:
    """Retention limit removes old rows and keeps new rows when set small."""
    import app.service as service_module

    # Insert an old login event directly.
    with service.db() as db:
        db.execute(
            "INSERT INTO login_events VALUES (?,?,?,?,?,?,?)",
            (
                "old-event-1",
                time.time() - 7200,
                None,
                "olddigest",
                "bad_password",
                "127.0.0.1",
                None,
            ),
        )
    # Set retention very small so the old row is outside the window.
    monkeypatch.setattr(service_module, "LOGIN_HISTORY_RETENTION_SECONDS", 10)

    client = client_for(service)
    # This login triggers pruning.
    login(client)

    with service.db() as db:
        old = db.execute("SELECT id FROM login_events WHERE id='old-event-1'").fetchone()
        new_rows = db.execute("SELECT id FROM login_events WHERE outcome='success'").fetchall()
    assert old is None, "old row should have been pruned"
    assert len(new_rows) >= 1, "new success row should remain"
