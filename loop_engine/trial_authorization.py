"""Stable single-trial requests; only an owner decision starts the execution clock."""

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from loop_engine.security import SafetyError, fingerprint, reparse
from loop_engine.state_store import StateStore

VERSION = "c-min-trial-owner-activation-v1"
QUESTION = "Approve this exact owner-activated single C-min trial"
REGISTRATIONS = {
    "c_min_auth_profile",
    "c_min_trial_history",
    "c_min_trial_offline_review",
    "c_min_trial_input_contract",
}
FIELDS = {
    "purpose",
    "runtime",
    "artifact",
    "workspace",
    "plan",
    "input_hash",
    "profile",
    "history",
    "max_calls",
    "refresh",
    "offline_review",
    "input_version",
}


def require(value: bool, message: str) -> None:
    if not value:
        raise SafetyError(message)


def validate_request(request: Any) -> None:
    from loop_engine.c_min_trial import PLAN_HASH, SCHEMA
    from loop_engine.trial_input_binding import VERSION3, contract

    require(
        isinstance(request, dict)
        and set(request) == {"version", "execution_seconds", "permit", "registrations"},
        "Exact stable trial request required",
    )
    require(
        request["version"] == VERSION
        and type(request["execution_seconds"]) is int
        and request["execution_seconds"] == 180,
        "Fixed trial execution cap required",
    )
    permit, registrations = request["permit"], request["registrations"]
    require(isinstance(permit, dict) and set(permit) == FIELDS, "Stable trial permit fields differ")
    require(
        all(
            isinstance(permit[k], str) and 0 < len(permit[k]) <= 4096
            for k in FIELDS - {"max_calls"}
        ),
        "Stable trial strings differ",
    )
    require(
        permit["purpose"] == "c-min-single-validation"
        and permit["plan"] == PLAN_HASH
        and type(permit["max_calls"]) is int
        and permit["max_calls"] == 1
        and permit["refresh"] == "official-existing-secure-backend-only"
        and permit["input_version"] == VERSION3,
        "Stable trial operation changed",
    )
    require(
        isinstance(registrations, dict) and set(registrations) == REGISTRATIONS,
        "Exact trial registrations required",
    )
    require(
        fingerprint(registrations["c_min_auth_profile"]) == permit["profile"],
        "Trial profile changed",
    )
    require(
        registrations["c_min_trial_history"]
        == {
            "binding": permit["history"],
            "reconciled": True,
            "additional_slots": 1,
        },
        "Historical holds/additional single slot changed",
    )
    require(
        registrations["c_min_trial_offline_review"]
        == {
            "binding": permit["offline_review"],
            "runtime": permit["runtime"],
            "passed": True,
        },
        "Independent review binding changed",
    )
    specification = contract(registrations["c_min_trial_input_contract"])
    require(fingerprint(specification) == permit["input_hash"], "Trial input contract changed")
    launch = specification["launch"]
    require(
        set(launch)
        == {
            "runtime",
            "artifact",
            "workspace",
            "profile",
            "history",
            "model",
            "destination",
            "argv",
            "schema",
        }
        and all(
            launch[k] == permit[k]
            for k in ("runtime", "artifact", "workspace", "profile", "history")
        )
        and launch["model"] == "gpt-6.1-sol"
        and launch["destination"] == "https://chatgpt.com/backend-api/codex/responses"
        and launch["schema"] == fingerprint(SCHEMA),
        "Exact trial launch context changed",
    )


def validate_context(root: Path, request: dict[str, Any]) -> None:
    """Read-only credential metadata/settings validation, never a credential CLI."""
    import tomllib

    from loop_engine.c_min_runtime import verify_profile
    from loop_engine.c_min_trial import argv_for
    from loop_engine.docker_boundary import image_audit_evidence
    from loop_engine.runtime_diagnostics import runtime_identity
    from loop_engine.toolless_boundary import ToollessBoundary

    validate_request(request)
    permit, profile = request["permit"], request["registrations"]["c_min_auth_profile"]
    require(
        permit["runtime"] == runtime_identity(root), "Trial runtime changed while awaiting approval"
    )

    class Candidate:
        def metadata(self, key: str) -> Any:
            require(key == "c_min_auth_profile", "Unexpected candidate metadata")
            return profile

    verify_profile(Candidate())  # type: ignore[arg-type]
    workspace = root / ".loop/runtime/probes/c-min-single-validation"
    require(
        permit["workspace"] == str(workspace.resolve())
        and not any(reparse(p) for p in (workspace, *workspace.parents)),
        "Trial workspace changed",
    )
    require(
        workspace.is_dir()
        and {p.name for p in workspace.iterdir()} == {"synthetic.txt"}
        and not reparse(workspace / "synthetic.txt")
        and (workspace / "synthetic.txt").read_bytes() == b"C_MIN_SYNTHETIC_ONLY\n",
        "Synthetic trial workspace changed",
    )
    qa = json.loads((root / ".loop/runtime/qa-image.json").read_text())
    require(image_audit_evidence(root, qa["image_id"], root), "Current trial QA audit required")
    settings = tomllib.loads((Path(profile["home"]) / "config.toml").read_text(encoding="utf-8"))
    boundary = ToollessBoundary(
        root,
        qa["image_id"],
        list(settings.get("mcp_servers", {})),
        notification_policy=profile.get("notification_policy"),
        catalog_policy=profile.get("model_catalog"),
    )
    require(
        boundary._binding(workspace) == permit["artifact"],
        "Trial artifact changed while awaiting approval",
    )
    require(
        request["registrations"]["c_min_trial_input_contract"]["launch"]["argv"]
        == argv_for(root, workspace),
        "Trial argv changed",
    )


def settled(db: Any) -> None:
    require(
        not db.execute("SELECT 1 FROM executions WHERE status='running'").fetchone(),
        "Unsettled execution",
    )
    queries = {
        "c_min_trials": "SELECT 1 FROM c_min_trials",
        "c_min_trial_activations": "SELECT 1 FROM c_min_trial_activations",
    }
    for table, query in queries.items():
        if db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
            require(
                not db.execute(query).fetchone(),
                "Trial authorization/slot already used; never renew",
            )
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='model_invocations'").fetchone():
        require(
            not db.execute("SELECT 1 FROM model_invocations WHERE phase!='completed'").fetchone(),
            "Unsettled model invocation; never replay",
        )


def prepare(root: Path, state: StateStore, request: dict[str, Any]) -> str:
    from loop_engine.approval import ApprovalQueue

    validate_context(root, request)
    with state.transaction() as db:
        settled(db)
        require(
            state.metadata("control") == "stopped"
            and not state.metadata("orphan_uncertainty", False),
            "Stopped settled Controller required",
        )
        require(
            state.metadata("c_min_trial_permit") is None
            and state.metadata("c_min_live_permit") is None
            and state.metadata("c_min_run_proposal") is None,
            "Existing permission requires explicit reconciliation",
        )
        existing = state.metadata("c_min_trial_request")
        require(
            existing is None or existing == request,
            "Different existing trial request requires explicit reconciliation",
        )
        db.execute(
            "INSERT INTO metadata VALUES ('c_min_trial_request',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (state.encode(request),),
        )
    return ApprovalQueue(state).request(
        None,
        "scope",
        fingerprint(request),
        QUESTION + ": fixed credentials/refresh, input and one slot; 180 seconds begin "
        "only on the recorded owner approval?",
        "high",
    )


def activate(state: StateStore, db: Any, row: Any, approved_at: float) -> None:
    """Called only inside ApprovalQueue.resolve's owner-decision transaction."""
    require(row["task_id"] is None and row["category"] == "scope", "Trial owner scope differs")
    request = state.metadata("c_min_trial_request")
    validate_request(request)
    require(fingerprint(request) == row["target_hash"], "Pending trial request changed")
    require(
        math.isfinite(approved_at) and approved_at >= row["created"] > 0,
        "Finite non-reversed approval timestamp required",
    )
    validate_context(state.path.parents[2], request)
    settled(db)
    require(
        state.metadata("control") == "stopped" and not state.metadata("orphan_uncertainty", False),
        "Controller lifetime changed",
    )
    require(
        state.metadata("c_min_trial_permit") is None
        and state.metadata("c_min_live_permit") is None
        and state.metadata("c_min_run_proposal") is None,
        "Existing grant cannot be replaced",
    )
    for key, value in request["registrations"].items():
        current = state.metadata(key)
        require(current is None or current == value, "Existing trial registration differs")
    permit = {
        **request["permit"],
        "expires": approved_at + 180,
        "approval_scope": row["target_hash"],
    }
    activation = {
        "decision": row["id"],
        "scope": row["target_hash"],
        "approved_at": approved_at,
        "expires": permit["expires"],
        "permit": fingerprint(permit),
    }
    db.execute(
        "CREATE TABLE IF NOT EXISTS c_min_trial_activations("
        "slot INTEGER PRIMARY KEY CHECK(slot=1),document TEXT NOT NULL)"
    )
    db.execute("INSERT INTO c_min_trial_activations VALUES (1,?)", (state.encode(activation),))
    for key, value in {**request["registrations"], "c_min_trial_permit": permit}.items():
        db.execute(
            "INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, state.encode(value)),
        )
    state._event(db, "trial.activated", None, activation)


def authorized(state: StateStore, permit: dict[str, Any], decision: str) -> bool:
    request = state.metadata("c_min_trial_request")
    try:
        validate_request(request)
        scope = fingerprint(request)
        with state.connect() as db:
            record = db.execute(
                "SELECT document FROM c_min_trial_activations WHERE slot=1"
            ).fetchone()
            owner = db.execute("SELECT * FROM decisions WHERE id=?", (decision,)).fetchone()
        if not record or not owner:
            return False
        activation = json.loads(record[0])
        at = owner["decided"]
        return bool(
            owner["task_id"] is None
            and owner["category"] == "scope"
            and owner["status"] == "approved"
            and math.isfinite(at)
            and at <= time.time() < at + 180
            and owner["target_hash"] == scope
            and owner["actor"]
            and owner["reason"]
            and activation
            == {
                "decision": decision,
                "scope": scope,
                "approved_at": at,
                "expires": at + 180,
                "permit": fingerprint(permit),
            }
            and permit == {**request["permit"], "expires": at + 180, "approval_scope": scope}
            and all(state.metadata(k) == v for k, v in request["registrations"].items())
        )
    except (ValueError, TypeError, KeyError, sqlite3.Error):
        return False
