"""Hash-bound human decisions. Model results can request, never resolve, approvals."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from loop_engine.schemas import validate
from loop_engine.security import reject_secrets
from loop_engine.state_store import StateStore


class ApprovalQueue:
    def __init__(self, state: StateStore) -> None:
        self.state = state

    def request(
        self,
        task_id: str | None,
        category: str,
        target_hash: str,
        question: str,
        risk: str = "medium",
        blocking_tasks: list[str] | None = None,
    ) -> str:
        decision = {
            "id": "DEC-" + uuid4().hex[:16],
            "task_id": task_id,
            "category": category,
            "risk": risk,
            "question": question,
            "options": ["approve", "reject", "revise"],
            "status": "pending",
            "blocking_tasks": blocking_tasks or ([task_id] if task_id else []),
            "target_hash": target_hash,
        }
        validate("decision", decision)
        with self.state.transaction() as db:
            existing = db.execute(
                "SELECT id FROM decisions WHERE task_id IS ? AND category=? AND target_hash=?",
                (task_id, category, target_hash),
            ).fetchone()
            if existing:
                return str(existing[0])
            db.execute(
                "INSERT INTO decisions VALUES (?,?,?,?,?,'pending',NULL,NULL,NULL,?)",
                (
                    decision["id"],
                    task_id,
                    category,
                    target_hash,
                    self.state.encode(decision),
                    time.time(),
                ),
            )
            self.state._event(
                db, "approval.requested", task_id, {"id": decision["id"], "category": category}
            )
        return str(decision["id"])

    def decisions(self) -> list[dict[str, Any]]:
        import json

        with self.state.connect() as db:
            return [
                {
                    **json.loads(row["document"]),
                    "status": row["status"],
                    "actor": row["actor"],
                    "reason": row["reason"],
                    "decided": row["decided"],
                }
                for row in db.execute("SELECT * FROM decisions ORDER BY created")
            ]

    def status(self, task: str | None, category: str, binding: str) -> str | None:
        with self.state.connect() as db:
            row = db.execute(
                "SELECT status FROM decisions WHERE task_id IS ? AND category=? AND target_hash=?",
                (task, category, binding),
            ).fetchone()
            return str(row[0]) if row else None

    def resolve(self, choices: list[dict[str, str]], actor: str) -> None:
        if not actor.strip() or not choices:
            raise ValueError("Human actor and choices required")
        if len({choice.get("id") for choice in choices}) != len(choices):
            raise ValueError("Duplicate decision choices")
        reject_secrets(choices)
        with self.state.transaction() as db:
            for choice in choices:
                if (
                    set(choice) != {"id", "action", "target_hash", "reason"}
                    or not choice["reason"].strip()
                ):
                    raise ValueError("Each choice requires ID/action/exact hash/reason")
                if choice["action"] not in {"approve", "reject", "revise"}:
                    raise ValueError("Unknown human decision")
                row = db.execute("SELECT * FROM decisions WHERE id=?", (choice["id"],)).fetchone()
                if (
                    not row
                    or row["status"] != "pending"
                    or row["target_hash"] != choice["target_hash"]
                ):
                    raise ValueError("Decision missing, settled, or content hash changed")
            for choice in choices:
                status = {"approve": "approved", "reject": "rejected", "revise": "revise"}[
                    choice["action"]
                ]
                db.execute(
                    "UPDATE decisions SET status=?,actor=?,reason=?,decided=? WHERE id=?",
                    (status, actor, choice["reason"], time.time(), choice["id"]),
                )
                self.state._event(
                    db,
                    "approval.resolved",
                    None,
                    {"id": choice["id"], "status": status, "actor": actor},
                )

    def pending_for(self, task_id: str) -> bool:
        return any(
            decision["status"] != "approved"
            and (decision["task_id"] == task_id or task_id in decision["blocking_tasks"])
            for decision in self.decisions()
        )
