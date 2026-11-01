"""Existing Controller delivery adapter: verified commit, fast-forward, ordinary Push.

Intent precedes every mutation. Reconciliation observes Git rather than replaying
an uncertain mutation. No PR, App, Broker, merge API or force Push is used.
"""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loop_engine.git_manager import GitManager
from loop_engine.models import Task
from loop_engine.security import SafetyError
from loop_engine.state_store import StateStore


def validate_policy(policy: dict[str, Any]) -> None:
    if (
        not policy["enabled"]
        or policy["auto_merge"] != "off"
        or policy["remote"] != "origin"
        or not re.fullmatch(r"loop/[A-Za-z0-9][A-Za-z0-9_-]{0,99}", policy["base"])
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", policy["repository"])
    ):
        raise SafetyError(
            "Local delivery requires an enabled origin, loop/* branch and no auto-merge"
        )


class LocalDelivery:
    def __init__(
        self, root: Path, state: StateStore, git: GitManager, policy: dict[str, Any]
    ) -> None:
        validate_policy(policy)
        self.root, self.state, self.git, self.policy = root, state, git, policy
        self.ref = "refs/heads/" + policy["base"]
        git.recoverable_commits = True

    def _remote_head(self, cancelled: Callable[[], bool]) -> str | None:
        repository = self.policy["repository"]
        urls = self.git._git(
            ["remote", "get-url", "--push", "--all", "origin"], cancelled=cancelled
        ).splitlines()
        fetch_urls = self.git._git(
            ["remote", "get-url", "--all", "origin"], cancelled=cancelled
        ).splitlines()
        approved = {
            f"https://github.com/{repository}.git",
            f"https://github.com/{repository}",
            f"git@github.com:{repository}.git",
        }
        if len(urls) != 1 or len(fetch_urls) != 1 or not set(urls + fetch_urls) <= approved:
            raise SafetyError("Push destination differs from the approved repository")
        output = self.git._git(["ls-remote", "--refs", "origin", self.ref], cancelled=cancelled)
        if not output:
            return None
        fields = output.split()
        if (
            len(fields) != 2
            or fields[1] != self.ref
            or not re.fullmatch(r"[a-f0-9]{40,64}", fields[0])
        ):
            raise SafetyError("Unexpected remote reference response")
        return fields[0]

    def check_baseline(self, *, cancelled: Callable[[], bool]) -> None:
        """Do not spend another model attempt on an unexpectedly changed branch."""
        self.git.operation_cancelled = cancelled
        self.git._safe_configuration()
        current = self.git._git(["rev-parse", self.ref], cancelled=cancelled)
        expected = self.state.metadata("local_published_head") or self.state.metadata(
            "local_initial_head"
        )
        remote = self._remote_head(cancelled)
        if (expected and current != expected) or remote not in {None, current}:
            raise SafetyError("Development baseline changed unexpectedly")
        if remote is None and self.state.metadata("local_published_head"):
            raise SafetyError("Published development branch was deleted")
        if not expected:
            self.state.set_metadata("local_initial_head", current)

    def deliver(
        self, task: Task, checkpoint: dict[str, Any], *, cancelled: Callable[[], bool]
    ) -> dict[str, Any]:
        self.git.operation_cancelled = cancelled
        if (
            cancelled()
            or not checkpoint.get("verified")
            or not checkpoint.get("verification", {}).get("passed")
        ):
            raise SafetyError("Delivery requires current verified evidence and an active budget")
        self.git._safe_configuration()
        workspace = Path(checkpoint["workspace"])
        intent = checkpoint.get("local_delivery_intent")
        if not intent:
            current = self.git._git(["rev-parse", self.ref], cancelled=cancelled)
            remote = self._remote_head(cancelled)
            if current != checkpoint["base"] or remote not in {None, current}:
                raise SafetyError("Integration/remote base moved unexpectedly")
            # An absent branch is valid only for its first publication, never after deletion.
            if remote is None and self.state.metadata("local_published_head"):
                raise SafetyError("Previously published remote branch disappeared")
            intent = {
                "ref": self.ref,
                "base": current,
                "remote_before": remote,
                "binding": checkpoint["binding"],
            }
            self.state.checkpoint(task.id, {**checkpoint, "local_delivery_intent": intent})
        if intent["ref"] != self.ref or intent["binding"] != checkpoint["binding"]:
            raise SafetyError("Delivery policy or source binding changed")
        committed = self.git.finalize(task, workspace, checkpoint["binding"])["head"]
        current = self.git._git(["rev-parse", self.ref], cancelled=cancelled)
        remote = self._remote_head(cancelled)
        if current not in {intent["base"], committed} or remote not in {
            intent["remote_before"],
            committed,
        }:
            raise SafetyError("Unexpected integration or remote history; never force Push")
        if current != committed:
            self.git._git(["merge-base", "--is-ancestor", current, committed], cancelled=cancelled)
            worktrees = self.git._git(["worktree", "list", "--porcelain"], cancelled=cancelled)
            if "branch " + self.ref in worktrees.splitlines():
                # Only the clean primary checkout may be updated; other user worktrees are retained.
                if self.git._git(
                    ["symbolic-ref", "HEAD"], cancelled=cancelled
                ) != self.ref or self.git._git(["status", "--porcelain"], cancelled=cancelled):
                    raise SafetyError("Integration checkout is occupied or dirty")
                self.git._git(["merge", "--ff-only", committed], cancelled=cancelled)
            else:
                self.git._git(["update-ref", self.ref, committed, current], cancelled=cancelled)
        self.state.checkpoint(
            task.id, {**self.state.get_checkpoint(task.id), "integrated_head": committed}
        )
        if remote != committed:
            # Recheck immediately before ordinary Push. A concurrent divergent update
            # is rejected by Git's server-side fast-forward rule; never force/lease.
            if self._remote_head(cancelled) != intent["remote_before"]:
                raise SafetyError("Remote changed before Push")
            self.git._git(
                [
                    "push",
                    "--porcelain",
                    "--no-mirror",
                    "--no-follow-tags",
                    "--recurse-submodules=no",
                    "origin",
                    f"{committed}:{self.ref}",
                ],
                timeout=30,
                cancelled=cancelled,
            )
        if self._remote_head(cancelled) != committed:
            raise SafetyError("Push outcome not confirmed")
        self.state.checkpoint(
            task.id, {**self.state.get_checkpoint(task.id), "pushed_head": committed}
        )
        self.state.set_metadata("local_published_head", committed)
        return {"complete": True, "integrated_head": committed, "pushed_head": committed}
