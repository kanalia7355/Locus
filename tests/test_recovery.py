import sys
import time

import pytest
from app import cli
from app.service import PASSWORDS, Service, digest
from test_api import ORIGIN, client_for, login

NEW_PASSWORD = "Synthetic-test-password-01!"


def redeem(client, username: str, code: str, password: str = NEW_PASSWORD):
    return client.post(
        "/api/auth/recovery",
        json={"username": username, "recovery_code": code, "new_password": password},
        headers=ORIGIN,
    )


def test_recovery_success_digest_audit_and_session_revocation(service: Service) -> None:
    first = client_for(service)
    login(first)
    second = client_for(service)
    response = second.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Changed-password-long-01!"},
        headers=ORIGIN,
    )
    assert response.status_code == 200
    old_tokens = [first.cookies.get("locus_session"), second.cookies.get("locus_session")]
    user_id = service.authenticate(old_tokens[0], allow_rotation=True).id

    issued_at = time.time()
    code = service.issue_recovery("alice")
    with service.db() as db:
        stored = db.execute("SELECT * FROM recovery_codes WHERE user_id=?", (user_id,)).fetchone()
        assert stored["code_hash"] == digest(code)
        assert code not in str(dict(stored))
        assert 86399 < stored["expires"] - time.time() <= 86400
        assert stored["expires"] >= issued_at + 86400
        assert stored["used"] == 0
        issue_audit = db.execute(
            "SELECT actor_id,operation,target_id,outcome FROM audit "
            "WHERE operation='credential.recovery.issue' AND target_id=?",
            (user_id,),
        ).fetchone()
        assert dict(issue_audit) == {
            "actor_id": "local-cli",
            "operation": "credential.recovery.issue",
            "target_id": user_id,
            "outcome": "ok",
        }
        assert code not in str(dict(issue_audit))
        assert digest(code) not in str(dict(issue_audit))
        assert (
            db.execute("SELECT COUNT(*) FROM sessions WHERE user_id=?", (user_id,)).fetchone()[0]
            == 2
        )

    recovery_client = client_for(service)
    assert redeem(recovery_client, "alice", code).status_code == 200
    assert not recovery_client.cookies.get("locus_session")
    assert first.get("/api/projects").status_code == 401
    assert second.get("/api/projects").status_code == 401
    with service.db() as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        stored = db.execute("SELECT * FROM recovery_codes WHERE user_id=?", (user_id,)).fetchone()
        audit = db.execute(
            "SELECT actor_id,operation,target_id,outcome FROM audit "
            "WHERE operation='credential.recover' AND target_id=?",
            (user_id,),
        ).fetchone()
        assert user["must_rotate"] == 0
        assert user["temp_expires"] is None
        assert PASSWORDS.verify(user["password_hash"], NEW_PASSWORD)
        assert stored["used"] == 1
        assert stored["expires"] <= time.time()
        assert (
            db.execute("SELECT COUNT(*) FROM sessions WHERE user_id=?", (user_id,)).fetchone()[0]
            == 0
        )
        assert dict(audit) == {
            "actor_id": "recovery",
            "operation": "credential.recover",
            "target_id": user_id,
            "outcome": "ok",
        }
        assert code not in str(dict(audit))
        assert digest(code) not in str(dict(audit))

    fresh = client_for(service)
    fresh_login = fresh.post(
        "/api/auth/login",
        json={"username": "alice", "password": NEW_PASSWORD},
        headers=ORIGIN,
    )
    assert fresh_login.status_code == 200
    assert fresh_login.json()["must_rotate"] is False


def test_wrong_and_unknown_recovery_credentials_have_same_failure(service: Service) -> None:
    client = client_for(service)
    code = service.issue_recovery("alice")
    wrong = redeem(client, "alice", "incorrect-recovery-code")
    unknown = redeem(client, "unknown-user", code)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_new_recovery_issue_replaces_previous_code(service: Service) -> None:
    client = client_for(service)
    old_code = service.issue_recovery("alice")
    new_code = service.issue_recovery("alice")
    assert redeem(client, "alice", old_code).status_code == 401
    assert redeem(client, "alice", new_code).status_code == 200


def test_recovery_clears_forced_rotation_state(service: Service) -> None:
    client = client_for(service)
    code = service.issue_recovery("alice")
    assert redeem(client, "alice", code).status_code == 200
    with service.db() as db:
        user = db.execute("SELECT * FROM users WHERE username='alice'").fetchone()
        assert user["must_rotate"] == 0
        assert user["temp_used"] == 0
        assert user["temp_expires"] is None


def test_recovery_code_is_single_use(service: Service) -> None:
    client = client_for(service)
    code = service.issue_recovery("alice")
    assert redeem(client, "alice", code).status_code == 200
    replay = redeem(client, "alice", code)
    assert replay.status_code == 401
    assert replay.json() == {"detail": "利用者IDまたは回復コードを確認してください"}


def test_expired_recovery_code_has_generic_failure(service: Service) -> None:
    client = client_for(service)
    code = service.issue_recovery("alice")
    with service.db() as db:
        db.execute(
            "UPDATE recovery_codes SET expires=? WHERE user_id="
            "(SELECT id FROM users WHERE username=?)",
            (time.time() - 1, "alice"),
        )
    expired = redeem(client, "alice", code)
    unknown = redeem(client, "missing-user", code)
    assert expired.status_code == unknown.status_code == 401
    assert expired.json() == unknown.json()


@pytest.mark.parametrize("new_password", ["too-short", "Temporary-password-02!"])
def test_recovery_rejects_weak_or_unchanged_password(service: Service, new_password: str) -> None:
    client = client_for(service)
    code = service.issue_recovery("alice")
    rejected = redeem(client, "alice", code, new_password)
    assert rejected.status_code == 422
    assert redeem(client, "alice", code).status_code == 200


def test_recovery_rate_limit_is_per_username(service: Service) -> None:
    client = client_for(service)
    for _ in range(5):
        assert redeem(client, "alice", "wrong-code").status_code == 401
    assert redeem(client, "alice", "wrong-code").status_code == 429
    assert redeem(client, "different-user", "wrong-code").status_code == 401


def test_recovery_does_not_enable_disabled_account(service: Service) -> None:
    client = client_for(service)
    login(client)
    code = service.issue_recovery("alice")
    with service.db() as db:
        before_hash = db.execute(
            "SELECT password_hash FROM users WHERE username='alice'"
        ).fetchone()[0]
        db.execute("UPDATE users SET enabled=0 WHERE username='alice'")

    response = redeem(client, "alice", code)
    assert response.status_code == 401
    assert response.json() == {"detail": "利用者IDまたは回復コードを確認してください"}
    assert client.get("/api/projects").status_code == 401
    with service.db() as db:
        user = db.execute("SELECT * FROM users WHERE username='alice'").fetchone()
        assert user["enabled"] == 0
        assert user["password_hash"] == before_hash
        assert (
            db.execute("SELECT used FROM recovery_codes WHERE user_id=?", (user["id"],)).fetchone()[
                0
            ]
            == 0
        )


def test_cli_shows_recovery_code_exactly_once(
    service: Service, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class CLIService:
        def __init__(self, path):
            self.path = path

        def issue_recovery(self, username: str) -> str:
            return service.issue_recovery(username)

        def close(self) -> None:
            pass

    monkeypatch.setattr(cli, "Service", CLIService)
    monkeypatch.setattr(sys, "argv", ["locus", "issue-recovery", "--username", "alice"])
    cli.main()
    output = capsys.readouterr().out
    with service.db() as db:
        row = db.execute(
            "SELECT code_hash FROM recovery_codes WHERE user_id="
            "(SELECT id FROM users WHERE username=?)",
            ("alice",),
        ).fetchone()
    # The CLI is the only place where the one-time value is emitted.
    prefix = "Recovery code (shown only once; valid for 24 hours): "
    assert output.count(prefix) == 1
    assert "Local operation complete" in output
    code = output.split(prefix, 1)[1].splitlines()[0]
    assert output.count(code) == 1
    assert digest(code) == row["code_hash"]
