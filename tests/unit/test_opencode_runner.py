"""OpenCode CLI adapter: model selection, invocation, parsing, and fail-closed errors."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from loop_engine.models import Task


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


class FakeProcess:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, argv, cwd, **kwargs):
        self.calls.append({"argv": argv, "cwd": cwd, **kwargs})
        return self.result


class NoBoundary:
    file_proposals = False
    c_min = False

    def require(self, workspace, control_root):
        return None

    def command(self, argv, workspace):
        return argv


def test_execute_builds_noninteractive_command_and_returns_validated_result(tmp_path: Path) -> None:
    from loop_engine.opencode_runner import OpenCodeRunner

    task = sample_task()
    result_payload = {
        "task_id": "TASK-001",
        "status": "implemented",
        "summary": "ok",
        "files_changed": ["backend/app/x.py"],
        "tests_added": [],
        "issues": [],
        "approval_requests": [],
    }
    process = FakeProcess(
        SimpleNamespace(
            outcome="exit", returncode=0, stdout=json.dumps(result_payload), stderr="", elapsed=0.1
        )
    )
    runner = OpenCodeRunner(
        tmp_path,
        boundary=NoBoundary(),
        process=process,
        model="opencode/iceman-free",
        binary="opencode",
    )

    result = runner.execute(
        task, {"goal": "synthetic"}, tmp_path, timeout=30, cancelled=lambda: False
    )

    assert result == result_payload
    assert process.calls
    argv = process.calls[0]["argv"]
    assert argv[:2] == ["opencode", "run"]
    assert "--model" in argv and "opencode/iceman-free" in argv
    assert "--format" in argv


def test_execute_classifies_quota_exhaustion(tmp_path: Path) -> None:
    from loop_engine.opencode_runner import OpenCodeError, OpenCodeRunner

    task = sample_task()
    process = FakeProcess(
        SimpleNamespace(
            outcome="exit",
            returncode=1,
            stdout="",
            stderr="quota exceeded for free model",
            elapsed=0.1,
        )
    )
    runner = OpenCodeRunner(
        tmp_path,
        boundary=NoBoundary(),
        process=process,
        model="opencode/iceman-free",
        binary="opencode",
    )

    with pytest.raises(OpenCodeError) as exc:
        runner.execute(task, {}, tmp_path, timeout=30, cancelled=lambda: False)
    assert exc.value.category == "quota_exhausted"


def test_execute_times_out_and_reports_timeout(tmp_path: Path) -> None:
    from loop_engine.opencode_runner import OpenCodeError, OpenCodeRunner

    task = sample_task()
    process = FakeProcess(
        SimpleNamespace(outcome="timeout", returncode=None, stdout="", stderr="", elapsed=30.0)
    )
    runner = OpenCodeRunner(
        tmp_path,
        boundary=NoBoundary(),
        process=process,
        model="opencode/iceman-free",
        binary="opencode",
    )

    with pytest.raises(OpenCodeError) as exc:
        runner.execute(task, {}, tmp_path, timeout=30, cancelled=lambda: False)
    assert exc.value.category == "timeout"


def test_execute_rejects_malformed_output(tmp_path: Path) -> None:
    from loop_engine.opencode_runner import OpenCodeError, OpenCodeRunner

    task = sample_task()
    process = FakeProcess(
        SimpleNamespace(outcome="exit", returncode=0, stdout="not-json", stderr="", elapsed=0.1)
    )
    runner = OpenCodeRunner(
        tmp_path,
        boundary=NoBoundary(),
        process=process,
        model="opencode/iceman-free",
        binary="opencode",
    )

    with pytest.raises(OpenCodeError) as exc:
        runner.execute(task, {}, tmp_path, timeout=30, cancelled=lambda: False)
    assert exc.value.category == "malformed_output"


def test_execute_parses_json_line_result(tmp_path: Path) -> None:
    from loop_engine.opencode_runner import OpenCodeRunner

    task = sample_task()
    result_payload = {
        "task_id": "TASK-001",
        "status": "implemented",
        "summary": "ok",
        "files_changed": ["backend/app/x.py"],
        "tests_added": [],
        "issues": [],
        "approval_requests": [],
    }
    stdout = "\n".join([json.dumps({"type": "event"}), json.dumps(result_payload)])
    process = FakeProcess(
        SimpleNamespace(outcome="exit", returncode=0, stdout=stdout, stderr="", elapsed=0.1)
    )
    runner = OpenCodeRunner(
        tmp_path,
        boundary=NoBoundary(),
        process=process,
        model="opencode/iceman-free",
        binary="opencode",
    )
    assert runner.execute(task, {}, tmp_path, timeout=30, cancelled=lambda: False) == result_payload
