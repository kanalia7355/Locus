import pytest
from app.main import create_app
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
    assert (
        client.post(
            "/api/auth/password",
            json={
                "current_password": "Temporary-password-02!",
                "new_password": "short",
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
    assert client.get(f"/api/documents/{document_id}").json()["status"] == "quarantined"
    assert client.get(f"/api/documents/{document_id}/chunks").status_code == 409


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
    assert client.post("/api/admin/delegations", json={}, headers=ORIGIN).status_code == 409
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
