import json
from pathlib import Path
from types import SimpleNamespace

from loop_engine.models import Task
from loop_engine.opencode_runner import OpenCodeRunner


def sample_task() -> Task:
    return Task.from_dict(
        {
            "id": "TASK-001",
            "title": "Synthetic task",
            "status": "running",
            "priority": 1,
            "dependencies": [],
            "acceptance_criteria": ["change is applied"],
            "verification_profile": "repository",
            "attempts": 1,
            "max_attempts": 3,
            "risk_level": "low",
            "requires_approval": False,
            "review_required": True,
            "allowed_paths": ["backend/app"],
            "branch": None,
            "worktree": None,
            "last_error": None,
            "version": 1,
        }
    )


class NoBoundary:
    file_proposals = False
    c_min = False

    def require(self, workspace, control_root):
        return None

    def command(self, argv, workspace):
        return argv


class SeqProcess:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def run(self, argv, cwd, **kwargs):
        self.calls.append({"argv": argv, "cwd": cwd, **kwargs})
        return self.results.pop(0)


def test_execute_falls_back_to_next_eligible_model_on_quota_exhaustion(tmp_path: Path) -> None:
    task = sample_task()
    payload = {
        "task_id": "TASK-001",
        "status": "implemented",
        "summary": "ok",
        "files_changed": ["backend/app/x.py"],
        "tests_added": [],
        "issues": [],
        "approval_requests": [],
    }
    process = SeqProcess(
        [
            SimpleNamespace(
                outcome="exit", returncode=1, stdout="", stderr="quota exceeded", elapsed=0.1
            ),
            SimpleNamespace(
                outcome="exit", returncode=0, stdout=json.dumps(payload), stderr="", elapsed=0.1
            ),
        ]
    )
    runner = OpenCodeRunner(
        tmp_path,
        boundary=NoBoundary(),
        process=process,
        model="opencode/iceman-free",
        fallback_models=["opencode/beam-free"],
        binary="opencode",
    )
    result = runner.execute(task, {}, tmp_path, timeout=30, cancelled=lambda: False)
    assert result == payload
    assert (
        process.calls[0]["argv"][process.calls[0]["argv"].index("--model") + 1]
        == "opencode/iceman-free"
    )
    assert (
        process.calls[1]["argv"][process.calls[1]["argv"].index("--model") + 1]
        == "opencode/beam-free"
    )
