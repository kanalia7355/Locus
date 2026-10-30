import time
from pathlib import Path
from typing import Any

from test_loop_controller import (
    ReviewFixture,
    VerifyFixture,
    WorkerFixture,
    WorkspaceFixture,
    setup,
)

from loop_engine.controller import Controller


def test_pause_during_review_and_expired_resume_never_deliver(tmp_path: Path) -> None:
    from test_loop_foundation import task

    state = setup(tmp_path, [task()])

    class PauseReview(ReviewFixture):
        def evaluate(self, task: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
            state.set_metadata("control", "paused")
            return super().evaluate(task, *args, **kwargs)

    worker = WorkerFixture()
    controller = Controller(
        tmp_path, state, worker, VerifyFixture(), PauseReview(), WorkspaceFixture(tmp_path)
    )
    controller.run()
    assert state.task("TASK-001").status == "awaiting_approval"
    assert state.get_checkpoint("TASK-001")["verified"]
    budget = state.metadata("run_budget")
    budget["deadline"] = time.time() - 1
    state.set_metadata("run_budget", budget)
    controller.run(resume=True)
    assert state.task("TASK-001").status == "awaiting_approval"
    assert len(worker.calls) == 1
