"""One-shot validation purpose of the existing C-min adapter; never a Controller task."""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from loop_engine.approval import ApprovalQueue
from loop_engine.model_gate import check, strict_json
from loop_engine.security import SafetyError, create_text, fingerprint, reparse, within
from loop_engine.state_store import StateStore

# Public owner-approved document digest, not authentication material.
# pragma: allowlist nextline secret
PLAN_HASH = "eca090f9d22f4347e16ae371cba9106d6600906d0806b6a5eb9852e864a01af7"
PROMPT = (
    "This is a synthetic transport verification. Do not use tools. Return exactly "
    'the JSON object {"ok":true,"proof":"C_MIN_SYNTHETIC_OK"}.'
)
SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean", "const": True},
        "proof": {"type": "string", "const": "C_MIN_SYNTHETIC_OK"},
    },
    "required": ["ok", "proof"],
    "additionalProperties": False,
}


def authorize(
    root: Path, state: StateStore, workspace: Path, artifact: str, approval: str
) -> dict[str, Any]:
    from loop_engine.runtime_diagnostics import runtime_identity

    permit = state.metadata("c_min_trial_permit")
    fields = {
        "purpose",
        "runtime",
        "artifact",
        "workspace",
        "plan",
        "input_hash",
        "profile",
        "history",
        "expires",
        "max_calls",
        "refresh",
        "offline_review",
    }
    check(
        {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(fields),
            "properties": {
                **{
                    k: {"type": "string", "minLength": 1, "maxLength": 4096}
                    for k in fields - {"expires", "max_calls"}
                },
                "expires": {"type": "number"},
                "max_calls": {"type": "integer", "const": 1},
            },
        },
        permit,
    )
    if (
        not isinstance(permit, dict)
        or set(permit) != fields
        or permit["purpose"] != "c-min-single-validation"
        or permit["runtime"] != runtime_identity(root)
        or permit["artifact"] != artifact
        or permit["workspace"] != str(workspace.resolve())
        or permit["plan"] != PLAN_HASH
        or permit["max_calls"] != 1
        or not time.time() < permit["expires"] <= time.time() + 180
        or permit["refresh"] != "official-existing-secure-backend-only"
        or permit["profile"] != fingerprint(state.metadata("c_min_auth_profile"))
        or state.metadata("c_min_trial_history")
        != {"binding": permit["history"], "reconciled": True, "additional_slots": 1}
        or state.metadata("c_min_trial_offline_review")
        != {"binding": permit["offline_review"], "runtime": permit["runtime"], "passed": True}
        or ApprovalQueue(state).status(None, "scope", fingerprint(permit)) != "approved"
    ):
        raise SafetyError("Separate exact one-shot trial authorization is absent")
    with state.connect() as db:
        decision = db.execute(
            "SELECT id FROM decisions WHERE id=? AND task_id IS NULL AND category='scope' "
            "AND target_hash=? AND status='approved'",
            (approval, fingerprint(permit)),
        ).fetchone()
    if not decision or any(reparse(p) for p in (workspace, *workspace.parents)):
        raise SafetyError("Trial approval/workspace identity differs")
    if not workspace.is_dir() or any(p.name != "synthetic.txt" for p in workspace.iterdir()):
        raise SafetyError("Synthetic-only trial workspace required")
    marker = workspace / "synthetic.txt"
    if reparse(marker) or marker.read_bytes() != b"C_MIN_SYNTHETIC_ONLY\n":
        raise SafetyError("Synthetic marker changed")
    return permit


def reserve(state: StateStore, permit: dict[str, Any], artifact: str) -> dict[str, Any]:
    """Lifetime single slot; no new approval/nonce can replay an uncertain trial."""
    owner = {
        "role": "trial",
        "schema": "trial",
        "owner_id": "C-MIN-SINGLE",
        "attempt": 1,
        "spec": fingerprint(permit),
        "binding": artifact,
    }
    with state.connect() as db:
        db.execute("PRAGMA synchronous=FULL")
        if db.execute("PRAGMA synchronous").fetchone()[0] != 2:
            raise SafetyError("Trial durability unavailable")
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS c_min_trials(
                slot INTEGER PRIMARY KEY CHECK(slot=1), owner_key TEXT NOT NULL,
                phase TEXT NOT NULL, document TEXT NOT NULL)""")
            if db.execute("SELECT 1 FROM c_min_trials").fetchone():
                raise SafetyError("Trial slot already consumed/reserved; never replay")
            db.execute(
                "INSERT INTO c_min_trials VALUES(1,?,'reserved',?)",
                (fingerprint(owner), state.encode({"permit": fingerprint(permit)})),
            )
            state._event(db, "trial.reserved", None, {"permit": fingerprint(permit)})
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return owner


def exact_input(value: dict[str, Any], permit: dict[str, Any]) -> None:
    # Includes every configuration, message, provenance and additional_tools item.
    # No stripping or acceptance based only on the user-supplied prompt.
    if fingerprint(value["input"]) != permit["input_hash"]:
        raise SafetyError("Trial semantic input differs before upstream reservation")


def record_result(
    state: StateStore, journal: Any, identifier: str, permit: dict[str, Any], output: str
) -> dict[str, Any]:
    events = [strict_json(line.encode()) for line in output.splitlines()]
    if not events or events[-1].get("type") != "turn.completed":
        raise SafetyError("Trial CLI completion is missing")
    messages: list[Any] = []
    phase = 0
    for event in events:
        kind = event.get("type")
        if phase == 0 and kind == "thread.started":
            phase = 1
            continue
        if phase == 1 and kind == "turn.started":
            phase = 2
            continue
        if phase == 2 and kind == "turn.completed" and len(messages) == 1:
            phase = 3
            continue
        item = event.get("item", {})
        if phase == 2 and kind == "item.completed" and item.get("type") == "agent_message":
            messages.append(strict_json(item.get("text", "").encode()))
        elif phase == 2 and kind == "item.completed" and item.get("type") == "reasoning":
            continue
        else:
            raise SafetyError("Unknown trial CLI event")
    if len(messages) != 1 or phase != 3:
        raise SafetyError("Trial needs one final synthetic message")
    check(SCHEMA, messages[0])
    journal.advance(identifier, "terminal_validated", "cli_validated")
    proof = {
        "purpose": "c-min-single-validation",
        "surface_version": 3,
        "protocol": "c-min-lite-v3",
        "passed": False,  # Not successful until the authoritative acknowledgement commits.
        "runtime": permit["runtime"],
        "artifact": permit["artifact"],
        "permit": fingerprint(permit),
        "invocation": identifier,
        "calls": 1,
        "schema_validated": True,
    }
    with state.connect() as db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        changed = db.execute(
            "UPDATE c_min_trials SET phase='validated',document=? "
            "WHERE slot=1 AND phase='reserved'",
            (state.encode(proof),),
        ).rowcount
        if changed != 1:
            db.rollback()
            raise SafetyError("Trial acknowledgement changed; no resend")
        db.commit()
    journal.acknowledge(identifier)
    return {**proof, "passed": True}


def status(state: StateStore) -> dict[str, Any]:
    """Read-only outcome observation, never launch or retry a model."""
    with state.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='c_min_trials'").fetchone():
            return {"purpose": "c-min-single-validation", "phase": "absent", "passed": False}
        row = db.execute("SELECT phase,document FROM c_min_trials WHERE slot=1").fetchone()
        if row is None:
            return {"purpose": "c-min-single-validation", "phase": "absent", "passed": False}
        proof = json.loads(row["document"])
        passed = False
        if row["phase"] == "completed":
            entry = db.execute(
                "SELECT phase FROM model_invocations WHERE id=?", (proof.get("invocation"),)
            ).fetchone()
            passed = bool(entry and entry[0] == "completed" and proof.get("passed") is True)
        return {"purpose": "c-min-single-validation", "phase": row["phase"], "passed": passed}


def run(root: Path, state: StateStore, plan: Path, approval: str) -> dict[str, Any]:
    from loop_engine.c_min_runtime import invoke
    from loop_engine.codex_runner import codex_binary
    from loop_engine.process import ProcessRunner
    from loop_engine.runtime_diagnostics import boundary_for

    if reparse(plan) or hashlib.sha256(plan.read_bytes()).hexdigest() != PLAN_HASH:
        raise SafetyError("Approved trial plan bytes differ")
    # Deny before even inspecting operator configuration unless an exact permit exists.
    permit = state.metadata("c_min_trial_permit")
    if not isinstance(permit, dict):
        raise SafetyError("No real-connection trial permit; no CLI or auth access")
    workspace = within(root, ".loop/runtime/probes/c-min-single-validation")
    boundary = boundary_for(root)
    artifact = boundary._binding(workspace)
    permit = authorize(root, state, workspace, artifact, approval)
    contract = within(root, ".loop/runtime/contracts/c-min-trial.json")
    create_text(contract, json.dumps(SCHEMA))
    if json.loads(contract.read_text()) != SCHEMA:
        raise SafetyError("Trial output contract differs")
    binary = codex_binary(root)
    if binary is None:
        raise SafetyError("Pinned trial CLI unavailable")
    argv = [
        binary,
        "exec",
        "--json",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--cd",
        str(workspace),
        "--output-schema",
        str(contract),
        "-",
    ]
    outcome, journal, identifier = invoke(
        root,
        state,
        boundary,
        ProcessRunner(),
        argv,
        PROMPT,
        workspace,
        SCHEMA,
        {},
        time.monotonic() + max(0, permit["expires"] - time.time()),
        lambda: False,
        trial_approval=approval,
    )
    try:
        return record_result(state, journal, identifier, permit, outcome.stdout)
    except BaseException:
        journal.hold(identifier)
        raise
