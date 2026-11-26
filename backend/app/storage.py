"""Storage engine seam that backs :class:`app.service.Service`.

Everything SQLite-specific that used to be scattered through ``service.py`` lives
here, behind :class:`StorageEngine`.  PostgreSQL support (T-PH7-212) will conform
to the same protocol without changing the rest of the codebase.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol, cast


class StorageError(sqlite3.Error):
    """Raised when a storage operation fails, independent of the concrete engine.

    Inheriting from ``sqlite3.Error`` keeps the existing ``except sqlite3.Error``
    callers (e.g. ``app.agents.registry``) working while the seam is introduced.
    """


class StorageIntegrityError(StorageError, sqlite3.IntegrityError):
    """Raised when a constraint such as a unique key is violated."""


def _storage_error_class(
    base: type[StorageError], sqlite_error: type[sqlite3.Error]
) -> type[StorageError]:
    """Build a storage error subclass that also inherits the concrete sqlite error."""
    combined = type(
        "Storage" + sqlite_error.__name__, (base, sqlite_error), {"__module__": __name__}
    )
    return cast(type[StorageError], combined)


def _storage_error(exc: sqlite3.Error) -> StorageError:
    """Wrap ``exc`` in a storage error while preserving its concrete sqlite subtype."""
    if isinstance(exc, sqlite3.IntegrityError):
        if isinstance(exc, StorageIntegrityError):
            return type(exc)(str(exc))
        return _storage_error_class(StorageIntegrityError, sqlite3.IntegrityError)(str(exc))
    if isinstance(exc, StorageError):
        return type(exc)(str(exc))
    return _storage_error_class(StorageError, sqlite3.Error)(str(exc))


class StorageCursor(Protocol):
    """Cursor contract: rows are mapping-style, so ``row["col"]`` and ``dict(row)`` work."""

    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...

    def fetchmany(self, size: int | None = None) -> list[Any]: ...

    @property
    def rowcount(self) -> int: ...

    @property
    def lastrowid(self) -> int | None: ...

    @property
    def description(self) -> Any: ...

    def __iter__(self) -> Iterator[Any]: ...


class StorageConnection(Protocol):
    """Read/write handle used by ``Service`` and exposed as ``Service.conn``.

    ``execute()`` returns a cursor whose ``fetchone()`` / ``fetchall()`` produce
    mapping-style rows, so ``row["col"]`` and ``dict(row)`` keep working exactly
    as they did with ``sqlite3.Row``.
    """

    row_factory: Any

    @property
    def in_transaction(self) -> bool: ...

    def execute(self, sql: str, params: Any = ()) -> StorageCursor: ...

    def executemany(self, sql: str, seq_of_params: Any) -> StorageCursor: ...

    def executescript(self, sql: str) -> StorageCursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class StorageEngine(Protocol):
    """Protocol for a storage engine that backs ``Service``.

    The engine owns the transaction lifecycle.  ``Service.db()`` enters
    ``transaction()`` for write serialization and then reads the handle from
    ``connection()``; callers do not issue ``BEGIN``/``COMMIT`` themselves.
    """

    @property
    def lock(self) -> Any:
        """Write-serialization lock shared with ``Service.lock``.

        ``Service`` exposes this lock to collaborators (the agent registry) and
        temporarily releases it around connector calls, so it must be the same
        object the engine holds for the duration of ``transaction()``.
        """
        ...

    @property
    def conn(self) -> StorageConnection:
        """Return the read/write handle kept for ``Service.conn`` compatibility."""
        ...

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Begin a write-serialized transaction and commit on normal exit.

        On exception the transaction is rolled back.  A caller that has already
        committed explicitly (and did not begin again) is left alone, matching
        the legacy ``sqlite3`` commit/rollback guards in ``Service.db()``.
        """
        ...

    @contextmanager
    def connection(self) -> Iterator[StorageConnection]:
        """Yield the low-level handle used inside ``transaction()``."""
        ...

    def apply_schema(self, script: str) -> None:
        """Execute a schema script (``CREATE TABLE`` / ``CREATE TRIGGER`` etc.)."""

        ...

    def ensure_column(self, table: str, column: str, definition: str) -> None:
        """Add a column to *table* if it does not already exist."""

        ...

    def columns(self, table: str) -> set[str]:
        """Return the set of column names for *table.*"""

        ...

    def close(self) -> None:
        """Tidily shut down the engine (close underlying connections, etc.)."""

        ...


class _WrappedCursor:
    """Cursor wrapper that translates sqlite3 errors into storage errors."""

    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    def fetchone(self) -> Any:
        try:
            return self._cursor.fetchone()
        except sqlite3.Error as exc:
            raise _storage_error(exc) from exc

    def fetchall(self) -> list[Any]:
        try:
            return self._cursor.fetchall()
        except sqlite3.Error as exc:
            raise _storage_error(exc) from exc

    def fetchmany(self, size: int | None = None) -> list[Any]:
        try:
            if size is None:
                return self._cursor.fetchmany()
            return self._cursor.fetchmany(size)
        except sqlite3.Error as exc:
            raise _storage_error(exc) from exc

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self) -> int | None:
        return self._cursor.lastrowid

    @property
    def description(self) -> Any:
        return self._cursor.description

    def __iter__(self) -> Iterator[Any]:
        try:
            yield from self._cursor
        except sqlite3.Error as exc:
            raise _storage_error(exc) from exc

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class _WrappedConnection:
    """Connection wrapper that translates sqlite3 errors into storage errors."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def row_factory(self) -> Any:
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        self._conn.row_factory = value

    def execute(self, sql: str, params: Any = ()) -> _WrappedCursor:
        try:
            return _WrappedCursor(self._conn.execute(sql, params))
        except sqlite3.IntegrityError as exc:
            raise _storage_error(exc) from exc
        except sqlite3.Error as exc:
            raise _storage_error(exc) from exc

    def executemany(self, sql: str, seq_of_params: Any) -> _WrappedCursor:
        try:
            return _WrappedCursor(self._conn.executemany(sql, seq_of_params))
        except sqlite3.IntegrityError as exc:
            raise _storage_error(exc) from exc
        except sqlite3.Error as exc:
            raise _storage_error(exc) from exc

    def executescript(self, sql: str) -> _WrappedCursor:
        try:
            return _WrappedCursor(self._conn.executescript(sql))
        except sqlite3.Error as exc:
            raise _storage_error(exc) from exc

    def commit(self) -> None:
        try:
            self._conn.commit()
        except sqlite3.Error as exc:
            raise _storage_error(exc) from exc

    def rollback(self) -> None:
        try:
            self._conn.rollback()
        except sqlite3.Error as exc:
            raise _storage_error(exc) from exc

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error as exc:
            raise _storage_error(exc) from exc

    @property
    def raw(self) -> sqlite3.Connection:
        return self._conn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


class SqliteEngine:
    """``StorageEngine`` implementation reproducing the legacy SQLite behaviour.

    This mirrors exactly what ``Service.__init__`` and ``Service.db()`` used to
    do with raw ``sqlite3``: one shared connection, ``check_same_thread=False``,
    autocommit mode (``isolation_level=None``), mapping rows, foreign keys on,
    an ``RLock`` serializing write transactions and ``BEGIN IMMEDIATE``.
    """

    backend_name = "sqlite"

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        self._conn = _WrappedConnection(raw)
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    @property
    def conn(self) -> _WrappedConnection:
        """Return the shared connection handle kept for ``Service.conn``."""
        return self._conn

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            raw = self._conn.raw
            try:
                raw.execute("BEGIN IMMEDIATE")
            except sqlite3.Error as exc:
                raise _storage_error(exc) from exc
            try:
                yield
            except BaseException:
                try:
                    if raw.in_transaction:
                        raw.rollback()
                except sqlite3.Error as exc:
                    raise _storage_error(exc) from exc
                raise
            else:
                try:
                    if raw.in_transaction:
                        raw.commit()
                except sqlite3.Error as exc:
                    raise _storage_error(exc) from exc

    @contextmanager
    def connection(self) -> Iterator[_WrappedConnection]:
        # The write-serialization lock is held by transaction(); re-acquiring it
        # here would make the caller's explicit release (around connector calls)
        # ineffective because the RLock recursion count would stay above zero.
        yield self._conn

    def apply_schema(self, script: str) -> None:
        with self._lock:
            try:
                self._conn.raw.executescript(script)
            except sqlite3.Error as exc:
                raise _storage_error(exc) from exc

    def ensure_column(self, table: str, column: str, definition: str) -> None:
        with self._lock:
            if column not in self.columns(table):
                try:
                    self._conn.raw.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                except sqlite3.Error as exc:
                    raise _storage_error(exc) from exc

    def columns(self, table: str) -> set[str]:
        with self._lock:
            rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row["name"] for row in rows}

    def close(self) -> None:
        with self._lock:
            self._conn.close()


SNAPSHOT_FORMAT_VERSION = 1

# Topological parent-first table order covering every Service table so foreign
# keys are satisfied during import (and reverse order during reset).
SERVICE_SNAPSHOT_TABLES: tuple[str, ...] = (
    "users",
    "sessions",
    "recovery_codes",
    "projects",
    "project_owners",
    "roles",
    "memberships",
    "membership_roles",
    "delegation_families",
    "delegation_grants",
    "delegation_events",
    "conversations",
    "documents",
    "chunks",
    "storage_sources",
    "source_objects",
    "document_source_bindings",
    "document_origins",
    "messages",
    "generated_answers",
    "chat_jobs",
    "audit",
    "audit_chain",
    "audit_chain_head",
    "login_events",
    "login_throttle",
)

OPTIONAL_SNAPSHOT_TABLES: tuple[str, ...] = (
    "runner_instances",
    "workspace_policies",
    "workspaces",
    "agent_adapters",
    "provider_contract_verifications",
    "adapter_capabilities",
    "workspace_adapter_bindings",
    "adapter_health",
    "adapter_credentials",
    "job_authorization_receipts",
    "runner_artifacts",
)

_SNAPSHOT_ORDER_KEYS: dict[str, tuple[str, ...]] = {
    "users": ("id",),
    "sessions": ("token_hash",),
    "recovery_codes": ("user_id",),
    "projects": ("id",),
    "project_owners": ("project_id",),
    "roles": ("id",),
    "memberships": ("user_id", "project_id"),
    "membership_roles": ("user_id", "project_id", "role"),
    "delegation_families": ("id",),
    "delegation_grants": ("id",),
    "delegation_events": ("id",),
    "conversations": ("id",),
    "documents": ("id",),
    "chunks": ("id",),
    "storage_sources": ("id",),
    "source_objects": ("source_id", "object_id"),
    "document_source_bindings": ("document_id", "source_id", "object_id"),
    "document_origins": ("document_id",),
    "messages": ("id",),
    "generated_answers": ("message_id",),
    "chat_jobs": ("id",),
    "audit": ("at", "id"),
    "audit_chain": ("seq",),
    "audit_chain_head": ("id",),
    "login_events": ("id",),
    "login_throttle": ("user_id",),
    "runner_instances": ("id",),
    "workspace_policies": ("id", "version"),
    "workspaces": ("id",),
    "agent_adapters": ("id",),
    "provider_contract_verifications": ("id",),
    "adapter_capabilities": ("id",),
    "workspace_adapter_bindings": (
        "workspace_id",
        "runner_instance_id",
        "adapter_id",
        "policy_id",
        "policy_version",
    ),
    "adapter_health": ("runner_instance_id", "adapter_id"),
    "adapter_credentials": ("runner_instance_id", "adapter_id"),
    "job_authorization_receipts": ("id",),
    "runner_artifacts": ("id",),
}


def select_storage_engine(
    default_sqlite_path: Path, *, environ: Mapping[str, str] | None = None
) -> StorageEngine:
    """Choose ``PostgresEngine`` when ``LOCUS_DATABASE_URL`` is set, else ``SqliteEngine``."""
    env = os.environ if environ is None else environ
    if "LOCUS_DATABASE_URL" not in env:
        return SqliteEngine(default_sqlite_path)
    from app.storage_postgres import PostgresEngine, validate_database_url

    dsn = validate_database_url(env["LOCUS_DATABASE_URL"])
    return PostgresEngine(dsn)


def _normalize_snapshot_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, bool):
            return int(value)
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return str(value)


def _canonical_row_sort_key(row: Mapping[str, Any], order_cols: Sequence[str]) -> tuple[Any, ...]:
    parts: list[Any] = []
    for col in order_cols:
        val = row.get(col)
        if val is None:
            parts.append((0, ""))
        elif isinstance(val, (int, float)):
            parts.append((1, float(val)))
        else:
            parts.append((2, str(val)))
    return tuple(parts)


def _table_checksum(table: str, rows: Sequence[Mapping[str, Any]]) -> str:
    order_cols = _SNAPSHOT_ORDER_KEYS.get(table)
    ordered = (
        sorted(rows, key=lambda r: _canonical_row_sort_key(r, order_cols))
        if order_cols
        else list(rows)
    )
    normalized_rows = [
        {k: _normalize_snapshot_value(row[k]) for k in sorted(row.keys())} for row in ordered
    ]
    payload = json.dumps(normalized_rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def export_snapshot(engine: StorageEngine) -> dict[str, Any]:
    """Export all tables from *engine* into an engine-independent snapshot dict."""
    tables_data: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, int] = {}
    checksums: dict[str, str] = {}

    with engine.transaction(), engine.connection() as conn:
        for table in SERVICE_SNAPSHOT_TABLES:
            cols = engine.columns(table)
            if not cols:
                raise StorageError(f"Required table '{table}' is missing from source engine")
            if table == "audit" and engine.columns("audit_chain"):
                raw_rows = conn.execute(
                    "SELECT audit.* FROM audit "
                    "LEFT JOIN audit_chain ON audit_chain.audit_id = audit.id "
                    "ORDER BY CASE WHEN audit_chain.seq IS NULL THEN 1 ELSE 0 END ASC, "
                    "audit_chain.seq ASC, audit.at ASC, audit.id ASC"
                ).fetchall()
            else:
                order_cols = _SNAPSHOT_ORDER_KEYS.get(table, ())
                valid_order = [c for c in order_cols if c in cols]
                order_sql = (
                    f" ORDER BY {', '.join(f'{c} ASC' for c in valid_order)}" if valid_order else ""
                )
                raw_rows = conn.execute(f"SELECT * FROM {table}{order_sql}").fetchall()  # noqa: S608
            exported_rows = [
                {col: _normalize_snapshot_value(row[col]) for col in sorted(row.keys())}
                for row in raw_rows
            ]
            tables_data[table] = exported_rows
            counts[table] = len(exported_rows)
            checksums[table] = _table_checksum(table, exported_rows)

        for table in OPTIONAL_SNAPSHOT_TABLES:
            cols = engine.columns(table)
            if not cols:
                continue
            order_cols = _SNAPSHOT_ORDER_KEYS.get(table, ())
            valid_order = [c for c in order_cols if c in cols]
            order_sql = (
                f" ORDER BY {', '.join(f'{c} ASC' for c in valid_order)}" if valid_order else ""
            )
            raw_rows = conn.execute(f"SELECT * FROM {table}{order_sql}").fetchall()  # noqa: S608
            exported_rows = [
                {col: _normalize_snapshot_value(row[col]) for col in sorted(row.keys())}
                for row in raw_rows
            ]
            tables_data[table] = exported_rows
            counts[table] = len(exported_rows)
            checksums[table] = _table_checksum(table, exported_rows)

    overall_payload = json.dumps(
        {"counts": counts, "checksums": checksums}, sort_keys=True, separators=(",", ":")
    )
    return {
        "version": SNAPSHOT_FORMAT_VERSION,
        "table_order": [
            t for t in (*SERVICE_SNAPSHOT_TABLES, *OPTIONAL_SNAPSHOT_TABLES) if t in tables_data
        ],
        "tables": tables_data,
        "counts": counts,
        "checksums": checksums,
        "overall_checksum": hashlib.sha256(overall_payload.encode("utf-8")).hexdigest(),
    }


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    """Validate structural completeness, row counts, and SHA-256 checksums of *snapshot*."""
    if not isinstance(snapshot, Mapping):
        raise StorageError("Snapshot must be a mapping")
    if snapshot.get("version") != SNAPSHOT_FORMAT_VERSION:
        raise StorageError(f"Unsupported snapshot version: {snapshot.get('version')!r}")
    tables = snapshot.get("tables")
    counts = snapshot.get("counts")
    checksums = snapshot.get("checksums")
    if (
        not isinstance(tables, Mapping)
        or not isinstance(counts, Mapping)
        or not isinstance(checksums, Mapping)
    ):
        raise StorageError("Snapshot is missing 'tables', 'counts', or 'checksums'")

    missing_required = [t for t in SERVICE_SNAPSHOT_TABLES if t not in tables]
    if missing_required:
        raise StorageError(f"Snapshot is missing required tables: {', '.join(missing_required)}")

    for table, rows in tables.items():
        if not isinstance(rows, list):
            raise StorageError(f"Snapshot table '{table}' rows must be a list")
        if table not in counts or counts[table] != len(rows):
            raise StorageError(
                f"Snapshot count mismatch for table '{table}': "
                f"recorded={counts.get(table)!r}, actual={len(rows)}"
            )
        actual_checksum = _table_checksum(table, rows)
        if checksums.get(table) != actual_checksum:
            raise StorageError(f"Snapshot checksum mismatch for table '{table}'")

    extra_counts = set(counts.keys()) - set(tables.keys())
    extra_checksums = set(checksums.keys()) - set(tables.keys())
    if extra_counts or extra_checksums:
        raise StorageError("Snapshot metadata references tables absent from 'tables'")

    expected_overall_payload = json.dumps(
        {"counts": dict(counts), "checksums": dict(checksums)},
        sort_keys=True,
        separators=(",", ":"),
    )
    expected_overall = hashlib.sha256(expected_overall_payload.encode("utf-8")).hexdigest()
    if snapshot.get("overall_checksum") != expected_overall:
        raise StorageError("Snapshot overall_checksum mismatch")


def verify_snapshot(engine: StorageEngine, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Verify *snapshot* and compare *engine*'s live counts and checksums against it."""
    validate_snapshot(snapshot)
    live = export_snapshot(engine)
    expected_tables = snapshot["tables"]

    for table in expected_tables:
        if table not in live["tables"]:
            raise StorageError(f"Target engine is missing table '{table}'")
        if live["counts"][table] != snapshot["counts"][table]:
            raise StorageError(
                f"Row count mismatch after migration for '{table}': "
                f"expected={snapshot['counts'][table]}, actual={live['counts'][table]}"
            )
        if live["checksums"][table] != snapshot["checksums"][table]:
            raise StorageError(f"Checksum mismatch after migration for '{table}'")

    return {
        "ok": True,
        "tables_verified": len(expected_tables),
        "counts": dict(live["counts"]),
        "overall_checksum": live["overall_checksum"],
    }


def import_snapshot(engine: StorageEngine, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Import a validated *snapshot* into an empty initialized *engine* and verify parity."""
    validate_snapshot(snapshot)
    tables: Mapping[str, list[dict[str, Any]]] = snapshot["tables"]
    ordered_tables = [
        t for t in (*SERVICE_SNAPSHOT_TABLES, *OPTIONAL_SNAPSHOT_TABLES) if t in tables
    ]

    with engine.transaction(), engine.connection() as conn:
        for table in ordered_tables:
            existing_cols = engine.columns(table)
            if not existing_cols:
                raise StorageError(
                    f"Target engine does not have table '{table}'; initialize schema first"
                )
            existing_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            if int(existing_count) != 0:
                raise StorageError(
                    f"Target table '{table}' is not empty ({existing_count} rows); "
                    "import requires a clean initialized target database"
                )

        for table in ordered_tables:
            rows = tables[table]
            if not rows:
                continue
            if table in {"audit_chain", "audit_chain_head"}:
                # Importing into 'audit' triggers audit_chain_insert which populates
                # audit_chain and audit_chain_head automatically in (at, id) order.
                # Verify that the trigger-populated state matches the snapshot; if the
                # target had no trigger rows (e.g. empty or custom), insert explicitly.
                current_count = int(
                    conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
                )
                if current_count > 0:
                    continue

            cols = sorted(rows[0].keys())
            col_list = ", ".join(cols)
            placeholders = ", ".join("?" for _ in cols)
            insert_kw = "INSERT OR IGNORE INTO" if table == "membership_roles" else "INSERT INTO"
            sql = f"{insert_kw} {table} ({col_list}) VALUES ({placeholders})"  # noqa: S608
            for row in rows:
                conn.execute(sql, tuple(row[c] for c in cols))

    return verify_snapshot(engine, snapshot)
