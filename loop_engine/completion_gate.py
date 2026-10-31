"""Deterministic completion: model declarations alone cannot finish a Goal."""

from typing import Any

from loop_engine.models import Task


def reasons(
    report: dict[str, Any],
    verification: dict[str, Any],
    tasks: list[Task],
    decisions: list[dict[str, Any]],
    *,
    current_head: str,
    spec_hash: str,
) -> list[str]:
    blocked = []
    if report.get("head") != current_head or report.get("spec_hash") != spec_hash:
        blocked.append("stale_head_or_goal")
    criteria = report.get("criteria", [])
    if not criteria or any(
        item.get("status") != "met" or not item.get("evidence", "").strip() for item in criteria
    ):
        blocked.append("acceptance_not_proven")
    checks = verification.get("checks", [])
    required = [check for check in checks if check.get("required")]
    if (
        verification.get("head") != current_head
        or verification.get("spec_hash") != spec_hash
        or verification.get("passed") is not True
        or not required
        or any(check.get("status") != "passed" for check in required)
    ):
        blocked.append("required_verification_not_proven")
    if report.get("review_passed") is not True or report.get("blocking_findings"):
        blocked.append("independent_project_review_not_passed")
    if report.get("gaps"):
        blocked.append("unresolved_gaps")
    if any(task.status not in {"completed", "cancelled"} for task in tasks):
        blocked.append("unfinished_tasks")
    if any(item["status"] != "approved" for item in decisions):
        blocked.append("human_decisions_unresolved")
    return blocked
