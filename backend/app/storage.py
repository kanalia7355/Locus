"""Storage engine seam that backs :class:`app.service.Service`.

Everything SQLite-specific that used to be scattered through ``service.py`` lives
here, behind :class:`StorageEngine`.  PostgreSQL support (T-PH7-212) will conform
to the same protocol without changing the rest of the codebase.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
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
