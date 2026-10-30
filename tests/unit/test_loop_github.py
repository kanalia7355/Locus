from pathlib import Path
from typing import Any

from test_loop_foundation import task

from loop_engine.approval import ApprovalQueue
from loop_engine.cli import initialize
from loop_engine.config import default
from loop_engine.github_manager import GitHubManager, merge_reasons
from loop_engine.security import fingerprint


def evidence() -> dict[str, Any]:
    keys = (
        "human_authorized",
        "review_passed",
        "trusted_review_publisher",
        "review_head_base_policy_bound",
        "ci_complete",
        "protection_verified",
        "strict_current_base",
        "conversations_resolved",
        "mergeable",
        "head_matches",
        "base_matches",
        "atomic_base_binding",
    )
    return {**dict.fromkeys(keys, True), "pending_approvals": False, "paths": ["src/app.py"]}


def test_each_merge_safety_gate_is_mandatory_and_never_inferred() -> None:
    config = default()["github"]
    config.update(auto_merge="safe", auto_merge_allowed_paths=["src"])
    work = task(risk_level="low")
    proof = evidence()
    assert merge_reasons(work, config, proof) == []
    for key, value in proof.items():
        if isinstance(value, bool) and value:
            assert merge_reasons(work, config, {**proof, key: False}), key
    assert merge_reasons(work, config, {**proof, "pending_approvals": True})
    assert merge_reasons(work, config, {**proof, "paths": [".github/workflows/unsafe.yml"]})
    assert merge_reasons(task(risk_level="high"), config, proof)
    assert merge_reasons(work, {**config, "auto_merge": "off"}, proof)


def test_pr_creation_is_explicitly_approved_and_reconciled_before_retry(tmp_path: Path) -> None:
    state = initialize(tmp_path, "Goal")
    work = task(risk_level="low")
    state.import_plan("Goal", "hash", [work])
    config = default()["github"]
    config.update(enabled=True, repository="example/research", delivery="pull_request")
    checkpoint = {
        "binding": fingerprint("source"),
        "workspace": str(tmp_path),
        "snapshot": {"paths": ["src/app.py"]},
    }

    class GitFixture:
        def finalize(self, *args: Any) -> dict[str, str]:
            return {"head": "head-sha", "branch": "loop/TASK-001-fixture"}

        def _git(self, args: list[str], *other: Any) -> str:
            return (
                "https://github.com/example/research.git"
                if args[:2] == ["remote", "get-url"]
                else ""
            )

    class GitHubFixture(GitHubManager):
        created = 0

        def _existing(self, branch: str, cancelled: Any) -> list[dict[str, Any]]:
            return (
                [
                    {
                        "number": 1,
                        "url": "https://github.com/example/research/pull/1",
                        "state": "OPEN",
                        "headRefOid": "head-sha",
                    }
                ]
                if self.created
                else []
            )

        def _gh(self, args: list[str], **kwargs: Any) -> str:
            if args[:2] == ["pr", "create"]:
                self.created += 1
                assert "--body-file" in args and "--head" in args and "--no-maintainer-edit" in args
            return ""

        def remote_evidence(self, *args: Any) -> dict[str, Any]:
            return {"ci_complete": False}

    manager = GitHubFixture(tmp_path, state, GitFixture(), config)  # type: ignore[arg-type]
    assert not manager.deliver(work, checkpoint, cancelled=lambda: False)["complete"]
    assert manager.created == 0
    decision = ApprovalQueue(state).decisions()[0]
    ApprovalQueue(state).resolve(
        [
            {
                "id": decision["id"],
                "action": "approve",
                "reason": "Fixture repository approval",
                "target_hash": decision["target_hash"],
            }
        ],
        "human",
    )
    assert not manager.deliver(work, checkpoint, cancelled=lambda: False)["complete"]
    assert not manager.deliver(work, checkpoint, cancelled=lambda: False)["complete"]
    assert manager.created == 1
