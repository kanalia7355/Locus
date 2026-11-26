"""Storage engine seam verification for the T-PH7-211 storage abstraction.

Covers the acceptance criteria of the storage seam task:

- AC1: ``backend/app/service.py`` / ``main.py`` / ``cli.py`` never touch the
  ``sqlite3`` module; only ``backend/app/storage.py`` owns it.
- AC3: the storage seam is actually exercised.  A ``SqliteEngine`` subclass
  with exactly one broken behaviour must make a representative acceptance fail,
  while the default engine must let the same acceptance pass.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from app.service import Principal, Service
from app.storage import SqliteEngine, StorageConnection, StorageEngine, StorageIntegrityError
from app.storage_postgres import PostgresEngine
from fastapi import HTTPException

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = ("backend/app/service.py", "backend/app/main.py", "backend/app/cli.py")
DOCUMENT_NAME = "carol-research.txt"
DOCUMENT_CONTENT = "synthetic pre-scan content"


def _source(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _sqlite3_module_references(source: str) -> list[str]:
    """Collect every ``sqlite3`` module reference in *source*.

    AST based, so comments and string literals (for example the
    ``storage/locus.sqlite3`` database filename) are not mistaken for module
    usage, while ``import sqlite3``, ``from sqlite3 ...`` and ``sqlite3.*``
    attribute chains are all caught.
    """
    found: list[str] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sqlite3":
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "sqlite3":
                found.append(str(node.module))
        elif isinstance(node, ast.Name) and node.id == "sqlite3":
            found.append(node.id)
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "sqlite3"
        ):
            found.append("sqlite3")
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(ast.parse(source))
    return found


def test_no_sqlite3_outside_storage_module() -> None:
    """AC1: ``service.py`` / ``main.py`` / ``cli.py`` contain zero ``sqlite3`` occurrences."""
    for relative_path in SOURCE_FILES:
        source = _source(relative_path)
        references = _sqlite3_module_references(source)
        assert not references, (
            f"{relative_path} must not reference the sqlite3 module: {references}"
        )
        # Also reject raw substring re-introductions (e.g. __import__("sqlite3")),
        # discounting only the default database filename ``locus.sqlite3``.
        cleaned = source.replace("locus.sqlite3", "")
        assert "sqlite3" not in cleaned, (
            f"{relative_path} must not contain 'sqlite3' outside the default filename"
        )


def _open_contract_engine(engine_kind: str, tmp_path: Path) -> StorageEngine:
    """Open a StorageEngine for the parameterized contract suite.

    Uses ``pytest.skip()`` inside the test body (no custom pytest marker) ONLY when
    ``engine_kind == 'postgres'`` and ``LOCUS_DATABASE_URL`` is unset.  When
    ``LOCUS_DATABASE_URL`` is set, skipping is forbidden: driver/connection errors
    raise immediately and fail the test.
    """
    if engine_kind == "sqlite":
        return SqliteEngine(tmp_path / "contract.sqlite3")
    if engine_kind == "postgres":
        if "LOCUS_DATABASE_URL" not in os.environ:
            pytest.skip("LOCUS_DATABASE_URL is not set; skipping live PostgreSQL contract run")
        dsn = os.environ["LOCUS_DATABASE_URL"]
        engine = PostgresEngine(dsn, connect_immediately=True)
        return engine
    raise ValueError(f"Unknown engine_kind: {engine_kind}")


@pytest.mark.parametrize("engine_kind", ["sqlite", "postgres"])
def test_storage_error_preserves_cause(engine_kind: str, tmp_path: Path) -> None:
    """StorageEngine wraps driver errors in StorageError/StorageIntegrityError with __cause__."""
    engine = _open_contract_engine(engine_kind, tmp_path)
    table_name = f"items_{os.getpid()}"
    try:
        engine.apply_schema(f"CREATE TABLE IF NOT EXISTS {table_name} (id TEXT PRIMARY KEY)")
        with engine.transaction(), engine.connection() as conn:
            conn.execute(f"DELETE FROM {table_name}")  # noqa: S608
            conn.execute(f"INSERT INTO {table_name} VALUES (?)", ("dup",))  # noqa: S608
        with pytest.raises(StorageIntegrityError) as exc_info:
            with engine.transaction(), engine.connection() as conn:
                conn.execute(f"INSERT INTO {table_name} VALUES (?)", ("dup",))  # noqa: S608
        assert exc_info.value.__cause__ is not None
    finally:
        engine.close()


class _OkCursor:
    """Cursor that reports a successful write without touching a real database."""

    rowcount = 0

    def fetchone(self) -> Any:
        return None

    def fetchall(self) -> list[Any]:
        return []

    def fetchmany(self, size: int | None = None) -> list[Any]:
        return []

    @property
    def lastrowid(self) -> int | None:
        return None

    @property
    def description(self) -> Any:
        return None

    def __iter__(self) -> Iterator[Any]:
        return iter([])

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)


class _OkConnection:
    """Connection that swallows integrity violations instead of translating them."""

    def __init__(self, wrapped: StorageConnection) -> None:
        self._conn = wrapped

    @property
    def in_transaction(self) -> bool:
        return self._conn.in_transaction

    @property
    def row_factory(self) -> Any:
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        self._conn.row_factory = value

    def execute(self, sql: str, params: Any = ()) -> Any:
        try:
            return self._conn.execute(sql, params)
        except StorageIntegrityError:
            # The fake swallows StorageIntegrityError and returns success instead.
            return _OkCursor()

    def executemany(self, sql: str, seq_of_params: Any) -> Any:
        try:
            return self._conn.executemany(sql, seq_of_params)
        except StorageIntegrityError:
            return _OkCursor()

    def executescript(self, sql: str) -> Any:
        return self._conn.executescript(sql)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


class _DroppingCursor:
    """Cursor that drops the first fetched row to simulate a lossy read path."""

    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        rows = list(self._cursor.fetchall())
        return rows[1:] if rows else rows

    def fetchmany(self, size: int | None = None) -> list[Any]:
        rows = list(self._cursor.fetchall())
        kept = rows[1:] if rows else rows
        if size is None:
            return kept
        return kept[:size]

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    def __iter__(self) -> Iterator[Any]:
        return iter(self.fetchall())


class _DroppingConnection:
    """Connection whose cursors drop the first fetched row."""

    def __init__(self, wrapped: StorageConnection) -> None:
        self._conn = wrapped

    @property
    def in_transaction(self) -> bool:
        return self._conn.in_transaction

    @property
    def row_factory(self) -> Any:
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        self._conn.row_factory = value

    def execute(self, sql: str, params: Any = ()) -> _DroppingCursor:
        return _DroppingCursor(self._conn.execute(sql, params))

    def executemany(self, sql: str, seq_of_params: Any) -> _DroppingCursor:
        return _DroppingCursor(self._conn.executemany(sql, seq_of_params))

    def executescript(self, sql: str) -> _DroppingCursor:
        return _DroppingCursor(self._conn.executescript(sql))

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


class FakeRollbackEngine(SqliteEngine):
    """``SqliteEngine`` subclass whose transaction always rolls back."""

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            raw = self._conn.raw
            raw.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                if raw.in_transaction:
                    raw.rollback()
                raise
            else:
                if raw.in_transaction:
                    # Deliberately never commits: writes performed inside the
                    # transaction must be discarded for this acceptance to fail.
                    raw.rollback()


class FakeFirstRowDropEngine(SqliteEngine):
    """``SqliteEngine`` subclass whose read handles drop the first result row."""

    @contextmanager
    def connection(self) -> Iterator[StorageConnection]:
        yield _DroppingConnection(self._conn)


class FakeNoIntegrityErrorEngine(SqliteEngine):
    """``SqliteEngine`` subclass that never reports integrity violations."""

    @contextmanager
    def connection(self) -> Iterator[StorageConnection]:
        yield _OkConnection(self._conn)


@pytest.mark.parametrize("engine_kind", ["sqlite", "postgres"])
def test_real_engine_commits_registration_and_rejects_duplicates(
    engine_kind: str, tmp_path: Path
) -> None:
    """Engine contract: writes commit, columns/schema apply, duplicate users reject with 409."""
    engine = _open_contract_engine(engine_kind, tmp_path)
    service = Service(tmp_path / "seam.sqlite3", engine=engine)
    try:
        assert "id" in engine.columns("users")
        user_id = service.provision("carol", "Temporary-password-05!")
        assert (
            service.conn.execute("SELECT id FROM users WHERE username='carol'").fetchone()
            is not None
        )
        service.create_project("org-c", "project-c", "検証用プロジェクト", owner_id=user_id)
        assert (
            service.conn.execute("SELECT id FROM projects WHERE id='project-c'").fetchone()
            is not None
        )
        service.assign("carol", "project-c", "project_lead")
        document = service.upload(
            Principal(user_id, "carol", True, False),
            "project-c",
            DOCUMENT_NAME,
            DOCUMENT_CONTENT,
            "personal",
        )
        assert (
            service.conn.execute(
                "SELECT id FROM documents WHERE id=?", (document["id"],)
            ).fetchone()
            is not None
        )
        with pytest.raises(HTTPException) as exc_info:
            service.provision("carol", "Temporary-password-06!")
        assert exc_info.value.status_code == 409
    finally:
        service.close()


def test_postgres_contract_does_not_skip_when_database_url_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2 guard: when LOCUS_DATABASE_URL is set, the postgres branch must run, never skip."""
    monkeypatch.setenv("LOCUS_DATABASE_URL", "postgresql://127.0.0.1:5432/locus_test")
    skipped = False
    try:
        _open_contract_engine("postgres", tmp_path)
    except pytest.skip.Exception:
        skipped = True
    except Exception:  # noqa: S110 — driver absence or unreachable port raises a real error, not skip
        pass
    assert not skipped, "PostgreSQL contract test must not skip when LOCUS_DATABASE_URL is set"


def test_rollback_engine_discards_user_creation_and_registration(tmp_path: Path) -> None:
    """A transaction that never commits must discard user creation and document upload."""
    # 1. Broken fake: Service.provision() and Service.upload() do not persist.
    fake_path = tmp_path / "seam-fake.sqlite3"
    fake = Service(fake_path, engine=FakeRollbackEngine(fake_path))
    try:
        fake.provision("carol", "Temporary-password-05!")
    finally:
        fake.close()
    checker = SqliteEngine(fake_path)
    try:
        assert (
            checker.conn.execute("SELECT id FROM users WHERE username='carol'").fetchone() is None
        )
    finally:
        checker.close()

    # Seed prerequisite user + project + membership via real engine, then run
    # Service.upload() through FakeRollbackEngine and verify document does not persist.
    setup = Service(fake_path)
    try:
        doc_owner_id = setup.provision("docowner", "Temporary-password-05!")
        setup.create_project("org-c", "project-c", "検証用プロジェクト", owner_id=doc_owner_id)
        setup.assign("docowner", "project-c", "researcher")
    finally:
        setup.close()

    fake_upload = Service(fake_path, engine=FakeRollbackEngine(fake_path))
    try:
        uploaded = fake_upload.upload(
            Principal(doc_owner_id, "docowner", False, False),
            "project-c",
            DOCUMENT_NAME,
            DOCUMENT_CONTENT,
            "personal",
        )
    finally:
        fake_upload.close()
    checker2 = SqliteEngine(fake_path)
    try:
        assert (
            checker2.conn.execute(
                "SELECT id FROM documents WHERE id=?", (uploaded["id"],)
            ).fetchone()
            is None
        )
    finally:
        checker2.close()

    # 2. Default engine: the exact same Service.provision() + Service.upload() persist.
    real_path = tmp_path / "seam-real.sqlite3"
    real = Service(real_path)
    try:
        real_user_id = real.provision("carol", "Temporary-password-05!")
        real.create_project("org-c", "project-c", "検証用プロジェクト", owner_id=real_user_id)
        real.assign("carol", "project-c", "researcher")
        real_uploaded = real.upload(
            Principal(real_user_id, "carol", False, False),
            "project-c",
            DOCUMENT_NAME,
            DOCUMENT_CONTENT,
            "personal",
        )
    finally:
        real.close()
    real_checker = SqliteEngine(real_path)
    try:
        assert (
            real_checker.conn.execute("SELECT id FROM users WHERE id=?", (real_user_id,)).fetchone()
            is not None
        )
        assert (
            real_checker.conn.execute(
                "SELECT id FROM documents WHERE id=?", (real_uploaded["id"],)
            ).fetchone()
            is not None
        )
    finally:
        real_checker.close()


def test_first_row_drop_engine_breaks_project_listing(tmp_path: Path) -> None:
    """A read handle that drops the first row must break authorization and listing."""
    service = Service(
        tmp_path / "seam.sqlite3", engine=FakeFirstRowDropEngine(tmp_path / "seam.sqlite3")
    )
    try:
        user_id = service.provision("admin", "Temporary-password-01!", system_admin=True)
        service.create_project("org-a", "project-a", "研究プロジェクト", owner_id=user_id)
        projects = service.admin_projects(Principal(user_id, "admin", True, False))
        # The representative acceptance (the created project must be listed) fails:
        # the broken engine drops the first fetched row, so the listing loses it.
        assert projects == []
    finally:
        service.close()
    # The same acceptance passes with the default engine.
    real = Service(tmp_path / "seam-real.sqlite3")
    try:
        real_user_id = real.provision("admin", "Temporary-password-01!", system_admin=True)
        real.create_project("org-a", "project-a", "研究プロジェクト", owner_id=real_user_id)
        real_projects = real.admin_projects(Principal(real_user_id, "admin", True, False))
        assert len(real_projects) == 1
        assert real_projects[0]["id"] == "project-a"
    finally:
        real.close()


def test_no_integrity_error_engine_allows_duplicate_user_creation(tmp_path: Path) -> None:
    """A fake that never reports integrity violations must not reject duplicates."""
    service = Service(
        tmp_path / "seam.sqlite3", engine=FakeNoIntegrityErrorEngine(tmp_path / "seam.sqlite3")
    )
    try:
        service.provision("carol", "Temporary-password-05!")
        # The fake never raises, so the same username may be created twice.
        second_user_id = service.provision("carol", "Temporary-password-06!")
        assert second_user_id is not None
    finally:
        service.close()
    # The same acceptance passes with the default engine: duplicates are rejected.
    real = Service(tmp_path / "seam-real.sqlite3")
    try:
        real.provision("carol", "Temporary-password-05!")
        with pytest.raises(HTTPException) as exc_info:
            real.provision("carol", "Temporary-password-06!")
        assert exc_info.value.status_code == 409
    finally:
        real.close()
