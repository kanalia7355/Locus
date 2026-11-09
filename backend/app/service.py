"""Transactional prototype services; production adapters remain undecided."""

import hashlib
import json
import math
import re
import secrets
import sqlite3
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

from app.scanner import UNAVAILABLE, ScanResult

Json = dict[str, Any]
PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
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


def fail(status: int, detail: str) -> NoReturn:
    raise HTTPException(status, detail)


class ModelBusy(Exception):
    """Raised when the single model slot is occupied; the caller may enqueue instead."""


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


class UnavailableScanner:
    def scan(self, content: str) -> ScanResult:
        return UNAVAILABLE


class Service:
    def __init__(self, path: Path, *, scanner: Scanner | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.lock = threading.RLock()
        self.scanner = scanner or UnavailableScanner()
        # Fail-closed visibility: only an adapter that can actually perform the
        # safety check counts as configured; the placeholder always quarantines.
        self.scanner_configured = not isinstance(self.scanner, UnavailableScanner)
        # Operational outcome of the most recent scan, reported separately from
        # adapter configuration: None means no scan has run yet.
        self.scanner_last_outcome: str | None = None
        self.limits: OrderedDict[str, list[float]] = OrderedDict()
        self.chat_dispatch: dict[str, ChatDispatch] = {}
        self.chat_dispatch_lock = threading.Lock()
        self.dummy_hash = PASSWORDS.hash(secrets.token_urlsafe(32))
        self.conn.executescript("""
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
        """)
        chat_job_columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(chat_jobs)")
        }
        if "cancel_requested" not in chat_job_columns:
            self.conn.execute(
                "ALTER TABLE chat_jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0"
            )
        # Additive migrations preserve databases created before concurrent role holdings.
        self._ensure_column("memberships", "denied_permissions", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column("roles", "denied_permissions", "TEXT NOT NULL DEFAULT '[]'")
        self.conn.execute(
            "INSERT OR IGNORE INTO membership_roles (user_id,project_id,role) "
            "SELECT user_id,project_id,role FROM memberships"
        )

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @contextmanager
    def db(self) -> Iterator[sqlite3.Connection]:
        with self.lock:
            # Include authorization SELECTs in the same write-serialized unit as publication.
            # The connection context alone begins only at first DML in legacy sqlite3 mode.
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
            except BaseException:
                self.conn.rollback()
                raise
            else:
                self.conn.commit()

    def recover_jobs(self) -> None:
        """Called only at application-worker startup, never by provisioning CLI connections."""
        with self.db() as db:
            db.execute("UPDATE documents SET status='queued' WHERE status='scanning'")
            # Queued dialogues were held only in this process; their dispatch closures
            # no longer exist after a restart, so they fail visibly instead of hanging.
            db.execute(
                "UPDATE chat_jobs SET status='failed',updated=?,detail=? "
                "WHERE status IN ('queued','running')",
                (time.time(), "アプリケーションの再起動により中止しました。再度送信してください"),
            )
            self.chat_dispatch.clear()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def _audit(
        self, db: sqlite3.Connection, actor: str, operation: str, target: str, outcome: str = "ok"
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
        db: sqlite3.Connection,
        username: str,
        password: str,
        *,
        system_admin: bool = False,
        audit_actor: str,
    ) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{2,63}", username):
            fail(422, "利用者IDは3〜64文字の英数字・_.-で指定してください")
        if not 14 <= len(password) <= 128:
            fail(422, "仮パスワードは14〜128文字で指定してください")
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
        except sqlite3.IntegrityError:
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
            temporary_password = secrets.token_urlsafe(24)
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
        self, db: sqlite3.Connection, user_id: str, project_id: str, role: str
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
            except sqlite3.IntegrityError:
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
                "accepted_formats": ["txt", "md", "csv"],
                "max_file_bytes": 262144,
                "scanner_configured": self.scanner_configured,
                "scanner_last_outcome": self.scanner_last_outcome,
                "ingestion_queue_limit": 32,
                "per_user_ingestion_queue_limit": 4,
                "ingestion_status_counts": counts,
                "configuration_available": False,
            }

    def _project_member_mutation(
        self,
        db: sqlite3.Connection,
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

    def load_status(self, actor: Principal, *, model_busy: bool, model_enabled: bool) -> Json:
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        with self.db() as db:
            queued = db.execute("SELECT COUNT(*) FROM chat_jobs WHERE status='queued'").fetchone()[
                0
            ]
            running = db.execute(
                "SELECT j.id,u.username,j.updated FROM chat_jobs j "
                "LEFT JOIN users u ON u.id=j.user_id WHERE j.status='running' "
                "ORDER BY j.created,j.id LIMIT 1"
            ).fetchone()
            return {
                "model_slot": {
                    "enabled": model_enabled,
                    "busy": model_busy,
                },
                "chat_queue": {
                    "queued": queued,
                    "limit": CHAT_QUEUE_LIMIT,
                    "per_user_limit": CHAT_USER_QUEUE_LIMIT,
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

    def _session(self, db: sqlite3.Connection, user_id: str, rotation: bool) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        db.execute("DELETE FROM sessions WHERE expires < ? OR last_seen < ?", (now, now - 1800))
        db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?)",
            (digest(token), user_id, now + 28800, now, int(rotation)),
        )
        return token

    def login(self, username: str, password: str, peer: str) -> tuple[str, Json]:
        with self.db() as db:
            self._limit("peer:" + peer, 20)
            self._limit("user:" + digest(username), 5)
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            valid = False
            try:
                valid = PASSWORDS.verify(
                    user["password_hash"] if user else self.dummy_hash, password
                )
            except VerificationError:
                pass
            if (
                not user
                or not valid
                or not user["enabled"]
                or (
                    user["must_rotate"]
                    and (user["temp_used"] or user["temp_expires"] < time.time())
                )
            ):
                # Do not expose whether an account exists.
                fail(401, "利用者IDまたはパスワードを確認してください")
            if user["must_rotate"]:
                db.execute("UPDATE users SET temp_used=1 WHERE id=?", (user["id"],))
            token = self._session(db, user["id"], bool(user["must_rotate"]))
            self._audit(db, user["id"], "session.start", user["id"])
            return token, self._public_user(user)

    @staticmethod
    def _public_user(user: sqlite3.Row) -> Json:
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
        self, db: sqlite3.Connection, token: str | None, *, allow_rotation: bool = False
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
        if len(new) < 14 or len(new) > 128 or current == new:
            fail(422, "異なる14〜128文字のパスワードを設定してください")
        with self.db() as db:
            if session_token is not None:
                session_actor = self._authenticate(db, session_token, allow_rotation=True)
                if session_actor.id != principal.id:
                    fail(401, "ログインしてください")
            self._limit("rotate:" + principal.id, 5)
            user = db.execute("SELECT * FROM users WHERE id=?", (principal.id,)).fetchone()
            if not user or not user["enabled"]:
                fail(401, "ログインしてください")
            try:
                PASSWORDS.verify(user["password_hash"], current)
            except VerificationError:
                fail(401, "現在のパスワードを確認してください")
            if user["must_rotate"] and user["temp_expires"] <= time.time():
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
            if not 14 <= len(new_password) <= 128:
                fail(422, "異なる14〜128文字のパスワードを設定してください")
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

    def logout(self, token: str | None) -> None:
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token or ""),))

    def _membership(self, db: sqlite3.Connection, actor: Principal, project: str) -> sqlite3.Row:
        row = db.execute(
            "SELECT m.*,p.org_id,p.name FROM memberships m JOIN projects p "
            "ON p.id=m.project_id WHERE m.user_id=? AND m.project_id=?",
            (actor.id, project),
        ).fetchone()
        if not row:
            fail(404, "対象が見つかりません")
        return row  # type: ignore[no-any-return]

    def _held_roles(self, db: sqlite3.Connection, user_id: str, project: str) -> list[str]:
        rows = db.execute(
            "SELECT role FROM membership_roles WHERE user_id=? AND project_id=? ORDER BY role",
            (user_id, project),
        ).fetchall()
        # Legacy memberships are copied into this table during startup migration. An empty
        # normalized set therefore stays permissionless rather than resurrecting stale roles.
        return [row["role"] for row in rows]

    def _role_permissions(
        self, db: sqlite3.Connection, role: str, project: str
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
        self, db: sqlite3.Connection, user_id: str, project: str
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
        db: sqlite3.Connection,
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
        except (HTTPException, sqlite3.Error, ValueError, TypeError):
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
        self, db: sqlite3.Connection, actor: Principal, project: str
    ) -> set[str]:
        try:
            user = db.execute("SELECT enabled FROM users WHERE id=?", (actor.id,)).fetchone()
        except (sqlite3.Error, ValueError, TypeError):
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
        except (sqlite3.Error, ValueError, TypeError, OverflowError):
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

    def _permissions(
        self, db: sqlite3.Connection, actor: Principal, project: str
    ) -> frozenset[str]:
        allowed, denied, _roles = self._role_access(db, actor.id, project)
        allowed.update(self._delegated_permissions(db, actor, project))
        # Explicit deny wins over every role and delegation allow. Membership is still
        # independently required by _role_access, even when a grant otherwise matches.
        effective = allowed - denied
        if "read" not in effective:
            effective.discard("retrieve")
        return frozenset(effective)

    def _permission_ceiling(
        self, db: sqlite3.Connection, actor: Principal, project: str
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
        self, db: sqlite3.Connection, actor: Principal, project: str
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
        self, db: sqlite3.Connection, grantor_id: str, project: str
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
        self, db: sqlite3.Connection, actor: Principal, project: str, permission: str
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
                "effective_permissions": sorted(
                    self._permissions(
                        db,
                        Principal(target["id"], username, False, False),
                        project,
                    )
                ),
            }

    def _conversation(
        self, db: sqlite3.Connection, actor: Principal, conversation: str
    ) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM conversations WHERE id=? AND owner_id=?", (conversation, actor.id)
        ).fetchone()
        if not row:
            fail(404, "会話が見つかりません")
        self.require(db, actor, row["project_id"], "retrieve")
        return row  # type: ignore[no-any-return]

    def _can_read(
        self,
        db: sqlite3.Connection,
        actor: Principal,
        row: sqlite3.Row,
        operation: str = "read",
        conversation: str | None = None,
    ) -> bool:
        try:
            self.require(db, actor, row["project_id"], operation)
        except HTTPException:
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
        db: sqlite3.Connection,
        actor: Principal,
        document: str,
        conversation: str | None = None,
    ) -> sqlite3.Row:
        row = db.execute("SELECT * FROM documents WHERE id=?", (document,)).fetchone()
        if not row or not self._can_read(db, actor, row, conversation=conversation):
            fail(404, "資料が見つかりません")
        return row  # type: ignore[no-any-return]

    def _managed_document(
        self,
        db: sqlite3.Connection,
        actor: Principal,
        document: str,
    ) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM documents WHERE id=? AND owner_id=?",
            (document, actor.id),
        ).fetchone()
        if not row:
            fail(404, "資料が見つかりません")
        self.require(db, actor, row["project_id"], "upload")
        if row["kind"] == "attachment":
            self._conversation(db, actor, row["conversation_id"])
        return row  # type: ignore[no-any-return]

    @staticmethod
    def _metadata(row: sqlite3.Row, actor_id: str) -> Json:
        data = {
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
            )
        }
        return {**data, "owned": row["owner_id"] == actor_id}

    def documents(self, actor: Principal, project: str) -> list[Json]:
        with self.db() as db:
            self.require(db, actor, project, "read")
            return [
                self._metadata(row, actor.id)
                for row in db.execute(
                    "SELECT * FROM documents WHERE project_id=? ORDER BY created DESC",
                    (project,),
                ).fetchall()
                if self._can_read(db, actor, row)
                or (
                    row["owner_id"] == actor.id
                    and row["kind"] == "shared"
                    and "upload" in self._permissions(db, actor, project)
                )
            ]

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

            source_terms: dict[str, sqlite3.Row] = {}
            for chunk in db.execute(
                "SELECT * FROM chunks WHERE document_id=? ORDER BY page,ordinal", (document,)
            ).fetchall():
                for word in terms(chunk["text"]):
                    source_terms.setdefault(word, chunk)
            results: list[Json] = []
            for candidate in db.execute(
                "SELECT id,owner_id,project_id,kind,name,status,reason,conversation_id,"
                "grants,created "
                "FROM documents WHERE project_id=? AND status='ready' AND id<>? "
                "ORDER BY id",
                (source["project_id"], document),
            ).fetchall():
                if not self._can_read(
                    db, actor, candidate, "retrieve", conversation
                ) or not self._can_read(db, actor, candidate, "read", conversation):
                    continue
                matches: dict[str, sqlite3.Row] = {}
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

    def upload(
        self,
        actor: Principal,
        project: str,
        name: str,
        content: str,
        kind: str,
        conversation: str | None = None,
    ) -> Json:
        if (
            not name
            or len(name) > 160
            or any(c in name for c in "/\\:\x00")
            or name.startswith(".")
            or Path(name).suffix.lower() not in {".txt", ".md", ".csv"}
            or any(ord(c) < 32 for c in name)
        ):
            fail(422, "対応形式はUTF-8のtxt・md・csvです。安全なファイル名を指定してください")
        if (
            not content.strip()
            or len(content.encode("utf-8")) > 262144
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
            queued = db.execute(
                "SELECT COUNT(*) FROM documents WHERE status IN ('queued','scanning')"
            ).fetchone()[0]
            owned = db.execute(
                "SELECT COUNT(*) FROM documents WHERE owner_id=? AND status "
                "IN ('queued','scanning')",
                (actor.id,),
            ).fetchone()[0]
            if queued >= 32 or owned >= 4:
                fail(429, "取り込み待ちが上限です。完了後に再試行してください")
            total = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            personal = db.execute(
                "SELECT COUNT(*) FROM documents WHERE owner_id=?", (actor.id,)
            ).fetchone()[0]
            if total >= 1000 or personal >= 100:
                fail(429, "検証環境の資料数上限です。不要な資料を削除してください")
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

    def _ingestion_allowed(self, db: sqlite3.Connection, document: sqlite3.Row) -> bool:
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
        return True

    def process_next(self) -> bool:
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM documents WHERE status='queued' ORDER BY created LIMIT 1"
            ).fetchone()
            if not row:
                return False
            # Recheck queued work BEFORE exposing content to a scanner adapter.
            if not self._ingestion_allowed(db, row):
                db.execute(
                    "UPDATE documents SET status='cancelled',reason=? WHERE id=?",
                    ("登録者の利用権限が失効しました", row["id"]),
                )
                return True
            db.execute("UPDATE documents SET status='scanning' WHERE id=?", (row["id"],))
        try:
            outcome = self.scanner.scan(row["content"]).outcome
        except Exception:
            # A configured adapter that raises still fails closed; the check
            # simply could not run, which is not a rejection verdict.
            outcome = "unavailable"
        self.scanner_last_outcome = outcome
        # Scanner runs outside the transaction. Never publish stale work after revoke/delete/cancel.
        with self.db() as db:
            live = db.execute("SELECT * FROM documents WHERE id=?", (row["id"],)).fetchone()
            if not live or live["status"] != "scanning":
                return True
            if not self._ingestion_allowed(db, live):
                db.execute(
                    "UPDATE documents SET status='cancelled',reason=? WHERE id=?",
                    ("登録者の利用権限が失効しました", row["id"]),
                )
                return True
            if outcome != "clean":
                # Fail closed for every non-clean outcome, but keep an explicit
                # rejection distinct from a check that could not run at all.
                reason = (
                    "安全検査を通過していないため隔離中です。本文は検索に使いません"
                    if outcome == "rejected"
                    else "安全検査を実行できないため隔離中です（既定拒否）。本文は検索に使いません"
                )
                db.execute(
                    "UPDATE documents SET status='quarantined',reason=? WHERE id=?",
                    (reason, row["id"]),
                )
                return True
            self._index(db, live)
            return True

    def _index(self, db: sqlite3.Connection, row: sqlite3.Row) -> None:
        db.execute("DELETE FROM chunks WHERE document_id=?", (row["id"],))
        for page, text in enumerate(row["content"].split("\f"), start=1):
            for ordinal, offset in enumerate(range(0, len(text), 700), start=1):
                db.execute(
                    "INSERT INTO chunks VALUES (?,?,?,?,?)",
                    (uid(), row["id"], page, ordinal, text[offset : offset + 700]),
                )
        db.execute("UPDATE documents SET status='ready',reason='' WHERE id=?", (row["id"],))

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
            if row["owner_id"] != actor.id or row["status"] not in {"queued", "scanning"}:
                fail(409, "この取り込みは取消できません")
            db.execute(
                "UPDATE documents SET status='cancelled',content='',reason=? WHERE id=?",
                ("利用者が取り消しました", document),
            )
            self._audit(db, actor.id, "ingestion.cancel", document)

    def _owned_attachment(
        self, db: sqlite3.Connection, actor: Principal, document: str
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

    def publish(self, actor: Principal, document: str, grants: list[Json]) -> None:
        with self.db() as db:
            row = self._managed_document(db, actor, document)
            self.require(db, actor, row["project_id"], "publish")
            if row["owner_id"] != actor.id or row["kind"] == "attachment":
                fail(403, "会話添付や他人の資料は公開できません")
            for grant in grants:
                role = grant.get("role")
                operations = grant.get("operations")
                custom = db.execute(
                    "SELECT id FROM roles WHERE id=? AND project_id=?",
                    (role, row["project_id"]),
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
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,project_id,created FROM conversations "
                    "WHERE owner_id=? AND project_id=? "
                    "ORDER BY created DESC",
                    (actor.id, project),
                ).fetchall()
            ]

    def _citations(
        self, db: sqlite3.Connection, actor: Principal, ids: list[str], conversation: str
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
        self, db: sqlite3.Connection, actor: Principal, row: sqlite3.Row, conversation: str
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

    def _cancel_chat_if_requested(self, db: sqlite3.Connection, job: str) -> bool:
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
    # One bounded, arrival-ordered line in front of the single model slot. The
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

    def process_next_chat(self) -> bool:
        """Run at most one queued dialogue; called by the background worker loop."""
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM chat_jobs WHERE status='queued' ORDER BY created,id LIMIT 1"
            ).fetchone()
            if row is None:
                return False
            if time.time() - row["created"] > CHAT_WAIT_SECONDS:
                self._fail_chat(db, row["id"], "対話の待機上限を超えました。再度送信してください")
                return True
            dispatch = self.chat_dispatch.get(row["id"])
            if dispatch is None:
                self._fail_chat(
                    db,
                    row["id"],
                    "アプリケーションの再起動により中止しました。再度送信してください",
                )
                return True
            taken = db.execute(
                "UPDATE chat_jobs SET status='running',updated=? WHERE id=? AND status='queued'",
                (time.time(), row["id"]),
            ).rowcount
            if not taken:
                return False
        job_id = row["id"]
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
            detail = (
                "ログイン状態が変わりました。再度ログインして送信してください"
                if exc.status_code in {401, 403}
                else str(exc.detail)
            )
            self._finish_chat(job_id, "failed", detail)
            return True
        except Exception:
            self._finish_chat(job_id, "failed", "対話の処理中に問題が発生しました")
            return True
        # send() commits completion with its answer atomically; a cancellation
        # winner commits no message. Drop the process-local dispatch either way.
        with self.chat_dispatch_lock:
            self.chat_dispatch.pop(job_id, None)
        return True

    def _fail_chat(self, db: sqlite3.Connection, job: str, detail: str) -> None:
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
            except sqlite3.IntegrityError:
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
            except sqlite3.IntegrityError:
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

    def audit(self, actor: Principal) -> list[Json]:
        if not actor.system_admin:
            fail(403, "管理権限が必要です")
        with self.db() as db:
            return [
                dict(row) for row in db.execute("SELECT * FROM audit ORDER BY at DESC LIMIT 200")
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
