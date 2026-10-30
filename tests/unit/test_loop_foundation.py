import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from loop_engine.cli import initialize, main
from loop_engine.config import default, load
from loop_engine.locking import ProjectLock
from loop_engine.models import Task
from loop_engine.scheduler import Scheduler
from loop_engine.security import SafetyError, fingerprint, reject_secrets, relative_path
from loop_engine.state_store import StateStore


def task(number: int = 1, **kwargs: object) -> Task:
    return Task(
        id=f"TASK-{number:03}",
        title=f"Implement slice {number}",
        acceptance_criteria=["A meaningful scenario passes"],
        verification_profile="python",
        allowed_paths=["src", "tests"],
        **kwargs,
    )  # type: ignore[arg-type]


def test_schema_closed_and_limit_caps(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    config = default()
    path.write_text(yaml.safe_dump(config))
    assert load(path)["loop"]["max_attempts_per_task"] == 3
    for key, value in (
        ("max_attempts_per_task", 4),
        ("max_review_cycles", 3),
        ("max_concurrent_tasks", 2),
    ):
        altered = default()
        altered["loop"][key] = value
        path.write_text(yaml.safe_dump(altered))
        with pytest.raises(ValueError):
            load(path)
    config["unknown"] = True
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        load(path)


def test_dag_and_import_are_atomic(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.sqlite3")
    with pytest.raises(ValueError, match="Cyclic"):
        state.import_plan(
            "goal", "hash", [task(1, dependencies=["TASK-002"]), task(2, dependencies=["TASK-001"])]
        )
    assert state.tasks() == []
    with pytest.raises(ValueError, match="Unknown"):
        state.import_plan("goal", "hash", [task(1, dependencies=["TASK-099"])])
    with pytest.raises(ValueError):
        state.import_plan("goal", "hash", [task(1, status="completed")])
    state.import_plan(
        "goal",
        "hash",
        [task(1, status="ready"), task(2, status="ready", dependencies=["TASK-001"])],
    )
    assert Scheduler(state).next_ready_task().id == "TASK-001"  # type: ignore[union-attr]


def test_transitions_attempts_claim_cas_and_persistence(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    state = StateStore(path)
    state.import_plan("goal", "hash", [task(status="ready")])
    for attempt in range(1, 4):
        claimed, execution = state.claim("TASK-001", "run", 3)
        assert claimed.attempts == attempt
        with pytest.raises(ValueError):
            StateStore(path).claim("TASK-001", "other", 3)
        state.finish_execution(execution, "failed", {"code": "verification_failed"})
        state.transition("TASK-001", "running", "ready", version=state.task("TASK-001").version)
    with pytest.raises(ValueError, match="budget"):
        StateStore(path).claim("TASK-001", "other", 3)
    assert StateStore(path).task("TASK-001").attempts == 3
    with pytest.raises(ValueError):
        state.transition("TASK-001", "ready", "completed", version=state.task("TASK-001").version)
    with pytest.raises(ValueError):
        state.transition("TASK-001", "planned", "ready", version=state.task("TASK-001").version)
    with state.transaction() as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM events")


def test_lock_and_secret_path_guards(tmp_path: Path) -> None:
    path = tmp_path / "controller.lock"
    with ProjectLock(path), pytest.raises(RuntimeError):
        with ProjectLock(path):
            pass
    with ProjectLock(path):
        pass
    for unsafe in ("../outside", "/absolute", "C:/secret", "src\\escape", ".git/config"):
        with pytest.raises(SafetyError):
            relative_path(unsafe)
    with pytest.raises(SafetyError):
        reject_secrets("api_key=" + "not-a-real-secret-fixture")
    original = task()
    assert (
        original.specification_hash()
        == replace(original, attempts=2, status="blocked").specification_hash()
    )
    assert (
        original.specification_hash()
        != replace(original, title="Changed requirement").specification_hash()
    )
    assert len(fingerprint({"x": 1})) == 64


def test_init_preserves_files_and_cli_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".loop").mkdir()
    original = tmp_path / ".loop/goal.md"
    original.write_text("User-owned Goal")
    initialize(tmp_path, "Do not replace existing Goal")
    assert original.read_text() == "User-owned Goal"
    assert main(["--project", str(tmp_path), "status"]) == 0
    assert "No plan" not in capsys.readouterr().out
    assert main(["--project", str(tmp_path), "pause"]) == 0
    assert StateStore(tmp_path / ".loop/runtime/state.sqlite3").metadata("control") == "paused"
