"""Fresh-context independent review, bound to the exact source and test evidence."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from loop_engine.codex_runner import CodexRunner
from loop_engine.models import Task
from loop_engine.schemas import validate
from loop_engine.security import fingerprint


class Reviewer:
    def __init__(self, runner: CodexRunner) -> None:
        self.runner = runner

    def evaluate(
        self,
        task: Task,
        workspace: Path,
        context: dict[str, Any],
        snapshot: dict[str, Any],
        verification: dict[str, Any],
        *,
        timeout: float,
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]:
        review = self.runner.invoke(
            "review",
            {
                "role": "independent read-only reviewer; no edits, subagents, secrets or network",
                "task": task.document(),
                "immutable_goal_specifications": context,
                "actual_diff": snapshot,
                "test_evidence": verification,
            },
            workspace,
            readonly=True,
            timeout=timeout,
            cancelled=cancelled,
        )
        validate("review", review)
        if review["task_id"] != task.id:
            raise ValueError("Review task identity mismatch")
        return review


def blocking(review: dict[str, Any]) -> bool:
    validate("review", review)
    return review["disposition"] != "pass" or any(
        finding["blocking"] or finding["severity"] in {"critical", "high"}
        for finding in review["findings"]
    )


def review_binding(
    task: Task, spec_hash: str, snapshot: dict[str, Any], verification: dict[str, Any]
) -> str:
    return fingerprint(
        {
            "task": task.specification_hash(),
            "source_specification": spec_hash,
            "snapshot": snapshot,
            "verification": verification,
        }
    )
