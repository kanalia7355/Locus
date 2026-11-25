from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from app.main import create_app
from app.service import Service
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://127.0.0.1:5174"}


def _load_connectors_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "locus_connectors_base",
        Path(__file__).resolve().parents[1] / "backend" / "app" / "connectors.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


connectors = _load_connectors_module()
SourceItem = connectors.SourceItem
SyncEngine = connectors.SyncEngine


class FakeConnector:
    def __init__(self, items: list[Any] | None = None) -> None:
        self.items = list(items or [])
        self.contents: dict[str, bytes] = {}
        self.list_calls = 0
        self.fetch_calls: list[str] = []

    def list_items(self, cursor: str | None = None) -> tuple[list[Any], str | None]:
        self.list_calls += 1
        if cursor is None:
            return list(self.items), None
        return [], None

    def fetch_content(self, external_id: str) -> bytes:
        self.fetch_calls.append(external_id)
        return self.contents[external_id]


def login(client: TestClient, username: str = "admin", number: str = "01") -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": f"Temporary-password-{number}!"},
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


def admin_actor(service: Service) -> Any:
    with service.db() as db:
        row = db.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    from app.service import Principal

    return Principal(row["id"], row["username"], bool(row["system_admin"]), False)


def test_sync_registers_documents_and_records_origin(service: Service) -> None:
    connector = FakeConnector([SourceItem("ext-1", "note.txt", "rev-1", "h1", 12, 1.0)])
    connector.contents["ext-1"] = b"hello connector"
    service.register_sync_connector("fake", connector, configured=True)

    result = SyncEngine(service).sync(
        admin_actor(service),
        "project-a",
        connector,
        "fake-source",
        connector_id="fake",
    )

    assert result["registered"] == 1
    assert result["updated"] == 0
    assert result["skipped"] == 0
    assert result["failed"] == 0
    assert result["revoked"] == 0

    origin = service.get_document_origin("fake", "ext-1")
    assert origin is not None
    assert origin["connector_id"] == "fake"
    assert origin["external_id"] == "ext-1"
    assert origin["external_revision"] == "rev-1"
    assert origin["source_label"] == "fake-source"
    assert origin["revoked"] is False

    with service.db() as db:
        doc = db.execute("SELECT * FROM documents WHERE id=?", (origin["document_id"],)).fetchone()
    assert doc is not None
    assert doc["name"] == "note.txt"
    assert doc["content"] == "hello connector"
    assert doc["kind"] == "personal"
    assert doc["status"] == "queued"


def test_sync_is_idempotent_and_revision_creates_new_document(service: Service) -> None:
    connector = FakeConnector([SourceItem("ext-1", "note.txt", "rev-1", "h1", 12, 1.0)])
    connector.contents["ext-1"] = b"hello connector"
    service.register_sync_connector("fake", connector, configured=True)
    actor = admin_actor(service)

    first = SyncEngine(service).sync(
        actor, "project-a", connector, "fake-source", connector_id="fake"
    )
    first_origin = service.get_document_origin("fake", "ext-1")
    assert first_origin is not None
    connector.fetch_calls.clear()

    second = SyncEngine(service).sync(
        actor, "project-a", connector, "fake-source", connector_id="fake"
    )
    second_origin = service.get_document_origin("fake", "ext-1")
    assert first["registered"] == 1
    assert second["registered"] == 0
    assert second["updated"] == 0
    assert second["skipped"] == 1
    assert connector.fetch_calls == []
    assert second_origin is not None
    assert second_origin["document_id"] == first_origin["document_id"]

    connector.items = [SourceItem("ext-1", "note.txt", "rev-2", "h2", 13, 2.0)]
    connector.contents["ext-1"] = b"hello changed"
    third = SyncEngine(service).sync(
        actor, "project-a", connector, "fake-source", connector_id="fake"
    )
    third_origin = service.get_document_origin("fake", "ext-1")
    assert third["updated"] == 1
    assert third["registered"] == 0
    assert third_origin is not None
    assert third_origin["document_id"] != first_origin["document_id"]
    assert third_origin["external_revision"] == "rev-2"

    with service.db() as db:
        docs = db.execute(
            "SELECT id,content FROM documents WHERE name='note.txt' ORDER BY created"
        ).fetchall()
    assert len(docs) == 2
    assert {row["content"] for row in docs} == {"hello connector", "hello changed"}


def test_sync_skips_invalid_format_and_oversize_without_retaining_content(
    service: Service,
) -> None:
    bad = b"TOP SECRET SHOULD NOT BE STORED"
    connector = FakeConnector(
        [
            SourceItem("ext-bad-ext", "image.png", "rev-1", "h1", 10, 1.0),
            SourceItem("ext-bad-utf8", "bad.txt", "rev-1", "h2", 10, 1.0),
            SourceItem("ext-big", "big.txt", "rev-1", "h3", 300000, 1.0),
            SourceItem("ext-ok", "ok.txt", "rev-1", "h4", 2, 1.0),
        ]
    )
    connector.contents["ext-bad-ext"] = b"binary"
    connector.contents["ext-bad-utf8"] = b"\xff\xfe\x00"
    connector.contents["ext-big"] = b"a" * 300000
    connector.contents["ext-ok"] = b"ok"
    service.register_sync_connector("fake", connector, configured=True)

    result = SyncEngine(service).sync(
        admin_actor(service),
        "project-a",
        connector,
        "fake-source",
        connector_id="fake",
    )

    assert result["registered"] == 1
    assert result["skipped"] == 3
    assert result["failed"] == 0
    assert service.get_document_origin("fake", "ext-bad-ext") is None
    assert service.get_document_origin("fake", "ext-bad-utf8") is None
    assert service.get_document_origin("fake", "ext-big") is None
    assert service.get_document_origin("fake", "ext-ok") is not None

    with service.db() as db:
        docs = db.execute("SELECT name,content FROM documents").fetchall()
    assert [(row["name"], row["content"]) for row in docs] == [("ok.txt", "ok")]
    assert bad not in b"".join(row["content"].encode("utf-8") for row in docs)
    assert "TOP SECRET" not in str(result)
    assert "image.png" not in str(result)


def test_sync_marks_missing_items_revoked(service: Service) -> None:
    connector = FakeConnector([SourceItem("ext-1", "note.txt", "rev-1", "h1", 4, 1.0)])
    connector.contents["ext-1"] = b"note"
    service.register_sync_connector("fake", connector, configured=True)
    actor = admin_actor(service)

    SyncEngine(service).sync(actor, "project-a", connector, "label", connector_id="fake")
    connector.items = []
    result = SyncEngine(service).sync(actor, "project-a", connector, "label", connector_id="fake")

    assert result["revoked"] == 1
    origin = service.get_document_origin("fake", "ext-1")
    assert origin is not None
    assert origin["revoked"] is True
    assert service.is_document_origin_revoked(origin["document_id"]) is True


def test_connector_admin_api_requires_admin_and_exposes_presence_only(
    service: Service,
) -> None:
    sentinel = "presence" + "-only-" + "marker-12345"
    connector = FakeConnector([SourceItem("ext-1", "note.txt", "rev-1", "h1", 4, 1.0)])
    connector.contents["ext-1"] = b"note"
    connector.credential = sentinel  # type: ignore[attr-defined]
    service.register_sync_connector("fake", connector, configured=True)

    admin = client_for(service)
    login(admin, "admin", "01")
    listing = admin.get("/api/admin/connectors")
    assert listing.status_code == 200, listing.text
    payload = listing.json()
    assert any(item["connector_id"] == "fake" and item["configured"] is True for item in payload)
    assert sentinel not in listing.text

    sync = admin.post(
        "/api/admin/connectors/fake/sync",
        json={"project_id": "project-a", "source": "label"},
        headers=ORIGIN,
    )
    assert sync.status_code == 200, sync.text
    body = sync.json()
    assert body["registered"] == 1
    assert body["updated"] == 0
    assert body["skipped"] == 0
    assert body["failed"] == 0
    assert sentinel not in sync.text

    with service.db() as db:
        audits = db.execute(
            "SELECT operation,target_id,outcome FROM audit WHERE operation='connector.sync'"
        ).fetchall()
    assert len(audits) == 1
    assert audits[0]["target_id"] == "fake"
    assert audits[0]["outcome"] == "ok"
    assert sentinel not in str([dict(row) for row in audits])

    user = client_for(service)
    login(user, "alice", "02")
    assert user.get("/api/admin/connectors").status_code == 403
    denied = user.post(
        "/api/admin/connectors/fake/sync",
        json={"project_id": "project-a", "source": "label"},
        headers=ORIGIN,
    )
    assert denied.status_code == 403


def test_connector_documents_follow_upload_scan_acl_and_limits(service: Service) -> None:
    connector = FakeConnector([SourceItem("ext-1", "note.txt", "rev-1", "h1", 4, 1.0)])
    connector.contents["ext-1"] = b"note"
    service.register_sync_connector("fake", connector, configured=True)
    actor = admin_actor(service)
    with service.db() as db:
        db.execute(
            "UPDATE users SET must_rotate=0,temp_expires=NULL,temp_used=0 WHERE id=?",
            (actor.id,),
        )

    result = SyncEngine(service).sync(actor, "project-a", connector, "label", connector_id="fake")
    assert result["registered"] == 1
    origin = service.get_document_origin("fake", "ext-1")
    assert origin is not None

    # Same ingestion path as manual upload: queued then quarantined by unavailable scanner.
    assert service.process_next() is True
    with service.db() as db:
        doc = db.execute(
            "SELECT status,reason,kind,owner_id,project_id FROM documents WHERE id=?",
            (origin["document_id"],),
        ).fetchone()
    assert doc is not None
    assert doc["status"] == "quarantined"
    assert "既定拒否" in doc["reason"]
    assert doc["kind"] == "personal"
    assert doc["owner_id"] == actor.id
    assert doc["project_id"] == "project-a"

    # Limits are enforced through Service.upload; fill per-owner in-flight quota.
    connector2 = FakeConnector(
        [SourceItem(f"ext-{i}", f"n{i}.txt", "rev-1", "h", 1, 1.0) for i in range(5)]
    )
    for i in range(5):
        connector2.contents[f"ext-{i}"] = b"x"
    service.register_sync_connector("fake2", connector2, configured=True)
    with service.db() as db:
        for i in range(4):
            db.execute(
                "INSERT INTO documents "
                "(id,owner_id,project_id,kind,name,content,status,grants,created) "
                "VALUES (?,?,?,?,?,?,'queued','[]',?)",
                (
                    f"pad-{i}",
                    actor.id,
                    "project-a",
                    "personal",
                    f"pad{i}.txt",
                    "x",
                    1.0,
                ),
            )
    result2 = SyncEngine(service).sync(
        actor, "project-a", connector2, "label", connector_id="fake2"
    )
    assert result2["registered"] == 0
    assert result2["failed"] >= 1
    assert service.get_document_origin("fake2", "ext-0") is None
