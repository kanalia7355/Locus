import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from loop_engine.completion_gate import reasons
from loop_engine.gap_analyzer import analyze
from loop_engine.goal_evaluator import criteria
from loop_engine.process import ProcessRunner
from loop_engine.progress_evaluator import evaluate
from loop_engine.security import fingerprint


def source() -> dict[str, Any]:
    return {
        "goal.md": "Feature and safe edge cases",
        "acceptance.md": "- Implement feature\n- Clamp negatives\n",
    }


def report(head: str = "a" * 40, *, complete: bool = False) -> dict[str, Any]:
    ids = list(criteria(source()))
    return {
        "head": head,
        "spec_hash": fingerprint(source()),
        "criteria": [
            {
                "id": identifier,
                "status": "met" if complete else "unmet",
                "evidence": "Observed src/app.py and reproducible checks",
            }
            for identifier in ids
        ],
        "gaps": []
        if complete
        else [
            {
                "key": "negative",
                "category": "bug",
                "severity": "low",
                "title": "Clamp negative inputs",
                "allowed_paths": ["src/app.py"],
                "criterion_ids": [ids[1]],
                "file": "src/app.py",
                "anchor": "return value * 2",
                "evidence": "Negative input returns -2",
                "reproduction": "Call total(-1); observed -2, expected 0",
                "acceptance": ["total(-1) returns 0"],
                "expected_effect": "Eliminate invalid negative totals; preserve positive inputs",
                "depends_on": [],
            }
        ],
        "review_passed": True,
        "blocking_findings": [],
    }


def snapshot() -> dict[str, Any]:
    return {"head": "a" * 40, "files": {"src/app.py": "return value * 2"}}


@pytest.mark.parametrize(
    "mutation", ["criterion", "head", "anchor", "benefit", "reproduction", "goal_change"]
)
def test_unsubstantiated_or_changed_goal_evaluation_rejected(mutation: str) -> None:
    value = report()
    if mutation == "criterion":
        value["criteria"].pop()
    elif mutation == "head":
        value["head"] = "b" * 40
    elif mutation in {"anchor", "reproduction"}:
        value["gaps"][0][mutation] = ""
    elif mutation == "benefit":
        value["gaps"][0]["expected_effect"] = ""
    else:
        value["relaxed_goal"] = "Accept missing features"
    with pytest.raises(ValueError):
        analyze(value, source(), snapshot())


def test_reworded_finding_has_same_identity_and_stagnation_persists() -> None:
    first = report()
    gap = analyze(first, source(), snapshot())
    changed = deepcopy(first)
    changed["gaps"][0].update(key="new wording", title="Different wording")
    assert analyze(changed, source(), snapshot())[0]["identity"] == gap[0]["identity"]
    progress: dict[str, Any] = {}
    for _ in range(4):
        progress = evaluate(progress, first, gap, ["TASK-001:verification_failed"])
    assert progress["halt"]


def test_completion_requires_current_required_verification_and_no_decisions() -> None:
    value = report(complete=True)
    verified = {
        "head": value["head"],
        "spec_hash": value["spec_hash"],
        "passed": True,
        "checks": [{"required": True, "status": "passed"}],
    }
    assert not reasons(
        value, verified, [], [], current_head=value["head"], spec_hash=value["spec_hash"]
    )
    assert reasons(
        value,
        {**verified, "checks": []},
        [],
        [],
        current_head=value["head"],
        spec_hash=value["spec_hash"],
    )
    assert reasons(
        value,
        verified,
        [],
        [{"status": "pending"}],
        current_head=value["head"],
        spec_hash=value["spec_hash"],
    )
    assert reasons(value, verified, [], [], current_head="b" * 40, spec_hash=value["spec_hash"])


def test_cancelled_process_never_launches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("A cancelled run must not launch a process")

    monkeypatch.setattr("subprocess.Popen", forbidden)
    result = ProcessRunner().run(
        [sys.executable, "-c", "pass"], tmp_path, timeout=10, cancelled=lambda: True
    )
    assert result.outcome == "cancelled"
