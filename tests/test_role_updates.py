"""Editing uses the creation ceiling and immediately rechecks existing grants."""

import json

import pytest
from app.service import Service
from test_api import ORIGIN, client_for, login


def test_role_edit_preserves_ids_and_revokes_live_access(service: Service) -> None:
    admin, bob = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(bob, "bob", "03")
    role = admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={"name": "参照担当", "permissions": ["read", "retrieve"]},
    ).json()["id"]
    service.assign("bob", "project-a", role)
    document = service.seed_synthetic("admin", "project-a")
    grants = [{"role": role, "operations": ["read", "retrieve"]}]
    assert (
        admin.put(
            f"/api/documents/{document}/publication", headers=ORIGIN, json={"grants": grants}
        ).status_code
        == 204
    )
    conversation = bob.post(
        "/api/conversations", headers=ORIGIN, json={"project_id": "project-a"}
    ).json()["id"]
    response = bob.post(
        f"/api/conversations/{conversation}/messages",
        headers=ORIGIN,
        json={"text": "成膜", "scope": "all", "attachment_ids": []},
    )
    assert {item["document_id"] for item in response.json()["citations"]} == {document}
    path = f"/api/projects/project-a/roles/{role}"
    edited = admin.put(
        path, headers=ORIGIN, json={"name": "閲覧担当", "permissions": ["read", "read"]}
    )
    assert edited.status_code == 200
    assert edited.json() == {"id": role, "name": "閲覧担当", "permissions": ["read"]}
    assert bob.get(f"/api/documents/{document}/chunks").status_code == 200
    assert bob.get(f"/api/documents/{document}/related").status_code == 404
    assert bob.get(f"/api/conversations/{conversation}").status_code == 403
    assert (
        admin.put(
            path, headers=ORIGIN, json={"name": "閲覧担当", "permissions": ["read", "retrieve"]}
        ).status_code
        == 200
    )
    assert bob.get(f"/api/conversations/{conversation}").json()["messages"][0]["citations"]
    assert (
        admin.put(path, headers=ORIGIN, json={"name": "閲覧担当", "permissions": []}).status_code
        == 200
    )
    assert bob.get(f"/api/documents/{document}/chunks").status_code == 404
    with service.db() as db:
        assert (
            db.execute(
                "SELECT role FROM memberships WHERE user_id="
                "(SELECT id FROM users WHERE username='bob') AND project_id='project-a'"
            ).fetchone()["role"]
            == role
        )
        assert db.execute("SELECT grants FROM documents WHERE id=?", (document,)).fetchone()[
            "grants"
        ] == json.dumps(grants)
    audit = admin.get("/api/admin/audit").json()
    events = [event for event in audit if event["operation"] == "role.update"]
    assert len(events) == 3
    assert all(event["target_id"] == role for event in events)
    assert "閲覧担当" not in str(events)


@pytest.mark.parametrize(
    "permissions", [["manage_roles"], ["manage_members"], ["root"], ["retrieve"]]
)
def test_role_edit_rejects_invalid_permissions_without_mutation(
    service: Service, permissions: list[str]
) -> None:
    admin = client_for(service)
    login(admin, "admin", "01")
    role = admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={"name": "変更前", "permissions": ["read"]},
    ).json()["id"]
    assert (
        admin.put(
            f"/api/projects/project-a/roles/{role}",
            headers=ORIGIN,
            json={"name": "変更後", "permissions": permissions},
        ).status_code
        == 422
    )
    catalog = admin.get("/api/projects/project-a/roles").json()["custom"]
    assert catalog[0]["name"] == "変更前" and catalog[0]["permissions"] == ["read"]
    assert not any(
        event["operation"] == "role.update" for event in admin.get("/api/admin/audit").json()
    )


def test_role_edit_checks_scope_ceiling_and_name_conflicts(service: Service) -> None:
    admin, alice, eve = client_for(service), client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(alice)
    login(eve, "eve", "04")
    created = admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={"name": "保持する名前", "permissions": ["read", "upload"]},
    ).json()
    role = created["id"]
    path = f"/api/projects/project-a/roles/{role}"
    data = {"name": "新しい名前", "permissions": ["read"]}
    assert client_for(service).put(path, headers=ORIGIN, json=data).status_code == 401
    rotation = client_for(service)
    assert (
        rotation.post(
            "/api/auth/login",
            headers=ORIGIN,
            json={"username": "bob", "password": "Temporary-password-03!"},
        ).status_code
        == 200
    )
    service.assign("bob", "project-a", "assistant_admin")
    assert rotation.put(path, headers=ORIGIN, json=data).status_code == 403
    assert alice.put(path, headers=ORIGIN, json=data).status_code == 403
    assert eve.put(path, headers=ORIGIN, json=data).status_code == 404
    for target in ("researcher", "missing"):
        assert (
            admin.put(
                f"/api/projects/project-a/roles/{target}", headers=ORIGIN, json=data
            ).status_code
            == 404
        )
    service.assign("admin", "project-b", "project_lead")
    assert (
        admin.put(f"/api/projects/project-b/roles/{role}", headers=ORIGIN, json=data).status_code
        == 404
    )
    admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={"name": "競合する名前", "permissions": []},
    )
    assert (
        admin.put(
            path, headers=ORIGIN, json={"name": "競合する名前", "permissions": []}
        ).status_code
        == 409
    )
    assert admin.put(path, headers=ORIGIN, json={"name": " ", "permissions": []}).status_code == 422
    assert admin.get("/api/projects/project-a/roles").json()["custom"][0] == {
        **created,
        "project_id": "project-a",
    }
    service.assign("alice", "project-a", "assistant_admin")
    assert (
        alice.put(
            path, headers=ORIGIN, json={"name": "新しい名前", "permissions": ["read", "upload"]}
        ).status_code
        == 422
    )
    assert alice.put(path, headers=ORIGIN, json=data).status_code == 200
    assert admin.get("/api/projects/project-a/roles").json()["custom"][0]["id"] == role


def test_role_update_rolls_back_when_audit_cannot_be_recorded(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = client_for(service)
    login(admin, "admin", "01")
    created = admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={"name": "監査前の状態", "permissions": ["read"]},
    ).json()

    def unavailable(*args: object) -> None:
        raise RuntimeError("synthetic audit unavailable")

    monkeypatch.setattr(service, "_audit", unavailable)
    with pytest.raises(RuntimeError, match="synthetic audit unavailable"):
        admin.put(
            f"/api/projects/project-a/roles/{created['id']}",
            headers=ORIGIN,
            json={"name": "保存されない名前", "permissions": []},
        )
    assert admin.get("/api/projects/project-a/roles").json()["custom"] == [
        {**created, "project_id": "project-a"}
    ]
    assert not any(
        event["operation"] == "role.update" for event in admin.get("/api/admin/audit").json()
    )
