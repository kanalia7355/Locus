"""Synthetic storage-source connector, sync cycle and original-source ACL (DATA-008)."""

import sqlite3
from pathlib import Path

import pytest
from app.connectors.scheduler import SourceScheduler
from app.connectors.synthetic import SyntheticSourceConnector
from app.scanner import CLEAN, ScanResult
from app.service import Principal, Service
from fastapi import HTTPException
from test_api import ORIGIN, client_for, login

SOURCE_ID = "synthetic-local"
OBJECT_ID = "synthetic-object-1"
CONTENT = (
    "【合成サンプル・実研究データではありません】\n"
    "成膜条件Aは処理温度180°C、処理時間30分。\n"
    "成膜条件Bは処理温度200°C、処理時間20分。\n"
)


class AcceptingScanner:
    def scan(self, content: str) -> ScanResult:
        return CLEAN


class RevokingDuringScanScanner:
    """Accepts the content, then drops the source-side read permission mid-scan."""

    def __init__(
        self, connector: SyntheticSourceConnector, user_id: str, object_id: str = OBJECT_ID
    ) -> None:
        self.connector = connector
        self.user_id = user_id
        self.object_id = object_id

    def scan(self, content: str) -> ScanResult:
        self.connector.set_readable(self.object_id, self.user_id, False)
        return CLEAN


class RaisingSourceConnector(SyntheticSourceConnector):
    def can_read(self, source_id: str, object_id: str, user_id: str) -> bool | None:
        raise TimeoutError("source connector unavailable")


def add_source_object(
    service: Service,
    object_id: str = OBJECT_ID,
    *,
    readable_by: dict[str, bool] | None = None,
) -> SyntheticSourceConnector:
    connector = service.source_connector_for(SOURCE_ID)
    if not isinstance(connector, SyntheticSourceConnector):
        raise AssertionError("synthetic source connector expected")
    connector.add(
        object_id,
        revision="rev-1",
        name="合成サンプル_成膜条件.txt",
        content=CONTENT,
        readable_by=readable_by
        if readable_by is not None
        else {"admin": True, "bob": True, "alice": True},
    )
    return connector


def ingest_source(
    service: Service,
    actor: Principal,
    object_id: str = OBJECT_ID,
    *,
    kind: str = "shared",
) -> str:
    document = service.source_ingest(
        actor,
        SOURCE_ID,
        object_id,
        CONTENT,
        "合成サンプル_成膜条件.txt",
        kind=kind,
        project="project-a",
    )
    return str(document["id"])


def document_status(service: Service, document: str) -> str:
    with service.db() as db:
        return str(db.execute("SELECT status FROM documents WHERE id=?", (document,)).fetchone()[0])


def chunk_count(service: Service, document: str) -> int:
    with service.db() as db:
        return int(
            db.execute("SELECT COUNT(*) FROM chunks WHERE document_id=?", (document,)).fetchone()[0]
        )


# --- Scheduler interval and notification control ---------------------------------


def test_source_sync_interval_default_can_be_overridden_and_validated(service: Service) -> None:
    assert service.source_interval_seconds == 600
    assert service.source_scheduler.interval_seconds == 600
    service.set_source_interval_seconds(120)
    assert service.source_interval_seconds == 120
    assert service.source_scheduler.interval_seconds == 120
    for invalid in (0, -5, 600.5, "600"):
        with pytest.raises(HTTPException) as caught:
            service.set_source_interval_seconds(invalid)  # type: ignore[arg-type]
        assert caught.value.status_code == 422


def test_source_scheduler_defaults_to_ten_minute_cycle_and_honors_notification() -> None:
    scheduler = SourceScheduler(interval_seconds=600, clock=lambda: 1000.0)
    assert scheduler.interval_seconds == 600
    assert scheduler.should_run(SOURCE_ID, now=1000.0) is True
    scheduler.mark_run(SOURCE_ID, now=1000.0)
    assert scheduler.should_run(SOURCE_ID, now=1000.0) is False
    assert scheduler.should_run(SOURCE_ID, now=1000.0 + 599.0) is False
    assert scheduler.should_run(SOURCE_ID, now=1000.0 + 600.0) is True
    scheduler.notify(SOURCE_ID)
    assert scheduler.should_run(SOURCE_ID, now=1000.0) is True


# --- Simultaneous invisibility across all six retrieval paths ------------------


def test_source_revocation_hides_all_six_paths_simultaneously(service: Service) -> None:
    service.scanner = AcceptingScanner()
    admin = client_for(service)
    login(admin, "admin", "01")
    actor = service.authenticate(admin.cookies.get("locus_session"))
    connector = add_source_object(service, readable_by={"admin": True, "bob": True, "alice": True})
    document = ingest_source(service, actor, kind="shared")
    assert service.process_next() is True
    assert document_status(service, document) == "ready"

    bob = client_for(service)
    login(bob, "bob", "03")
    service.authenticate(bob.cookies.get("locus_session"))

    # (a) listing
    listed = bob.get("/api/documents", params={"project_id": "project-a"})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [document]
    # (a-owner) The ingesting owner's listing branch must apply the same source
    # gate; this branch is the one that does not go through _can_read.
    owner_listed = admin.get("/api/documents", params={"project_id": "project-a"})
    assert [item["id"] for item in owner_listed.json()] == [document]
    # (b) document body
    assert bob.get(f"/api/documents/{document}").status_code == 200
    chunks = bob.get(f"/api/documents/{document}/chunks")
    assert chunks.status_code == 200 and chunks.json()
    # (c) related documents
    assert bob.get(f"/api/documents/{document}/related").status_code == 200
    # (d) question search candidates and (e) conversation citations via a question
    conversation = bob.post(
        "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
    ).json()["id"]
    asked = bob.post(
        f"/api/conversations/{conversation}/messages",
        json={"text": "成膜条件", "scope": "all", "attachment_ids": []},
        headers=ORIGIN,
    )
    assert asked.status_code == 200
    assert asked.json()["citations"]
    with service.db() as db:
        db.execute(
            "INSERT INTO generated_answers VALUES (?,?,?)",
            (asked.json()["id"], "合成回答", "fixture-model"),
        )
    history = bob.get(f"/api/conversations/{conversation}").json()["messages"][0]
    # (f) generated answer
    assert history["answer"] == "合成回答"
    assert history["citations"]

    connector.set_readable(OBJECT_ID, "bob", False)
    # The ingesting owner must lose source access too, or its owner-listing
    # branch would still be allowed by the source and the assertion vacuous.
    connector.set_readable(OBJECT_ID, "admin", False)
    assert service.source_cycle(SOURCE_ID) is True

    # The same source-side revocation must hide all six paths at once.
    assert bob.get("/api/documents", params={"project_id": "project-a"}).json() == []
    assert admin.get("/api/documents", params={"project_id": "project-a"}).json() == []
    assert bob.get(f"/api/documents/{document}").status_code == 404
    assert bob.get(f"/api/documents/{document}/chunks").status_code == 404
    assert bob.get(f"/api/documents/{document}/related").status_code == 404
    asked_after = bob.post(
        f"/api/conversations/{conversation}/messages",
        json={"text": "成膜条件", "scope": "all", "attachment_ids": []},
        headers=ORIGIN,
    )
    assert asked_after.status_code == 200
    assert asked_after.json()["citations"] == []
    history_after = bob.get(f"/api/conversations/{conversation}").json()["messages"][0]
    assert history_after["citations"] == []
    assert history_after["answer"] is None
    assert history_after["answer_hidden"] is True


# --- Immediate notification firing ---------------------------------------------


def test_source_notification_fires_cycle_immediately_without_clock_advance(
    service: Service,
) -> None:
    scheduler = SourceScheduler(interval_seconds=600, clock=lambda: 1000.0)
    service.source_scheduler = scheduler
    service.scanner = AcceptingScanner()
    admin = client_for(service)
    login(admin, "admin", "01")
    actor = service.authenticate(admin.cookies.get("locus_session"))
    connector = add_source_object(service, readable_by={"admin": True, "bob": True})
    document = ingest_source(service, actor, kind="shared")
    assert service.process_next() is True
    assert chunk_count(service, document) == 1
    scheduler.mark_run(SOURCE_ID, now=1000.0)
    assert scheduler.should_run(SOURCE_ID, now=1000.0) is False
    connector.set_readable(OBJECT_ID, "admin", False)
    # Without a notification the interval gate stays closed at the same clock:
    # the cycle does not run, so the derived chunk is not cleaned up.
    assert scheduler.should_run(SOURCE_ID, now=1000.0) is False
    assert chunk_count(service, document) == 1
    service.source_notify(SOURCE_ID, actor.id)
    assert scheduler.should_run(SOURCE_ID, now=1000.0) is True
    # The worker loop drives the cycle as soon as the scheduler reports due,
    # without waiting for the 600-second interval.
    assert service.source_cycle(SOURCE_ID) is True
    assert chunk_count(service, document) == 0
    assert document_status(service, document) == "failed"


# --- Permission hash comparison -----------------------------------------------


def test_source_permission_hash_change_fires_and_stable_hash_skips(service: Service) -> None:
    service.scanner = AcceptingScanner()
    admin = client_for(service)
    login(admin, "admin", "01")
    actor = service.authenticate(admin.cookies.get("locus_session"))
    add_source_object(service, readable_by={"admin": True, "bob": True, "alice": True})
    document = ingest_source(service, actor, kind="shared")
    assert service.source_cycle(SOURCE_ID) is False
    with service.db() as db:
        stored_hash = str(
            db.execute(
                "SELECT permission_hash FROM source_objects WHERE source_id=? AND object_id=?",
                (SOURCE_ID, OBJECT_ID),
            ).fetchone()["permission_hash"]
        )
    connector = add_source_object(service, readable_by={"admin": True, "bob": True, "alice": True})
    connector.set_readable(OBJECT_ID, "alice", False)
    assert service.source_cycle(SOURCE_ID) is True
    with service.db() as db:
        changed_hash = str(
            db.execute(
                "SELECT permission_hash FROM source_objects WHERE source_id=? AND object_id=?",
                (SOURCE_ID, OBJECT_ID),
            ).fetchone()["permission_hash"]
        )
    assert changed_hash != stored_hash
    with service.db() as db:
        chunks_before = int(
            db.execute("SELECT COUNT(*) FROM chunks WHERE document_id=?", (document,)).fetchone()[0]
        )
    assert service.source_cycle(SOURCE_ID) is False
    with service.db() as db:
        assert (
            int(
                db.execute(
                    "SELECT COUNT(*) FROM chunks WHERE document_id=?", (document,)
                ).fetchone()[0]
            )
            == chunks_before
        )


# --- Undecidable source state fails closed -------------------------------------


def test_undecidable_source_state_hides_bound_document_without_leaking_error(
    tmp_path: Path,
) -> None:
    svc = Service(
        tmp_path / "source.sqlite3",
        scanner=AcceptingScanner(),
        source_connector=RaisingSourceConnector(),
    )
    try:
        svc.provision("admin", "Temporary-password-01!", system_admin=True)
        svc.provision("alice", "Temporary-password-02!")
        svc.create_project("org-a", "project-a", "研究プロジェクト")
        svc.assign("admin", "project-a", "project_lead")
        svc.assign("alice", "project-a", "researcher")
        client = client_for(svc)
        login(client, "admin", "01")
        actor = svc.authenticate(client.cookies.get("locus_session"))
        connector = svc.source_connector_for(SOURCE_ID)
        assert isinstance(connector, SyntheticSourceConnector)
        connector.add(OBJECT_ID, revision="rev-1", content=CONTENT, readable_by={"admin": True})
        document_json = svc.source_ingest(
            actor,
            SOURCE_ID,
            OBJECT_ID,
            CONTENT,
            "合成サンプル_成膜条件.txt",
            kind="personal",
            project="project-a",
        )
        document = str(document_json["id"])
        assert svc.process_next() is True
        with svc.db() as db:
            assert (
                db.execute("SELECT status FROM documents WHERE id=?", (document,)).fetchone()[0]
                != "ready"
            )
            assert (
                int(
                    db.execute(
                        "SELECT COUNT(*) FROM chunks WHERE document_id=?", (document,)
                    ).fetchone()[0]
                )
                == 0
            )
        assert client.get(f"/api/documents/{document}").status_code == 404
        assert client.get(f"/api/documents/{document}/chunks").status_code == 404
    finally:
        svc.close()


# --- Connector credential is not the user's source permission ------------------


def test_connector_credential_does_not_grant_user_source_access(service: Service) -> None:
    service.scanner = AcceptingScanner()
    admin = client_for(service)
    login(admin, "admin", "01")
    actor = service.authenticate(admin.cookies.get("locus_session"))
    # Source allows the service account and alice, but not bob: the connector
    # credential must not become the user's source permission.
    add_source_object(service, readable_by={"admin": True, "alice": True})
    document = ingest_source(service, actor, kind="shared")
    assert service.process_next() is True
    assert [
        item["id"]
        for item in admin.get("/api/documents", params={"project_id": "project-a"}).json()
    ] == [document]
    bob = client_for(service)
    login(bob, "bob", "03")
    assert bob.get("/api/documents", params={"project_id": "project-a"}).json() == []

    # Reverse direction: source allows the user, but Locus-side ownership denies.
    alice = client_for(service)
    login(alice, "alice", "02")
    alice_actor = service.authenticate(alice.cookies.get("locus_session"))
    personal = ingest_source(service, alice_actor, kind="personal")
    assert alice.get(f"/api/documents/{personal}").status_code == 200
    assert bob.get(f"/api/documents/{personal}").status_code == 404


# --- Two-check ingestion with source permission --------------------------------


def test_ingestion_source_check_runs_before_scan_and_before_index(service: Service) -> None:
    service.scanner = AcceptingScanner()
    admin = client_for(service)
    login(admin, "admin", "01")
    service.authenticate(admin.cookies.get("locus_session"))
    alice = client_for(service)
    login(alice, "alice", "02")
    alice_actor = service.authenticate(alice.cookies.get("locus_session"))
    connector = add_source_object(service, readable_by={"alice": True})
    document = ingest_source(service, alice_actor, kind="personal")
    connector.set_readable(OBJECT_ID, "alice", False)
    assert service.process_next() is True
    assert document_status(service, document) == "cancelled"
    assert chunk_count(service, document) == 0

    connector.add(
        "synthetic-object-2",
        revision="rev-1",
        name="合成サンプル_成膜条件B.txt",
        content=CONTENT,
        readable_by={"alice": True},
    )
    document_two = ingest_source(service, alice_actor, "synthetic-object-2", kind="personal")
    service.scanner = RevokingDuringScanScanner(connector, "alice", "synthetic-object-2")
    assert service.process_next() is True
    assert document_status(service, document_two) == "cancelled"
    assert chunk_count(service, document_two) == 0


# --- Hide first, then clean up chunks -----------------------------------------


def test_source_revocation_cancels_indexed_chunks(service: Service) -> None:
    service.scanner = AcceptingScanner()
    admin = client_for(service)
    login(admin, "admin", "01")
    service.authenticate(admin.cookies.get("locus_session"))
    alice = client_for(service)
    login(alice, "alice", "02")
    alice_actor = service.authenticate(alice.cookies.get("locus_session"))
    connector = add_source_object(service, readable_by={"alice": True})
    document = ingest_source(service, alice_actor, kind="personal")
    assert service.process_next() is True
    assert chunk_count(service, document) == 1
    connector.set_readable(OBJECT_ID, "alice", False)
    assert service.source_cycle(SOURCE_ID) is True
    with service.db() as db:
        assert (
            int(
                db.execute(
                    "SELECT COUNT(*) FROM chunks WHERE document_id=?", (document,)
                ).fetchone()[0]
            )
            == 0
        )
        assert (
            str(db.execute("SELECT status FROM documents WHERE id=?", (document,)).fetchone()[0])
            == "failed"
        )


def test_source_cleanup_failure_keeps_document_hidden(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.scanner = AcceptingScanner()
    admin = client_for(service)
    login(admin, "admin", "01")
    service.authenticate(admin.cookies.get("locus_session"))
    alice = client_for(service)
    login(alice, "alice", "02")
    alice_actor = service.authenticate(alice.cookies.get("locus_session"))
    connector = add_source_object(service, readable_by={"alice": True})
    document = ingest_source(service, alice_actor, kind="personal")
    assert service.process_next() is True
    connector.set_readable(OBJECT_ID, "alice", True)

    def broken_cleanup(db: object, document_id: str) -> None:
        raise RuntimeError("cleanup unavailable")

    monkeypatch.setattr(service, "_cleanup_source_document", broken_cleanup)
    connector.set_readable(OBJECT_ID, "alice", False)
    with pytest.raises(RuntimeError):
        service.source_cycle(SOURCE_ID)
    # Invisibility is fail-closed on the source gate and survives a failed cleanup.
    assert alice.get(f"/api/documents/{document}").status_code == 404
    assert chunk_count(service, document) == 1


def test_legacy_database_without_source_tables_still_opens(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    first = Service(path)
    first.close()
    connection = sqlite3.connect(path)
    for table in ("document_source_bindings", "source_objects", "storage_sources"):
        connection.execute(f"DROP TABLE IF EXISTS {table}")
    connection.commit()
    connection.close()
    second = Service(path)
    second.close()
