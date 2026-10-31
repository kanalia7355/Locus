"""Simulated remote delivery, explicitly not App/GitHub deployment proof."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from loop_engine.broker_policy import writer_rulesets
from loop_engine.broker_policy_reader import CI_CONTEXTS, PREFIX, observe_policy
from loop_engine.broker_transport import GitHubBrokerTransport
from loop_engine.github_app import GitHubMissing
from loop_engine.merge_broker import BrokerJournal, MergeBinding, MergeBroker
from loop_engine.models import Task
from loop_engine.review_publication import (
    PublicationJournal,
    ReviewInputs,
    ReviewPublicationService,
)
from loop_engine.reviewer import Reviewer
from loop_engine.security import SafetyError

H, B, M, L = (char * 40 for char in "abdc")


class World:
    def __init__(self) -> None:
        self.base = B
        self.merged = False
        self.lock: dict[str, Any] | None = None
        self.lock_commit: dict[str, Any] = {}
        self.writes: list[tuple[str, str]] = []
        self.checks = [
            {
                "id": index + 1,
                "name": name,
                "head_sha": H,
                "status": "completed",
                "conclusion": "success",
                "app": {"id": 15368},
            }
            for index, name in enumerate(CI_CONTEXTS)
        ]
        self.reviews: list[dict[str, Any]] = []
        self.queued: dict[str, str] | None = None
        self.unresolved = False
        self.lost: str | None = None
        self.policy: dict[str, Any] = {
            **{
                name: {"enabled": True}
                for name in (
                    "enforce_admins",
                    "required_conversation_resolution",
                    "required_linear_history",
                )
            },
            **{name: {"enabled": False} for name in ("allow_force_pushes", "allow_deletions")},
            "required_pull_request_reviews": {
                "dismiss_stale_reviews": True,
                "require_last_push_approval": True,
                "required_approving_review_count": 1,
            },
            "required_status_checks": {
                "strict": True,
                "checks": [{"context": name, "app_id": 15368} for name in CI_CONTEXTS]
                + [{"context": "loop-independent-review", "app_id": 5555922}],
            },
        }
        self.rules = [
            {"id": index + 1, **rule}
            for index, rule in enumerate(writer_rulesets(5556060, 5555922))
        ]

    def detail(self) -> dict[str, Any]:
        repo = {"full_name": "kanalia7355/Locus", "id": 1440108668}
        return {
            "number": 7,
            "draft": False,
            "state": "closed" if self.merged else "open",
            "user": {"login": "kanalia7355"},
            "title": "fix(app): preserve source binding",
            "head": {"sha": H, "repo": repo},
            "base": {"ref": "main", "sha": self.base, "repo": repo},
            "mergeable": True,
            "mergeable_state": "clean",
            "merged": self.merged,
            "merge_commit_sha": M if self.merged else None,
            "merged_by": {"login": "locus-merge[bot]", "type": "Bot"},
        }

    def call(self, role: str, method: str, path: str, document: Any) -> Any:
        if method != "GET":
            self.writes.append((method, path))
        if self.lost == path:
            raise TimeoutError("simulated lost response")
        if path == PREFIX + "/branches/main":
            return {"name": "main", "protected": True, "commit": {"sha": self.base}}
        if path.endswith("/protection"):
            return deepcopy(self.policy)
        if "/rulesets?" in path:
            return [{"id": rule["id"]} for rule in self.rules]
        if "/rulesets/" in path:
            return deepcopy(self.rules[int(path.rsplit("/", 1)[1]) - 1])
        if "/git/commits" in path:
            if method == "POST":
                self.lock_commit = {**document, "parents": [{"sha": B}]}
                return {"sha": L}
            return deepcopy(self.lock_commit) if path.endswith(L) else {"tree": {"sha": H}}
        if path.endswith("/git/refs"):
            if self.lock is not None:
                raise SafetyError("Remote lock exists")
            self.lock = {"ref": document["ref"], "object": {"sha": L, "type": "commit"}}
            return deepcopy(self.lock)
        if "/git/ref" in path:
            if method == "DELETE":
                self.lock = None
                return None
            if self.lock is None:
                raise GitHubMissing("absent")
            return deepcopy(self.lock)
        if path.endswith("/reviews") and method == "POST":
            assert role == "review"
            value = {
                "id": 50,
                "user": {"login": "locus-review[bot]", "type": "Bot"},
                "state": "APPROVED",
                "commit_id": document["commit_id"],
                "body": document["body"],
            }
            self.reviews.append(value)
            return deepcopy(value)
        if "/reviews?" in path:
            return deepcopy(self.reviews)
        if "/check-runs?" in path:
            return {"total_count": len(self.checks), "check_runs": deepcopy(self.checks)}
        if path.endswith("/check-runs") and method == "POST":
            assert role == "review"
            value = {**document, "id": 60, "app": {"id": 5555922, "slug": "locus-review"}}
            self.checks.append(value)
            return deepcopy(value)
        if path.endswith("/merge") and method == "PUT":
            assert role == "merge" and document["sha"] == H
            assert document["merge_method"] == "squash"
            self.merged, self.base = True, M
            return {"merged": True, "sha": M}
        if path.endswith("/commits/" + M):
            return {"sha": M, "parents": [{"sha": B}]}
        if path.endswith("/pulls/7"):
            return self.detail()
        raise AssertionError((method, path))


class API:
    def __init__(self, world: World, role: str) -> None:
        self.world, self.role = world, role
        self.app_id = 5555922 if role == "review" else 5556060

    def call(self, method: str, path: str, document: Any = None) -> Any:
        return self.world.call(self.role, method, path, document)

    def pull_request_state(self, pull: int) -> dict[str, Any]:
        assert pull == 7
        nodes = [{"isResolved": False}] if self.world.unresolved else []
        return {
            "headRefOid": H,
            "baseRefOid": self.world.base,
            "reviewDecision": "APPROVED" if self.world.reviews else "REVIEW_REQUIRED",
            "autoMergeRequest": self.world.queued,
            "reviewThreads": {
                "nodes": nodes,
                "totalCount": len(nodes),
                "pageInfo": {"hasNextPage": False},
            },
        }

    def bot_login(self) -> str:
        return f"locus-{self.role}[bot]"


class ReviewAuthority:
    def __init__(self, root: Path) -> None:
        self.inputs = ReviewInputs(
            Task("TASK-002", "fix source", ["preserve source"], "repository", ["backend/**"]),
            root,
            {},
            {"base": B, "paths": ["backend/example.py"]},
            {"passed": True, "checks": [{"required": True, "status": "passed"}]},
            H,
        )
        self.stale = False

    def load(self, task_id: str) -> ReviewInputs:
        assert task_id == self.inputs.task.id
        return self.inputs

    def require(self, inputs: ReviewInputs) -> None:
        if self.stale:
            raise SafetyError("simulated stale source or deployment")


class FreshReviewer:
    def __init__(self) -> None:
        self.calls = 0
        self.disposition = "pass"
        self.findings: list[dict[str, Any]] = []

    def evaluate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return {"task_id": "TASK-002", "disposition": self.disposition, "findings": self.findings}


class TestAuthority:
    """Only a simulated deployment; not available through CLI/configuration."""

    def require(self, binding: MergeBinding) -> None:
        assert binding.repository == "kanalia7355/Locus"


class FakePolicyObserver:
    def __init__(self, world: World) -> None:
        self.world = world

    def observe(self) -> dict[str, Any]:
        return observe_policy(API(self.world, "merge"), 5556060, 5555922)


def publish(root: Path, world: World) -> MergeBinding:
    return ReviewPublicationService(
        API(world, "review"),
        FakePolicyObserver(world),
        cast(Reviewer, FreshReviewer()),
        ReviewAuthority(root),
        PublicationJournal(root / "publication.db"),
    ).publish("TASK-002", 7, timeout=30, cancelled=lambda: False)


def test_fresh_review_publication_to_serialized_squash(tmp_path: Path) -> None:
    world = World()
    binding = publish(tmp_path, world)
    transport = GitHubBrokerTransport(API(world, "merge"), 5555922, authority=TestAuthority())
    broker = MergeBroker(BrokerJournal(tmp_path / "broker.db"), transport)
    assert broker.execute(binding) == M
    assert broker.reconcile(binding) == M and world.lock is None
    assert len([path for method, path in world.writes if method == "PUT"]) == 1


def test_default_authority_denies_before_any_remote_mutation(tmp_path: Path) -> None:
    world = World()
    policy = observe_policy(API(world, "merge"), 5556060, 5555922)
    binding = MergeBinding("kanalia7355/Locus", 7, H, B, policy["policy_hash"], "e" * 64, "f" * 64)
    remote = GitHubBrokerTransport(API(world, "merge"), 5555922)
    with pytest.raises(SafetyError, match="activation authority"):
        remote.acquire("1" * 32, binding)
    assert not world.writes


@pytest.mark.parametrize("defect", ["ci", "dismissed", "forged_check", "queued", "thread", "base"])
def test_changed_gate_never_merges_or_releases_lock(tmp_path: Path, defect: str) -> None:
    world = World()
    binding = publish(tmp_path, world)
    if defect == "ci":
        world.checks[0]["conclusion"] = "failure"
    elif defect == "dismissed":
        world.reviews[0]["state"] = "DISMISSED"
    elif defect == "forged_check":
        world.checks[-1]["app"]["id"] = 15368
    elif defect == "queued":
        world.queued = {"enabledAt": "synthetic"}
    elif defect == "thread":
        world.unresolved = True
    else:
        world.base = "0" * 40
    remote = GitHubBrokerTransport(API(world, "merge"), 5555922, authority=TestAuthority())
    with pytest.raises(SafetyError):
        MergeBroker(BrokerJournal(tmp_path / "broker.db"), remote).execute(binding)
    assert not world.merged and world.lock is not None
    assert not any(method == "PUT" for method, _ in world.writes)


def test_uncertain_check_publication_is_not_replayed(tmp_path: Path) -> None:
    world = World()
    world.lost = PREFIX + "/check-runs"
    with pytest.raises(TimeoutError):
        publish(tmp_path, world)
    world.lost = None
    with pytest.raises(SafetyError, match="reconciliation"):
        publish(tmp_path, world)
    assert len(world.writes) == 1 and not world.reviews


@pytest.mark.parametrize("lost_path", ["/check-runs", "/pulls/7/reviews"])
def test_uncertain_publication_cannot_replay_with_new_review_or_qa(
    tmp_path: Path, lost_path: str
) -> None:
    world = World()
    world.lost = PREFIX + lost_path
    with pytest.raises(TimeoutError):
        publish(tmp_path, world)
    writes = len(world.writes)
    world.lost = None
    reviewer, authority = FreshReviewer(), ReviewAuthority(tmp_path)
    reviewer.findings = [
        {
            "severity": "info",
            "file": "backend/example.py",
            "finding": "Different passing review wording",
            "evidence": "synthetic",
            "recommended_action": "none",
            "blocking": False,
        }
    ]
    authority.inputs.verification["elapsed_seconds"] = 42
    service = ReviewPublicationService(
        API(world, "review"),
        FakePolicyObserver(world),
        cast(Reviewer, reviewer),
        authority,
        PublicationJournal(tmp_path / "publication.db"),
    )
    with pytest.raises(SafetyError, match="reconciliation"):
        service.publish("TASK-002", 7, timeout=30, cancelled=lambda: False)
    assert reviewer.calls == 0 and len(world.writes) == writes


def test_failed_fresh_review_never_publishes(tmp_path: Path) -> None:
    world, reviewer = World(), FreshReviewer()
    reviewer.disposition = "fail"
    service = ReviewPublicationService(
        API(world, "review"),
        FakePolicyObserver(world),
        cast(Reviewer, reviewer),
        ReviewAuthority(tmp_path),
        PublicationJournal(tmp_path / "publication.db"),
    )
    with pytest.raises(SafetyError, match="did not pass"):
        service.publish("TASK-002", 7, timeout=30, cancelled=lambda: False)
    assert reviewer.calls == 1 and not world.writes


def test_missing_qa_or_cancellation_never_invokes_reviewer(tmp_path: Path) -> None:
    world, reviewer, authority = World(), FreshReviewer(), ReviewAuthority(tmp_path)
    authority.inputs = replace(authority.inputs, verification={"passed": True, "checks": []})
    service = ReviewPublicationService(
        API(world, "review"),
        FakePolicyObserver(world),
        cast(Reviewer, reviewer),
        authority,
        PublicationJournal(tmp_path / "publication.db"),
    )
    with pytest.raises(SafetyError, match="verification"):
        service.publish("TASK-002", 7, timeout=30, cancelled=lambda: False)
    with pytest.raises(SafetyError, match="cancelled"):
        service.publish("TASK-002", 7, timeout=30, cancelled=lambda: True)
    assert reviewer.calls == 0 and not world.writes
