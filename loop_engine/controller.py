"""Serial deterministic loop; no success is inferred from the model's status string."""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from loop_engine.approval import ApprovalQueue
from loop_engine.config import load
from loop_engine.locking import ProjectLock
from loop_engine.models import Task, check_result
from loop_engine.planning import source_snapshot
from loop_engine.reporting import write_report
from loop_engine.reviewer import blocking, review_binding
from loop_engine.scheduler import Scheduler
from loop_engine.security import SafetyError, allowed, fingerprint, protected
from loop_engine.state_store import StateStore


class Worker(Protocol):
    def execute(
        self,
        task: Task,
        context: dict[str, Any],
        workspace: Path,
        *,
        timeout: float,
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]: ...


class Workspaces(Protocol):
    def prepare(self, task: Task) -> Path: ...
    def snapshot(self, task: Task, workspace: Path) -> dict[str, Any]: ...
    def finalize(self, task: Task, workspace: Path, binding: str) -> dict[str, Any]: ...


class Controller:
    def __init__(
        self,
        root: Path,
        state: StateStore,
        worker: Worker,
        verifier: Any,
        reviewer: Any,
        workspaces: Workspaces,
        publisher: Any = None,
        development: Any = None,
    ) -> None:
        self.root = root
        self.state = state
        self.worker = worker
        self.verifier = verifier
        self.reviewer = reviewer
        self.workspaces = workspaces
        self.publisher = publisher
        self.development = development
        self.queue = ApprovalQueue(state)
        self.config = load(root / ".loop/config.yaml")
        self.deadline = 0.0

    def cancelled(self) -> bool:
        return self.state.metadata("control") != "running" or time.time() >= self.deadline

    def _transition(self, task_id: str, target: str, error: str | None = None) -> None:
        task = self.state.task(task_id)
        if task.status == target:
            return
        self.state.transition(task_id, task.status, target, error, version=task.version)

    def _context(self) -> dict[str, Any]:
        if self.state.metadata("policy_migration_pending"):
            raise SafetyError("Policy migration is unsettled; reconcile before model execution")
        snapshot = source_snapshot(self.root)
        if fingerprint(snapshot) != self.state.metadata("spec_hash"):
            raise SafetyError(
                "Source specification or policy changed; reapproval/replanning required"
            )
        return snapshot

    def run(self, *, resume: bool = False, duration_seconds: float | None = None) -> str:
        with ProjectLock(self.root / ".loop/runtime/controller.lock"):
            context = self._context()
            with self.state.connect() as db:
                unsettled = db.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status IN ('running','verifying','reviewing')"
                ).fetchone()[0]
                unsettled += db.execute(
                    "SELECT COUNT(*) FROM executions WHERE status='running'"
                ).fetchone()[0]
            if unsettled or self.state.metadata("orphan_uncertainty", False):
                self.state.event("recovery.required", reason="executor_lifetime_unsettled")
                return "recovery_required"
            budget = self.state.metadata("run_budget") if resume else None
            maximum = self.config["loop"]["max_runtime_minutes"] * 60
            if duration_seconds is not None and not 0 < duration_seconds <= maximum:
                raise SafetyError("Requested window exceeds the configured runtime cap")
            if not budget:
                now = time.time()
                budget = {
                    "id": uuid4().hex,
                    "started": now,
                    "deadline": now + (duration_seconds or maximum),
                    "tasks": [],
                }
                self.state.set_metadata("run_budget", budget)
            elif duration_seconds is not None:
                # A human requests a new bounded window, retaining task/run counters.
                budget["deadline"] = time.time() + duration_seconds
                self.state.set_metadata("run_budget", budget)
            self.deadline = budget["deadline"]
            session_started = time.monotonic()
            self.state.set_metadata("control", "running")
            try:
                if not self.cancelled():
                    self._resume_deliveries()
                if self.config["github"]["delivery"] == "local_commit_push" and any(
                    task.status != "completed"
                    and self.state.get_checkpoint(task.id).get("local_delivery_intent")
                    for task in self.state.tasks()
                ):
                    return "local_delivery_held"
                if self.development and not self.cancelled():
                    if not self._delivery_baseline():
                        return "local_delivery_held"
                    self._assess_project()
                while not self.cancelled():
                    if (
                        self.development
                        and self.state.metadata("development_status", {}).get("status")
                        == "main_changed"
                    ):
                        self._assess_project()
                        continue
                    if self.development and self.state.metadata("development_status", {}).get(
                        "status"
                    ) in {"complete", "stalled", "evaluation_limit"}:
                        return "goal_" + str(self.state.metadata("development_status")["status"])
                    self._context()
                    if not self._delivery_baseline():
                        return "local_delivery_held"
                    task = Scheduler(self.state).next_ready_task()
                    if not task:
                        pending_ci = any(
                            task.status == "awaiting_approval"
                            and not self.queue.pending_for(task.id)
                            and self.state.get_pr(task.id).get("ci", {}).get("status") == "pending"
                            for task in self.state.tasks()
                        )
                        if pending_ci:
                            time.sleep(min(2, max(0, self.deadline - time.time())))
                            self._resume_deliveries()
                            continue
                        break
                    if task.id not in budget["tasks"]:
                        if len(budget["tasks"]) >= self.config["loop"]["max_tasks_per_run"]:
                            break
                        budget["tasks"].append(task.id)
                        self.state.set_metadata("run_budget", budget)
                    self._execute(task, context, budget["id"])
                    write_report(self.state, self.root)
                return "idle" if not self.cancelled() else "paused_or_limited"
            finally:
                budget["consumed_seconds"] = (
                    budget.get("consumed_seconds", 0) + time.monotonic() - session_started
                )
                self.state.set_metadata("run_budget", budget)
                if self.state.metadata("control") == "running":
                    self.state.set_metadata("control", "stopped")
                write_report(self.state, self.root)

    def _delivery_baseline(self) -> bool:
        check = getattr(self.publisher, "check_baseline", None)
        if not check:
            return True
        try:
            check(cancelled=self.cancelled)
            return True
        except (ValueError, OSError):
            self.state.event("local_delivery.baseline_held")
            self.state.set_metadata("control", "stopped")
            return False

    def _assess_project(self, merge_sha: str | None = None) -> None:
        try:
            outcome = self.development.cycle(
                deadline=self.deadline, cancelled=self.cancelled, expected_merge=merge_sha
            )
            if outcome in {"stalled", "evaluation_limit"}:
                self.state.set_metadata("development_status", {"status": outcome})
            elif outcome == "main_changed":
                self.state.set_metadata("development_status", {"status": outcome})
        except (ValueError, OSError):
            self.queue.request(
                None,
                "scope",
                fingerprint(
                    {
                        "spec": self.state.metadata("spec_hash"),
                        "reason": "project_evaluation_unavailable",
                    }
                ),
                "Project evaluation unavailable or interrupted. Inspect main, evidence and "
                "isolation before changing scope; independent approved tasks may continue.",
            )
            self.state.set_metadata("development_status", {"status": "evaluation_held"})

    def _execute(self, task: Task, context: dict[str, Any], run_id: str) -> None:
        if self.queue.pending_for(task.id):
            self._transition(task.id, "awaiting_approval", "human_decision_pending")
            return
        try:
            workspace = self.workspaces.prepare(task)
            initial = self.workspaces.snapshot(task, workspace)
        except (ValueError, OSError):
            self._transition(task.id, "blocked", "workspace_unavailable")
            return
        scope_hash = fingerprint(
            {
                "task": task.specification_hash(),
                "spec": self.state.metadata("spec_hash"),
                "base": initial.get("base"),
                "policy": self.config,
                "risk_floor": self.state.effective_risk(task.id),
            }
        )
        if task.requires_approval or self.state.effective_risk(task.id) == "high":
            if self.queue.status(task.id, "scope", scope_hash) != "approved":
                self.queue.request(
                    task.id,
                    "scope",
                    scope_hash,
                    "Approve this exact task/base/policy scope?",
                    "high",
                )
                self._transition(task.id, "awaiting_approval", "preapproval_required")
                return
        task, execution = self.state.claim(
            task.id, run_id, self.config["loop"]["max_attempts_per_task"]
        )
        timeout = min(self.config["loop"]["task_timeout_minutes"] * 60, self.deadline - time.time())
        task_deadline = time.monotonic() + timeout

        def task_cancelled() -> bool:
            return self.cancelled() or time.monotonic() >= task_deadline

        try:
            attempt_context = {
                **context,
                "previous_failure": self.state.get_checkpoint(task.id).get("failure_context"),
                "effective_risk": self.state.effective_risk(task.id),
            }
            result = self.worker.execute(
                task, attempt_context, workspace, timeout=timeout, cancelled=task_cancelled
            )
            check_result(task, result)
            self.state.finish_execution(execution, "returned", result)
        except (ValueError, OSError):
            self.state.finish_execution(
                execution, "failed", {"code": "worker_unavailable_or_invalid"}
            )
            self._transition(task.id, "blocked", "worker_unavailable_or_invalid")
            return
        if task_cancelled():
            self._transition(task.id, "blocked", "interrupted_requires_assessment")
            return
        if result["status"] != "implemented":
            self._retry_or_block(task.id, "worker_reported_failure")
            return
        snapshot = self.workspaces.snapshot(task, workspace)
        if any(not allowed(path, task.allowed_paths) for path in snapshot["paths"]):
            self._transition(task.id, "blocked", "actual_diff_outside_scope")
            return
        for request in result["approval_requests"]:
            self.queue.request(
                task.id,
                request["category"],
                fingerprint({"scope": scope_hash, "diff": snapshot}),
                request["question"],
            )
        self._transition(task.id, "verifying")
        verification = self.verifier.run(
            task.verification_profile,
            workspace,
            self.root,
            timeout=max(0, min(task_deadline - time.monotonic(), self.deadline - time.time())),
            cancelled=task_cancelled,
        )
        self.state.evidence("verification_results", execution, verification)
        if time.monotonic() >= task_deadline:
            self._transition(task.id, "blocked", "task_time_limit")
            return
        if self.cancelled():
            self._transition(task.id, "awaiting_approval", "paused_after_verification")
            return
        if not verification["passed"]:
            self.state.checkpoint(
                task.id,
                {
                    **self.state.get_checkpoint(task.id),
                    "failure_context": verification,
                },
            )
            if verification["status"] == "unavailable" or any(
                check["status"] == "skipped" and check["required"]
                for check in verification["checks"]
            ):
                self._transition(task.id, "blocked", "required_verification_unavailable")
            else:
                self._retry_or_block(task.id, "verification_failed")
            return
        self._transition(task.id, "reviewing")
        binding = review_binding(task, self.state.metadata("spec_hash"), snapshot, verification)
        try:
            review = self.reviewer.evaluate(
                task,
                workspace,
                context,
                snapshot,
                verification,
                timeout=max(0, min(task_deadline - time.monotonic(), self.deadline - time.time())),
                cancelled=task_cancelled,
            )
            self.state.evidence("reviews", task.id, review, binding)
        except (ValueError, OSError):
            self._transition(task.id, "blocked", "independent_review_unavailable")
            return
        if blocking(review):
            checkpoint = self.state.get_checkpoint(task.id)
            checkpoint["failure_context"] = review
            cycles = checkpoint.get("review_cycles", 0)
            if cycles >= self.config["loop"]["max_review_cycles"]:
                self._transition(task.id, "blocked", "review_cycle_limit")
            else:
                self.state.checkpoint(task.id, {**checkpoint, "review_cycles": cycles + 1})
                self._retry_or_block(task.id, "review_findings")
            return
        # Verification/review must still describe the current worktree and immutable control policy.
        if time.monotonic() >= task_deadline:
            self._transition(task.id, "blocked", "task_time_limit")
            return
        self._context()
        if self.workspaces.snapshot(task, workspace) != snapshot:
            self._transition(task.id, "blocked", "source_changed_after_verification")
            return
        checkpoint = self.state.get_checkpoint(task.id)
        self.state.checkpoint(
            task.id,
            {
                **checkpoint,
                "verified": True,
                "binding": binding,
                "snapshot": snapshot,
                "verification": verification,
                "workspace": str(workspace),
                "implementation": "verified",
            },
        )
        if self.cancelled():
            self._transition(task.id, "awaiting_approval", "paused_before_delivery")
            return
        if any(protected(path) for path in snapshot["paths"]):
            self.queue.request(
                task.id,
                "security",
                binding,
                "Separately approve changed tests/verification/policy/dependency surfaces?",
            )
        self._deliver(task)

    def _retry_or_block(self, task_id: str, reason: str) -> None:
        task = self.state.task(task_id)
        limit = min(task.max_attempts, self.config["loop"]["max_attempts_per_task"])
        self._transition(task_id, "ready" if task.attempts < limit else "blocked", reason)

    def _deliver(self, task: Task) -> None:
        if self.cancelled():
            if self.state.task(task.id).status != "awaiting_approval":
                self._transition(task.id, "awaiting_approval", "delivery_paused_or_limited")
            return
        checkpoint = self.state.get_checkpoint(task.id)
        # Central gate also applies to verified checkpoints resumed after a pause/crash.
        if any(protected(path) for path in checkpoint.get("snapshot", {}).get("paths", [])):
            self.queue.request(
                task.id,
                "security",
                checkpoint["binding"],
                "Separately approve changed tests/verification/policy/dependency surfaces?",
            )
        if self.queue.pending_for(task.id):
            self._transition(task.id, "awaiting_approval", "delivery_decision_pending")
            return
        delivery = self.config["github"]["delivery"]
        if delivery == "local":
            self._transition(task.id, "completed")
            return
        if not self.publisher:
            self._transition(task.id, "awaiting_approval", "github_publication_unavailable")
            return
        if delivery == "local_commit_push":
            # Persist a resumable, executor-idle stage BEFORE any Git mutation.
            self._transition(task.id, "awaiting_approval", "local_delivery_pending")
        try:
            delivered = self.publisher.deliver(task, checkpoint, cancelled=self.cancelled)
        except (ValueError, OSError):
            if delivery == "local_commit_push":
                # Stop the whole run: another task must not start on unpublished HEAD.
                # Resume reconciles durable Git intents, without resetting task attempts.
                self.state.set_metadata("control", "stopped")
                self.state.event("local_delivery.held", task.id)
                return
            # Never leave a settled worker in an active stage after a service outage.
            # No mutation is replayed here; reconciliation is task-scoped and human.
            self.queue.request(
                task.id,
                "publication",
                fingerprint(
                    {
                        "binding": checkpoint["binding"],
                        "reason": "delivery_unavailable_or_uncertain",
                    }
                ),
                "Reconcile Git/PR/CI outcome and service access before retrying delivery.",
            )
            self._transition(task.id, "awaiting_approval", "delivery_unavailable_or_uncertain")
            return
        if self.cancelled():
            if self.state.task(task.id).status != "awaiting_approval":
                self._transition(task.id, "awaiting_approval", "delivery_paused_or_limited")
            return
        if delivered.get("repairable"):
            # Revoke all old source approvals/evidence before a fresh claim increments
            # the same task budget. A subsequent commit must pass local QA + review.
            checkpoint = self.state.get_checkpoint(task.id)
            self.state.checkpoint(
                task.id,
                {
                    **checkpoint,
                    "verified": False,
                    "previous_committed_head": checkpoint.get("committed_head"),
                    "committed_head": None,
                    "commit_intent": None,
                    "failure_context": delivered["ci"],
                },
            )
            self._retry_or_block(task.id, "ci_failed")
        elif delivered.get("complete"):
            if delivered.get("merged") is True and delivered.get("merge_sha"):
                self.state.checkpoint(
                    task.id,
                    {**self.state.get_checkpoint(task.id), "merge_sha": delivered["merge_sha"]},
                )
            self._transition(task.id, "completed")
            if self.development and delivery == "local_commit_push":
                self._assess_project(delivered["integrated_head"])
            if (
                self.development
                and delivery == "merged"
                and delivered.get("merged") is True
                and delivered.get("merge_sha")
            ):
                self._assess_project(delivered["merge_sha"])
        else:
            ci = delivered.get("ci", {})
            if ci.get("status") not in {None, "pending", "passed"}:
                self.queue.request(
                    task.id,
                    "scope",
                    fingerprint({"binding": checkpoint["binding"], "ci": ci}),
                    f"CI held ({ci.get('status')}, {ci.get('category', 'unclassified')}). "
                    "Recommend inspecting service/check configuration and current run evidence; "
                    "do not change credentials, billing, checks or permissions automatically.",
                )
            self._transition(task.id, "awaiting_approval", "ci_or_merge_or_approval_pending")

    def _resume_deliveries(self) -> None:
        for task in self.state.tasks():
            if self.cancelled():
                break
            if task.status != "awaiting_approval":
                continue
            reconcile = getattr(self.publisher, "reconcile_ci_registration", None)
            if reconcile and self.queue.ci_registration_decision(task.id):
                try:
                    reconcile(task, self.state.get_checkpoint(task.id), cancelled=self.cancelled)
                except (ValueError, OSError):
                    self.state.event("ci.registration_recheck_held", task.id)
            if self.queue.pending_for(task.id):
                continue
            checkpoint = self.state.get_checkpoint(task.id)
            if checkpoint.get("verified"):
                if self.config["github"]["delivery"] == "local_commit_push":
                    self._deliver(task)
                    continue
                workspace = Path(checkpoint["workspace"])
                if self.workspaces.snapshot(task, workspace) != checkpoint["snapshot"]:
                    self._transition(task.id, "blocked", "verified_source_changed")
                else:
                    self._deliver(task)
            else:
                self._transition(task.id, "ready")
