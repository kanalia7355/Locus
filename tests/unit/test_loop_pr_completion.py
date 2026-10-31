from pathlib import Path
from typing import Any

import pytest
from test_loop_foundation import task

from loop_engine.approval import ApprovalQueue
from loop_engine.cli import initialize
from loop_engine.config import default
from loop_engine.github_manager import GitHubManager
from loop_engine.security import fingerprint


@pytest.mark.parametrize("missing", ["head_matches", "base_matches", None])
def test_pr_delivery_requires_exact_head_and_base(
    tmp_path: Path, missing: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = initialize(tmp_path, "Fixture")
    work = task()
    state.import_plan("Fixture", "hash", [work])
    config = default()["github"]
    config.update(enabled=True, repository="example/repo", delivery="pull_request")
    checkpoint = {"binding": fingerprint("verified"), "workspace": str(tmp_path)}

    class GitFixture:
        def finalize(self, *args: Any) -> dict[str, str]:
            return {"head": "h", "branch": "loop/TASK-001-fixture"}

        def _git(self, *args: Any) -> str:
            return "https://github.com/example/repo.git"

    class PRFixture(GitHubManager):
        def _existing(self, *args: Any) -> list[dict[str, Any]]:
            return [{"number": 1, "state": "OPEN", "headRefOid": "h"}]

        def _api(self, endpoint: str, *args: Any) -> dict[str, Any]:
            assert (
                endpoint == "repos/example/repo/pulls/1"
            )  # No protection API for PR-only delivery.
            return {
                "head": {
                    "sha": "other" if missing == "head_matches" else "h",
                    "repo": {"full_name": "example/repo"},
                },
                "base": {
                    "ref": "other" if missing == "base_matches" else "main",
                    "repo": {"full_name": "example/repo"},
                },
            }

        def remote_evidence(self, *args: Any) -> dict[str, Any]:
            pytest.fail("PR-only delivery must not invoke merge protection APIs")

    queue = ApprovalQueue(state)
    binding = fingerprint({"config": config, "binding": checkpoint["binding"]})
    identifier = queue.request(work.id, "publication", binding, "Approve exact scope?")
    queue.resolve(
        [{"id": identifier, "action": "approve", "target_hash": binding, "reason": "Fixture"}],
        "human",
    )
    manager = PRFixture(tmp_path, state, GitFixture(), config)  # type: ignore[arg-type]
    monkeypatch.setattr(
        "loop_engine.github_manager.ChecksMonitor.observe",
        lambda *args, **kwargs: {"status": "passed", "repairable": False},
    )
    delivered = manager.deliver(work, checkpoint, cancelled=lambda: False)
    assert delivered["complete"] is (missing is None)
    assert delivered["merged"] is False
