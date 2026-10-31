"""Explicitly authorized gh integration and fail-closed merge eligibility."""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loop_engine.approval import ApprovalQueue
from loop_engine.checks import ChecksMonitor
from loop_engine.config import load
from loop_engine.git_manager import GitManager
from loop_engine.models import Task
from loop_engine.planning import bounded_json
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError, allowed, atomic_text, fingerprint
from loop_engine.state_store import StateStore


def merge_reasons(task: Task, config: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    reasons = []
    if config["auto_merge"] != "safe" or not evidence.get("human_authorized"):
        reasons.append("auto_merge_not_authorized")
    if (
        task.risk_level != "low"
        or evidence.get("risk_level", task.risk_level) != "low"
        or evidence.get("pending_approvals")
    ):
        reasons.append("risk_or_pending_approval")
    if not evidence.get("paths") or any(
        not allowed(path, config["auto_merge_allowed_paths"]) for path in evidence["paths"]
    ):
        reasons.append("paths_not_allowlisted")
    for key in (
        "review_passed",
        "trusted_review_publisher",
        "review_head_base_policy_bound",
        "ci_complete",
        "protection_verified",
        "strict_current_base",
        "conversations_resolved",
        "mergeable",
        "head_matches",
        "base_matches",
        "atomic_base_binding",
    ):
        if evidence.get(key) is not True:
            reasons.append(key)
    return reasons


class GitHubManager:
    def __init__(
        self, root: Path, state: StateStore, git: GitManager, config: dict[str, Any]
    ) -> None:
        self.root, self.state, self.git, self.config = root, state, git, config
        self.queue = ApprovalQueue(state)
        self.process = ProcessRunner()

    def _gh(self, args: list[str], *, cancelled: Callable[[], bool] = lambda: False) -> str:
        if cancelled():
            raise SafetyError("GitHub operation cancelled")
        outcome = self.process.run(["gh", *args], self.root, timeout=30, cancelled=cancelled)
        if outcome.outcome != "exit" or outcome.returncode != 0:
            raise SafetyError("GitHub operation failed or uncertain; reconcile before mutation")
        return outcome.stdout

    def _api(self, endpoint: str, cancelled: Callable[[], bool]) -> Any:
        return bounded_json(self._gh(["api", endpoint], cancelled=cancelled))

    def _existing(self, branch: str, cancelled: Callable[[], bool]) -> list[dict[str, Any]]:
        values = bounded_json(
            self._gh(
                [
                    "pr",
                    "list",
                    "--repo",
                    self.config["repository"],
                    "--head",
                    branch,
                    "--base",
                    self.config["base"],
                    "--state",
                    "all",
                    "--json",
                    "number,url,state,headRefOid,baseRefName",
                ],
                cancelled=cancelled,
            )
        )
        if len(values) > 1:
            raise SafetyError("Ambiguous pull request identity")
        return values  # type: ignore[no-any-return]

    def deliver(
        self, task: Task, checkpoint: dict[str, Any], *, cancelled: Callable[[], bool]
    ) -> dict[str, Any]:
        if not self.config["enabled"] or not re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.config["repository"]
        ):
            return {"complete": False, "reason": "repository_not_configured"}
        publication = fingerprint({"config": self.config, "binding": checkpoint["binding"]})
        routine = load(self.root / ".loop/config.yaml")["approval"]["routine_publication"]
        if not routine and self.queue.status(task.id, "publication", publication) != "approved":
            self.queue.request(
                task.id,
                "publication",
                publication,
                "Authorize this exact repository/base and verified change publication?",
            )
            return {"complete": False, "reason": "publication_approval_pending"}
        workspace = Path(checkpoint["workspace"])
        commit = self.git.finalize(task, workspace, checkpoint["binding"])
        repo = self.config["repository"]
        remote = self.git._git(["remote", "get-url", "origin"], workspace)
        if remote not in {
            f"https://github.com/{repo}.git",
            f"https://github.com/{repo}",
            f"git@github.com:{repo}.git",
        }:
            raise SafetyError("Remote repository identity does not match authorization")
        destinations = self.git._git(
            ["remote", "get-url", "--push", "--all", "origin"], workspace
        ).splitlines()
        if len(destinations) != 1 or destinations[0] not in {
            f"https://github.com/{repo}.git",
            f"https://github.com/{repo}",
            f"git@github.com:{repo}.git",
        }:
            raise SafetyError("Effective push destinations differ from authorized repository")
        existing = self._existing(commit["branch"], cancelled)
        if not existing:
            intent = self.state.get_pr(task.id)
            if intent.get("create_uncertain"):
                raise SafetyError("Prior PR create outcome is uncertain; no blind duplicate create")
            self.state.record_pr(
                task.id, {"create_intent": True, "head": commit["head"], "branch": commit["branch"]}
            )
            self.git._git(["push", "origin", f"{commit['branch']}:{commit['branch']}"], workspace)
            body = (
                f"Task: {task.id}\n\nGoal relation: {task.title}\n\n"
                f"Verified change: {checkpoint['binding']}\n\nFiles: "
                + ", ".join(checkpoint["snapshot"]["paths"])
                + "\n\nVerification: local required checks passed.\nLocal review: passed.\n"
                + "CI and trusted remote review remain separate gates.\n"
                + (
                    "Approval: operator standing publication authorization.\n"
                    if routine
                    else "Approval: exact publication approved.\n"
                )
                + f"Risk: {task.risk_level}. No automatic protection bypass.\n"
            )
            body_path = self.root / ".loop/runtime" / f"{task.id}-pr-body.md"
            atomic_text(body_path, body)
            try:
                self._gh(
                    [
                        "pr",
                        "create",
                        "--repo",
                        repo,
                        "--head",
                        commit["branch"],
                        "--base",
                        self.config["base"],
                        "--title",
                        f"feat: implement {task.id}",
                        "--body-file",
                        str(body_path),
                        "--no-maintainer-edit",
                    ],
                    cancelled=cancelled,
                )
            except SafetyError:
                self.state.record_pr(task.id, {"create_uncertain": True, **commit})
                raise
            existing = self._existing(commit["branch"], cancelled)
        if not existing:
            return {"complete": False, "reason": "pull_request_not_observable"}
        pr = existing[0]
        if pr["headRefOid"] != commit["head"] and pr["state"] == "OPEN":
            previous = checkpoint.get("previous_committed_head")
            if not previous or pr["headRefOid"] != previous:
                raise SafetyError("PR head changed outside the verified repair lineage")
            self.git._git(["merge-base", "--is-ancestor", previous, commit["head"]], workspace)
            self.git._git(["push", "origin", f"{commit['branch']}:{commit['branch']}"], workspace)
            observed_prs = self._existing(commit["branch"], cancelled)
            if not observed_prs:
                raise SafetyError("Repair push outcome uncertain")
            pr = observed_prs[0]
        self.state.record_pr(task.id, {**pr, **commit, "publication": "observed"})
        if pr["headRefOid"] != commit["head"]:
            raise SafetyError("PR head changed")
        if pr["state"] == "MERGED":
            return {"complete": False, "state": "merged_requires_evidence_reconciliation"}
        if pr["state"] != "OPEN":
            return {"complete": False, "reason": "pr_not_open"}
        ci = ChecksMonitor(self.root, repo, self.config["required_checks"]).observe(
            pr["number"],
            commit["head"],
            cancelled=cancelled,
        )
        self.state.record_pr(task.id, {**pr, **commit, "ci": ci})
        if ci["status"] != "passed":
            return {"complete": False, "ci": ci, "repairable": ci["repairable"]}
        if self.config["delivery"] == "pull_request":
            detail = self._api(f"repos/{repo}/pulls/{pr['number']}", cancelled)
            identity = (
                detail.get("head", {}).get("sha") == commit["head"]
                and detail.get("head", {}).get("repo", {}).get("full_name") == repo
                and detail.get("base", {}).get("ref") == self.config["base"]
                and detail.get("base", {}).get("repo", {}).get("full_name") == repo
            )
            return {
                "complete": identity,
                "state": "pull_request_verified_merge_held" if identity else "identity_mismatch",
                "merged": False,
            }
        evidence = self.remote_evidence(task, checkpoint, pr, cancelled)
        reasons = merge_reasons(task, self.config, evidence)
        if reasons:
            return {"complete": False, "merge_blockers": reasons}
        if cancelled():
            return {"complete": False, "reason": "cancelled"}
        # Immediate conditional merge; never enable a future-head auto-merge authorization.
        self._gh(
            [
                "pr",
                "merge",
                str(pr["number"]),
                "--repo",
                repo,
                "--squash",
                "--match-head-commit",
                commit["head"],
                "--subject",
                f"feat: implement {task.id}",
            ],
            cancelled=cancelled,
        )
        observed = self._existing(commit["branch"], cancelled)
        if not observed or observed[0]["state"] != "MERGED":
            return {"complete": False, "reason": "merge_not_observed"}
        detail = self._api(f"repos/{repo}/pulls/{pr['number']}", cancelled)
        merge_sha = detail.get("merge_commit_sha", "")
        if (
            detail.get("merged") is not True
            or detail.get("head", {}).get("sha") != commit["head"]
            or detail.get("base", {}).get("ref") != self.config["base"]
            or detail.get("base", {}).get("repo", {}).get("full_name") != repo
            or not re.fullmatch(r"[a-f0-9]{40,64}", merge_sha)
        ):
            raise SafetyError("Merge result identity requires reconciliation")
        return {"complete": True, "merged": True, "merge_sha": merge_sha}

    def remote_evidence(
        self,
        task: Task,
        checkpoint: dict[str, Any],
        pr: dict[str, Any],
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]:
        repo, base, head = self.config["repository"], self.config["base"], pr["headRefOid"]
        evidence: dict[str, Any] = {
            "paths": checkpoint["snapshot"]["paths"],
            "review_passed": True,
            "pending_approvals": self.queue.pending_for(task.id),
            "risk_level": self.state.effective_risk(task.id),
            "head_matches": head == self.state.get_checkpoint(task.id).get("committed_head"),
        }
        branch = self._api(f"repos/{repo}/branches/{base}", cancelled)
        base_sha = branch["commit"]["sha"]
        evidence["base_matches"] = base_sha == checkpoint["snapshot"]["base"]
        binding = fingerprint({"repo": repo, "base": base_sha, "head": head, "policy": self.config})
        evidence["human_authorized"] = self.queue.status(task.id, "merge", binding) == "approved"
        if self.config["auto_merge"] == "safe" and not evidence["human_authorized"]:
            self.queue.request(
                task.id,
                "merge",
                binding,
                "Authorize conditional merge for this exact head/base/policy?",
                "low",
            )
        protection = self._api(f"repos/{repo}/branches/{base}/protection", cancelled)
        rules = self._api(f"repos/{repo}/rules/branches/{base}", cancelled)
        status_policy = protection.get("required_status_checks", {})
        required = self.config["required_checks"]
        checks = self._api(f"repos/{repo}/commits/{head}/check-runs?per_page=100", cancelled)
        runs = checks.get("check_runs", [])
        evidence["ci_complete"] = (
            bool(required)
            and checks.get("total_count") == len(runs)
            and all(
                any(
                    run["name"] == name
                    and run["status"] == "completed"
                    and run["conclusion"] == "success"
                    for run in runs
                )
                for name in required
            )
        )
        evidence["strict_current_base"] = status_policy.get("strict") is True
        policy_checks = status_policy.get("checks", [])
        evidence["protection_verified"] = (
            branch.get("protected") is True
            and protection.get("enforce_admins", {}).get("enabled") is True
            and protection.get("required_pull_request_reviews", {}).get(
                "required_approving_review_count", 0
            )
            >= 1
            and protection.get("required_pull_request_reviews", {}).get("dismiss_stale_reviews")
            is True
            and protection.get("required_conversation_resolution", {}).get("enabled") is True
            and set(required) <= {check["context"] for check in policy_checks}
            and not any(rule.get("type") == "merge_queue" for rule in rules)
        )
        # A separate authenticated review publisher must publish the head/base/policy binding.
        trusted = [
            run
            for run in runs
            if run["name"] == "loop-independent-review"
            and run.get("app", {}).get("id", 0) > 0
            and bool(run.get("app", {}).get("slug"))
            and run.get("app", {}).get("slug") != "github-actions"
            and any(
                check["context"] == run["name"]
                and check.get("app_id") == run.get("app", {}).get("id")
                for check in policy_checks
            )
        ]
        evidence["trusted_review_publisher"] = bool(trusted) and all(
            run["conclusion"] == "success" for run in trusted
        )
        evidence["review_head_base_policy_bound"] = bool(trusted) and all(
            run.get("external_id") == binding for run in trusted
        )
        detail = self._api(f"repos/{repo}/pulls/{pr['number']}", cancelled)
        evidence["mergeable"] = (
            detail.get("mergeable") is True and detail.get("mergeable_state") == "clean"
        )
        owner, name = repo.split("/")
        query = (
            "query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name)"
            "{pullRequest(number:$number){reviewThreads(first:100){nodes{isResolved}"
            "pageInfo{hasNextPage}}}}}"
        )
        graph = bounded_json(
            self._gh(
                [
                    "api",
                    "graphql",
                    "-f",
                    "query=" + query,
                    "-f",
                    "owner=" + owner,
                    "-f",
                    "name=" + name,
                    "-F",
                    f"number={pr['number']}",
                ],
                cancelled=cancelled,
            )
        )
        threads = graph["data"]["repository"]["pullRequest"]["reviewThreads"]
        evidence["conversations_resolved"] = threads["pageInfo"]["hasNextPage"] is False and all(
            thread["isResolved"] is True for thread in threads["nodes"]
        )
        evidence["base_matches"] = (
            evidence["base_matches"]
            and self._api(f"repos/{repo}/branches/{base}", cancelled)["commit"]["sha"] == base_sha
        )
        evidence["head_matches"] = evidence["head_matches"] and detail["head"]["sha"] == head
        evidence["head_matches"] = (
            evidence["head_matches"] and detail["head"]["repo"]["full_name"] == repo
        )
        evidence["base_matches"] = evidence["base_matches"] and (
            detail.get("base", {}).get("ref") == base
            and detail.get("base", {}).get("sha") == base_sha
            and detail.get("base", {}).get("repo", {}).get("full_name") == repo
        )
        evidence["atomic_base_binding"] = False  # gh does not atomically match the PR base ref.
        return evidence

    def reconcile_ci_registration(
        self, task: Task, checkpoint: dict[str, Any], *, cancelled: Callable[[], bool]
    ) -> bool:
        if not self.queue.ci_registration_decision(task.id):
            return False
        workspace = Path(checkpoint["workspace"])
        head = checkpoint["committed_head"]
        if (
            self.git.snapshot(task, workspace) != checkpoint["snapshot"]
            or self.git._git(["rev-parse", "HEAD"], workspace) != head
        ):
            raise SafetyError("CI registration recovery source changed")
        pr = self.state.get_pr(task.id)
        observed = ChecksMonitor(
            self.root, self.config["repository"], self.config["required_checks"]
        ).observe(pr["number"], head, cancelled=cancelled)
        if observed.get("status") != "passed":
            return False
        detail = self._api(f"repos/{self.config['repository']}/pulls/{pr['number']}", cancelled)
        if (
            detail.get("state") != "open"
            or detail.get("head", {}).get("sha") != head
            or detail.get("head", {}).get("repo", {}).get("full_name") != self.config["repository"]
            or detail.get("base", {}).get("ref") != self.config["base"]
            or detail.get("base", {}).get("repo", {}).get("full_name") != self.config["repository"]
        ):
            raise SafetyError("CI registration recovery PR identity changed")
        return self.queue.retire_ci_registration(task.id, observed)
