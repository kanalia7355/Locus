"""Bounded current-head CI observations. Remote logs are untrusted input."""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loop_engine.planning import bounded_json
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError, reject_secrets


def sanitized(value: str, limit: int = 12000) -> str:
    # Never persist a suspect line. The guard also catches tokens embedded in URLs.
    clean = []
    for line in value.splitlines():
        line = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line)
        if re.search(r"(?i)(password|token|secret|authorization|api.?key)\s*[:=]", line):
            clean.append("[credential-bearing line removed]")
            continue
        try:
            reject_secrets(line)
        except ValueError:
            clean.append("[sensitive line removed]")
        else:
            clean.append(line)
    return "\n".join(clean)[-limit:]


def classify(log: str) -> str:
    text = log.lower()
    for category, terms in (
        ("billing", ("billing", "spending limit", "payment", "budget exceeded")),
        ("authentication", ("authentication failed", "bad credentials", "http 401")),
        ("permission", ("permission denied", "resource not accessible", "http 403")),
        ("infrastructure", ("github incident", "service unavailable", "runner lost", "http 503")),
    ):
        if any(term in text for term in terms):
            return category
    if any(
        term in text for term in ("assertionerror", "failed tests/", "error ts", "mypy error:")
    ) or re.search(
        r"\.(?:py|tsx?|jsx?|rs|go):\d+(?::\d+)?:?\s*(?:error|[a-z]\d{3})",
        text,
    ):
        return "code"
    return "unknown"


class ChecksMonitor:
    def __init__(self, root: Path, repository: str, required: list[str]) -> None:
        self.root, self.repository, self.required = root, repository, required
        self.process = ProcessRunner()

    def _gh(
        self, args: list[str], cancelled: Callable[[], bool], codes: tuple[int, ...] = (0,)
    ) -> str:
        if cancelled():
            raise SafetyError("CI observation cancelled")
        result = self.process.run(["gh", *args], self.root, timeout=30, cancelled=cancelled)
        if result.outcome != "exit" or result.returncode not in codes:
            raise SafetyError("CI service unavailable; no repair attempted")
        return result.stdout

    def observe(self, number: int, head: str, *, cancelled: Callable[[], bool]) -> dict[str, Any]:
        if not self.required:
            return {
                "status": "missing",
                "head": head,
                "repairable": False,
                "checks": [],
                "runs": [],
            }
        prefix = ["--repo", self.repository]

        def current() -> str:
            return str(
                bounded_json(
                    self._gh(
                        ["pr", "view", str(number), *prefix, "--json", "headRefOid"], cancelled
                    )
                )["headRefOid"]
            )

        if current() != head:
            return {"status": "stale", "head": head, "repairable": False}
        checks = bounded_json(
            self._gh(
                ["pr", "checks", str(number), *prefix, "--json", "name,state,bucket,link"],
                cancelled,
                (0, 1, 8),
            )
        )
        runs = bounded_json(
            self._gh(
                [
                    "run",
                    "list",
                    *prefix,
                    "--commit",
                    head,
                    "--limit",
                    "100",
                    "--json",
                    "databaseId,headSha,status,conclusion",
                ],
                cancelled,
            )
        )
        if not isinstance(checks, list) or not isinstance(runs, list):
            raise SafetyError("Invalid CI observation")
        if current() != head or any(run["headSha"] != head for run in runs):
            return {"status": "stale", "head": head, "repairable": False}
        evidence: dict[str, Any] = {
            "head": head,
            "checks": checks,
            "runs": runs,
            "repairable": False,
        }
        names = [check["name"] for check in checks]
        # Push and PR workflows may publish the same context at the same HEAD.
        # Require every observed instance to pass; never choose a successful
        # duplicate while ignoring its failed, pending or cancelled sibling.
        if not checks or not self.required or any(name not in names for name in self.required):
            return {**evidence, "status": "missing"}
        if any(check["bucket"] == "pending" for check in checks):
            return {**evidence, "status": "pending"}
        if all(check["bucket"] == "pass" for check in checks):
            return {**evidence, "status": "passed"}
        failed = [check for check in checks if check["bucket"] == "fail"]
        if (
            not failed
            or len(failed) > 3
            or any(check["bucket"] not in {"pass", "fail"} for check in checks)
        ):
            return {**evidence, "status": "unsuccessful"}
        logs_parts = []
        bound_runs = []
        for check in failed:
            match = re.fullmatch(
                rf"https://github\.com/{re.escape(self.repository)}/actions/runs/(\d+)/job/(\d+)(?:\?.*)?",
                check.get("link", ""),
            )
            if not match:
                return {**evidence, "status": "failed", "category": "unbound_check"}
            run_id, job_id = map(int, match.groups())
            args = ["run", "view", str(run_id), *prefix, "--json", "attempt,headSha,jobs"]
            detail = bounded_json(self._gh(args, cancelled))
            if detail["headSha"] != head or not any(
                job["databaseId"] == job_id and job["conclusion"] == "failure"
                for job in detail["jobs"]
            ):
                return {**evidence, "status": "stale"}
            attempt = detail["attempt"]
            logs_parts.append(
                self._gh(
                    [
                        "run",
                        "view",
                        str(run_id),
                        *prefix,
                        "--attempt",
                        str(attempt),
                        "--job",
                        str(job_id),
                        "--log-failed",
                    ],
                    cancelled,
                )
            )
            after = bounded_json(self._gh(args, cancelled))
            if after != detail or current() != head:
                return {**evidence, "status": "stale"}
            bound_runs.append({"run_id": run_id, "job_id": job_id, "attempt": attempt})
        logs = "\n".join(logs_parts)
        category = classify(logs)
        return {
            **evidence,
            "status": "failed",
            "category": category,
            "failed_jobs": bound_runs,
            "repairable": category == "code",
            "failure_context": sanitized(logs),
        }
