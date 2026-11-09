"""Coverage union and the unchanged total deadline are observable QA contracts."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from coverage import CoverageData

from scripts import verify


def measured(path: Path) -> dict[str, set[int]]:
    data = CoverageData(basename=str(path))
    data.read()
    return {Path(name).name: set(data.lines(name) or []) for name in data.measured_files()}


def test_parallel_coverage_matches_a_real_serial_run(tmp_path: Path) -> None:
    (tmp_path / "tests/integration").mkdir(parents=True)
    (tmp_path / "tests/e2e").mkdir()
    (tmp_path / "demo.py").write_text("def left():\n    return 1\n\ndef right():\n    return 2\n")
    (tmp_path / "tests/integration/test_left.py").write_text(
        "from demo import left\ndef test_left():\n    assert left() == 1\n"
    )
    (tmp_path / "tests/test_right.py").write_text(
        "from demo import right\ndef test_right():\n    assert right() == 2\n"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath=["."]\n[tool.coverage.run]\nsource=["demo"]\n'
    )
    checks = verify.python_test_checks(tmp_path, 20)
    assert all(item["exit_code"] == 0 for item in checks)
    assert [item["name"] for item in checks][-2:] == ["coverage-combine", "coverage-report"]
    combined = next((tmp_path / ".loop/runtime/coverage").glob("*/combined"))
    serial = tmp_path / "serial-coverage"
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--cov", "--cov-report="],
        cwd=tmp_path,
        env={**os.environ, "COVERAGE_FILE": str(serial)},
        timeout=20,
        check=True,
    )  # noqa: S603
    assert measured(combined) == measured(serial) == {"demo.py": {1, 2, 4, 5}}


def fake_groups(monkeypatch, *, code=0, create=True, finish=None):
    def run(groups, **kwargs):
        if create:
            for name, _ in groups:
                Path(kwargs["environments"][name]["COVERAGE_FILE"]).write_text("synthetic")
        if finish:
            finish(kwargs)
        return [{"name": name, "exit_code": code, "outcome": "exit"} for name, _ in groups]

    monkeypatch.setattr(verify, "bounded_test_groups", run)


def test_failed_group_never_runs_coverage_postprocessing(tmp_path: Path, monkeypatch) -> None:
    fake_groups(monkeypatch, code=7)
    calls = []
    monkeypatch.setattr(verify.subprocess, "run", lambda *a, **kw: calls.append(a))
    checks = verify.python_test_checks(tmp_path, 10)
    assert [item["exit_code"] for item in checks] == [7, 7] and calls == []


def test_prior_coverage_cannot_replace_missing_current_data(tmp_path: Path, monkeypatch) -> None:
    stale = tmp_path / ".loop/runtime/coverage/old"
    stale.mkdir(parents=True)
    for name, _ in verify.PYTHON_GROUPS:
        (stale / name).write_text("old data")
    fake_groups(monkeypatch, create=False)
    checks = verify.python_test_checks(tmp_path, 10)
    assert checks[-1]["exit_code"] == 1 and checks[-1]["outcome"] == "missing_current_data"


def test_postprocessing_cannot_get_a_fresh_deadline(tmp_path: Path, monkeypatch) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(verify, "time", SimpleNamespace(monotonic=lambda: clock["now"]))

    def finish(kwargs):
        assert kwargs["deadline"] == 105.0
        clock["now"] = 106.0

    fake_groups(monkeypatch, finish=finish)
    calls = []
    monkeypatch.setattr(verify.subprocess, "run", lambda *a, **kw: calls.append(a))
    checks = verify.python_test_checks(tmp_path, 10, deadline=105.0)
    assert checks[-1]["exit_code"] == 124 and checks[-1]["outcome"] == "deadline_before_start"
    assert calls == []


@pytest.mark.parametrize("stage", ["combine", "report"])
def test_coverage_command_failure_is_not_a_pass(tmp_path: Path, monkeypatch, stage) -> None:
    fake_groups(monkeypatch)
    calls = []

    def run(command, **kwargs):
        assert 0 < kwargs["timeout"] <= 10
        calls.append(command[3])
        return subprocess.CompletedProcess(command, 31 if command[3] == stage else 0)

    monkeypatch.setattr(verify.subprocess, "run", run)
    checks = verify.python_test_checks(tmp_path, 10)
    assert checks[-1]["exit_code"] == 31
    assert calls == (["combine"] if stage == "combine" else ["combine", "report"])
