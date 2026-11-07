"""Disabled-by-default post-Push promotion, in the existing delivery/SQLite authority.

Only an explicitly supplied offline backend is accepted in this release. No
GitHub mutation transport, activation flag, token handling or fallback exists.
"""

import json
import re
import time
from collections.abc import Callable
from typing import Any, Protocol

from loop_engine.git_manager import GitManager
from loop_engine.models import Task
from loop_engine.reviewer import blocking, review_binding
from loop_engine.security import SafetyError, fingerprint
from loop_engine.state_store import StateStore

SOURCE = "refs/heads/loop/local-development"
TARGET = "refs/heads/main"


def atomic_payload(repository_id: str, before: str, after: str) -> dict[str, Any]:
    """Pure GraphQL input builder, not a transport or permission to send it."""
    if not all(re.fullmatch(r"[a-f0-9]{40}", x) and x != "0" * 40 for x in (before, after)):
        raise SafetyError("Existing exact commit IDs required")
    return {
        "repositoryId": repository_id,
        "refUpdates": [
            {"name": TARGET, "beforeOid": before, "afterOid": after, "force": False},
            {"name": SOURCE, "beforeOid": after, "afterOid": after, "force": False},
        ],
    }


class PromotionBackend(Protocol):
    offline: bool

    def refs(self) -> dict[str, str]: ...

    def checks(self, sha: str) -> dict[str, Any]: ...

    def update_refs(self, before: str, after: str) -> None:
        """Atomic source before=after=target AND main before/after, force=false."""
        ...


def verified_ci(snapshot: dict[str, Any], policy: dict[str, Any], sha: str) -> str:
    try:
        return _verified_ci(snapshot, policy, sha)
    except (KeyError, TypeError, AttributeError, ValueError):
        raise SafetyError("Required CI snapshot rejected") from None


def _verified_ci(snapshot: dict[str, Any], policy: dict[str, Any], sha: str) -> str:
    """Input contract requires a complete, provenance-bound latest-attempt snapshot."""
    if (
        set(snapshot) != {"complete", "repository_id", "sha", "branch", "runs"}
        or snapshot["complete"] is not True
        or snapshot["repository_id"] != policy["repository_id"]
        or snapshot["sha"] != sha
        or snapshot["branch"] != SOURCE.removeprefix("refs/heads/")
    ):
        raise SafetyError("Incomplete or mismatched CI provenance")
    runs = snapshot["runs"]
    if not isinstance(runs, list) or len(runs) != len(policy["workflows"]):
        raise SafetyError("Missing or ambiguous required workflows")
    for expected in policy["workflows"]:
        matches = [r for r in runs if r.get("path") == expected["path"]]
        if len(matches) != 1:
            raise SafetyError("Ambiguous required workflow identity")
        run = matches[0]
        if (
            set(run)
            != {
                "path",
                "digest",
                "id",
                "attempt",
                "latest_attempt",
                "event",
                "app_id",
                "sha",
                "jobs",
            }
            or run["digest"] != expected["digest"]
            or run["event"] != "push"
            or run["sha"] != sha
            or run["app_id"] != 15368
            or type(run["id"]) is not int
            or run["id"] <= 0
            or type(run["attempt"]) is not int
            or run["attempt"] < 1
            or run["attempt"] != run["latest_attempt"]
        ):
            raise SafetyError("Untrusted or stale required workflow attempt")
        jobs = run["jobs"]
        if not isinstance(jobs, list) or sorted(j["name"] for j in jobs) != sorted(
            expected["jobs"]
        ):
            raise SafetyError("Required jobs missing or duplicated")
        for job in jobs:
            if (
                set(job) != {"id", "name", "status", "conclusion", "sha"}
                or type(job["id"]) is not int
                or job["id"] <= 0
                or job["sha"] != sha
                or job["status"] != "completed"
                or job["conclusion"] != "success"
            ):
                raise SafetyError("Required exact-SHA CI has not passed")
    return fingerprint(snapshot)


class MainIntegration:
    def __init__(
        self, state: StateStore, git: GitManager, policy: dict[str, Any], backend: PromotionBackend
    ) -> None:
        if (
            backend.offline is not True
            or set(policy) != {"repository", "repository_id", "source", "target", "workflows"}
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", policy["repository"])
            or not isinstance(policy["repository_id"], str)
            or not policy["repository_id"]
            or policy["source"] != SOURCE
            or policy["target"] != TARGET
            or not policy["workflows"]
        ):
            raise SafetyError("Only reviewed offline promotion policy is supported")
        names: set[str] = set()
        for item in policy["workflows"]:
            if (
                set(item) != {"path", "digest", "jobs"}
                or item["path"]
                not in {
                    ".github/workflows/quality.yml",
                    ".github/workflows/loop-ci.yml",
                    ".github/workflows/pr-title.yml",
                }
                or item["path"] in names
                or not re.fullmatch(r"[a-f0-9]{64}", item["digest"])
                or not isinstance(item["jobs"], list)
                or not item["jobs"]
                or len(set(item["jobs"])) != len(item["jobs"])
            ):
                raise SafetyError("Invalid required CI policy")
            names.add(item["path"])
        required = {
            ".github/workflows/quality.yml": ["verify"],
            ".github/workflows/loop-ci.yml": [
                f"engine ({os}, {version})"
                for os in ("ubuntu-latest", "windows-latest")
                for version in ("3.11", "3.13")
            ],
            ".github/workflows/pr-title.yml": ["conventional-title"],
        }
        if {w["path"]: sorted(w["jobs"]) for w in policy["workflows"]} != {
            k: sorted(v) for k, v in required.items()
        }:
            raise SafetyError("All existing required checks must remain mandatory")
        self.state, self.git, self.backend = state, git, backend
        self.policy = json.loads(json.dumps(policy))
        with state.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS main_promotions(
                key TEXT PRIMARY KEY, target_ref TEXT NOT NULL, sha TEXT NOT NULL,
                phase TEXT NOT NULL, document TEXT NOT NULL)""")

    def _persist(self, key: str, phase: str, document: dict[str, Any]) -> None:
        with self.state.connect() as db:
            db.execute("PRAGMA synchronous=FULL")
            if db.execute("PRAGMA synchronous").fetchone()[0] != 2:
                raise SafetyError("Promotion durability unavailable")
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT * FROM main_promotions WHERE key=?", (key,)).fetchone()
                if row:
                    old = json.loads(row["document"])
                    immutable = {"sha", "before", "binding", "policy", "run", "deadline"}
                    if any(old[k] != document[k] for k in immutable):
                        raise SafetyError("Promotion identity changed")
                    allowed = {
                        "ci_pending": {"ci_verified"},
                        "ci_verified": {"update_reserved"},
                        "update_reserved": {"remote_confirmed"},
                        "remote_confirmed": {"recorded"},
                        "recorded": set(),
                    }
                    if phase not in allowed[row["phase"]]:
                        raise SafetyError("Promotion transition race")
                    db.execute(
                        "UPDATE main_promotions SET phase=?,document=? WHERE key=?",
                        (phase, self.state.encode(document), key),
                    )
                else:
                    if (
                        phase != "ci_pending"
                        or db.execute(
                            "SELECT 1 FROM main_promotions "
                            "WHERE target_ref=? AND phase!='recorded'",
                            (TARGET,),
                        ).fetchone()
                    ):
                        raise SafetyError("Unsettled promotion excludes a new operation")
                    db.execute(
                        "INSERT INTO main_promotions VALUES (?,?,?,?,?)",
                        (key, TARGET, document["sha"], phase, self.state.encode(document)),
                    )
                self.state._event(db, "main.promotion." + phase, None, {"key": key})
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def _evidence(self, task: Task, checkpoint: dict[str, Any], sha: str) -> None:
        if (
            not checkpoint.get("verified")
            or checkpoint.get("verification", {}).get("passed") is not True
            or checkpoint.get("binding")
            != review_binding(
                task,
                self.state.metadata("spec_hash"),
                checkpoint["snapshot"],
                checkpoint["verification"],
            )
            or any(
                checkpoint.get(k) != sha
                for k in ("committed_head", "integrated_head", "pushed_head")
            )
            or self.git.snapshot(task, self.git.root / checkpoint["workspace"])
            != checkpoint["snapshot"]
            or self.git._git(["rev-parse", sha + "^{tree}"])
            != checkpoint.get("local_commit_intent", {}).get("tree")
        ):
            raise SafetyError("Promotion source/QA identity differs")
        with self.state.connect() as db:
            rows = db.execute(
                "SELECT document FROM reviews WHERE task_id=? AND binding_hash=? "
                "ORDER BY created DESC",
                (task.id, checkpoint["binding"]),
            ).fetchall()
        if not rows or blocking(json.loads(rows[0][0])):
            raise SafetyError("No independent passing source review")

    def deliver(
        self, task: Task, checkpoint: dict[str, Any], *, cancelled: Callable[[], bool]
    ) -> dict[str, Any]:
        if cancelled():
            observed = self.reconcile(task, checkpoint)
            if observed is not None:
                return observed
            raise SafetyError("Cancelled promotion cannot create or send an update")
        sha = checkpoint.get("pushed_head", "")
        if not re.fullmatch(r"[a-f0-9]{40}", sha):
            raise SafetyError("Confirmed published commit required")
        self.git.operation_cancelled = cancelled
        self.git._safe_configuration()
        self._evidence(task, checkpoint, sha)
        key = fingerprint({"repository": self.policy["repository_id"], "ref": TARGET, "sha": sha})
        with self.state.connect() as db:
            row = db.execute("SELECT * FROM main_promotions WHERE key=?", (key,)).fetchone()
        refs = self.backend.refs()
        if set(refs) != {SOURCE, TARGET} or refs[SOURCE] != sha:
            raise SafetyError("Source/main references changed")
        if not row:
            budget = self.state.metadata("run_budget", {})
            if cancelled() or time.time() >= budget.get("deadline", 0):
                raise SafetyError("Promotion budget exhausted")
            before = refs[TARGET]
            self.git._git(["merge-base", "--is-ancestor", before, sha])
            aggregate = {
                "before": before,
                "sha": sha,
                "binding": checkpoint["binding"],
                "policy": fingerprint(self.policy),
            }
            if self.state.metadata("main_range_review") != {**aggregate, "passed": True}:
                raise SafetyError("Independent aggregate range review required")
            doc = {**aggregate, "run": budget["id"], "deadline": budget["deadline"]}
            self._persist(key, "ci_pending", doc)
            phase = "ci_pending"
        else:
            doc, phase = json.loads(row["document"]), row["phase"]
            if doc["binding"] != checkpoint["binding"] or doc["policy"] != fingerprint(self.policy):
                raise SafetyError("Promotion receipt binding changed")
        ci_evidence = self.backend.checks(sha)
        proof = verified_ci(ci_evidence, self.policy, sha)
        if phase in {"update_reserved", "remote_confirmed", "recorded"}:
            if refs[TARGET] != sha:
                raise SafetyError("Uncertain/changed main; do not replay update")
            if phase == "update_reserved":
                self._persist(key, "remote_confirmed", doc)
                phase = "remote_confirmed"
            if phase == "remote_confirmed":
                self._persist(key, "recorded", doc)
            return {"complete": True, "integrated_head": sha, "main_head": sha}
        if refs[TARGET] != doc["before"]:
            raise SafetyError("Main moved before promotion")
        if phase == "ci_pending":
            doc = {**doc, "ci": proof, "ci_evidence": ci_evidence}
            self._persist(key, "ci_verified", doc)
        if (
            cancelled()
            or time.time() >= doc["deadline"]
            or self.state.metadata("run_budget", {}).get("id") != doc["run"]
            or self.backend.refs() != {SOURCE: sha, TARGET: doc["before"]}
            or verified_ci(self.backend.checks(sha), self.policy, sha) != doc["ci"]
        ):
            raise SafetyError("Promotion changed or expired immediately before update")
        self._persist(key, "update_reserved", doc)
        if cancelled() or time.time() >= doc["deadline"]:
            raise SafetyError("Reserved update expired; no replay")
        self.backend.update_refs(doc["before"], sha)
        if self.backend.refs() != {SOURCE: sha, TARGET: sha}:
            raise SafetyError("Main update result is not confirmed")
        self._persist(key, "remote_confirmed", doc)
        self._persist(key, "recorded", doc)
        return {"complete": True, "integrated_head": sha, "main_head": sha}

    def reconcile(self, task: Task, checkpoint: dict[str, Any]) -> dict[str, Any] | None:
        """Only observe a previously reserved outcome; never call update_refs here.

        Bounded Git reads are permitted after cancellation. Restore the caller's
        mutation cancellation callback even if any observation fails.
        """
        sha = checkpoint.get("pushed_head")
        if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{40}", sha):
            raise SafetyError("No published SHA to reconcile")
        key = fingerprint({"repository": self.policy["repository_id"], "ref": TARGET, "sha": sha})
        with self.state.connect() as db:
            row = db.execute("SELECT * FROM main_promotions WHERE key=?", (key,)).fetchone()
        if row is None or row["phase"] not in {"update_reserved", "remote_confirmed", "recorded"}:
            return None
        doc = json.loads(row["document"])
        previous = self.git.operation_cancelled
        self.git.operation_cancelled = lambda: False
        try:
            self.git._safe_configuration()
            self._evidence(task, checkpoint, sha)
            if doc["policy"] != fingerprint(self.policy) or doc["binding"] != checkpoint["binding"]:
                raise SafetyError("Reserved promotion identity differs")
            if self.backend.refs() != {SOURCE: sha, TARGET: sha}:
                raise SafetyError("Uncertain main outcome; observational recovery cannot resend")
            verified_ci(doc["ci_evidence"], self.policy, sha)
            verified_ci(self.backend.checks(sha), self.policy, sha)
            phase = row["phase"]
            if phase == "update_reserved":
                self._persist(key, "remote_confirmed", doc)
                phase = "remote_confirmed"
            if phase == "remote_confirmed":
                self._persist(key, "recorded", doc)
            return {"complete": True, "integrated_head": sha, "main_head": sha}
        finally:
            self.git.operation_cancelled = previous
