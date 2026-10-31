import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from test_development_contracts import report, snapshot, source
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
from loop_engine.development import DevelopmentLoop
from loop_engine.duration import parse_duration
from loop_engine.gap_analyzer import analyze
from loop_engine.goal_evaluator import criteria
from loop_engine.improvement_planner import ImprovementPlanner


def test_atomic_dedup_dependency_updates_and_no_attempt_reset(tmp_path: Path) -> None:
    state = setup(tmp_path, [task(1)])
    planner = ImprovementPlanner(state, ["src"], "python")
    gaps = analyze(report(), source(), snapshot())
    spec = state.metadata("spec_hash")
    receipt: dict[str, Any] = {"progress": {"stagnant": 0}}
    generated = planner.apply(gaps, head="a" * 40, spec_hash=spec, receipt=receipt)
    assert [work.id for work in generated] == ["TASK-002"]
    changed = deepcopy(gaps)
    changed[0].update(title="Reworded", severity="medium", depends_on=["TASK-001"])
    assert planner.apply(changed, head="b" * 40, spec_hash=spec, receipt=receipt) == []
    assert state.task("TASK-002").priority == 60
    assert state.task("TASK-002").dependencies == ["TASK-001"]
    changed[0]["depends_on"] = ["TASK-002"]
    with pytest.raises(ValueError):
        planner.apply(changed, head="c" * 40, spec_hash=spec, receipt=receipt)
    assert planner.receipt(spec, "c" * 40) is None
    assert state.task("TASK-002").dependencies == ["TASK-001"]
    work, execution = state.claim("TASK-001", "run", 3)
    state.finish_execution(execution, "failed", {"code": "fixture"})
    state.transition(work.id, "running", "blocked", version=state.task(work.id).version)
    assert state.task("TASK-001").attempts == 1
    assert len(state.tasks()) == 2


def test_architecture_and_out_of_scope_gaps_require_preapproval(tmp_path: Path) -> None:
    state = setup(tmp_path, [task(1)])
    gap = analyze(report(), source(), snapshot())[0]
    gap["category"] = "architecture"
    work = ImprovementPlanner(state, ["other"], "python").apply(
        [gap], head="a" * 40, spec_hash=state.metadata("spec_hash"), receipt={"progress": {}}
    )[0]
    assert work.requires_approval and work.risk_level == "high"


def test_explicit_resume_window_preserves_counters_and_task_cap(tmp_path: Path) -> None:
    state = setup(tmp_path, [task(1)])
    controller = Controller(
        tmp_path,
        state,
        WorkerFixture(),
        VerifyFixture(),
        ReviewFixture(),
        WorkspaceFixture(tmp_path),
    )
    controller.run(duration_seconds=10)
    first = state.metadata("run_budget")
    state.set_metadata("run_budget", {**first, "deadline": 0})
    controller.run(resume=True, duration_seconds=20)
    resumed = state.metadata("run_budget")
    assert resumed["id"] == first["id"] and resumed["tasks"] == first["tasks"]
    assert resumed["deadline"] > first["deadline"]
    assert state.task("TASK-001").attempts == 1
    assert parse_duration("2h") == 7200
    with pytest.raises(ValueError):
        parse_duration("7h")
    with pytest.raises(ValueError):
        controller.run(resume=True, duration_seconds=61)  # Fixture has a one-minute cap.


@pytest.mark.parametrize("prior", ["untouched", "attempted", "approved"])
def test_existing_finding_risk_escalation_never_inherits_low_risk(
    tmp_path: Path, prior: str
) -> None:
    state = setup(tmp_path, [task(1)])
    planner = ImprovementPlanner(state, ["src"], "python")
    gaps = analyze(report(), source(), snapshot())
    spec = state.metadata("spec_hash")
    work = planner.apply(gaps, head="a" * 40, spec_hash=spec, receipt={"progress": {}})[0]
    if prior == "attempted":
        claimed, execution = state.claim(work.id, "fixture", 3)
        state.finish_execution(execution, "failed", {"code": "fixture"})
        state.transition(work.id, "running", "ready", version=claimed.version)
    elif prior == "approved":
        queue = ApprovalQueue(state)
        identifier = queue.request(work.id, "scope", spec, "Fixture prior approval")
        queue.resolve(
            [{"id": identifier, "action": "approve", "reason": "Fixture", "target_hash": spec}],
            "human-fixture",
        )
    gaps[0]["severity"] = "critical"
    planner.apply(gaps, head="b" * 40, spec_hash=spec, receipt={"progress": {}})
    updated = state.task(work.id)
    assert state.effective_risk(work.id) == "high"
    if prior == "untouched":
        assert updated.risk_level == "high" and updated.requires_approval
    else:
        assert ApprovalQueue(state).pending_for(work.id)
        assert updated.specification_hash() == work.specification_hash()
    assert updated.attempts == (1 if prior == "attempted" else 0)


def development_fixture(root: Path, *, racing: bool = False) -> tuple[Any, Any, Any]:
    (root / ".loop").mkdir()
    (root / ".loop/acceptance.md").write_text(source()["acceptance.md"])
    state = setup(root, [task(1)])
    state.set_metadata("run_budget", {"id": "fixture"})

    class Snapshots:
        head = "a" * 40
        race = racing

        def configure(self, *args: Any) -> None:
            pass

        def refresh(self, *args: Any) -> tuple[Path, dict[str, Any]]:
            return root, {**snapshot(), "head": self.head}

        def current_head(self) -> str:
            if self.race:
                self.head, self.race = "b" * 40, False
            return self.head

        def stable(self, *args: Any) -> bool:
            return True

    class Evaluator:
        def assess(self, src: Any, snap: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
            value = report(snap["head"], complete=True)
            value["spec_hash"] = state.metadata("spec_hash")
            assert set(item["id"] for item in value["criteria"]) == set(criteria(src))
            return value

    class Verification:
        calls = 0

        def run(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            self.calls += 1
            passed = self.calls > 1
            return {
                "passed": passed,
                "status": "passed" if passed else "failed",
                "checks": [{"required": True, "status": "passed" if passed else "failed"}],
            }

    verifier = Verification()
    development = DevelopmentLoop(
        root,
        state,
        Snapshots(),
        Evaluator(),
        verifier,
        ImprovementPlanner(state, ["src"], "python"),
    )
    return state, development, verifier


def test_main_race_invalidates_a_previously_complete_goal(tmp_path: Path) -> None:
    state, development, verifier = development_fixture(tmp_path, racing=True)
    state.set_metadata("development_status", {"status": "complete", "head": "old"})
    controller = Controller(
        tmp_path,
        state,
        WorkerFixture(),
        VerifyFixture(),
        ReviewFixture(),
        WorkspaceFixture(tmp_path),
        development=development,
    )
    controller.deadline = time.time() + 60
    state.set_metadata("control", "running")
    controller._assess_project()
    assert state.metadata("development_status")["status"] == "main_changed"
    assert state.task("TASK-001").attempts == 0


def test_same_head_failed_verification_is_refreshed_and_stagnation_persists(tmp_path: Path) -> None:
    state, development, verifier = development_fixture(tmp_path)
    for _ in range(2):
        development.cycle(deadline=time.time() + 60, cancelled=lambda: False)
    assert verifier.calls == 2
    assert len(state.tasks()) == 1
    receipt = development.planner.receipt(state.metadata("spec_hash"), "a" * 40)
    assert receipt["verification"]["passed"]
    assert state.metadata("development_progress")["stagnant"] == 0  # QA recovery is progress.
    for _ in range(3):
        development.cycle(deadline=time.time() + 60, cancelled=lambda: False)
    assert state.metadata("development_status")["status"] == "stalled"


def test_fourth_assessment_qa_recovery_can_complete_instead_of_stalling(tmp_path: Path) -> None:
    state, development, verifier = development_fixture(tmp_path)
    claimed, execution = state.claim("TASK-001", "fixture", 3)
    state.finish_execution(execution, "returned", {"code": "fixture"})
    for target in ("verifying", "reviewing", "completed"):
        work = state.task(claimed.id)
        state.transition(work.id, work.status, target, version=work.version)
    verifier.calls = -2  # Three failed mandatory checks followed by recovery.
    for _ in range(4):
        development.cycle(deadline=time.time() + 60, cancelled=lambda: False)
    assert state.metadata("development_status")["status"] == "complete"
    assert state.metadata("development_progress")["stagnant"] == 0


def test_whole_controller_reassesses_racing_main_before_selecting_work(tmp_path: Path) -> None:
    state, development, verifier = development_fixture(tmp_path, racing=True)
    state.set_metadata("development_status", {"status": "complete", "head": "old"})

    class Worker(WorkerFixture):
        def execute(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            assert state.metadata("development_budget")["cycles"] >= 2
            return super().execute(*args, **kwargs)

    worker = Worker()
    controller = Controller(
        tmp_path,
        state,
        worker,
        VerifyFixture(),
        ReviewFixture(),
        WorkspaceFixture(tmp_path),
        development=development,
    )
    assert controller.run(duration_seconds=10) != "goal_complete"
    assert worker.calls == ["TASK-001"]
