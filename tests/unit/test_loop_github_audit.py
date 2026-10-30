import json
from pathlib import Path
from typing import Any

import pytest
from test_loop_foundation import task

from loop_engine.approval import ApprovalQueue
from loop_engine.cli import initialize
from loop_engine.config import default
from loop_engine.github_manager import GitHubManager, merge_reasons
from loop_engine.security import SafetyError, fingerprint


def test_effective_push_destination_is_checked_before_remote_mutation(tmp_path: Path) -> None:
    state = initialize(tmp_path, "Goal")
    work = task()
    state.import_plan("Goal", "hash", [work])
    config = default()["github"]
    config.update(enabled=True, repository="example/repo")
    checkpoint = {"binding": fingerprint("verified"), "workspace": str(tmp_path)}

    class BadPushGit:
        def finalize(self, *args: Any) -> dict[str, str]:
            return {"head": "h", "branch": "loop/TASK-001-task"}

        def _git(self, args: list[str], *other: Any) -> str:
            return (
                "https://unapproved.example/repo"
                if "--push" in args
                else "https://github.com/example/repo.git"
            )

    manager = GitHubManager(tmp_path, state, BadPushGit(), config)  # type: ignore[arg-type]
    binding = fingerprint({"config": config, "binding": checkpoint["binding"]})
    identifier = ApprovalQueue(state).request(work.id, "publication", binding, "Exact publication?")
    ApprovalQueue(state).resolve(
        [{"id": identifier, "action": "approve", "target_hash": binding, "reason": "Fixture"}],
        "human",
    )
    with pytest.raises(SafetyError, match="push destinations"):
        manager.deliver(work, checkpoint, cancelled=lambda: False)


def test_retargeted_pr_base_is_denied_and_atomic_api_gap_remains_explicit(tmp_path: Path) -> None:
    state = initialize(tmp_path, "Goal")
    work = task(risk_level="low")
    state.import_plan("Goal", "hash", [work])
    state.checkpoint(work.id, {"committed_head": "h"})
    config = default()["github"]
    config.update(
        repository="example/repo",
        required_checks=["ci", "loop-independent-review"],
        auto_merge="safe",
        auto_merge_allowed_paths=["src"],
    )
    binding = fingerprint({"repo": "example/repo", "base": "b", "head": "h", "policy": config})

    class RetargetedGitHub(GitHubManager):
        def _api(self, endpoint: str, cancelled: Any) -> Any:
            if endpoint.endswith("/protection"):
                return {
                    "required_status_checks": {
                        "strict": True,
                        "checks": [
                            {"context": "ci", "app_id": 1},
                            {"context": "loop-independent-review", "app_id": 2},
                        ],
                    },
                    "enforce_admins": {"enabled": True},
                    "required_pull_request_reviews": {
                        "required_approving_review_count": 1,
                        "dismiss_stale_reviews": True,
                    },
                    "required_conversation_resolution": {"enabled": True},
                }
            if "/rules/" in endpoint:
                return []
            if "/branches/" in endpoint:
                return {"commit": {"sha": "b"}, "protected": True}
            if "/check-runs" in endpoint:
                return {
                    "total_count": 2,
                    "check_runs": [
                        {
                            "name": name,
                            "status": "completed",
                            "conclusion": "success",
                            "app": {"id": index, "slug": "trusted-review-app"},
                            "external_id": binding,
                        }
                        for name, index in [("ci", 1), ("loop-independent-review", 2)]
                    ],
                }
            return {
                "head": {"sha": "h", "repo": {"full_name": "example/repo"}},
                "base": {
                    "ref": "retargeted",
                    "sha": "different",
                    "repo": {"full_name": "example/repo"},
                },
                "mergeable": True,
                "mergeable_state": "clean",
            }

        def _gh(self, *args: Any, **kwargs: Any) -> str:
            return json.dumps(
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {"nodes": [], "pageInfo": {"hasNextPage": False}}
                            }
                        }
                    }
                }
            )

    manager = RetargetedGitHub(tmp_path, state, None, config)  # type: ignore[arg-type]
    proof = manager.remote_evidence(
        work,
        {"snapshot": {"base": "b", "paths": ["src/app.txt"]}},
        {"number": 1, "headRefOid": "h"},
        lambda: False,
    )
    assert proof["base_matches"] is False
    assert proof["atomic_base_binding"] is False
    assert "base_matches" in merge_reasons(work, config, proof)
    assert "atomic_base_binding" in merge_reasons(work, config, proof)
