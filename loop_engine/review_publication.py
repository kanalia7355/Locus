"""Fresh independent review and durable, exact-bound App publication.

No command accepts a review JSON/pass flag from an implementer. The authority
must load protected Controller evidence and revalidate source/QA provenance.
This service core stays inactive until the deployment authority is established.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from loop_engine.broker_policy_reader import PREFIX, REVIEW_CONTEXT
from loop_engine.broker_transport import BrokerAPI, exact_pull, review_marker
from loop_engine.merge_broker import BrokerJournal, MergeBinding
from loop_engine.models import Task
from loop_engine.reviewer import Reviewer, blocking
from loop_engine.security import SafetyError, fingerprint, reject_secrets


@dataclass(frozen=True)
class ReviewInputs:
    task: Task
    workspace: Path
    context: dict[str, Any]
    snapshot: dict[str, Any]
    verification: dict[str, Any]
    head: str


class ReviewAuthority(Protocol):
    def load(self, task_id: str) -> ReviewInputs: ...
    def require(self, inputs: ReviewInputs) -> None:
        """Check deployment, current source/specification and mandatory QA."""
        ...


class PolicyObserver(Protocol):
    def observe(self) -> dict[str, Any]:
        """Fresh fixed-operation response over the authenticated broker channel.

        The Review service must never receive a Merge App client/key. Production
        must authenticate the channel and bind request freshness; arbitrary JSON
        or a worker-supplied snapshot does not implement this interface.
        """
        ...


class PublicationJournal:
    def __init__(self, path: Path) -> None:
        self.journal = BrokerJournal(path)
        with self.journal.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS review_publications (
                binding TEXT PRIMARY KEY, document TEXT NOT NULL,
                phase TEXT NOT NULL, remote_id INTEGER
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS publication_jobs (
                source TEXT PRIMARY KEY, owner TEXT UNIQUE NOT NULL, binding TEXT UNIQUE
            )""")

    def reserve(self, pull: int, head: str, base: str) -> tuple[str, str]:
        # Model wording, elapsed QA timings and changed policy cannot evade a
        # previously reserved operation for this exact PR source/base pair.
        source = fingerprint(
            {"repository": "kanalia7355/Locus", "pull": pull, "head": head, "base": base}
        )
        owner = uuid4().hex
        with self.journal.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM publication_jobs WHERE source=?", (source,)).fetchone():
                raise SafetyError("Existing publication requires reconciliation, not replay")
            db.execute("INSERT INTO publication_jobs VALUES (?,?,NULL)", (source, owner))
        return source, owner

    def begin(self, source: str, owner: str, binding: MergeBinding, review: dict[str, Any]) -> None:
        reject_secrets(review)
        with self.journal.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            claimed = db.execute(
                "UPDATE publication_jobs SET binding=? "
                "WHERE source=? AND owner=? AND binding IS NULL",
                (binding.identity, source, owner),
            ).rowcount
            if claimed != 1:
                raise SafetyError("Publication reservation missing or changed")
            if db.execute(
                "SELECT 1 FROM review_publications WHERE binding=?", (binding.identity,)
            ).fetchone():
                raise SafetyError("Existing publication requires reconciliation, not replay")
            db.execute(
                "INSERT INTO review_publications VALUES (?,?,'prepared',NULL)",
                (
                    binding.identity,
                    json.dumps(review, sort_keys=True),
                ),
            )

    def move(self, binding: MergeBinding, old: str, new: str, remote_id: int | None = None) -> None:
        if remote_id is not None and (type(remote_id) is not int or remote_id <= 0):
            raise SafetyError("Invalid publication identity")
        with self.journal.connect() as db:
            count = db.execute(
                "UPDATE review_publications SET phase=?,remote_id=? WHERE binding=? AND phase=?",
                (new, remote_id, binding.identity, old),
            ).rowcount
            if count != 1:
                raise SafetyError("Publication intent already claimed or changed")


class ReviewPublicationService:
    def __init__(
        self,
        review_api: BrokerAPI,
        policy_observer: PolicyObserver,
        reviewer: Reviewer,
        authority: ReviewAuthority,
        journal: PublicationJournal,
    ) -> None:
        if review_api.role != "review":
            raise SafetyError("Review App identity required")
        self.api, self.policy_observer, self.reviewer = review_api, policy_observer, reviewer
        self.authority, self.journal = authority, journal

    def publish(
        self, task_id: str, pull: int, *, timeout: float, cancelled: Callable[[], bool]
    ) -> MergeBinding:
        deadline = time.monotonic() + timeout

        def active() -> None:
            if cancelled() or time.monotonic() >= deadline:
                raise SafetyError("Review publication cancelled or time-limited")

        active()
        inputs = self.authority.load(task_id)
        self.authority.require(inputs)
        checks = inputs.verification.get("checks", [])
        required = [check for check in checks if check.get("required") is True]
        if (
            inputs.task.id != task_id
            or inputs.verification.get("passed") is not True
            or not required
            or any(check.get("status") != "passed" for check in required)
        ):
            raise SafetyError("Current mandatory verification is not established")
        policy = self.policy_observer.observe()
        if policy["issues"]:
            raise SafetyError("Required protected policy is not established")
        active()
        source, owner = self.journal.reserve(pull, inputs.head, inputs.snapshot["base"])
        review = self.reviewer.evaluate(
            inputs.task,
            inputs.workspace,
            inputs.context,
            inputs.snapshot,
            inputs.verification,
            timeout=max(0, deadline - time.monotonic()),
            cancelled=cancelled,
        )
        if blocking(review):
            raise SafetyError("Fresh independent review did not pass")
        binding = MergeBinding(
            "kanalia7355/Locus",
            pull,
            inputs.head,
            inputs.snapshot["base"],
            policy["policy_hash"],
            fingerprint(review),
            fingerprint(inputs.verification),
        )

        def current() -> None:
            active()
            self.authority.require(inputs)
            observation = self.policy_observer.observe()
            if observation["issues"] or observation["policy_hash"] != binding.policy:
                raise SafetyError("Policy or base changed before review publication")
            exact_pull(self.api.call("GET", PREFIX + f"/pulls/{pull}"), binding)
            graph = self.api.pull_request_state(pull)
            if (
                graph.get("headRefOid") != binding.head
                or graph.get("baseRefOid") != binding.base
                or "autoMergeRequest" not in graph
                or graph["autoMergeRequest"] is not None
            ):
                raise SafetyError("Source/base changed or native auto-merge is queued")
            active()

        current()
        self.journal.begin(source, owner, binding, review)
        self.journal.move(binding, "prepared", "check_intent")
        check = self.api.call(
            "POST",
            PREFIX + "/check-runs",
            {
                "name": REVIEW_CONTEXT,
                "head_sha": binding.head,
                "external_id": binding.identity,
                "status": "completed",
                "conclusion": "success",
                "output": {"title": "Independent review passed", "summary": review_marker(binding)},
            },
        )
        if (
            type(check.get("id")) is not int
            or check["id"] <= 0
            or check.get("app", {}).get("id") != self.api.app_id
            or check.get("head_sha") != binding.head
            or check.get("external_id") != binding.identity
            or check.get("name") != REVIEW_CONTEXT
            or check.get("status") != "completed"
            or check.get("conclusion") != "success"
        ):
            raise SafetyError("Check publication uncertain; do not replay")
        self.journal.move(binding, "check_intent", "check_observed", check["id"])
        current()
        login = self.api.bot_login()
        active()
        self.journal.move(binding, "check_observed", "approval_intent")
        approval = self.api.call(
            "POST",
            PREFIX + f"/pulls/{pull}/reviews",
            {
                "event": "APPROVE",
                "commit_id": binding.head,
                "body": review_marker(binding),
            },
        )
        if (
            type(approval.get("id")) is not int
            or approval["id"] <= 0
            or approval.get("user", {}).get("type") != "Bot"
            or approval.get("user", {}).get("login") != login
            or approval.get("commit_id") != binding.head
            or approval.get("state") != "APPROVED"
            or approval.get("body") != review_marker(binding)
        ):
            raise SafetyError("Approval publication uncertain; do not replay")
        self.journal.move(binding, "approval_intent", "published", approval["id"])
        current()
        return binding
