"""A killed Windows Job may return zero: that is never successful QA."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import loop_engine.runtime_diagnostics as runtime
from loop_engine.process import ProcessResult


@pytest.mark.parametrize("outcome", ["exit", "timeout", "cancelled"])
def test_zero_exit_code_without_normal_completion_cannot_pass_qa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    expected = {"uid": 1000, "daemon_absent": True, "network_denied": True, "lease_denied": True}
    docker = Mock()
    docker.run.side_effect = [
        ProcessResult(outcome, 0, json.dumps(expected)),
        ProcessResult("timeout", 0),
    ]
    boundary = SimpleNamespace(probe=lambda _: {"passed": False}, docker=docker)
    monkeypatch.setattr(runtime, "boundary_for", lambda _: boundary)
    monkeypatch.setattr(runtime, "runtime_identity", lambda _: "fixture-identity")
    evidence = runtime.probe(tmp_path)
    assert evidence["qa"] is (outcome == "exit")
    assert evidence["passed"] is False  # Unproven model is never promoted by successful QA.
    stored = json.loads((tmp_path / ".loop/runtime/live-runtime.json").read_text())
    assert stored == evidence
