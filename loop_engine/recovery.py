"""Conservative crash reconciliation; no killing stored PIDs or blind external replay."""

import json
from pathlib import Path
from typing import Any

from loop_engine.approval import ApprovalQueue
from loop_engine.security import fingerprint, reparse
from loop_engine.state_store import StateStore


def inspect(state: StateStore, root: Path) -> dict[str, Any]:
    problems: list[dict[str, str]] = []
    with state.connect() as db:
        for row in db.execute("SELECT id,task_id FROM executions WHERE status='running'"):
            problems.append(
                {
                    "task_id": row["task_id"],
                    "reason": "executor_lifetime_unknown",
                    "execution": row["id"],
                }
            )
        for row in db.execute(
            "SELECT id FROM tasks WHERE status IN ('running','verifying','reviewing')"
        ):
            problems.append({"task_id": row["id"], "reason": "interrupted_active_stage"})
        for row in db.execute("SELECT task_id,document FROM checkpoints"):
            checkpoint = json.loads(row["document"])
            if checkpoint.get("commit_intent") and not checkpoint.get("committed_head"):
                problems.append({"task_id": row["task_id"], "reason": "commit_outcome_uncertain"})
            if checkpoint.get("workspace"):
                expected = root.resolve() / ".loop/runtime/worktrees" / row["task_id"]
                actual = Path(checkpoint["workspace"])
                if reparse(actual) or actual.resolve() != expected.resolve() or not actual.exists():
                    problems.append(
                        {"task_id": row["task_id"], "reason": "worktree_identity_unsettled"}
                    )
        for row in db.execute("SELECT task_id,document FROM pull_requests"):
            value = json.loads(row["document"])
            if value.get("create_uncertain"):
                problems.append(
                    {"task_id": row["task_id"], "reason": "pull_request_outcome_uncertain"}
                )
    return {
        "safe_to_start": not problems,
        "problems": problems,
        "action": "resume_known_idle_state"
        if not problems
        else "human_assessment_and_external_reconciliation_required",
        "automatic_replay": False,
    }


def queue_assessment(state: StateStore, root: Path) -> dict[str, Any]:
    report = inspect(state, root)
    if not report["safe_to_start"]:
        state.set_metadata("orphan_uncertainty", True)
        ApprovalQueue(state).request(
            None,
            "recovery",
            fingerprint(report),
            "Assess interrupted executor/Git/PR state; approval cannot prove process termination.",
            "high",
            blocking_tasks=sorted({item["task_id"] for item in report["problems"]}),
        )
        state.event("recovery.blocked", count=len(report["problems"]))
    return report
