"""Explicitly approved, resumable specification/policy migration, never reset.

Each old document is preserved before replacement. Durable applying intent
precedes filesystem changes; SQLite changes its active snapshot only after all
new files are observed. Unknown intermediate content requires human recovery.
"""

import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from loop_engine.approval import ApprovalQueue
from loop_engine.config import load
from loop_engine.locking import ProjectLock
from loop_engine.planning import SOURCE_FILES, source_snapshot
from loop_engine.schemas import validate
from loop_engine.security import SafetyError, fingerprint, within
from loop_engine.state_store import StateStore


class PolicyMigration:
    def __init__(self, root: Path, state: StateStore) -> None:
        self.root, self.state = root, state
        with state.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS policy_migrations (
                id TEXT PRIMARY KEY, target TEXT UNIQUE NOT NULL, document TEXT NOT NULL,
                phase TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS migration_files (
                migration TEXT NOT NULL, name TEXT NOT NULL,
                capture TEXT NOT NULL, staged TEXT NOT NULL,
                PRIMARY KEY(migration,name)
            )""")

    def _idle(self) -> None:
        if self.state.metadata("control") not in {"paused", "stopped"}:
            raise SafetyError("Stop the Controller before migrating policy")
        with self.state.connect() as db:
            if db.execute("SELECT 1 FROM executions WHERE status='running'").fetchone():
                raise SafetyError("An executor is unsettled; do not migrate")
            if db.execute(
                "SELECT 1 FROM tasks WHERE status IN ('running','verifying','reviewing')"
            ).fetchone():
                raise SafetyError("An active task requires reconciliation before migration")
        if self.state.metadata("orphan_uncertainty", False):
            raise SafetyError("Uncertain executor lifetime prevents migration")

    def prepare(self, proposed: dict[str, Any]) -> dict[str, str]:
        if set(proposed) != {*SOURCE_FILES, "policy"}:
            raise SafetyError("Complete exact source snapshot required")
        validate("config", proposed["policy"])
        if proposed["policy"]["github"]["base"] != "main":
            raise SafetyError("This integration migration targets main only")
        if len(yaml.safe_dump(proposed["policy"]).encode()) > 65536:
            raise SafetyError("Proposed policy exceeds the runtime configuration limit")
        if any(
            not isinstance(proposed[name], str) or len(proposed[name].encode()) > 64000
            for name in SOURCE_FILES
        ):
            raise SafetyError("Invalid migration specification document")
        if not proposed["goal.md"].strip():
            raise SafetyError("Migration cannot erase the Goal")
        with ProjectLock(within(self.root, ".loop/runtime/controller.lock")):
            self._idle()
            old = source_snapshot(self.root)
            if fingerprint(old) != self.state.metadata("spec_hash"):
                raise SafetyError("Current specification is not the frozen source")
            if proposed["acceptance.md"] != old["acceptance.md"]:
                raise SafetyError("This migration cannot change Goal acceptance")
            for section in ("loop", "security", "verification", "qa", "approval"):
                if proposed["policy"][section] != old["policy"][section]:
                    raise SafetyError("Migration cannot weaken or replace execution/QA limits")
            for key in ("repository", "remote", "required_checks", "protect_default_branch"):
                if proposed["policy"]["github"][key] != old["policy"]["github"][key]:
                    raise SafetyError("Migration cannot change repository or required CI")
            for key in ("max_cycles_per_run", "stagnation_limit", "evaluation_timeout_minutes"):
                if proposed["policy"]["development"][key] != old["policy"]["development"][key]:
                    raise SafetyError("Migration cannot change Development limits")
            if proposed == old:
                raise SafetyError("No policy migration needed")
            document = {"protocol": "locus-policy-migration-v1", "old": old, "new": proposed}
            encoded = self.state.encode(document)
            target = fingerprint(document)
            with self.state.transaction() as db:
                existing = db.execute(
                    "SELECT id FROM policy_migrations WHERE target=?", (target,)
                ).fetchone()
                identity = str(existing[0]) if existing else uuid4().hex
                if not existing:
                    db.execute(
                        "INSERT INTO policy_migrations VALUES (?,?,?,'prepared')",
                        (identity, target, encoded),
                    )
                    self.state._event(
                        db,
                        "policy.migration_prepared",
                        None,
                        {"id": identity, "target_hash": target},
                    )
            decision = ApprovalQueue(self.state).request(
                None,
                "scope",
                target,
                "Approve this exact versioned Goal/policy migration; acceptance, task attempts, "
                "budgets, decisions and evidence stay unchanged. Review every source diff.",
                "high",
            )
            return {
                "id": identity,
                "target_hash": target,
                "decision_id": decision,
                "new_specification_hash": fingerprint(proposed),
            }

    def _files(self, snapshot: dict[str, Any]) -> dict[str, str]:
        return {
            **{name: snapshot[name] for name in SOURCE_FILES},
            "config.yaml": yaml.safe_dump(snapshot["policy"], sort_keys=False),
        }

    def apply(self, identity: str) -> str:
        with ProjectLock(within(self.root, ".loop/runtime/controller.lock")):
            return self._apply(identity)

    def _apply(self, identity: str) -> str:
        self._idle()
        with self.state.connect() as db:
            row = db.execute("SELECT * FROM policy_migrations WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise SafetyError("Unknown policy migration")
        document = json.loads(row["document"])
        if fingerprint(document) != row["target"]:
            raise SafetyError("Migration proposal identity changed")
        if ApprovalQueue(self.state).status(None, "scope", row["target"]) != "approved":
            raise SafetyError("Exact operator approval is required before replacing source files")
        old, new = document["old"], document["new"]
        new_hash = fingerprint(new)
        if row["phase"] == "applied":
            if source_snapshot(self.root) != new or self.state.metadata("spec_hash") != new_hash:
                raise SafetyError("Applied migration no longer matches current state")
            return new_hash
        if row["phase"] not in {"prepared", "applying"}:
            raise SafetyError("Unknown migration phase")
        if self.state.metadata("spec_hash") != fingerprint(old):
            raise SafetyError("Frozen specification changed before migration")
        if row["phase"] == "prepared" and source_snapshot(self.root) != old:
            raise SafetyError("Source changed before backup; migration not started")
        old_files, new_files = self._files(old), self._files(new)
        # Preserve actual old bytes, including the original YAML presentation.
        # Backups are created once and are never replaced on recovery.
        for name in old_files:
            path = within(self.root, ".loop/" + name)
            current_path = path
            if not path.exists() and row["phase"] == "applying":
                with self.state.connect() as db:
                    moved = db.execute(
                        "SELECT capture FROM migration_files WHERE migration=? AND name=?",
                        (identity, name),
                    ).fetchone()
                if moved is None:
                    raise SafetyError("Missing source without a capture intent")
                current_path = within(self.root, moved["capture"])
            current_bytes = current_path.read_bytes()
            current = current_bytes.decode("utf-8").replace("\r\n", "\n")
            backup = within(self.root, f".loop/runtime/migrations/{identity}/old/{name}")
            if not backup.exists():
                if row["phase"] != "prepared":
                    raise SafetyError("Migration backup missing during recovery")
                backup.parent.mkdir(parents=True, exist_ok=True)
                staged_backup = backup.with_name(name + ".staging-" + uuid4().hex)
                with staged_backup.open("xb") as stream:
                    stream.write(current_bytes)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Atomic no-replace publication; interrupted staging files are
                # retained, never mistaken for the complete original backup.
                os.link(staged_backup, backup)
            original = backup.read_text(encoding="utf-8")
            if (
                load(backup) != old["policy"]
                if name == "config.yaml"
                else original != old_files[name]
            ):
                raise SafetyError("Original migration backup identity changed")
            if name == "config.yaml":
                current_value = load(current_path)
                known = current_value in (old["policy"], new["policy"])
            else:
                known = current in (old_files[name], new_files[name])
            if not known:
                raise SafetyError("Unknown intermediate source content; preserve and reconcile")
        with self.state.transaction() as db:
            db.execute("UPDATE policy_migrations SET phase='applying' WHERE id=?", (identity,))
            db.execute(
                "INSERT INTO metadata VALUES ('policy_migration_pending',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (self.state.encode(identity),),
            )
            self.state._event(db, "policy.migration_applying", None, {"id": identity})
        for name, content in new_files.items():
            path = within(self.root, ".loop/" + name)
            with self.state.connect() as db:
                started = db.execute(
                    "SELECT 1 FROM migration_files WHERE migration=? AND name=?", (identity, name)
                ).fetchone()
            if not started and path.exists() and path.read_text(encoding="utf-8") == content:
                continue
            self._install(identity, name, content)
        if source_snapshot(self.root) != new:
            raise SafetyError("New source snapshot not observed; retain migration intent")
        with self.state.transaction() as db:
            if self.state.metadata("spec_hash") != fingerprint(old):
                raise SafetyError("Concurrent specification mutation")
            existing = db.execute("SELECT id FROM goals WHERE spec_hash=?", (new_hash,)).fetchall()
            if len(existing) > 1:
                raise SafetyError("Ambiguous Goal version requires reconciliation")
            if not existing:
                db.execute(
                    "INSERT INTO goals VALUES (?,?,?,?)",
                    (
                        uuid4().hex,
                        self.state.encode({"goal": new["goal.md"], "migration": identity}),
                        new_hash,
                        time.time(),
                    ),
                )
            for key, value in {
                "spec_snapshot": new,
                "spec_hash": new_hash,
                "policy_migration_pending": None,
            }.items():
                db.execute(
                    "INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) "
                    "DO UPDATE SET value=excluded.value",
                    (key, self.state.encode(value)),
                )
            db.execute("UPDATE policy_migrations SET phase='applied' WHERE id=?", (identity,))
            self.state._event(
                db,
                "policy.migration_applied",
                None,
                {"id": identity, "old": fingerprint(old), "new": new_hash},
            )
        return new_hash

    def _install(self, identity: str, name: str, content: str) -> None:
        with self.state.transaction() as db:
            row = db.execute(
                "SELECT * FROM migration_files WHERE migration=? AND name=?", (identity, name)
            ).fetchone()
            if row is None:
                prefix = f".loop/runtime/migrations/{identity}/"
                db.execute(
                    "INSERT INTO migration_files VALUES (?,?,?,?)",
                    (
                        identity,
                        name,
                        prefix + "captured/" + uuid4().hex,
                        prefix + "new/" + uuid4().hex,
                    ),
                )
                row = db.execute(
                    "SELECT * FROM migration_files WHERE migration=? AND name=?", (identity, name)
                ).fetchone()
        assert row is not None
        target = within(self.root, ".loop/" + name)
        capture = within(self.root, row["capture"])
        staged = within(self.root, row["staged"])
        backup = within(self.root, f".loop/runtime/migrations/{identity}/old/{name}")
        if not capture.exists():
            capture.parent.mkdir(parents=True, exist_ok=True)
            # Rename captures the exact destination, including a racing edit.
            # It never discards that file. A newly recreated target is protected
            # by the atomic no-replace link used below, not read-then-overwrite.
            target = within(self.root, ".loop/" + name)
            os.rename(target, capture)
        capture = within(self.root, row["capture"])
        captured = capture.read_bytes()
        wanted = content.encode("utf-8")
        if captured not in (backup.read_bytes(), wanted):
            if not target.exists():
                # Restore visibility without overwriting a concurrent editor's
                # recreated target; the captured data is retained in either case.
                try:
                    os.link(capture, target)
                except FileExistsError:
                    pass
            raise SafetyError("Concurrent user edit captured and preserved; reconcile manually")
        if target.exists():
            if target.read_bytes() == wanted:
                return
            raise SafetyError("Target recreated during migration; preserve and reconcile")
        staged.parent.mkdir(parents=True, exist_ok=True)
        if staged.exists():
            if staged.read_bytes() != wanted:
                raise SafetyError("Incomplete staging data retained; reconcile manually")
        else:
            temporary = within(self.root, row["staged"] + ".temporary-" + uuid4().hex)
            with temporary.open("xb") as stream:
                stream.write(wanted)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, staged)
        # os.link fails atomically if an editor recreated the destination. No
        # existing destination is ever overwritten, on Windows or POSIX.
        target = within(self.root, ".loop/" + name)
        os.link(staged, target)
