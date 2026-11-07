"""Account state changes are authorized, atomic and immediately revoke sessions."""

import sqlite3

import pytest
from fastapi import HTTPException
from test_api import ORIGIN, client_for, login


def user_id(service, username="alice"):
    return service.conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()[0]


def toggle(client, target, enabled):
    return client.put(
        f"/api/admin/users/{target}/enabled", json={"enabled": enabled}, headers=ORIGIN
    )


def test_disable_revokes_all_sessions_and_enable_only_allows_future_login(service):
    admin, alice, other = (client_for(service) for _ in range(3))
    login(admin, "admin", "01")
    login(alice)
    credentials = {"username": "alice", "password": "Changed-password-long-01!"}
    assert other.post("/api/auth/login", json=credentials, headers=ORIGIN).status_code == 200
    target = user_id(service)
    assert (
        next(row for row in admin.get("/api/admin/users").json() if row["id"] == target)["enabled"]
        is True
    )
    response = toggle(admin, target, False)
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert (
        service.conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id=?", (target,)).fetchone()[
            0
        ]
        == 0
    )
    for client in (alice, other):
        assert client.get("/api/auth/me").status_code == 401
        assert client.get("/api/projects").status_code == 401
        assert (
            client.post(
                "/api/auth/password",
                json={
                    "current_password": credentials["password"],
                    "new_password": "Another-password-02!",
                },
                headers=ORIGIN,
            ).status_code
            == 401
        )
    denied = alice.post("/api/auth/login", json=credentials, headers=ORIGIN)
    assert denied.status_code == 401
    assert denied.json()["detail"] == "利用者IDまたはパスワードを確認してください"
    assert toggle(admin, target, True).json()["enabled"] is True
    assert alice.get("/api/auth/me").status_code == 401
    assert (
        service.conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id=?", (target,)).fetchone()[
            0
        ]
        == 0
    )
    assert alice.post("/api/auth/login", json=credentials, headers=ORIGIN).status_code == 200
    events = service.conn.execute(
        "SELECT actor_id,operation,target_id,outcome FROM audit WHERE operation LIKE 'account.%' "
        "AND operation != 'account.provision' ORDER BY at"
    ).fetchall()
    assert [tuple(row) for row in events] == [
        (user_id(service, "admin"), "account.disable", target, "ok"),
        (user_id(service, "admin"), "account.enable", target, "ok"),
    ]


def test_toggle_requires_system_admin_before_target_lookup(service):
    client = client_for(service)
    assert toggle(client, "missing", False).status_code == 401
    login(client)
    # Project/organization administration is not global account administration.
    service.assign("alice", "project-a", "organization_admin")
    for target in (user_id(service), "missing", user_id(service, "admin")):
        assert toggle(client, target, False).status_code == 403


def test_unknown_self_and_invalid_payload_do_not_change_state_or_audit(service):
    admin = client_for(service)
    login(admin, "admin", "01")
    before = list(service.conn.execute("SELECT * FROM audit"))
    assert toggle(admin, "missing", False).status_code == 404
    assert toggle(admin, user_id(service, "admin"), False).status_code == 422
    for value in ("false", 0, None):
        assert toggle(admin, user_id(service), value).status_code == 422
    assert (
        admin.put(
            f"/api/admin/users/{user_id(service)}/enabled",
            json={"enabled": False, "system_admin": True},
            headers=ORIGIN,
        ).status_code
        == 422
    )
    assert list(service.conn.execute("SELECT * FROM audit")) == before
    assert admin.get("/api/auth/me").status_code == 200


def test_another_system_admin_can_be_disabled_and_is_audited(service):
    service.provision("second-admin", "Temporary-password-05!", system_admin=True)
    admin = client_for(service)
    login(admin, "admin", "01")
    target = user_id(service, "second-admin")
    assert toggle(admin, target, False).status_code == 200
    event = service.conn.execute("SELECT * FROM audit WHERE operation='account.disable'").fetchone()
    assert event["target_id"] == target
    assert event["actor_id"] == user_id(service, "admin")
    denied = client_for(service).post(
        "/api/auth/login",
        json={"username": "second-admin", "password": "Temporary-password-05!"},
        headers=ORIGIN,
    )
    assert denied.status_code == 401


@pytest.mark.parametrize("enabled", [False, True])
def test_toggle_and_session_deletion_roll_back_if_audit_fails(service, monkeypatch, enabled):
    admin, alice = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(alice)
    token = admin.cookies.get("locus_session")
    target = user_id(service)
    if enabled:
        service.set_user_enabled(token, target, False)
    before = list(service.conn.execute("SELECT * FROM audit"))
    sessions = list(service.conn.execute("SELECT * FROM sessions"))

    def broken(*args):
        raise sqlite3.OperationalError("synthetic audit unavailable")

    monkeypatch.setattr(service, "_audit", broken)
    with pytest.raises(sqlite3.OperationalError):
        service.set_user_enabled(token, target, enabled)
    assert service.conn.execute("SELECT enabled FROM users WHERE id=?", (target,)).fetchone()[
        0
    ] == (not enabled)
    assert list(service.conn.execute("SELECT * FROM sessions")) == sessions
    assert list(service.conn.execute("SELECT * FROM audit")) == before


def test_stale_disabled_principals_cannot_rotate_or_toggle(service):
    admin, alice = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(alice)
    admin_token = admin.cookies.get("locus_session")
    alice_token = alice.cookies.get("locus_session")
    actor = service.authenticate(admin_token)
    stale = service.authenticate(alice_token)
    service.set_user_enabled(admin_token, stale.id, False)
    with pytest.raises(HTTPException) as error:
        service.rotate(
            stale,
            "Changed-password-long-01!",
            "Another-password-long-02!",
            session_token=alice_token,
        )
    assert error.value.status_code == 401
    service.set_user_enabled(admin_token, stale.id, True)
    # Re-enabling never revives the purged session; stale request data is not authorization.
    with pytest.raises(HTTPException) as error:
        service.rotate(
            stale,
            "Changed-password-long-01!",
            "Another-password-long-02!",
            session_token=alice_token,
        )
    assert error.value.status_code == 401
    with pytest.raises(HTTPException) as error:
        service.set_user_enabled(alice_token, actor.id, False)
    assert error.value.status_code == 401
    with service.db() as db:
        db.execute("UPDATE users SET enabled=0 WHERE id=?", (actor.id,))
    with pytest.raises(HTTPException) as error:
        service.set_user_enabled(admin_token, stale.id, True)
    assert error.value.status_code == 401


def test_toggle_rate_limit_is_per_actor_not_target(service):
    admin = client_for(service)
    login(admin, "admin", "01")
    for _ in range(30):
        assert toggle(admin, user_id(service), True).status_code == 200
    assert toggle(admin, user_id(service, "bob"), False).status_code == 429
    assert service.conn.execute("SELECT enabled FROM users WHERE username='bob'").fetchone()[0] == 1
    assert (
        service.conn.execute(
            "SELECT COUNT(*) FROM audit WHERE operation='account.enable'"
        ).fetchone()[0]
        == 30
    )
