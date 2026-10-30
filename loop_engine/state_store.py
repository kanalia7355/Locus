"""SQLite is authoritative; transitions, claims and append-only evidence are transactional."""

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from loop_engine.models import TRANSITIONS, Task, validate_graph
from loop_engine.schemas import validate
from loop_engine.security import reject_secrets


class StateStore:
    def __init__(self, path: Path) -> None:
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("Unsafe state database path")
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY, document TEXT NOT NULL, spec_hash TEXT NOT NULL,
                    created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, goal_id TEXT REFERENCES goals(id),
                    document TEXT NOT NULL, spec_hash TEXT NOT NULL, status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
                    version INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_dependencies (
                    task_id TEXT REFERENCES tasks(id), dependency_id TEXT REFERENCES tasks(id),
                    PRIMARY KEY(task_id,dependency_id)
                );
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id), run_id TEXT NOT NULL,
                    kind TEXT NOT NULL, attempt INTEGER NOT NULL, status TEXT NOT NULL,
                    result TEXT NOT NULL, started REAL NOT NULL, finished REAL,
                    UNIQUE(task_id,kind,attempt)
                );
                CREATE TABLE IF NOT EXISTS verification_results (
                    id TEXT PRIMARY KEY, execution_id TEXT REFERENCES executions(id),
                    document TEXT NOT NULL, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id),
                    binding_hash TEXT NOT NULL, document TEXT NOT NULL, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY, task_id TEXT, category TEXT NOT NULL,
                    target_hash TEXT NOT NULL, document TEXT NOT NULL, status TEXT NOT NULL,
                    actor TEXT, reason TEXT, decided REAL, created REAL NOT NULL,
                    UNIQUE(task_id,category,target_hash)
                );
                CREATE TABLE IF NOT EXISTS pull_requests (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(id), document TEXT NOT NULL,
                    updated REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkpoints (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(id), document TEXT NOT NULL,
                    updated REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL,
                    kind TEXT NOT NULL, task_id TEXT, document TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
                    BEGIN SELECT RAISE(ABORT,'Events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
                    BEGIN SELECT RAISE(ABORT,'Events are append-only'); END;
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.rollback()
                raise
            else:
                db.commit()

    @staticmethod
    def encode(value: Any) -> str:
        reject_secrets(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def _event(self, db: sqlite3.Connection, kind: str, task: str | None, data: Any) -> None:
        db.execute(
            "INSERT INTO events(at,kind,task_id,document) VALUES (?,?,?,?)",
            (time.time(), kind, task, self.encode(data)),
        )

    def event(self, kind: str, task: str | None = None, **data: Any) -> None:
        with self.transaction() as db:
            self._event(db, kind, task, data)

    def metadata(self, key: str, default: Any = None) -> Any:
        with self.connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set_metadata(self, key: str, value: Any) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) "
                "DO UPDATE SET value=excluded.value",
                (key, self.encode(value)),
            )
            self._event(db, "control.changed", None, {"key": key})

    def import_plan(
        self,
        goal: str,
        spec_hash: str,
        tasks: list[Task],
        *,
        metadata: dict[str, Any] | None = None,
        decisions: list[dict[str, Any]] | None = None,
    ) -> str:
        validate_graph(tasks)
        if any(
            task.status not in {"planned", "ready"}
            or task.attempts
            or task.branch
            or task.worktree
            or task.version
            for task in tasks
        ):
            raise ValueError("Plans cannot assert completed work or prior executions")
        for decision in decisions or []:
            validate("decision", decision)
        self.encode(metadata or {})
        goal_id = uuid4().hex
        with self.transaction() as db:
            if db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]:
                raise ValueError("Existing plan is immutable; use a separately reviewed goal")
            db.execute(
                "INSERT INTO goals VALUES (?,?,?,?)",
                (goal_id, self.encode({"goal": goal}), spec_hash, time.time()),
            )
            for task in tasks:
                db.execute(
                    "INSERT INTO tasks VALUES (?,?,?,?,?,0,0,?)",
                    (
                        task.id,
                        goal_id,
                        self.encode(task.document()),
                        task.specification_hash(),
                        task.status,
                        time.time(),
                    ),
                )
            for task in tasks:
                for dependency in task.dependencies:
                    db.execute("INSERT INTO task_dependencies VALUES (?,?)", (task.id, dependency))
            for key, value in (metadata or {}).items():
                db.execute(
                    "INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) "
                    "DO UPDATE SET value=excluded.value",
                    (key, self.encode(value)),
                )
            for decision in decisions or []:
                db.execute(
                    "INSERT INTO decisions VALUES (?,?,?,?,?,'pending',NULL,NULL,NULL,?)",
                    (
                        decision["id"],
                        decision["task_id"],
                        decision["category"],
                        decision["target_hash"],
                        self.encode(decision),
                        time.time(),
                    ),
                )
            self._event(db, "plan.imported", None, {"goal_id": goal_id, "count": len(tasks)})
        return goal_id

    @staticmethod
    def _task(row: sqlite3.Row) -> Task:
        data = json.loads(row["document"])
        data.update(status=row["status"], attempts=row["attempts"], version=row["version"])
        return Task.from_dict(data)

    def tasks(self) -> list[Task]:
        with self.connect() as db:
            return [self._task(row) for row in db.execute("SELECT * FROM tasks ORDER BY id")]

    def task(self, task_id: str) -> Task:
        with self.connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                raise ValueError("Unknown task")
            return self._task(row)

    def transition(
        self, task_id: str, expected: str, target: str, error: str | None = None, *, version: int
    ) -> None:
        if target not in TRANSITIONS.get(expected, set()):
            raise ValueError("Invalid task state transition")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row or row["status"] != expected or row["version"] != version:
                raise ValueError("Concurrent state change rejected")
            unsettled = db.execute(
                "SELECT COUNT(*) FROM executions WHERE task_id=? AND status='running'", (task_id,)
            ).fetchone()[0]
            if unsettled:
                raise ValueError("Execution must be reconciled before transition")
            data = json.loads(row["document"])
            data.update(status=target, last_error=error)
            db.execute(
                "UPDATE tasks SET status=?,document=?,version=version+1,updated=? WHERE id=?",
                (target, self.encode(data), time.time(), task_id),
            )
            self._event(
                db, "task.transition", task_id, {"from": expected, "to": target, "error": error}
            )

    def claim(self, task_id: str, run_id: str, max_attempts: int) -> tuple[Task, str]:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row or row["status"] != "ready":
                raise ValueError("Task is not ready")
            task = self._task(row)
            if task.attempts >= min(task.max_attempts, max_attempts, 3):
                raise ValueError("Implementation attempt budget exhausted")
            incomplete = db.execute(
                "SELECT COUNT(*) FROM task_dependencies d JOIN tasks t ON t.id=d.dependency_id "
                "WHERE d.task_id=? AND t.status!='completed'",
                (task_id,),
            ).fetchone()[0]
            active = db.execute(
                "SELECT COUNT(*) FROM tasks WHERE status IN ('running','verifying','reviewing')"
            ).fetchone()[0]
            unsettled = db.execute(
                "SELECT COUNT(*) FROM executions WHERE status='running'"
            ).fetchone()[0]
            if incomplete or active or unsettled:
                raise ValueError("Dependency or single-task execution guard rejected claim")
            task.attempts += 1
            task.status = "running"
            task.version = row["version"] + 1
            execution = uuid4().hex
            db.execute(
                "UPDATE tasks SET attempts=?,status='running',document=?,"
                "version=version+1,updated=? WHERE id=?",
                (task.attempts, self.encode(task.document()), time.time(), task_id),
            )
            db.execute(
                "INSERT INTO executions VALUES (?,?,?,?,?,?,'{}',?,NULL)",
                (
                    execution,
                    task_id,
                    run_id,
                    "worker",
                    task.attempts,
                    "running",
                    time.time(),
                ),
            )
            self._event(
                db, "execution.claimed", task_id, {"id": execution, "attempt": task.attempts}
            )
            return task, execution

    def finish_execution(self, execution: str, status: str, result: Any) -> None:
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE executions SET status=?,result=?,finished=? "
                "WHERE id=? AND status='running'",
                (status, self.encode(result), time.time(), execution),
            ).rowcount
            if changed != 1:
                raise ValueError("Execution was already settled")
            self._event(db, "execution.finished", None, {"id": execution, "status": status})

    def evidence(
        self, table: str, task_id: str, document: dict[str, Any], binding: str = ""
    ) -> str:
        identifier = uuid4().hex
        with self.transaction() as db:
            if table == "reviews":
                db.execute(
                    "INSERT INTO reviews VALUES (?,?,?,?,?)",
                    (identifier, task_id, binding, self.encode(document), time.time()),
                )
            elif table == "verification_results":
                db.execute(
                    "INSERT INTO verification_results VALUES (?,?,?,?)",
                    (identifier, task_id, self.encode(document), time.time()),
                )
            else:
                raise ValueError("Unsupported evidence table")
            self._event(db, "evidence.recorded", None, {"id": identifier, "kind": table})
        return identifier

    def checkpoint(self, task_id: str, document: dict[str, Any]) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO checkpoints VALUES (?,?,?) ON CONFLICT(task_id) "
                "DO UPDATE SET document=excluded.document,updated=excluded.updated",
                (task_id, self.encode(document), time.time()),
            )

    def get_checkpoint(self, task_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT document FROM checkpoints WHERE task_id=?", (task_id,)
            ).fetchone()
            return json.loads(row[0]) if row else {}

    def record_pr(self, task_id: str, document: dict[str, Any]) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO pull_requests VALUES (?,?,?) ON CONFLICT(task_id) "
                "DO UPDATE SET document=excluded.document,updated=excluded.updated",
                (task_id, self.encode(document), time.time()),
            )

    def get_pr(self, task_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT document FROM pull_requests WHERE task_id=?", (task_id,)
            ).fetchone()
            return json.loads(row[0]) if row else {}
