"""Crash-conservative, globally serialized merge protocol (ADR-0007).

No live transport is enabled here. A production transport must prove exclusive
main/lock writers and independently bound review before it can be wired into the
Controller. Local locks, caller booleans and native queued auto-merge are not a
replacement for that proof. Tests use a shared remote compare-and-create model.
"""

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from loop_engine.security import SafetyError, fingerprint, reparse


@dataclass(frozen=True)
class MergeBinding:
    repository: str
    pull: int
    head: str
    base: str
    policy: str
    review: str
    verification: str

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository)
            or any(part in {".", ".."} for part in self.repository.split("/"))
            or type(self.pull) is not int
            or self.pull <= 0
            or any(not re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (self.head, self.base))
            or any(
                not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in (self.policy, self.review, self.verification)
            )
        ):
            raise SafetyError("Invalid exact merge binding")

    @property
    def identity(self) -> str:
        return fingerprint(asdict(self))


class BrokerTransport(Protocol):
    """Trusted, pinned service adapter; never supplied by a worker/PR.

    acquire is a GLOBAL atomic create, not read-then-write. No expiry/stealing.
    release is owner checked; unknown results must retain exclusivity.
    validate re-reads ALL remote policy/PR/check/review/conversation evidence and
    matches the installation, exclusive-writer attestation, source identities,
    exact binding, risk/allowlist, standing authority and pending decisions.
    It may not accept a caller's assertion that any gate passed.
    """

    def acquire(self, owner: str, binding: MergeBinding) -> None: ...
    def owns(self, owner: str, binding: MergeBinding) -> bool: ...
    def validate(self, binding: MergeBinding) -> None: ...
    def merge(self, binding: MergeBinding) -> str: ...
    def observed_merge(self, binding: MergeBinding) -> str | None: ...
    def release(self, owner: str, binding: MergeBinding) -> None: ...


class BrokerJournal:
    """Durable mutation intent precedes every remote write; no credentials."""

    def __init__(self, path: Path) -> None:
        path = path.absolute()
        self._check_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS broker_attempts (
                    id TEXT PRIMARY KEY, binding TEXT NOT NULL,
                    owner TEXT UNIQUE NOT NULL, phase TEXT NOT NULL,
                    merge_sha TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS broker_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    attempt TEXT NOT NULL, phase TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS broker_no_update
                    BEFORE UPDATE ON broker_events
                    BEGIN SELECT RAISE(ABORT,'Append-only journal'); END;
                CREATE TRIGGER IF NOT EXISTS broker_no_delete
                    BEFORE DELETE ON broker_events
                    BEGIN SELECT RAISE(ABORT,'Append-only journal'); END;
            """)

    @staticmethod
    def _check_path(path: Path) -> None:
        # SQLite opens journal/WAL sidecars itself. A linked ancestor or an
        # existing linked sidecar must not redirect those writes either.
        candidates = [
            path,
            *path.parents,
            *(path.with_name(path.name + suffix) for suffix in ("-journal", "-wal", "-shm")),
        ]
        if any(reparse(candidate) for candidate in candidates):
            raise SafetyError("Unsafe broker journal path or sidecar")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self._check_path(self.path)
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def begin(self, binding: MergeBinding) -> str:
        owner = uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # A new process may observe an old intent but cannot overwrite it.
            if db.execute(
                "SELECT 1 FROM broker_attempts WHERE id=?", (binding.identity,)
            ).fetchone():
                raise SafetyError("Existing merge intent requires reconciliation, not replay")
            db.execute(
                "INSERT INTO broker_attempts(id,binding,owner,phase) VALUES (?,?,?,?)",
                (binding.identity, json.dumps(asdict(binding)), owner, "acquiring"),
            )
            db.execute(
                "INSERT INTO broker_events(attempt,phase) VALUES (?,?)",
                (binding.identity, "acquiring"),
            )
        return owner

    def read(self, binding: MergeBinding) -> dict[str, str]:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM broker_attempts WHERE id=?", (binding.identity,)
            ).fetchone()
            if row is None or json.loads(row["binding"]) != asdict(binding):
                raise SafetyError("Unknown broker intent")
            return dict(row)

    def move(self, binding: MergeBinding, old: str, new: str, merge_sha: str = "") -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "UPDATE broker_attempts SET phase=?,merge_sha=? WHERE id=? AND phase=?",
                (new, merge_sha, binding.identity, old),
            ).rowcount
            if count != 1:
                raise SafetyError("Broker intent already claimed or changed")
            db.execute(
                "INSERT INTO broker_events(attempt,phase) VALUES (?,?)", (binding.identity, new)
            )


class MergeBroker:
    """Never releases an acquiring/merging intent after an uncertain response.

    A rejected preflight also retains the lock: an explicit recovery protocol
    must establish no write was sent before releasing it. Conservative stopping
    is preferable to guessing about a crashed predecessor. No TTL is consulted.
    """

    def __init__(self, journal: BrokerJournal, remote: BrokerTransport) -> None:
        self.journal, self.remote = journal, remote

    @staticmethod
    def _sha(value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise SafetyError("Invalid observed merge commit")
        return value

    def execute(self, binding: MergeBinding) -> str:
        owner = self.journal.begin(binding)
        self.remote.acquire(owner, binding)
        self.journal.move(binding, "acquiring", "locked")
        if not self.remote.owns(owner, binding):
            raise SafetyError("Global lock ownership changed")
        self.remote.validate(binding)
        self.journal.move(binding, "locked", "merging")
        # Once this intent is durable, no retry/expiry may release the lock
        # unless the exact merge is conclusively observed.
        sha = self._sha(self.remote.merge(binding))
        observed = self.remote.observed_merge(binding)
        if observed != sha:
            raise SafetyError("Merge response not reconciled; exclusivity retained")
        self.journal.move(binding, "merging", "merged", sha)
        return self._release(binding, owner, sha)

    def _release(self, binding: MergeBinding, owner: str, sha: str) -> str:
        if not self.remote.owns(owner, binding):
            raise SafetyError("Lock absent/changed; operator reconciliation required")
        # Validation of a merged result must establish actor, original H/B,
        # squash SHA and ancestry, not just merged=true for a PR number.
        if self.remote.observed_merge(binding) != sha:
            raise SafetyError("Merge observation changed")
        self.journal.move(binding, "merged", "releasing", sha)
        self.remote.release(owner, binding)
        self.journal.move(binding, "releasing", "released", sha)
        return sha

    def reconcile(self, binding: MergeBinding) -> str:
        row = self.journal.read(binding)
        if row["phase"] == "released":
            return self._sha(row["merge_sha"])
        if row["phase"] not in {"merging", "merged"}:
            raise SafetyError("No automatic recovery proof; retain global lock")
        if not self.remote.owns(row["owner"], binding):
            raise SafetyError("Global lock ownership unproven")
        observed = self.remote.observed_merge(binding)
        if observed is None:
            raise SafetyError("Remote write may still complete; do not release or retry")
        sha = self._sha(observed)
        if row["phase"] == "merging":
            self.journal.move(binding, "merging", "merged", sha)
        elif row["merge_sha"] != sha:
            raise SafetyError("Recorded merge SHA changed")
        return self._release(binding, row["owner"], sha)
