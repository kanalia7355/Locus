from pathlib import Path
from typing import Any

import pytest
from test_loop_controller import (
    ReviewFixture,
    VerifyFixture,
    WorkerFixture,
    WorkspaceFixture,
    setup,
)
from test_loop_foundation import task

from loop_engine.controller import Controller
from loop_engine.security import SafetyError
from loop_engine.state_store import StateStore


def test_ci_repairs_share_budget_and_survive_reopen(tmp_path: Path) -> None:
    state = setup(tmp_path, [task(1), task(2)])

    class Publisher:
        def deliver(self, work: Any, checkpoint: Any, **kwargs: Any) -> dict[str, Any]:
            if work.id == "TASK-002":
                return {"complete": True}
            return {
                "complete": False,
                "repairable": True,
                "ci": {"status": "failed", "failure_context": "AssertionError: expected 2"},
            }

    class Worker(WorkerFixture):
        def execute(self, work: Any, context: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
            if work.attempts > 1:
                assert context["previous_failure"]["failure_context"].startswith("AssertionError")
            return super().execute(work, context, *args, **kwargs)

    controller = Controller(
        tmp_path,
        state,
        Worker(),
        VerifyFixture(),
        ReviewFixture(),
        WorkspaceFixture(tmp_path),
        Publisher(),
    )
    controller.config["github"]["delivery"] = "pull_request"
    controller.run()
    reopened = StateStore(state.path)
    assert reopened.task("TASK-001").attempts == 3
    assert reopened.task("TASK-001").status == "blocked"
    assert reopened.task("TASK-002").status == "completed"
    assert not reopened.get_checkpoint("TASK-001")["verified"]


@pytest.mark.parametrize("failure", ["exception", "permission"])
def test_delivery_service_failure_holds_one_task_without_global_recovery(
    tmp_path: Path, failure: str
) -> None:
    state = setup(tmp_path, [task(1), task(2)])

    class Publisher:
        def deliver(self, work: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
            if work.id == "TASK-001":
                if failure == "exception":
                    raise SafetyError("Service unavailable")
                return {
                    "complete": False,
                    "repairable": False,
                    "ci": {"status": "failed", "category": "permission"},
                }
            return {"complete": True}

    controller = Controller(
        tmp_path,
        state,
        WorkerFixture(),
        VerifyFixture(),
        ReviewFixture(),
        WorkspaceFixture(tmp_path),
        Publisher(),
    )
    controller.config["github"]["delivery"] = "pull_request"
    controller.run()
    assert state.task("TASK-001").status == "awaiting_approval"
    assert controller.queue.pending_for("TASK-001")
    assert state.task("TASK-002").status == "completed"
    with state.connect() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM executions WHERE status='running'").fetchone()[0] == 0
        )
