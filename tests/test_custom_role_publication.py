"""Cloned project roles must work as scoped document publication targets."""

import json

from app.service import Service
from test_api import ORIGIN, client_for, login


def test_custom_role_publication_and_live_permission_ceiling(service: Service) -> None:
    admin, bob = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(bob, "bob", "03")
    created = admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={"name": "合成資料の参照担当", "permissions": ["read", "retrieve"]},
    )
    assert created.status_code == 201
    role = created.json()["id"]
    service.assign("bob", "project-a", role)
    document = service.seed_synthetic("admin", "project-a")
    publication = f"/api/documents/{document}/publication"
    grants = [{"role": role, "operations": ["read", "retrieve"]}]
    assert admin.put(publication, headers=ORIGIN, json={"grants": grants}).status_code == 204
    assert bob.get(f"/api/documents/{document}/chunks").status_code == 200
    conversation = bob.post(
        "/api/conversations", headers=ORIGIN, json={"project_id": "project-a"}
    ).json()["id"]

    def retrieve() -> dict:
        response = bob.post(
            f"/api/conversations/{conversation}/messages",
            headers=ORIGIN,
            json={"text": "成膜条件", "scope": "all", "attachment_ids": []},
        )
        assert response.status_code == 200
        return response.json()

    assert {c["document_id"] for c in retrieve()["citations"]} == {document}
    with service.db() as db:
        db.execute("UPDATE roles SET permissions=? WHERE id=?", (json.dumps(["read"]), role))
    assert bob.get(f"/api/documents/{document}/chunks").status_code == 200
    assert bob.get(f"/api/documents/{document}/related").status_code == 404
    assert bob.get(f"/api/conversations/{conversation}").status_code == 403
    with service.db() as db:
        db.execute(
            "UPDATE roles SET permissions=? WHERE id=?", (json.dumps(["read", "retrieve"]), role)
        )
    assert admin.put(publication, headers=ORIGIN, json={"grants": []}).status_code == 204
    assert bob.get(f"/api/documents/{document}/chunks").status_code == 404
    history = bob.get(f"/api/conversations/{conversation}").json()
    assert all(message["citations"] == [] for message in history["messages"])


def test_foreign_unknown_and_nonowner_custom_grants_are_rejected(service: Service) -> None:
    admin, alice, eve = client_for(service), client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(alice)
    login(eve, "eve", "04")
    service.assign("eve", "project-b", "project_lead")
    foreign = eve.post(
        "/api/projects/project-b/roles",
        headers=ORIGIN,
        json={"name": "別組織の担当", "permissions": ["read"]},
    ).json()["id"]
    document = service.seed_synthetic("admin", "project-a")
    path = f"/api/documents/{document}/publication"
    service.create_project("org-a", "project-c", "同じ組織の別プロジェクト")
    service.assign("admin", "project-c", "project_lead")
    same_org = admin.post(
        "/api/projects/project-c/roles",
        headers=ORIGIN,
        json={"name": "同じ組織の別担当", "permissions": ["read"]},
    ).json()["id"]
    for role in (foreign, same_org, "does-not-exist"):
        assert (
            admin.put(
                path, headers=ORIGIN, json={"grants": [{"role": role, "operations": ["read"]}]}
            ).status_code
            == 422
        )
    local = admin.post(
        "/api/projects/project-a/roles",
        headers=ORIGIN,
        json={"name": "このプロジェクトの担当", "permissions": ["read"]},
    ).json()["id"]
    grants = [{"role": local, "operations": ["read"]}]
    assert alice.put(path, headers=ORIGIN, json={"grants": grants}).status_code == 404
    assert (
        admin.put(
            path, headers=ORIGIN, json={"grants": [{"role": local, "operations": ["retrieve"]}]}
        ).status_code
        == 422
    )
    assert admin.get(f"/api/documents/{document}").json()["kind"] == "personal"
