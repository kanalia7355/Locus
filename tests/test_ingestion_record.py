"""Persisted ingestion record field observations for DATA-006 (T-PH6-131)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import app.sandbox
import pytest
from app.main import create_app
from app.sandbox import SUBPROCESS_GUARANTEES, SandboxResult
from app.scanner import CLEAN, REJECTED, UNAVAILABLE, ScanResult
from app.service import Service
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://127.0.0.1:5174"}


class FixedScanner:
    def __init__(self, result: ScanResult = CLEAN) -> None:
        self.result = result

    def scan(self, content: str) -> ScanResult:
        return self.result


def prepared_service(path: Path, scanner: ScanResult = CLEAN) -> Service:
    svc = Service(path, scanner=FixedScanner(scanner))
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


def login_alice(client: TestClient) -> None:
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


def login_admin(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Temporary-password-01!"},
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/api/auth/password",
        json={
            "current_password": "Temporary-password-01!",
            "new_password": "Changed-password-long-01!",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text


def upload_doc(client: TestClient, content: str, name: str = "synthetic.txt") -> dict[str, Any]:
    response = client.post(
        "/api/documents",
        json={
            "project_id": "project-a",
            "name": name,
            "content": content,
            "kind": "personal",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def persisted_record_fields(service: Service, doc_id: str) -> dict[str, Any]:
    """Read only the persisted ingestion metadata columns (never content)."""
    with service.db() as db:
        row = db.execute(
            "SELECT id, project_id, kind, name, status, reason, failure_code, "
            "sandbox, sandbox_guarantees, index_checkpoint FROM documents WHERE id=?",
            (doc_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def ingestion_audit_rows(service: Service, doc_id: str) -> list[dict[str, Any]]:
    with service.db() as db:
        rows = db.execute(
            "SELECT id, at, actor_id, operation, target_id, outcome "
            "FROM audit WHERE operation='document.ingest' AND target_id=? ORDER BY at",
            (doc_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def test_successful_ingestion_persists_boundary_fields_and_audit_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1 & AC2 (success): Boundary result (sandbox, honest guarantees, success)
    matches every persisted ingestion record field in SQLite, API views, and audit."""
    captured: list[SandboxResult] = []
    real_extract = app.sandbox.extract_with_sandbox

    def spy_extract(*args: Any, **kwargs: Any) -> SandboxResult:
        res = real_extract(*args, **kwargs)
        captured.append(res)
        return res

    monkeypatch.setattr("app.service.extract_with_sandbox", spy_extract)

    svc = prepared_service(tmp_path / "record-ok.sqlite3", CLEAN)
    try:
        alice = client_for(svc)
        login_alice(alice)
        created = upload_doc(alice, "1ページ目合成データ\f2ページ目合成データ")
        doc_id = str(created["id"])

        # Before process_next runs, extraction boundary fields are unpopulated defaults.
        assert created["status"] == "queued"
        assert created["stage"] == "queued"
        assert created["sandbox"] == ""
        assert created["sandbox_guarantees"] == {}
        assert created["failure_code"] == ""
        assert created["reason"] == ""

        assert svc.process_next() is True
        assert len(captured) == 1
        boundary = captured[0]
        assert boundary.success is True
        assert boundary.sandbox == "subprocess"
        assert boundary.guarantees == SUBPROCESS_GUARANTEES

        # 1. Re-open a fresh Service against the SQLite file to prove real disk persistence
        # (if an implementation returned in-memory fields without writing DB columns, this fails).
        reopened = Service(tmp_path / "record-ok.sqlite3", scanner=FixedScanner(CLEAN))
        try:
            db_record = persisted_record_fields(reopened, doc_id)
            assert db_record["id"] == doc_id
            assert db_record["project_id"] == "project-a"
            assert db_record["kind"] == "personal"
            assert db_record["name"] == "synthetic.txt"
            assert db_record["status"] == "ready"
            assert db_record["reason"] == ""
            assert db_record["failure_code"] == ""
            assert db_record["index_checkpoint"] == 2
            assert db_record["sandbox"] == boundary.sandbox
            persisted_guarantees = json.loads(db_record["sandbox_guarantees"])
            assert persisted_guarantees == boundary.guarantees
            # Design §5 honesty invariant on the persisted record:
            assert persisted_guarantees["wall_time"] == "verified"
            assert persisted_guarantees["output_bytes"] == "verified"
            assert persisted_guarantees["env_stripped"] == "verified"
            assert persisted_guarantees["network"] == "unverified"
            assert persisted_guarantees["memory"] == "unverified"
            assert persisted_guarantees["cpu"] == "unverified"
            assert persisted_guarantees["write_out_of_tmp"] == "△"

            audits = ingestion_audit_rows(reopened, doc_id)
            assert len(audits) == 1
            assert audits[0]["actor_id"] == "worker"
            assert audits[0]["operation"] == "document.ingest"
            assert audits[0]["target_id"] == doc_id
            assert audits[0]["outcome"] == "ready"
        finally:
            reopened.close()

        # 2. Observe via GET /api/documents/{id} and GET /api/documents list.
        single_view = alice.get(f"/api/documents/{doc_id}").json()
        list_view = alice.get("/api/documents", params={"project_id": "project-a"}).json()
        assert len(list_view) == 1
        for view in (single_view, list_view[0]):
            assert view["id"] == doc_id
            assert view["name"] == "synthetic.txt"
            assert view["project_id"] == "project-a"
            assert view["kind"] == "personal"
            assert view["status"] == "ready"
            assert view["stage"] == "done"
            assert view["reason"] == ""
            assert view["failure_code"] == ""
            assert view["sandbox"] == boundary.sandbox
            assert view["sandbox_guarantees"] == boundary.guarantees
            assert view["owned"] is True
            assert "content" not in view
    finally:
        svc.close()


@pytest.mark.parametrize(
    (
        "case_id",
        "extractor_key",
        "timeout",
        "output_limit",
        "expected_code",
        "expected_reason",
        "expected_guarantee_delta",
    ),
    [
        (
            "timeout",
            "infinite_loop",
            0.6,
            8 * 1024 * 1024,
            "extraction_timeout",
            "解析に時間がかかりすぎたため隔離中です。本文は検索に使いません",
            {"wall_time": "timed_out"},
        ),
        (
            "output_flood",
            "output_flood",
            10.0,
            64 * 1024,
            "extraction_output_limit",
            "解析結果が上限を超えたため隔離中です。本文は検索に使いません",
            {"wall_time": "verified", "output_bytes": "truncated"},
        ),
        (
            "abnormal_exit",
            "abnormal_exit",
            5.0,
            8 * 1024 * 1024,
            "extraction_failed",
            "本文を安全に抽出できなかったため隔離中です。本文は検索に使いません",
            {"wall_time": "verified", "output_bytes": "verified"},
        ),
        (
            "empty_body",
            "empty_body",
            5.0,
            8 * 1024 * 1024,
            "extraction_failed",
            "本文を安全に抽出できなかったため隔離中です。本文は検索に使いません",
            {"wall_time": "verified", "output_bytes": "verified"},
        ),
        (
            "invalid_json",
            "invalid_json",
            5.0,
            8 * 1024 * 1024,
            "extraction_failed",
            "本文を安全に抽出できなかったため隔離中です。本文は検索に使いません",
            {"wall_time": "verified", "output_bytes": "verified"},
        ),
    ],
    ids=["timeout", "output_flood", "abnormal_exit", "empty_body", "invalid_json"],
)
def test_boundary_failure_classifications_match_persisted_records_one_by_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    extractor_key: str,
    timeout: float,
    output_limit: int,
    expected_code: str,
    expected_reason: str,
    expected_guarantee_delta: dict[str, str],
) -> None:
    """AC1 & AC2 (failures): Each boundary failure reason classification (timeout,
    output byte limit, abnormal exit, empty body, invalid JSON) is persisted with
    matching status, failure_code, reason, sandbox, and sandbox_guarantees."""
    extra_sources = {
        "abnormal_exit": "import sys\nsys.stderr.write('synthetic crash\\n')\nsys.exit(2)\n",
        "empty_body": 'import json\nprint(json.dumps({"body": ""}), flush=True)\n',
        "invalid_json": 'print("not valid json", flush=True)\n',
    }
    if extractor_key in extra_sources:
        monkeypatch.setitem(app.sandbox.EXTRACTOR_SOURCE, "plaintext", extra_sources[extractor_key])
    else:
        monkeypatch.setitem(
            app.sandbox.EXTRACTOR_SOURCE,
            "plaintext",
            app.sandbox.EXTRACTOR_SOURCE[extractor_key],
        )

    captured: list[SandboxResult] = []
    real_extract = app.sandbox.extract_with_sandbox

    def bounded_extract(
        format_name: str,
        content: str,
        *,
        use_docker: bool = False,
        **_kwargs: Any,
    ) -> SandboxResult:
        res = real_extract(
            format_name,
            content,
            timeout=timeout,
            output_limit=output_limit,
            use_docker=use_docker,
        )
        captured.append(res)
        return res

    monkeypatch.setattr("app.service.extract_with_sandbox", bounded_extract)

    db_path = tmp_path / f"record-{case_id}.sqlite3"
    svc = prepared_service(db_path, CLEAN)
    try:
        alice = client_for(svc)
        login_alice(alice)
        created = upload_doc(alice, "合成入力データ")
        doc_id = str(created["id"])

        assert svc.process_next() is True
        assert len(captured) == 1
        boundary = captured[0]
        assert boundary.success is False
        assert boundary.sandbox == "subprocess"
        expected_guarantees = {**SUBPROCESS_GUARANTEES, **expected_guarantee_delta}
        assert boundary.guarantees == expected_guarantees

        # Re-open SQLite to confirm persistence on disk.
        reopened = Service(db_path, scanner=FixedScanner(CLEAN))
        try:
            db_record = persisted_record_fields(reopened, doc_id)
            assert db_record["status"] == "quarantined"
            assert db_record["failure_code"] == expected_code
            assert db_record["reason"] == expected_reason
            assert db_record["sandbox"] == boundary.sandbox
            assert json.loads(db_record["sandbox_guarantees"]) == boundary.guarantees
            assert db_record["index_checkpoint"] == 0

            with reopened.db() as db:
                chunk_count = db.execute(
                    "SELECT COUNT(*) FROM chunks WHERE document_id=?", (doc_id,)
                ).fetchone()[0]
            assert chunk_count == 0

            audits = ingestion_audit_rows(reopened, doc_id)
            assert len(audits) == 1
            assert audits[0]["operation"] == "document.ingest"
            assert audits[0]["target_id"] == doc_id
            assert audits[0]["outcome"] == "quarantined"
        finally:
            reopened.close()

        view = alice.get(f"/api/documents/{doc_id}").json()
        assert view["status"] == "quarantined"
        assert view["stage"] == "failed"
        assert view["failure_code"] == expected_code
        assert view["reason"] == expected_reason
        assert view["sandbox"] == boundary.sandbox
        assert view["sandbox_guarantees"] == boundary.guarantees
    finally:
        svc.close()


@pytest.mark.parametrize(
    ("scan_outcome", "expected_code", "expected_reason"),
    [
        (
            REJECTED,
            "scanner_rejected",
            "安全検査を通過していないため隔離中です。本文は検索に使いません",
        ),
        (
            UNAVAILABLE,
            "scanner_unavailable",
            "安全検査を実行できないため隔離中です（既定拒否）。本文は検索に使いません",
        ),
    ],
    ids=["scanner_rejected", "scanner_unavailable"],
)
def test_scanner_quarantine_still_persists_extraction_boundary_fields(
    tmp_path: Path,
    scan_outcome: ScanResult,
    expected_code: str,
    expected_reason: str,
) -> None:
    """AC2: When extraction succeeds in subprocess sandbox and the scanner rejects or
    is unavailable, the persisted record still preserves both the scanner failure
    classification and the extraction boundary's sandbox/guarantees."""
    db_path = tmp_path / f"scan-{expected_code}.sqlite3"
    svc = prepared_service(db_path, scan_outcome)
    try:
        alice = client_for(svc)
        login_alice(alice)
        created = upload_doc(alice, "合成スキャン対象データ")
        doc_id = str(created["id"])

        assert svc.process_next() is True

        reopened = Service(db_path, scanner=FixedScanner(scan_outcome))
        try:
            db_record = persisted_record_fields(reopened, doc_id)
            assert db_record["status"] == "quarantined"
            assert db_record["failure_code"] == expected_code
            assert db_record["reason"] == expected_reason
            assert db_record["sandbox"] == "subprocess"
            assert json.loads(db_record["sandbox_guarantees"]) == SUBPROCESS_GUARANTEES

            audits = ingestion_audit_rows(reopened, doc_id)
            assert len(audits) == 1
            assert audits[0]["outcome"] == "quarantined"
        finally:
            reopened.close()

        view = alice.get(f"/api/documents/{doc_id}").json()
        assert view["status"] == "quarantined"
        assert view["stage"] == "failed"
        assert view["failure_code"] == expected_code
        assert view["reason"] == expected_reason
        assert view["sandbox"] == "subprocess"
        assert view["sandbox_guarantees"] == SUBPROCESS_GUARANTEES
    finally:
        svc.close()


def test_secrets_body_and_key_values_never_appear_in_ingestion_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3: Presence-only / metadata-only rule — secret values, document body text,
    and key values (planted parent env key/value, API key fixture, user credentials)
    never appear in persisted ingestion record fields, API metadata responses,
    storage status, or audit logs across both ready and quarantined ingestions."""
    planted_env_key = "EXTRACTED_VAR"
    planted_api_key = "sk-synthetic-01-not-a-real-key"
    ready_body = f"機密研究ノート本文マーカー9912 {planted_api_key}"
    quarantined_body = "隔離対象本文マーカー8841 sk-synthetic-02-not-a-real-key"

    monkeypatch.setenv(planted_env_key, planted_api_key)

    db_path = tmp_path / "redaction.sqlite3"
    svc = prepared_service(db_path, CLEAN)
    try:
        alice = client_for(svc)
        admin = client_for(svc)
        login_alice(alice)
        login_admin(admin)

        # 1) Normal ingestion using env_reader-aware or plaintext extractor:
        # First run with plaintext on body containing body marker + synthetic key.
        ready_doc = upload_doc(alice, ready_body, name="ready-note.txt")
        assert svc.process_next() is True

        # 2) Run with env_reader extractor while parent env holds planted_api_key.
        monkeypatch.setitem(
            app.sandbox.EXTRACTOR_SOURCE,
            "plaintext",
            app.sandbox.EXTRACTOR_SOURCE["env_reader"],
        )
        env_doc = upload_doc(alice, "入力プレースホルダ", name="env-check.txt")
        assert svc.process_next() is True

        # 3) Failing extractor emitting body/key on stderr and non-zero exit -> quarantined.
        failing_leaky_source = """\
import sys, os
raw = sys.stdin.read()
sys.stderr.write("ERR:" + raw + ":" + os.environ.get("EXTRACTED_VAR", "") + "\\n")
sys.exit(3)
"""
        monkeypatch.setitem(app.sandbox.EXTRACTOR_SOURCE, "plaintext", failing_leaky_source)
        failed_doc = upload_doc(alice, quarantined_body, name="failed-note.txt")
        assert svc.process_next() is True

        forbidden_values = (
            planted_env_key,
            planted_api_key,
            "sk-synthetic-02-not-a-real-key",
            "機密研究ノート本文マーカー9912",
            "隔離対象本文マーカー8841",
            "入力プレースホルダ",
            "Temporary-password-01!",
            "Temporary-password-02!",
            "Changed-password-long-01!",
            alice.cookies.get("locus_session") or "",
            admin.cookies.get("locus_session") or "",
        )
        assert all(forbidden_values)
        assert os.environ.get(planted_env_key) == planted_api_key

        # Inspect persisted ingestion record metadata columns for all three documents,
        # plus all API document metadata endpoints, admin storage status, and audit logs.
        for doc_id in (ready_doc["id"], env_doc["id"], failed_doc["id"]):
            record = persisted_record_fields(svc, str(doc_id))
            serialized_record = json.dumps(record, ensure_ascii=False)
            single_resp = alice.get(f"/api/documents/{doc_id}")
            assert single_resp.status_code == 200
            single_json = single_resp.text
            assert "content" not in single_resp.json()

            for secret_or_body in forbidden_values:
                assert secret_or_body not in serialized_record
                assert secret_or_body not in single_json

        docs_list_text = alice.get("/api/documents", params={"project_id": "project-a"}).text
        audit_text = admin.get("/api/admin/audit").text
        storage_text = admin.get("/api/admin/storage").text
        with svc.db() as db:
            raw_audit_db = json.dumps(
                [dict(r) for r in db.execute("SELECT * FROM audit").fetchall()],
                ensure_ascii=False,
            )

        for secret_or_body in forbidden_values:
            assert secret_or_body not in docs_list_text
            assert secret_or_body not in audit_text
            assert secret_or_body not in storage_text
            assert secret_or_body not in raw_audit_db
    finally:
        svc.close()


def test_omitting_record_persistence_is_caught_by_record_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1 guard: Explicitly verify that queued defaults are empty before ingestion,
    that normal ingestion persists the boundary fields, and that if an implementation
    executes the boundary without persisting `sandbox`/`sandbox_guarantees` or the
    `document.ingest` audit row, the record inspection assertions fail."""
    db_path = tmp_path / "guard.sqlite3"
    svc = prepared_service(db_path, CLEAN)
    try:
        alice = client_for(svc)
        login_alice(alice)
        created = upload_doc(alice, "永続化検証サンプル")
        doc_id = str(created["id"])

        # Queued row before ingestion has empty defaults — distinct from persisted state.
        before = persisted_record_fields(svc, doc_id)
        assert before["sandbox"] == ""
        assert json.loads(before["sandbox_guarantees"]) == {}
        assert ingestion_audit_rows(svc, doc_id) == []

        assert svc.process_next() is True

        after = persisted_record_fields(svc, doc_id)
        assert after["sandbox"] == "subprocess"
        assert json.loads(after["sandbox_guarantees"]) == SUBPROCESS_GUARANTEES
        assert len(ingestion_audit_rows(svc, doc_id)) == 1

        # Simulate a regression that runs extraction and marks the document ready
        # without persisting boundary fields or the ingestion audit row.
        regressed = upload_doc(alice, "回帰検証サンプル", name="regressed.txt")
        regressed_id = str(regressed["id"])

        def non_persisting_process_next() -> bool:
            with svc.db() as db:
                db.execute("UPDATE documents SET status='ready' WHERE id=?", (regressed_id,))
            return True

        monkeypatch.setattr(svc, "process_next", non_persisting_process_next)
        assert svc.process_next() is True

        reopened = Service(db_path, scanner=FixedScanner(CLEAN))
        try:
            broken_record = persisted_record_fields(reopened, regressed_id)
            with pytest.raises(AssertionError):
                assert broken_record["sandbox"] == "subprocess"
                assert json.loads(broken_record["sandbox_guarantees"]) == SUBPROCESS_GUARANTEES
                assert len(ingestion_audit_rows(reopened, regressed_id)) == 1
        finally:
            reopened.close()
    finally:
        svc.close()
