"""Transactional prototype services; production adapters remain undecided."""

import hashlib
import json
import math
import re
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, Protocol
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException

from app.connectors import CONNECTOR_FACTORIES, connector_for
from app.connectors.base import SourceConnector, SourceObject
from app.connectors.scheduler import DEFAULT_INTERVAL_SECONDS, SourceScheduler
from app.connectors.synthetic import SyntheticSourceConnector
from app.formats import (
    accepted_format_names,
    format_catalog,
    format_for,
    max_content_bytes,
)
from app.password_rules import (
    LOCK_DURATION_SECONDS,
    LOCK_FAILURE_THRESHOLD,
    check_password_strength,
)
from app.sandbox import SUBPROCESS_GUARANTEES, SandboxResult, extract_with_sandbox
from app.scanner import UNAVAILABLE, ScanResult
from app.storage import (
    SqliteEngine,
    StorageConnection,
    StorageEngine,
    StorageError,
    StorageIntegrityError,
)

Json = dict[str, Any]
PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
# Login history retention: 1 year (matches the 1-year audit retention decision).
# Pruning is limited to login_events only; no other tables are auto-deleted.
LOGIN_HISTORY_RETENTION_SECONDS = 365 * 24 * 60 * 60
SECONDS_PER_DAY = 24 * 60 * 60
DEFAULT_RETENTION_DAYS = 365
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 3650
NON_ADMIN = frozenset({"read", "retrieve", "upload", "publish"})
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "system_admin": frozenset(),
    "organization_admin": NON_ADMIN | {"manage_roles", "manage_members"},
    "assistant_admin": frozenset({"read", "retrieve", "manage_roles"}),
    "project_lead": NON_ADMIN | {"manage_roles", "manage_members"},
    "researcher": frozenset({"read", "retrieve", "upload"}),
    "research_assistant": frozenset({"read", "retrieve", "upload"}),
    "general_user": frozenset({"read", "retrieve", "upload"}),
    "viewer": frozenset({"read", "retrieve"}),
    "guest": frozenset({"read"}),
    "auditor": frozenset({"read"}),
}
ALL_PERMISSIONS = frozenset().union(*ROLE_PERMISSIONS.values()) | NON_ADMIN
# Coarse ingestion stages exposed to the UI. Persisted statuses stay backward
# compatible (`ready` remains the usable state); `indexing` is the new resumable
# stage between scanning and publication.
DOCUMENT_STAGES = {
    "queued": "queued",
    "scanning": "scanning",
    "indexing": "indexing",
    "ready": "done",
    "quarantined": "failed",
    "failed": "failed",
    "cancelled": "failed",
}
CHUNK_CHARS = 700

# Ingestion bounds. `upload` enforces them and `inventory` reports against them,
# so both must read the same values: a format or limit change that reached only
# one of them would make the pre-ingestion report disagree with the write path.
# Accepted formats and their per-format byte bounds are declared in the single
# table in `app.formats`; both write paths and the formats API read that table.
MAX_NAME_LENGTH = 160
IN_FLIGHT_LIMIT = 32
OWNER_IN_FLIGHT_LIMIT = 4
DOCUMENT_LIMIT = 1000
OWNER_DOCUMENT_LIMIT = 100


def unsafe_document_name(name: str) -> bool:
    """True when the name itself is rejected, regardless of its extension."""
    return (
        not name
        or len(name) > MAX_NAME_LENGTH
        or any(character in name for character in "/\\:\x00")
        or name.startswith(".")
        or any(ord(character) < 32 for character in name)
    )


def unsupported_extension(name: str) -> bool:
    """True when the extension is outside the accepted text formats."""
    return format_for(name) is None


SYNTHETIC_TEXT = (
    "【合成サンプル・実研究データではありません】\n"
    "成膜条件Aは処理温度180°C、処理時間30分。\n"
    "成膜条件Bは処理温度200°C、処理時間20分。\n"
    "この記述はUIと出典確認の検証専用です。実験結果や性能を示しません。"
)


def uid() -> str:
    return uuid4().hex


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


AUDIT_CHAIN_GENESIS = "genesis"


def _audit_canon_at(at: Any) -> str:
    """Canonical text form for audit timestamps.

    SQLite REAL values round-trip through Python floats; format with enough
    precision to keep the same float value stable across hash computation and
    verification reads.
    """
    if isinstance(at, bool):
        # bool is an int subclass; treat as its numeric value explicitly.
        return format(float(int(at)), ".17g")
    if isinstance(at, (int, float)):
        return format(float(at), ".17g")
    return str(at)


def _audit_hash_payload(
    prev_hash: str,
    audit_id: str,
    at: Any,
    actor_id: str,
    operation: str,
    target_id: str,
    outcome: str,
) -> str:
    """Hash one audit row into the append-only chain.

    Canonicalization is length-prefixed UTF-8 for every field (prev_hash plus
    the 6 audit columns) joined with NUL. The length prefix makes column
    boundaries unambiguous, so shifting bytes between adjacent columns cannot
    produce the same payload.
    """
    fields = [
        str(prev_hash),
        str(audit_id),
        _audit_canon_at(at),
        str(actor_id),
        str(operation),
        str(target_id),
        str(outcome),
    ]
    body = "\x00".join(f"{len(f.encode('utf-8'))}:{f}" for f in fields)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _audit_sha256_udf(
    prev_hash: Any,
    audit_id: Any,
    at: Any,
    actor_id: Any,
    operation: Any,
    target_id: Any,
    outcome: Any,
) -> str:
    """SQLite UDF wrapper; registered per-connection as audit_sha256."""
    return _audit_hash_payload(
        str(prev_hash),
        str(audit_id),
        at,
        str(actor_id),
        str(operation),
        str(target_id),
        str(outcome),
    )


def fail(status: int, detail: str) -> NoReturn:
    raise HTTPException(status, detail)


class ModelBusy(Exception):
    """Raised when the single model slot is occupied; the caller may enqueue instead."""


class ChatCancelled(Exception):
    """Raised inside a streamed dialogue once its owner asked to cancel it."""


# Bounded development-safety limits for the dialogue waiting line, mirroring the
# ingestion queue limits. They are not verified user capacity.
CHAT_WAIT_SECONDS = 300.0
CHAT_QUEUE_LIMIT = 16
CHAT_USER_QUEUE_LIMIT = 2


@dataclass(frozen=True)
class ChatDispatch:
    """Process-local closures for one queued dialogue; never persisted to storage."""

    token: str
    generate: Callable[[str, list[Json]], tuple[str, str]]
    validate: Callable[[], None] | None


@dataclass(frozen=True)
class Principal:
    id: str
    username: str
    system_admin: bool
    must_rotate: bool


class Scanner(Protocol):
    def scan(self, content: str) -> ScanResult: ...


_SYNC_CONNECTORS_MODULE = None


def _sync_connectors_module() -> Any:
    global _SYNC_CONNECTORS_MODULE
    if _SYNC_CONNECTORS_MODULE is None:
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "app_connectors_sync_base", Path(__file__).with_name("connectors.py")
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("connectors module unavailable")
        module = importlib.util.module_from_spec(spec)
        import sys

        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _SYNC_CONNECTORS_MODULE = module
    return _SYNC_CONNECTORS_MODULE


class UnavailableScanner:
    def scan(self, content: str) -> ScanResult:
        return UNAVAILABLE


class Service:
    def __init__(
        self,
        path: Path,
        *,
        scanner: Scanner | None = None,
        source_connector: SourceConnector | None = None,
        source_scheduler: SourceScheduler | None = None,
        engine: StorageEngine | None = None,
    ) -> None:
        self._engine = engine if engine is not None else SqliteEngine(path)
        self._register_audit_hash_function()
        self.scanner = scanner or UnavailableScanner()
        # Fail-closed visibility: only an adapter that can actually perform the
        # safety check counts as configured; the placeholder always quarantines.
        self.scanner_configured = not isinstance(self.scanner, UnavailableScanner)
        # Operational outcome of the most recent scan, reported separately from
        # adapter configuration: None means no scan has run yet.
        self.scanner_last_outcome: str | None = None
        configured = (
            source_connector if source_connector is not None else connector_for("synthetic")
        )
        self.source_connector: SourceConnector = configured or SyntheticSourceConnector()
        self.source_connectors: dict[str, SourceConnector] = {
            self.source_connector.source_id: self.source_connector
        }
        # Every registered destination kind is available through the same table;
        # later tasks add one registry entry and no service wiring.
        for kind in CONNECTOR_FACTORIES:
            if kind == self.source_connector.kind:
                continue
            registered = connector_for(kind)
            if registered is not None:
                self.source_connectors.setdefault(registered.source_id, registered)
        self.source_interval_seconds: int = DEFAULT_INTERVAL_SECONDS
        self.retention_days: int = DEFAULT_RETENTION_DAYS
        self.source_scheduler: SourceScheduler = (
            source_scheduler
            if source_scheduler is not None
            else SourceScheduler(interval_seconds=self.source_interval_seconds)
        )
        # Sync-connector registry (new common base). Values never include credentials.
        self.sync_connectors: dict[str, Any] = {}
        self.sync_connector_credentials_configured: dict[str, bool] = {
            "local_folder": False,
            "google_drive": False,
            "box": False,
        }
        self.limits: OrderedDict[str, list[float]] = OrderedDict()
        self.chat_dispatch: dict[str, ChatDispatch] = {}
        self.chat_dispatch_lock = threading.Lock()
        self.last_chat_user: str | None = None
        self.dummy_hash = PASSWORDS.hash(secrets.token_urlsafe(32))
        self._engine.apply_schema("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
                must_rotate INTEGER NOT NULL, temp_expires REAL,
                temp_used INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1, system_admin INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                expires REAL NOT NULL, last_seen REAL NOT NULL, rotation_only INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recovery_codes (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                code_hash TEXT NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, org_id TEXT NOT NULL, name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS project_owners (
                project_id TEXT PRIMARY KEY REFERENCES projects(id),
                user_id TEXT NOT NULL REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS memberships (
                user_id TEXT REFERENCES users(id), project_id TEXT REFERENCES projects(id),
                role TEXT NOT NULL, PRIMARY KEY(user_id, project_id)
            );
            CREATE TABLE IF NOT EXISTS roles (
                id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id), name TEXT NOT NULL,
                permissions TEXT NOT NULL, UNIQUE(project_id, name)
            );
            CREATE TABLE IF NOT EXISTS membership_roles (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                PRIMARY KEY(user_id, project_id, role)
            );
            CREATE TABLE IF NOT EXISTS delegation_families (
                id TEXT PRIMARY KEY,
                grantor_id TEXT NOT NULL REFERENCES users(id),
                recipient_id TEXT NOT NULL REFERENCES users(id),
                project_id TEXT NOT NULL REFERENCES projects(id),
                permissions TEXT NOT NULL,
                created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS delegation_grants (
                id TEXT PRIMARY KEY,
                family_id TEXT NOT NULL REFERENCES delegation_families(id),
                version INTEGER NOT NULL CHECK(version > 0),
                permissions TEXT NOT NULL,
                created REAL NOT NULL,
                expires REAL NOT NULL,
                UNIQUE(family_id, version)
            );
            CREATE TABLE IF NOT EXISTS delegation_events (
                id TEXT PRIMARY KEY,
                grant_id TEXT NOT NULL REFERENCES delegation_grants(id),
                event_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                at REAL NOT NULL,
                UNIQUE(grant_id, event_type)
            );
            CREATE TRIGGER IF NOT EXISTS delegation_family_no_update
            BEFORE UPDATE ON delegation_families BEGIN
                SELECT RAISE(ABORT, 'delegation families are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_family_no_delete
            BEFORE DELETE ON delegation_families BEGIN
                SELECT RAISE(ABORT, 'delegation families are retained');
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_grant_no_update
            BEFORE UPDATE ON delegation_grants BEGIN
                SELECT RAISE(ABORT, 'delegation grants are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_grant_no_delete
            BEFORE DELETE ON delegation_grants BEGIN
                SELECT RAISE(ABORT, 'delegation grants are retained');
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_event_no_update
            BEFORE UPDATE ON delegation_events BEGIN
                SELECT RAISE(ABORT, 'delegation events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_event_no_delete
            BEFORE DELETE ON delegation_events BEGIN
                SELECT RAISE(ABORT, 'delegation events are retained');
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_grantor_membership_delete
            AFTER DELETE ON memberships BEGIN
                INSERT OR IGNORE INTO delegation_events
                    (id,grant_id,event_type,actor_id,at)
                SELECT lower(hex(randomblob(16))),g.id,'invalidate','system',
                    (julianday('now') - 2440587.5) * 86400.0
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=OLD.user_id AND f.project_id=OLD.project_id;
                INSERT INTO audit
                SELECT lower(hex(randomblob(16))),(julianday('now') - 2440587.5) * 86400.0,
                    'system','delegation.invalidate',g.id,'ok'
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=OLD.user_id AND f.project_id=OLD.project_id
                    AND EXISTS (SELECT 1 FROM delegation_events e
                        WHERE e.grant_id=g.id AND e.event_type='invalidate')
                    AND NOT EXISTS (SELECT 1 FROM audit a
                        WHERE a.operation='delegation.invalidate' AND a.target_id=g.id);
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_grantor_role_update
            AFTER UPDATE OF permissions,denied_permissions ON roles BEGIN
                INSERT OR IGNORE INTO delegation_events
                    (id,grant_id,event_type,actor_id,at)
                SELECT lower(hex(randomblob(16))),g.id,'invalidate','system',
                    (julianday('now') - 2440587.5) * 86400.0
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                JOIN membership_roles mr ON mr.user_id=f.grantor_id
                    AND mr.project_id=f.project_id AND mr.role=OLD.id
                WHERE OLD.project_id=f.project_id;
                INSERT INTO audit
                SELECT lower(hex(randomblob(16))),(julianday('now') - 2440587.5) * 86400.0,
                    'system','delegation.invalidate',g.id,'ok'
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                JOIN membership_roles mr ON mr.user_id=f.grantor_id
                    AND mr.project_id=f.project_id AND mr.role=OLD.id
                WHERE OLD.project_id=f.project_id
                    AND EXISTS (SELECT 1 FROM delegation_events e
                        WHERE e.grant_id=g.id AND e.event_type='invalidate')
                    AND NOT EXISTS (SELECT 1 FROM audit a
                        WHERE a.operation='delegation.invalidate' AND a.target_id=g.id);
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_grantor_role_add
            AFTER INSERT ON membership_roles BEGIN
                INSERT OR IGNORE INTO delegation_events
                    (id,grant_id,event_type,actor_id,at)
                SELECT lower(hex(randomblob(16))),g.id,'invalidate','system',
                    (julianday('now') - 2440587.5) * 86400.0
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=NEW.user_id AND f.project_id=NEW.project_id;
                INSERT INTO audit
                SELECT lower(hex(randomblob(16))),(julianday('now') - 2440587.5) * 86400.0,
                    'system','delegation.invalidate',g.id,'ok'
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=NEW.user_id AND f.project_id=NEW.project_id
                    AND EXISTS (SELECT 1 FROM delegation_events e
                        WHERE e.grant_id=g.id AND e.event_type='invalidate')
                    AND NOT EXISTS (SELECT 1 FROM audit a
                        WHERE a.operation='delegation.invalidate' AND a.target_id=g.id);
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_grantor_role_remove
            AFTER DELETE ON membership_roles BEGIN
                INSERT OR IGNORE INTO delegation_events
                    (id,grant_id,event_type,actor_id,at)
                SELECT lower(hex(randomblob(16))),g.id,'invalidate','system',
                    (julianday('now') - 2440587.5) * 86400.0
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=OLD.user_id AND f.project_id=OLD.project_id;
                INSERT INTO audit
                SELECT lower(hex(randomblob(16))),(julianday('now') - 2440587.5) * 86400.0,
                    'system','delegation.invalidate',g.id,'ok'
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=OLD.user_id AND f.project_id=OLD.project_id
                    AND EXISTS (SELECT 1 FROM delegation_events e
                        WHERE e.grant_id=g.id AND e.event_type='invalidate')
                    AND NOT EXISTS (SELECT 1 FROM audit a
                        WHERE a.operation='delegation.invalidate' AND a.target_id=g.id);
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_grantor_role_update
            AFTER UPDATE OF permissions,denied_permissions ON roles BEGIN
                INSERT OR IGNORE INTO delegation_events
                    (id,grant_id,event_type,actor_id,at)
                SELECT lower(hex(randomblob(16))),g.id,'invalidate','system',
                    (julianday('now') - 2440587.5) * 86400.0
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                JOIN membership_roles mr ON mr.user_id=f.grantor_id
                    AND mr.project_id=f.project_id AND mr.role=OLD.id
                WHERE OLD.project_id=f.project_id;
                INSERT INTO audit
                SELECT lower(hex(randomblob(16))),(julianday('now') - 2440587.5) * 86400.0,
                    'system','delegation.invalidate',g.id,'ok'
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                JOIN membership_roles mr ON mr.user_id=f.grantor_id
                    AND mr.project_id=f.project_id AND mr.role=OLD.id
                WHERE OLD.project_id=f.project_id
                    AND EXISTS (SELECT 1 FROM delegation_events e
                        WHERE e.grant_id=g.id AND e.event_type='invalidate')
                    AND NOT EXISTS (SELECT 1 FROM audit a
                        WHERE a.operation='delegation.invalidate' AND a.target_id=g.id);
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_grantor_deny_update
            AFTER UPDATE OF denied_permissions ON memberships BEGIN
                INSERT OR IGNORE INTO delegation_events
                    (id,grant_id,event_type,actor_id,at)
                SELECT lower(hex(randomblob(16))),g.id,'invalidate','system',
                    (julianday('now') - 2440587.5) * 86400.0
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=NEW.user_id AND f.project_id=NEW.project_id
                    AND OLD.denied_permissions<>NEW.denied_permissions
                    AND NOT EXISTS (SELECT 1 FROM delegation_events e WHERE e.grant_id=g.id);
                INSERT INTO audit
                SELECT lower(hex(randomblob(16))),(julianday('now') - 2440587.5) * 86400.0,
                    'system','delegation.invalidate',g.id,'ok'
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=NEW.user_id AND f.project_id=NEW.project_id
                    AND EXISTS (SELECT 1 FROM delegation_events e
                        WHERE e.grant_id=g.id AND e.event_type='invalidate')
                    AND NOT EXISTS (SELECT 1 FROM audit a
                        WHERE a.operation='delegation.invalidate' AND a.target_id=g.id);
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_grantor_disable
            AFTER UPDATE OF enabled ON users WHEN OLD.enabled<>NEW.enabled AND NEW.enabled=0 BEGIN
                INSERT OR IGNORE INTO delegation_events
                    (id,grant_id,event_type,actor_id,at)
                SELECT lower(hex(randomblob(16))),g.id,'invalidate','system',
                    (julianday('now') - 2440587.5) * 86400.0
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=NEW.id
                    AND NOT EXISTS (SELECT 1 FROM delegation_events e WHERE e.grant_id=g.id);
                INSERT INTO audit
                SELECT lower(hex(randomblob(16))),(julianday('now') - 2440587.5) * 86400.0,
                    'system','delegation.invalidate',g.id,'ok'
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=NEW.id
                    AND EXISTS (SELECT 1 FROM delegation_events e
                        WHERE e.grant_id=g.id AND e.event_type='invalidate')
                    AND NOT EXISTS (SELECT 1 FROM audit a
                        WHERE a.operation='delegation.invalidate' AND a.target_id=g.id);
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_owner_change_invalidate
            AFTER UPDATE OF user_id ON project_owners BEGIN
                INSERT OR IGNORE INTO delegation_events
                    (id,grant_id,event_type,actor_id,at)
                SELECT lower(hex(randomblob(16))),g.id,'invalidate','system',
                    (julianday('now') - 2440587.5) * 86400.0
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=OLD.user_id AND f.project_id=OLD.project_id
                    AND NOT EXISTS (SELECT 1 FROM delegation_events e WHERE e.grant_id=g.id);
                INSERT INTO audit
                SELECT lower(hex(randomblob(16))),(julianday('now') - 2440587.5) * 86400.0,
                    'system','delegation.invalidate',g.id,'ok'
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=OLD.user_id AND f.project_id=OLD.project_id
                    AND EXISTS (SELECT 1 FROM delegation_events e
                        WHERE e.grant_id=g.id AND e.event_type='invalidate')
                    AND NOT EXISTS (SELECT 1 FROM audit a
                        WHERE a.operation='delegation.invalidate' AND a.target_id=g.id);
            END;
            CREATE TRIGGER IF NOT EXISTS delegation_owner_delete_invalidate
            AFTER DELETE ON project_owners BEGIN
                INSERT OR IGNORE INTO delegation_events
                    (id,grant_id,event_type,actor_id,at)
                SELECT lower(hex(randomblob(16))),g.id,'invalidate','system',
                    (julianday('now') - 2440587.5) * 86400.0
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=OLD.user_id AND f.project_id=OLD.project_id
                    AND NOT EXISTS (SELECT 1 FROM delegation_events e WHERE e.grant_id=g.id);
                INSERT INTO audit
                SELECT lower(hex(randomblob(16))),(julianday('now') - 2440587.5) * 86400.0,
                    'system','delegation.invalidate',g.id,'ok'
                FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id
                WHERE f.grantor_id=OLD.user_id AND f.project_id=OLD.project_id
                    AND EXISTS (SELECT 1 FROM delegation_events e
                        WHERE e.grant_id=g.id AND e.event_type='invalidate')
                    AND NOT EXISTS (SELECT 1 FROM audit a
                        WHERE a.operation='delegation.invalidate' AND a.target_id=g.id);
            END;
            CREATE TRIGGER IF NOT EXISTS membership_role_insert AFTER INSERT ON memberships
            BEGIN
                INSERT OR IGNORE INTO membership_roles (user_id,project_id,role)
                VALUES (NEW.user_id,NEW.project_id,NEW.role);
            END;
            CREATE TRIGGER IF NOT EXISTS membership_role_update AFTER UPDATE OF role ON memberships
            BEGIN
                DELETE FROM membership_roles
                WHERE user_id=NEW.user_id AND project_id=NEW.project_id AND role<>NEW.role;
                INSERT OR IGNORE INTO membership_roles (user_id,project_id,role)
                VALUES (NEW.user_id,NEW.project_id,NEW.role);
            END;
            CREATE TRIGGER IF NOT EXISTS membership_role_delete AFTER DELETE ON memberships
            BEGIN
                DELETE FROM membership_roles WHERE user_id=OLD.user_id
                    AND project_id=OLD.project_id;
            END;
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id),
                project_id TEXT REFERENCES projects(id), created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id),
                project_id TEXT REFERENCES projects(id), kind TEXT NOT NULL, name TEXT NOT NULL,
                content TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
                conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
                grants TEXT NOT NULL DEFAULT '[]', created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY, document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
                page INTEGER NOT NULL, ordinal INTEGER NOT NULL, text TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS storage_sources (
                id TEXT PRIMARY KEY, connector TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                configuration TEXT NOT NULL DEFAULT '{}', created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS source_objects (
                source_id TEXT NOT NULL, object_id TEXT NOT NULL, revision TEXT NOT NULL,
                permission_hash TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'unknown',
                observed_at REAL NOT NULL, PRIMARY KEY (source_id, object_id)
            );
            CREATE TABLE IF NOT EXISTS document_source_bindings (
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                source_id TEXT NOT NULL, object_id TEXT NOT NULL, revision TEXT NOT NULL,
                sync_state TEXT NOT NULL DEFAULT 'pending',
                PRIMARY KEY (document_id, source_id, object_id)
            );
            CREATE TABLE IF NOT EXISTS document_origins (
                document_id TEXT PRIMARY KEY,
                connector_id TEXT NOT NULL,
                external_id TEXT NOT NULL,
                external_revision TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL DEFAULT '',
                source_label TEXT NOT NULL DEFAULT '',
                synced_at REAL NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0,
                UNIQUE(connector_id, external_id)
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, conversation_id TEXT REFERENCES conversations(id)
                ON DELETE CASCADE, text TEXT NOT NULL, citation_ids TEXT NOT NULL,
                scope TEXT NOT NULL, created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS generated_answers (
                message_id TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
                answer TEXT NOT NULL, model TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_jobs (
                id TEXT PRIMARY KEY,
                conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL, text TEXT NOT NULL, scope TEXT NOT NULL,
                attachments TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '', message_id TEXT,
                created REAL NOT NULL, updated REAL NOT NULL,
                cancel_requested INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS audit (
                id TEXT PRIMARY KEY, at REAL NOT NULL, actor_id TEXT NOT NULL,
                operation TEXT NOT NULL, target_id TEXT NOT NULL, outcome TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_chain (
                audit_id TEXT PRIMARY KEY REFERENCES audit(id),
                seq INTEGER NOT NULL UNIQUE,
                prev_hash TEXT NOT NULL,
                row_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_chain_head (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                row_count INTEGER NOT NULL,
                head_hash TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS audit_no_update
            BEFORE UPDATE ON audit BEGIN
                SELECT RAISE(ABORT, 'audit rows are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS audit_no_delete
            BEFORE DELETE ON audit BEGIN
                SELECT RAISE(ABORT, 'audit rows are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS audit_chain_no_update
            BEFORE UPDATE ON audit_chain BEGIN
                SELECT RAISE(ABORT, 'audit chain rows are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS audit_chain_no_delete
            BEFORE DELETE ON audit_chain BEGIN
                SELECT RAISE(ABORT, 'audit chain rows are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS audit_chain_head_no_delete
            BEFORE DELETE ON audit_chain_head BEGIN
                SELECT RAISE(ABORT, 'audit chain head is retained');
            END;
            CREATE TRIGGER IF NOT EXISTS audit_chain_insert
            AFTER INSERT ON audit BEGIN
                INSERT INTO audit_chain (audit_id, seq, prev_hash, row_hash)
                SELECT
                    NEW.id,
                    COALESCE((SELECT row_count FROM audit_chain_head WHERE id = 1), 0) + 1,
                    COALESCE((SELECT head_hash FROM audit_chain_head WHERE id = 1), 'genesis'),
                    audit_sha256(
                        COALESCE((SELECT head_hash FROM audit_chain_head WHERE id = 1), 'genesis'),
                        NEW.id, NEW.at, NEW.actor_id, NEW.operation, NEW.target_id, NEW.outcome
                    );
                INSERT INTO audit_chain_head (id, row_count, head_hash)
                VALUES (1, 1, (SELECT row_hash FROM audit_chain WHERE audit_id = NEW.id))
                ON CONFLICT(id) DO UPDATE SET
                    row_count = row_count + 1,
                    head_hash = (SELECT row_hash FROM audit_chain WHERE audit_id = NEW.id);
            END;
            CREATE TABLE IF NOT EXISTS login_events (
                id TEXT PRIMARY KEY, at REAL NOT NULL,
                user_id TEXT, username_digest TEXT NOT NULL,
                outcome TEXT NOT NULL, peer TEXT NOT NULL, user_agent TEXT
            );
            CREATE TABLE IF NOT EXISTS login_throttle (
                user_id TEXT NOT NULL,
                failures INTEGER NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0,
                last_failure REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id)
            );
        """)
        chat_job_columns = self._engine.columns("chat_jobs")
        if "cancel_requested" not in chat_job_columns:
            self._engine.ensure_column(
                "chat_jobs", "cancel_requested", "INTEGER NOT NULL DEFAULT 0"
            )
        # Additive migrations preserve databases created before concurrent role holdings.
        self._engine.ensure_column(
            "memberships", "denied_permissions", "TEXT NOT NULL DEFAULT '[]'"
        )
        self._engine.ensure_column("roles", "denied_permissions", "TEXT NOT NULL DEFAULT '[]'")
        # Ingestion resume checkpoint (last fully indexed page) and a short,
        # non-sensitive failure category for the UI. Additive: old databases
        # keep working with a fresh checkpoint and no failure code.
        self._engine.ensure_column("documents", "index_checkpoint", "INTEGER NOT NULL DEFAULT 0")
        self._engine.ensure_column("documents", "failure_code", "TEXT NOT NULL DEFAULT ''")
        # Extraction sandbox kind ("docker" / "subprocess") and honest containment
        # guarantees recorded per ingested document (DATA-006 / design §4-§5).
        self._engine.ensure_column("documents", "sandbox", "TEXT NOT NULL DEFAULT ''")
        self._engine.ensure_column("documents", "sandbox_guarantees", "TEXT NOT NULL DEFAULT '{}'")
        self._engine.conn.execute(
            "INSERT OR IGNORE INTO membership_roles (user_id,project_id,role) "
            "SELECT user_id,project_id,role FROM memberships"
        )
        self._migrate_audit_chain()

    @property
    def lock(self) -> Any:
        """Write-serialization lock owned by the storage engine."""
        return self._engine.lock

    @property
    def conn(self) -> StorageConnection:
        """Read/write handle owned by the storage engine (``Service.conn`` compatibility)."""
        return self._engine.conn

    @contextmanager
    def db(self) -> Iterator[StorageConnection]:
        with self._engine.transaction():
            with self._engine.connection() as conn:
                # Include authorization SELECTs in the same write-serialized unit as publication.
                yield conn

    def recover_jobs(self) -> None:
        """Called only at application-worker startup, never by provisioning CLI connections."""
        with self.db() as db:
            # Both scanning and indexing are resumable: chunks completed before
            # the restart stay in place and the checkpoint lets indexing skip
            # them instead of inserting duplicates.
            db.execute(
                "UPDATE documents SET status='queued' WHERE status IN ('scanning','indexing')"
            )
            # An indexing failure is retried after a restart from its checkpoint.
            db.execute(
                "UPDATE documents SET status='queued',reason='',failure_code='' "
                "WHERE status='failed' AND failure_code='index_failed'"
            )
            # Queued dialogues were held only in this process; their dispatch closures
            # no longer exist after a restart, so they fail visibly instead of hanging.
            db.execute(
                "UPDATE chat_jobs SET status='failed',updated=?,detail=? "
                "WHERE status IN ('queued','running')",
                (time.time(), "アプリケーションの再起動により中止しました。再度送信してください"),
            )
            self.chat_dispatch.clear()

    def close(self) -> None:
        self._engine.close()

    def _register_audit_hash_function(self) -> None:
        # T-PH7-214: the audit_chain AFTER INSERT trigger calls audit_sha256.
        # Registration is per-connection; SQLite only (PostgreSQL uses a
        # different hash function path and is not implemented in this job).
        raw = getattr(getattr(self._engine, "conn", None), "raw", None)
        create_function = getattr(raw, "create_function", None)
        if callable(create_function):
            create_function("audit_sha256", 7, _audit_sha256_udf)

    def _migrate_audit_chain(self) -> None:
        """Backfill audit_chain for databases created before the chain existed.

        Runs once: if audit_chain_head already has a row the chain is left as-is.
        Existing audit rows are chained in (at, id) ascending order so the result
        is deterministic and immediately verifiable.
        """
        with self.db() as db:
            head = db.execute("SELECT row_count FROM audit_chain_head WHERE id = 1").fetchone()
            if head is not None:
                return
            rows = db.execute(
                "SELECT id, at, actor_id, operation, target_id, outcome "
                "FROM audit ORDER BY at ASC, id ASC"
            ).fetchall()
            if not rows:
                return
            prev_hash = AUDIT_CHAIN_GENESIS
            last_hash = prev_hash
            row_count = 0
            for seq, row in enumerate(rows, start=1):
                row_hash = _audit_hash_payload(
                    prev_hash,
                    row["id"],
                    row["at"],
                    row["actor_id"],
                    row["operation"],
                    row["target_id"],
                    row["outcome"],
                )
                db.execute(
                    "INSERT INTO audit_chain (audit_id, seq, prev_hash, row_hash) VALUES (?,?,?,?)",
                    (row["id"], seq, prev_hash, row_hash),
                )
                prev_hash = row_hash
                last_hash = row_hash
                row_count = seq
            db.execute(
                "INSERT INTO audit_chain_head (id, row_count, head_hash) VALUES (1, ?, ?)",
                (row_count, last_hash),
            )

    def _audit(
        self, db: StorageConnection, actor: str, operation: str, target: str, outcome: str = "ok"
    ) -> None:
        db.execute(
            "INSERT INTO audit VALUES (?,?,?,?,?,?)",
            (uid(), time.time(), actor, operation, target, outcome),
        )

    def provision(
        self,
        username: str,
        password: str,
        *,
        system_admin: bool = False,
        audit_actor: str = "local-cli",
    ) -> str:
        with self.db() as db:
            return self._provision(
                db, username, password, system_admin=system_admin, audit_actor=audit_actor
            )

    def _provision(
        self,
        db: StorageConnection,
        username: str,
        password: str,
        *,
        system_admin: bool = False,
        audit_actor: str,
    ) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{2,63}", username):
            fail(422, "利用者IDは3〜64文字の英数字・_.-で指定してください")
        ok, reason = check_password_strength(password, username)
        if not ok:
            # reason is str | None per type annotation, but check_password_strength
            # always returns a str when ok is False. Handle None defensively.
            if reason is None:
                fail(422, "パスワードの強さに問題があります")
            else:
                fail(422, reason)
        user_id = uid()
        try:
            db.execute(
                "INSERT INTO users VALUES (?,?,?,?,?,0,1,?)",
                (
                    user_id,
                    username,
                    PASSWORDS.hash(password),
                    1,
                    time.time() + 86400,
                    int(system_admin),
                ),
            )
        except StorageIntegrityError:
            fail(409, "利用者IDは使用済みです")
        self._audit(db, audit_actor, "account.provision", user_id)
        return user_id

    def provision_web_user(
        self, actor: Principal, username: str, *, session_token: str | None
    ) -> Json:
        with self.db() as db:
            # Bind authorization to the live session inside the serialized creation transaction.
            current = self._authenticate(db, session_token)
            if current.id != actor.id:
                fail(401, "ログインしてください")
            if not current.system_admin:
                fail(403, "管理権限が必要です")
            self._limit("admin-provision:" + current.id, 10)
            # Generate a temporary password that meets the strength rules:
            # 14-128 chars, 3+ of 4 character types, no user ID substring,
            # no 5+ repeated chars, no consecutive 5 ASCII chars.
            while True:
                temporary_password = secrets.token_urlsafe(24)
                ok, reason = check_password_strength(temporary_password, username)
                if ok:
                    break
            user_id = self._provision(db, username, temporary_password, audit_actor=current.id)
        return {
            "id": user_id,
            "username": username,
            "temporary_password": temporary_password,
            "must_rotate": True,
        }

    def create_project(
        self, org_id: str, project_id: str, name: str, *, owner_id: str | None = None
    ) -> None:
        with self.db() as db:
            db.execute("INSERT INTO projects VALUES (?,?,?)", (project_id, org_id, name))
            if owner_id:
                db.execute(
                    "INSERT INTO project_owners (project_id,user_id) VALUES (?,?)",
                    (project_id, owner_id),
                )
            self._audit(db, "local-cli", "project.create", project_id)

    def _replace_role_holding(
        self, db: StorageConnection, user_id: str, project_id: str, role: str
    ) -> None:
        db.execute(
            "DELETE FROM membership_roles WHERE user_id=? AND project_id=?",
            (user_id, project_id),
        )
        # An upsert here would override the OR IGNORE clauses of nested trigger
        # bodies (SQLite conflict-resolution override) and abort live delegation
        # invalidation with a spurious UNIQUE failure; update or insert explicitly.
        updated = db.execute(
            "UPDATE memberships SET role=? WHERE user_id=? AND project_id=?",
            (role, user_id, project_id),
        ).rowcount
        if not updated:
            db.execute(
                "INSERT INTO memberships (user_id,project_id,role) VALUES (?,?,?)",
                (user_id, project_id, role),
            )
        db.execute(
            "DELETE FROM membership_roles WHERE user_id=? AND project_id=?",
            (user_id, project_id),
        )
        db.execute(
            "INSERT INTO membership_roles (user_id,project_id,role) VALUES (?,?,?)",
            (user_id, project_id, role),
        )

    def assign(self, username: str, project_id: str, role: str | None) -> None:
        """Compatibility helper that replaces all role holdings with one role."""
        with self.db() as db:
            user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if not user:
                fail(404, "利用者が見つかりません")
            if not db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone():
                fail(404, "プロジェクトが見つかりません")
            if role is None:
                db.execute(
                    "DELETE FROM membership_roles WHERE user_id=? AND project_id=?",
                    (user["id"], project_id),
                )
                db.execute(
                    "DELETE FROM memberships WHERE user_id=? AND project_id=?",
                    (user["id"], project_id),
                )
                self._audit(db, "local-cli", "membership.remove", project_id + ":" + user["id"])
                return
            custom = db.execute(
                "SELECT id FROM roles WHERE id=? AND project_id=?", (role, project_id)
            ).fetchone()
            if role not in ROLE_PERMISSIONS and not custom:
                fail(422, "不明なロールです")
            self._replace_role_holding(db, user["id"], project_id, role)
            self._audit(db, "local-cli", "membership.assign", project_id + ":" + user["id"])

    def create_admin_project(
        self,
        token: str | None,
        project_id: str,
        org_id: str,
        name: str,
        owner_id: str | None = None,
    ) -> Json:
        if (
            not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", project_id)
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", org_id)
            or not name.strip()
            or len(name) > 128
            or any(ord(char) < 32 for char in name)
        ):
            fail(422, "プロジェクトID・組織ID・名称を確認してください")
        with self.db() as db:
            actor = self._authenticate(db, token)
            if not actor.system_admin:
                fail(403, "管理権限が必要です")
            self._limit("admin-project:" + actor.id, 10)
            try:
                db.execute("INSERT INTO projects VALUES (?,?,?)", (project_id, org_id, name))
                selected_owner_id = owner_id
                if selected_owner_id is not None:
                    owner = db.execute(
                        "SELECT enabled FROM users WHERE id=?", (selected_owner_id,)
                    ).fetchone()
                    if not owner or not owner["enabled"]:
                        fail(422, "有効な所有者を指定してください")
                    db.execute(
                        "INSERT INTO project_owners (project_id,user_id) VALUES (?,?)",
                        (project_id, selected_owner_id),
                    )
            except StorageIntegrityError:
                fail(409, "プロジェクトIDまたは所有者の指定を確認してください")
            self._audit(db, actor.id, "project.create", project_id)
            return {"id": project_id, "org_id": org_id, "name": name}

    def admin_projects(self, actor: Principal) -> list[Json]:
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        with self.db() as db:
            projects = [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY name,id")]
            for project in projects:
                project["members"] = [
                    {
                        **dict(row),
                        "roles": self._held_roles(db, row["user_id"], project["id"]),
                        "denied_permissions": json.loads(row["denied_permissions"]),
                        "delegated_permissions": sorted(
                            self._delegated_permissions(
                                db,
                                Principal(row["user_id"], row["username"], False, False),
                                project["id"],
                            )
                        ),
                        "effective_permissions": sorted(
                            self._permissions(
                                db,
                                Principal(row["user_id"], row["username"], False, False),
                                project["id"],
                            )
                        ),
                    }
                    for row in db.execute(
                        "SELECT u.id AS user_id,u.username,m.role,m.denied_permissions "
                        "FROM memberships m "
                        "JOIN users u ON u.id=m.user_id WHERE m.project_id=? ORDER BY u.username",
                        (project["id"],),
                    )
                ]
                project["roles"] = [
                    {"id": name, "name": name}
                    for name in ROLE_PERMISSIONS
                    if name != "system_admin"
                ] + [
                    {"id": row["id"], "name": row["name"]}
                    for row in db.execute(
                        "SELECT id,name FROM roles WHERE project_id=? ORDER BY name",
                        (project["id"],),
                    )
                ]
            return projects

    def storage_status(self, actor: Principal) -> Json:
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        with self.db() as db:
            counts = {
                row["status"]: row["count"]
                for row in db.execute(
                    "SELECT status,COUNT(*) AS count FROM documents GROUP BY status"
                )
            }
            return {
                "backend": "sqlite",
                "mode": "local-only",
                "external_enabled": False,
                "accepted_formats": accepted_format_names(),
                "max_file_bytes": max_content_bytes(),
                "scanner_configured": self.scanner_configured,
                "scanner_last_outcome": self.scanner_last_outcome,
                "ingestion_queue_limit": 32,
                "per_user_ingestion_queue_limit": 4,
                "ingestion_status_counts": counts,
                "configuration_available": False,
            }

    def register_sync_connector(
        self,
        connector_id: str,
        connector: Any,
        *,
        configured: bool | None = None,
    ) -> None:
        self.sync_connectors[connector_id] = connector
        if configured is not None:
            self.sync_connector_credentials_configured[connector_id] = bool(configured)
        elif connector_id not in self.sync_connector_credentials_configured:
            self.sync_connector_credentials_configured[connector_id] = False

    def admin_connectors(self, actor: Principal) -> list[Json]:
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        ids = set(self.sync_connector_credentials_configured) | set(self.sync_connectors)
        return [
            {
                "connector_id": connector_id,
                "configured": bool(
                    self.sync_connector_credentials_configured.get(connector_id, False)
                ),
            }
            for connector_id in sorted(ids)
        ]

    def sync_connector(
        self, actor: Principal, connector_id: str, project: str, source: str
    ) -> Json:
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        connector = self.sync_connectors.get(connector_id)
        if connector is None:
            fail(404, "コネクタが見つかりません")
        with self.db() as db:
            if not db.execute("SELECT 1 FROM projects WHERE id=?", (project,)).fetchone():
                fail(404, "プロジェクトが見つかりません")
        module = _sync_connectors_module()
        engine = module.SyncEngine(self)
        result = engine.sync(
            actor,
            project,
            connector,
            source_label=str(source),
            connector_id=connector_id,
        )
        with self.db() as db:
            self._audit(db, actor.id, "connector.sync", connector_id)
        # Return only aggregate counts; never include content or credentials.
        return {
            "connector_id": connector_id,
            "project_id": project,
            "registered": int(result.get("registered", 0)),
            "updated": int(result.get("updated", 0)),
            "skipped": int(result.get("skipped", 0)),
            "failed": int(result.get("failed", 0)),
        }

    def formats(self, actor: Principal) -> Json:
        """Accepted document formats, served from the single format table.

        The catalog is not project-scoped; it is read through the same actor
        machinery as the other read endpoints, so an authenticated caller sees
        the format table the upload and inventory paths enforce.
        """
        return {
            "formats": format_catalog(),
            "accepted_extensions": accepted_format_names(),
            "max_file_bytes": max_content_bytes(),
        }

    def source_connector_for(self, source_id: str) -> SourceConnector | None:
        return self.source_connectors.get(source_id)

    def set_source_interval_seconds(self, seconds: int) -> None:
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 1:
            fail(422, "ソース同期の巡回間隔は1以上の整数（秒）で指定してください")
        with self.db() as db:
            self._audit(db, "system", "source.interval", str(seconds))
        self.source_interval_seconds = seconds
        self.source_scheduler.interval_seconds = seconds

    def source_notify(self, source_id: str, actor_id: str) -> None:
        """Internal permission-change notification entry; the HTTP surface is a later task."""
        with self.db() as db:
            self._audit(db, actor_id, "source.notify", source_id)
        self.source_scheduler.notify(source_id)

    def source_cycle(self, source_id: str) -> bool:
        """One storage-source sync cycle; the worker loop drives this per source."""
        connector = self.source_connector_for(source_id)
        if connector is None:
            self.source_scheduler.mark_run(source_id)
            return False
        try:
            try:
                objects = connector.list_objects(source_id=source_id)
            except Exception:
                # Record the failed cycle; marking the run keeps a broken destination
                # from being retried on every worker tick (~0.25 s).
                with self.db() as db:
                    self._audit(db, "worker", "source.cycle", source_id, outcome="error")
                raise
            # Connector calls run outside the process-wide write transaction so a
            # slow destination cannot stall request handlers sharing self.lock.
            observations: list[tuple[SourceObject, str | None]] = []
            for obj in objects:
                try:
                    permission = connector.permission_hash(
                        source_id=source_id, object_id=obj.object_id
                    )
                except Exception:
                    permission = None
                observations.append((obj, permission))
            performed = False
            with self.db() as db:
                self._audit(db, "worker", "source.cycle", source_id)
                for obj, permission in observations:
                    if self._observe_source(db, source_id, obj, permission):
                        performed = True
                candidates: list[tuple[str, Any, Principal]] = []
                for binding in db.execute(
                    "SELECT b.document_id, b.source_id, b.object_id, b.revision AS bound_revision, "
                    "o.revision AS observed_revision, o.state "
                    "FROM document_source_bindings b "
                    "JOIN source_objects o ON o.source_id=b.source_id AND o.object_id=b.object_id "
                    "WHERE b.source_id=?",
                    (source_id,),
                ).fetchall():
                    document = db.execute(
                        "SELECT * FROM documents WHERE id=?", (binding["document_id"],)
                    ).fetchone()
                    if document is None:
                        continue
                    owner = db.execute(
                        "SELECT * FROM users WHERE id=?", (document["owner_id"],)
                    ).fetchone()
                    if owner is None:
                        continue
                    candidates.append(
                        (
                            str(document["id"]),
                            binding,
                            Principal(
                                str(owner["id"]),
                                str(owner["username"]),
                                bool(owner["system_admin"]),
                                bool(owner["must_rotate"]),
                            ),
                        )
                    )
            denied = [
                document_id
                for document_id, binding, owner_actor in candidates
                if not self._source_binding_allows(connector, binding, owner_actor)
            ]
            if denied:
                # Hide first in a committed transaction; chunk cleanup follows so a
                # cleanup failure can never create a readable window.
                with self.db() as db:
                    for document_id in denied:
                        self._hide_source_document(db, document_id)
                failure: Exception | None = None
                for document_id in denied:
                    try:
                        with self.db() as db:
                            self._cleanup_source_document(db, document_id)
                    except Exception as error:
                        with self.db() as db:
                            self._audit(db, "worker", "source.revoke", document_id, outcome="error")
                        if failure is None:
                            failure = error
                if failure is not None:
                    raise failure
            return performed
        finally:
            self.source_scheduler.mark_run(source_id)

    def source_ingest(
        self,
        actor: Principal,
        source_id: str,
        object_id: str,
        content: str,
        name: str,
        *,
        kind: str = "personal",
        grants: list[Json] | None = None,
        project: str,
    ) -> Json:
        """Ingest one source object into the local documents store (1:1 slice)."""
        document_format = format_for(name)
        if unsafe_document_name(name) or document_format is None:
            fail(422, "対応形式はUTF-8のtxt・md・csvです。安全なファイル名を指定してください")
        if (
            not content.strip()
            or len(content.encode("utf-8")) > document_format.max_bytes
            or any(ord(character) < 32 and character not in "\n\r\t\f" for character in content)
        ):
            fail(422, "本文は空でないUTF-8テキスト、256 KiB以内にしてください")
        if kind not in {"personal", "shared"}:
            fail(422, "ソース取り込み資料は個人資料または公開資料として登録してください")
        connector = self.source_connector_for(source_id)
        if connector is None:
            fail(422, "保存先が見つかりません")
        objects = connector.list_objects(source_id=source_id)
        obj = next((candidate for candidate in objects if candidate.object_id == object_id), None)
        if obj is None:
            fail(422, "保存先に対象オブジェクトが見つかりません")
        permission: str | None = None
        try:
            permission = connector.permission_hash(source_id=source_id, object_id=object_id)
        except Exception:
            permission = None
        effective_grants: list[Json] = (
            grants
            if grants is not None
            else (
                [{"role": "viewer", "operations": ["read", "retrieve"]}] if kind == "shared" else []
            )
        )
        with self.db() as db:
            self.require(db, actor, project, "upload")
            self._check_ingestion_limits(db, actor)
            effective_grants = self._validated_grants(db, project, effective_grants)
            document = uid()
            db.execute(
                "INSERT INTO documents "
                "(id,owner_id,project_id,kind,name,content,status,grants,created) "
                "VALUES (?,?,?,?,?,?,'queued',?,?)",
                (
                    document,
                    actor.id,
                    project,
                    kind,
                    name,
                    content,
                    json.dumps(effective_grants),
                    time.time(),
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO source_objects "
                "(source_id,object_id,revision,permission_hash,state,observed_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    source_id,
                    object_id,
                    obj.revision,
                    permission or "",
                    "ok" if permission is not None else "unavailable",
                    time.time(),
                ),
            )
            db.execute(
                "INSERT OR IGNORE INTO document_source_bindings "
                "(document_id,source_id,object_id,revision,sync_state) "
                "VALUES (?,?,?,?,'pending')",
                (document, source_id, object_id, obj.revision),
            )
            self._audit(db, actor.id, "source.ingest", document)
            return self._metadata(
                db.execute("SELECT * FROM documents WHERE id=?", (document,)).fetchone(), actor.id
            )

    def _observe_source(
        self,
        db: StorageConnection,
        source_id: str,
        obj: SourceObject,
        permission: str | None,
    ) -> bool:
        row = db.execute(
            "SELECT revision,permission_hash,state FROM source_objects "
            "WHERE source_id=? AND object_id=?",
            (source_id, obj.object_id),
        ).fetchone()
        permission_changed = row is not None and permission != row["permission_hash"]
        changed = row is None or permission_changed or str(obj.revision) != str(row["revision"])
        if changed:
            state = "ok" if permission is not None else "unavailable"
            if row is None:
                db.execute(
                    "INSERT INTO source_objects "
                    "(source_id,object_id,revision,permission_hash,state,observed_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (source_id, obj.object_id, obj.revision, permission or "", state, time.time()),
                )
            else:
                db.execute(
                    "UPDATE source_objects SET revision=?,permission_hash=?,state=?,observed_at=? "
                    "WHERE source_id=? AND object_id=?",
                    (obj.revision, permission or "", state, time.time(), source_id, obj.object_id),
                )
            if permission_changed:
                # Metadata only: the hash and object identity, never the ACL payload.
                self._audit(
                    db, "worker", "source.permission.change", f"{source_id}:{obj.object_id}"
                )
            self.source_scheduler.notify(source_id)
            return True
        return False

    @staticmethod
    def _source_binding_allows(connector: SourceConnector, binding: Any, actor: Principal) -> bool:
        """Evaluate a captured binding without holding the database transaction."""
        if str(binding["bound_revision"]) != str(binding["observed_revision"]):
            # Unknown or stale source state fails closed; staleness is never authorization.
            return False
        if binding["state"] != "ok":
            # An unavailable source must not authorize content either.
            return False
        try:
            allowed = connector.can_read(
                source_id=str(binding["source_id"]),
                object_id=str(binding["object_id"]),
                user_id=actor.username,
            )
        except Exception:
            # Connector failures are denials, never errors surfaced to readers.
            return False
        return allowed is True

    def _source_allows(self, db: StorageConnection, actor: Principal, row: Any) -> bool:
        """Original-source ACL gate. Reads binding/revision/state from db within transaction.
        Unbound documents pass; bound ones must pass the DB checks.
        connector.can_read() is called by the caller outside the transaction (DATA-008)."""
        binding = db.execute(
            "SELECT source_id,object_id,revision FROM document_source_bindings WHERE document_id=?",
            (row["id"],),
        ).fetchone()
        if not binding:
            return True
        source_object = db.execute(
            "SELECT revision,state FROM source_objects WHERE source_id=? AND object_id=?",
            (binding["source_id"], binding["object_id"]),
        ).fetchone()
        if not source_object or str(binding["revision"]) != str(source_object["revision"]):
            return False
        if source_object["state"] != "ok":
            return False
        return True

    def _source_connector_allows(self, db: StorageConnection, actor: Principal, row: Any) -> bool:
        """Check connector.can_read outside the process lock/tx, then re-verify.

        Must be called while holding self.lock inside self.db(). If a binding
        exists, this commits the current tx, releases self.lock for the
        connector call, then re-acquires the lock and begins a new tx before
        re-verifying that the binding/source state is unchanged. Fail-closed.
        """
        binding = db.execute(
            "SELECT source_id,object_id,revision FROM document_source_bindings WHERE document_id=?",
            (row["id"],),
        ).fetchone()
        if not binding:
            return True
        source_id = str(binding["source_id"])
        object_id = str(binding["object_id"])
        revision = str(binding["revision"])
        connector = self.source_connector_for(source_id)
        if connector is None:
            return False
        if self.conn.in_transaction:
            self.conn.commit()
        self.lock.release()
        try:
            try:
                allowed = connector.can_read(
                    source_id=source_id,
                    object_id=object_id,
                    user_id=actor.username,
                )
            except Exception:
                return False
            if allowed is not True:
                return False
        finally:
            self.lock.acquire()
            self.conn.execute("BEGIN IMMEDIATE")
        binding2 = db.execute(
            "SELECT b.source_id,b.object_id,b.revision,o.revision AS observed_revision,o.state "
            "FROM document_source_bindings b "
            "JOIN source_objects o ON o.source_id=b.source_id AND o.object_id=b.object_id "
            "WHERE b.document_id=?",
            (row["id"],),
        ).fetchone()
        if not binding2:
            return False
        if (
            str(binding2["source_id"]) != source_id
            or str(binding2["object_id"]) != object_id
            or str(binding2["revision"]) != revision
            or str(binding2["observed_revision"]) != revision
            or str(binding2["state"]) != "ok"
        ):
            # Fail closed: the binding identity may have changed while the connector
            # round-trip was in flight, so a stale verdict must never authorize.
            return False
        doc_state = db.execute(
            "SELECT status,failure_code FROM documents WHERE id=?",
            (row["id"],),
        ).fetchone()
        if doc_state and str(doc_state["failure_code"]) == "source_denied":
            return False
        return True

    def _hide_source_document(self, db: StorageConnection, document_id: str) -> None:
        """Make a revoked source document invisible before chunk cleanup runs."""
        changed = db.execute(
            "UPDATE documents SET status='failed',reason=?,failure_code='source_denied' "
            "WHERE id=? AND status IN ('queued','scanning','indexing','ready')",
            ("元保存先の利用権限が失効したため索引物を削除しました", document_id),
        ).rowcount
        if changed:
            self._audit(db, "worker", "source.revoke", document_id)

    def _cleanup_source_document(self, db: StorageConnection, document_id: str) -> None:
        """Delete source-derived chunks after a source revocation was observed."""
        db.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
        db.execute(
            "UPDATE documents SET status='failed',reason=?,failure_code='source_denied' "
            "WHERE id=? AND status='ready'",
            ("元保存先の利用権限が失効したため索引物を削除しました", document_id),
        )

    # --- Connector origin tracking (T-STC-001 common base) -----------------

    def get_document_origin(self, connector_id: str, external_id: str) -> Json | None:
        with self.db() as db:
            row = db.execute(
                "SELECT document_id,connector_id,external_id,external_revision,"
                "content_hash,source_label,synced_at,revoked "
                "FROM document_origins WHERE connector_id=? AND external_id=?",
                (connector_id, external_id),
            ).fetchone()
        if row is None:
            return None
        return {**dict(row), "revoked": bool(row["revoked"])}

    def get_document_origin_by_document(self, document_id: str) -> Json | None:
        with self.db() as db:
            row = db.execute(
                "SELECT document_id,connector_id,external_id,external_revision,"
                "content_hash,source_label,synced_at,revoked "
                "FROM document_origins WHERE document_id=?",
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return {**dict(row), "revoked": bool(row["revoked"])}

    def is_document_origin_revoked(self, document_id: str) -> bool:
        """Hook for read-path refusal integration (T-STC-005)."""
        origin = self.get_document_origin_by_document(document_id)
        return bool(origin and origin["revoked"])

    def record_document_origin(
        self,
        *,
        document_id: str,
        connector_id: str,
        external_id: str,
        external_revision: str,
        content_hash: str,
        source_label: str,
    ) -> None:
        with self.db() as db:
            existing = db.execute(
                "SELECT document_id FROM document_origins WHERE connector_id=? AND external_id=?",
                (connector_id, external_id),
            ).fetchone()
            now = time.time()
            if existing is None:
                db.execute(
                    "INSERT INTO document_origins "
                    "(document_id,connector_id,external_id,external_revision,content_hash,"
                    "source_label,synced_at,revoked) VALUES (?,?,?,?,?,?,?,0)",
                    (
                        document_id,
                        connector_id,
                        external_id,
                        external_revision,
                        content_hash,
                        source_label,
                        now,
                    ),
                )
            else:
                db.execute(
                    "UPDATE document_origins SET document_id=?,external_revision=?,content_hash=?,"
                    "source_label=?,synced_at=?,revoked=0 WHERE connector_id=? AND external_id=?",
                    (
                        document_id,
                        external_revision,
                        content_hash,
                        source_label,
                        now,
                        connector_id,
                        external_id,
                    ),
                )

    def revoke_missing_document_origins(
        self, connector_id: str, seen_external_ids: set[str]
    ) -> int:
        with self.db() as db:
            rows = db.execute(
                "SELECT external_id,revoked FROM document_origins WHERE connector_id=?",
                (connector_id,),
            ).fetchall()
            missing = [
                str(row["external_id"])
                for row in rows
                if not row["revoked"] and str(row["external_id"]) not in seen_external_ids
            ]
            if missing:
                db.executemany(
                    "UPDATE document_origins SET revoked=1,synced_at=? "
                    "WHERE connector_id=? AND external_id=?",
                    [(time.time(), connector_id, external_id) for external_id in missing],
                )
        return len(missing)

    def _project_member_mutation(
        self,
        db: StorageConnection,
        actor: Principal,
        project_id: str,
        user_id: str,
        role: str | None,
    ) -> Json:
        if not db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone():
            fail(404, "プロジェクトが見つかりません")
        target = db.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            fail(404, "利用者が見つかりません")
        if role is None:
            removed = (
                db.execute(
                    "DELETE FROM memberships WHERE user_id=? AND project_id=?",
                    (user_id, project_id),
                ).rowcount
                > 0
            )
            if removed:
                self._audit(db, actor.id, "membership.remove", project_id + ":" + user_id)
            return {"project_id": project_id, "user_id": user_id, "removed": removed}
        if role == "system_admin":
            fail(422, "システム管理者ロールは所属に設定できません")
        custom = db.execute(
            "SELECT id FROM roles WHERE id=? AND project_id=?", (role, project_id)
        ).fetchone()
        if role not in ROLE_PERMISSIONS and not custom:
            fail(422, "不明なロールです")
        if not db.execute("SELECT enabled FROM users WHERE id=?", (user_id,)).fetchone()[0]:
            fail(409, "無効な利用者は所属に追加できません")
        member_changed = db.execute(
            "INSERT OR IGNORE INTO memberships (user_id,project_id,role) VALUES (?,?,?)",
            (user_id, project_id, role),
        ).rowcount
        role_changed = db.execute(
            "INSERT OR IGNORE INTO membership_roles (user_id,project_id,role) VALUES (?,?,?)",
            (user_id, project_id, role),
        ).rowcount
        if member_changed or role_changed:
            self._audit(db, actor.id, "membership.assign", project_id + ":" + user_id)
        return {"project_id": project_id, "user_id": user_id, "role": role}

    def set_project_member(
        self, token: str | None, project_id: str, user_id: str, role: str
    ) -> Json:
        with self.db() as db:
            actor = self._authenticate(db, token)
            if not actor.system_admin:
                fail(403, "管理権限が必要です")
            self._limit("admin-project-member:" + actor.id, 30)
            return self._project_member_mutation(db, actor, project_id, user_id, role)

    def remove_project_member(self, token: str | None, project_id: str, user_id: str) -> None:
        with self.db() as db:
            actor = self._authenticate(db, token)
            if not actor.system_admin:
                fail(403, "管理権限が必要です")
            self._limit("admin-project-member:" + actor.id, 30)
            self._project_member_mutation(db, actor, project_id, user_id, None)

    def load_status(
        self,
        actor: Principal,
        *,
        model_busy: int,
        model_slots: int,
        model_enabled: bool,
    ) -> Json:
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        with self.db() as db:
            queued = db.execute("SELECT COUNT(*) FROM chat_jobs WHERE status='queued'").fetchone()[
                0
            ]
            queued_per_user = [
                row[0]
                for row in db.execute(
                    "SELECT COUNT(*) FROM chat_jobs WHERE status='queued' "
                    "GROUP BY user_id ORDER BY COUNT(*) DESC"
                ).fetchall()
            ]
            running = db.execute(
                "SELECT j.id,u.username,j.updated FROM chat_jobs j "
                "LEFT JOIN users u ON u.id=j.user_id WHERE j.status='running' "
                "ORDER BY j.created,j.id LIMIT 1"
            ).fetchone()
            oldest_queued = db.execute(
                "SELECT MIN(created) FROM chat_jobs WHERE status='queued'"
            ).fetchone()[0]
            return {
                "model_slot": {
                    "enabled": model_enabled,
                    "busy": model_busy,
                    "total": model_slots,
                },
                "chat_queue": {
                    "queued": queued,
                    "limit": CHAT_QUEUE_LIMIT,
                    "per_user_limit": CHAT_USER_QUEUE_LIMIT,
                    "wait_deadline_seconds": CHAT_WAIT_SECONDS,
                    "queued_per_user": queued_per_user,
                    "oldest_queued_wait_seconds": (
                        time.time() - oldest_queued if oldest_queued is not None else 0
                    ),
                    "running_job": (
                        {
                            "id": running["id"],
                            "username": running["username"],
                            "started_at": running["updated"],
                        }
                        if running
                        else None
                    ),
                },
            }

    def _limit(self, key: str, maximum: int) -> None:
        now = time.time()
        recent = [at for at in self.limits.pop(key, []) if at > now - 60]
        if len(recent) >= maximum:
            self.limits[key] = recent
            fail(429, "試行回数が多いため、1分後に再試行してください")
        recent.append(now)
        self.limits[key] = recent
        while len(self.limits) > 1024:
            self.limits.popitem(last=False)

    def _session(self, db: StorageConnection, user_id: str, rotation: bool) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        db.execute("DELETE FROM sessions WHERE expires < ? OR last_seen < ?", (now, now - 1800))
        db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?)",
            (digest(token), user_id, now + 28800, now, int(rotation)),
        )
        return token

    def login(
        self,
        username: str,
        password: str,
        peer: str,
        user_agent: str | None = None,
    ) -> tuple[str, Json]:
        """Record a login event before either succeeding or failing.

        Outcomes (ordered by check priority):
          'unknown_user'   – no such account
          'disabled'       – account is disabled
          'locked'         – account is under login lock
          'temp_expired'   – must-rotate temp password has expired
          'bad_password'   – password does not match
          'success'        – all checks pass
        The event is written with db.execute() + explicit commit so it persists
        even when the subsequent fail(401) raises HTTPException.
        """
        with self.db() as db:
            # Instant burst limits (60s window) remain in memory.
            self._limit("peer:" + peer, 20)
            self._limit("user:" + digest(username), 5)

            now = time.time()
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

            # Determine outcome (ordered by check priority).
            outcome: str | None = None
            throttle_key = user["id"] if user is not None else digest(username)

            # Check throttle lock (absolute deadline, auto-expires).
            row = db.execute(
                "SELECT failures, locked_until, last_failure FROM login_throttle WHERE user_id=?",
                (throttle_key,),
            ).fetchone()
            failures = int(row["failures"]) if row else 0
            locked_until = float(row["locked_until"]) if row else 0.0

            if row and locked_until > now:
                outcome = "locked"

            # Unknown account.
            if user is None and outcome is None:
                outcome = "unknown_user"

            # Disabled account.
            if user is not None and not user["enabled"] and outcome is None:
                outcome = "disabled"

            # Expired temporary password.
            if (
                user is not None
                and outcome is None
                and user["must_rotate"]
                and (user["temp_used"] or float(user["temp_expires"]) < now)
            ):
                outcome = "temp_expired"

            # Password verification (always performed to avoid leaking account existence).
            valid = False
            if user is not None:
                try:
                    valid = PASSWORDS.verify(user["password_hash"], password)
                except VerificationError:
                    valid = False
            else:
                try:
                    PASSWORDS.verify(self.dummy_hash, password)
                except VerificationError:
                    pass

            if outcome is None and not valid:
                outcome = "bad_password"

            # Success if nothing else matched.
            if outcome is None:
                outcome = "success"

            # Record the login event before any fail()/return.
            # user_id: known account ID, or NULL for unknown_user.
            # username_digest is always stored as digest(username) (never raw input).
            # user_agent is capped at 256 chars; NULL when absent.
            # Persisted before fail(401) with an explicit commit so the row survives
            # the HTTPException that exits the db() context.
            ua = user_agent[:256] if user_agent else None
            db.execute(
                "INSERT INTO login_events VALUES (?,?,?,?,?,?,?)",
                (
                    uid(),
                    now,
                    throttle_key if user is not None else None,
                    digest(username),
                    outcome,
                    peer,
                    ua,
                ),
            )
            # Retention pruning: delete rows older than the 1-year window.
            # Scoped to login_events only; no other table is auto-deleted.
            cutoff = now - LOGIN_HISTORY_RETENTION_SECONDS
            db.execute("DELETE FROM login_events WHERE at < ?", (cutoff,))
            db.commit()

            if outcome == "success":
                # Successful login resets long-term failure tracking.
                db.execute(
                    "INSERT OR REPLACE INTO login_throttle "
                    "(user_id, failures, locked_until, last_failure) VALUES (?,?,?,?)",
                    (throttle_key, 0, 0.0, now),
                )
                if user["must_rotate"]:
                    db.execute("UPDATE users SET temp_used=1 WHERE id=?", (user["id"],))
                token = self._session(db, user["id"], bool(user["must_rotate"]))
                self._audit(db, user["id"], "session.start", user["id"])
                return token, self._public_user(user)

            # Already-locked attempts must not extend the lock (T-PH7-221).
            if outcome == "locked":
                fail(401, "利用者IDまたはパスワードを確認してください")

            # Failed login: increment failures; apply a fixed-duration lock at threshold.
            failures += 1
            if failures >= LOCK_FAILURE_THRESHOLD:
                locked_until = now + LOCK_DURATION_SECONDS
            else:
                locked_until = 0.0
            last_failure = now
            db.execute(
                "INSERT OR REPLACE INTO login_throttle "
                "(user_id, failures, locked_until, last_failure) VALUES (?,?,?,?)",
                (throttle_key, failures, locked_until, last_failure),
            )
            db.commit()
            # Do not expose whether the account exists, password was wrong, or account is locked.
            fail(401, "利用者IDまたはパスワードを確認してください")

    @staticmethod
    def _public_user(user: Any) -> Json:
        return {
            "id": user["id"],
            "username": user["username"],
            "system_admin": bool(user["system_admin"]),
            "must_rotate": bool(user["must_rotate"]),
        }

    def authenticate(self, token: str | None, *, allow_rotation: bool = False) -> Principal:
        with self.db() as db:
            return self._authenticate(db, token, allow_rotation=allow_rotation)

    def _authenticate(
        self, db: StorageConnection, token: str | None, *, allow_rotation: bool = False
    ) -> Principal:
        session = db.execute(
            "SELECT s.*, u.username,u.system_admin,u.must_rotate,u.enabled "
            "FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=?",
            (digest(token or ""),),
        ).fetchone()
        now = time.time()
        if (
            not session
            or not session["enabled"]
            or session["expires"] <= now
            or (session["last_seen"] <= now - 1800)
        ):
            fail(401, "ログインしてください")
        if (session["rotation_only"] or session["must_rotate"]) and not allow_rotation:
            fail(403, "最初に仮パスワードを変更してください")
        db.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, digest(token or "")))
        return Principal(
            session["user_id"],
            session["username"],
            bool(session["system_admin"]),
            bool(session["must_rotate"]),
        )

    def rotate(
        self, principal: Principal, current: str, new: str, *, session_token: str | None = None
    ) -> str:
        self._limit("rotate:" + principal.id, 5)
        with self.db() as db:
            if session_token is not None:
                session_actor = self._authenticate(db, session_token, allow_rotation=True)
                if session_actor.id != principal.id:
                    fail(401, "ログインしてください")
            user = db.execute("SELECT * FROM users WHERE id=?", (principal.id,)).fetchone()
            if not user or not user["enabled"]:
                fail(401, "ログインしてください")

            username = user["username"]
            ok, reason = check_password_strength(new, username)
            if not ok:
                # reason is str | None per type annotation, but check_password_strength
                # always returns a str when ok is False. Handle None defensively.
                if reason is None:
                    fail(422, "パスワードの強さに問題があります")
                else:
                    fail(422, reason)
            if len(current) < 14 or len(current) > 128 or current == new:
                fail(422, "異なる14〜128文字のパスワードを設定してください")

            try:
                PASSWORDS.verify(user["password_hash"], current)
            except VerificationError:
                fail(401, "現在のパスワードを確認してください")

            now = time.time()
            if (
                user["must_rotate"]
                and user["temp_expires"] is not None
                and user["temp_expires"] <= now
            ):
                fail(401, "仮パスワードが失効しています。ローカル管理者へ連絡してください")

            db.execute(
                "UPDATE users SET password_hash=?,must_rotate=0,temp_expires=NULL WHERE id=?",
                (PASSWORDS.hash(new), principal.id),
            )
            db.execute("DELETE FROM sessions WHERE user_id=?", (principal.id,))
            token = self._session(db, principal.id, False)
            self._audit(db, principal.id, "credential.rotate", principal.id)
            return token

    def issue_recovery(self, username: str) -> str:
        code = secrets.token_urlsafe(32)
        with self.db() as db:
            user = db.execute(
                "SELECT id,enabled FROM users WHERE username=?", (username,)
            ).fetchone()
            if not user:
                fail(404, "利用者が見つかりません")
            if not user["enabled"]:
                fail(409, "無効な利用者には回復コードを発行できません")
            db.execute(
                "INSERT OR REPLACE INTO recovery_codes (user_id,code_hash,expires,used) "
                "VALUES (?,?,?,0)",
                (user["id"], digest(code), time.time() + 86400),
            )
            self._audit(db, "local-cli", "credential.recovery.issue", user["id"])
        return code

    def recover(self, username: str, code: str, new_password: str) -> None:
        with self.db() as db:
            self._limit("recovery:" + digest(username), 5)
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            recovery = db.execute(
                "SELECT * FROM recovery_codes WHERE user_id=?", (user["id"] if user else "",)
            ).fetchone()
            matches = secrets.compare_digest(
                recovery["code_hash"] if recovery else "0" * 64, digest(code)
            )
            now = time.time()
            if (
                not user
                or not recovery
                or not matches
                or recovery["used"]
                or recovery["expires"] <= now
                or not user["enabled"]
            ):
                fail(401, "利用者IDまたは回復コードを確認してください")
            ok, reason = check_password_strength(new_password, username)
            if not ok:
                # reason is str | None per type annotation, but check_password_strength
                # always returns a str when ok is False. Handle None defensively.
                if reason is None:
                    fail(422, "パスワードの強さに問題があります")
                else:
                    fail(422, reason)
            try:
                PASSWORDS.verify(user["password_hash"], new_password)
            except VerificationError:
                pass
            else:
                fail(422, "異なる14〜128文字のパスワードを設定してください")
            db.execute(
                "UPDATE users SET password_hash=?,must_rotate=0,temp_used=0,temp_expires=NULL "
                "WHERE id=?",
                (PASSWORDS.hash(new_password), user["id"]),
            )
            db.execute(
                "UPDATE recovery_codes SET used=1,expires=? WHERE user_id=?",
                (now, user["id"]),
            )
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            self._audit(db, "recovery", "credential.recover", user["id"])

    def unlock(self, user_id: str, *, actor: Principal) -> None:
        """Admin unlock of a user's login lockout.

        Clears the lock immediately; the caller must be system_admin.
        Records the action in _audit.
        """
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        with self.db() as db:
            db.execute(
                "UPDATE login_throttle SET locked_until=0, failures=0 WHERE user_id=?",
                (user_id,),
            )
            self._audit(db, actor.id, "account.unlock", user_id)

    def inventory(
        self, actor: Principal, project: str, candidates: list[dict[str, int | str]]
    ) -> Json:
        """Report, before anything is uploaded, what each candidate would do.

        Each candidate is ``{"name": str, "size": int}`` — a name and a byte
        count. The body is never sent, so nothing here can read, store or index
        a document's content.

        Every verdict comes from the same rules and the same bounds `upload`
        enforces, so the report cannot drift from the write path:

        - ``accepted`` — would be queued
        - ``invalid_name`` — unsafe, empty, over-long or dot-leading name
        - ``unsupported_format`` — extension outside the accepted text formats
        - ``too_large`` — byte count over the per-document bound
        - ``queue_full`` — the global or the owner's in-flight bound is reached
        - ``limit_reached`` — the global or the owner's document count is reached

        An actor without `upload` permission for the project is refused outright
        rather than receiving a per-candidate verdict: the project is the unit the
        permission applies to (acceptance criterion 3). The task definition also
        lists a ``not_permitted`` candidate status, which cannot occur under that
        rule; the refusal is the behaviour and the status is not reported.

        The inventory itself writes nothing: no document, chunk, message or audit
        row is created for it. It deliberately authorizes through the shared
        `require` path, which maintains its own delegation-expiry bookkeeping
        exactly as it does for any other authorized read; bypassing that path to
        keep this method write-free would duplicate authorization logic, which is
        the more dangerous trade.
        """
        with self.db() as db:
            # Deny by default, through the one authorization path.
            self.require(db, actor, project, "upload")
            # Snapshots only; the counts can move before an actual upload, which
            # is why a verdict is a report and not a reservation.
            queued = db.execute(
                "SELECT COUNT(*) FROM documents WHERE status IN ('queued','scanning','indexing')"
            ).fetchone()[0]
            personal_queued = db.execute(
                "SELECT COUNT(*) FROM documents WHERE owner_id=? AND status "
                "IN ('queued','scanning','indexing')",
                (actor.id,),
            ).fetchone()[0]
            total_docs = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            personal_docs = db.execute(
                "SELECT COUNT(*) FROM documents WHERE owner_id=?", (actor.id,)
            ).fetchone()[0]

            reasons = (
                "accepted",
                "invalid_name",
                "unsupported_format",
                "too_large",
                "queue_full",
                "limit_reached",
            )
            counted = dict.fromkeys(reasons, 0)
            reported: list[Json] = []
            total_bytes = 0
            for candidate in candidates:
                name = str(candidate["name"])
                size = int(candidate["size"])
                total_bytes += size
                # The first failing rule is the reported reason, in the order
                # `upload` applies them.
                document_format = format_for(name)
                if unsafe_document_name(name):
                    reason = "invalid_name"
                elif document_format is None:
                    reason = "unsupported_format"
                elif size > document_format.max_bytes:
                    reason = "too_large"
                elif queued >= IN_FLIGHT_LIMIT or personal_queued >= OWNER_IN_FLIGHT_LIMIT:
                    reason = "queue_full"
                elif total_docs >= DOCUMENT_LIMIT or personal_docs >= OWNER_DOCUMENT_LIMIT:
                    reason = "limit_reached"
                else:
                    reason = "accepted"
                counted[reason] += 1
                reported.append({"name": name, "status": reason})

            return {
                "inventory": reported,
                "summary": {
                    "total": len(candidates),
                    "total_bytes": total_bytes,
                    "by_reason": counted,
                },
            }

    def logout(self, token: str | None) -> None:
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token or ""),))

    def _membership(self, db: StorageConnection, actor: Principal, project: str) -> Any:
        row = db.execute(
            "SELECT m.*,p.org_id,p.name FROM memberships m JOIN projects p "
            "ON p.id=m.project_id WHERE m.user_id=? AND m.project_id=?",
            (actor.id, project),
        ).fetchone()
        if not row:
            fail(404, "対象が見つかりません")
        return row

    def _held_roles(self, db: StorageConnection, user_id: str, project: str) -> list[str]:
        rows = db.execute(
            "SELECT role FROM membership_roles WHERE user_id=? AND project_id=? ORDER BY role",
            (user_id, project),
        ).fetchall()
        # Legacy memberships are copied into this table during startup migration. An empty
        # normalized set therefore stays permissionless rather than resurrecting stale roles.
        return [row["role"] for row in rows]

    def _role_permissions(
        self, db: StorageConnection, role: str, project: str
    ) -> tuple[frozenset[str], frozenset[str]]:
        if role in ROLE_PERMISSIONS:
            return ROLE_PERMISSIONS[role], frozenset()
        row = db.execute(
            "SELECT permissions,denied_permissions FROM roles WHERE id=? AND project_id=?",
            (role, project),
        ).fetchone()
        if not row:
            return frozenset(), frozenset()
        return frozenset(json.loads(row["permissions"])), frozenset(
            json.loads(row["denied_permissions"])
        )

    def _role_access(
        self, db: StorageConnection, user_id: str, project: str
    ) -> tuple[set[str], set[str], set[str]]:
        membership = db.execute(
            "SELECT denied_permissions FROM memberships WHERE user_id=? AND project_id=?",
            (user_id, project),
        ).fetchone()
        if not membership:
            fail(404, "対象が見つかりません")
        roles = self._held_roles(db, user_id, project)
        allowed: set[str] = set()
        denied: set[str] = set(json.loads(membership["denied_permissions"]))
        for role in roles:
            role_allowed, role_denied = self._role_permissions(db, role, project)
            allowed.update(role_allowed)
            denied.update(role_denied)
        return allowed, denied, set(roles)

    def _delegation_authority(
        self,
        db: StorageConnection,
        grantor_id: str,
        project: str,
        permissions: set[str],
    ) -> bool:
        try:
            user = db.execute("SELECT enabled FROM users WHERE id=?", (grantor_id,)).fetchone()
            if not user or not user["enabled"]:
                return False
            allowed, denied, roles = self._role_access(db, grantor_id, project)
            ceiling = self._permission_ceiling_for_grantor(db, grantor_id, project)
        except (HTTPException, StorageError, ValueError, TypeError):
            return False
        owner = db.execute(
            "SELECT 1 FROM project_owners WHERE project_id=? AND user_id=?",
            (project, grantor_id),
        ).fetchone()
        # Organization-admin authority is represented by an explicit role holding
        # on the target project in this prototype; there is no org-wide grant path.
        grant_authority = bool(owner or "organization_admin" in roles)
        return bool(
            grant_authority
            and (owner or "manage_roles" in (allowed - denied))
            and permissions <= NON_ADMIN
            and permissions <= ceiling
            and permissions <= (allowed - denied)
            and not ("retrieve" in permissions and "read" not in permissions)
        )

    def _delegation_now(self) -> float:
        """Delegation clock boundary; Unix epoch seconds in the SQLite prototype."""
        return time.time()

    def _valid_delegation_now(self) -> float | None:
        try:
            now = self._delegation_now()
        except Exception:
            return None
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(now)
            or now < 0
        ):
            return None
        return float(now)

    def _delegated_permissions(
        self, db: StorageConnection, actor: Principal, project: str
    ) -> set[str]:
        try:
            user = db.execute("SELECT enabled FROM users WHERE id=?", (actor.id,)).fetchone()
        except (StorageError, ValueError, TypeError):
            return set()
        if not user or not user["enabled"]:
            return set()
        try:
            grants = db.execute(
                "SELECT g.id,g.expires,g.permissions,f.grantor_id "
                "FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id "
                "WHERE f.recipient_id=? AND f.project_id=? AND g.version=("
                "SELECT MAX(current.version) FROM delegation_grants current "
                "WHERE current.family_id=g.family_id) ORDER BY g.id",
                (actor.id, project),
            ).fetchall()
            now = self._valid_delegation_now()
            if now is None:
                return set()
        except (StorageError, ValueError, TypeError, OverflowError):
            return set()
        permissions: set[str] = set()
        for grant in grants:
            events = db.execute(
                "SELECT event_type FROM delegation_events WHERE grant_id=?",
                (grant["id"],),
            ).fetchall()
            if events:
                continue
            try:
                expires = float(grant["expires"])
                granted = set(json.loads(grant["permissions"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                invalidated = db.execute(
                    "INSERT OR IGNORE INTO delegation_events "
                    "(id,grant_id,event_type,actor_id,at) VALUES (?,?,?,?,?)",
                    (uid(), grant["id"], "invalidate", "system", now),
                ).rowcount
                if invalidated:
                    self._audit(db, "system", "delegation.invalidate", grant["id"])
                continue
            if not math.isfinite(expires) or now >= expires:
                inserted = db.execute(
                    "INSERT OR IGNORE INTO delegation_events "
                    "(id,grant_id,event_type,actor_id,at) VALUES (?,?,?,?,?)",
                    (uid(), grant["id"], "expire", "system", now),
                ).rowcount
                if inserted:
                    self._audit(db, "system", "delegation.expire", grant["id"])
                continue
            if self._delegation_authority(db, grant["grantor_id"], project, granted):
                permissions.update(granted)
            else:
                invalidated = db.execute(
                    "INSERT OR IGNORE INTO delegation_events "
                    "(id,grant_id,event_type,actor_id,at) VALUES (?,?,?,?,?)",
                    (uid(), grant["id"], "invalidate", "system", now),
                ).rowcount
                if invalidated:
                    self._audit(db, "system", "delegation.invalidate", grant["id"])
        return permissions

    def _permissions(self, db: StorageConnection, actor: Principal, project: str) -> frozenset[str]:
        allowed, denied, _roles = self._role_access(db, actor.id, project)
        allowed.update(self._delegated_permissions(db, actor, project))
        # Explicit deny wins over every role and delegation allow. Membership is still
        # independently required by _role_access, even when a grant otherwise matches.
        effective = allowed - denied
        if "read" not in effective:
            effective.discard("retrieve")
        return frozenset(effective)

    def _permission_ceiling(
        self, db: StorageConnection, actor: Principal, project: str
    ) -> frozenset[str]:
        """Permissions that a non-admin custom role may grant to other users."""
        membership = self._membership(db, actor, project)
        roles = self._held_roles(db, actor.id, project)
        if not roles:
            return frozenset()
        # A delegated role must be a subset of EACH held role's ceiling. Intersection is
        # intentional: union here would let complementary roles manufacture a new authority.
        ceilings = []
        for role in roles:
            allowed, denied = self._role_permissions(db, role, project)
            ceilings.append((allowed - denied) & NON_ADMIN)
        ceiling = set(ceilings[0])
        for permissions in ceilings[1:]:
            ceiling.intersection_update(permissions)
        ceiling.difference_update(json.loads(membership["denied_permissions"]))
        return frozenset(ceiling)

    def _held_permission_ceiling(
        self, db: StorageConnection, actor: Principal, project: str
    ) -> frozenset[str]:
        """Intersection of held roles' own permissions; never union for delegation."""
        membership = self._membership(db, actor, project)
        roles = self._held_roles(db, actor.id, project)
        if not roles:
            return frozenset()
        ceilings = []
        for role in roles:
            allowed, denied = self._role_permissions(db, role, project)
            ceilings.append(allowed - denied)
        ceiling = set(ceilings[0])
        for permissions in ceilings[1:]:
            ceiling.intersection_update(permissions)
        ceiling.difference_update(json.loads(membership["denied_permissions"]))
        return frozenset(ceiling)

    def add_role_holding(self, actor: Principal, project: str, username: str, role: str) -> None:
        with self.db() as db:
            if not db.execute("SELECT 1 FROM projects WHERE id=?", (project,)).fetchone():
                fail(404, "プロジェクトが見つかりません")
            if not actor.system_admin:
                self.require(db, actor, project, "manage_members")
                self._membership(db, actor, project)
            target = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if not target:
                fail(404, "利用者が見つかりません")
            enabled = db.execute(
                "SELECT enabled FROM users WHERE id=?", (target["id"],)
            ).fetchone()[0]
            if not enabled:
                fail(409, "無効な利用者にはロールを割り当てられません")
            if role == "system_admin":
                fail(422, "システム管理者ロールは所属に設定できません")
            allowed, denied = self._role_permissions(db, role, project)
            if (
                role not in ROLE_PERMISSIONS
                and not db.execute(
                    "SELECT 1 FROM roles WHERE id=? AND project_id=?", (role, project)
                ).fetchone()
            ):
                fail(404, "ロールが見つかりません")
            if (
                (
                    not actor.system_admin
                    and (
                        not allowed <= NON_ADMIN
                        or not allowed <= self._held_permission_ceiling(db, actor, project)
                    )
                )
                or (actor.system_admin and not allowed <= NON_ADMIN)
                or not denied <= ALL_PERMISSIONS
            ):
                fail(422, "ロールの権限が本人の非管理委任上限を超えています")
            db.execute(
                "INSERT OR IGNORE INTO membership_roles (user_id,project_id,role) VALUES (?,?,?)",
                (target["id"], project, role),
            )
            db.execute(
                "INSERT OR IGNORE INTO memberships (user_id,project_id,role) VALUES (?,?,?)",
                (target["id"], project, role),
            )
            self._audit(db, actor.id, "membership.role.assign", project + ":" + target["id"])

    def remove_role_holding(self, actor: Principal, project: str, username: str, role: str) -> None:
        with self.db() as db:
            if not db.execute("SELECT 1 FROM projects WHERE id=?", (project,)).fetchone():
                fail(404, "プロジェクトが見つかりません")
            if not actor.system_admin:
                self.require(db, actor, project, "manage_members")
            target = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if not target:
                fail(404, "利用者が見つかりません")
            deleted = db.execute(
                "DELETE FROM membership_roles WHERE user_id=? AND project_id=? AND role=?",
                (target["id"], project, role),
            ).rowcount
            if not deleted:
                fail(404, "ロール所属が見つかりません")
            remaining = self._held_roles(db, target["id"], project)
            if remaining:
                db.execute(
                    "UPDATE memberships SET role=? WHERE user_id=? AND project_id=?",
                    (remaining[0], target["id"], project),
                )
                db.executemany(
                    "INSERT OR IGNORE INTO membership_roles (user_id,project_id,role) "
                    "VALUES (?,?,?)",
                    ((target["id"], project, held_role) for held_role in remaining),
                )
            else:
                db.execute(
                    "DELETE FROM memberships WHERE user_id=? AND project_id=?",
                    (target["id"], project),
                )
            self._audit(db, actor.id, "membership.role.remove", project + ":" + target["id"])

    def set_membership_denials(
        self, actor: Principal, project: str, username: str, denied_permissions: list[str]
    ) -> list[str]:
        with self.db() as db:
            if not db.execute("SELECT 1 FROM projects WHERE id=?", (project,)).fetchone():
                fail(404, "プロジェクトが見つかりません")
            if not actor.system_admin:
                self.require(db, actor, project, "manage_members")
            target = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if (
                not target
                or not db.execute(
                    "SELECT 1 FROM memberships WHERE user_id=? AND project_id=?",
                    (target["id"] if target else "", project),
                ).fetchone()
            ):
                fail(404, "所属が見つかりません")
            if not set(denied_permissions) <= ALL_PERMISSIONS:
                fail(422, "不明な権限です")
            normalized = sorted(set(denied_permissions))
            db.execute(
                "UPDATE memberships SET denied_permissions=? WHERE user_id=? AND project_id=?",
                (json.dumps(normalized), target["id"], project),
            )
            self._audit(db, actor.id, "membership.deny.update", project + ":" + target["id"])
            return normalized

    def _permission_ceiling_for_grantor(
        self, db: StorageConnection, grantor_id: str, project: str
    ) -> frozenset[str]:
        """Apply concurrent-role ceilings independently of the active holding union."""
        roles = self._role_access(db, grantor_id, project)[2]
        if not roles:
            return frozenset()
        permissions = self._permission_ceiling(db, Principal(grantor_id, "", False, False), project)
        ceilings = []
        for role in roles:
            allowed, denied = self._role_permissions(db, role, project)
            ceilings.append((allowed - denied) & NON_ADMIN)
        ceiling = set(ceilings[0])
        for role_ceiling in ceilings[1:]:
            ceiling.intersection_update(role_ceiling)
        membership = self._membership(db, Principal(grantor_id, "", False, False), project)
        ceiling.difference_update(json.loads(membership["denied_permissions"]))
        return frozenset(ceiling) & permissions

    def create_delegation(
        self,
        actor: Principal,
        session_token: str | None,
        project: str,
        recipient_id: str,
        permissions: list[str],
        ttl_seconds: int | None = None,
    ) -> Json:
        ttl = 86400 if ttl_seconds is None else ttl_seconds
        if isinstance(ttl, bool) or not isinstance(ttl, int) or not 900 <= ttl <= 604800:
            fail(422, "委任の有効期間は900〜604800秒です")
        requested = set(permissions)
        if (
            not requested
            or not requested <= ALL_PERMISSIONS
            or not requested <= NON_ADMIN
            or ("retrieve" in requested and "read" not in requested)
        ):
            fail(422, "委任する権限を確認してください")
        with self.db() as db:
            current = self._authenticate(db, session_token)
            if current.id != actor.id:
                fail(401, "ログインしてください")
            self._limit("delegation-create:" + current.id, 20)
            project_row = db.execute("SELECT id FROM projects WHERE id=?", (project,)).fetchone()
            recipient = db.execute(
                "SELECT id,enabled FROM users WHERE id=?", (recipient_id,)
            ).fetchone()
            if not project_row or not recipient or not recipient["enabled"]:
                fail(404, "委任先またはプロジェクトが見つかりません")
            if recipient["id"] == current.id:
                fail(403, "自分自身には委任できません")
            if not self._delegation_authority(db, current.id, project, requested):
                fail(403, "委任する権限または管理権限がありません")
            normalized = json.dumps(sorted(requested), separators=(",", ":"))
            active_families = db.execute(
                "SELECT g.id,g.expires,g.permissions FROM delegation_grants g "
                "JOIN delegation_families f ON f.id=g.family_id "
                "WHERE f.grantor_id=? AND f.recipient_id=? AND f.project_id=? "
                "AND g.version=(SELECT MAX(x.version) FROM delegation_grants x "
                "WHERE x.family_id=g.family_id)",
                (current.id, recipient_id, project),
            ).fetchall()
            now = self._valid_delegation_now()
            if now is None:
                fail(503, "現在時刻を検証できないため委任を停止しました")
            for active in active_families:
                events = db.execute(
                    "SELECT 1 FROM delegation_events WHERE grant_id=?", (active["id"],)
                ).fetchone()
                try:
                    active_expires = float(active["expires"])
                except (TypeError, ValueError):
                    active_expires = float("nan")
                if not events and (not math.isfinite(active_expires) or now >= active_expires):
                    db.execute(
                        "INSERT OR IGNORE INTO delegation_events "
                        "(id,grant_id,event_type,actor_id,at) VALUES (?,?,?,?,?)",
                        (uid(), active["id"], "expire", "system", now),
                    )
                    self._audit(db, "system", "delegation.expire", active["id"])
            family = db.execute(
                "SELECT id FROM delegation_families WHERE grantor_id=? AND recipient_id=? "
                "AND project_id=? AND permissions=? ORDER BY created,id LIMIT 1",
                (current.id, recipient_id, project, normalized),
            ).fetchone()
            if family:
                active_family = db.execute(
                    "SELECT g.id,g.expires,g.permissions FROM delegation_grants g "
                    "WHERE g.family_id=? AND g.version=(SELECT MAX(version) "
                    "FROM delegation_grants WHERE family_id=?)",
                    (family["id"], family["id"]),
                ).fetchone()
                if active_family:
                    try:
                        active_expires = float(active_family["expires"])
                        active_permissions = set(json.loads(active_family["permissions"]))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        active_expires = float("nan")
                        active_permissions = set()
                    active_event = db.execute(
                        "SELECT 1 FROM delegation_events WHERE grant_id=?",
                        (active_family["id"],),
                    ).fetchone()
                    if (
                        not active_event
                        and math.isfinite(active_expires)
                        and now < active_expires
                        and active_permissions == requested
                    ):
                        return {
                            "id": active_family["id"],
                            "family_id": family["id"],
                            "version": db.execute(
                                "SELECT version FROM delegation_grants WHERE id=?",
                                (active_family["id"],),
                            ).fetchone()["version"],
                            "expires": active_expires,
                            "deduplicated": True,
                        }
            else:
                previous_family = db.execute(
                    "SELECT f.id,g.id AS grant_id,g.expires,g.permissions "
                    "FROM delegation_families f JOIN delegation_grants g ON g.family_id=f.id "
                    "WHERE f.grantor_id=? AND f.recipient_id=? AND f.project_id=? "
                    "AND g.version=(SELECT MAX(version) FROM delegation_grants "
                    "WHERE family_id=f.id) ORDER BY f.created DESC LIMIT 1",
                    (current.id, recipient_id, project),
                ).fetchone()
                if previous_family:
                    try:
                        previous_expires = float(previous_family["expires"])
                        previous_permissions = set(json.loads(previous_family["permissions"]))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        previous_expires = float("nan")
                        previous_permissions = set()
                    previous_event = db.execute(
                        "SELECT 1 FROM delegation_events WHERE grant_id=?",
                        (previous_family["grant_id"],),
                    ).fetchone()
                    if (
                        not previous_event
                        and math.isfinite(previous_expires)
                        and now < previous_expires
                        and previous_permissions != requested
                    ):
                        fail(409, "有効中の委任の範囲または権限は変更できません")
            if family:
                family_id = family["id"]
                prior = db.execute(
                    "SELECT g.id,g.expires FROM delegation_grants g WHERE g.family_id=? "
                    "AND g.version=(SELECT MAX(version) FROM delegation_grants WHERE family_id=?)",
                    (family_id, family_id),
                ).fetchone()
                if prior:
                    events = db.execute(
                        "SELECT 1 FROM delegation_events WHERE grant_id=?", (prior["id"],)
                    ).fetchone()
                    now = self._valid_delegation_now()
                    if now is None:
                        fail(503, "現在時刻を検証できないため委任を停止しました")
                    try:
                        prior_expires = float(prior["expires"])
                    except (TypeError, ValueError):
                        prior_expires = float("nan")
                    if not events and math.isfinite(prior_expires) and prior_expires > now:
                        return {
                            "id": prior["id"],
                            "family_id": family_id,
                            "version": db.execute(
                                "SELECT version FROM delegation_grants WHERE id=?",
                                (prior["id"],),
                            ).fetchone()["version"],
                            "expires": prior["expires"],
                            "deduplicated": True,
                        }
                    if not events:
                        db.execute(
                            "INSERT OR IGNORE INTO delegation_events "
                            "(id,grant_id,event_type,actor_id,at) VALUES (?,?,?,?,?)",
                            (uid(), prior["id"], "supersede", current.id, now),
                        )
                        self._audit(db, current.id, "delegation.supersede", prior["id"])
                    version = db.execute(
                        "SELECT COALESCE(MAX(version),0)+1 FROM delegation_grants "
                        "WHERE family_id=?",
                        (family_id,),
                    ).fetchone()[0]
                else:
                    version = 1
            else:
                family_id = uid()
                version = 1
                now = self._delegation_now()
                db.execute(
                    "INSERT INTO delegation_families "
                    "(id,grantor_id,recipient_id,project_id,permissions,created) "
                    "VALUES (?,?,?,?,?,?)",
                    (family_id, current.id, recipient_id, project, normalized, now),
                )
            now = self._valid_delegation_now()
            if now is None:
                fail(503, "現在時刻を検証できないため委任を停止しました")
            grant_id = uid()
            expires = now + ttl
            if not math.isfinite(expires) or expires <= now:
                fail(503, "現在時刻を検証できないため委任を停止しました")
            if family:
                previous = db.execute(
                    "SELECT g.id,g.expires,g.permissions FROM delegation_grants g "
                    "WHERE g.family_id=? AND g.version=(SELECT MAX(version) "
                    "FROM delegation_grants WHERE family_id=?)",
                    (family_id, family_id),
                ).fetchone()
                if previous:
                    prior_expires = float(previous["expires"])
                    prior_permissions = json.loads(previous["permissions"])
                    if (
                        math.isfinite(prior_expires)
                        and now < prior_expires
                        and prior_permissions != sorted(requested)
                    ):
                        fail(409, "有効中の委任の権限は変更できません")
                    if not db.execute(
                        "SELECT 1 FROM delegation_events WHERE grant_id=?", (previous["id"],)
                    ).fetchone():
                        db.execute(
                            "INSERT INTO delegation_events "
                            "(id,grant_id,event_type,actor_id,at) VALUES (?,?,?,?,?)",
                            (uid(), previous["id"], "supersede", current.id, now),
                        )
                        self._audit(db, current.id, "delegation.supersede", previous["id"])
            db.execute(
                "INSERT INTO delegation_grants "
                "(id,family_id,version,permissions,created,expires) VALUES (?,?,?,?,?,?)",
                (grant_id, family_id, version, normalized, now, expires),
            )
            self._audit(db, current.id, "delegation.grant", grant_id)
            return {
                "id": grant_id,
                "family_id": family_id,
                "version": version,
                "expires": expires,
                "deduplicated": False,
            }

    def _end_delegation(
        self,
        actor: Principal,
        session_token: str | None,
        grant_id: str,
        event_type: str,
    ) -> Json:
        with self.db() as db:
            current = self._authenticate(db, session_token)
            if current.id != actor.id:
                fail(401, "ログインしてください")
            self._limit("delegation-end:" + current.id, 30)
            grant = db.execute(
                "SELECT g.id,g.family_id,f.grantor_id,f.recipient_id "
                "FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id "
                "WHERE g.id=?",
                (grant_id,),
            ).fetchone()
            if not grant:
                fail(404, "委任が見つかりません")
            authorized = (
                current.id == grant["grantor_id"]
                if event_type == "revoke"
                else current.id == grant["recipient_id"]
            )
            if not authorized:
                fail(404, "委任が見つかりません")
            existing = db.execute(
                "SELECT 1 FROM delegation_events WHERE grant_id=?", (grant_id,)
            ).fetchone()
            if not existing:
                now = self._valid_delegation_now()
                if now is None:
                    fail(503, "現在時刻を検証できないため委任を停止しました")
                db.execute(
                    "INSERT OR IGNORE INTO delegation_events "
                    "(id,grant_id,event_type,actor_id,at) VALUES (?,?,?,?,?)",
                    (uid(), grant_id, event_type, current.id, now),
                )
                self._audit(db, current.id, f"delegation.{event_type}", grant_id)
                changed = True
            else:
                self._audit(db, current.id, f"delegation.{event_type}", grant_id, "already_ended")
                changed = False
            return {"id": grant_id, "ended": True, "changed": changed}

    def delegation_options(self, actor: Principal, session_token: str | None) -> Json:
        with self.db() as db:
            current = self._authenticate(db, session_token)
            if current.id != actor.id:
                fail(401, "ログインしてください")
            self._limit("delegation-options:" + current.id, 60)
            rows = db.execute(
                "SELECT p.id,p.name FROM projects p WHERE EXISTS ("
                "SELECT 1 FROM memberships m WHERE m.project_id=p.id AND m.user_id=?) "
                "OR EXISTS (SELECT 1 FROM project_owners o "
                "WHERE o.project_id=p.id AND o.user_id=?) ORDER BY p.name,p.id",
                (current.id, current.id),
            ).fetchall()
            projects = []
            for row in rows:
                project = row["id"]
                if not self._delegation_authority(db, current.id, project, set()):
                    continue
                recipients = [
                    {"id": recipient["id"], "username": recipient["username"]}
                    for recipient in db.execute(
                        "SELECT u.id,u.username FROM memberships m "
                        "JOIN users u ON u.id=m.user_id "
                        "WHERE m.project_id=? AND m.user_id<>? AND u.enabled=1 "
                        "AND u.system_admin=0 "
                        "ORDER BY u.username,u.id",
                        (project, current.id),
                    )
                ]
                projects.append(
                    {
                        "id": project,
                        "name": row["name"],
                        "recipients": recipients,
                        "permission_ceiling": sorted(
                            self._permission_ceiling_for_grantor(db, current.id, project)
                        ),
                    }
                )
            return {"projects": projects}

    def delegations(self, actor: Principal, session_token: str | None) -> list[Json]:
        with self.db() as db:
            current = self._authenticate(db, session_token)
            if current.id != actor.id:
                fail(401, "ログインしてください")
            self._limit("delegation-list:" + current.id, 60)
            stale = db.execute(
                "SELECT g.id,g.expires,f.grantor_id,f.project_id,f.permissions "
                "FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id "
                "WHERE g.version=(SELECT MAX(x.version) FROM delegation_grants x "
                "WHERE x.family_id=g.family_id)"
            ).fetchall()
            now = self._valid_delegation_now()
            if now is None:
                fail(503, "現在時刻を検証できないため委任を停止しました")
            for grant in stale:
                try:
                    expires = float(grant["expires"])
                    permissions = set(json.loads(grant["permissions"]))
                except (TypeError, ValueError, json.JSONDecodeError):
                    event_type = "invalidate"
                else:
                    if not math.isfinite(expires) or now >= expires:
                        event_type = "expire"
                    elif not self._delegation_authority(
                        db, grant["grantor_id"], grant["project_id"], permissions
                    ):
                        event_type = "invalidate"
                    else:
                        continue
                inserted = db.execute(
                    "INSERT OR IGNORE INTO delegation_events "
                    "(id,grant_id,event_type,actor_id,at) VALUES (?,?,?,?,?)",
                    (uid(), grant["id"], event_type, "system", now),
                ).rowcount
                if inserted:
                    self._audit(db, "system", f"delegation.{event_type}", grant["id"])
            rows = db.execute(
                "SELECT g.id,g.family_id,g.version,g.permissions,g.created,g.expires,"
                "f.grantor_id,f.recipient_id,f.project_id,"
                "grantor.username AS grantor_username,recipient.username AS recipient_username "
                "FROM delegation_grants g JOIN delegation_families f ON f.id=g.family_id "
                "JOIN users grantor ON grantor.id=f.grantor_id "
                "JOIN users recipient ON recipient.id=f.recipient_id "
                "WHERE f.grantor_id=? OR f.recipient_id=? ORDER BY g.created DESC,g.id",
                (current.id, current.id),
            ).fetchall()
            results: list[Json] = []
            now = self._valid_delegation_now()
            if now is None:
                fail(503, "現在時刻を検証できないため委任を停止しました")
            for row in rows:
                events = db.execute(
                    "SELECT event_type,at,actor_id FROM delegation_events "
                    "WHERE grant_id=? ORDER BY at,event_type",
                    (row["id"],),
                ).fetchall()
                current_version = db.execute(
                    "SELECT MAX(version) FROM delegation_grants WHERE family_id=?",
                    (row["family_id"],),
                ).fetchone()[0]
                try:
                    expires = float(row["expires"])
                except (TypeError, ValueError):
                    expires = float("nan")
                status = (
                    "ended"
                    if events
                    else "expired"
                    if not math.isfinite(expires) or now >= expires
                    else "active"
                    if row["version"] == current_version
                    else "superseded"
                )
                results.append(
                    {
                        "id": row["id"],
                        "family_id": row["family_id"],
                        "version": row["version"],
                        "project_id": row["project_id"],
                        "grantor_id": row["grantor_id"],
                        "grantor_username": row["grantor_username"],
                        "recipient_id": row["recipient_id"],
                        "recipient_username": row["recipient_username"],
                        "permissions": json.loads(row["permissions"]),
                        "created": row["created"],
                        "expires": row["expires"],
                        "status": status,
                        "events": [
                            {
                                "type": event["event_type"],
                                "at": event["at"],
                                "actor_id": event["actor_id"],
                            }
                            for event in events
                        ],
                    }
                )
            return results

    def revoke_delegation(self, actor: Principal, session_token: str | None, grant_id: str) -> Json:
        return self._end_delegation(actor, session_token, grant_id, "revoke")

    def cancel_delegation(self, actor: Principal, session_token: str | None, grant_id: str) -> Json:
        return self._end_delegation(actor, session_token, grant_id, "cancel")

    def require(
        self, db: StorageConnection, actor: Principal, project: str, permission: str
    ) -> None:
        if permission not in self._permissions(db, actor, project):
            fail(403, "この操作は許可されていません")

    def projects(self, actor: Principal) -> list[Json]:
        with self.db() as db:
            rows = db.execute(
                "SELECT p.*,m.role FROM projects p JOIN memberships m "
                "ON p.id=m.project_id WHERE m.user_id=? ORDER BY p.name",
                (actor.id,),
            ).fetchall()
            return [
                {
                    **dict(row),
                    "roles": self._held_roles(db, actor.id, row["id"]),
                    "permissions": sorted(self._permissions(db, actor, row["id"])),
                }
                for row in rows
            ]

    def membership_roles(self, actor: Principal, project: str, username: str) -> Json:
        with self.db() as db:
            if not db.execute("SELECT 1 FROM projects WHERE id=?", (project,)).fetchone():
                fail(404, "プロジェクトが見つかりません")
            if not actor.system_admin:
                self.require(db, actor, project, "manage_members")
            target = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if not target:
                fail(404, "所属が見つかりません")
            membership = db.execute(
                "SELECT denied_permissions FROM memberships WHERE user_id=? AND project_id=?",
                (target["id"], project),
            ).fetchone()
            if not membership:
                fail(404, "所属が見つかりません")
            return {
                "username": username,
                "project_id": project,
                "roles": self._held_roles(db, target["id"], project),
                "denied_permissions": json.loads(membership["denied_permissions"]),
                "delegated_permissions": sorted(
                    self._delegated_permissions(
                        db,
                        Principal(target["id"], username, False, False),
                        project,
                    )
                ),
                "effective_permissions": sorted(
                    self._permissions(
                        db,
                        Principal(target["id"], username, False, False),
                        project,
                    )
                ),
            }

    def _conversation(self, db: StorageConnection, actor: Principal, conversation: str) -> Any:
        row = db.execute(
            "SELECT * FROM conversations WHERE id=? AND owner_id=?", (conversation, actor.id)
        ).fetchone()
        if not row:
            fail(404, "会話が見つかりません")
        self.require(db, actor, row["project_id"], "retrieve")
        return row

    def _can_read(
        self,
        db: StorageConnection,
        actor: Principal,
        row: Any,
        operation: str = "read",
        conversation: str | None = None,
    ) -> bool:
        try:
            self.require(db, actor, row["project_id"], operation)
        except HTTPException:
            return False
        # _source_allows performs the source gate check (binding, revision, state).
        # It is called within the caller's with self.db() as db: transaction;
        # after it returns we explicitly commit to release the write lock before
        # any further network I/O (DATA-008).
        if not self._source_allows(db, actor, row):
            # Original-source permission is an additional fail-closed gate on top of
            # the existing Locus gates; the intersection keeps its deny-by-default base.
            return False
        if not self._source_connector_allows(db, actor, row):
            return False
        if row["kind"] != "shared":
            return bool(
                row["owner_id"] == actor.id
                and (row["kind"] != "attachment" or row["conversation_id"] == conversation)
            )
        self._membership(db, actor, row["project_id"])
        held_roles = set(self._held_roles(db, actor.id, row["project_id"]))
        return any(
            g["role"] in held_roles and operation in g["operations"]
            for g in json.loads(row["grants"])
        )

    def _document(
        self,
        db: StorageConnection,
        actor: Principal,
        document: str,
        conversation: str | None = None,
    ) -> Any:
        row = db.execute("SELECT * FROM documents WHERE id=?", (document,)).fetchone()
        if not row or not self._can_read(db, actor, row, conversation=conversation):
            fail(404, "資料が見つかりません")
        return row

    def _managed_document(
        self,
        db: StorageConnection,
        actor: Principal,
        document: str,
    ) -> Any:
        row = db.execute(
            "SELECT * FROM documents WHERE id=? AND owner_id=?",
            (document, actor.id),
        ).fetchone()
        if not row:
            fail(404, "資料が見つかりません")
        self.require(db, actor, row["project_id"], "upload")
        if row["kind"] == "attachment":
            self._conversation(db, actor, row["conversation_id"])
        return row

    @staticmethod
    def _metadata(row: Any, actor_id: str) -> Json:
        available = set(row.keys())
        data: Json = {
            key: row[key]
            for key in (
                "id",
                "name",
                "project_id",
                "kind",
                "status",
                "reason",
                "created",
                "conversation_id",
                "failure_code",
                "sandbox",
            )
            if key in available
        }
        # Projections that omit additive columns still produce valid metadata.
        data.setdefault("failure_code", "")
        data.setdefault("sandbox", "")
        raw_guarantees = row["sandbox_guarantees"] if "sandbox_guarantees" in available else "{}"
        try:
            guarantees = json.loads(raw_guarantees) if isinstance(raw_guarantees, str) else {}
        except (TypeError, ValueError):
            guarantees = {}
        data["sandbox_guarantees"] = guarantees if isinstance(guarantees, dict) else {}
        return {
            **data,
            "stage": DOCUMENT_STAGES.get(row["status"], row["status"]),
            "owned": row["owner_id"] == actor_id,
        }

    def documents(self, actor: Principal, project: str, q: str | None = None) -> list[Json]:
        with self.db() as db:
            self.require(db, actor, project, "read")
            needle = (q or "").strip().lower()
            rows = []
            for row in db.execute(
                "SELECT * FROM documents WHERE project_id=? ORDER BY created DESC",
                (project,),
            ).fetchall():
                if not (
                    self._can_read(db, actor, row)
                    or (
                        row["owner_id"] == actor.id
                        and row["kind"] == "shared"
                        and "upload" in self._permissions(db, actor, project)
                        # The owner listing branch must not bypass the source gate;
                        # unbound documents still pass it unchanged.
                        and self._source_allows(db, actor, row)
                        and self._source_connector_allows(db, actor, row)
                    )
                ):
                    continue
                if needle and needle not in row["name"].lower():
                    continue
                rows.append(self._metadata(row, actor.id))
            return rows

    def document(self, actor: Principal, document: str, conversation: str | None = None) -> Json:
        with self.db() as db:
            return self._metadata(self._document(db, actor, document, conversation), actor.id)

    def chunks(
        self, actor: Principal, document: str, conversation: str | None = None
    ) -> list[Json]:
        with self.db() as db:
            row = self._document(db, actor, document, conversation)
            if row["status"] != "ready":
                fail(409, "この資料はまだ参照できません")
            return [
                dict(chunk)
                for chunk in db.execute(
                    "SELECT id,document_id,page,ordinal,text FROM chunks WHERE document_id=? "
                    "ORDER BY page,ordinal",
                    (document,),
                ).fetchall()
            ]

    def related(
        self, actor: Principal, document: str, conversation: str | None = None
    ) -> list[Json]:
        """Explain local lexical relationships using only currently retrievable chunks."""
        with self.db() as db:
            if conversation is not None:
                context = self._conversation(db, actor, conversation)
            source = self._document(db, actor, document, conversation)
            if conversation is not None and context["project_id"] != source["project_id"]:
                fail(404, "資料が見つかりません")
            if not self._can_read(db, actor, source, "retrieve", conversation):
                fail(404, "資料が見つかりません")
            if source["status"] != "ready":
                fail(409, "この資料はまだ参照できません")
            self._limit("related:" + actor.id, 20)

            def terms(text: str) -> set[str]:
                # Bounded by the existing upload limit. Exact Unicode words, not semantic claims.
                words = {word for word in re.findall(r"\w+", text.lower()) if 1 < len(word) <= 80}
                for run in re.findall(r"[一-龯ぁ-んァ-ヶー]+", text):
                    words.update(run[index : index + 2] for index in range(len(run) - 1))
                return words

            source_terms: dict[str, Any] = {}
            for chunk in db.execute(
                "SELECT * FROM chunks WHERE document_id=? ORDER BY page,ordinal", (document,)
            ).fetchall():
                for word in terms(chunk["text"]):
                    source_terms.setdefault(word, chunk)
            results: list[Json] = []
            for candidate in db.execute(
                "SELECT id,owner_id,project_id,kind,name,status,reason,conversation_id,"
                "grants,created,failure_code,sandbox,sandbox_guarantees "
                "FROM documents WHERE project_id=? AND status='ready' AND id<>? "
                "ORDER BY id",
                (source["project_id"], document),
            ).fetchall():
                if not self._can_read(
                    db, actor, candidate, "retrieve", conversation
                ) or not self._can_read(db, actor, candidate, "read", conversation):
                    continue
                matches: dict[str, Any] = {}
                for chunk in db.execute(
                    "SELECT * FROM chunks WHERE document_id=? ORDER BY page,ordinal",
                    (candidate["id"],),
                ).fetchall():
                    for word in terms(chunk["text"]) & source_terms.keys():
                        matches.setdefault(word, chunk)
                if matches:
                    results.append(
                        {
                            "document": self._metadata(candidate, actor.id),
                            "method": "lexical-common-terms",
                            "shared_term_count": len(matches),
                            "evidence": [
                                {
                                    "term": word,
                                    "source_chunk_id": source_terms[word]["id"],
                                    "source_page": source_terms[word]["page"],
                                    "target_chunk_id": matches[word]["id"],
                                    "target_page": matches[word]["page"],
                                }
                                for word in sorted(matches)[:10]
                            ],
                        }
                    )
            return sorted(
                results, key=lambda item: (-item["shared_term_count"], item["document"]["id"])
            )[:10]

    def _check_ingestion_limits(self, db: StorageConnection, actor: Principal) -> None:
        """Ingestion bounds shared by manual upload and original-source ingestion."""
        queued = db.execute(
            "SELECT COUNT(*) FROM documents WHERE status IN ('queued','scanning','indexing')"
        ).fetchone()[0]
        owned = db.execute(
            "SELECT COUNT(*) FROM documents WHERE owner_id=? AND status "
            "IN ('queued','scanning','indexing')",
            (actor.id,),
        ).fetchone()[0]
        if queued >= IN_FLIGHT_LIMIT or owned >= OWNER_IN_FLIGHT_LIMIT:
            fail(429, "取り込み待ちが上限です。完了後に再試行してください")
        total = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        personal = db.execute(
            "SELECT COUNT(*) FROM documents WHERE owner_id=?", (actor.id,)
        ).fetchone()[0]
        if total >= DOCUMENT_LIMIT or personal >= OWNER_DOCUMENT_LIMIT:
            fail(429, "検証環境の資料数上限です。不要な資料を削除してください")

    def upload(
        self,
        actor: Principal,
        project: str,
        name: str,
        content: str,
        kind: str,
        conversation: str | None = None,
    ) -> Json:
        document_format = format_for(name)
        if unsafe_document_name(name) or document_format is None:
            fail(422, "対応形式はUTF-8のtxt・md・csvです。安全なファイル名を指定してください")
        if (
            not content.strip()
            or len(content.encode("utf-8")) > document_format.max_bytes
            or any(ord(c) < 32 and c not in "\n\r\t\f" for c in content)
        ):
            fail(422, "本文は空でないUTF-8テキスト、256 KiB以内にしてください")
        if kind not in {"personal", "attachment"}:
            fail(422, "新規資料は個人資料または会話添付として登録してください")
        with self.db() as db:
            self.require(db, actor, project, "upload")
            if kind == "attachment":
                conv = self._conversation(db, actor, conversation or "")
                if conv["project_id"] != project:
                    fail(404, "会話が見つかりません")
            elif conversation is not None:
                fail(422, "個人資料は会話に結び付けられません")
            self._check_ingestion_limits(db, actor)
            document = uid()
            db.execute(
                "INSERT INTO documents (id,owner_id,project_id,kind,name,content,status,"
                "conversation_id,created) VALUES (?,?,?,?,?,?,'queued',?,?)",
                (document, actor.id, project, kind, name, content, conversation, time.time()),
            )
            self._audit(db, actor.id, "document.upload", document)
            return self._metadata(
                db.execute("SELECT * FROM documents WHERE id=?", (document,)).fetchone(), actor.id
            )

    def _ingestion_allowed(self, db: StorageConnection, document: Any) -> bool:
        user = db.execute("SELECT * FROM users WHERE id=?", (document["owner_id"],)).fetchone()
        if not user or not user["enabled"] or user["must_rotate"]:
            return False
        actor = Principal(user["id"], user["username"], bool(user["system_admin"]), False)
        try:
            self.require(db, actor, document["project_id"], "upload")
            if document["kind"] == "attachment":
                self._conversation(db, actor, document["conversation_id"])
        except HTTPException:
            return False
        # The original source must still allow the ingesting user, and the bound
        # revision must still be current; both fail closed before any indexing.
        # _source_allows performs the source gate check (binding, revision,
        # state).  After it returns we commit to release the write lock before
        # any further network I/O (DATA-008).
        if not self._source_allows(db, actor, document):
            return False
        if not self._source_connector_allows(db, actor, document):
            return False
        return True

    @staticmethod
    def _extract_failure(result: SandboxResult) -> tuple[str, str]:
        """Map a failed SandboxResult to a failure_code and user-safe quarantine reason (§6)."""
        if result.guarantees.get("wall_time") == "timed_out":
            return (
                "extraction_timeout",
                "解析に時間がかかりすぎたため隔離中です。本文は検索に使いません",
            )
        if result.guarantees.get("output_bytes") == "truncated":
            return (
                "extraction_output_limit",
                "解析結果が上限を超えたため隔離中です。本文は検索に使いません",
            )
        return (
            "extraction_failed",
            "本文を安全に抽出できなかったため隔離中です。本文は検索に使いません",
        )

    def _extract(self, name: str, raw_content: str) -> tuple[bool, str | None, str, str, str, str]:
        """Run sandbox extraction and unwrap only ``body`` from the JSON envelope.

        Returns ``(ok, body, sandbox, guarantees_json, failure_code, failure_reason)``.
        The JSON envelope is handled strictly in memory and never stored in ``documents``.
        """
        doc_format = format_for(name)
        if doc_format is None:
            return (
                False,
                None,
                "subprocess",
                json.dumps(SUBPROCESS_GUARANTEES, ensure_ascii=False),
                "extraction_failed",
                "対応していない形式のため隔離中です。本文は検索に使いません",
            )
        result = extract_with_sandbox(doc_format.extractor, raw_content)
        sandbox = result.sandbox if result.sandbox in {"docker", "subprocess"} else "subprocess"
        guarantees_json = json.dumps(result.guarantees, ensure_ascii=False)
        if not result.success or result.content is None:
            failure_code, failure_reason = self._extract_failure(result)
            return (False, None, sandbox, guarantees_json, failure_code, failure_reason)
        try:
            envelope = json.loads(result.content)
        except (TypeError, ValueError):
            return (
                False,
                None,
                sandbox,
                guarantees_json,
                "extraction_failed",
                "本文を安全に抽出できなかったため隔離中です。本文は検索に使いません",
            )
        body = envelope.get("body") if isinstance(envelope, dict) else None
        if not isinstance(body, str) or not body:
            return (
                False,
                None,
                sandbox,
                guarantees_json,
                "extraction_failed",
                "本文を安全に抽出できなかったため隔離中です。本文は検索に使いません",
            )
        return (True, body, sandbox, guarantees_json, "", "")

    def process_next(self) -> bool:
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM documents WHERE status='queued' ORDER BY created LIMIT 1"
            ).fetchone()
            if not row:
                return False
            # Recheck queued work BEFORE exposing content to an extractor or scanner adapter.
            if not self._ingestion_allowed(db, row):
                self._cancel_ingestion(
                    db, row["id"], "permission_revoked", "登録者の利用権限が失効しました"
                )
                self._audit(db, "worker", "document.ingest", row["id"], "cancelled")
                return True
            db.execute(
                "UPDATE documents SET status='scanning',reason='',failure_code='' WHERE id=?",
                (row["id"],),
            )
        # Resuming an interrupted 'indexing' row (index_checkpoint > 0) reuses its
        # already-extracted content so page checkpoints remain intact and extraction
        # never re-wraps or re-transforms a partially indexed body.
        already_extracted = int(row["index_checkpoint"] or 0) > 0
        if already_extracted:
            extracted_ok = True
            body: str | None = str(row["content"])
            sandbox = str(row["sandbox"] or "subprocess")
            guarantees_json = str(
                row["sandbox_guarantees"]
                if row["sandbox_guarantees"] and row["sandbox_guarantees"] != "{}"
                else json.dumps(SUBPROCESS_GUARANTEES, ensure_ascii=False)
            )
            extract_code = ""
            extract_reason = ""
        else:
            (
                extracted_ok,
                body,
                sandbox,
                guarantees_json,
                extract_code,
                extract_reason,
            ) = self._extract(str(row["name"]), str(row["content"]))
        outcome = "clean"
        if extracted_ok:
            assert body is not None
            try:
                outcome = self.scanner.scan(body).outcome
            except Exception:
                # A configured adapter that raises still fails closed; the check
                # simply could not run, which is not a rejection verdict.
                outcome = "unavailable"
            self.scanner_last_outcome = outcome
        # Extraction and scanner run outside the transaction. Never publish stale work
        # after revoke/delete/cancel, and never write extracted content mid-flight so a
        # crash + recover_jobs() retry always reads the original raw upload.
        with self.db() as db:
            live = db.execute("SELECT * FROM documents WHERE id=?", (row["id"],)).fetchone()
            if not live or live["status"] != "scanning":
                return True
            if not self._ingestion_allowed(db, live):
                self._cancel_ingestion(
                    db, row["id"], "permission_revoked", "登録者の利用権限が失効しました"
                )
                self._audit(db, "worker", "document.ingest", row["id"], "cancelled")
                return True
            if not extracted_ok or body is None:
                db.execute(
                    "UPDATE documents SET status='quarantined',reason=?,failure_code=?,"
                    "sandbox=?,sandbox_guarantees=? WHERE id=?",
                    (extract_reason, extract_code, sandbox, guarantees_json, row["id"]),
                )
                self._audit(db, "worker", "document.ingest", row["id"], "quarantined")
                return True
            if outcome != "clean":
                # Fail closed for every non-clean outcome, but keep an explicit
                # rejection distinct from a check that could not run at all.
                reason = (
                    "安全検査を通過していないため隔離中です。本文は検索に使いません"
                    if outcome == "rejected"
                    else "安全検査を実行できないため隔離中です（既定拒否）。本文は検索に使いません"
                )
                code = "scanner_rejected" if outcome == "rejected" else "scanner_unavailable"
                db.execute(
                    "UPDATE documents SET status='quarantined',reason=?,failure_code=?,"
                    "sandbox=?,sandbox_guarantees=? WHERE id=?",
                    (reason, code, sandbox, guarantees_json, row["id"]),
                )
                self._audit(db, "worker", "document.ingest", row["id"], "quarantined")
                return True
            # Chunks are built in a resumable stage. _index commits each completed
            # page checkpoint while keeping the checked publication transaction
            # free of stale scanner work. Store only the unwrapped body, never the
            # extractor's JSON envelope.
            db.execute(
                "UPDATE documents SET status='indexing',content=?,sandbox=?,"
                "sandbox_guarantees=? WHERE id=?",
                (body, sandbox, guarantees_json, row["id"]),
            )
            indexing_row = db.execute("SELECT * FROM documents WHERE id=?", (row["id"],)).fetchone()
            try:
                self._index(db, indexing_row)
            except Exception:
                # Roll back only the failed page; earlier committed checkpoints
                # are retained so a restart resumes instead of duplicating.
                db.rollback()
                db.execute("BEGIN IMMEDIATE")
                live = db.execute("SELECT * FROM documents WHERE id=?", (row["id"],)).fetchone()
                if live and live["status"] == "indexing":
                    db.execute(
                        "UPDATE documents SET status='failed',reason=?,failure_code=? WHERE id=?",
                        (
                            "索引処理に失敗しました。再起動後にチェックポイントから再開します",
                            "index_failed",
                            row["id"],
                        ),
                    )
            current = db.execute("SELECT status FROM documents WHERE id=?", (row["id"],)).fetchone()
            if current and current["status"] in {"ready", "quarantined", "failed", "cancelled"}:
                self._audit(db, "worker", "document.ingest", row["id"], str(current["status"]))
            return True

    @staticmethod
    def _cancel_ingestion(db: StorageConnection, document: str, code: str, reason: str) -> None:
        # Cancelled/revoked work must not leave indexable chunks behind.
        db.execute("DELETE FROM chunks WHERE document_id=?", (document,))
        db.execute(
            "UPDATE documents SET status='cancelled',reason=?,failure_code=? WHERE id=?",
            (reason, code, document),
        )

    @staticmethod
    def _insert_page(db: StorageConnection, document: str, page: int, text: str) -> None:
        for ordinal, offset in enumerate(range(0, len(text), CHUNK_CHARS), start=1):
            db.execute(
                "INSERT INTO chunks VALUES (?,?,?,?,?)",
                (uid(), document, page, ordinal, text[offset : offset + CHUNK_CHARS]),
            )

    def _index(self, db: StorageConnection, row: Any) -> None:
        """Index pages from the persisted checkpoint, committing each page.

        Pages already marked complete are reused as-is. Only one page is written
        per transaction, so an interrupted run can resume without producing
        duplicate chunks. The caller holds the write transaction; completed
        resumable pages are committed explicitly to persist their checkpoint.
        """
        pages = str(row["content"]).split("\f")
        checkpoint = int(row["index_checkpoint"] or 0)
        resumable = row["status"] == "indexing"
        for page in range(checkpoint + 1, len(pages) + 1):
            if resumable:
                # The ingestion path re-checks live work and permissions for every
                # page. The seed path (status='ready') keeps its old behavior.
                live = db.execute("SELECT * FROM documents WHERE id=?", (row["id"],)).fetchone()
                if not live or live["status"] != "indexing":
                    return
                if not self._ingestion_allowed(db, live):
                    self._cancel_ingestion(
                        db, row["id"], "permission_revoked", "登録者の利用権限が失効しました"
                    )
                    return
            # Any partial rows for a page that was not marked complete are
            # replaced; completed pages are never touched again.
            db.execute("DELETE FROM chunks WHERE document_id=? AND page=?", (row["id"], page))
            self._insert_page(db, row["id"], page, pages[page - 1])
            db.execute("UPDATE documents SET index_checkpoint=? WHERE id=?", (page, row["id"]))
            if resumable and page < len(pages):
                # Persist the checkpoint before the next page. The explicit
                # BEGIN keeps the caller's write-serialized unit for the next
                # page and its final publication check.
                db.commit()
                db.execute("BEGIN IMMEDIATE")
        db.execute(
            "UPDATE documents SET status='ready',reason='',failure_code='',"
            "index_checkpoint=? WHERE id=?",
            (len(pages), row["id"]),
        )

    def seed_synthetic(self, username: str, project: str, kind: str = "personal") -> str:
        """Local CLI/test-only fixed bytes; never accepts arbitrary file content."""
        with self.db() as db:
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not user or kind not in {"personal", "shared"}:
                fail(422, "サンプルの登録先を確認してください")
            actor = Principal(
                user["id"], username, bool(user["system_admin"]), bool(user["must_rotate"])
            )
            self.require(db, actor, project, "upload")
            document = uid()
            grants = [
                {"role": role, "operations": ["read", "retrieve"]}
                for role in ("project_lead", "researcher", "viewer")
            ]
            db.execute(
                "INSERT INTO documents (id,owner_id,project_id,kind,name,content,status,"
                "grants,created) VALUES (?,?,?,?,?,?,'ready',?,?)",
                (
                    document,
                    user["id"],
                    project,
                    kind,
                    "合成サンプル_成膜条件.txt",
                    SYNTHETIC_TEXT,
                    json.dumps(grants),
                    time.time(),
                ),
            )
            self._index(
                db, db.execute("SELECT * FROM documents WHERE id=?", (document,)).fetchone()
            )
            self._audit(db, "local-cli", "synthetic.seed", document)
            return document

    def cancel(self, actor: Principal, document: str) -> None:
        with self.db() as db:
            row = self._managed_document(db, actor, document)
            if row["owner_id"] != actor.id or row["status"] not in {
                "queued",
                "scanning",
                "indexing",
            }:
                fail(409, "この取り込みは取消できません")
            db.execute("DELETE FROM chunks WHERE document_id=?", (document,))
            db.execute(
                "UPDATE documents SET status='cancelled',content='',reason=?,failure_code=? "
                "WHERE id=?",
                ("利用者が取り消しました", "cancelled", document),
            )
            self._audit(db, actor.id, "ingestion.cancel", document)

    def _owned_attachment(
        self, db: StorageConnection, actor: Principal, document: str
    ) -> str | None:
        row = db.execute(
            "SELECT conversation_id FROM documents WHERE id=? AND owner_id=?", (document, actor.id)
        ).fetchone()
        return row["conversation_id"] if row else None

    def delete_document(self, actor: Principal, document: str) -> None:
        with self.db() as db:
            self._managed_document(db, actor, document)
            db.execute("DELETE FROM documents WHERE id=?", (document,))
            self._audit(db, actor.id, "document.delete", document)

    def _validated_grants(
        self, db: StorageConnection, project: str, grants: list[Json]
    ) -> list[Json]:
        """Publish-style grant validation, reused by original-source ingestion."""
        for grant in grants:
            role = grant.get("role")
            operations = grant.get("operations")
            custom = db.execute(
                "SELECT id FROM roles WHERE id=? AND project_id=?",
                (role, project),
            ).fetchone()
            if (
                (role not in ROLE_PERMISSIONS and not custom)
                or not isinstance(operations, list)
                or not operations
                or not set(operations) <= {"read", "retrieve"}
            ):
                fail(422, "公開先のロールと操作を確認してください")
            if "retrieve" in operations and "read" not in operations:
                fail(422, "チャット参照には閲覧の許可も必要です")
        return grants

    def publish(self, actor: Principal, document: str, grants: list[Json]) -> None:
        with self.db() as db:
            row = self._managed_document(db, actor, document)
            self.require(db, actor, row["project_id"], "publish")
            if row["owner_id"] != actor.id or row["kind"] == "attachment":
                fail(403, "会話添付や他人の資料は公開できません")
            grants = self._validated_grants(db, row["project_id"], grants)
            db.execute(
                "UPDATE documents SET kind=?,grants=? WHERE id=?",
                ("shared" if grants else "personal", json.dumps(grants), document),
            )
            self._audit(db, actor.id, "document.publish", document)

    def new_conversation(self, actor: Principal, project: str) -> Json:
        with self.db() as db:
            self.require(db, actor, project, "retrieve")
            conversation = uid()
            db.execute(
                "INSERT INTO conversations VALUES (?,?,?,?)",
                (conversation, actor.id, project, time.time()),
            )
            return {"id": conversation, "project_id": project}

    def conversations(self, actor: Principal, project: str) -> list[Json]:
        with self.db() as db:
            self.require(db, actor, project, "retrieve")
            rows = []
            for row in db.execute(
                """
                SELECT c.id, c.project_id, c.created,
                       (SELECT m.text FROM messages m
                        WHERE m.conversation_id = c.id
                        ORDER BY m.created ASC, m.rowid ASC
                        LIMIT 1) AS preview
                FROM conversations c
                WHERE c.owner_id=? AND c.project_id=?
                ORDER BY c.created DESC
                """,
                (actor.id, project),
            ).fetchall():
                item = dict(row)
                preview = " ".join((item.get("preview") or "").split())
                if len(preview) > 80:
                    preview = preview[:79].rstrip() + "…"
                item["preview"] = preview
                rows.append(item)
            return rows

    def _citations(
        self, db: StorageConnection, actor: Principal, ids: list[str], conversation: str
    ) -> list[Json]:
        citations = []
        for chunk_id in ids:
            chunk = db.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone()
            if not chunk:
                continue
            doc = db.execute(
                "SELECT * FROM documents WHERE id=?", (chunk["document_id"],)
            ).fetchone()
            if (
                doc
                and doc["status"] == "ready"
                and self._can_read(db, actor, doc, "retrieve", conversation)
            ):
                citations.append({**dict(chunk), "name": doc["name"]})
        return citations

    def _generated(
        self, db: StorageConnection, actor: Principal, row: Any, conversation: str
    ) -> Json:
        generated = db.execute(
            "SELECT * FROM generated_answers WHERE message_id=?", (row["id"],)
        ).fetchone()
        ids = json.loads(row["citation_ids"])
        if not generated:
            return {"answer": None, "model": None}
        if not ids or len(self._citations(db, actor, ids, conversation)) != len(ids):
            return {"answer": None, "model": None, "answer_hidden": True}
        return {"answer": generated["answer"], "model": generated["model"]}

    def conversation(self, actor: Principal, conversation: str) -> Json:
        with self.db() as db:
            conv = self._conversation(db, actor, conversation)
            messages = [
                {
                    "id": row["id"],
                    "text": row["text"],
                    "scope": row["scope"],
                    **self._generated(db, actor, row, conversation),
                    "citations": self._citations(
                        db, actor, json.loads(row["citation_ids"]), conversation
                    ),
                }
                for row in db.execute(
                    "SELECT * FROM messages WHERE conversation_id=? ORDER BY created",
                    (conversation,),
                ).fetchall()
            ]
            attachments = [
                self._metadata(row, actor.id)
                for row in db.execute(
                    "SELECT * FROM documents WHERE conversation_id=?",
                    (conversation,),
                ).fetchall()
                if self._can_read(db, actor, row, conversation=conversation)
            ]
            return {**dict(conv), "messages": messages, "attachments": attachments}

    def _cancel_chat_if_requested(self, db: StorageConnection, job: str) -> bool:
        row = db.execute(
            "SELECT user_id FROM chat_jobs WHERE id=? AND status='running' AND cancel_requested=1",
            (job,),
        ).fetchone()
        if not row:
            return False
        changed = db.execute(
            "UPDATE chat_jobs SET status='cancelled',updated=?,detail=?,message_id=NULL "
            "WHERE id=? AND status='running' AND cancel_requested=1",
            (time.time(), "質問を取り消しました", job),
        ).rowcount
        if changed:
            self._audit(db, row["user_id"], "chat.cancelled", job)
        return bool(changed)

    def send(
        self,
        actor: Principal,
        conversation: str,
        text: str,
        scope: str,
        attachments: list[str],
        *,
        generate: Callable[[str, list[Json]], tuple[str, str]] | None = None,
        validate: Callable[[], None] | None = None,
        token: str | None = None,
        charge_limit: bool = True,
        chat_job_id: str | None = None,
    ) -> Json | None:
        if scope not in {"all", "shared", "personal"}:
            fail(422, "参照範囲を確認してください")
        with self.db() as db:
            conv = self._conversation(db, actor, conversation)
            if charge_limit:
                # Charged once per question, at submission. Waiting-line retries
                # from the worker pass charge_limit=False so a busy slot cannot
                # exhaust the user's interactive budget or kill the queued job.
                self._limit("chat:" + actor.id, 20)
            count = db.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conversation,)
            ).fetchone()[0]
            if count >= 200:
                fail(429, "1会話200件までです。新しい会話を開始してください")
            for document in attachments:
                row = self._document(db, actor, document, conversation)
                if row["kind"] != "attachment" or row["status"] != "ready":
                    fail(409, "未解析・隔離中の添付は参照できません。取り外して再送信してください")
            candidates = []
            words = [w.lower() for w in re.findall(r"[\w]+", text)][:30]
            rows = db.execute(
                "SELECT * FROM documents WHERE project_id=? AND status='ready'",
                (conv["project_id"],),
            ).fetchall()
            for doc in rows:
                if not self._can_read(db, actor, doc, "retrieve", conversation):
                    continue
                if doc["kind"] == "attachment" and doc["id"] not in attachments:
                    continue
                if doc["kind"] != "attachment" and scope != "all" and doc["kind"] != scope:
                    continue
                for chunk in db.execute(
                    "SELECT * FROM chunks WHERE document_id=?", (doc["id"],)
                ).fetchall():
                    lower = chunk["text"].lower()
                    score = sum(1 for word in words if word in lower)
                    # Japanese sentences are not whitespace-delimited: match character bigrams.
                    score += sum(
                        1 for i in range(min(len(text) - 1, 60)) if text[i : i + 2].lower() in lower
                    )
                    if score:
                        candidates.append((score, chunk["id"]))
            ids = [chunk for _, chunk in sorted(candidates, reverse=True)[:5]]
            citations = self._citations(db, actor, ids, conversation)
            if generate:
                current = self._authenticate(db, token)
                if current.id != actor.id:
                    fail(401, "ログインしてください")
                if validate:
                    validate()
        # Honor cancellation before model dispatch, but never interrupt an HTTP
        # request once started. The final transaction arbitrates racing completion.
        if generate and citations and chat_job_id:
            with self.db() as db:
                if self._cancel_chat_if_requested(db, chat_job_id):
                    return None
        # Recheck immediately before dispatch: revocation/expiry between initial
        # retrieval and the external model call must not expose stale citations.
        if generate and citations:
            with self.db() as db:
                current = self._authenticate(db, token)
                if current.id != actor.id:
                    fail(401, "ログインしてください")
                self._conversation(db, current, conversation)
                for document in attachments:
                    attached = self._document(db, current, document, conversation)
                    if attached["kind"] != "attachment" or attached["status"] != "ready":
                        fail(409, "添付の権限または状態が変わりました")
                if validate:
                    validate()
                if self._citations(db, current, ids, conversation) != citations:
                    fail(409, "参照資料の権限または内容が変わりました")
        # Never hold the database transaction during model I/O.
        generated = generate(text, citations) if generate and citations else None
        with self.db() as db:
            self._conversation(db, actor, conversation)
            if generate:
                current = self._authenticate(db, token)
                if current.id != actor.id:
                    fail(401, "ログインしてください")
                self._conversation(db, current, conversation)
                for document in attachments:
                    attached = self._document(db, current, document, conversation)
                    if attached["kind"] != "attachment" or attached["status"] != "ready":
                        fail(409, "添付の権限または状態が変わりました")
                if validate:
                    validate()
                if self._citations(db, current, ids, conversation) != citations:
                    fail(409, "参照資料の権限または内容が変わりました")
            if chat_job_id:
                job_row = db.execute(
                    "SELECT status,cancel_requested FROM chat_jobs WHERE id=? AND user_id=?",
                    (chat_job_id, actor.id),
                ).fetchone()
                if not job_row or job_row["status"] != "running":
                    return None
                if job_row["cancel_requested"]:
                    self._cancel_chat_if_requested(db, chat_job_id)
                    return None
            if (
                db.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conversation,)
                ).fetchone()[0]
                >= 200
            ):
                fail(429, "1会話200件までです")
            message = uid()
            db.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?,?)",
                (message, conversation, text, json.dumps(ids), scope, time.time()),
            )
            if generated:
                db.execute("INSERT INTO generated_answers VALUES (?,?,?)", (message, *generated))
            if chat_job_id:
                changed = db.execute(
                    "UPDATE chat_jobs SET status='done',updated=?,detail='',message_id=? "
                    "WHERE id=? AND status='running' AND cancel_requested=0",
                    (time.time(), message, chat_job_id),
                ).rowcount
                if not changed:
                    fail(409, "質問の状態が変わりました")
                self._audit(db, "worker", "chat.done", chat_job_id)
            self._audit(db, actor.id, "retrieval.complete", conversation)
            return {
                "id": message,
                "text": text,
                "scope": scope,
                "answer": generated[0] if generated else None,
                "model": generated[1] if generated else None,
                "citations": self._citations(db, actor, ids, conversation),
            }

    def delete_conversation(self, actor: Principal, conversation: str) -> None:
        with self.db() as db:
            self._conversation(db, actor, conversation)
            db.execute("DELETE FROM conversations WHERE id=?", (conversation,))
            self._audit(db, actor.id, "conversation.delete", conversation)
            # Cascaded queued jobs leave process-local closures behind; drop them
            # in the same serialized unit, without nesting a second transaction.
            rows = db.execute(
                "SELECT id FROM chat_jobs WHERE conversation_id=?", (conversation,)
            ).fetchall()
            with self.chat_dispatch_lock:
                for row in rows:
                    self.chat_dispatch.pop(row["id"], None)

    # --- Dialogue waiting line -------------------------------------------------
    # One bounded, fair-share line in front of the single model slot. The
    # synchronous contract of send() is unchanged: submission stays inline while
    # the slot is free, and only an occupied slot produces a queued job (202).

    def enqueue_chat(
        self,
        actor: Principal,
        conversation: str,
        text: str,
        scope: str,
        attachments: list[str],
        *,
        token: str,
        generate: Callable[[str, list[Json]], tuple[str, str]],
        validate: Callable[[], None] | None,
    ) -> str:
        """Validate the question now and place it in the fair waiting line."""
        if scope not in {"all", "shared", "personal"}:
            fail(422, "参照範囲を確認してください")
        with self.db() as db:
            conv = self._conversation(db, actor, conversation)
            # No extra rate-limit charge here: the submitting send() call already
            # consumed the per-user budget for this question.
            if (
                db.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conversation,)
                ).fetchone()[0]
                >= 200
            ):
                fail(429, "1会話200件までです。新しい会話を開始してください")
            for document in attachments:
                row = self._document(db, actor, document, conversation)
                if row["kind"] != "attachment" or row["status"] != "ready":
                    fail(
                        409,
                        "未解析・隔離中の添付は参照できません。取り外して再送信してください",
                    )
            if db.execute(
                "SELECT id FROM chat_jobs WHERE conversation_id=? "
                "AND status IN ('queued','running')",
                (conversation,),
            ).fetchone():
                fail(409, "前の質問が処理中です。完了してから次の質問を送信してください")
            queued_total = db.execute(
                "SELECT COUNT(*) FROM chat_jobs WHERE status='queued'"
            ).fetchone()[0]
            queued_owned = db.execute(
                "SELECT COUNT(*) FROM chat_jobs WHERE status='queued' AND user_id=?",
                (actor.id,),
            ).fetchone()[0]
            if queued_total >= CHAT_QUEUE_LIMIT:
                fail(429, "対話の待機列が上限です。しばらく待ってから再試行してください")
            if queued_owned >= CHAT_USER_QUEUE_LIMIT:
                fail(429, "待機中の質問が上限です。完了後に送信してください")
            job_id = uid()
            now = time.time()
            db.execute(
                "INSERT INTO chat_jobs "
                "(id,conversation_id,user_id,text,scope,attachments,status,created,updated) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    conv["id"],
                    actor.id,
                    text,
                    scope,
                    json.dumps(attachments),
                    "queued",
                    now,
                    now,
                ),
            )
            self._audit(db, actor.id, "chat.enqueued", job_id)
            # Register inside the serialized database unit so the worker cannot
            # observe the queued row before its dispatch closures exist.
            with self.chat_dispatch_lock:
                self.chat_dispatch[job_id] = ChatDispatch(token, generate, validate)
        return job_id

    def start_stream_chat(
        self,
        actor: Principal,
        conversation: str,
        text: str,
        scope: str,
        attachments: list[str],
    ) -> str:
        """Claim the free model slot for an inline, streamed dialogue.

        The row is created as `running`, so cooperative cancellation, the restart
        sweep and the one-question-per-conversation rule all apply unchanged. It
        never enters the waiting line, and the answer is still committed once, by
        send(), after its final permission and citation checks.
        """
        if scope not in {"all", "shared", "personal"}:
            fail(422, "参照範囲を確認してください")
        with self.db() as db:
            conv = self._conversation(db, actor, conversation)
            if (
                db.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conversation,)
                ).fetchone()[0]
                >= 200
            ):
                fail(429, "1会話200件までです。新しい会話を開始してください")
            for document in attachments:
                row = self._document(db, actor, document, conversation)
                if row["kind"] != "attachment" or row["status"] != "ready":
                    fail(
                        409,
                        "未解析・隔離中の添付は参照できません。取り外して再送信してください",
                    )
            if db.execute(
                "SELECT id FROM chat_jobs WHERE conversation_id=? "
                "AND status IN ('queued','running')",
                (conversation,),
            ).fetchone():
                fail(409, "前の質問が処理中です。完了してから次の質問を送信してください")
            job_id = uid()
            now = time.time()
            db.execute(
                "INSERT INTO chat_jobs "
                "(id,conversation_id,user_id,text,scope,attachments,status,created,updated) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    conv["id"],
                    actor.id,
                    text,
                    scope,
                    json.dumps(attachments),
                    "running",
                    now,
                    now,
                ),
            )
            self._audit(db, actor.id, "chat.streaming", job_id)
        return job_id

    def stream_stopped(self, job: str) -> bool:
        """True when a streamed dialogue must stop: cancelled, finished or gone."""
        with self.db() as db:
            row = db.execute(
                "SELECT status,cancel_requested FROM chat_jobs WHERE id=?", (job,)
            ).fetchone()
        return not row or row["status"] != "running" or bool(row["cancel_requested"])

    def finish_stream_chat(self, job: str, detail: str) -> str:
        """Close a streamed dialogue that committed no answer, and report its state.

        A requested cancellation wins over the failure detail, so an interrupted
        stream is reported as cancelled rather than as a generation failure.
        """
        self._finish_chat(job, "failed", detail)
        with self.db() as db:
            row = db.execute("SELECT status FROM chat_jobs WHERE id=?", (job,)).fetchone()
        return str(row["status"]) if row else "failed"

    def chat_job(self, actor: Principal, job: str) -> Json:
        """Owner-only status view; expired waiting entries fail visibly here too."""
        with self.db() as db:
            self._limit("chatjob:" + actor.id, 120)
            row = db.execute(
                "SELECT * FROM chat_jobs WHERE id=? AND user_id=?", (job, actor.id)
            ).fetchone()
            if not row:
                fail(404, "質問が見つかりません")
            if row["status"] == "queued" and time.time() - row["created"] > CHAT_WAIT_SECONDS:
                changed = db.execute(
                    "UPDATE chat_jobs SET status='failed',updated=?,detail=? "
                    "WHERE id=? AND user_id=? AND status='queued'",
                    (
                        time.time(),
                        "対話の待機上限を超えました。再度送信してください",
                        job,
                        actor.id,
                    ),
                ).rowcount
                if changed:
                    self._audit(db, actor.id, "chat.expired", job)
                    with self.chat_dispatch_lock:
                        self.chat_dispatch.pop(job, None)
                row = db.execute("SELECT * FROM chat_jobs WHERE id=?", (job,)).fetchone()
            return {
                "id": row["id"],
                "conversation_id": row["conversation_id"],
                "status": row["status"],
                "detail": row["detail"],
                "message_id": row["message_id"],
                "cancel_requested": bool(row["cancel_requested"]),
                "created": row["created"],
            }

    def cancel_chat_job(self, actor: Principal, job: str) -> None:
        """Request cooperative cancellation without interrupting an in-flight model call."""
        remove_dispatch = False
        with self.db() as db:
            self._limit("chatjob:" + actor.id, 120)
            row = db.execute(
                "SELECT status,cancel_requested FROM chat_jobs WHERE id=? AND user_id=?",
                (job, actor.id),
            ).fetchone()
            if not row:
                fail(404, "質問が見つかりません")
            if row["status"] == "queued":
                changed = db.execute(
                    "UPDATE chat_jobs SET status='cancelled',updated=?,detail=?,message_id=NULL "
                    "WHERE id=? AND user_id=? AND status='queued'",
                    (time.time(), "質問を取り消しました", job, actor.id),
                ).rowcount
                if changed:
                    self._audit(db, actor.id, "chat.cancel", job)
                    remove_dispatch = True
            elif row["status"] == "running":
                if not row["cancel_requested"]:
                    changed = db.execute(
                        "UPDATE chat_jobs SET cancel_requested=1,updated=? "
                        "WHERE id=? AND user_id=? AND status='running' AND cancel_requested=0",
                        (time.time(), job, actor.id),
                    ).rowcount
                    if changed:
                        self._audit(db, actor.id, "chat.cancel.requested", job)
            elif row["status"] != "cancelled":
                fail(409, "処理済みの質問です")
        if remove_dispatch:
            with self.chat_dispatch_lock:
                self.chat_dispatch.pop(job, None)

    def _claim_chat_turn(
        self, last_user: str | None
    ) -> tuple[str, Any | None, ChatDispatch | None]:
        """Claim the oldest eligible queued dialogue for execution.

        Pick order is the fair-share order shared by the sequential worker and
        the parallel batch: the last-served user is picked after everyone else,
        ties break by creation time. Returns ``("started", row, dispatch)`` when
        a queued entry transitioned to ``running``, ``("handled", None, None)``
        when an entry was failed in place (wait deadline or the restart sweep),
        and ``("nothing", None, None)`` when no entry can be claimed right now.
        """
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM chat_jobs WHERE status='queued' "
                "ORDER BY CASE WHEN user_id=? THEN 1 ELSE 0 END, created, id LIMIT 1",
                (last_user,),
            ).fetchone()
            if row is None:
                return ("nothing", None, None)
            if time.time() - row["created"] > CHAT_WAIT_SECONDS:
                self._fail_chat(db, row["id"], "対話の待機上限を超えました。再度送信してください")
                return ("handled", None, None)
            dispatch = self.chat_dispatch.get(row["id"])
            if dispatch is None:
                self._fail_chat(
                    db,
                    row["id"],
                    "アプリケーションの再起動により中止しました。再度送信してください",
                )
                return ("handled", None, None)
            taken = db.execute(
                "UPDATE chat_jobs SET status='running',updated=? WHERE id=? AND status='queued'",
                (time.time(), row["id"]),
            ).rowcount
            if not taken:
                return ("nothing", None, None)
        return ("started", row, dispatch)

    def _run_chat_job(self, row: Any, dispatch: ChatDispatch, job_id: str) -> bool:
        try:
            principal = self.authenticate(dispatch.token)
            self.send(
                principal,
                row["conversation_id"],
                row["text"],
                row["scope"],
                json.loads(row["attachments"]),
                generate=dispatch.generate,
                validate=dispatch.validate,
                token=dispatch.token,
                # Submission already charged the per-user limit; worker retries
                # must not consume it again while they wait for the slot.
                charge_limit=False,
                chat_job_id=job_id,
            )
        except ModelBusy:
            # No HTTP request started. Requeue only if cancellation did not win.
            with self.db() as db:
                changed = db.execute(
                    "UPDATE chat_jobs SET status='queued',updated=? "
                    "WHERE id=? AND status='running' AND cancel_requested=0",
                    (time.time(), job_id),
                ).rowcount
                cancelled = False if changed else self._cancel_chat_if_requested(db, job_id)
            if cancelled:
                with self.chat_dispatch_lock:
                    self.chat_dispatch.pop(job_id, None)
                return True
            if not changed:
                self._finish_chat(job_id, "failed", "対話の実行状態を確認できませんでした")
                return True
            return False
        except HTTPException as exc:
            with self.lock:
                self.last_chat_user = row["user_id"]
            detail = (
                "ログイン状態が変わりました。再度ログインして送信してください"
                if exc.status_code in {401, 403}
                else str(exc.detail)
            )
            self._finish_chat(job_id, "failed", detail)
            return True
        except Exception:
            with self.lock:
                self.last_chat_user = row["user_id"]
            self._finish_chat(job_id, "failed", "対話の処理中に問題が発生しました")
            return True
        # A busy-slot retry has not consumed a turn. Other completed attempts,
        # including cooperative cancellation, have occupied the worker turn.
        with self.lock:
            self.last_chat_user = row["user_id"]
        # send() commits completion with its answer atomically; a cancellation
        # winner commits no message. Drop the process-local dispatch either way.
        with self.chat_dispatch_lock:
            self.chat_dispatch.pop(job_id, None)
        return True

    def process_next_chat(self) -> bool:
        """Run at most one queued dialogue; called by the background worker loop."""
        kind, row, dispatch = self._claim_chat_turn(self.last_chat_user)
        if kind == "nothing":
            return False
        if kind == "handled":
            return True
        assert row is not None and dispatch is not None
        return self._run_chat_job(row, dispatch, row["id"])

    def process_next_chat_batch(self, limit: int) -> list[str]:
        """Claim up to ``limit`` queued dialogues and run them concurrently.

        Claims are made one at a time in the shared fair-share order, so the
        last-served user still yields to waiting users and creation order is
        otherwise kept; only the model execution overlaps between entries.
        Callers pass the number of free model slots: at most ``limit`` entries
        leave the queue, and an entry never starts while its turn is not due.
        An entry whose generation raises is failed in place and cannot affect
        the other entries or hold a slot.

        Returns the started job ids in claim order.
        """
        if limit < 1:
            return []
        claims: list[tuple[Any, ChatDispatch]] = []
        last_user = self.last_chat_user
        while len(claims) < limit:
            kind, row, dispatch = self._claim_chat_turn(last_user)
            if kind == "nothing":
                break
            if kind == "handled":
                # The expired or restart-swept entry was failed in place; keep
                # looking so one stale entry cannot starve the rest of the line.
                continue
            assert row is not None and dispatch is not None
            claims.append((row, dispatch))
            last_user = row["user_id"]
        if not claims:
            return []

        def run(row: Any, dispatch: ChatDispatch) -> None:
            self._run_chat_job(row, dispatch, row["id"])

        threads = [threading.Thread(target=run, args=(row, dispatch)) for row, dispatch in claims]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return [row["id"] for row, _ in claims]

    def _fail_chat(self, db: StorageConnection, job: str, detail: str) -> None:
        changed = db.execute(
            "UPDATE chat_jobs SET status='failed',updated=?,detail=? "
            "WHERE id=? AND status='queued'",
            (time.time(), detail, job),
        ).rowcount
        if changed:
            # A no-op (already cancelled or finished elsewhere) is not a failure.
            self._audit(db, "worker", "chat.failed", job)
        with self.chat_dispatch_lock:
            self.chat_dispatch.pop(job, None)

    def _finish_chat(self, job: str, status: str, detail: str, message: str | None = None) -> None:
        with self.db() as db:
            row = db.execute(
                "SELECT cancel_requested FROM chat_jobs WHERE id=? AND status='running'",
                (job,),
            ).fetchone()
            if not row:
                changed = 0
            elif row["cancel_requested"]:
                changed = self._cancel_chat_if_requested(db, job)
            else:
                changed = db.execute(
                    "UPDATE chat_jobs SET status=?,updated=?,detail=?,message_id=? "
                    "WHERE id=? AND status='running' AND cancel_requested=0",
                    (status, time.time(), detail, message, job),
                ).rowcount
                if changed:
                    self._audit(db, "worker", f"chat.{status}", job)
        with self.chat_dispatch_lock:
            self.chat_dispatch.pop(job, None)

    def roles(self, actor: Principal, project: str) -> Json:
        with self.db() as db:
            self.require(db, actor, project, "manage_roles")
            return {
                "templates": [
                    {"id": name, "name": name, "permissions": sorted(permissions)}
                    for name, permissions in ROLE_PERMISSIONS.items()
                ],
                "custom": [
                    {
                        **{key: row[key] for key in row.keys() if key != "denied_permissions"},
                        "permissions": json.loads(row["permissions"]),
                        **(
                            {"denied_permissions": json.loads(row["denied_permissions"])}
                            if json.loads(row["denied_permissions"])
                            else {}
                        ),
                    }
                    for row in db.execute("SELECT * FROM roles WHERE project_id=?", (project,))
                ],
                "allowed_permissions": sorted(self._permission_ceiling(db, actor, project)),
            }

    def create_role(
        self,
        actor: Principal,
        project: str,
        name: str,
        permissions: list[str],
        denied_permissions: list[str] | None = None,
    ) -> Json:
        with self.db() as db:
            self.require(db, actor, project, "manage_roles")
            if not set(permissions) <= NON_ADMIN or not set(
                permissions
            ) <= self._permission_ceiling(db, actor, project):
                fail(422, "本人の委任上限内の非管理権限だけを指定できます")
            denied = set(denied_permissions or [])
            if not denied <= ALL_PERMISSIONS:
                fail(422, "不明な拒否権限です")
            # Denials only remove permissions, so any known permission may be denied;
            # the non-admin ceiling applies to grants, not to reductions in access.
            if "retrieve" in permissions and "read" not in permissions:
                fail(422, "チャット参照には閲覧権限も必要です")
            role_id = uid()
            try:
                db.execute(
                    "INSERT INTO roles (id,project_id,name,permissions,denied_permissions) "
                    "VALUES (?,?,?,?,?)",
                    (
                        role_id,
                        project,
                        name,
                        json.dumps(sorted(set(permissions))),
                        json.dumps(sorted(denied)),
                    ),
                )
            except StorageIntegrityError:
                fail(409, "ロール名は使用済みです")
            self._audit(db, actor.id, "role.create", role_id)
            result = {"id": role_id, "name": name, "permissions": sorted(set(permissions))}
            if denied:
                result["denied_permissions"] = sorted(denied)
            return result

    def update_role(
        self,
        actor: Principal,
        project: str,
        role_id: str,
        name: str,
        permissions: list[str],
        denied_permissions: list[str] | None = None,
    ) -> Json:
        with self.db() as db:
            self.require(db, actor, project, "manage_roles")
            if (
                role_id in ROLE_PERMISSIONS
                or not db.execute(
                    "SELECT id FROM roles WHERE id=? AND project_id=?", (role_id, project)
                ).fetchone()
            ):
                fail(404, "ロールが見つかりません")
            if not set(permissions) <= NON_ADMIN or not set(
                permissions
            ) <= self._permission_ceiling(db, actor, project):
                fail(422, "本人の委任上限内の非管理権限だけを指定できます")
            existing = db.execute(
                "SELECT denied_permissions FROM roles WHERE id=? AND project_id=?",
                (role_id, project),
            ).fetchone()
            denied = set(
                json.loads(existing["denied_permissions"])
                if denied_permissions is None
                else denied_permissions
            )
            if not denied <= ALL_PERMISSIONS:
                fail(422, "不明な拒否権限です")
            if "retrieve" in permissions and "read" not in permissions:
                fail(422, "チャット参照には閲覧権限も必要です")
            try:
                db.execute(
                    "UPDATE roles SET name=?,permissions=?,denied_permissions=? "
                    "WHERE id=? AND project_id=?",
                    (
                        name,
                        json.dumps(sorted(set(permissions))),
                        json.dumps(sorted(denied)),
                        role_id,
                        project,
                    ),
                )
            except StorageIntegrityError:
                fail(409, "ロール名は使用済みです")
            self._audit(db, actor.id, "role.update", role_id)
            result = {"id": role_id, "name": name, "permissions": sorted(set(permissions))}
            if denied:
                result["denied_permissions"] = sorted(denied)
            return result

    def record_model_discovery(self, actor: Principal, complete: bool) -> None:
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        with self.db() as db:
            self._audit(
                db,
                actor.id,
                "model.discover",
                "local-model-catalog",
                "complete" if complete else "partial",
            )

    def _verify_audit_chain(self, db: StorageConnection) -> Json:
        head = db.execute(
            "SELECT row_count, head_hash FROM audit_chain_head WHERE id = 1"
        ).fetchone()
        audit_count = db.execute("SELECT COUNT(*) AS count FROM audit").fetchone()["count"]
        chain_count = db.execute("SELECT COUNT(*) AS count FROM audit_chain").fetchone()["count"]

        if head is None:
            if audit_count == 0 and chain_count == 0:
                return {"ok": True, "checked": 0, "first_bad_id": None, "reason": "ok"}
            return {
                "ok": False,
                "checked": 0,
                "first_bad_id": None,
                "reason": "chain not provisioned",
            }

        expected_count = int(head["row_count"])
        if audit_count != expected_count or chain_count != expected_count:
            if audit_count < expected_count or chain_count < expected_count:
                missing = db.execute(
                    "SELECT c.seq, c.audit_id FROM audit_chain c "
                    "LEFT JOIN audit a ON a.id = c.audit_id "
                    "WHERE a.id IS NULL ORDER BY c.seq ASC"
                ).fetchall()
                if missing:
                    first_missing = int(missing[0]["seq"])
                    contiguous_tail = first_missing == expected_count - len(missing) + 1 and all(
                        int(row["seq"]) == first_missing + index
                        for index, row in enumerate(missing)
                    )
                    reason = "tail truncation" if contiguous_tail else "missing"
                    first_bad = str(missing[0]["audit_id"])
                else:
                    reason = "tail truncation"
                    first_bad = None
                return {
                    "ok": False,
                    "checked": min(audit_count, chain_count, expected_count),
                    "first_bad_id": first_bad,
                    "reason": reason,
                }
            extra = db.execute(
                "SELECT id FROM audit WHERE id NOT IN (SELECT audit_id FROM audit_chain) "
                "ORDER BY at ASC, id ASC LIMIT 1"
            ).fetchone()
            return {
                "ok": False,
                "checked": expected_count,
                "first_bad_id": str(extra["id"]) if extra is not None else None,
                "reason": "insertion",
            }

        rows = db.execute(
            "SELECT c.audit_id AS chain_audit_id, c.seq, c.prev_hash, c.row_hash, "
            "a.id, a.at, a.actor_id, a.operation, a.target_id, a.outcome "
            "FROM audit_chain c LEFT JOIN audit a ON a.id = c.audit_id "
            "ORDER BY c.seq ASC"
        ).fetchall()
        if len(rows) != expected_count:
            return {
                "ok": False,
                "checked": len(rows),
                "first_bad_id": None,
                "reason": "missing",
            }

        prev_hash = AUDIT_CHAIN_GENESIS
        for index, row in enumerate(rows, start=1):
            seq = int(row["seq"])
            if seq != index:
                return {
                    "ok": False,
                    "checked": index - 1,
                    "first_bad_id": str(row["chain_audit_id"]),
                    "reason": "insertion",
                }
            if row["id"] is None:
                return {
                    "ok": False,
                    "checked": index - 1,
                    "first_bad_id": str(row["chain_audit_id"]),
                    "reason": "missing",
                }
            if str(row["prev_hash"]) != prev_hash:
                return {
                    "ok": False,
                    "checked": index - 1,
                    "first_bad_id": str(row["id"]),
                    "reason": "content mismatch",
                }
            expected_hash = _audit_hash_payload(
                prev_hash,
                row["id"],
                row["at"],
                row["actor_id"],
                row["operation"],
                row["target_id"],
                row["outcome"],
            )
            if str(row["row_hash"]) != expected_hash:
                return {
                    "ok": False,
                    "checked": index - 1,
                    "first_bad_id": str(row["id"]),
                    "reason": "content mismatch",
                }
            prev_hash = str(row["row_hash"])

        if prev_hash != str(head["head_hash"]):
            return {
                "ok": False,
                "checked": expected_count,
                "first_bad_id": None,
                "reason": "content mismatch",
            }

        extra = db.execute(
            "SELECT id FROM audit WHERE id NOT IN (SELECT audit_id FROM audit_chain) "
            "ORDER BY at ASC, id ASC LIMIT 1"
        ).fetchone()
        if extra is not None:
            return {
                "ok": False,
                "checked": expected_count,
                "first_bad_id": str(extra["id"]),
                "reason": "insertion",
            }

        return {
            "ok": True,
            "checked": expected_count,
            "first_bad_id": None,
            "reason": "ok",
        }

    def verify_audit_chain(self, actor: Principal) -> Json:
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        with self.db() as db:
            return self._verify_audit_chain(db)

    def audit(self, actor: Principal) -> list[Json]:
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        with self.db() as db:
            return [
                dict(row) for row in db.execute("SELECT * FROM audit ORDER BY at DESC LIMIT 200")
            ]

    def get_login_history(self, actor: Principal, limit: int = 200) -> list[Json]:
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        limit = max(1, min(limit, 200))
        with self.db() as db:
            rows = db.execute(
                "SELECT id, at, user_id, outcome, peer, user_agent FROM login_events "
                "ORDER BY at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {
                    "at": row["at"],
                    "outcome": row["outcome"],
                    "peer": row["peer"],
                    "user_agent": row["user_agent"],
                    "username": (
                        db.execute(
                            "SELECT username FROM users WHERE id=?", (row["user_id"],)
                        ).fetchone()["username"]
                        if row["user_id"]
                        else None
                    ),
                }
                for row in rows
            ]

    def users(self, actor: Principal) -> list[Json]:
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        with self.db() as db:
            return [
                self._public_user(row) | {"enabled": bool(row["enabled"])}
                for row in db.execute("SELECT * FROM users ORDER BY username")
            ]

    def set_user_enabled(self, token: str | None, user_id: str, enabled: bool) -> Json:
        with self.db() as db:
            # Bind authorization to a live session inside the serialized mutation transaction.
            actor = self._authenticate(db, token)
            if not actor.system_admin:
                fail(403, "管理権限が必要です")
            self._limit("account-toggle:" + actor.id, 30)
            user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not user:
                fail(404, "利用者が見つかりません")
            if user_id == actor.id and not enabled:
                fail(422, "自分のアカウントは無効にできません")
            db.execute("UPDATE users SET enabled=? WHERE id=?", (int(enabled), user_id))
            if not enabled:
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            self._audit(db, actor.id, "account.enable" if enabled else "account.disable", user_id)
            return self._public_user(user) | {"enabled": enabled}

    # --- Data retention notice and admin-only manual deletion (DATA-015) -------

    def _retention_now(self) -> float:
        """Retention clock boundary; Unix epoch seconds in the SQLite prototype."""
        return time.time()

    def _valid_retention_now(self) -> float:
        try:
            now = self._retention_now()
        except Exception:
            fail(503, "現在時刻を検証できないため保存期間判定を停止しました")
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(now)
            or now < 0
        ):
            fail(503, "現在時刻を検証できないため保存期間判定を停止しました")
        return float(now)

    def _authenticate_system_admin(self, db: StorageConnection, token: str | None) -> Principal:
        if not token:
            fail(403, "管理権限が必要です")
        try:
            actor = self._authenticate(db, token)
        except HTTPException as exc:
            if exc.status_code == 401:
                fail(403, "管理権限が必要です")
            raise
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        return actor

    def set_retention_days(
        self,
        days: int | Callable[[], int],
        *,
        actor: Principal | None = None,
        session_token: str | None = None,
    ) -> Json:
        with self.lock:
            with self.db() as db:
                if session_token is not None:
                    current = self._authenticate_system_admin(db, session_token)
                    actor_id = current.id
                elif actor is not None:
                    if not actor.system_admin:
                        fail(403, "管理権限が必要です")
                    actor_id = actor.id
                else:
                    actor_id = "system"
                resolved = days() if callable(days) else days
                if (
                    isinstance(resolved, bool)
                    or not isinstance(resolved, int)
                    or not MIN_RETENTION_DAYS <= resolved <= MAX_RETENTION_DAYS
                ):
                    fail(
                        422,
                        f"保存期間は{MIN_RETENTION_DAYS}〜{MAX_RETENTION_DAYS}日の整数で指定してください",
                    )
                self._audit(db, actor_id, "retention.configure", str(resolved))
            self.retention_days = resolved
            return {"retention_days": self.retention_days}

    def retention_status(self, token: str | None) -> Json:
        """Return expired item counts and metadata-only listings for system_admin.

        Expiry rule (inclusive boundary):
        ``base_timestamp + retention_days * 86400 <= _retention_now()``.
        Never returns document content, chunk text, message text, or generated answers.
        """
        with self.db() as db:
            actor = self._authenticate_system_admin(db, token)
            self._limit("retention-read:" + actor.id, 60)
            now = self._valid_retention_now()
            window = self.retention_days * SECONDS_PER_DAY
            doc_rows = db.execute(
                "SELECT id, name, created FROM documents WHERE created + ? <= ? "
                "ORDER BY created ASC, id ASC",
                (window, now),
            ).fetchall()
            conv_rows = db.execute(
                "SELECT id, created FROM conversations WHERE created + ? <= ? "
                "ORDER BY created ASC, id ASC",
                (window, now),
            ).fetchall()
            audit_count = int(
                db.execute(
                    "SELECT COUNT(*) FROM audit WHERE at + ? <= ?",
                    (window, now),
                ).fetchone()[0]
            )
            return {
                "retention_days": self.retention_days,
                "counts": {
                    "documents": len(doc_rows),
                    "conversations": len(conv_rows),
                    "audit": audit_count,
                },
                "items": {
                    "documents": [
                        {
                            "id": str(row["id"]),
                            "name": str(row["name"]),
                            "created": float(row["created"]),
                            "expires": float(row["created"]) + window,
                        }
                        for row in doc_rows
                    ],
                    "conversations": [
                        {
                            "id": str(row["id"]),
                            "name": str(row["id"]),
                            "created": float(row["created"]),
                            "expires": float(row["created"]) + window,
                        }
                        for row in conv_rows
                    ],
                },
            }

    def _retention_inflight_refusal(self, db: StorageConnection, conversation_id: str) -> None:
        """DATA-015 decided rule: refuse retention deletion while a conversation is mid-work.

        Applied both when an admin deletes a conversation directly and when an
        explicitly named document belongs to that conversation (attachments share
        the conversation's mid-work state, so a `ready` attachment still cannot be
        removed while the conversation has a queued/running chat job).
        """
        active_job = db.execute(
            "SELECT 1 FROM chat_jobs WHERE conversation_id=? AND status IN ('queued','running')",
            (conversation_id,),
        ).fetchone()
        if active_job is not None:
            fail(409, "応答処理中の会話は完了後に削除してください")
        active_att = db.execute(
            "SELECT 1 FROM documents WHERE conversation_id=? "
            "AND status IN ('queued','scanning','indexing')",
            (conversation_id,),
        ).fetchone()
        if active_att is not None:
            fail(409, "取り込み処理中の添付を含む会話は完了後に削除してください")

    def delete_expired_retention(
        self,
        token: str | None,
        *,
        document_ids: list[str] | None = None,
        conversation_ids: list[str] | None = None,
        body: Callable[[], dict[str, Any]] | None = None,
    ) -> Json:
        """Manually delete explicitly named expired documents and conversations.

        Audit rows are never deletable here (T-PH7-214 owns audit chain truncation).
        In-flight documents (queued/scanning/indexing) and conversations with active
        chat jobs (queued/running) or in-flight attachments are refused with 409
        until their work completes.
        """
        with self.db() as db:
            actor = self._authenticate_system_admin(db, token)
            self._limit("retention-delete:" + actor.id, 30)
            if body is not None:
                parsed = body()
                resolved_docs = list(parsed["document_ids"])
                resolved_convs = list(parsed["conversation_ids"])
            else:
                resolved_docs = list(document_ids or [])
                resolved_convs = list(conversation_ids or [])

            if not resolved_docs and not resolved_convs:
                fail(422, "削除対象の識別子を1件以上指定してください")
            if len(set(resolved_docs)) != len(resolved_docs) or len(set(resolved_convs)) != len(
                resolved_convs
            ):
                fail(422, "重複しない識別子を指定してください")

            now = self._valid_retention_now()
            window = self.retention_days * SECONDS_PER_DAY

            for doc_id in resolved_docs:
                if not isinstance(doc_id, str) or not doc_id.strip():
                    fail(422, "削除対象の資料IDを確認してください")
                row = db.execute(
                    "SELECT id, created, status, conversation_id FROM documents WHERE id=?",
                    (doc_id,),
                ).fetchone()
                if row is None:
                    fail(422, "指定された期限到来資料が見つかりません")
                if float(row["created"]) + window > now:
                    fail(422, "保存期間が満了していない資料は削除できません")
                if row["status"] in {"queued", "scanning", "indexing"}:
                    fail(409, "取り込み処理中の資料は完了後に削除してください")
                # A document that belongs to a conversation inherits that
                # conversation's mid-work state, so an attachment that already
                # reached `ready` is still refused while its conversation is busy.
                if row["conversation_id"]:
                    self._retention_inflight_refusal(db, str(row["conversation_id"]))

            dispatches_to_drop: list[str] = []
            for conv_id in resolved_convs:
                if not isinstance(conv_id, str) or not conv_id.strip():
                    fail(422, "削除対象の会話IDを確認してください")
                row = db.execute(
                    "SELECT id, created FROM conversations WHERE id=?",
                    (conv_id,),
                ).fetchone()
                if row is None:
                    fail(422, "指定された期限到来会話が見つかりません")
                if float(row["created"]) + window > now:
                    fail(422, "保存期間が満了していない会話は削除できません")
                self._retention_inflight_refusal(db, conv_id)
                job_rows = db.execute(
                    "SELECT id FROM chat_jobs WHERE conversation_id=?",
                    (conv_id,),
                ).fetchall()
                dispatches_to_drop.extend(str(job["id"]) for job in job_rows)

            for doc_id in resolved_docs:
                db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
                self._audit(db, actor.id, "retention.delete", doc_id)

            for conv_id in resolved_convs:
                db.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
                self._audit(db, actor.id, "retention.delete", conv_id)

            if dispatches_to_drop:
                with self.chat_dispatch_lock:
                    for job_id in dispatches_to_drop:
                        self.chat_dispatch.pop(job_id, None)

            return {
                "deleted": {
                    "document_ids": resolved_docs,
                    "conversation_ids": resolved_convs,
                }
            }
