from pathlib import Path
from typing import Any

import pytest
import yaml
from test_loop_foundation import task

from loop_engine.cli import initialize
from loop_engine.config import default, load
from loop_engine.launcher import launch
from loop_engine.locking import ProjectLock
from loop_engine.qa_profiles import detect


def test_launch_does_not_invent_goal_or_spawn_duplicate(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr("loop_engine.cli.doctor", lambda root: {"ready_for_live_execution": False})
    initialize(tmp_path)
    assert launch(tmp_path)["status"] == "goal_required"
    with ProjectLock(tmp_path / ".loop/runtime/controller.lock"):
        assert launch(tmp_path)["status"] == "already_running"
    (tmp_path / ".loop/goal.md").write_text("An approved outcome")
    assert launch(tmp_path)["status"] == "plan_required_or_complete"


def test_alias_migration_preserves_policy_and_rejects_conflicts(tmp_path: Path) -> None:
    config = default()
    config["github"]["base_branch"] = "main"
    config["github"]["bypass_protection"] = False
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    assert load(path)["github"]["base"] == "main"
    config["github"]["base_branch"] = "other"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        load(path)
    config = default()
    config["qa"]["independent_review"] = False
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        load(path)


def test_missing_stack_is_not_a_passing_qa_profile(tmp_path: Path) -> None:
    assert detect(tmp_path)["detected"] == {}


def test_launch_failure_is_not_reported_as_success(tmp_path: Path, monkeypatch: Any) -> None:
    state = initialize(tmp_path, "Fixture Goal")
    state.import_plan("Fixture Goal", "hash", [task()])
    monkeypatch.setattr("loop_engine.cli.doctor", lambda root: {"ready_for_live_execution": True})
    monkeypatch.setattr("loop_engine.cli.run", lambda args: 2)
    assert launch(tmp_path) == {
        "status": "launch_failed",
        "exit_code": 2,
        "log": ".loop/runtime/logs/controller.log",
    }
