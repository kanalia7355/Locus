import threading
from pathlib import Path

from app.service import Service
from test_api import ORIGIN, client_for, login
from test_security import CallbackScanner


def test_publisher_can_stop_or_delete_even_without_a_recipient_grant(service: Service) -> None:
    admin, alice = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(alice)
    for action in ("stop", "delete"):
        document = service.seed_synthetic("admin", "project-a")
        assert (
            admin.put(
                f"/api/documents/{document}/publication",
                json={
                    "grants": [{"role": "researcher", "operations": ["read", "retrieve"]}],
                },
                headers=ORIGIN,
            ).status_code
            == 204
        )
        assert alice.get(f"/api/documents/{document}").status_code == 200
        owned = admin.get("/api/documents?project_id=project-a").json()
        assert any(doc["id"] == document and doc["owned"] for doc in owned)
        if action == "stop":
            assert (
                admin.put(
                    f"/api/documents/{document}/publication", json={"grants": []}, headers=ORIGIN
                ).status_code
                == 204
            )
            assert admin.get(f"/api/documents/{document}").json()["kind"] == "personal"
        else:
            assert admin.delete(f"/api/documents/{document}", headers=ORIGIN).status_code == 204
        assert alice.get(f"/api/documents/{document}").status_code == 404


def test_final_index_transaction_serializes_independent_connection_revocation(
    service: Service,
    tmp_path: Path,
) -> None:
    client = client_for(service)
    login(client)
    actor = service.authenticate(client.cookies.get("locus_session"))
    document = service.upload(actor, "project-a", "race.txt", "synthetic race", "personal")
    other = Service(tmp_path / "test.sqlite3")
    service.scanner = CallbackScanner()
    indexing = threading.Event()
    release = threading.Event()
    revoking = threading.Event()
    revoked = threading.Event()
    errors: list[BaseException] = []
    original = service._index

    def paused_index(db: object, row: object) -> None:
        indexing.set()
        if not release.wait(4):
            raise AssertionError("Test index release timed out")
        original(db, row)  # type: ignore[arg-type]

    def index() -> None:
        try:
            service.process_next()
        except BaseException as error:
            errors.append(error)

    def revoke() -> None:
        try:
            revoking.set()
            other.assign("alice", "project-a", None)
            revoked.set()
        except BaseException as error:
            errors.append(error)

    service._index = paused_index  # type: ignore[method-assign]
    worker = threading.Thread(target=index)
    revoker = threading.Thread(target=revoke)
    worker.start()
    try:
        assert indexing.wait(3)
        revoker.start()
        assert revoking.wait(3)
        # The independent writer must wait for the checked publication transaction.
        assert not revoked.wait(0.15)
    finally:
        release.set()
        worker.join(5)
        if revoker.ident is not None:
            revoker.join(5)
        other.close()
    assert not worker.is_alive() and not revoker.is_alive()
    assert not errors
    assert revoked.is_set()
    assert client.get(f"/api/documents/{document['id']}/chunks").status_code == 404
