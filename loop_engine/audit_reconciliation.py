"""Owner-permitted, exact-record authentication status reconciliation only."""

import hashlib
import json
import os
import time
from typing import Any

from loop_engine.audit_auth_state import AuthState
from loop_engine.audit_identity import AUDIT_ROOT, AuditDeployment
from loop_engine.audit_packet import canonical, hash_value
from loop_engine.audit_profile import auth_command
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError
from loop_engine.service_identity import protected_bytes


def permit(deployment: AuditDeployment) -> dict[str, Any]:
    value = json.loads(protected_bytes(AUDIT_ROOT / "reconciliation-permit.json"))
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "protocol",
            "identity",
            "previous_identity",
            "authentication",
            "trial",
            "diagnostic_inference",
        }
        or value["protocol"] != "locus-audit-reconciliation-v1"
        or value["identity"] != deployment.identity
        or value["previous_identity"] != deployment.state_identity
        or type(value["diagnostic_inference"]) is not bool
    ):
        raise SafetyError("Exact protected owner reconciliation permit required")
    for key in ("authentication", "trial"):
        hash_value(value[key])
    trial = deployment.state / "synthetic-model-proof.json"
    if hashlib.sha256(trial.read_bytes()).hexdigest() != value["trial"]:
        raise SafetyError("Original trial changed; preserve without replay")
    return value


def reconcile_auth(
    deployment: AuditDeployment, *, deadline: float, process: ProcessRunner | None = None
) -> dict[str, Any]:
    deployment.require_role("audit")
    approval = permit(deployment)
    authentication = AuthState(deployment.state / "home")
    raw = authentication.journal.read_bytes()
    if hashlib.sha256(raw).hexdigest() != approval["authentication"]:
        raise SafetyError("Authentication record changed; no reconciliation")
    authentication.require_active()
    left = deadline - time.monotonic()
    if not 0 < left <= 300:
        raise SafetyError("Bounded authentication reconciliation required")
    intent = deployment.state / "auth-reconciliation.json"
    # Never overwrite/retry an uncertain status operation. Preserve the exact
    # prior nonsecret record before changing its phase; no key/cache is changed.
    with intent.open("xb") as stream:
        stream.write(
            canonical(
                {
                    "phase": "status_intent",
                    "identity": deployment.identity,
                    "previous_record": json.loads(raw),
                    "permit": approval,
                }
            )
        )
        stream.flush()
        os.fsync(stream.fileno())
    outcome = (process or ProcessRunner()).run(
        auth_command(deployment.runtime / "codex.exe", "login", "status"),
        deployment.state,
        timeout=min(15, left),
        model=True,
        output_limit=8192,
        active_process_limit=1,
    )
    if (
        outcome.outcome != "exit"
        or outcome.returncode != 0
        or time.monotonic() >= deadline
        or outcome.stderr.strip().splitlines()[-1:] != ["Logged in using ChatGPT"]
    ):
        raise SafetyError("Fresh status not established; original authentication remains held")
    authentication.require_active()
    if (
        hashlib.sha256(authentication.journal.read_bytes()).hexdigest()
        != approval["authentication"]
    ):
        raise SafetyError("Authentication changed during reconciliation; preserve state")
    permit(deployment)
    authentication.finish("enrolled")
    return {
        "authenticated": True,
        "original_trial_preserved": True,
        "provider_request_sent": False,
        "activated": False,
    }
