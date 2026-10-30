from pathlib import Path

from test_loop_foundation import task

from loop_engine.cli import initialize, main
from loop_engine.recovery import inspect, queue_assessment
from loop_engine.reporting import write_report


def test_interrupted_execution_is_never_replayed_or_cleared_by_approval(tmp_path: Path) -> None:
    state = initialize(tmp_path, "Fixture Goal")
    state.import_plan("Fixture", "hash", [task(status="ready")])
    state.claim("TASK-001", "interrupted", 3)
    result = queue_assessment(state, tmp_path)
    assert not result["safe_to_start"] and result["automatic_replay"] is False
    assert state.metadata("orphan_uncertainty") is True
    assert state.task("TASK-001").attempts == 1
    assert main(["--project", str(tmp_path), "resume"]) == 2
    assert state.task("TASK-001").attempts == 1


def test_uncertain_commit_pr_and_worktree_are_reported(tmp_path: Path) -> None:
    state = initialize(tmp_path, "Fixture")
    state.import_plan("Fixture", "hash", [task()])
    state.checkpoint(
        "TASK-001", {"commit_intent": "uncertain", "workspace": str(tmp_path / "unexpected")}
    )
    state.record_pr("TASK-001", {"create_uncertain": True})
    reasons = {item["reason"] for item in inspect(state, tmp_path)["problems"]}
    assert reasons == {
        "commit_outcome_uncertain",
        "worktree_identity_unsettled",
        "pull_request_outcome_uncertain",
    }


def test_user_progress_file_is_preserved_while_db_report_is_available(tmp_path: Path) -> None:
    (tmp_path / ".loop").mkdir()
    path = tmp_path / ".loop/progress.md"
    path.write_text("User-owned notes")
    state = initialize(tmp_path, "Fixture")
    assert "SQLite" in write_report(state, tmp_path)
    assert path.read_text() == "User-owned notes"
    generated = tmp_path / ".loop/decisions.md"
    generated.write_text("User edited generated notes")
    write_report(state, tmp_path)
    assert generated.read_text() == "User edited generated notes"
