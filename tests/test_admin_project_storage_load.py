"""Admin project, storage and load views expose metadata only."""

import json
import sqlite3
import time

import pytest
from app.local_model import LocalModel
from app.main import create_app
from app.service import CHAT_QUEUE_LIMIT, CHAT_USER_QUEUE_LIMIT, Service
from fastapi.testclient import TestClient
from test_api import ORIGIN, client_for, login


def test_admin_project_creation_and_membership_are_atomic_and_metadata_audited(service: Service):
    admin = client_for(service)
    login(admin, "admin", "01")
    created = admin.post(
        "/api/admin/projects",
        headers=ORIGIN,
        json={"project_id": "new-project", "org_id": "org-c", "name": "New synthetic project"},
    )
    assert created.status_code == 201, created.text
    project = created.json()
    users = admin.get("/api/admin/users").json()
    alice = next(item for item in users if item["username"] == "alice")
    assigned = admin.put(
        "/api/admin/projects/new-project/members",
        headers=ORIGIN,
        json={"user_id": alice["id"], "role": "researcher"},
    )
    assert assigned.status_code == 200
    listing = admin.get("/api/admin/projects").json()
    assert next(item for item in listing if item["id"] == project["id"])["members"] == [
        {
            "user_id": alice["id"],
            "username": "alice",
            "role": "researcher",
            "roles": ["researcher"],
            "denied_permissions": [],
            "effective_permissions": ["read", "retrieve", "upload"],
        }
    ]
    remove = admin.delete(f"/api/admin/projects/new-project/members/{alice['id']}", headers=ORIGIN)
    assert remove.status_code == 204
    events = list(
        service.conn.execute("SELECT actor_id,operation,target_id FROM audit ORDER BY at")
    )
    assert [row[1] for row in events[-3:]] == [
        "project.create",
        "membership.assign",
        "membership.remove",
    ]
    assert all(row[0] != "local-cli" for row in events[-3:])
    serialized = json.dumps([tuple(row) for row in events[-3:]])
    assert "New synthetic project" not in serialized
    assert "alice" not in serialized
    no_op_remove = admin.delete(
        f"/api/admin/projects/new-project/members/{alice['id']}", headers=ORIGIN
    )
    assert no_op_remove.status_code == 204
    assert service.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == len(events)


def test_admin_member_assignment_preserves_other_held_roles(service: Service):
    admin = client_for(service)
    login(admin, "admin", "01")
    alice = next(
        item for item in admin.get("/api/admin/users").json() if item["username"] == "alice"
    )
    assigned = admin.put(
        "/api/admin/projects/project-a/members",
        headers=ORIGIN,
        json={"user_id": alice["id"], "role": "viewer"},
    )
    assert assigned.status_code == 200
    project = next(
        item for item in admin.get("/api/admin/projects").json() if item["id"] == "project-a"
    )
    member = next(item for item in project["members"] if item["user_id"] == alice["id"])
    assert member["roles"] == ["researcher", "viewer"]
    assert member["effective_permissions"] == ["read", "retrieve", "upload"]
    denied = admin.put(
        "/api/projects/project-a/members/alice/denials",
        headers=ORIGIN,
        json={"denied_permissions": ["retrieve"]},
    )
    assert denied.status_code == 200
    refreshed = next(
        item for item in admin.get("/api/admin/projects").json() if item["id"] == "project-a"
    )
    refreshed_alice = next(item for item in refreshed["members"] if item["user_id"] == alice["id"])
    assert refreshed_alice["denied_permissions"] == ["retrieve"]
    assert refreshed_alice["effective_permissions"] == ["read", "upload"]
    assert {
        row[0]
        for row in service.conn.execute(
            "SELECT role FROM membership_roles WHERE user_id=? AND project_id='project-a'",
            (alice["id"],),
        )
    } == {"researcher", "viewer"}


def test_admin_project_endpoints_enforce_system_admin_validation_and_rate_limit(service: Service):
    alice, admin = client_for(service), client_for(service)
    login(alice)
    login(admin, "admin", "01")
    payload = {"project_id": "new-project", "org_id": "org-c", "name": "Synthetic"}
    assert alice.get("/api/admin/projects").status_code == 403
    assert alice.post("/api/admin/projects", json=payload, headers=ORIGIN).status_code == 403
    assert (
        alice.put(
            "/api/admin/projects/project-a/members",
            json={"user_id": "unknown", "role": "researcher"},
            headers=ORIGIN,
        ).status_code
        == 403
    )
    assert (
        admin.post(
            "/api/admin/projects", json={**payload, "project_id": "../bad"}, headers=ORIGIN
        ).status_code
        == 422
    )
    assert (
        admin.post(
            "/api/admin/projects", json={**payload, "name": "   "}, headers=ORIGIN
        ).status_code
        == 422
    )
    assert admin.post("/api/admin/projects", json=payload, headers=ORIGIN).status_code == 201
    assert admin.post("/api/admin/projects", json=payload, headers=ORIGIN).status_code == 409
    users = admin.get("/api/admin/users").json()
    alice_id = next(item["id"] for item in users if item["username"] == "alice")
    assert (
        admin.put(
            "/api/admin/projects/new-project/members",
            json={"user_id": alice_id, "role": "system_admin"},
            headers=ORIGIN,
        ).status_code
        == 422
    )
    assert (
        admin.put(
            "/api/admin/projects/new-project/members",
            json={"user_id": "unknown", "role": "researcher"},
            headers=ORIGIN,
        ).status_code
        == 404
    )
    assert (
        admin.put(
            "/api/admin/projects/new-project/members",
            json={"user_id": alice_id, "role": "not-a-role"},
            headers=ORIGIN,
        ).status_code
        == 422
    )
    with service.db() as db:
        db.execute("UPDATE users SET enabled=0 WHERE id=?", (alice_id,))
    assert (
        admin.put(
            "/api/admin/projects/new-project/members",
            json={"user_id": alice_id, "role": "researcher"},
            headers=ORIGIN,
        ).status_code
        == 409
    )
    admin_actor = service.authenticate(admin.cookies.get("locus_session"))
    service.limits["admin-project:" + admin_actor.id] = [time.time()] * 10
    assert (
        admin.post(
            "/api/admin/projects",
            json={"project_id": "rate-limited", "org_id": "org-c", "name": "Synthetic"},
            headers=ORIGIN,
        ).status_code
        == 429
    )
    assert service.conn.execute("SELECT 1 FROM projects WHERE id='rate-limited'").fetchone() is None
    service.limits["admin-project-member:" + admin_actor.id] = [time.time()] * 30
    bob_id = next(item["id"] for item in users if item["username"] == "bob")
    assert (
        admin.put(
            "/api/admin/projects/new-project/members",
            json={"user_id": bob_id, "role": "viewer"},
            headers=ORIGIN,
        ).status_code
        == 429
    )
    assert (
        service.conn.execute(
            "SELECT 1 FROM memberships WHERE project_id='new-project' AND user_id=?", (bob_id,)
        ).fetchone()
        is None
    )


def test_project_and_member_mutations_roll_back_when_audit_fails(service: Service, monkeypatch):
    admin = client_for(service)
    login(admin, "admin", "01")

    def broken(*_args):
        raise sqlite3.OperationalError("synthetic audit unavailable")

    monkeypatch.setattr(service, "_audit", broken)
    with pytest.raises(sqlite3.OperationalError):
        service.create_admin_project(
            admin.cookies.get("locus_session"), "rollback-project", "org-c", "Synthetic"
        )
    assert (
        service.conn.execute("SELECT 1 FROM projects WHERE id='rollback-project'").fetchone()
        is None
    )

    alice = service.conn.execute("SELECT id FROM users WHERE username='alice'").fetchone()[0]
    with pytest.raises(sqlite3.OperationalError):
        service.set_project_member(admin.cookies.get("locus_session"), "project-a", alice, "viewer")
    assert (
        service.conn.execute(
            "SELECT role FROM memberships WHERE project_id='project-a' AND user_id=?", (alice,)
        ).fetchone()[0]
        == "researcher"
    )


def test_storage_status_is_read_only_local_bounded_and_admin_only(service: Service):
    admin, alice = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(alice)
    result = admin.get("/api/admin/storage")
    assert result.status_code == 200
    assert result.json() == {
        "backend": "sqlite",
        "mode": "local-only",
        "external_enabled": False,
        "accepted_formats": ["txt", "md", "csv"],
        "max_file_bytes": 262144,
        "scanner_configured": False,
        "ingestion_queue_limit": 32,
        "per_user_ingestion_queue_limit": 4,
        "ingestion_status_counts": {},
        "configuration_available": False,
    }
    assert alice.get("/api/admin/storage").status_code == 403
    before = service.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    assert (
        admin.put("/api/admin/storage", json={"backend": "external"}, headers=ORIGIN).status_code
        == 405
    )
    assert service.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == before


def test_load_display_reads_queue_limits_and_running_job_without_chat_content(service: Service):
    admin, alice = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(alice)
    principal = service.authenticate(alice.cookies.get("locus_session"))
    conversation = service.new_conversation(principal, "project-a")["id"]
    now = time.time()
    with service.db() as db:
        db.execute(
            "INSERT INTO chat_jobs "
            "(id,conversation_id,user_id,text,scope,attachments,status,created,updated) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "synthetic-running-job",
                conversation,
                principal.id,
                "private question",
                "all",
                "[]",
                "running",
                now,
                now,
            ),
        )
        db.execute(
            "INSERT INTO chat_jobs "
            "(id,conversation_id,user_id,text,scope,attachments,status,created,updated) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "synthetic-queued-job",
                conversation,
                principal.id,
                "queued question",
                "all",
                "[]",
                "queued",
                now,
                now,
            ),
        )
    result = admin.get("/api/admin/load")
    assert result.status_code == 200
    assert result.json() == {
        "model_slot": {"enabled": False, "busy": False},
        "chat_queue": {
            "queued": 1,
            "limit": CHAT_QUEUE_LIMIT,
            "per_user_limit": CHAT_USER_QUEUE_LIMIT,
            "running_job": {
                "id": "synthetic-running-job",
                "username": "alice",
                "started_at": now,
            },
        },
    }
    assert "private question" not in result.text and "queued question" not in result.text
    assert alice.get("/api/admin/load").status_code == 403
    runtime = LocalModel()
    app = create_app(service=service, start_worker=False, local_model=runtime)
    with runtime.lock:
        busy_result = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
        busy_login = busy_result.post(
            "/api/auth/login",
            json={"username": "admin", "password": "Changed-password-long-01!"},
            headers=ORIGIN,
        )
        assert busy_login.status_code == 200
        observed = busy_result.get("/api/admin/load").json()
        assert observed["model_slot"]["busy"] is True
