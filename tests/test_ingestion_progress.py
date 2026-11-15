"""Ingestion stage reporting and single-process checkpoint resume."""

import sqlite3
from pathlib import Path

import pytest
from app.main import create_app
from app.scanner import CLEAN, REJECTED, UNAVAILABLE, ScanResult
from app.service import Service
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://127.0.0.1:5174"}


class AcceptingScanner:
    def scan(self, content: str) -> ScanResult:
        return CLEAN


class FixedOutcomeScanner:
    def __init__(self, outcome: ScanResult) -> None:
        self.outcome = outcome

    def scan(self, content: str) -> ScanResult:
        return self.outcome


class CallbackScanner:
    def __init__(self, callback) -> None:  # type: ignore[no-untyped-def]
        self.callback = callback

    def scan(self, content: str) -> ScanResult:
        self.callback()
        return CLEAN


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Temporary-password-02!"},
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/api/auth/password",
        json={
            "current_password": "Temporary-password-02!",
            "new_password": "Changed-password-long-01!",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text


def prepared_service(path: Path, scanner: ScanResult) -> Service:
    svc = Service(path, scanner=FixedOutcomeScanner(scanner))
    svc.provision("admin", "Temporary-password-01!", system_admin=True)
    svc.provision("alice", "Temporary-password-02!")
    svc.create_project("org-a", "project-a", "研究プロジェクト")
    svc.assign("alice", "project-a", "researcher")
    return svc


def client_for(service: Service) -> TestClient:
    return TestClient(
        create_app(service=service, start_worker=False),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )


def upload(client: TestClient, content: str) -> dict:  # type: ignore[type-arg]
    response = client.post(
        "/api/documents",
        json={
            "project_id": "project-a",
            "name": "synthetic.txt",
            "content": content,
            "kind": "personal",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def test_upload_reports_queued_scanning_indexing_and_done_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    svc = prepared_service(tmp_path / "stages.sqlite3", CLEAN)
    seen_status: list[str] = []

    class ObservingScanner:
        def __init__(self, service: Service) -> None:
            self.service = service

        def scan(self, content: str) -> ScanResult:
            with self.service.db() as db:
                seen_status.append(db.execute("SELECT status FROM documents").fetchone()["status"])
            return CLEAN

    original_insert = Service._insert_page

    def observe_insert(
        self: Service, db: sqlite3.Connection, document: str, page: int, text: str
    ) -> None:
        seen_status.append(
            db.execute("SELECT status FROM documents WHERE id=?", (document,)).fetchone()["status"]
        )
        original_insert(db, document, page, text)

    monkeypatch.setattr(Service, "_insert_page", observe_insert)
    try:
        client = client_for(svc)
        login(client)
        created = upload(client, "first page\fsecond page")
        svc.scanner = ObservingScanner(svc)
        assert created["status"] == "queued"
        assert created["stage"] == "queued"
        assert created["failure_code"] == ""
        assert svc.process_next()
        stored = client.get(f"/api/documents/{created['id']}").json()
        assert stored["status"] == "ready"
        assert stored["stage"] == "done"
        assert "scanning" in seen_status
        assert "indexing" in seen_status
    finally:
        svc.close()


@pytest.mark.parametrize(
    ("outcome", "code"),
    [(REJECTED, "scanner_rejected"), (UNAVAILABLE, "scanner_unavailable")],
)
def test_failed_scan_reports_stage_and_short_failure_category(
    tmp_path: Path, outcome: ScanResult, code: str
) -> None:
    svc = prepared_service(tmp_path / "failed.sqlite3", outcome)
    try:
        client = client_for(svc)
        login(client)
        created = upload(client, "synthetic sample")
        assert svc.process_next()
        stored = client.get(f"/api/documents/{created['id']}").json()
        assert stored["status"] == "quarantined"
        assert stored["stage"] == "failed"
        assert stored["failure_code"] == code
        assert "安全検査" in stored["reason"]
    finally:
        svc.close()


def test_restart_resumes_from_checkpoint_without_duplicate_chunks(tmp_path: Path) -> None:
    path = tmp_path / "resume.sqlite3"
    first = prepared_service(path, CLEAN)
    client = client_for(first)
    login(client)
    created = upload(client, "A" * 1400 + "\f" + "B" * 700)
    expected_page_one = [
        "A" * 700,
        "A" * 700,
    ]
    # Simulate a process crash after page 1 committed but before page 2 began.
    # A partial page-2 row must be replaced, not duplicated.
    with first.db() as db:
        for ordinal, text in enumerate(expected_page_one, start=1):
            db.execute(
                "INSERT INTO chunks VALUES (?,?,?,?,?)",
                (f"existing-{ordinal}", created["id"], 1, ordinal, text),
            )
        db.execute(
            "INSERT INTO chunks VALUES (?,?,?,?,?)",
            ("partial", created["id"], 2, 1, "partial"),
        )
        db.execute(
            "UPDATE documents SET status='indexing',index_checkpoint=1 WHERE id=?",
            (created["id"],),
        )
    first.close()

    reopened = Service(path, scanner=FixedOutcomeScanner(CLEAN))
    try:
        reopened.recover_jobs()
        assert reopened.process_next()
        with reopened.db() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (created["id"],)).fetchone()
            assert row["status"] == "ready"
            assert row["index_checkpoint"] == 2
            chunks = db.execute(
                "SELECT id,page,ordinal,text FROM chunks WHERE document_id=? ORDER BY page,ordinal",
                (created["id"],),
            ).fetchall()
        assert [(chunk["page"], chunk["ordinal"]) for chunk in chunks] == [
            (1, 1),
            (1, 2),
            (2, 1),
        ]
        assert chunks[0]["id"] == "existing-1"
        assert chunks[1]["id"] == "existing-2"
        assert chunks[2]["text"] == "B" * 700
        # Reused page-1 chunks stay exactly once and the job does not re-run.
        assert all(chunk["id"] != "partial" for chunk in chunks)
        assert reopened.process_next() is False
    finally:
        reopened.close()


def test_permission_loss_during_scan_cancels_without_indexing(tmp_path: Path) -> None:
    svc = prepared_service(tmp_path / "revoked.sqlite3", CLEAN)
    try:
        client = client_for(svc)
        login(client)
        created = upload(client, "synthetic sample")

        def revoke() -> None:
            svc.assign("alice", "project-a", None)

        svc.scanner = CallbackScanner(revoke)
        assert svc.process_next()
        with svc.db() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (created["id"],)).fetchone()
            chunks = db.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id=?", (created["id"],)
            ).fetchone()[0]
        assert row["status"] == "cancelled"
        assert row["failure_code"] == "permission_revoked"
        assert chunks == 0
    finally:
        svc.close()


def test_permission_loss_before_resume_cancels_and_drops_committed_chunks(
    tmp_path: Path,
) -> None:
    path = tmp_path / "revoked-resume.sqlite3"
    first = prepared_service(path, CLEAN)
    client = client_for(first)
    login(client)
    created = upload(client, "first page\fsecond page")
    with first.db() as db:
        first._insert_page(db, created["id"], 1, "first page")
        db.execute(
            "UPDATE documents SET status='indexing',index_checkpoint=1 WHERE id=?",
            (created["id"],),
        )
    first.assign("alice", "project-a", None)
    first.close()

    reopened = Service(path, scanner=FixedOutcomeScanner(CLEAN))
    try:
        reopened.recover_jobs()
        assert reopened.process_next()
        with reopened.db() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (created["id"],)).fetchone()
            chunks = db.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id=?", (created["id"],)
            ).fetchone()[0]
        assert row["status"] == "cancelled"
        assert row["failure_code"] == "permission_revoked"
        assert chunks == 0
    finally:
        reopened.close()


def test_cancel_during_indexing_drops_completed_chunks(tmp_path: Path) -> None:
    svc = prepared_service(tmp_path / "cancel-indexing.sqlite3", CLEAN)
    try:
        client = client_for(svc)
        login(client)
        created = upload(client, "first page\fsecond page")
        actor = svc.authenticate(client.cookies.get("locus_session"))
        with svc.db() as db:
            svc._insert_page(db, created["id"], 1, "first page")
            db.execute(
                "UPDATE documents SET status='indexing',index_checkpoint=1 WHERE id=?",
                (created["id"],),
            )
        svc.cancel(actor, created["id"])
        with svc.db() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (created["id"],)).fetchone()
            chunks = db.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id=?", (created["id"],)
            ).fetchone()[0]
        assert row["status"] == "cancelled"
        assert row["failure_code"] == "cancelled"
        assert chunks == 0
    finally:
        svc.close()
