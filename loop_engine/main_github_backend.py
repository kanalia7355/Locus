"""Offline-only gh protocol adapter for the existing MainIntegration dependency.

Uses existing GitHubManager's process and bounded JSON parsing. A real/default
ProcessRunner is rejected; no activation path or GitHub write is enabled here.
"""

import base64
import hashlib
import json
import math
import re
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar
from urllib.parse import urlencode

from loop_engine.github_manager import GitHubManager
from loop_engine.main_integration import SOURCE, TARGET, atomic_payload, verified_ci
from loop_engine.planning import bounded_json
from loop_engine.security import SafetyError, fingerprint

P = ParamSpec("P")
R = TypeVar("R")


def _closed(function: Callable[P, R]) -> Callable[P, R]:  # noqa: UP047 -- Python3.11 runtime
    @wraps(function)
    def guarded(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return function(*args, **kwargs)
        except (KeyError, TypeError, AttributeError, ValueError):
            raise SafetyError("GitHub response contract rejected; no fallback") from None

    return guarded


class OfflineGitHubBackend:
    offline = True

    def __init__(self, manager: GitHubManager, policy: dict[str, Any], deadline: float) -> None:
        if getattr(manager.process, "offline", False) is not True:
            raise SafetyError("Real GitHub transport is not activated")
        if not math.isfinite(deadline) or not time.time() < deadline <= time.time() + 1800:
            raise SafetyError("Bounded offline adapter deadline required")
        if (
            manager.config["repository"] != policy["repository"]
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", policy["repository"])
            or policy["source"] != SOURCE
            or policy["target"] != TARGET
        ):
            raise SafetyError("Offline GitHub repository/ref policy mismatch")
        self.manager, self.policy, self.deadline = manager, policy, deadline
        self.repo = policy["repository"]
        self.observation_deadline: float | None = None

    def _intent(self, sha: str | None = None) -> dict[str, Any] | None:
        with self.manager.state.connect() as db:
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='main_promotions'"
            ).fetchone():
                return None
            rows = db.execute(
                "SELECT * FROM main_promotions WHERE target_ref=?", (TARGET,)
            ).fetchall()
        for row in reversed(rows):
            if sha is not None and row["sha"] != sha:
                continue
            if row["phase"] in {"update_reserved", "remote_confirmed", "recorded"}:
                doc = json.loads(row["document"])
                if doc["policy"] == fingerprint(self.policy):
                    return {**doc, "phase": row["phase"]}
        return None

    def _send_allowed(self, before: str, after: str) -> None:
        doc = self._intent(after)
        budget = self.manager.state.metadata("run_budget", {})
        if (
            doc is None
            or doc["phase"] != "update_reserved"
            or doc["before"] != before
            or self.manager.state.metadata("control") != "running"
            or budget.get("id") != doc["run"]
            or time.time() >= min(self.deadline, doc["deadline"], budget.get("deadline", 0))
        ):
            raise SafetyError("No current reserved main mutation within the Controller budget")
        verified_ci(doc["ci_evidence"], self.policy, after)

    def _api(self, endpoint: str, payload: dict[str, Any] | None = None) -> Any:
        left = self.deadline - time.time()
        if left <= 0 and payload is None and self._intent() is not None:
            # A fixed observational window never re-enables POST or task execution.
            if self.observation_deadline is None:
                self.observation_deadline = time.time() + 60
            left = self.observation_deadline - time.time()
        if left <= 0 or getattr(self.manager.process, "offline", False) is not True:
            raise SafetyError("Offline transport expired or changed")
        args = ["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint]
        if payload is not None:
            if endpoint != "graphql":
                raise SafetyError("Only the fixed atomic mutation shape is supported")
            args = [
                "gh",
                "api",
                "--hostname",
                "github.com",
                "--method",
                "POST",
                "graphql",
                "--input",
                "-",
            ]
        result = self.manager.process.run(
            args,
            self.manager.root,
            timeout=min(30, left),
            stdin="" if payload is None else json.dumps(payload),
            output_limit=1_000_000,
        )
        if result.outcome != "exit" or result.returncode != 0:
            raise SafetyError("GitHub outcome unavailable; no retry/fallback")
        value = bounded_json(result.stdout)
        if isinstance(value, dict) and value.get("errors"):
            raise SafetyError("GraphQL operation rejected or uncertain")
        return value

    def _identity(self) -> None:
        repo, user = self._api("repos/" + self.repo), self._api("user")
        if (
            repo.get("node_id") != self.policy["repository_id"]
            or repo.get("full_name") != self.repo
            or repo.get("permissions", {}).get("push") is not True
            or user.get("login") != self.repo.split("/")[0]
        ):
            raise SafetyError("GitHub identity or permission differs")

    @_closed
    def refs(self) -> dict[str, str]:
        self._identity()
        result = {}
        for ref in (SOURCE, TARGET):
            value = self._api(f"repos/{self.repo}/git/ref/" + ref.removeprefix("refs/"))
            sha = value.get("object", {}).get("sha", "")
            if (
                value.get("ref") != ref
                or value.get("object", {}).get("type") != "commit"
                or not re.fullmatch(r"[a-f0-9]{40}", sha)
            ):
                raise SafetyError("Invalid exact Git reference")
            result[ref] = sha
        return result

    def _pages(self, endpoint: str, field: str) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        total = None
        separator = "&" if "?" in endpoint else "?"
        for page in range(1, 11):
            result = self._api(endpoint + separator + f"per_page=100&page={page}")
            if (
                not isinstance(result, dict)
                or type(result.get("total_count")) is not int
                or not 0 <= result["total_count"] <= 1000
                or not isinstance(result.get(field), list)
            ):
                raise SafetyError("Invalid bounded GitHub page")
            if total is None:
                total = result["total_count"]
            if total != result["total_count"]:
                raise SafetyError("GitHub pages changed during observation")
            chunk = result[field]
            if len(chunk) > 100 or any(not isinstance(x, dict) for x in chunk):
                raise SafetyError("Invalid GitHub page items")
            values.extend(chunk)
            if len(values) == total:
                if len({x["id"] for x in values}) != total:
                    raise SafetyError("Duplicate GitHub page item")
                return values
            if len(chunk) != 100 or len(values) > total:
                raise SafetyError("Truncated GitHub page")
        raise SafetyError("GitHub pagination budget exhausted")

    @_closed
    def checks(self, sha: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-f0-9]{40}", sha):
            raise SafetyError("Exact CI commit required")
        self._identity()
        query = urlencode(
            {"head_sha": sha, "event": "push", "branch": SOURCE.removeprefix("refs/heads/")}
        )
        runs = self._pages(f"repos/{self.repo}/actions/runs?{query}", "workflow_runs")
        normalized = []
        for expected in self.policy["workflows"]:
            matches = [r for r in runs if r.get("path") == expected["path"]]
            if len(matches) != 1:
                raise SafetyError("Missing or ambiguous pushed workflow")
            run = matches[0]
            if (
                run.get("head_sha") != sha
                or run.get("event") != "push"
                or run.get("head_branch") != SOURCE.removeprefix("refs/heads/")
                or run.get("repository", {}).get("node_id") != self.policy["repository_id"]
                or run.get("head_repository", {}).get("node_id") != self.policy["repository_id"]
                or type(run.get("id")) is not int
                or run["id"] <= 0
                or type(run.get("run_attempt")) is not int
                or run["run_attempt"] < 1
                or run.get("status") != "completed"
                or run.get("conclusion") != "success"
                or type(run.get("check_suite_id")) is not int
                or run["check_suite_id"] <= 0
            ):
                raise SafetyError("Unbound workflow identity/attempt")
            path = expected["path"]
            blob = self._api(f"repos/{self.repo}/contents/{path}?ref={sha}")
            if (
                blob.get("type") != "file"
                or blob.get("path") != path
                or blob.get("encoding") != "base64"
                or not 0 < blob.get("size", 0) <= 65536
            ):
                raise SafetyError("Workflow source cannot be verified")
            try:
                content = base64.b64decode("".join(blob["content"].splitlines()), validate=True)
            except (ValueError, TypeError):
                raise SafetyError("Workflow encoding rejected") from None
            digest = hashlib.sha256(content).hexdigest()
            if len(content) != blob["size"] or digest != expected["digest"]:
                raise SafetyError("Workflow bytes differ from reviewed CI policy")
            run_id, attempt = run["id"], run["run_attempt"]
            jobs = self._pages(
                f"repos/{self.repo}/actions/runs/{run_id}/attempts/{attempt}/jobs", "jobs"
            )
            bound_jobs = []
            for job in jobs:
                url = job.get("check_run_url", "")
                match = re.fullmatch(
                    rf"https://api\.github\.com/repos/{re.escape(self.repo)}/check-runs/(\d+)", url
                )
                if (
                    not match
                    or job.get("run_id") != run_id
                    or job.get("run_attempt") != attempt
                    or job.get("head_sha") != sha
                ):
                    raise SafetyError("Job does not belong to exact workflow attempt")
                check_run = self._api(f"repos/{self.repo}/check-runs/{match[1]}")
                if (
                    check_run.get("app", {}).get("id") != 15368
                    or check_run.get("id") != int(match[1])
                    or check_run.get("head_sha") != sha
                    or check_run.get("name") != job.get("name")
                    or check_run.get("check_suite", {}).get("id") != run.get("check_suite_id")
                    or check_run.get("status") != job.get("status")
                    or check_run.get("conclusion") != job.get("conclusion")
                ):
                    raise SafetyError("Untrusted or inconsistent Checks publisher")
                bound_jobs.append(
                    {
                        "id": job["id"],
                        "name": job["name"],
                        "status": job["status"],
                        "conclusion": job["conclusion"],
                        "sha": sha,
                    }
                )
            after = self._api(f"repos/{self.repo}/actions/runs/{run_id}")
            if any(
                after.get(k) != run.get(k)
                for k in (
                    "id",
                    "path",
                    "head_sha",
                    "head_branch",
                    "run_attempt",
                    "event",
                    "status",
                    "conclusion",
                    "check_suite_id",
                    "repository",
                    "head_repository",
                )
            ):
                raise SafetyError("Workflow changed while collecting its jobs")
            normalized.append(
                {
                    "path": path,
                    "digest": digest,
                    "id": run_id,
                    "attempt": attempt,
                    "latest_attempt": after["run_attempt"],
                    "event": "push",
                    "app_id": 15368,
                    "sha": sha,
                    "jobs": bound_jobs,
                }
            )
        return {
            "complete": True,
            "repository_id": self.policy["repository_id"],
            "sha": sha,
            "branch": SOURCE.removeprefix("refs/heads/"),
            "runs": normalized,
        }

    def _protection(self, before: str) -> None:
        branch = self._api(f"repos/{self.repo}/branches/main")
        policy = self._api(f"repos/{self.repo}/branches/main/protection")
        rules = self._api(f"repos/{self.repo}/rules/branches/main")
        expected = {(name, 15368) for w in self.policy["workflows"] for name in w["jobs"]}
        checks = policy.get("required_status_checks", {})
        if (
            branch.get("protected") is not True
            or branch.get("commit", {}).get("sha") != before
            or policy.get("required_pull_request_reviews") is not None
            or policy.get("enforce_admins", {}).get("enabled") is not True
            or checks.get("strict") is not True
            or {(x.get("context"), x.get("app_id")) for x in checks.get("checks", [])} != expected
            or policy.get("allow_force_pushes", {}).get("enabled") is not False
            or policy.get("allow_deletions", {}).get("enabled") is not False
            or rules != []
        ):
            raise SafetyError("PR-free protected fast-forward policy is not established")

    @_closed
    def update_refs(self, before: str, after: str) -> None:
        # MainIntegration has already durably reserved the single operation.
        self._send_allowed(before, after)
        if self.refs() != {SOURCE: after, TARGET: before}:
            raise SafetyError("References changed before atomic update")
        self._protection(before)
        self._send_allowed(before, after)
        payload = {
            "query": (
                "mutation($input:UpdateRefsInput!){updateRefs(input:$input){clientMutationId}}"
            ),
            "variables": {"input": atomic_payload(self.policy["repository_id"], before, after)},
        }
        result = self._api("graphql", payload)
        if not isinstance(result.get("data", {}).get("updateRefs"), dict):
            raise SafetyError("Atomic update reply unknown; no resend")
        if self.refs() != {SOURCE: after, TARGET: after}:
            raise SafetyError("Atomic update is not confirmed")
        self._protection(after)
