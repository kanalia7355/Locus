"""Synthetic tests for wiring sandbox document extraction into ingestion (T-PH6-128)."""

import json
from pathlib import Path

import app.sandbox
import pytest
from app.main import create_app
from app.scanner import CLEAN, ScanResult
from app.service import Service
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://127.0.0.1:5174"}


class AcceptingScanner:
    def scan(self, content: str) -> ScanResult:
        return CLEAN


def prepared_service(path: Path) -> Service:
    svc = Service(path, scanner=AcceptingScanner())
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


def upload(client: TestClient, content: str, name: str = "synthetic.txt") -> dict[str, object]:
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


def test_extracted_body_is_stored_unwrapped_and_preserves_form_feed_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1a + ID4: Extracted body (not JSON envelope) is stored in documents.content,
    form-feed pagination produces 2 chunks, and honest subprocess sandbox metadata is recorded."""
    # Transform input inside the extractor so the test proves extraction actually ran
    # and its JSON envelope was unwrapped into plain body text.
    transforming_source = """\
import sys, json
raw = sys.stdin.read()
print(json.dumps({"body": "[extracted]" + raw, "pages": 2, "warnings": []}), flush=True)
"""
    monkeypatch.setitem(app.sandbox.EXTRACTOR_SOURCE, "plaintext", transforming_source)
    svc = prepared_service(tmp_path / "extract-ok.sqlite3")
    try:
        client = client_for(svc)
        login(client)
        created = upload(client, "1ページ目の合成本文\f2ページ目の合成本文")
        doc_id = str(created["id"])

        assert svc.process_next() is True

        stored = client.get(f"/api/documents/{doc_id}").json()
        assert stored["status"] == "ready"
        assert stored["sandbox"] == "subprocess"
        guarantees = stored["sandbox_guarantees"]
        assert isinstance(guarantees, dict)
        # Subprocess boundary must never claim strong network or memory limits (§5 invariant).
        assert guarantees.get("network") != "strong"
        assert guarantees.get("memory") != "strong"
        assert guarantees.get("cpu") != "strong"

        with svc.db() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
            assert row["content"] == "[extracted]1ページ目の合成本文\f2ページ目の合成本文"
            assert not str(row["content"]).lstrip().startswith("{")
            assert row["sandbox"] == "subprocess"
            persisted_guarantees = json.loads(row["sandbox_guarantees"])
            assert persisted_guarantees.get("network") == "unverified"
            assert persisted_guarantees.get("memory") == "unverified"

        chunks = client.get(f"/api/documents/{doc_id}/chunks").json()
        assert len(chunks) == 2
        assert chunks[0]["page"] == 1
        assert chunks[0]["text"] == "[extracted]1ページ目の合成本文"
        assert chunks[1]["page"] == 2
        assert chunks[1]["text"] == "2ページ目の合成本文"
    finally:
        svc.close()


def test_non_json_extractor_output_is_quarantined_with_user_safe_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1b: When an extractor emits 'not json', the document is quarantined (never ready)
    with user-facing Japanese wording and no internal paths, commands, stack, or extractor names."""
    not_json_source = """\
import sys
sys.stdin.read()
print("not json", flush=True)
"""
    monkeypatch.setitem(app.sandbox.EXTRACTOR_SOURCE, "plaintext", not_json_source)

    def bypass_interpret(
        outcome: app.sandbox._Outcome, sandbox: str, guarantees: dict[str, str]
    ) -> app.sandbox.SandboxResult:
        # Exercise service-side envelope parsing even when sandbox returns raw stdout.
        return app.sandbox.SandboxResult(
            success=True,
            content=outcome.stdout,
            sandbox=sandbox,
            guarantees=dict(guarantees),
            exit_code=outcome.exit_code,
            error_message=None,
        )

    monkeypatch.setattr(app.sandbox, "_interpret", bypass_interpret)
    svc = prepared_service(tmp_path / "not-json.sqlite3")
    try:
        client = client_for(svc)
        login(client)
        created = upload(client, "合成サンプル本文")
        doc_id = str(created["id"])

        assert svc.process_next() is True

        stored = client.get(f"/api/documents/{doc_id}").json()
        assert stored["status"] == "quarantined"
        assert stored["status"] != "ready"
        assert stored["failure_code"] == "extraction_failed"
        reason = str(stored["reason"])
        assert "隔離" in reason
        for forbidden in (
            "plaintext",
            "python",
            "Traceback",
            "json",
            "JSONDecodeError",
            "\\",
            "locus-extract",
            "-c",
        ):
            assert forbidden.lower() not in reason.lower()
        assert client.get(f"/api/documents/{doc_id}/chunks").status_code == 409
        with svc.db() as db:
            count = db.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id=?", (doc_id,)
            ).fetchone()[0]
            row = db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        assert count == 0
        assert row["sandbox"] == "subprocess"
    finally:
        svc.close()


def test_default_sandbox_non_json_output_is_quarantined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1b (end-to-end with unmodified sandbox._interpret): 'not json' stdout is quarantined."""
    not_json_source = """\
import sys
sys.stdin.read()
print("not json", flush=True)
"""
    monkeypatch.setitem(app.sandbox.EXTRACTOR_SOURCE, "plaintext", not_json_source)
    svc = prepared_service(tmp_path / "not-json-e2e.sqlite3")
    try:
        client = client_for(svc)
        login(client)
        created = upload(client, "合成サンプル本文")
        doc_id = str(created["id"])

        assert svc.process_next() is True

        stored = client.get(f"/api/documents/{doc_id}").json()
        assert stored["status"] == "quarantined"
        assert stored["failure_code"] == "extraction_failed"
        reason = str(stored["reason"])
        assert "隔離" in reason
        for forbidden in ("plaintext", "python", "Traceback", "\\", "locus-extract", "-c"):
            assert forbidden.lower() not in reason.lower()
    finally:
        svc.close()


@pytest.mark.parametrize(
    "payload",
    [
        '{"pages": 1}',
        '{"body": null}',
        '{"body": ""}',
        '{"body": 123}',
        '["not", "an", "object"]',
    ],
)
def test_json_without_valid_body_is_quarantined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    """AC1c: JSON output missing a valid non-empty string 'body' is quarantined, never ready."""
    bodyless_source = f"""\
import sys
sys.stdin.read()
sys.stdout.write({payload!r} + "\\n")
sys.stdout.flush()
"""
    monkeypatch.setitem(app.sandbox.EXTRACTOR_SOURCE, "plaintext", bodyless_source)

    def raw_stdout_interpret(
        outcome: app.sandbox._Outcome, sandbox: str, guarantees: dict[str, str]
    ) -> app.sandbox.SandboxResult:
        return app.sandbox.SandboxResult(
            success=True,
            content=outcome.stdout,
            sandbox=sandbox,
            guarantees=dict(guarantees),
            exit_code=outcome.exit_code,
            error_message=None,
        )

    monkeypatch.setattr(app.sandbox, "_interpret", raw_stdout_interpret)
    svc = prepared_service(tmp_path / "no-body.sqlite3")
    try:
        client = client_for(svc)
        login(client)
        created = upload(client, "合成サンプル本文")
        doc_id = str(created["id"])

        assert svc.process_next() is True

        stored = client.get(f"/api/documents/{doc_id}").json()
        assert stored["status"] == "quarantined"
        assert stored["status"] != "ready"
        assert stored["failure_code"] == "extraction_failed"
        reason = str(stored["reason"])
        assert "隔離" in reason
        for forbidden in ("plaintext", "python", "Traceback", "\\", "locus-extract", "-c"):
            assert forbidden.lower() not in reason.lower()
        with svc.db() as db:
            count = db.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id=?", (doc_id,)
            ).fetchone()[0]
        assert count == 0
    finally:
        svc.close()


def test_requeue_after_crash_between_extraction_and_scan_does_not_double_wrap_or_reprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1d: If ingestion crashes after extraction starts/completes and recover_jobs() requeues
    the document, re-running process_next() neither double-wraps content in JSON envelopes nor
    corrupts the original raw input."""
    # Use an extractor that prefixes input: if re-ingestion fed previously mutated content back
    # into the extractor (or wrapped an envelope twice), the prefix or JSON envelope would double.
    prefixing_source = """\
import sys, json
data = sys.stdin.read()
print(json.dumps({"body": "ONCE:" + data}), flush=True)
"""
    monkeypatch.setitem(app.sandbox.EXTRACTOR_SOURCE, "plaintext", prefixing_source)

    # Run process_next up to scan, interrupt before finalization so recover_jobs()
    # requeues a row that already ran extraction once.
    db_path = tmp_path / "requeue-live.sqlite3"
    first = prepared_service(db_path)
    seen_scan_inputs: list[str] = []

    class InterruptScan:
        def scan(self, content: str) -> ScanResult:
            seen_scan_inputs.append(content)
            raise BaseException("simulated process termination mid-scan")

    first.scanner = InterruptScan()  # type: ignore[assignment]
    client = client_for(first)
    login(client)
    created = upload(client, "成膜ページ1\f成膜ページ2")
    doc_id = str(created["id"])
    with pytest.raises(BaseException, match="simulated process termination"):
        first.process_next()
    first.close()

    reopened = Service(db_path, scanner=AcceptingScanner())
    try:
        reopened.recover_jobs()
        assert reopened.process_next() is True
        with reopened.db() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
            chunks = db.execute(
                "SELECT page, ordinal, text FROM chunks WHERE document_id=? ORDER BY page, ordinal",
                (doc_id,),
            ).fetchall()
        assert row["status"] == "ready"
        # Content must be extracted cleanly once from original raw input, never '{"body": ...}'
        # and never 'ONCE:ONCE:...'.
        assert row["content"] == "ONCE:成膜ページ1\f成膜ページ2"
        assert seen_scan_inputs == ["ONCE:成膜ページ1\f成膜ページ2"]
        assert [(c["page"], c["ordinal"], c["text"]) for c in chunks] == [
            (1, 1, "ONCE:成膜ページ1"),
            (2, 1, "成膜ページ2"),
        ]
    finally:
        reopened.close()
