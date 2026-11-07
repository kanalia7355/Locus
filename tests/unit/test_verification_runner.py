"""Verification concurrency must retain failures and the original shared deadline."""

import subprocess
import sys
from threading import Barrier
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import verify_loop


def test_both_groups_run_concurrently_and_retain_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    barrier = Barrier(2)
    commands: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert 0 < kwargs["timeout"] <= 5
        barrier.wait(timeout=3)
        return subprocess.CompletedProcess(command, 1 if "tests/unit" in command else 0)

    monkeypatch.setattr(verify_loop.subprocess, "run", run)
    results = verify_loop.windows_test_groups(timeout=5)
    assert [result["exit_code"] for result in results] == [1, 0]
    assert [result["outcome"] for result in results] == ["exit", "exit"]
    selected = [path for command in commands for path in command if path.startswith("tests/")]
    assert sorted(selected) == ["tests/e2e", "tests/integration", "tests/unit"]
    assert (
        len(
            {
                argument
                for command in commands
                for argument in command
                if argument.startswith("cache_dir=")
            }
        )
        == 2
    )


def test_exhausted_shared_window_never_launches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(verify_loop.subprocess, "run", lambda command, **kw: calls.append(command))
    results = verify_loop.windows_test_groups(timeout=0)
    assert calls == []
    assert [result["exit_code"] for result in results] == [124, 124]
    assert all(result["outcome"] == "deadline_before_start" for result in results)


def test_timeout_and_launch_error_are_both_retained(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(command: list[str], **kwargs: Any) -> None:
        if "tests/unit" in command:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        raise OSError("synthetic launch failure")

    monkeypatch.setattr(verify_loop.subprocess, "run", run)
    results = verify_loop.windows_test_groups(timeout=5)
    assert [result["exit_code"] for result in results] == [124, 125]
    assert [result["outcome"] for result in results] == ["timeout", "launch_error"]


def test_real_children_obey_remaining_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    original = subprocess.run
    timeouts: list[float] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        timeouts.append(kwargs["timeout"])
        return original([sys.executable, "-c", "import time; time.sleep(5)"], **kwargs)

    monkeypatch.setattr(verify_loop.subprocess, "run", run)
    results = verify_loop.windows_test_groups(timeout=0.2)
    assert all(0 < value <= 0.2 for value in timeouts)
    assert [result["exit_code"] for result in results] == [124, 124]


def test_clock_rounding_never_expands_the_configured_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1000.2 - 1000 is slightly greater than 0.2 in binary floating point.
    monkeypatch.setattr(verify_loop, "time", SimpleNamespace(monotonic=lambda: 1000.0))
    timeouts: list[float] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        timeouts.append(kwargs["timeout"])
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(verify_loop.subprocess, "run", run)
    assert all(result["exit_code"] == 0 for result in verify_loop.windows_test_groups(timeout=0.2))
    assert timeouts == [0.2, 0.2]
