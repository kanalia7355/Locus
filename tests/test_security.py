import socket
import time
from collections.abc import Callable

import pytest
from app.service import PASSWORDS, Service, digest
from fastapi import HTTPException
from test_api import ORIGIN, client_for, login


class CallbackScanner:
    def __init__(self, action: Callable[[], None] = lambda: None) -> None:
        self.action = action

    def scan(self, content: str) -> bool:
        self.action()
        return True


def test_hashes_temporary_expiry_and_session_expiry(service: Service) -> None:  # noqa: F811
    with service.db() as db:
        user = db.execute("SELECT * FROM users WHERE username='alice'").fetchone()
        assert user["password_hash"].startswith("$argon2id$")
        assert PASSWORDS.verify(user["password_hash"], "Temporary-password-02!")
        db.execute("UPDATE users SET temp_expires=? WHERE id=?", (time.time() - 1, user["id"]))
    client = client_for(service)
    assert (
        client.post(
            "/api/auth/login",
            json={
                "username": "alice",
                "password": "Temporary-password-02!",
            },
            headers=ORIGIN,
        ).status_code
        == 401
    )
    login(client, "bob", "03")
    token = client.cookies.get("locus_session")
    with service.db() as db:
        db.execute(
            "UPDATE sessions SET last_seen=? WHERE token_hash=?",
            (time.time() - 1801, digest(token)),
        )
    assert client.get("/api/projects").status_code == 401
    client.post(
        "/api/auth/login",
        json={"username": "bob", "password": "Changed-password-long-01!"},
        headers=ORIGIN,
    )
    with service.db() as db:
        db.execute("UPDATE sessions SET expires=?", (time.time() - 1,))
    assert client.get("/api/projects").status_code == 401


def test_login_limit_and_unknown_account_errors(service: Service) -> None:  # noqa: F811
    client = client_for(service)
    invalid_input = "bad"
    unknown = client.post(
        "/api/auth/login", json={"username": "unknown", "password": invalid_input}, headers=ORIGIN
    )
    known = client.post(
        "/api/auth/login", json={"username": "alice", "password": invalid_input}, headers=ORIGIN
    )
    assert unknown.status_code == known.status_code == 401
    assert unknown.json() == known.json()
    for _ in range(4):
        assert (
            client.post(
                "/api/auth/login",
                json={"username": "alice", "password": invalid_input},
                headers=ORIGIN,
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"username": "alice", "password": invalid_input}, headers=ORIGIN
        ).status_code
        == 429
    )


@pytest.mark.parametrize("action", ["delete", "cancel", "revoke", "disable"])
def test_ingestion_final_transaction_blocks_stale_work(service: Service, action: str) -> None:  # noqa: F811
    client = client_for(service)
    login(client)
    actor = service.authenticate(client.cookies.get("locus_session"))
    doc = service.upload(actor, "project-a", "synthetic.txt", "合成テスト\f2ページ目", "personal")

    def race() -> None:
        if action == "delete":
            service.delete_document(actor, doc["id"])
        elif action == "cancel":
            service.cancel(actor, doc["id"])
        elif action == "revoke":
            service.assign("alice", "project-a", None)
        else:
            with service.db() as db:
                db.execute("UPDATE users SET enabled=0 WHERE id=?", (actor.id,))

    service.scanner = CallbackScanner(race)
    assert service.process_next()
    with service.db() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM chunks WHERE document_id=?", (doc["id"],)).fetchone()[
                0
            ]
            == 0
        )
        row = db.execute("SELECT * FROM documents WHERE id=?", (doc["id"],)).fetchone()
        assert row is None if action == "delete" else row["status"] == "cancelled"


def test_synthetic_scanned_pages_and_attachment_conversation_binding(service: Service) -> None:  # noqa: F811
    client = client_for(service)
    login(client)
    actor = service.authenticate(client.cookies.get("locus_session"))
    one = service.new_conversation(actor, "project-a")["id"]
    two = service.new_conversation(actor, "project-a")["id"]
    doc = service.upload(
        actor, "project-a", "sample.txt", "成膜の合成検証\f2ページ目", "attachment", one
    )
    service.scanner = CallbackScanner()
    service.process_next()
    assert len(service.chunks(actor, doc["id"], one)) == 2
    with pytest.raises(HTTPException) as error:
        service.chunks(actor, doc["id"], two)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException):
        service.chunks(actor, doc["id"])
    assert service.send(actor, two, "成膜", "all", [])["citations"] == []
    assert service.send(actor, one, "成膜", "all", [doc["id"]])["citations"]
    service.delete_conversation(actor, one)
    with service.db() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM chunks WHERE document_id=?", (doc["id"],)).fetchone()[
                0
            ]
            == 0
        )


def test_queue_capacity_and_cancel(service: Service) -> None:  # noqa: F811
    client = client_for(service)
    login(client)
    actor = service.authenticate(client.cookies.get("locus_session"))
    docs = [
        service.upload(actor, "project-a", f"{index}.txt", "synthetic", "personal")
        for index in range(4)
    ]
    with pytest.raises(HTTPException) as error:
        service.upload(actor, "project-a", "overflow.txt", "synthetic", "personal")
    assert error.value.status_code == 429
    service.cancel(actor, docs[0]["id"])
    assert service.upload(actor, "project-a", "next.txt", "synthetic", "personal")


def test_publication_rechecks_history_and_prevents_escalation(service: Service) -> None:  # noqa: F811
    admin, bob = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(bob, "bob", "03")
    actor = service.authenticate(admin.cookies.get("locus_session"))
    doc = service.seed_synthetic("admin", "project-a", "personal")
    assert bob.get(f"/api/documents/{doc}").status_code == 404
    service.publish(
        actor,
        doc,
        [
            {"role": "project_lead", "operations": ["read", "retrieve"]},
            {"role": "viewer", "operations": ["read", "retrieve"]},
        ],
    )
    assert bob.get(f"/api/documents/{doc}").status_code == 200
    cid = bob.post("/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN).json()[
        "id"
    ]
    assert bob.post(
        f"/api/conversations/{cid}/messages", json={"text": "成膜"}, headers=ORIGIN
    ).json()["citations"]
    service.publish(actor, doc, [{"role": "project_lead", "operations": ["read", "retrieve"]}])
    assert bob.get(f"/api/conversations/{cid}").json()["messages"][0]["citations"] == []
    assert bob.get(f"/api/documents/{doc}/chunks").status_code == 404
    assert (
        bob.put(
            f"/api/documents/{doc}/publication", json={"grants": []}, headers=ORIGIN
        ).status_code
        == 404
    )


def test_local_retrieval_does_not_open_external_sockets(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: F811
    original = socket.socket.connect

    def blocked(sock: socket.socket, address: object) -> None:
        # Windows asyncio constructs its internal socketpair over loopback TCP.
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            original(sock, address)
            return
        raise AssertionError("Unexpected external connection")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    client = client_for(service)
    login(client)
    service.seed_synthetic("alice", "project-a")
    cid = client.post(
        "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
    ).json()["id"]
    assert client.post(
        f"/api/conversations/{cid}/messages", json={"text": "成膜"}, headers=ORIGIN
    ).json()["citations"]


def test_reject_cloud_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import create_app

    monkeypatch.setenv("ALLOW_CLOUD_EGRESS", "true")
    with pytest.raises(RuntimeError, match="Cloud"):
        create_app()
