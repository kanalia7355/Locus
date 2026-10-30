from pathlib import Path
from typing import Any

from test_loop_controller import (
    ReviewFixture,
    VerifyFixture,
    WorkerFixture,
    WorkspaceFixture,
    setup,
)
from test_loop_foundation import task

from loop_engine.approval import ApprovalQueue
from loop_engine.controller import Controller


def test_paused_protected_change_cannot_bypass_delivery_approval(tmp_path: Path) -> None:
    state = setup(tmp_path, [task()])

    class ProtectedWorkspace(WorkspaceFixture):
        def snapshot(self, task: Any, workspace: Path) -> dict[str, Any]:
            return {**super().snapshot(task, workspace), "paths": ["tests/test_feature.py"]}

    class PauseReview(ReviewFixture):
        def evaluate(self, task: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
            state.set_metadata("control", "paused")
            return super().evaluate(task, *args, **kwargs)

    workspace = ProtectedWorkspace(tmp_path)
    worker = WorkerFixture()
    Controller(tmp_path, state, worker, VerifyFixture(), PauseReview(), workspace).run()
    assert state.task("TASK-001").status == "awaiting_approval"
    Controller(tmp_path, state, worker, VerifyFixture(), ReviewFixture(), workspace).run(
        resume=True
    )
    assert state.task("TASK-001").status == "awaiting_approval"
    decision = ApprovalQueue(state).decisions()[0]
    assert decision["category"] == "security" and decision["status"] == "pending"
