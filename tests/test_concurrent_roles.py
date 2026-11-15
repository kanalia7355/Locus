"""Concurrent role holdings union within one project; scoped denies remain absolute."""

import json
import sqlite3

import pytest
from app.service import Principal, Service
from fastapi import HTTPException
from test_api import ORIGIN, client_for, login


def test_legacy_membership_migrates_to_single_held_role(tmp_path) -> None:
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE users (id TEXT PRIMARY KEY);
        CREATE TABLE projects (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, name TEXT NOT NULL);
        CREATE TABLE memberships (
            user_id TEXT, project_id TEXT, role TEXT, PRIMARY KEY(user_id, project_id)
        );
        CREATE TABLE roles (
            id TEXT PRIMARY KEY, project_id TEXT, name TEXT, permissions TEXT
        );
        INSERT INTO users VALUES ('legacy-user');
        INSERT INTO projects VALUES ('legacy-project', 'legacy-org', 'Legacy project');
        INSERT INTO memberships VALUES ('legacy-user', 'legacy-project', 'viewer');
        """
    )
    connection.close()

    service = Service(path)
    try:
        with service.db() as db:
            assert service._held_roles(db, "legacy-user", "legacy-project") == ["viewer"]
            actor = Principal("legacy-user", "legacy", False, False)
            assert service._permissions(db, actor, "legacy-project") == frozenset(
                {"read", "retrieve"}
            )
            membership = db.execute(
                "SELECT denied_permissions FROM memberships WHERE user_id='legacy-user'"
            ).fetchone()
            assert json.loads(membership["denied_permissions"]) == []
    finally:
        service.close()


def test_concurrent_roles_union_and_deny_overrides_same_scope(service: Service) -> None:
    admin, bob = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(bob, "bob", "03")
    service.assign("bob", "project-a", None)
    read_role = admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={"name": "read-only", "permissions": ["read"]},
    ).json()["id"]
    upload_role = admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={"name": "upload-only", "permissions": ["upload"]},
    ).json()["id"]
    service.add_role_holding(
        service.authenticate(admin.cookies.get("locus_session")), "project-a", "bob", read_role
    )
    service.add_role_holding(
        service.authenticate(admin.cookies.get("locus_session")), "project-a", "bob", upload_role
    )
    bob_projects = bob.get("/api/projects").json()
    project = next(item for item in bob_projects if item["id"] == "project-a")
    assert set(project["roles"]) == {read_role, upload_role}
    assert set(project["permissions"]) == {"read", "upload"}

    deny_read = admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={"name": "deny-read", "permissions": [], "denied_permissions": ["read"]},
    ).json()["id"]
    service.add_role_holding(
        service.authenticate(admin.cookies.get("locus_session")), "project-a", "bob", deny_read
    )
    service.set_membership_denials(
        service.authenticate(admin.cookies.get("locus_session")),
        "project-a",
        "bob",
        ["manage_roles"],
    )
    service.assign("bob", "project-b", "researcher")
    document = service.seed_synthetic("admin", "project-a")
    with service.db() as db:
        actor = service._authenticate(db, bob.cookies.get("locus_session"))
        assert service._permissions(db, actor, "project-a") == frozenset({"upload"})
        assert service._permissions(db, actor, "project-b") == frozenset(
            {"read", "retrieve", "upload"}
        )
        assert not service._can_read(
            db,
            actor,
            db.execute("SELECT * FROM documents WHERE id=?", (document,)).fetchone(),
        )


def test_explicit_denials_are_project_scoped(service: Service) -> None:
    admin = client_for(service)
    login(admin, "admin", "01")
    actor = service.authenticate(admin.cookies.get("locus_session"))
    service.assign("admin", "project-b", "project_lead")
    service.set_membership_denials(actor, "project-a", "admin", ["read"])
    with service.db() as db:
        current = Principal(actor.id, actor.username, actor.system_admin, actor.must_rotate)
        assert "read" not in service._permissions(db, current, "project-a")
        assert "read" in service._permissions(db, current, "project-b")


def test_multiple_roles_cannot_combine_into_delegation_ceiling(service: Service) -> None:
    admin, alice = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(alice)
    actor = service.authenticate(alice.cookies.get("locus_session"))
    # One role grants member-management while the other narrows the delegation ceiling.
    # Permissions are unioned for use, but every held role's ceiling must be respected.
    service.assign("alice", "project-a", "project_lead")
    service.add_role_holding(
        service.authenticate(admin.cookies.get("locus_session")),
        "project-a",
        "alice",
        "auditor",
    )
    with service.db() as db:
        assert service._permissions(db, actor, "project-a") >= {"manage_members", "upload"}
        assert service._permission_ceiling(db, actor, "project-a") == frozenset({"read"})
    with pytest.raises(HTTPException) as combined:
        service.create_role(actor, "project-a", "combined", ["read", "upload"])
    assert combined.value.status_code == 422

    existing_role = service.create_role(actor, "project-a", "bounded", ["read"])["id"]
    with pytest.raises(HTTPException) as update_escalation:
        service.update_role(actor, "project-a", existing_role, "bounded", ["read", "upload"])
    assert update_escalation.value.status_code == 422
    with service.db() as db:
        stored = db.execute("SELECT permissions FROM roles WHERE id=?", (existing_role,)).fetchone()
        assert json.loads(stored["permissions"]) == ["read"]

    upload_role = service.create_role(
        service.authenticate(admin.cookies.get("locus_session")),
        "project-a",
        "upload-only",
        ["upload"],
    )["id"]
    with pytest.raises(HTTPException) as self_escalation:
        service.add_role_holding(actor, "project-a", "alice", upload_role)
    assert self_escalation.value.status_code == 422


def test_membership_denial_and_role_changes_are_audited_transactionally(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = client_for(service)
    login(admin, "admin", "01")
    actor = service.authenticate(admin.cookies.get("locus_session"))
    role = service.create_role(actor, "project-a", "deny-retrieve", [], ["retrieve"])["id"]
    service.add_role_holding(actor, "project-a", "bob", role)
    assert service.set_membership_denials(actor, "project-a", "bob", ["read"]) == ["read"]
    with service.db() as db:
        events = db.execute(
            "SELECT operation FROM audit WHERE operation IN "
            "('role.create','membership.role.assign','membership.deny.update')"
        ).fetchall()
        assert [row["operation"] for row in events[-3:]] == [
            "role.create",
            "membership.role.assign",
            "membership.deny.update",
        ]
        before = json.loads(
            db.execute(
                "SELECT denied_permissions FROM memberships WHERE user_id="
                "(SELECT id FROM users WHERE username='bob') AND project_id='project-a'"
            ).fetchone()[0]
        )
    assert before == ["read"]

    def unavailable(*args: object) -> None:
        raise RuntimeError("synthetic audit unavailable")

    monkeypatch.setattr(service, "_audit", unavailable)
    with pytest.raises(RuntimeError, match="synthetic audit unavailable"):
        service.set_membership_denials(actor, "project-a", "bob", ["upload"])
    with service.db() as db:
        row = db.execute(
            "SELECT denied_permissions FROM memberships WHERE user_id="
            "(SELECT id FROM users WHERE username='bob') AND project_id='project-a'"
        ).fetchone()
        assert json.loads(row["denied_permissions"]) == ["read"]


def test_role_holding_and_denial_api_checks_manage_members(service: Service) -> None:
    bob, admin = client_for(service), client_for(service)
    login(bob, "bob", "03")
    login(admin, "admin", "01")
    role = admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={"name": "scoped-reader", "permissions": ["read"]},
    ).json()["id"]
    assert bob.get("/api/projects/project-a/members/alice/roles").status_code == 403
    assert (
        bob.post(f"/api/projects/project-a/members/alice/roles/{role}", headers=ORIGIN).status_code
        == 403
    )
    assert (
        bob.put(
            "/api/projects/project-a/members/alice/denials",
            headers=ORIGIN,
            json={"denied_permissions": ["read"]},
        ).status_code
        == 403
    )
    assert (
        admin.post(f"/api/projects/project-a/members/bob/roles/{role}", headers=ORIGIN).status_code
        == 204
    )
    state = admin.get("/api/projects/project-a/members/bob/roles").json()
    assert set(state["roles"]) == {"viewer", role}
    assert (
        admin.delete(
            f"/api/projects/project-a/members/bob/roles/{role}", headers=ORIGIN
        ).status_code
        == 204
    )
    assert (
        admin.put(
            "/api/projects/project-a/members/alice/denials",
            headers=ORIGIN,
            json={"denied_permissions": ["unknown"]},
        ).status_code
        == 422
    )


def test_system_admin_can_manage_holdings_in_unassigned_project_with_non_admin_role_ceiling(
    service: Service,
) -> None:
    admin = client_for(service)
    login(admin, "admin", "01")
    service.create_project("org-c", "unassigned-project", "Synthetic project")
    assigned = admin.post(
        "/api/projects/unassigned-project/members/alice/roles/researcher",
        headers=ORIGIN,
    )
    assert assigned.status_code == 204
    denied = admin.put(
        "/api/projects/unassigned-project/members/alice/denials",
        headers=ORIGIN,
        json={"denied_permissions": ["retrieve"]},
    )
    assert denied.status_code == 200
    state = admin.get("/api/projects/unassigned-project/members/alice/roles", headers=ORIGIN).json()
    assert state["roles"] == ["researcher"]
    assert state["denied_permissions"] == ["retrieve"]
    assert state["delegated_permissions"] == []
    assert state["effective_permissions"] == ["read", "upload"]
    assert (
        admin.post(
            "/api/projects/unassigned-project/members/bob/roles/system_admin",
            headers=ORIGIN,
        ).status_code
        == 422
    )


def test_effective_permissions_preview_exposes_delegation_and_respects_explicit_denials(
    service: Service,
) -> None:
    admin, alice = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(alice)
    service.assign("alice", "project-a", "organization_admin")
    users = admin.get("/api/admin/users").json()
    bob_id = next(item["id"] for item in users if item["username"] == "bob")
    alice_token = alice.cookies.get("locus_session")
    alice_actor = service.authenticate(alice_token)
    service.create_delegation(alice_actor, alice_token, "project-a", bob_id, ["upload"])

    roles_preview = admin.get("/api/projects/project-a/members/bob/roles").json()
    assert roles_preview["roles"] == ["viewer"]
    assert roles_preview["delegated_permissions"] == ["upload"]
    assert roles_preview["denied_permissions"] == []
    assert roles_preview["effective_permissions"] == ["read", "retrieve", "upload"]

    project_a = next(
        item for item in admin.get("/api/admin/projects").json() if item["id"] == "project-a"
    )
    bob_member = next(item for item in project_a["members"] if item["username"] == "bob")
    assert bob_member["delegated_permissions"] == ["upload"]
    assert bob_member["effective_permissions"] == ["read", "retrieve", "upload"]

    denied = admin.put(
        "/api/projects/project-a/members/bob/denials",
        headers=ORIGIN,
        json={"denied_permissions": ["upload"]},
    )
    assert denied.status_code == 200

    roles_after_deny = admin.get("/api/projects/project-a/members/bob/roles").json()
    assert roles_after_deny["delegated_permissions"] == ["upload"]
    assert roles_after_deny["denied_permissions"] == ["upload"]
    assert roles_after_deny["effective_permissions"] == ["read", "retrieve"]

    project_after_deny = next(
        item for item in admin.get("/api/admin/projects").json() if item["id"] == "project-a"
    )
    bob_after_deny = next(
        item for item in project_after_deny["members"] if item["username"] == "bob"
    )
    assert bob_after_deny["delegated_permissions"] == ["upload"]
    assert bob_after_deny["denied_permissions"] == ["upload"]
    assert bob_after_deny["effective_permissions"] == ["read", "retrieve"]


def test_role_update_denials_and_built_in_roles_remain_protected(service: Service) -> None:
    admin = client_for(service)
    login(admin, "admin", "01")
    created = admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={"name": "editable", "permissions": ["read"], "denied_permissions": ["upload"]},
    )
    assert created.status_code == 201
    role = created.json()["id"]
    path = f"/api/projects/project-a/roles/{role}"
    updated = admin.put(
        path,
        headers=ORIGIN,
        json={"name": "editable", "permissions": ["read"], "denied_permissions": ["retrieve"]},
    )
    assert updated.status_code == 200
    assert updated.json()["denied_permissions"] == ["retrieve"]
    assert (
        admin.put(
            "/api/projects/project-a/roles/researcher",
            headers=ORIGIN,
            json={"name": "mutated", "permissions": ["read"], "denied_permissions": []},
        ).status_code
        == 404
    )
    assert (
        admin.put(
            path,
            headers=ORIGIN,
            json={"name": "editable", "permissions": ["read"], "denied_permissions": ["unknown"]},
        ).status_code
        == 422
    )


def test_concurrent_role_deny_overrides_active_delegation_immediately(service: Service) -> None:
    admin, owner_client, bob = client_for(service), client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(owner_client, "alice", "02")
    login(bob, "bob", "03")
    service.assign("alice", "project-a", "project_lead")
    owner = service.authenticate(owner_client.cookies.get("locus_session"))
    with service.db() as db:
        db.execute(
            "INSERT INTO project_owners (project_id,user_id) VALUES (?,?)",
            ("project-a", owner.id),
        )
    bob_actor = service.authenticate(bob.cookies.get("locus_session"))
    grant = owner_client.post(
        "/api/admin/delegations",
        headers=ORIGIN,
        json={
            "project_id": "project-a",
            "recipient_id": bob_actor.id,
            "permissions": ["read", "retrieve", "upload"],
        },
    )
    assert grant.status_code == 201

    def upload() -> int:
        return bob.post(
            "/api/documents",
            headers=ORIGIN,
            json={
                "project_id": "project-a",
                "name": "delegated-upload.txt",
                "content": "synthetic delegated upload",
                "kind": "personal",
            },
        ).status_code

    # The active delegation alone is enough for the backend to accept an upload
    assert upload() == 201

    # Bob has viewer role + active delegation for upload, but adding a concurrent role
    # that explicitly denies retrieve/upload immediately removes them from effective permissions.
    deny_role = admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={
            "name": "concurrent-deny-retrieve-upload",
            "permissions": [],
            "denied_permissions": ["retrieve", "upload"],
        },
    ).json()["id"]
    assert (
        admin.post(
            f"/api/projects/project-a/members/bob/roles/{deny_role}", headers=ORIGIN
        ).status_code
        == 204
    )
    preview = admin.get("/api/projects/project-a/members/bob/roles").json()
    assert set(preview["delegated_permissions"]) == {"read", "retrieve", "upload"}
    # Role-scoped denials stay on the role, yet they subtract from the effective set.
    assert preview["denied_permissions"] == []
    assert preview["effective_permissions"] == ["read"]

    # The backend, not UI hiding, enforces the concurrent role denial immediately.
    assert upload() == 403
