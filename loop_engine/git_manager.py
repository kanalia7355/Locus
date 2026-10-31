"""Scoped task worktrees. No reset/clean/force/hook-bypass/default-branch writes."""

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loop_engine.models import Task
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError, allowed, fingerprint, reject_secrets, reparse, within
from loop_engine.state_store import StateStore


class GitManager:
    def __init__(self, root: Path, state: StateStore, base: str = "main") -> None:
        self.root = root.resolve()
        self.state = state
        self.base = base
        self.process = ProcessRunner()

    def _git(
        self,
        args: list[str],
        cwd: Path | None = None,
        *,
        timeout: float = 30,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> str:
        if cancelled() or timeout <= 0:
            raise SafetyError("Git operation cancelled")
        result = self.process.run(
            ["git", *args], cwd or self.root, timeout=timeout, cancelled=cancelled
        )
        if result.outcome != "exit" or result.returncode != 0:
            raise SafetyError("Git operation failed; no unsafe fallback")
        return result.stdout.strip("\n")

    def _safe_configuration(
        self,
        workspace: Path | None = None,
        *,
        deadline: float | None = None,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> None:
        def command(args: list[str]) -> str:
            return self._git(
                args,
                workspace,
                timeout=30 if deadline is None else min(30, deadline - time.time()),
                cancelled=cancelled,
            )

        data = command(["config", "--null", "--list", "--show-origin"])
        reject_secrets(data)
        lower = data.lower()
        if any(
            key in lower
            for key in (
                "core.fsmonitor\n",
                "core.hookspath\n",
                "filter.",
                "core.sshcommand\n",
                "core.gitproxy\n",
                ".pushinsteadof\n",
            )
        ):
            raise SafetyError(
                "Custom Git executable configuration requires separate security assessment"
            )
        hooks = Path(command(["rev-parse", "--git-path", "hooks"]))
        if not hooks.is_absolute():
            hooks = self.root / hooks
        if hooks.exists() and any(
            path.is_file() and not path.name.endswith(".sample") for path in hooks.iterdir()
        ):
            raise SafetyError(
                "Installed Git hooks require explicit assessment; hooks are not bypassed"
            )

    @staticmethod
    def branch(task: Task) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", task.title.lower()).strip("-")[:45] or "task"
        return f"loop/{task.id}-{slug}"

    def prepare(self, task: Task) -> Path:
        self._safe_configuration()
        base_sha = self._git(["rev-parse", "--verify", self.base + "^{commit}"])
        if not re.fullmatch(r"[a-f0-9]{40,64}", base_sha):
            raise SafetyError("A committed approved base is required")
        for dependency in task.dependencies:
            checkpoint = self.state.get_checkpoint(dependency)
            if not checkpoint.get("merge_sha"):
                raise SafetyError(
                    "Dependency implementation is not integrated into the approved base"
                )
            self._git(["merge-base", "--is-ancestor", checkpoint["merge_sha"], base_sha])
        branch = self.branch(task)
        directory = within(self.root, ".loop/runtime/worktrees/" + task.id)
        checkpoint = self.state.get_checkpoint(task.id)
        if directory.exists():
            if (
                reparse(directory)
                or checkpoint.get("branch") != branch
                or checkpoint.get("base") != base_sha
            ):
                raise SafetyError(
                    "Existing worktree identity/base changed; recovery assessment required"
                )
            if (
                Path(self._git(["rev-parse", "--show-toplevel"], directory)).resolve()
                != directory.resolve()
            ):
                raise SafetyError("Worktree path identity mismatch")
            if self._git(["symbolic-ref", "--short", "HEAD"], directory) != branch:
                raise SafetyError("Worktree branch identity mismatch")
        else:
            directory.parent.mkdir(parents=True, exist_ok=True)
            self._git(["worktree", "add", "-b", branch, str(directory), base_sha])
            self.state.checkpoint(
                task.id,
                {**checkpoint, "branch": branch, "base": base_sha, "workspace": str(directory)},
            )
        return directory

    def snapshot(self, task: Task, workspace: Path) -> dict[str, Any]:
        self._git(["diff", "--cached", "--quiet", "--exit-code"], workspace)
        checkpoint = self.state.get_checkpoint(task.id)
        if not checkpoint.get("base"):
            raise SafetyError("No trusted worktree baseline")
        tracked = self._git(["diff", "--name-only", "-z", checkpoint["base"]], workspace)
        untracked = self._git(["ls-files", "--others", "--exclude-standard", "-z"], workspace)
        paths = sorted(set(path for path in (tracked + untracked).split("\0") if path))
        contents: dict[str, str] = {}
        for name in paths:
            if not allowed(name, task.allowed_paths):
                raise SafetyError("Actual Git change outside task scope")
            path = within(workspace, name)
            if path.is_file():
                if path.stat().st_size > 1_000_000:
                    raise SafetyError("Changed file exceeds audit boundary")
                data = path.read_bytes()
                if b"\0" in data:
                    raise SafetyError("Binary changes require separate assessment")
                value = data.decode("utf-8")
                reject_secrets(value)
                contents[name] = fingerprint(
                    {"content": value, "mode": path.stat().st_mode & 0o777}
                )
            else:
                contents[name] = "deleted"
        return {
            "base": checkpoint["base"],
            "branch": checkpoint["branch"],
            "paths": paths,
            "diff_hash": fingerprint(contents),
        }

    def review_diff(self, workspace: Path, base: str) -> str:
        data = self._git(["diff", "--no-ext-diff", "--no-textconv", base, "--"], workspace)
        reject_secrets(data)
        return data

    def finalize(self, task: Task, workspace: Path, binding: str) -> dict[str, Any]:
        self._safe_configuration(workspace)
        checkpoint = self.state.get_checkpoint(task.id)
        snapshot = self.snapshot(task, workspace)
        if checkpoint.get("committed_head"):
            head = self._git(["rev-parse", "HEAD"], workspace)
            if head != checkpoint["committed_head"] or checkpoint.get("snapshot") != snapshot:
                raise SafetyError("Commit identity changed; refusing duplicate commit")
            return {"head": head, "branch": checkpoint["branch"]}
        if checkpoint.get("commit_intent"):
            # A prior commit may have succeeded: reconcile rather than blindly commit again.
            raise SafetyError("Unsettled commit intent requires recovery assessment")
        if checkpoint.get("snapshot") != snapshot or checkpoint.get("binding") != binding:
            raise SafetyError("Verified source changed before commit")
        self.state.checkpoint(task.id, {**checkpoint, "commit_intent": snapshot["diff_hash"]})
        for name in snapshot["paths"]:
            self._git(["add", "--", name], workspace)
        staged = self._git(["diff", "--cached", "--name-only", "-z", checkpoint["base"]], workspace)
        if sorted(path for path in staged.split("\0") if path) != snapshot["paths"]:
            raise SafetyError("Prospective index contains unverified paths")
        self._git(["diff", "--quiet", "--exit-code"], workspace)
        prospective_tree = self._git(["write-tree"], workspace)
        if snapshot["paths"]:
            self._git(["commit", "-m", f"feat: implement {task.id}"], workspace)
        head = self._git(["rev-parse", "HEAD"], workspace)
        if self._git(["rev-parse", "HEAD^{tree}"], workspace) != prospective_tree:
            raise SafetyError("Committed tree differs from the verified prospective index")
        self.state.checkpoint(
            task.id, {**self.state.get_checkpoint(task.id), "committed_head": head}
        )
        return {"head": head, "branch": checkpoint["branch"]}
