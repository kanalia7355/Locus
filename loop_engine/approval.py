"""Hash-bound human decisions. Model results can request, never resolve, approvals."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from loop_engine.schemas import validate
from loop_engine.security import fingerprint, reject_secrets
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
            decision["status"] not in {"approved", "obsolete"}
            and (decision["task_id"] == task_id or task_id in decision["blocking_tasks"])
            for decision in self.decisions()
        )

    def ci_registration_decision(self, task_id: str) -> dict[str, Any] | None:
        """Only the legacy system-generated, positively active registration wait."""
        task = self.state.task(task_id)
        checkpoint, pr = self.state.get_checkpoint(task_id), self.state.get_pr(task_id)
        policy = self.state.metadata("spec_snapshot", {}).get("policy", {}).get("github", {})
        previous = pr.get("ci", {})
        if (
            task.status != "awaiting_approval"
            or task.requires_approval
            or self.state.effective_risk(task_id) == "high"
            or policy.get("delivery") != "pull_request"
            or policy.get("auto_merge") != "off"
            or checkpoint.get("verified") is not True
            or not checkpoint.get("binding")
            or not checkpoint.get("committed_head")
            or previous.get("status") != "missing"
            or previous.get("head") != checkpoint["committed_head"]
            or pr.get("headRefOid") != checkpoint["committed_head"]
            or not (
                any(check.get("bucket") == "pending" for check in previous.get("checks", []))
                or any(
                    run.get("status") in {"queued", "in_progress"}
                    for run in previous.get("runs", [])
                )
            )
        ):
            return None
        target = fingerprint({"binding": checkpoint["binding"], "ci": previous})
        return next(
            (
                decision
                for decision in self.decisions()
                if decision["task_id"] == task_id
                and decision["status"] == "pending"
                and decision["category"] == "scope"
                and decision["risk"] == "medium"
                and decision["target_hash"] == target
                and decision["question"].startswith("CI held (missing, unclassified).")
            ),
            None,
        )

    def retire_ci_registration(self, task_id: str, observed: dict[str, Any]) -> bool:
        """Record a vanished CI condition, never a human approval or merge permission."""
        decision = self.ci_registration_decision(task_id)
        checkpoint = self.state.get_checkpoint(task_id)
        policy = self.state.metadata("spec_snapshot", {}).get("policy", {}).get("github", {})
        checks, runs = observed.get("checks", []), observed.get("runs", [])
        required = policy.get("required_checks", [])
        if (
            not decision
            or observed.get("status") != "passed"
            or observed.get("head") != checkpoint.get("committed_head")
            or not checks
            or not required
            or not runs
            or len(runs) >= 100
            or not set(required) <= {check.get("name") for check in checks}
            or any(check.get("bucket") != "pass" for check in checks)
            or any(
                run.get("headSha") != observed["head"]
                or run.get("status") != "completed"
                or run.get("conclusion") != "success"
                for run in runs
            )
        ):
            return False
        with self.state.transaction() as db:
            changed = db.execute(
                "UPDATE decisions SET status='obsolete',actor='system:ci-observation',"
                "reason=?,decided=? "
                "WHERE id=? AND status='pending' AND target_hash=?",
                (
                    "Configured checks passed at the verified head; no human approval granted.",
                    time.time(),
                    decision["id"],
                    decision["target_hash"],
                ),
            ).rowcount
            if changed:
                self.state._event(
                    db,
                    "approval.condition_obsolete",
                    task_id,
                    {
                        "id": decision["id"],
                        "head": observed["head"],
                        "observation_hash": fingerprint(observed),
                        "human_approval": False,
                    },
                )
        return bool(changed)
