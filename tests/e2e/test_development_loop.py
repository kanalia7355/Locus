"""Real local Git/Python; synthetic Codex, GitHub checks/protection and merge authority."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from test_development_contracts import report
from test_loop_controller import ReviewFixture
from test_loop_execution import FixtureBoundary
from test_loop_foundation import task
from test_loop_git import git

from loop_engine.cli import initialize
from loop_engine.config import default
from loop_engine.controller import Controller
from loop_engine.development import DevelopmentLoop
from loop_engine.git_manager import GitManager
from loop_engine.github_manager import merge_reasons
from loop_engine.goal_evaluator import criteria
from loop_engine.improvement_planner import ImprovementPlanner
from loop_engine.planning import import_plan
from loop_engine.security import fingerprint
from loop_engine.state_store import StateStore
from loop_engine.verification import Verifier


def test_real_local_implementation_ci_repair_merge_and_next_improvement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "--local", "user.name", "Development fixture")
    git(tmp_path, "config", "--local", "user.email", "fixture@example.invalid")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text("def total(value):\n    return 0\n")
    (tmp_path / ".gitignore").write_text(".loop/\n__pycache__/\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "test: initialize development fixture")
    state = initialize(tmp_path, "Feature and safe edge cases")
    (tmp_path / ".loop/acceptance.md").write_text("- Implement feature\n- Clamp negatives\n")
    config = default()
    config["github"].update(delivery="merged", auto_merge="safe", auto_merge_allowed_paths=["src"])
    config["verification"] = {
        "python": [
            {
                "name": "actual-positive-input",
                "level": "functional",
                "argv": ["{python}", "-c", "exec(open('src/app.py').read()); assert total(1) > 0"],
                "required": True,
            }
        ]
    }
    (tmp_path / ".loop/config.yaml").write_text(yaml.safe_dump(config))
    import_plan(
        tmp_path,
        state,
        {
            "requirements": "Fixture only",
            "architecture": "Fixture only",
            "nonfunctional_requirements": [],
            "constraints": [],
            "risks": [],
            "tasks": [task(1, risk_level="low").document()],
            "decisions": [],
        },
    )
    manager = GitManager(tmp_path, state)
    # Known test-owned Git fixture only. This does not establish live policy trust.
    monkeypatch.setattr(manager, "_safe_configuration", lambda *args: None)
    timeline = []

    class MainFixture:
        def configure(self, *args: Any) -> None:
            pass

        def current_head(self) -> str:
            return git(tmp_path, "rev-parse", "main")

        def refresh(self, expected_merge: str | None) -> tuple[Path, dict[str, Any]]:
            head = self.current_head()
            if expected_merge:
                git(tmp_path, "merge-base", "--is-ancestor", expected_merge, head)
            directory = tmp_path / ".loop/runtime/evaluations" / head
            if not directory.exists():
                directory.parent.mkdir(parents=True, exist_ok=True)
                git(tmp_path, "worktree", "add", "--detach", str(directory), head)
            return directory, {
                "head": head,
                "files": {"src/app.py": (directory / "src/app.py").read_text()},
            }

        def stable(self, directory: Path, head: str) -> bool:
            return git(directory, "rev-parse", "HEAD") == head and not git(
                directory, "status", "--porcelain"
            )

    class EvaluatorFixture:
        def assess(
            self, source: Any, snapshot: Any, workspace: Path, **kwargs: Any
        ) -> dict[str, Any]:
            timeline.append("evaluate-main")
            code = snapshot["files"]["src/app.py"]
            value = report(snapshot["head"], complete="max(0" in code)
            value["spec_hash"] = fingerprint(source)
            ids = list(criteria(source))
            for item, identifier in zip(value["criteria"], ids, strict=True):
                item["id"] = identifier
            if "* 2" in code:
                value["criteria"][0]["status"] = "met"
                if value["gaps"]:
                    value["gaps"][0].update(criterion_ids=[ids[1]], depends_on=["TASK-001"])
            else:
                value["gaps"] = []  # Initial approved task covers the known feature gap.
            return value

    class WorkerFixture:
        def execute(
            self, work: Any, context: Any, workspace: Path, **kwargs: Any
        ) -> dict[str, Any]:
            timeline.append("implement:" + work.id)
            expression = (
                "value"
                if work.id == "TASK-001" and work.attempts == 1
                else "max(0, value * 2)"
                if work.id == "TASK-002"
                else "value * 2"
            )
            (workspace / "src/app.py").write_text(f"def total(value):\n    return {expression}\n")
            return {
                "task_id": work.id,
                "status": "implemented",
                "summary": "Synthetic worker writes actual fixture source",
                "files_changed": ["src/app.py"],
                "tests_added": [],
                "issues": [],
                "approval_requests": [],
            }

    class PublisherFixture:
        def deliver(self, work: Any, checkpoint: Any, **kwargs: Any) -> dict[str, Any]:
            commit = manager.finalize(work, Path(checkpoint["workspace"]), checkpoint["binding"])
            timeline.append("create-or-update-pr:" + work.id)
            state.record_pr(
                work.id, {"number": int(work.id[5:]), "head": commit["head"], "synthetic": True}
            )
            namespace: dict[str, Any] = {}
            exec((Path(checkpoint["workspace"]) / "src/app.py").read_text(), namespace)  # noqa: S102 — test-owned source
            if namespace["total"](1) != 2:
                timeline.append("ci-failed")
                return {
                    "complete": False,
                    "repairable": True,
                    "ci": {
                        "head": commit["head"],
                        "run_id": 1001,
                        "failure_context": "AssertionError: total(1) must equal 2",
                    },
                }
            if work.id == "TASK-002":
                assert namespace["total"](-1) == 0
            timeline.append("ci-passed")
            evidence = dict.fromkeys(
                [
                    "human_authorized",
                    "review_passed",
                    "trusted_review_publisher",
                    "review_head_base_policy_bound",
                    "ci_complete",
                    "protection_verified",
                    "strict_current_base",
                    "conversations_resolved",
                    "mergeable",
                    "head_matches",
                    "base_matches",
                    "atomic_base_binding",
                ],
                True,
            )
            evidence.update(paths=["src/app.py"], pending_approvals=False)
            assert merge_reasons(work, config["github"], evidence) == []
            git(tmp_path, "merge", "--ff-only", commit["branch"])
            timeline.append("safe-merge:" + work.id)
            return {
                "complete": True,
                "merged": True,
                "merge_sha": git(tmp_path, "rev-parse", "main"),
            }

    verifier = Verifier(config["verification"], boundary=FixtureBoundary())
    development = DevelopmentLoop(
        tmp_path,
        state,
        MainFixture(),
        EvaluatorFixture(),
        verifier,
        ImprovementPlanner(state, ["src"], "python"),
    )
    controller = Controller(
        tmp_path,
        state,
        WorkerFixture(),
        verifier,
        ReviewFixture(),
        manager,
        PublisherFixture(),
        development,
    )
    assert controller.run(duration_seconds=60) == "goal_complete"
    assert state.task("TASK-001").attempts == 2
    assert state.task("TASK-002").status == "completed"
    assert timeline.count("evaluate-main") == 3
    assert (
        timeline.index("ci-failed")
        < timeline.index("safe-merge:TASK-001")
        < timeline.index("implement:TASK-002")
    )
    assert StateStore(state.path).metadata("development_status")["status"] == "complete"
    assert git(tmp_path, "branch", "--show-current") == "main"
