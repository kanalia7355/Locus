"""Offline tests for PostgreSQL engine, dialect translation, DSN checks, and migration."""

from __future__ import annotations

import builtins
import copy
import importlib
import secrets
import sys
from pathlib import Path
from typing import Any

import pytest
from app.main import create_app
from app.service import Principal, Service
from app.storage import (
    SERVICE_SNAPSHOT_TABLES,
    SqliteEngine,
    StorageError,
    StorageIntegrityError,
    export_snapshot,
    import_snapshot,
    select_storage_engine,
    validate_snapshot,
    verify_snapshot,
)
from app.storage_postgres import (
    MappingRow,
    PostgresEngine,
    normalize_postgres_error,
    redact_database_url,
    translate_column_types,
    translate_placeholders,
    translate_schema_script,
    translate_sql,
    translate_trigger,
    validate_database_url,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _extract_service_schema_script() -> str:
    source = (REPO_ROOT / "backend" / "app" / "service.py").read_text(encoding="utf-8")
    marker = 'self._engine.apply_schema("""'
    start = source.index(marker) + len(marker)
    end = source.index('""")', start)
    return source[start:end]


# --- AC1a: Lazy psycopg import ----------------------------------------------


def test_storage_postgres_imports_without_psycopg_and_defers_driver_to_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Module import and engine instantiation succeed without psycopg; only connect() imports it."""
    real_import = builtins.__import__
    import_attempts: list[str] = []

    def blocking_import(
        name: str,
        globals_: Any = None,
        locals_: Any = None,
        fromlist: Any = (),
        level: int = 0,
    ) -> Any:
        if name == "psycopg" or name.startswith("psycopg."):
            import_attempts.append(name)
            raise ModuleNotFoundError("No module named 'psycopg'")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocking_import)
    monkeypatch.delitem(sys.modules, "psycopg", raising=False)
    monkeypatch.delitem(sys.modules, "app.storage_postgres", raising=False)

    reloaded = importlib.import_module("app.storage_postgres")
    assert import_attempts == [], "Importing app.storage_postgres must not import psycopg"

    engine = reloaded.PostgresEngine("postgresql://127.0.0.1:5432/locus_dev")
    assert import_attempts == [], "Instantiating PostgresEngine must not import psycopg"

    with pytest.raises(StorageError, match="psycopg"):
        engine.connect()
    assert import_attempts == ["psycopg"]


# --- AC1b & AC1c: Pure SQL dialect translation -------------------------------


def test_translate_real_service_queries_and_triggers() -> None:
    """Pure dialect functions translate real SQL statements from backend/app/service.py."""
    # 1. INSERT INTO audit ... (service.py _audit)
    audit_sql = "INSERT INTO audit VALUES (?,?,?,?,?,?)"
    assert translate_sql(audit_sql) == "INSERT INTO audit VALUES (%s,%s,%s,%s,%s,%s)"

    # 2. INSERT OR IGNORE INTO membership_roles ... (service.py startup + role holdings)
    mr_values_sql = (
        "INSERT OR IGNORE INTO membership_roles (user_id,project_id,role) VALUES (?,?,?)"
    )
    assert (
        translate_sql(mr_values_sql)
        == "INSERT INTO membership_roles (user_id,project_id,role) VALUES (%s,%s,%s) "
        "ON CONFLICT DO NOTHING"
    )
    mr_select_sql = (
        "INSERT OR IGNORE INTO membership_roles (user_id,project_id,role) "
        "SELECT user_id,project_id,role FROM memberships"
    )
    assert (
        translate_sql(mr_select_sql) == "INSERT INTO membership_roles (user_id,project_id,role) "
        "SELECT user_id,project_id,role FROM memberships ON CONFLICT DO NOTHING"
    )

    # 3. Real membership_role sync triggers + membership_role_delete trigger from service.py
    trigger_insert = """
    CREATE TRIGGER IF NOT EXISTS membership_role_insert AFTER INSERT ON memberships
    BEGIN
        INSERT OR IGNORE INTO membership_roles (user_id,project_id,role)
        VALUES (NEW.user_id,NEW.project_id,NEW.role);
    END;
    """
    pg_trg_insert = translate_trigger(trigger_insert)
    assert "CREATE OR REPLACE FUNCTION locus_trg_fn_membership_role_insert()" in pg_trg_insert
    assert "RETURNS TRIGGER LANGUAGE plpgsql" in pg_trg_insert
    assert (
        "INSERT INTO membership_roles (user_id,project_id,role)\n"
        "        VALUES (NEW.user_id,NEW.project_id,NEW.role) ON CONFLICT DO NOTHING;"
        in pg_trg_insert
    )
    assert (
        "CREATE TRIGGER membership_role_insert AFTER INSERT ON memberships "
        "FOR EACH ROW EXECUTE FUNCTION locus_trg_fn_membership_role_insert();" in pg_trg_insert
    )

    trigger_update = """
    CREATE TRIGGER IF NOT EXISTS membership_role_update AFTER UPDATE OF role ON memberships
    BEGIN
        DELETE FROM membership_roles
        WHERE user_id=NEW.user_id AND project_id=NEW.project_id AND role<>NEW.role;
        INSERT OR IGNORE INTO membership_roles (user_id,project_id,role)
        VALUES (NEW.user_id,NEW.project_id,NEW.role);
    END;
    """
    pg_trg_update = translate_trigger(trigger_update)
    assert "CREATE OR REPLACE FUNCTION locus_trg_fn_membership_role_update()" in pg_trg_update
    assert "DELETE FROM membership_roles" in pg_trg_update
    assert "ON CONFLICT DO NOTHING;" in pg_trg_update
    assert (
        "CREATE TRIGGER membership_role_update AFTER UPDATE OF role ON memberships "
        "FOR EACH ROW EXECUTE FUNCTION locus_trg_fn_membership_role_update();" in pg_trg_update
    )

    trigger_delete = """
    CREATE TRIGGER IF NOT EXISTS membership_role_delete AFTER DELETE ON memberships
    BEGIN
        DELETE FROM membership_roles WHERE user_id=OLD.user_id
            AND project_id=OLD.project_id;
    END;
    """
    pg_trg_delete = translate_trigger(trigger_delete)
    assert "CREATE OR REPLACE FUNCTION locus_trg_fn_membership_role_delete()" in pg_trg_delete
    assert "DELETE FROM membership_roles WHERE user_id=OLD.user_id" in pg_trg_delete
    assert (
        "CREATE TRIGGER membership_role_delete AFTER DELETE ON memberships "
        "FOR EACH ROW EXECUTE FUNCTION locus_trg_fn_membership_role_delete();" in pg_trg_delete
    )

    # 4. SELECT ... WHERE project_id=? AND status='ready' AND id<>? (service.py related())
    related_sql = (
        "SELECT id,owner_id,project_id,kind,name,status,reason,conversation_id,"
        "grants,created,failure_code,sandbox,sandbox_guarantees "
        "FROM documents WHERE project_id=? AND status='ready' AND id<>? "
        "ORDER BY id"
    )
    assert translate_sql(related_sql) == (
        "SELECT id,owner_id,project_id,kind,name,status,reason,conversation_id,"
        "grants,created,failure_code,sandbox,sandbox_guarantees "
        "FROM documents WHERE project_id=%s AND status='ready' AND id<>%s "
        "ORDER BY id"
    )


def test_translate_column_types_and_transaction_and_pragma() -> None:
    """REAL -> DOUBLE PRECISION (not timestamptz); BEGIN -> SERIALIZABLE; PRAGMA -> columns."""
    ddl = (
        "CREATE TABLE IF NOT EXISTS sessions ("
        "token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, "
        "expires REAL NOT NULL, last_seen REAL NOT NULL, rotation_only INTEGER NOT NULL)"
    )
    translated_ddl = translate_column_types(ddl)
    assert "DOUBLE PRECISION NOT NULL" in translated_ddl
    assert "INTEGER NOT NULL" in translated_ddl
    assert "TEXT PRIMARY KEY" in translated_ddl
    assert "timestamptz" not in translated_ddl.lower()
    assert "timestamp" not in translated_ddl.lower()

    assert translate_sql("BEGIN IMMEDIATE") == "BEGIN ISOLATION LEVEL SERIALIZABLE"

    pragma_translated = translate_sql("PRAGMA table_info(documents)")
    assert "information_schema.columns" in pragma_translated
    assert "table_name = 'documents'" in pragma_translated


def test_translate_entire_service_schema_script_offline() -> None:
    """Every DDL and trigger in Service.__init__ translates cleanly without timestamptz."""
    schema_script = _extract_service_schema_script()
    statements = translate_schema_script(schema_script)
    joined = "\n".join(statements)
    assert len(statements) >= 30
    assert "DOUBLE PRECISION" in joined
    assert "timestamptz" not in joined.lower()
    assert "RAISE(ABORT" not in joined
    assert "INSERT OR IGNORE" not in joined
    assert "randomblob" not in joined
    assert "julianday" not in joined
    assert "CREATE OR REPLACE FUNCTION audit_sha256(" in joined
    assert "rtrim(rtrim(txt, '0'), '.')" in joined


def test_question_marks_inside_string_literals_are_preserved() -> None:
    """Placeholders inside single-quoted literals (including Japanese) stay untouched."""
    sql = (
        "SELECT id, '本当に削除しますか? (y/n)' AS prompt, 'it''s ok? yes?' AS note "
        "FROM documents WHERE project_id=? AND reason<>'why? unknown' AND id<>?"
    )
    translated = translate_placeholders(sql)
    assert translated == (
        "SELECT id, '本当に削除しますか? (y/n)' AS prompt, 'it''s ok? yes?' AS note "
        "FROM documents WHERE project_id=%s AND reason<>'why? unknown' AND id<>%s"
    )


def test_serialization_failure_is_raised_as_storage_error_without_retry() -> None:
    """Serialization failures normalize to StorageError and are never silently retried."""

    class FakeSerializationFailure(Exception):
        sqlstate = "40001"

    err = normalize_postgres_error(FakeSerializationFailure("could not serialize access"))
    assert isinstance(err, StorageError)
    assert not isinstance(err, StorageIntegrityError)
    assert "serialization_failure" in str(err)

    calls = 0

    class FakeCursor:
        description = None
        rowcount = 0

        def execute(self, sql: str, params: Any = None) -> None:
            nonlocal calls
            if "INSERT INTO audit" in sql:
                calls += 1
                raise FakeSerializationFailure("concurrent update")

    class FakeRawConn:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def rollback(self) -> None:
            pass

        def commit(self) -> None:
            pass

        def close(self) -> None:
            pass

    engine = PostgresEngine("postgresql://127.0.0.1:5432/locus")
    from app.storage_postgres import _PostgresConnection

    engine._conn = _PostgresConnection(FakeRawConn())
    with pytest.raises(StorageError, match="serialization_failure"):
        with engine.transaction(), engine.connection() as conn:
            conn.execute("INSERT INTO audit VALUES (?,?,?,?,?,?)", ("1", 1.0, "u", "op", "t", "ok"))
    assert calls == 1, "Serialization failure must not be retried automatically"


# --- AC1d & AC1e: DSN validation, secret redaction, default SQLite -----------


@pytest.mark.parametrize(
    ("url_template", "needs_secret"),
    [
        ("", False),
        ("   ", False),
        ("sqlite:///tmp/locus.sqlite3", False),
        ("sqlite:///:memory:", False),
        ("mysql://dbuser:{secret}@127.0.0.1:3306/locus", True),
        ("http://dbuser:{secret}@127.0.0.1:8000/locus", True),
        ("postgresql://dbuser:{secret}@8.8.8.8:5432/locus", True),
        ("postgresql://dbuser:{secret}@db.public-cloud.example.com:5432/locus", True),
        ("postgresql://dbuser:{secret}@0.0.0.0:5432/locus", True),
        ("postgresql://dbuser:{secret}@127.0.0.1:5432/", True),
    ],
)
def test_validate_database_url_rejects_invalid_and_redacts_password(
    url_template: str, needs_secret: bool
) -> None:
    per_run_token = f"sentinel-{secrets.token_hex(8)}" if needs_secret else ""
    bad_url = url_template.format(secret=per_run_token) if needs_secret else url_template
    with pytest.raises(ValueError) as exc_info:
        validate_database_url(bad_url)
    message = str(exc_info.value)
    if per_run_token:
        assert per_run_token not in message
    redacted = redact_database_url(bad_url)
    if per_run_token:
        assert per_run_token not in redacted


@pytest.mark.parametrize(
    "valid_url",
    [
        "postgresql://127.0.0.1:5432/locus",
        "postgres://localhost:5432/locus",
        "postgresql://[::1]:5432/locus",
        "postgresql://locus_app@10.20.30.40:5432/locus_prod",
        "postgresql://locus_app@172.16.5.10:5432/locus_prod",
        "postgresql://locus_app@192.168.10.25:5432/locus_prod",
        "postgresql://locus_app@postgres.internal:5432/locus_prod",
        "postgresql://locus_app@db-primary:5432/locus_prod",
    ],
)
def test_validate_database_url_accepts_loopback_and_private_lan_hosts(valid_url: str) -> None:
    assert validate_database_url(valid_url) == valid_url


def test_create_app_rejects_invalid_database_url_without_leaking_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    per_run_token = f"sentinel-{secrets.token_hex(8)}"
    monkeypatch.setenv(
        "LOCUS_DATABASE_URL",
        "postgresql://admin:" + per_run_token + "@203.0.113.10:5432/locus",
    )
    with pytest.raises(RuntimeError) as exc_info:
        create_app(start_worker=False)
    assert per_run_token not in str(exc_info.value)


def test_service_selects_sqlite_when_database_url_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOCUS_DATABASE_URL", raising=False)
    selected = select_storage_engine(tmp_path / "selected.sqlite3")
    try:
        assert isinstance(selected, SqliteEngine)
    finally:
        selected.close()

    svc = Service(tmp_path / "default.sqlite3")
    try:
        assert isinstance(svc._engine, SqliteEngine)
        admin_id = svc.provision("admin", "Temporary-password-01!", system_admin=True)
        status = svc.storage_status(Principal(admin_id, "admin", True, False))
        assert status["backend"] == "sqlite"
    finally:
        svc.close()


def test_select_storage_engine_returns_postgres_when_database_url_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCUS_DATABASE_URL", "postgresql://127.0.0.1:5432/locus")
    selected = select_storage_engine(tmp_path / "unused.sqlite3")
    assert isinstance(selected, PostgresEngine)
    assert not (tmp_path / "unused.sqlite3").exists()


def test_mapping_row_supports_dict_and_positional_lookup() -> None:
    row = MappingRow(("id", "count"), ("doc-1", 3))
    assert row["id"] == "doc-1"
    assert row[0] == "doc-1"
    assert row[1] == 3
    assert dict(row) == {"id": "doc-1", "count": 3}


# --- AC3: Offline migration round-trip & missing-table failure ---------------


def test_snapshot_roundtrip_sqlite_to_sqlite_preserves_all_tables_and_rows(
    service: Service, tmp_path: Path
) -> None:
    """Seed documents, chunks, conversations, messages, grants, and audit rows, then round-trip."""
    # Seed shared & personal synthetic documents + chunks via Service.seed_synthetic
    shared_doc_id = service.seed_synthetic("alice", "project-a", "shared")
    personal_doc_id = service.seed_synthetic("alice", "project-a", "personal")

    temp_token, _ = service.login("alice", "Temporary-password-02!", "127.0.0.1", "pytest")
    rot_actor = service.authenticate(temp_token, allow_rotation=True)
    session_token = service.rotate(
        rot_actor, "Temporary-password-02!", "Changed-password-long-01!", session_token=temp_token
    )
    alice = service.authenticate(session_token)

    # Create a conversation, upload an attachment, send a message (creates messages + audit rows)
    conv = service.new_conversation(alice, "project-a")
    service.upload(
        alice,
        "project-a",
        "notes.txt",
        "成膜条件Aの追加メモ",
        "attachment",
        conv["id"],
    )
    msg = service.send(
        alice,
        conv["id"],
        "成膜条件Aの処理温度は?",
        "all",
        [],
        generate=lambda _q, _c: ("処理温度は180°Cです。", "synthetic-local"),
        token=session_token,
    )
    assert msg is not None

    snapshot = export_snapshot(service._engine)
    assert set(SERVICE_SNAPSHOT_TABLES).issubset(snapshot["tables"].keys())
    assert snapshot["counts"]["documents"] >= 3
    assert snapshot["counts"]["chunks"] >= 2
    assert snapshot["counts"]["conversations"] == 1
    assert snapshot["counts"]["messages"] == 1
    assert snapshot["counts"]["generated_answers"] == 1
    assert snapshot["counts"]["audit"] > 0
    assert snapshot["counts"]["audit_chain"] == snapshot["counts"]["audit"]

    # Prepare an empty initialized target Service (fresh schema, zero user data)
    target_path = tmp_path / "migrated.sqlite3"
    target_service = Service(target_path)
    try:
        verification = import_snapshot(target_service._engine, snapshot)
        assert verification["ok"] is True
        assert verification["overall_checksum"] == snapshot["overall_checksum"]

        re_exported = export_snapshot(target_service._engine)
        assert re_exported["counts"] == snapshot["counts"]
        assert re_exported["checksums"] == snapshot["checksums"]
        assert re_exported["tables"] == snapshot["tables"]

        # Confirm JSON grants, chunk text, conversation messages, and audit chain integrity survive
        shared_doc = target_service.document(alice, shared_doc_id)
        assert shared_doc["kind"] == "shared"
        personal_doc = target_service.document(alice, personal_doc_id)
        assert personal_doc["kind"] == "personal"
        chunks = target_service.chunks(alice, shared_doc_id)
        assert any("成膜条件A" in c["text"] for c in chunks)

        loaded_conv = target_service.conversation(alice, conv["id"])
        assert len(loaded_conv["messages"]) == 1
        assert loaded_conv["messages"][0]["answer"] == "処理温度は180°Cです。"

        admin_row = target_service.conn.execute(
            "SELECT id, username FROM users WHERE username='admin'"
        ).fetchone()
        admin = Principal(admin_row["id"], admin_row["username"], True, False)
        chain_check = target_service.verify_audit_chain(admin)
        assert chain_check["ok"] is True
        assert chain_check["checked"] == snapshot["counts"]["audit"]
    finally:
        target_service.close()


def test_snapshot_validation_fails_when_table_is_dropped_or_tampered(
    service: Service, tmp_path: Path
) -> None:
    """Dropping one required table (or tampering with a row/count) fails validation and import."""
    service.seed_synthetic("alice", "project-a", "shared")
    snapshot = export_snapshot(service._engine)

    # 1. Intentionally drop one table ("chunks") from the snapshot
    missing_chunks = copy.deepcopy(snapshot)
    missing_chunks["tables"].pop("chunks")
    missing_chunks["counts"].pop("chunks", None)
    missing_chunks["checksums"].pop("chunks", None)

    with pytest.raises(StorageError, match="chunks"):
        validate_snapshot(missing_chunks)

    target_service = Service(tmp_path / "reject_missing.sqlite3")
    try:
        with pytest.raises(StorageError, match="chunks"):
            import_snapshot(target_service._engine, missing_chunks)
        with pytest.raises(StorageError, match="chunks"):
            verify_snapshot(target_service._engine, missing_chunks)
    finally:
        target_service.close()

    # 2. Tamper with a row body without updating checksum -> fails checksum check
    tampered = copy.deepcopy(snapshot)
    tampered["tables"]["documents"][0]["content"] = "tampered content"
    with pytest.raises(StorageError, match="checksum"):
        validate_snapshot(tampered)


def test_snapshot_roundtrip_preserves_audit_chain_when_timestamps_tie(
    service: Service, tmp_path: Path
) -> None:
    """Audit rows with identical timestamps must export/import in exact audit_chain.seq order."""
    tied_at = 1_700_000_000.0
    with service.db() as db:
        db.execute(
            "INSERT INTO audit VALUES (?,?,?,?,?,?)",
            ("zzzz-first-seq", tied_at, "admin", "test.first", "t1", "ok"),
        )
        db.execute(
            "INSERT INTO audit VALUES (?,?,?,?,?,?)",
            ("aaaa-second-seq", tied_at, "admin", "test.second", "t2", "ok"),
        )

    snapshot = export_snapshot(service._engine)
    target_service = Service(tmp_path / "tied_audit_migrated.sqlite3")
    try:
        result = import_snapshot(target_service._engine, snapshot)
        assert result["ok"] is True
        admin_row = target_service.conn.execute(
            "SELECT id, username FROM users WHERE username='admin'"
        ).fetchone()
        admin = Principal(admin_row["id"], admin_row["username"], True, False)
        assert target_service.verify_audit_chain(admin)["ok"] is True
    finally:
        target_service.close()
