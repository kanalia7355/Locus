"""One-send durable journal in the existing StateStore; no model content."""

import json
import sqlite3
import time
from typing import Any
from uuid import uuid4

from loop_engine.security import SafetyError, fingerprint
from loop_engine.state_store import StateStore

STEPS = (
    "prepared",
    "launch_reserved",
    "request_validated",
    "upstream_reserved",
    "terminal_validated",
    "cli_validated",
    "completed",
)


class InvocationJournal:
    def __init__(self, state: StateStore) -> None:
        self.state = state
        with state.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS model_invocations (
                id TEXT PRIMARY KEY, owner_key TEXT UNIQUE NOT NULL,
                owner TEXT NOT NULL, artifact TEXT NOT NULL, phase TEXT NOT NULL,
                deadline REAL NOT NULL, created REAL NOT NULL, result_ref TEXT
            )""")

    def _begin(self, db: sqlite3.Connection) -> None:
        db.execute("PRAGMA synchronous=FULL")
        if db.execute("PRAGMA synchronous").fetchone()[0] != 2:
            raise SafetyError("Durable model reservation unavailable")
        db.execute("BEGIN IMMEDIATE")

    def claim(self, owner: dict[str, Any], artifact: str, deadline: float) -> str:
        if (
            set(owner) != {"role", "schema", "owner_id", "spec", "binding", "attempt"}
            or not isinstance(owner.get("role"), str)
            or not isinstance(owner.get("schema"), str)
            or (owner["role"], owner["schema"])
            not in {
                ("worker", "proposal"),
                ("reviewer", "review"),
                ("evaluator", "evaluation"),
                ("trial", "trial"),
            }
            or any(
                not isinstance(owner[k], str) or not 0 < len(owner[k]) <= 256
                for k in ("owner_id", "spec", "binding")
            )
            or type(owner["attempt"]) is not int
            or not 1 <= owner["attempt"] <= 20
            or (owner["role"] != "evaluator" and owner["attempt"] > 3)
            or not time.time() < deadline <= time.time() + 1800
        ):
            raise SafetyError("Bounded model owner required")
        with self.state.connect() as db:
            self._begin(db)
            try:
                if owner["role"] == "trial":
                    if (
                        not db.execute(
                            "SELECT 1 FROM sqlite_master WHERE name='c_min_trials'"
                        ).fetchone()
                        or not db.execute(
                            "SELECT 1 FROM c_min_trials WHERE slot=1 "
                            "AND owner_key=? AND phase='reserved'",
                            (fingerprint(owner),),
                        ).fetchone()
                    ):
                        raise SafetyError("Dedicated one-shot trial slot required")
                existing = db.execute(
                    "SELECT * FROM model_invocations WHERE owner_key=?", (fingerprint(owner),)
                ).fetchone()
                if existing is not None:
                    others = db.execute(
                        "SELECT 1 FROM model_invocations WHERE phase!='completed' AND id!=?",
                        (existing["id"],),
                    ).fetchone()
                    if (
                        existing["phase"] != "prepared"
                        or others is not None
                        or existing["artifact"] != artifact
                        or existing["deadline"] <= time.time()
                    ):
                        raise SafetyError("Existing model reservation requires reconciliation")
                    db.commit()
                    return str(existing["id"])
                if db.execute(
                    "SELECT 1 FROM model_invocations WHERE phase != 'completed'"
                ).fetchone():
                    raise SafetyError("Unsettled model invocation; reconcile without replay")
                identifier = uuid4().hex
                db.execute(
                    "INSERT INTO model_invocations VALUES (?,?,?,?,?,?,?,NULL)",
                    (
                        identifier,
                        fingerprint(owner),
                        self.state.encode(owner),
                        artifact,
                        "prepared",
                        deadline,
                        time.time(),
                    ),
                )
                self.state._event(db, "model.reserved", None, {"id": identifier})
                db.commit()
                return identifier
            except (sqlite3.IntegrityError, ValueError):
                db.rollback()
                raise SafetyError("Model owner already reserved; no replay") from None

    def advance(self, identifier: str, before: str, after: str) -> None:
        if (
            before not in STEPS
            or after not in STEPS
            or STEPS.index(after) != STEPS.index(before) + 1
        ):
            raise SafetyError("Invalid model reservation transition")
        if after == "completed":
            raise SafetyError("Caller result acknowledgement required")
        with self.state.connect() as db:
            self._begin(db)
            changed = db.execute(
                "UPDATE model_invocations SET phase=? WHERE id=? AND phase=? AND deadline>?",
                (after, identifier, before, time.time()),
            ).rowcount
            if changed != 1:
                db.rollback()
                raise SafetyError("Model reservation expired/reused")
            self.state._event(db, "model.phase", None, {"id": identifier, "phase": after})
            db.commit()

    def hold(self, identifier: str) -> None:
        with self.state.transaction() as db:
            db.execute(
                "UPDATE model_invocations SET phase='held' WHERE id=? AND phase!='completed'",
                (identifier,),
            )
            self.state._event(db, "model.held", None, {"id": identifier})

    def bind_trial_input(self, identifier: str, binding: dict[str, Any]) -> None:
        """Atomically consume all generated aliases with request_validated, once."""
        with self.state.connect() as db:
            self._begin(db)
            try:
                row = db.execute(
                    "SELECT * FROM model_invocations WHERE id=?", (identifier,)
                ).fetchone()
                if (
                    row is None
                    or json.loads(row["owner"])["role"] != "trial"
                    or row["phase"] != "launch_reserved"
                    or time.time() >= row["deadline"]
                    or binding["expires"] != row["deadline"]
                    or set(binding)
                    != {
                        "contract",
                        "request",
                        "aliases",
                        "values",
                        "pid",
                        "creation",
                        "utc",
                        "monotonic",
                        "expires",
                    }
                ):
                    raise SafetyError("Trial input reservation identity differs")
                if not db.execute(
                    "SELECT 1 FROM c_min_trials WHERE slot=1 AND owner_key=? AND phase='reserved'",
                    (row["owner_key"],),
                ).fetchone():
                    raise SafetyError("Trial lifetime slot changed")
                db.execute(
                    "CREATE TABLE IF NOT EXISTS trial_input_bindings ("
                    "invocation TEXT PRIMARY KEY REFERENCES model_invocations(id), "
                    "document TEXT NOT NULL)"
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS trial_input_aliases (identity TEXT PRIMARY KEY, "
                    "invocation TEXT NOT NULL REFERENCES model_invocations(id))"
                )
                db.execute(
                    "INSERT INTO trial_input_bindings VALUES (?,?)",
                    (identifier, self.state.encode(binding)),
                )
                for alias in binding["aliases"]:
                    db.execute("INSERT INTO trial_input_aliases VALUES (?,?)", (alias, identifier))
                db.execute(
                    "UPDATE model_invocations SET phase='request_validated' WHERE id=?",
                    (identifier,),
                )
                self.state._event(
                    db, "model.phase", None, {"id": identifier, "phase": "request_validated"}
                )
                db.commit()
            except sqlite3.IntegrityError:
                db.rollback()
                raise SafetyError("Generated trial value already reserved; no replay") from None
            except BaseException:
                db.rollback()
                raise

    def trial_binding(self, identifier: str, phase: str) -> dict[str, Any]:
        with self.state.connect() as db:
            row = db.execute(
                "SELECT b.document FROM trial_input_bindings b JOIN model_invocations m "
                "ON b.invocation=m.id JOIN c_min_trials t ON t.owner_key=m.owner_key "
                "WHERE m.id=? AND m.phase=? AND t.slot=1 AND t.phase='reserved'",
                (identifier, phase),
            ).fetchone()
            if row is None:
                raise SafetyError("Durable trial input evidence missing")
            return dict(json.loads(row["document"]))

    def acknowledge(self, identifier: str) -> None:
        with self.state.connect() as db:
            self._begin(db)
            row = db.execute("SELECT * FROM model_invocations WHERE id=?", (identifier,)).fetchone()
            if row is None or row["phase"] not in {"cli_validated", "completed"}:
                db.rollback()
                raise SafetyError("No validated invocation awaiting caller result")
            owner = json.loads(row["owner"])
            if owner["role"] == "worker":
                result = db.execute(
                    "SELECT id FROM executions WHERE id=? AND status='returned' AND finished>=?",
                    (owner["owner_id"], row["created"]),
                ).fetchone()
            elif owner["role"] == "reviewer":
                result = db.execute(
                    "SELECT id FROM reviews WHERE binding_hash=? AND created>=?",
                    (owner["binding"], row["created"]),
                ).fetchone()
            elif owner["role"] == "trial":
                result = db.execute(
                    "SELECT owner_key FROM c_min_trials WHERE slot=1 AND owner_key=? "
                    "AND phase IN ('validated','completed')",
                    (fingerprint(owner),),
                ).fetchone()
            else:
                result = db.execute(
                    "SELECT binding FROM development_evaluations WHERE binding=? AND created>=?",
                    (owner["binding"], row["created"]),
                ).fetchone()
            if result is None:
                db.rollback()
                raise SafetyError("Authoritative caller result missing; no replay")
            if row["phase"] == "completed":
                if row["result_ref"] != str(result[0]):
                    raise SafetyError("Completed caller result binding changed")
                db.commit()
                return
            db.execute(
                "UPDATE model_invocations SET phase='completed',result_ref=? WHERE id=?",
                (str(result[0]), identifier),
            )
            if owner["role"] == "trial":
                trial = db.execute("SELECT document FROM c_min_trials WHERE slot=1").fetchone()
                proof = json.loads(trial[0])
                if proof.get("invocation") != identifier:
                    raise SafetyError("Trial result identity differs")
                proof["passed"] = True
                db.execute(
                    "UPDATE c_min_trials SET phase='completed',document=? WHERE slot=1",
                    (self.state.encode(proof),),
                )
            self.state._event(db, "model.completed", None, {"id": identifier})
            db.commit()
