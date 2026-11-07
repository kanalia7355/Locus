"""Exact-binding remote gate/transport. No Controller or live CLI activation.

The service authority is a trusted deployment interface, never model-supplied
evidence. Until isolated service packaging and live writer proofs exist, the
default authority denies even lock creation. This is not an activation switch.
"""

import re
from typing import Any, Protocol

from loop_engine.broker_policy_reader import CI_CONTEXTS, PREFIX, REVIEW_CONTEXT, observe_policy
from loop_engine.github_mutex import GitHubMutex
from loop_engine.merge_broker import MergeBinding
from loop_engine.security import SafetyError


class BrokerAPI(Protocol):
    role: str
    app_id: int

    def call(self, method: str, path: str, document: dict[str, Any] | None = None) -> Any: ...
    def pull_request_state(self, pull: int) -> dict[str, Any]: ...
    def bot_login(self) -> str: ...


class ServiceAuthority(Protocol):
    def require(self, binding: MergeBinding) -> None:
        """Revalidate pinned deployment, live proofs, scope, risk and approvals."""
        ...


class InactiveAuthority:
    def require(self, binding: MergeBinding) -> None:
        raise SafetyError("Isolated service and activation authority are not established")


def review_marker(binding: MergeBinding) -> str:
    return "Locus independently reviewed binding: " + binding.identity


def exact_pull(detail: dict[str, Any], binding: MergeBinding, *, merged: bool = False) -> None:
    if (
        binding.repository != "kanalia7355/Locus"
        or detail.get("number") != binding.pull
        or detail.get("draft") is not False
        or detail.get("state") != ("closed" if merged else "open")
        or detail.get("user", {}).get("login") != "kanalia7355"
        or detail.get("head", {}).get("sha") != binding.head
        or detail.get("head", {}).get("repo", {}).get("full_name") != binding.repository
        or detail.get("head", {}).get("repo", {}).get("id") != 1440108668
        or detail.get("base", {}).get("ref") != "main"
        or detail.get("base", {}).get("repo", {}).get("full_name") != binding.repository
        or detail.get("base", {}).get("repo", {}).get("id") != 1440108668
        or (not merged and detail.get("base", {}).get("sha") != binding.base)
    ):
        raise SafetyError("Pull request source/base/author identity changed")


def require_review_check(runs: list[dict[str, Any]], binding: MergeBinding, app_id: int) -> str:
    candidates = [
        run
        for run in runs
        if run.get("name") == REVIEW_CONTEXT and run.get("app", {}).get("id") == app_id
    ]
    if not candidates or any(type(run.get("id")) is not int for run in candidates):
        raise SafetyError("Trusted independent review check unavailable")
    latest = max(candidates, key=lambda run: run["id"])
    slug = latest.get("app", {}).get("slug", "")
    if (
        latest.get("head_sha") != binding.head
        or latest.get("external_id") != binding.identity
        or latest.get("status") != "completed"
        or latest.get("conclusion") != "success"
        or not isinstance(slug, str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", slug)
        or slug == "github-actions"
    ):
        raise SafetyError("Independent review check is stale, failed or unbound")
    return slug + "[bot]"


class GitHubBrokerTransport:
    def __init__(
        self, api: BrokerAPI, review_app_id: int, *, authority: ServiceAuthority | None = None
    ) -> None:
        if api.role != "merge" or type(review_app_id) is not int or review_app_id <= 0:
            raise SafetyError("Distinct approved App roles required")
        if review_app_id == api.app_id:
            raise SafetyError("Distinct approved App roles required")
        self.api, self.review_app_id = api, review_app_id
        self.authority = authority or InactiveAuthority()
        self.mutex = GitHubMutex(api)
        self.held: tuple[str, MergeBinding] | None = None

    def acquire(self, owner: str, binding: MergeBinding) -> None:
        self.authority.require(binding)
        self.mutex.acquire(owner, binding)
        self.held = owner, binding

    def owns(self, owner: str, binding: MergeBinding) -> bool:
        return self.mutex.owns(owner, binding)

    def validate(self, binding: MergeBinding) -> None:
        self.authority.require(binding)
        if self.held is None or self.held[1] != binding or not self.owns(*self.held):
            raise SafetyError("Owned global mutex required for gate inspection")
        observation = observe_policy(self.api, self.api.app_id, self.review_app_id)
        if (
            observation["issues"]
            or observation["policy_hash"] != binding.policy
            or observation["facts"]["base"] != binding.base
        ):
            raise SafetyError("Protected policy or exact base changed")
        detail = self.api.call("GET", PREFIX + f"/pulls/{binding.pull}")
        exact_pull(detail, binding)
        if detail.get("mergeable") is not True or detail.get("mergeable_state") != "clean":
            raise SafetyError("Pull request is not conclusively mergeable")
        checks = self.api.call("GET", PREFIX + f"/commits/{binding.head}/check-runs?per_page=100")
        runs = checks.get("check_runs")
        if (
            not isinstance(runs, list)
            or len(runs) >= 100
            or type(checks.get("total_count")) is not int
            or checks["total_count"] != len(runs)
        ):
            raise SafetyError("Complete check-run inventory required")
        for context in CI_CONTEXTS:
            relevant = [run for run in runs if run.get("name") == context]
            if not relevant or any(
                run.get("head_sha") != binding.head
                or run.get("app", {}).get("id") != 15368
                or run.get("status") != "completed"
                or run.get("conclusion") != "success"
                for run in relevant
            ):
                raise SafetyError("Required CI is missing, pending, failed or untrusted")
        login = require_review_check(runs, binding, self.review_app_id)
        reviews = self.api.call("GET", PREFIX + f"/pulls/{binding.pull}/reviews?per_page=100")
        if not isinstance(reviews, list) or len(reviews) >= 100:
            raise SafetyError("Complete approving-review inventory required")
        own = [review for review in reviews if review.get("user", {}).get("login") == login]
        if not own or any(type(review.get("id")) is not int for review in own):
            raise SafetyError("Independent App approval unavailable")
        latest = max(own, key=lambda review: review["id"])
        if (
            latest.get("state") != "APPROVED"
            or latest.get("commit_id") != binding.head
            or latest.get("user", {}).get("type") != "Bot"
            or latest.get("body") != review_marker(binding)
        ):
            raise SafetyError("Independent App approval is stale, dismissed or unbound")
        graph = self.api.pull_request_state(binding.pull)
        threads = graph.get("reviewThreads", {})
        nodes = threads.get("nodes")
        if (
            graph.get("headRefOid") != binding.head
            or graph.get("baseRefOid") != binding.base
            or "autoMergeRequest" not in graph
            or graph["autoMergeRequest"] is not None
            or graph.get("reviewDecision") != "APPROVED"
            or threads.get("pageInfo", {}).get("hasNextPage") is not False
            or not isinstance(nodes, list)
            or threads.get("totalCount") != len(nodes)
            or any(node.get("isResolved") is not True for node in nodes)
        ):
            raise SafetyError("Review/conversation/queued-merge state is not safe")
        # Policy and PR reads can be slow: close head/base/policy races before PUT.
        after = observe_policy(self.api, self.api.app_id, self.review_app_id)
        if after["issues"] or after["policy_hash"] != binding.policy:
            raise SafetyError("Policy changed during merge preflight")
        exact_pull(self.api.call("GET", PREFIX + f"/pulls/{binding.pull}"), binding)
        self.authority.require(binding)

    def merge(self, binding: MergeBinding) -> str:
        self.validate(binding)
        detail = self.api.call("GET", PREFIX + f"/pulls/{binding.pull}")
        exact_pull(detail, binding)
        title = detail.get("title", "")
        if not isinstance(title, str) or not re.fullmatch(
            r"(?:feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
            r"(?:\([A-Za-z0-9_.-]+\))?!?: [^\r\n]{1,200}",
            title,
        ):
            raise SafetyError("Conventional squash title required")
        result = self.api.call(
            "PUT",
            PREFIX + f"/pulls/{binding.pull}/merge",
            {
                "sha": binding.head,
                "merge_method": "squash",
                "commit_title": title,
            },
        )
        sha = result.get("sha", "")
        if result.get("merged") is not True or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise SafetyError("Merge outcome uncertain; retain global lock")
        return str(sha)

    def observed_merge(self, binding: MergeBinding) -> str | None:
        detail = self.api.call("GET", PREFIX + f"/pulls/{binding.pull}")
        if detail.get("merged") is not True:
            return None
        exact_pull(detail, binding, merged=True)
        actor = detail.get("merged_by", {})
        sha = detail.get("merge_commit_sha", "")
        if actor.get("type") != "Bot" or actor.get("login") != self.api.bot_login():
            raise SafetyError("Merge actor unavailable")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise SafetyError("Merge commit unavailable")
        commit = self.api.call("GET", PREFIX + f"/commits/{sha}")
        if commit.get("sha") != sha or [
            parent.get("sha") for parent in commit.get("parents", [])
        ] != [binding.base]:
            raise SafetyError("Exact-base squash ancestry or actor not proven")
        main = self.api.call("GET", PREFIX + "/branches/main")
        if main.get("commit", {}).get("sha") != sha:
            raise SafetyError("Merged result is not the exclusively held main head")
        self.authority.require(binding)
        return sha

    def release(self, owner: str, binding: MergeBinding) -> None:
        if self.observed_merge(binding) is None:
            raise SafetyError("Definitive merge observation required before releasing")
        self.mutex.release(owner, binding)
        self.held = None
