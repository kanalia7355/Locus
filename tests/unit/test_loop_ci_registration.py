import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from test_loop_checks import MonitorFixture
from test_loop_foundation import task

from loop_engine.approval import ApprovalQueue
from loop_engine.cli import initialize
from loop_engine.config import default
from loop_engine.github_manager import GitHubManager
from loop_engine.security import SafetyError, fingerprint


def setup_wait(tmp_path: Path, *, active: bool = True) -> tuple[Any, Any, str, dict, dict]:
    state = initialize(tmp_path, "Fixture")
    work = task(risk_level="low")
    state.import_plan("Fixture", "hash", [work])
    state.transition(work.id, "planned", "awaiting_approval", version=0)
    policy = default()["github"]
    policy.update(
        enabled=True,
        repository="example/repo",
        delivery="pull_request",
        required_checks=["unit", "title"],
    )
    state.set_metadata("spec_snapshot", {"policy": {"github": policy}})
    checkpoint = {
        "verified": True,
        "binding": fingerprint("reviewed"),
        "committed_head": "h",
        "workspace": str(tmp_path),
        "snapshot": {"paths": ["src/app.py"], "base": "b"},
    }
    state.checkpoint(work.id, checkpoint)
    previous = {
        "status": "missing",
        "head": "h",
        "checks": [{"name": "unit", "bucket": "pending" if active else "pass"}],
        "runs": [
            {
                "headSha": "h",
                "status": "queued" if active else "completed",
                "conclusion": "" if active else "success",
            }
        ],
    }
    state.record_pr(work.id, {"ci": previous, "headRefOid": "h", "number": 1})
    queue = ApprovalQueue(state)
    identifier = queue.request(
        work.id,
        "scope",
        fingerprint({"binding": checkpoint["binding"], "ci": previous}),
        "CI held (missing, unclassified). Inspect configured checks.",
    )
    observed = {
        "status": "passed",
        "head": "h",
        "checks": [{"name": name, "bucket": "pass"} for name in policy["required_checks"]],
        "runs": [{"headSha": "h", "status": "completed", "conclusion": "success"}],
    }
    return state, queue, identifier, observed, policy


def test_late_registration_retires_only_condition_not_human_approvals(tmp_path: Path) -> None:
    state, queue, identifier, observed, _ = setup_wait(tmp_path)
    human = queue.request(
        "TASK-001", "security", fingerprint("production"), "Approve production scope?"
    )
    assert queue.retire_ci_registration("TASK-001", observed)
    records = {item["id"]: item for item in queue.decisions()}
    assert records[identifier]["status"] == "obsolete"
    assert records[identifier]["actor"] == "system:ci-observation"
    assert records[human]["status"] == "pending"
    assert queue.pending_for("TASK-001")
    assert queue.status("TASK-001", "merge", fingerprint("merge")) is None
    assert not queue.retire_ci_registration("TASK-001", observed)


@pytest.mark.parametrize(
    "fault",
    [
        "stale_head",
        "missing_name",
        "pending",
        "fail",
        "cancel",
        "skipping",
        "running",
        "failed_run",
        "empty_runs",
        "binding",
        "merged_delivery",
        "auto_merge",
    ],
)
def test_incomplete_or_unbound_evidence_cannot_retire_wait(tmp_path: Path, fault: str) -> None:
    state, queue, identifier, observed, policy = setup_wait(tmp_path)
    if fault == "stale_head":
        observed["head"] = "other"
    elif fault == "missing_name":
        observed["checks"].pop()
    elif fault in {"pending", "fail", "cancel", "skipping"}:
        observed["checks"][0]["bucket"] = fault
    elif fault == "running":
        observed["runs"][0]["status"] = "in_progress"
    elif fault == "failed_run":
        observed["runs"][0]["conclusion"] = "failure"
    elif fault == "empty_runs":
        observed["runs"] = []
    elif fault == "binding":
        checkpoint = state.get_checkpoint("TASK-001")
        state.checkpoint("TASK-001", {**checkpoint, "binding": fingerprint("changed")})
    else:
        policy["delivery" if fault == "merged_delivery" else "auto_merge"] = (
            "merged" if fault == "merged_delivery" else "safe"
        )
        state.set_metadata("spec_snapshot", {"policy": {"github": policy}})
    assert not queue.retire_ci_registration("TASK-001", observed)
    assert (
        next(item for item in queue.decisions() if item["id"] == identifier)["status"] == "pending"
    )


def test_terminal_missing_check_remains_a_real_decision(tmp_path: Path) -> None:
    _, queue, _, observed, _ = setup_wait(tmp_path, active=False)
    assert not queue.retire_ci_registration("TASK-001", observed)
    assert queue.pending_for("TASK-001")


@pytest.mark.parametrize(
    "action,status", [("approve", "approved"), ("reject", "rejected"), ("revise", "revise")]
)
def test_concurrent_human_choice_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str, status: str
) -> None:
    _, queue, identifier, observed, _ = setup_wait(tmp_path)
    original = queue.ci_registration_decision

    def human_choice_between_read_and_update(task_id: str) -> dict | None:
        decision = original(task_id)
        assert decision is not None
        queue.resolve(
            [
                {
                    "id": identifier,
                    "action": action,
                    "target_hash": decision["target_hash"],
                    "reason": "Concurrent human fixture choice",
                }
            ],
            "human-fixture",
        )
        return decision

    monkeypatch.setattr(queue, "ci_registration_decision", human_choice_between_read_and_update)
    assert not queue.retire_ci_registration("TASK-001", observed)
    record = next(item for item in queue.decisions() if item["id"] == identifier)
    assert record["status"] == status and record["actor"] == "human-fixture"


@pytest.mark.parametrize(
    "run_status,expected",
    [("queued", "pending"), ("in_progress", "pending"), ("completed", "missing")],
)
def test_not_yet_registered_context_waits_only_with_positive_active_evidence(
    tmp_path: Path, run_status: str, expected: str
) -> None:
    class Registering(MonitorFixture):
        def _gh(self, args: list[str], *other: Any) -> str:
            result = super()._gh(args, *other)
            if args[:2] == ["run", "list"]:
                values = json.loads(result)
                values[0]["status"] = run_status
                return json.dumps(values)
            return result

    monitor = Registering(tmp_path, "pass")
    monitor.required.append("title")
    assert monitor.observe(1, "new", cancelled=lambda: False)["status"] == expected


@pytest.mark.parametrize("changed", ["source", "repository", "head", "base", None])
def test_remote_identity_and_verified_source_are_rechecked_before_retirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str | None
) -> None:
    state, queue, _, observed, policy = setup_wait(tmp_path)
    checkpoint = state.get_checkpoint("TASK-001")

    class GitFixture:
        def snapshot(self, *args: Any) -> dict:
            return {"changed": True} if changed == "source" else checkpoint["snapshot"]

        def _git(self, *args: Any) -> str:
            return "h"

    class Manager(GitHubManager):
        def _api(self, *args: Any) -> dict:
            return {
                "state": "open",
                "head": {
                    "sha": "other" if changed == "head" else "h",
                    "repo": {
                        "full_name": "other/repo" if changed == "repository" else "example/repo"
                    },
                },
                "base": {
                    "ref": "other" if changed == "base" else "main",
                    "repo": {"full_name": "example/repo"},
                },
            }

    monkeypatch.setattr(
        "loop_engine.github_manager.ChecksMonitor.observe",
        lambda *args, **kwargs: deepcopy(observed),
    )
    manager = Manager(tmp_path, state, GitFixture(), policy)  # type: ignore[arg-type]
    if changed:
        with pytest.raises(SafetyError):
            manager.reconcile_ci_registration(
                state.task("TASK-001"), checkpoint, cancelled=lambda: False
            )
        assert queue.pending_for("TASK-001")
    else:
        assert manager.reconcile_ci_registration(
            state.task("TASK-001"), checkpoint, cancelled=lambda: False
        )
        assert not queue.pending_for("TASK-001")
