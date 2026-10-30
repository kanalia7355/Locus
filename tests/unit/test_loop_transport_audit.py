from pathlib import Path

import pytest
from test_loop_execution import FixtureBoundary, FixtureProcess
from test_loop_foundation import task

from loop_engine.codex_runner import CodexRunner
from loop_engine.security import SafetyError


def test_boundary_wraps_every_codex_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("loop_engine.codex_runner.shutil.which", lambda unused: "codex")

    class WrappedBoundary(FixtureBoundary):
        def command(self, argv: list[str], workspace: Path) -> list[str]:
            return ["isolated-transport", *argv]

    process = FixtureProcess()
    runner = CodexRunner(tmp_path, boundary=WrappedBoundary(), process=process)  # type: ignore[arg-type]
    runner.execute(task(), {}, tmp_path, timeout=10, cancelled=lambda: False)
    assert len(process.calls) == 3
    assert all(call[0] == "isolated-transport" for call in process.calls)


def test_cancelled_runner_never_launches_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("loop_engine.codex_runner.shutil.which", lambda unused: "codex")
    process = FixtureProcess()
    runner = CodexRunner(tmp_path, boundary=FixtureBoundary(), process=process)  # type: ignore[arg-type]
    with pytest.raises(SafetyError):
        runner.execute(task(), {}, tmp_path, timeout=10, cancelled=lambda: True)
    assert process.calls == []
