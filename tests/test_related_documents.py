"""Live ACL and actual chunk provenance for local lexical relationships."""

import json

import pytest
from app.service import Service
from test_api import ORIGIN, client_for, login
from test_security import CallbackScanner


def test_relationship_evidence_and_live_revocation(service: Service) -> None:
    alice, admin = client_for(service), client_for(service)
    login(alice)
    login(admin, "admin", "01")
    source = service.seed_synthetic("alice", "project-a")
    target = service.seed_synthetic("admin", "project-a", "shared")
    hidden = service.seed_synthetic("admin", "project-a")
    service.seed_synthetic("eve", "project-b", "shared")
    path = f"/api/documents/{source}/related"
    response = alice.get(path)
    assert response.status_code == 200
    related = response.json()
    assert [item["document"]["id"] for item in related] == [target]
    assert hidden not in response.text
    item = related[0]
    assert item["method"] == "lexical-common-terms"
    assert item["shared_term_count"] >= len(item["evidence"]) > 0
    source_chunks = {c["id"]: c for c in alice.get(f"/api/documents/{source}/chunks").json()}
    target_chunks = {c["id"]: c for c in alice.get(f"/api/documents/{target}/chunks").json()}
    for evidence in item["evidence"]:
        for side, chunks in (("source", source_chunks), ("target", target_chunks)):
            chunk = chunks[evidence[f"{side}_chunk_id"]]
            assert chunk["page"] == evidence[f"{side}_page"]
            assert evidence["term"] in chunk["text"].lower()
    assert admin.get(path).status_code == 404  # Admin has no private-source bypass.
    assert (
        admin.put(
            f"/api/documents/{target}/publication", json={"grants": []}, headers=ORIGIN
        ).status_code
        == 204
    )
    assert alice.get(path).json() == []


@pytest.mark.parametrize("change", ["read_only", "role", "delete", "not_ready"])
def test_relationships_recheck_candidate_eligibility(service: Service, change: str) -> None:
    alice = client_for(service)
    login(alice)
    source = service.seed_synthetic("alice", "project-a")
    target = service.seed_synthetic("admin", "project-a", "shared")
    path = f"/api/documents/{source}/related"
    assert len(alice.get(path).json()) == 1
    with service.db() as db:
        if change == "read_only":
            db.execute(
                "UPDATE documents SET grants=? WHERE id=?",
                (json.dumps([{"role": "researcher", "operations": ["read"]}]), target),
            )
        elif change == "role":
            db.execute(
                "UPDATE memberships SET role='guest' WHERE project_id='project-a' "
                "AND user_id=(SELECT id FROM users WHERE username='alice')"
            )
        elif change == "delete":
            db.execute("DELETE FROM documents WHERE id=?", (target,))
        else:
            db.execute("UPDATE documents SET status='quarantined' WHERE id=?", (target,))
    response = alice.get(path)
    assert response.status_code == (404 if change == "role" else 200)
    if change != "role":
        assert response.json() == []


def test_relationships_attachment_context_and_pending_source(service: Service) -> None:
    alice, bob = client_for(service), client_for(service)
    login(alice)
    login(bob, "bob", "03")
    service.scanner = CallbackScanner()
    source = service.seed_synthetic("alice", "project-a")
    first = alice.post(
        "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
    ).json()["id"]
    other = alice.post(
        "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
    ).json()["id"]
    foreign = bob.post(
        "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
    ).json()["id"]
    attachment = alice.post(
        "/api/documents",
        json={
            "project_id": "project-a",
            "name": "sample.txt",
            "kind": "attachment",
            "conversation_id": first,
            "content": "成膜条件A unrelated",
        },
        headers=ORIGIN,
    ).json()["id"]
    assert (
        alice.get(
            f"/api/documents/{attachment}/related", params={"conversation_id": first}
        ).status_code
        == 409
    )
    service.process_next()
    path = f"/api/documents/{source}/related"
    assert alice.get(path).json() == []
    assert alice.get(path, params={"conversation_id": other}).json() == []
    assert alice.get(path, params={"conversation_id": foreign}).status_code == 404
    result = alice.get(path, params={"conversation_id": first}).json()
    assert [item["document"]["id"] for item in result] == [attachment]
    assert alice.get(f"/api/documents/{attachment}/related").status_code == 404


def test_relationships_are_bounded_deterministic_and_exclude_self(service: Service) -> None:
    alice = client_for(service)
    login(alice)
    source = service.seed_synthetic("alice", "project-a")
    targets = [service.seed_synthetic("alice", "project-a") for _ in range(12)]
    path = f"/api/documents/{source}/related"
    first = alice.get(path).json()
    assert len(first) == 10
    assert [item["document"]["id"] for item in first] == sorted(targets)[:10]
    assert first == alice.get(path).json()
