"""Transactional prototype services; production adapters remain undecided."""

import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, Protocol
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException

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


@dataclass(frozen=True)
class Principal:
    id: str
    username: str
    system_admin: bool
    must_rotate: bool


class Scanner(Protocol):
    def scan(self, content: str) -> bool: ...


class UnavailableScanner:
    def scan(self, content: str) -> bool:
        return False


class Service:
    def __init__(self, path: Path, *, scanner: Scanner | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.lock = threading.RLock()
        self.scanner = scanner or UnavailableScanner()
        self.limits: OrderedDict[str, list[float]] = OrderedDict()
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
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, org_id TEXT NOT NULL, name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memberships (
                user_id TEXT REFERENCES users(id), project_id TEXT REFERENCES projects(id),
                role TEXT NOT NULL, PRIMARY KEY(user_id, project_id)
            );
            CREATE TABLE IF NOT EXISTS roles (
                id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id), name TEXT NOT NULL,
                permissions TEXT NOT NULL, UNIQUE(project_id, name)
            );
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
            CREATE TABLE IF NOT EXISTS audit (
                id TEXT PRIMARY KEY, at REAL NOT NULL, actor_id TEXT NOT NULL,
                operation TEXT NOT NULL, target_id TEXT NOT NULL, outcome TEXT NOT NULL
            );
        """)

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

    def provision(self, username: str, password: str, *, system_admin: bool = False) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{2,63}", username):
            fail(422, "利用者IDは3〜64文字の英数字・_.-で指定してください")
        if not 14 <= len(password) <= 128:
            fail(422, "仮パスワードは14〜128文字で指定してください")
        user_id = uid()
        with self.db() as db:
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
            self._audit(db, "local-cli", "account.provision", user_id)
        return user_id

    def create_project(self, org_id: str, project_id: str, name: str) -> None:
        with self.db() as db:
            db.execute("INSERT INTO projects VALUES (?,?,?)", (project_id, org_id, name))

    def assign(self, username: str, project_id: str, role: str | None) -> None:
        with self.db() as db:
            user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if not user:
                fail(404, "利用者が見つかりません")
            if not db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone():
                fail(404, "プロジェクトが見つかりません")
            if role is None:
                db.execute(
                    "DELETE FROM memberships WHERE user_id=? AND project_id=?",
                    (user["id"], project_id),
                )
                return
            custom = db.execute(
                "SELECT id FROM roles WHERE id=? AND project_id=?", (role, project_id)
            ).fetchone()
            if role not in ROLE_PERMISSIONS and not custom:
                fail(422, "不明なロールです")
            db.execute(
                "INSERT OR REPLACE INTO memberships VALUES (?,?,?)", (user["id"], project_id, role)
            )

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
            db.execute(
                "UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, digest(token or ""))
            )
            return Principal(
                session["user_id"],
                session["username"],
                bool(session["system_admin"]),
                bool(session["must_rotate"]),
            )

    def rotate(self, principal: Principal, current: str, new: str) -> str:
        if len(new) < 14 or len(new) > 128 or current == new:
            fail(422, "異なる14〜128文字のパスワードを設定してください")
        with self.db() as db:
            self._limit("rotate:" + principal.id, 5)
            user = db.execute("SELECT * FROM users WHERE id=?", (principal.id,)).fetchone()
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

    def _permissions(
        self, db: sqlite3.Connection, actor: Principal, project: str
    ) -> frozenset[str]:
        membership = self._membership(db, actor, project)
        role = membership["role"]
        if role in ROLE_PERMISSIONS:
            return ROLE_PERMISSIONS[role]
        row = db.execute(
            "SELECT permissions FROM roles WHERE id=? AND project_id=?", (role, project)
        ).fetchone()
        return frozenset(json.loads(row["permissions"])) if row else frozenset()

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
                {**dict(row), "permissions": sorted(self._permissions(db, actor, row["id"]))}
                for row in rows
            ]

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
        membership = self._membership(db, actor, row["project_id"])
        return any(
            g["role"] == membership["role"] and operation in g["operations"]
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

    def process_next(self) -> bool:
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM documents WHERE status='queued' ORDER BY created LIMIT 1"
            ).fetchone()
            if not row:
                return False
            db.execute("UPDATE documents SET status='scanning' WHERE id=?", (row["id"],))
        try:
            approved = self.scanner.scan(row["content"])
        except Exception:
            approved = False
        # Scanner runs outside the transaction. Never publish stale work after revoke/delete/cancel.
        with self.db() as db:
            live = db.execute("SELECT * FROM documents WHERE id=?", (row["id"],)).fetchone()
            if not live or live["status"] != "scanning":
                return True
            user = db.execute("SELECT * FROM users WHERE id=?", (live["owner_id"],)).fetchone()
            actor = Principal(
                user["id"], user["username"], bool(user["system_admin"]), bool(user["must_rotate"])
            )
            try:
                if not user["enabled"] or actor.must_rotate:
                    fail(403, "失効")
                self.require(db, actor, live["project_id"], "upload")
                if live["kind"] == "attachment":
                    self._conversation(db, actor, live["conversation_id"])
            except HTTPException:
                db.execute(
                    "UPDATE documents SET status='cancelled',reason=? WHERE id=?",
                    ("登録者の利用権限が失効しました", row["id"]),
                )
                return True
            if not approved:
                db.execute(
                    "UPDATE documents SET status='quarantined',reason=? WHERE id=?",
                    ("検査機能が未接続のため隔離中です。本文は検索に使いません", row["id"]),
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
                if (
                    role not in ROLE_PERMISSIONS
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

    def conversation(self, actor: Principal, conversation: str) -> Json:
        with self.db() as db:
            conv = self._conversation(db, actor, conversation)
            messages = [
                {
                    "id": row["id"],
                    "text": row["text"],
                    "scope": row["scope"],
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

    def send(
        self, actor: Principal, conversation: str, text: str, scope: str, attachments: list[str]
    ) -> Json:
        if scope not in {"all", "shared", "personal"}:
            fail(422, "参照範囲を確認してください")
        with self.db() as db:
            conv = self._conversation(db, actor, conversation)
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
            message = uid()
            db.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?,?)",
                (message, conversation, text, json.dumps(ids), scope, time.time()),
            )
            self._audit(db, actor.id, "retrieval.complete", conversation)
            return {
                "id": message,
                "text": text,
                "scope": scope,
                "citations": self._citations(db, actor, ids, conversation),
            }

    def delete_conversation(self, actor: Principal, conversation: str) -> None:
        with self.db() as db:
            self._conversation(db, actor, conversation)
            db.execute("DELETE FROM conversations WHERE id=?", (conversation,))
            self._audit(db, actor.id, "conversation.delete", conversation)

    def roles(self, actor: Principal, project: str) -> Json:
        with self.db() as db:
            self.require(db, actor, project, "manage_roles")
            return {
                "templates": [
                    {"id": name, "name": name, "permissions": sorted(permissions)}
                    for name, permissions in ROLE_PERMISSIONS.items()
                ],
                "custom": [
                    {**dict(row), "permissions": json.loads(row["permissions"])}
                    for row in db.execute("SELECT * FROM roles WHERE project_id=?", (project,))
                ],
                "allowed_permissions": sorted(self._permissions(db, actor, project) & NON_ADMIN),
            }

    def create_role(
        self, actor: Principal, project: str, name: str, permissions: list[str]
    ) -> Json:
        with self.db() as db:
            self.require(db, actor, project, "manage_roles")
            if not set(permissions) <= NON_ADMIN or not set(permissions) <= self._permissions(
                db, actor, project
            ):
                fail(422, "本人の許可範囲内の非管理権限だけを指定できます")
            if "retrieve" in permissions and "read" not in permissions:
                fail(422, "チャット参照には閲覧権限も必要です")
            role_id = uid()
            try:
                db.execute(
                    "INSERT INTO roles VALUES (?,?,?,?)",
                    (role_id, project, name, json.dumps(sorted(set(permissions)))),
                )
            except sqlite3.IntegrityError:
                fail(409, "ロール名は使用済みです")
            self._audit(db, actor.id, "role.create", role_id)
            return {"id": role_id, "name": name, "permissions": sorted(set(permissions))}

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
                self._public_user(row)
                for row in db.execute("SELECT * FROM users ORDER BY username")
            ]
