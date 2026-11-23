"""Synthetic tests for connector transaction scope (DATA-008 T-PH7-205).

Verifies that connector.can_read() does not hold the write transaction
across a network round-trip, and that revocation during the check is
fail-closed.
"""

import threading
import time

import pytest
from app.scanner import CLEAN, ScanResult
from app.service import Principal, Service
from fastapi import HTTPException
from test_api import client_for, login


class AcceptingScanner:
    """A scanner that always returns CLEAN, so process_next() finishes."""

    def scan(self, content: str) -> ScanResult:
        return CLEAN


SOURCE_ID = "synthetic-local"
OBJECT_ID = "synthetic-object-1"
OBJECT_ID_B = "synthetic-object-2"

CONTENT = (
    "【合成サンプル・実研究データではありません】\n"
    "成膜条件Aは処理温度180°C、処理時間30分。\n"
    "成膜条件Bは処理温度200°C、処理時間20分。\n"
)


def add_source_object(
    service: Service,
    object_id: str = OBJECT_ID,
    *,
    readable_by: dict[str, bool] | None = None,
) -> ...:
    connector = service.source_connector_for(SOURCE_ID)
    if not hasattr(connector, "objects"):
        connector.objects = {}
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
    return str(document["id"])  # type: ignore[return-value]


# -----------------------------------------------------------
# Test: slow connector does not hold the write lock
# -----------------------------------------------------------


class SlowConnector:
    """A synthetic connector that waits inside can_read to simulate network latency."""

    def __init__(self) -> None:
        self.objects: dict[str, ...] = {}
        self._called = False
        self.started = threading.Event()
        self.proceed = threading.Event()

    def add(
        self,
        object_id: str,
        *,
        revision: str = "rev-1",
        name: str = "",
        content: str = "",
        readable_by: dict[str, bool] | None = None,
    ) -> None:
        self.objects[object_id] = type(
            "_SyntheticObject",
            (),
            {
                "object_id": object_id,
                "revision": revision,
                "name": name,
                "content": content,
                "readable_by": readable_by if readable_by is not None else {},
            },
        )()

    def list_objects(self, source_id: str):
        """Return synthetic objects for this source, mimicking a real connector's list_objects."""
        result = []
        for obj in self.objects.values():
            result.append(
                type(
                    "_SyntheticObject",
                    (),
                    {
                        "object_id": obj.object_id,
                        "revision": obj.revision,
                        "name": obj.name,
                        "content": obj.content,
                    },
                )()
            )
        return result

    def permission_hash(self, source_id: str, object_id: str) -> str | None:
        """Return a permission hash for the given object (synthetic)."""
        obj = self.objects.get(object_id)
        if obj is None:
            return None
        readable = obj.readable_by if hasattr(obj, "readable_by") else {}
        if "admin" in readable and readable["admin"]:
            return "hash-allow"
        return None

    def set_readable(self, object_id: str, user_id: str, allowed: bool) -> None:
        obj = self.objects.get(object_id)
        if obj is None:
            return
        obj.readable_by = (
            {**obj.readable_by, user_id: allowed}
            if hasattr(obj, "readable_by")
            else {user_id: allowed}
        )

    def can_read(self, source_id: str, object_id: str, user_id: str) -> bool | None:
        self._called = True
        self.started.set()
        # Block until the test releases; no timeout fallback, so a regression that
        # still holds the write lock cannot slip through a timed wait.
        self.proceed.wait()
        obj = self.objects.get(object_id)
        if obj is None:
            return None
        return obj.readable_by.get(user_id)


@pytest.fixture
def slow_connector_service(tmp_path) -> Service:
    """Service with a synthetic connector for the transaction-scope test."""
    svc = Service(tmp_path / "slow.sqlite3")
    svc.scanner = AcceptingScanner()
    admin_user_id = svc.provision("admin", "Temporary-password-01!", system_admin=True)
    svc.provision("alice", "Temporary-password-02!")
    svc.create_project("org-a", "project-a", "研究プロジェクト")
    # Add admin as member of project-a so that _permissions/_role_access works.
    # Use general_user role which includes upload permission.
    with svc.db() as db:
        db.execute(
            "INSERT OR IGNORE INTO memberships (user_id,project_id,role) VALUES (?,?,?)",
            (admin_user_id, "project-a", "general_user"),
        )
        db.execute(
            "INSERT OR IGNORE INTO membership_roles (user_id,project_id,role) "
            "SELECT user_id,project_id,role FROM memberships"
        )
    svc.source_connectors[SOURCE_ID] = SlowConnector()
    return svc


def test_slow_connector_does_not_hold_write_lock(slow_connector_service: Service) -> None:
    """A slow connector that sleeps inside can_read must not hold the write lock.

    AC1 (DATA-008 / T-PH7-205): while can_read waits, another write must be able
    to proceed. We run process_next in a background thread; when the connector
    signals it is inside can_read, the main thread performs a write. If the lock
    were held, the write would block until can_read finished.
    """
    admin = client_for(slow_connector_service)
    login(admin, "admin", "01")
    actor = slow_connector_service.authenticate(admin.cookies.get("locus_session"))

    connector = add_source_object(slow_connector_service)
    document = ingest_source(slow_connector_service, actor)
    assert isinstance(connector, SlowConnector)

    result: dict[str, bool] = {}

    def run() -> None:
        result["ok"] = slow_connector_service.process_next()

    worker = threading.Thread(target=run)
    worker.start()
    assert connector.started.wait(timeout=5), "connector.can_read() was not called"

    # While the connector is blocked in can_read, a separate write must proceed.
    write_done = threading.Event()

    def do_write() -> None:
        with slow_connector_service.db() as db:
            db.execute(
                "INSERT INTO audit (id,at,actor_id,operation,target_id,outcome) "
                "VALUES ('tx-scope-probe',0,'test','probe','probe','ok')"
            )
        write_done.set()

    writer = threading.Thread(target=do_write)
    writer.start()
    try:
        assert write_done.wait(timeout=2), (
            "write blocked while connector.can_read() was in progress"
        )
    finally:
        # Always release the connector, even on failure, so the worker cannot hang.
        connector.proceed.set()
        worker.join(timeout=5)
        writer.join(timeout=5)
    assert not worker.is_alive()
    assert result.get("ok") is True

    with slow_connector_service.db() as db:
        status = str(
            db.execute("SELECT status FROM documents WHERE id=?", (document,)).fetchone()[0]
        )
    assert status == "ready", f"Document status expected 'ready', got '{status}'"
    assert connector._called is True


# -----------------------------------------------------------
# Test: binding repointed mid-read is denied (fail-closed re-check)
# -----------------------------------------------------------


def test_binding_repoint_during_read_is_denied(slow_connector_service: Service) -> None:
    """If the binding is repointed to another source object (same revision) while a
    slow connector call is in flight on the read path, the re-check must deny."""
    admin = client_for(slow_connector_service)
    login(admin, "admin", "01")
    actor = slow_connector_service.authenticate(admin.cookies.get("locus_session"))

    connector = add_source_object(slow_connector_service, readable_by={"admin": True})
    document = ingest_source(slow_connector_service, actor, kind="personal")

    result: dict[str, bool] = {}

    def run() -> None:
        try:
            slow_connector_service.document(actor, document)
            result["ok"] = True
        except HTTPException:
            result["ok"] = False

    worker = threading.Thread(target=run)
    worker.start()
    assert connector.started.wait(timeout=5), "connector.can_read() was not called"

    # Repoint the binding to another source object with the same revision while
    # can_read is in flight; the post-check must fail closed on the identity change.
    with slow_connector_service.db() as db:
        db.execute("DELETE FROM document_source_bindings WHERE document_id=?", (document,))
        db.execute(
            "INSERT INTO document_source_bindings "
            "(document_id,source_id,object_id,revision,sync_state) "
            "VALUES (?,?,?,?,'pending')",
            (document, SOURCE_ID, OBJECT_ID_B, "rev-1"),
        )
        db.execute(
            "INSERT OR REPLACE INTO source_objects "
            "(source_id,object_id,revision,permission_hash,state,observed_at) "
            "VALUES (?,?,?,?,?,?)",
            (SOURCE_ID, OBJECT_ID_B, "rev-1", "hash-allow", "ok", time.time()),
        )
    connector.proceed.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert result.get("ok") is False, (
        "read must be denied after the binding was repointed mid-check"
    )


# -----------------------------------------------------------
# Test: revocation during read is denied (fail-closed)
# -----------------------------------------------------------


def test_revocation_during_read_is_denied(slow_connector_service: Service) -> None:
    """If the source binding is revoked while a read check is in progress,
    the check should fail closed (deny access)."""
    admin = client_for(slow_connector_service)
    login(admin, "admin", "01")
    actor = slow_connector_service.authenticate(admin.cookies.get("locus_session"))

    connector = add_source_object(slow_connector_service, readable_by={"admin": True})
    document = ingest_source(slow_connector_service, actor, kind="shared")

    # Revoke the admin's read access mid-process.
    # Because _can_read and _ingestion_allowed now release the transaction
    # before calling the connector, the revocation can take effect during
    # the check, and the fail-closed behaviour applies.
    connector.set_readable(OBJECT_ID, "admin", False)
    slow_connector_service.source_cycle(SOURCE_ID)

    # The document should no longer be accessible.
    with slow_connector_service.db() as db:
        status = str(
            db.execute("SELECT status FROM documents WHERE id=?", (document,)).fetchone()[0]
        )
    # After revocation the document must be denied (fail-closed).
    # It may be 'cancelled' or 'failed' depending on timing, but must not be 'ready'.
    assert status != "ready", (
        f"Document should be denied after revocation, but status is '{status}'"
    )


# -----------------------------------------------------------
# Test: connector exception / timeout results in denial
# -----------------------------------------------------------


class RaisingConnector:
    """A synthetic connector that always raises an exception."""

    def list_objects(self, source_id: str):
        """Return a synthetic object for this source (connector unavailable otherwise)."""
        return [
            type(
                "_SyntheticObject",
                (),
                {
                    "object_id": OBJECT_ID,
                    "revision": "rev-1",
                    "name": "test.txt",
                    "content": "",
                },
            )()
        ]

    def permission_hash(self, source_id: str, object_id: str) -> str | None:
        """Return None (connector unavailable)."""
        return None

    def can_read(self, source_id: str, object_id: str, user_id: str) -> bool | None:
        raise TimeoutError("source connector unavailable")


def test_connector_exception_results_in_denial(slow_connector_service: Service) -> None:
    """If the connector raises an exception during can_read, the source
    gate must fail closed and deny access (existing behaviour preserved)."""
    admin = client_for(slow_connector_service)
    login(admin, "admin", "01")
    actor = slow_connector_service.authenticate(admin.cookies.get("locus_session"))

    # Set up a source object via add_source_object, then replace the connector
    # with one that raises during can_read.
    add_source_object(slow_connector_service)
    slow_connector_service.source_connectors[SOURCE_ID] = RaisingConnector()
    document = ingest_source(slow_connector_service, actor, kind="personal")

    with slow_connector_service.db() as db:
        status = str(
            db.execute("SELECT status FROM documents WHERE id=?", (document,)).fetchone()[0]
        )
    # Connector failure must result in denial (not 'ready').
    assert status != "ready", (
        f"Document should be denied after connector exception, but status is '{status}'"
    )
