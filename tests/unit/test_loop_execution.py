import json
import sys
from pathlib import Path
from typing import Any

from test_loop_foundation import task

from loop_engine.codex_runner import CodexRunner
from loop_engine.process import ProcessResult, ProcessRunner
from loop_engine.verification import Verifier


class FixtureBoundary:
    """Test-only transport; never selectable through runtime configuration."""

    def require(self, workspace: Path, control_root: Path) -> None:
        pass

    def command(self, argv: list[str], workspace: Path) -> list[str]:
        return argv


class FixtureProcess:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, argv: list[str], cwd: Path, **kwargs: Any) -> ProcessResult:
        self.calls.append(argv)
        if "exec" in argv:
            result = {
                "task_id": "TASK-001",
                "status": "implemented",
                "summary": "Fixture result",
                "files_changed": ["src/main.py"],
                "tests_added": [],
                "issues": [],
                "approval_requests": [],
            }
            return ProcessResult(
                "exit",
                0,
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": json.dumps(result)},
                    }
                ),
            )
        return ProcessResult("exit", 0)


def test_actual_process_timeout_and_output_bound(tmp_path: Path) -> None:
    process = ProcessRunner()
    success = process.run([sys.executable, "-c", 'print("bounded")'], tmp_path, timeout=10)
    assert success.outcome == "exit" and success.returncode == 0
    timed = process.run(
        [sys.executable, "-c", "import time; time.sleep(10)"], tmp_path, timeout=0.15
    )
    assert timed.outcome == "timeout"
    overflow = process.run(
        [sys.executable, "-c", 'print("x" * 20000)'], tmp_path, timeout=5, output_limit=100
    )
    assert overflow.outcome == "output_limit" and len(overflow.stdout) <= 100


def test_runner_uses_documented_restrictive_flags_and_schema(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr("loop_engine.codex_runner.shutil.which", lambda unused: sys.executable)
    process = FixtureProcess()
    runner = CodexRunner(tmp_path, boundary=FixtureBoundary(), process=process)  # type: ignore[arg-type]
    result = runner.execute(task(), {}, tmp_path, timeout=10, cancelled=lambda: False)
    assert result["status"] == "implemented"
    args = process.calls[-1]
    assert "--ephemeral" in args and "--output-schema" in args
    assert args[args.index("--sandbox") + 1] == "workspace-write"
    assert "multi_agent" in args and 'approval_policy="never"' in args
    assert not any("danger" in arg or "ignore-rules" in arg or "resume" == arg for arg in args)


def test_missing_skipped_and_failed_required_verification_do_not_pass(tmp_path: Path) -> None:
    profile = {
        "python": [
            {
                "name": "tests",
                "level": "functional",
                "argv": ["{python}", "-c", "raise SystemExit(1)"],
                "required": True,
            }
        ]
    }
    assert (
        Verifier({}).run("missing", tmp_path, tmp_path, timeout=1, cancelled=lambda: False)[
            "status"
        ]
        == "unavailable"
    )
    skipped = Verifier(profile).run(
        "python", tmp_path, tmp_path, timeout=1, cancelled=lambda: False
    )
    assert not skipped["passed"] and skipped["checks"][0]["status"] == "skipped"
    failed = Verifier(profile, boundary=FixtureBoundary()).run(
        "python", tmp_path, tmp_path, timeout=5, cancelled=lambda: False
    )
    assert not failed["passed"] and failed["checks"][0]["status"] == "failed"
