"""Controller integration for OpenCode runner (synthetic/offline)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from loop_engine.cli import initialize
from loop_engine.config import default
from loop_engine.controller import Controller
from loop_engine.opencode_runner import OpenCodeRunner
from loop_engine.planning import import_plan
from loop_engine.state_store import StateStore


def sample_task_doc() -> dict:
    return {
        "id": "TASK-001",
        "title": "Synthetic task",
        "status": "ready",
        "priority": 1,
        "dependencies": [],
        "acceptance_criteria": ["change is applied"],
        "verification_profile": "synthetic",
        "attempts": 0,
        "max_attempts": 3,
        "risk_level": "low",
        "requires_approval": False,
        "review_required": True,
        "allowed_paths": ["src"],
        "branch": None,
        "worktree": None,
        "last_error": None,
        "version": 0,
    }


class FakeProcess:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = []

    def run(self, argv, cwd, **kwargs):
        self.calls.append({"argv": argv, "cwd": cwd, **kwargs})
        return SimpleNamespace(
            outcome="exit", returncode=0, stdout=json.dumps(self.payload), stderr="", elapsed=0.1
        )


class AllowBoundary:
    file_proposals = False
    c_min = False

    def require(self, workspace, control_root):
        return None

    def command(self, argv, workspace):
        return argv


class WorkspaceFixture:
    def __init__(self, root: Path):
        self.root = root

    def prepare(self, task):
        return self.root

    def snapshot(self, task, workspace):
        return {"base": "base", "head": "head", "paths": ["src/app.txt"], "diff_hash": task.id}

    def finalize(self, task, workspace, binding):
        return {"head": "final"}


class VerifyFixture:
    def run(self, profile, workspace, control_root, *, timeout, cancelled):
        return {
            "passed": True,
            "status": "passed",
            "checks": [
                {
                    "name": "synthetic",
                    "level": "functional",
                    "required": True,
                    "status": "passed",
                    "exit_code": 0,
                }
            ],
            "profile_hash": "ok",
        }


class ReviewFixture:
    def evaluate(self, task, workspace, context, snapshot, verification, *, timeout, cancelled):
        return {"task_id": task.id, "disposition": "pass", "findings": []}

    def acknowledge(self):
        return None


def setup(root: Path) -> StateStore:
    state = initialize(root, "Synthetic OpenCode integration goal")
    config = default()
    config["github"]["delivery"] = "local"
    config["loop"]["max_runtime_minutes"] = 1
    (root / ".loop/config.yaml").write_text(yaml.safe_dump(config))
    import_plan(
        root,
        state,
        {
            "requirements": "Synthetic",
            "architecture": "Synthetic",
            "nonfunctional_requirements": [],
            "constraints": [],
            "risks": [],
            "tasks": [sample_task_doc()],
            "decisions": [],
        },
    )
    return state


def test_controller_persists_completed_task_with_opencode_runner(tmp_path: Path) -> None:
    state = setup(tmp_path)
    payload = {
        "task_id": "TASK-001",
        "status": "implemented",
        "summary": "synthetic implementation",
        "files_changed": ["src/app.txt"],
        "tests_added": [],
        "issues": [],
        "approval_requests": [],
    }
    process = FakeProcess(payload)
    worker = OpenCodeRunner(
        tmp_path,
        boundary=AllowBoundary(),
        process=process,
        model="opencode/iceman-free",
        binary="opencode",
    )
    controller = Controller(
        tmp_path, state, worker, VerifyFixture(), ReviewFixture(), WorkspaceFixture(tmp_path)
    )
    outcome = controller.run()
    assert outcome == "idle"
    assert state.task("TASK-001").status == "completed"
    assert process.calls
    assert state.get_checkpoint("TASK-001").get("implementation") == "verified"
