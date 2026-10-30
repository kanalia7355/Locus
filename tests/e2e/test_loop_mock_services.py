import json
from pathlib import Path
from typing import Any

from test_loop_controller import ReviewFixture, VerifyFixture, WorkerFixture, WorkspaceFixture
from test_loop_foundation import task

from loop_engine.approval import ApprovalQueue
from loop_engine.cli import main
from loop_engine.controller import Controller
from loop_engine.state_store import StateStore


def test_human_cli_init_plan_start_approval_resume_report_with_mock_services(
    tmp_path: Path, monkeypatch: Any
) -> None:
    goal = tmp_path / "human-goal.md"
    goal.write_text("Implement fixture without changing the acceptance criteria")
    assert main(["--project", str(tmp_path), "init", "--goal-file", str(goal)]) == 0
    proposal = {
        "requirements": "Proposal",
        "nonfunctional_requirements": [],
        "architecture": "Proposal",
        "constraints": [],
        "risks": [],
        "tasks": [task(1, risk_level="high").document(), task(2).document()],
        "decisions": [],
    }
    path = tmp_path / "human-plan.json"
    path.write_text(json.dumps(proposal))
    assert main(["--project", str(tmp_path), "plan", "--file", str(path)]) == 0
    state = StateStore(tmp_path / ".loop/runtime/state.sqlite3")
    worker = WorkerFixture()

    class E2EWorkspace(WorkspaceFixture):
        def prepare(self, task: Any) -> Path:
            directory = self.root / ".loop/runtime/worktrees" / task.id
            directory.mkdir(parents=True, exist_ok=True)
            return directory

    def fixture_controller(root: Path, actual: StateStore) -> Controller:
        return Controller(
            root, actual, worker, VerifyFixture(), ReviewFixture(), E2EWorkspace(root)
        )

    monkeypatch.setattr("loop_engine.cli.build_controller", fixture_controller)
    assert main(["--project", str(tmp_path), "start"]) == 0
    assert state.task("TASK-001").status == "awaiting_approval"
    assert state.task("TASK-002").status == "completed"
    decision = ApprovalQueue(state).decisions()[0]
    assert (
        main(
            [
                "--project",
                str(tmp_path),
                "approve",
                decision["id"],
                "--target-hash",
                decision["target_hash"],
                "--reason",
                "Human fixture approval",
            ]
        )
        == 0
    )
    assert main(["--project", str(tmp_path), "resume"]) == 0
    assert state.task("TASK-001").status == "completed"
    assert main(["--project", str(tmp_path), "report"]) == 0
    assert "completed" in (tmp_path / ".loop/progress.md").read_text()
    assert worker.calls == ["TASK-002", "TASK-001"]
