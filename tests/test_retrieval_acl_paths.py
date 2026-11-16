"""Current-ACL evidence for every existing retrieval path: nothing leaks after revocation.

The lexical, related, source, history, queued-job and model-context paths must each
re-evaluate permissions at the moment of access, so stale results never survive a
membership removal, publication revoke, account disable or explicit deny.
"""

from app.service import Principal, Service
from fastapi.testclient import TestClient
from test_api import ORIGIN, client_for, login


def viewer_and_admin(service: Service) -> tuple[TestClient, TestClient]:
    bob, admin = client_for(service), client_for(service)
    login(bob, "bob", "03")
    login(admin, "admin", "01")
    return bob, admin


def grant_to_viewer(service: Service, actor: Principal, document: str) -> None:
    service.publish(actor, document, [{"role": "viewer", "operations": ["read", "retrieve"]}])


def test_lexical_search_hides_documents_after_publication_revoke(service: Service) -> None:
    bob, admin = viewer_and_admin(service)
    actor = service.authenticate(admin.cookies.get("locus_session"))
    document = service.seed_synthetic("admin", "project-a", "shared")
    listed = bob.get("/api/documents", params={"project_id": "project-a", "q": "成膜"})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [document]
    assert bob.get(f"/api/documents/{document}").status_code == 200
    # The same search after the publication is revoked must not leak the document.
    service.publish(actor, document, [])
    assert bob.get("/api/documents", params={"project_id": "project-a", "q": "成膜"}).json() == []
    assert bob.get(f"/api/documents/{document}").status_code == 404


def test_lexical_search_denied_after_membership_removal(service: Service) -> None:
    bob, admin = viewer_and_admin(service)
    document = service.seed_synthetic("admin", "project-a", "shared")
    listed = bob.get("/api/documents", params={"project_id": "project-a"})
    assert [item["id"] for item in listed.json()] == [document]
    service.assign("bob", "project-a", None)
    assert bob.get("/api/documents", params={"project_id": "project-a"}).status_code == 404
    assert bob.get(f"/api/documents/{document}").status_code == 404


def test_related_documents_drop_after_revocation_and_explicit_deny(service: Service) -> None:
    bob, admin = viewer_and_admin(service)
    actor = service.authenticate(admin.cookies.get("locus_session"))
    source = service.seed_synthetic("admin", "project-a", "shared")
    target = service.seed_synthetic("admin", "project-a", "shared")
    path = f"/api/documents/{source}/related"
    assert [item["document"]["id"] for item in bob.get(path).json()] == [target]
    service.publish(actor, target, [])
    assert bob.get(path).json() == []
    # An explicit deny also removes the retrieval permission immediately.
    grant_to_viewer(service, actor, target)
    assert [item["document"]["id"] for item in bob.get(path).json()] == [target]
    service.set_membership_denials(actor, "project-a", "bob", ["retrieve"])
    assert bob.get(path).status_code == 404


def test_source_chunks_hidden_after_publication_revoke_or_disable(service: Service) -> None:
    bob, admin = viewer_and_admin(service)
    actor = service.authenticate(admin.cookies.get("locus_session"))
    document = service.seed_synthetic("admin", "project-a", "shared")
    chunks = bob.get(f"/api/documents/{document}/chunks")
    assert chunks.status_code == 200 and chunks.json()
    service.publish(actor, document, [])
    assert bob.get(f"/api/documents/{document}/chunks").status_code == 404
    grant_to_viewer(service, actor, document)
    assert bob.get(f"/api/documents/{document}/chunks").status_code == 200
    with service.db() as db:
        db.execute("UPDATE users SET enabled=0 WHERE username='bob'")
    assert bob.get(f"/api/documents/{document}/chunks").status_code == 401


def test_conversation_history_masks_generated_answer_after_revoke(service: Service) -> None:
    bob, admin = viewer_and_admin(service)
    actor = service.authenticate(admin.cookies.get("locus_session"))
    document = service.seed_synthetic("admin", "project-a", "shared")
    conversation = bob.post(
        "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
    ).json()["id"]
    message = bob.post(
        f"/api/conversations/{conversation}/messages", json={"text": "成膜"}, headers=ORIGIN
    ).json()
    assert message["citations"]
    with service.db() as db:
        db.execute(
            "INSERT INTO generated_answers VALUES (?,?,?)",
            (message["id"], "合成回答", "fixture-model"),
        )
    history = bob.get(f"/api/conversations/{conversation}").json()["messages"][0]
    assert history["answer"] == "合成回答"
    assert history["citations"]
    assert history.get("answer_hidden") is not True
    service.publish(actor, document, [])
    masked = bob.get(f"/api/conversations/{conversation}").json()["messages"][0]
    assert masked["answer"] is None
    assert masked["model"] is None
    assert masked["answer_hidden"] is True
    assert masked["citations"] == []


def test_queued_dialogue_fails_closed_after_membership_removal(service: Service) -> None:
    alice, admin = client_for(service), client_for(service)
    login(alice)
    login(admin, "admin", "01")
    service.seed_synthetic("admin", "project-a", "shared")
    token = alice.cookies.get("locus_session")
    actor = service.authenticate(token)
    captured: list[list[dict]] = []

    def generate(text: str, citations: list[dict]) -> tuple[str, str]:
        captured.append(citations)
        return "合成回答", "fixture-model"

    def enqueue(conversation: str) -> str:
        return service.enqueue_chat(
            actor,
            conversation,
            "成膜条件",
            "all",
            [],
            token=token,
            generate=generate,
            validate=None,
        )

    # Control: a queued job that keeps its permissions reaches the model and commits.
    control = enqueue(service.new_conversation(actor, "project-a")["id"])
    assert service.process_next_chat() is True
    assert service.chat_job(actor, control)["status"] == "done"
    assert captured and captured[0]
    # A job enqueued before its owner loses the project must never run with stale access.
    pending = enqueue(service.new_conversation(actor, "project-a")["id"])
    service.assign("alice", "project-a", None)
    assert service.process_next_chat() is True
    with service.db() as db:
        row = db.execute("SELECT status FROM chat_jobs WHERE id=?", (pending,)).fetchone()
        assert row["status"] == "failed"
        assert (
            db.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (pending,)
            ).fetchone()[0]
            == 0
        )
    assert len(captured) == 1  # the revoked job never reached the model


def test_model_context_only_contains_currently_authorized_citations(service: Service) -> None:
    bob, admin = viewer_and_admin(service)
    actor = service.authenticate(admin.cookies.get("locus_session"))
    first = service.seed_synthetic("admin", "project-a", "shared")
    second = service.seed_synthetic("admin", "project-a", "shared")
    token = bob.cookies.get("locus_session")
    principal = service.authenticate(token)
    conversation = service.new_conversation(principal, "project-a")["id"]
    captured: list[list[dict]] = []

    def generate(text: str, citations: list[dict]) -> tuple[str, str]:
        captured.append(citations)
        return "合成回答", "fixture-model"

    def ask() -> dict:
        result = service.send(
            principal,
            conversation,
            "成膜条件",
            "all",
            [],
            generate=generate,
            token=token,
        )
        assert result is not None
        return result

    before = ask()
    assert {citation["document_id"] for citation in before["citations"]} == {first, second}
    assert {citation["document_id"] for citation in captured[-1]} == {first, second}
    # After revocation the model context may only contain the still-authorized document.
    service.publish(actor, second, [])
    after = ask()
    assert {citation["document_id"] for citation in after["citations"]} == {first}
    assert {citation["document_id"] for citation in captured[-1]} == {first}
