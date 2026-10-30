from pathlib import Path
from typing import Any

import yaml
from test_loop_foundation import task

from loop_engine.approval import ApprovalQueue
from loop_engine.cli import initialize
from loop_engine.config import default
from loop_engine.controller import Controller
from loop_engine.planning import import_plan


class WorkerFixture:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, task: Any, context: Any, workspace: Path, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(task.id)
        return {
            "task_id": task.id,
            "status": "implemented",
            "summary": "Fixture implementation",
            "files_changed": ["src/app.txt"],
            "tests_added": [],
            "issues": [],
            "approval_requests": [],
        }


class WorkspaceFixture:
    def __init__(self, root: Path) -> None:
        self.root = root

    def prepare(self, task: Any) -> Path:
        return self.root

    def snapshot(self, task: Any, workspace: Path) -> dict[str, Any]:
        return {
            "base": "base-sha",
            "head": "head-sha",
            "paths": ["src/app.txt"],
            "diff_hash": task.id,
        }

    def finalize(self, task: Any, workspace: Path, binding: str) -> dict[str, Any]:
        return {"head": "final-head"}


class VerifyFixture:
    def __init__(self, fail: str = "") -> None:
        self.fail = fail

    def run(self, profile: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        passed = profile != self.fail
        return {
            "passed": passed,
            "status": "passed" if passed else "failed",
            "checks": [
                {"name": "scenario", "required": True, "status": "passed" if passed else "failed"}
            ],
        }


class ReviewFixture:
    def __init__(self, failing: bool = False) -> None:
        self.failing = failing
        self.calls = 0

    def evaluate(self, task: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return {
            "task_id": task.id,
            "disposition": "fail" if self.failing else "pass",
            "findings": [],
        }


def setup(root: Path, tasks: list[Any]) -> Any:
    state = initialize(root, "Implement the exact approved fixture Goal")
    config = default()
    config["loop"]["max_runtime_minutes"] = 1
    (root / ".loop/config.yaml").write_text(yaml.safe_dump(config))
    import_plan(
        root,
        state,
        {
            "requirements": "Fixture",
            "architecture": "Fixture",
            "nonfunctional_requirements": [],
            "constraints": [],
            "risks": [],
            "tasks": [task.document() for task in tasks],
            "decisions": [],
        },
    )
    return state


def test_three_failed_attempts_hold_task_but_continue_independent_work(tmp_path: Path) -> None:
    one = task(1)
    one.verification_profile = "failing"
    state = setup(tmp_path, [one, task(2), task(3, dependencies=["TASK-001"])])
    worker = WorkerFixture()
    controller = Controller(
        tmp_path,
        state,
        worker,
        VerifyFixture("failing"),
        ReviewFixture(),
        WorkspaceFixture(tmp_path),
    )
    controller.run()
    assert worker.calls.count("TASK-001") == 3
    assert state.task("TASK-001").status == "blocked"
    assert state.task("TASK-002").status == "completed"
    assert state.task("TASK-003").status == "ready"
    assert state.task("TASK-001").attempts == 3


def test_high_risk_scope_approval_then_resume_without_repeating_completed_work(
    tmp_path: Path,
) -> None:
    state = setup(tmp_path, [task(1, risk_level="high"), task(2)])
    worker = WorkerFixture()
    controller = Controller(
        tmp_path, state, worker, VerifyFixture(), ReviewFixture(), WorkspaceFixture(tmp_path)
    )
    controller.run()
    assert state.task("TASK-001").status == "awaiting_approval"
    assert worker.calls == ["TASK-002"]
    queue = ApprovalQueue(state)
    decision = queue.decisions()[0]
    queue.resolve(
        [
            {
                "id": decision["id"],
                "action": "approve",
                "target_hash": decision["target_hash"],
                "reason": "Reviewed exact scope",
            }
        ],
        "human-fixture",
    )
    controller.run(resume=True)
    assert worker.calls == ["TASK-002", "TASK-001"]
    assert state.task("TASK-001").status == "completed"


def test_review_fixes_share_the_three_attempt_budget(tmp_path: Path) -> None:
    state = setup(tmp_path, [task()])
    worker = WorkerFixture()
    review = ReviewFixture(True)
    Controller(tmp_path, state, worker, VerifyFixture(), review, WorkspaceFixture(tmp_path)).run()
    assert len(worker.calls) == review.calls == 3
    assert state.task("TASK-001").status == "blocked"
    assert state.get_checkpoint("TASK-001")["review_cycles"] == 2


def test_uncertain_execution_blocks_all_new_tasks_and_resume_preserves_budget(
    tmp_path: Path,
) -> None:
    state = setup(tmp_path, [task(1), task(2)])
    state.claim("TASK-001", "unclean-run", 3)
    worker = WorkerFixture()
    result = Controller(
        tmp_path, state, worker, VerifyFixture(), ReviewFixture(), WorkspaceFixture(tmp_path)
    ).run(resume=True)
    assert result == "recovery_required" and worker.calls == []
