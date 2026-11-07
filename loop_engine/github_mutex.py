"""GitHub-wide compare-and-create mutex, without expiry or lock stealing.

This primitive alone does NOT authorize merges. Its refs must be protected by
the independently proved lock writer ruleset, and all main writers must also
be restricted. No Controller or live merge command wires this primitive yet.
"""

import json
import re
from dataclasses import asdict
from typing import Any, Protocol

from loop_engine.broker_policy import LOCK_BRANCH
from loop_engine.github_app import GitHubMissing
from loop_engine.merge_broker import MergeBinding
from loop_engine.security import SafetyError


class RepositoryAPI(Protocol):
    def call(self, method: str, path: str, document: dict[str, Any] | None = None) -> Any: ...


class GitHubMutex:
    def __init__(self, api: RepositoryAPI) -> None:
        self.api = api
        self.prefix = "/repos/kanalia7355/Locus/git"
        self.reference = "refs/heads/" + LOCK_BRANCH

    @staticmethod
    def _marker(owner: str, binding: MergeBinding) -> str:
        if not re.fullmatch(r"[0-9a-f]{32}", owner) or binding.repository != "kanalia7355/Locus":
            raise SafetyError("Invalid global lock identity")
        return json.dumps(
            {"protocol": "locus-broker-v1", "owner": owner, "binding": asdict(binding)},
            sort_keys=True,
            separators=(",", ":"),
        )

    def acquire(self, owner: str, binding: MergeBinding) -> None:
        marker = self._marker(owner, binding)
        # An orphan commit is harmless. Only GitHub's atomic reference creation
        # admits a holder; pre-reading a missing ref is never used as a lock.
        base = self.api.call("GET", self.prefix + "/commits/" + binding.base)
        commit = self.api.call(
            "POST",
            self.prefix + "/commits",
            {"message": marker, "tree": base["tree"]["sha"], "parents": [binding.base]},
        )
        sha = commit["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise SafetyError("Invalid lock commit")
        self.api.call("POST", self.prefix + "/refs", {"ref": self.reference, "sha": sha})
        if not self.owns(owner, binding):
            raise SafetyError("Global lock creation not observed; do not retry")

    def owns(self, owner: str, binding: MergeBinding) -> bool:
        marker = self._marker(owner, binding)
        try:
            reference = self.api.call("GET", self.prefix + "/ref/heads/" + LOCK_BRANCH)
        except GitHubMissing:
            return False
        if (
            reference.get("ref") != self.reference
            or reference.get("object", {}).get("type") != "commit"
        ):
            raise SafetyError("Unexpected global lock ref identity")
        sha = reference["object"]["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise SafetyError("Invalid lock ref SHA")
        commit = self.api.call("GET", self.prefix + "/commits/" + sha)
        return commit.get("message") == marker and [
            parent.get("sha") for parent in commit.get("parents", [])
        ] == [binding.base]

    def release(self, owner: str, binding: MergeBinding) -> None:
        # Caller must already have conclusively reconciled the remote merge.
        # There is no force-update, stale timestamp, PID or expiry escape hatch.
        if not self.owns(owner, binding):
            raise SafetyError("Global mutex is not owned")
        self.api.call("DELETE", self.prefix + "/refs/heads/" + LOCK_BRANCH)
