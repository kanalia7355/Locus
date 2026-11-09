"""Fixed preparation operations, under the service's isolated Windows identity.

Preparation can authenticate/provision the exact existing App and observe repo
policy. It cannot publish reviews/checks, change refs/protection or merge a PR.
"""

import base64
import json
import os
from pathlib import Path
from typing import Any

from loop_engine.app_credentials import WindowsAppVault
from loop_engine.app_provisioning import REPOSITORY_ID, provision
from loop_engine.broker_policy_reader import PREFIX, observe_policy
from loop_engine.github_app import GitHubApp
from loop_engine.security import SafetyError
from loop_engine.service_identity import DEPLOYMENT_ROOT, ROLES, Deployment


def dispatch(
    deployment: Deployment, role: str, peer: str, document: dict[str, Any]
) -> dict[str, Any]:
    deployment.require_role(role)
    if peer not in deployment.clients(role):
        raise SafetyError("Unauthorized service caller")
    operation = document.get("operation")
    operator = peer == deployment.settings["operator_sid"]
    if operation not in {"health", "verify", "provision", "policy"}:
        raise SafetyError("No publication/merge or arbitrary API operation is available")
    if operation != "policy" and not operator:
        raise SafetyError("Operator-only credential preparation")
    if operation == "policy" and role != "merge":
        raise SafetyError("Policy inspection belongs only to the Merge service")
    wanted = {"operation", "key_base64"} if operation == "provision" else {"operation"}
    if set(document) != wanted:
        raise SafetyError("Unexpected service operation fields")
    vault = WindowsAppVault()
    _, _, app_id, installation = ROLES[role]
    other = "merge" if role == "review" else "review"
    if vault.get(other, ROLES[other][2]) is not None:
        raise SafetyError("Cross-role credential unexpectedly accessible; do not activate")
    present = vault.get(role, app_id) is not None
    state = DEPLOYMENT_ROOT / "state" / role
    intent = state / "credential-import-intent.json"
    if operation == "health":
        try:
            (DEPLOYMENT_ROOT / "state" / other / "isolation-canary.txt").read_bytes()
        except PermissionError:
            other_state_denied = True
        else:
            other_state_denied = False
        try:
            with (deployment.runtime / "sealed-canary.txt").open("ab"):
                pass
        except PermissionError:
            source_write_denied = True
        else:
            source_write_denied = False
        if not other_state_denied or not source_write_denied:
            raise SafetyError("Service filesystem isolation was not demonstrated")
        return {
            "role": role,
            "identity": deployment.identity,
            "isolated_account": True,
            "key_present": present,
            "credential_import_held": intent.exists(),
            "cross_role_key_absent": True,
            "other_state_denied": True,
            "source_write_denied": True,
            "activated": False,
        }
    client = GitHubApp(role, app_id, installation, REPOSITORY_ID, vault)
    if operation == "verify":
        client.call("GET", PREFIX + "/branches/main")
        return {"role": role, "authenticated": True, "activated": False}
    if operation == "policy":
        return observe_policy(client, app_id, ROLES["review"][2])
    # Never overwrite a provisioned identity or retry an uncertain key write.
    if present:
        raise SafetyError("Existing role credential requires verification, not replacement")
    if intent.exists():
        raise SafetyError("Previous credential import requires explicit reconciliation, not replay")
    encoded = document["key_base64"]
    if not isinstance(encoded, str) or len(encoded) > 3500:
        raise SafetyError("Invalid credential input size")
    try:
        value = base64.b64decode(encoded, validate=True)
    except ValueError:
        raise SafetyError("Invalid credential input encoding") from None
    if not 0 < len(value) <= 2560:
        raise SafetyError("Unsupported credential size")
    if not state.is_dir():
        raise SafetyError("Prepared isolated state directory required")
    with intent.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "role": role,
                "app_id": app_id,
                "installation_id": installation,
                "automatic_replay": False,
            },
            stream,
        )
        stream.flush()
        os.fsync(stream.fileno())
    return provision(Path(state), role, app_id, installation, vault, value=value)
