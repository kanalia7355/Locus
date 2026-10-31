"""Outer loop runs inside the existing Controller lock, budget and sandbox policy."""

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loop_engine.approval import ApprovalQueue
from loop_engine.completion_gate import reasons
from loop_engine.gap_analyzer import analyze
from loop_engine.git_manager import GitManager
from loop_engine.improvement_planner import ImprovementPlanner
from loop_engine.planning import source_snapshot
from loop_engine.progress_evaluator import evaluate
from loop_engine.security import SafetyError, fingerprint, reject_secrets, within
from loop_engine.state_store import StateStore


class MainSnapshot:
    def __init__(self, root: Path, git: GitManager, repository: str, branch: str = "main") -> None:
        self.root, self.git, self.repository, self.branch = root, git, repository, branch
        self.deadline = 0.0
        self.cancelled: Callable[[], bool] = lambda: True

    def configure(self, deadline: float, cancelled: Callable[[], bool]) -> None:
        self.deadline, self.cancelled = deadline, cancelled

    def _git(self, args: list[str], cwd: Path | None = None) -> str:
        return self.git._git(
            args, cwd, timeout=min(30, self.deadline - time.time()), cancelled=self.cancelled
        )

    def current_head(self) -> str:
        self._git(["rev-parse", "--is-inside-work-tree"])
        self.git._safe_configuration(deadline=self.deadline, cancelled=self.cancelled)
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository)
            or self.branch != "main"
        ):
            raise SafetyError("Development reevaluation requires the approved repository main")
        remote = self._git(["remote", "get-url", "origin"])
        if remote not in {
            f"https://github.com/{self.repository}.git",
            f"https://github.com/{self.repository}",
            f"git@github.com:{self.repository}.git",
        }:
            raise SafetyError("Evaluation remote identity mismatch")
        self._git(["fetch", "--no-tags", "origin", "main:refs/remotes/origin/main"])
        return self._git(["rev-parse", "refs/remotes/origin/main^{commit}"])

    def stable(self, workspace: Path, head: str) -> bool:
        return self._git(["rev-parse", "HEAD"], workspace) == head and not self._git(
            ["status", "--porcelain", "--untracked-files=all"], workspace
        )

    def refresh(self, expected_merge: str | None) -> tuple[Path, dict[str, Any]]:
        head = self.current_head()
        if not re.fullmatch(r"[a-f0-9]{40,64}", head):
            raise SafetyError("Invalid main identity")
        if expected_merge:
            if not re.fullmatch(r"[a-f0-9]{40,64}", expected_merge):
                raise SafetyError("Invalid merged commit identity")
            self._git(["merge-base", "--is-ancestor", expected_merge, head])
        workspace = within(self.root, ".loop/runtime/evaluations/" + head)
        if not workspace.exists():
            workspace.parent.mkdir(parents=True, exist_ok=True)
            self._git(["worktree", "add", "--detach", str(workspace), head])
        if not self.stable(workspace, head):
            raise SafetyError("Evaluation worktree changed")
        names = self._git(["ls-files", "-z"], workspace).split("\0")
        files: dict[str, str] = {}
        used = 0
        for name in names:
            if not name or name.startswith((".git", ".loop", ".agents", ".codex")):
                continue
            path = within(workspace, name)
            if not path.is_file() or path.stat().st_size > 64000:
                continue
            try:
                data = path.read_text(encoding="utf-8")
            except UnicodeError:
                continue
            reject_secrets(data)
            used += len(data.encode("utf-8"))
            if used > 500000 or len(files) >= 100:
                break
            files[name] = data
        return workspace, {
            "head": head,
            "files": files,
            "inventory_truncated": len(files) < len([name for name in names if name]),
        }


class DevelopmentLoop:
    def __init__(
        self,
        root: Path,
        state: StateStore,
        snapshots: Any,
        evaluator: Any,
        verifier: Any,
        planner: ImprovementPlanner,
    ) -> None:
        self.root, self.state, self.snapshots = root, state, snapshots
        self.evaluator, self.verifier, self.planner = evaluator, verifier, planner

    def cycle(
        self, *, deadline: float, cancelled: Callable[[], bool], expected_merge: str | None = None
    ) -> str:
        state = self.state
        source = source_snapshot(self.root)
        binding = fingerprint(source)
        if binding != state.metadata("spec_hash"):
            raise SafetyError("Goal/design/policy changed; human reapproval required")
        state.set_metadata("development_status", {"status": "evaluating"})
        config = source["policy"]["development"]
        budget = state.metadata("run_budget", {})
        if not budget.get("id"):
            raise SafetyError("Project evaluation requires the owning Controller budget")
        usage = state.metadata("development_budget", {})
        if usage.get("run") != budget.get("id"):
            usage = {"run": budget.get("id"), "cycles": 0}
        if usage["cycles"] >= config["max_cycles_per_run"]:
            return "evaluation_limit"

        def remaining() -> float:
            if cancelled() or time.time() >= deadline:
                raise SafetyError("Project evaluation time limit reached")
            return float(min(deadline - time.time(), config["evaluation_timeout_minutes"] * 60))

        remaining()
        self.snapshots.configure(deadline, cancelled)
        workspace, snapshot = self.snapshots.refresh(expected_merge)
        remaining()
        usage["cycles"] += 1
        state.set_metadata("development_budget", usage)
        local_deadline = time.monotonic() + remaining()

        def phase_cancelled() -> bool:
            return cancelled() or time.monotonic() >= local_deadline

        report = self.evaluator.assess(
            source, snapshot, workspace, timeout=remaining(), cancelled=phase_cancelled
        )
        if phase_cancelled():
            raise SafetyError("Project evaluation phase expired")
        gaps = analyze(report, source, snapshot)
        remaining()
        verification = self.verifier.run(
            self.planner.profile,
            workspace,
            self.root,
            timeout=max(0, min(remaining(), local_deadline - time.monotonic())),
            cancelled=phase_cancelled,
        )
        verification = {**verification, "head": snapshot["head"], "spec_hash": binding}
        if phase_cancelled():
            raise SafetyError("Project verification phase expired")
        remaining()
        if self.snapshots.current_head() != snapshot["head"] or not self.snapshots.stable(
            workspace, snapshot["head"]
        ):
            return "main_changed"
        failures = [
            task.id + ":" + (task.last_error or "")
            for task in state.tasks()
            if task.status in {"blocked", "failed"}
        ]
        progress = evaluate(
            state.metadata("development_progress", {}),
            report,
            gaps,
            failures,
            config["stagnation_limit"],
            verification=verification,
        )
        receipt = {"report": report, "verification": verification, "progress": progress}
        self.planner.apply(
            [] if progress["halt"] else gaps,
            head=snapshot["head"],
            spec_hash=binding,
            receipt=receipt,
        )
        report, verification = receipt["report"], receipt["verification"]
        remaining()
        if fingerprint(source_snapshot(self.root)) != binding:
            raise SafetyError("Source Goal changed during evaluation")
        latest_head = self.snapshots.current_head()
        if latest_head != snapshot["head"]:
            return "main_changed"
        blockers = reasons(
            report,
            verification,
            state.tasks(),
            ApprovalQueue(state).decisions(),
            current_head=latest_head,
            spec_hash=binding,
        )
        if not blockers:
            outcome = "complete"
        elif receipt["progress"]["halt"]:
            outcome = "stalled"
        else:
            outcome = "improvements_or_decisions_pending"
        state.set_metadata(
            "development_status",
            {"status": outcome, "head": snapshot["head"], "blockers": blockers},
        )
        return outcome
