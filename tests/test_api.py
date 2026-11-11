import time

import pytest
from app.main import create_app
from app.scanner import CLEAN, REJECTED, UNAVAILABLE, ScanResult
from app.service import Service
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://127.0.0.1:5174"}


def login(client: TestClient, username: str = "alice", number: str = "02") -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": f"Temporary-password-{number}!",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/api/auth/password",
        json={
            "current_password": f"Temporary-password-{number}!",
            "new_password": "Changed-password-long-01!",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text


def client_for(service: Service) -> TestClient:
    return TestClient(
        create_app(service=service, start_worker=False),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )


def test_first_login_rotation_and_revocation(service: Service) -> None:
    client = client_for(service)
    assert client.get("/api/projects").status_code == 401
    first = client.post(
        "/api/auth/login",
        json={
            "username": "alice",
            "password": "Temporary-password-02!",
        },
        headers=ORIGIN,
    )
    assert first.json()["must_rotate"] is True
    cookie = client.cookies.get("locus_session")
    assert "HttpOnly" in first.headers["set-cookie"]
    assert "SameSite=strict" in first.headers["set-cookie"]
    assert client.get("/api/projects").status_code == 403
    repeat = client_for(service).post(
        "/api/auth/login",
        json={
            "username": "alice",
            "password": "Temporary-password-02!",
        },
        headers=ORIGIN,
    )
    assert repeat.status_code == 401
    invalid_short_input = "short"
    assert (
        client.post(
            "/api/auth/password",
            json={
                "current_password": "Temporary-password-02!",
                "new_password": invalid_short_input,
            },
            headers=ORIGIN,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/auth/password",
            json={
                "current_password": "Temporary-password-02!",
                "new_password": "Changed-password-long-01!",
            },
            headers=ORIGIN,
        ).status_code
        == 200
    )
    assert client.cookies.get("locus_session") != cookie
    assert client.get("/api/projects").status_code == 200
    assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 204
    assert client.get("/api/projects").status_code == 401


def test_origin_host_and_body_limits(service: Service) -> None:
    client = client_for(service)
    for headers in ({}, {"Origin": "null"}, {"Origin": "https://hostile.example"}):
        assert client.post("/api/auth/logout", headers=headers).status_code == 403
    assert client.get("/api/health", headers={"Host": "hostile.example"}).status_code == 400
    assert client.post("/api/auth/login", headers=ORIGIN, content="x" * 310_000).status_code == 413
    assert client.get("/api/health").json() == {"status": "ok", "mode": "development-local-only"}


def test_project_document_and_history_isolation(service: Service) -> None:
    alice, bob, eve, admin = [client_for(service) for _ in range(4)]
    login(alice)
    login(bob, "bob", "03")
    login(eve, "eve", "04")
    login(admin, "admin", "01")
    private = service.seed_synthetic("alice", "project-a", "personal")
    shared = service.seed_synthetic("alice", "project-a", "shared")
    for outsider in (bob, eve, admin):
        assert outsider.get(f"/api/documents/{private}").status_code == 404
    assert bob.get(f"/api/documents/{shared}").status_code == 200
    assert eve.get(f"/api/documents/{shared}").status_code == 404
    response = alice.post("/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN)
    conversation_id = response.json()["id"]
    result = alice.post(
        f"/api/conversations/{conversation_id}/messages",
        json={
            "text": "成膜",
            "scope": "all",
            "attachment_ids": [],
        },
        headers=ORIGIN,
    )
    assert result.status_code == 200, result.text
    assert result.json()["citations"]
    for outsider in (bob, eve, admin):
        assert outsider.get(f"/api/conversations/{conversation_id}").status_code == 404
    service.assign("alice", "project-a", None)
    assert alice.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert alice.get(f"/api/documents/{shared}").status_code == 404


def test_upload_quarantine_and_validation(service: Service) -> None:
    client = client_for(service)
    login(client)
    for name, content in (("../../x.txt", "text"), ("x.exe", "text"), ("x.txt", "a\x00b")):
        assert (
            client.post(
                "/api/documents",
                json={
                    "project_id": "project-a",
                    "name": name,
                    "content": content,
                    "kind": "personal",
                },
                headers=ORIGIN,
            ).status_code
            == 422
        )
    response = client.post(
        "/api/documents",
        json={
            "project_id": "project-a",
            "name": "sample.txt",
            "content": "synthetic sample",
            "kind": "personal",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 201, response.text
    document_id = response.json()["id"]
    service.process_next()
    stored = client.get(f"/api/documents/{document_id}").json()
    assert stored["status"] == "quarantined"
    # Without a configured scanner the reason names the unavailable check itself,
    # not an unsupported scan verdict; ingestion still fails closed either way.
    unscanned_reason = "安全検査を実行できないため隔離中です（既定拒否）。本文は検索に使いません"
    assert stored["reason"] == unscanned_reason
    assert client.get(f"/api/documents/{document_id}/chunks").status_code == 409
    admin = client_for(service)
    login(admin, "admin", "01")
    principal = service.authenticate(admin.cookies.get("locus_session"))
    assert service.storage_status(principal)["scanner_configured"] is False


class AcceptingScanner:
    def scan(self, content: str) -> ScanResult:
        return CLEAN


def test_configured_scanner_ingests_and_reports_state(tmp_path) -> None:
    svc = Service(tmp_path / "scan.sqlite3", scanner=AcceptingScanner())
    try:
        svc.provision("admin", "Temporary-password-01!", system_admin=True)
        svc.provision("alice", "Temporary-password-02!")
        svc.create_project("org-a", "project-a", "研究プロジェクト")
        svc.assign("alice", "project-a", "researcher")
        client = client_for(svc)
        login(client)
        response = client.post(
            "/api/documents",
            json={
                "project_id": "project-a",
                "name": "sample.txt",
                "content": "synthetic sample",
                "kind": "personal",
            },
            headers=ORIGIN,
        )
        assert response.status_code == 201, response.text
        document_id = response.json()["id"]
        assert svc.process_next()
        assert client.get(f"/api/documents/{document_id}").json()["status"] == "ready"
        admin = client_for(svc)
        login(admin, "admin", "01")
        principal = svc.authenticate(admin.cookies.get("locus_session"))
        status = svc.storage_status(principal)
        assert status["scanner_configured"] is True
        assert status["scanner_last_outcome"] == "clean"
    finally:
        svc.close()


class UnreachableScanner:
    """Configured adapter whose operational check raises (timeout / outage)."""

    def scan(self, content: str) -> ScanResult:
        raise TimeoutError("scanner unreachable")


class UnavailableResultScanner:
    """Configured adapter that reports the check could not complete."""

    def scan(self, content: str) -> ScanResult:
        return UNAVAILABLE


@pytest.mark.parametrize(
    "scanner",
    [UnreachableScanner(), UnavailableResultScanner()],
    ids=["exception", "unavailable-result"],
)
def test_configured_scanner_failure_still_quarantines_and_reports_unavailable(
    tmp_path, scanner
) -> None:
    """A configured scanner that cannot run stays fail-closed, but the status
    names the unavailable check instead of claiming a failed verdict."""
    svc = Service(tmp_path / "scan.sqlite3", scanner=scanner)
    try:
        svc.provision("admin", "Temporary-password-01!", system_admin=True)
        svc.provision("alice", "Temporary-password-02!")
        svc.create_project("org-a", "project-a", "研究プロジェクト")
        svc.assign("alice", "project-a", "researcher")
        client = client_for(svc)
        login(client)
        response = client.post(
            "/api/documents",
            json={
                "project_id": "project-a",
                "name": "sample.txt",
                "content": "synthetic sample",
                "kind": "personal",
            },
            headers=ORIGIN,
        )
        assert response.status_code == 201, response.text
        document_id = response.json()["id"]
        assert svc.process_next()
        stored = client.get(f"/api/documents/{document_id}").json()
        assert stored["status"] == "quarantined"
        assert (
            stored["reason"]
            == "安全検査を実行できないため隔離中です（既定拒否）。本文は検索に使いません"
        )
        assert client.get(f"/api/documents/{document_id}/chunks").status_code == 409
        admin = client_for(svc)
        login(admin, "admin", "01")
        principal = svc.authenticate(admin.cookies.get("locus_session"))
        status = svc.storage_status(principal)
        assert status["scanner_configured"] is True
        assert status["scanner_last_outcome"] == "unavailable"
    finally:
        svc.close()


class RejectingScanner:
    """Configured adapter that explicitly rejects the content."""

    def scan(self, content: str) -> ScanResult:
        return REJECTED


def test_configured_scanner_explicit_rejection_still_quarantines_as_rejected(
    tmp_path,
) -> None:
    """An explicit rejection keeps fail-closed ingestion with the rejected
    status, distinct from a check that could not run."""
    svc = Service(tmp_path / "scan.sqlite3", scanner=RejectingScanner())
    try:
        svc.provision("admin", "Temporary-password-01!", system_admin=True)
        svc.provision("alice", "Temporary-password-02!")
        svc.create_project("org-a", "project-a", "研究プロジェクト")
        svc.assign("alice", "project-a", "researcher")
        client = client_for(svc)
        login(client)
        response = client.post(
            "/api/documents",
            json={
                "project_id": "project-a",
                "name": "sample.txt",
                "content": "synthetic sample",
                "kind": "personal",
            },
            headers=ORIGIN,
        )
        assert response.status_code == 201, response.text
        document_id = response.json()["id"]
        assert svc.process_next()
        stored = client.get(f"/api/documents/{document_id}").json()
        assert stored["status"] == "quarantined"
        assert stored["reason"] == "安全検査を通過していないため隔離中です。本文は検索に使いません"
        assert client.get(f"/api/documents/{document_id}/chunks").status_code == 409
        admin = client_for(svc)
        login(admin, "admin", "01")
        principal = svc.authenticate(admin.cookies.get("locus_session"))
        status = svc.storage_status(principal)
        assert status["scanner_configured"] is True
        assert status["scanner_last_outcome"] == "rejected"
    finally:
        svc.close()


def test_roles_denied_by_default_and_audit_redaction(service: Service) -> None:
    client = client_for(service)
    login(client)
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/admin/audit").status_code == 403
    assert (
        client.post(
            "/api/projects/project-a/roles",
            json={
                "name": "escalate",
                "permissions": ["manage_roles"],
            },
            headers=ORIGIN,
        ).status_code
        == 403
    )
    assert client.post("/api/admin/delegations", json={}, headers=ORIGIN).status_code == 422
    assert (
        client.post(
            "/api/admin/delegations",
            json={
                "project_id": "project-a",
                "recipient_id": service.provision("delegation-recipient", "Temporary-password-06!"),
                "permissions": ["read"],
            },
            headers=ORIGIN,
        ).status_code
        == 403
    )
    admin = client_for(service)
    login(admin, "admin", "01")
    assert (
        admin.post(
            "/api/projects/project-a/roles",
            json={
                "name": "invent",
                "permissions": ["root"],
            },
            headers=ORIGIN,
        ).status_code
        == 422
    )
    assert (
        admin.post(
            "/api/projects/project-a/roles",
            json={
                "name": "readers",
                "permissions": ["read", "retrieve"],
            },
            headers=ORIGIN,
        ).status_code
        == 201
    )
    log = admin.get("/api/admin/audit").text
    assert "password" not in log.lower()
    assert "Temporary" not in log
    assert "Changed" not in log


def test_citations_deleted_and_revoked_are_not_retained(service: Service) -> None:
    client = client_for(service)
    login(client)
    document_id = service.seed_synthetic("alice", "project-a", "personal")
    cid = client.post(
        "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
    ).json()["id"]
    sent = client.post(
        f"/api/conversations/{cid}/messages",
        json={
            "text": "成膜",
            "scope": "all",
            "attachment_ids": [],
        },
        headers=ORIGIN,
    ).json()
    assert sent["citations"]
    assert client.delete(f"/api/documents/{document_id}", headers=ORIGIN).status_code == 204
    history = client.get(f"/api/conversations/{cid}").json()
    assert history["messages"][0]["citations"] == []
    assert client.get(f"/api/documents/{document_id}/chunks").status_code == 404


def test_production_startup_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="development"):
        create_app()


def test_admin_web_provisioning_is_one_time_and_forces_rotation(
    service: Service, caplog: pytest.LogCaptureFixture
) -> None:
    admin = client_for(service)
    login(admin, "admin", "01")
    admin_id = admin.get("/api/auth/me").json()["id"]
    response = admin.post("/api/admin/users", json={"username": "new.researcher-1"}, headers=ORIGIN)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["username"] == "new.researcher-1"
    assert created["must_rotate"] is True
    temporary_password = created["temporary_password"]
    assert 14 <= len(temporary_password) <= 128
    assert set(created) == {"id", "username", "temporary_password", "must_rotate"}

    with service.db() as db:
        stored = db.execute(
            "SELECT password_hash,must_rotate,temp_expires FROM users WHERE id=?",
            (created["id"],),
        ).fetchone()
        audit = db.execute(
            "SELECT actor_id,operation,target_id FROM audit "
            "WHERE operation='account.provision' AND target_id=?",
            (created["id"],),
        ).fetchone()
    assert stored["password_hash"] != temporary_password
    assert stored["must_rotate"] == 1
    assert stored["temp_expires"] > time.time()
    assert audit["actor_id"] == admin_id
    assert audit["operation"] == "account.provision"
    assert audit["target_id"] == created["id"]
    assert temporary_password not in repr(dict(audit))
    assert temporary_password not in admin.get("/api/admin/audit").text
    assert temporary_password not in caplog.text
    assert "temporary_password" not in str(admin.get("/api/admin/users").json())

    created_user = client_for(service)
    first_login = created_user.post(
        "/api/auth/login",
        json={"username": created["username"], "password": temporary_password},
        headers=ORIGIN,
    )
    assert first_login.status_code == 200, first_login.text
    assert first_login.json()["must_rotate"] is True
    assert created_user.get("/api/projects").status_code == 403
    rotated = created_user.post(
        "/api/auth/password",
        json={
            "current_password": temporary_password,
            "new_password": "Changed-synthetic-password-01!",
        },
        headers=ORIGIN,
    )
    assert rotated.status_code == 200, rotated.text
    assert created_user.get("/api/auth/me").json()["must_rotate"] is False


def test_admin_web_provisioning_validation_and_duplicates(service: Service) -> None:
    admin = client_for(service)
    login(admin, "admin", "01")
    invalid = admin.post("/api/admin/users", json={"username": "alice' OR '1'='1"}, headers=ORIGIN)
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "利用者IDは3〜64文字の英数字・_.-で指定してください"
    duplicate = admin.post("/api/admin/users", json={"username": "alice"}, headers=ORIGIN)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "利用者IDは使用済みです"
    assert [row["username"] for row in admin.get("/api/admin/users").json()] == [
        "admin",
        "alice",
        "bob",
        "eve",
    ]


def test_admin_web_provisioning_requires_system_admin(service: Service) -> None:
    user = client_for(service)
    login(user)
    response = user.post("/api/admin/users", json={"username": "unauthorized-user"}, headers=ORIGIN)
    assert response.status_code == 403
    assert response.json()["detail"] == "管理権限が必要です"


def test_admin_web_provisioning_is_rate_limited(service: Service) -> None:
    admin = client_for(service)
    login(admin, "admin", "01")
    for index in range(10):
        response = admin.post(
            "/api/admin/users",
            json={"username": f"rate-user-{index:02d}"},
            headers=ORIGIN,
        )
        assert response.status_code == 201, response.text
    limited = admin.post("/api/admin/users", json={"username": "rate-user-last"}, headers=ORIGIN)
    assert limited.status_code == 429
    assert limited.json()["detail"] == "試行回数が多いため、1分後に再試行してください"

def test_document_list_search_filters_by_name(service: Service) -> None:
    client = client_for(service)
    login(client)
    svc = service
    # seed two personal docs with distinct names
    doc_a = svc.seed_synthetic("alice", "project-a", "personal")
    # rename not directly available; create via upload path for controlled names
    with svc.db() as db:
        db.execute("UPDATE documents SET name=? WHERE id=?", ("alpha-notes.txt", doc_a))
    res = client.post(
        "/api/documents",
        json={
            "project_id": "project-a",
            "name": "beta-report.txt",
            "content": "synthetic beta",
            "kind": "personal",
        },
        headers=ORIGIN,
    )
    assert res.status_code == 201, res.text
    doc_b = res.json()["id"]
    assert svc.process_next()

    all_docs = client.get("/api/documents", params={"project_id": "project-a"}).json()
    names = {d["name"] for d in all_docs}
    assert "alpha-notes.txt" in names and "beta-report.txt" in names

    filtered = client.get(
        "/api/documents", params={"project_id": "project-a", "q": "alpha"}
    ).json()
    assert [d["name"] for d in filtered] == ["alpha-notes.txt"]

    filtered_ci = client.get(
        "/api/documents", params={"project_id": "project-a", "q": "BETA"}
    ).json()
    assert [d["id"] for d in filtered_ci] == [doc_b]

    none_match = client.get(
        "/api/documents", params={"project_id": "project-a", "q": "nomatch"}
    ).json()
    assert none_match == []


def test_document_list_search_respects_visibility(service: Service) -> None:
    alice = client_for(service)
    bob = client_for(service)
    login(alice)
    login(bob, "bob", "03")
    private = service.seed_synthetic("alice", "project-a", "personal")
    shared = service.seed_synthetic("alice", "project-a", "shared")
    with service.db() as db:
        db.execute("UPDATE documents SET name=? WHERE id=?", ("alpha-private.txt", private))
        db.execute("UPDATE documents SET name=? WHERE id=?", ("alpha-shared.txt", shared))

    alice_hits = alice.get(
        "/api/documents", params={"project_id": "project-a", "q": "alpha"}
    ).json()
    assert {d["id"] for d in alice_hits} == {private, shared}

    bob_hits = bob.get(
        "/api/documents", params={"project_id": "project-a", "q": "alpha"}
    ).json()
    assert [d["id"] for d in bob_hits] == [shared]
    assert all(d["name"] == "alpha-shared.txt" for d in bob_hits)
