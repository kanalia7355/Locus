"""Fixed owner preparation operations for the dedicated audit identity."""

import time
from typing import Any

from loop_engine.app_credentials import WindowsAppVault
from loop_engine.audit_identity import AuditDeployment
from loop_engine.audit_os_guard import require_private_crash_policy
from loop_engine.audit_profile import auth_command, check_profile, preflight
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError
from loop_engine.service_identity import ROLES


def dispatch(
    deployment: AuditDeployment, peer: str, body: dict[str, Any], *, deadline: float
) -> dict[str, Any]:
    deployment.require_role("audit")
    if (
        peer not in deployment.clients("audit")
        or not isinstance(body, dict)
        or type(deadline) not in {int, float}
        or not 0 < deadline - time.monotonic() <= 300
    ):
        raise SafetyError("Fixed authenticated audit preparation operation required")
    operation = body.get("operation")
    review_operations = {"reserve", "chunk", "run", "result", "findings_chunk", "ack"}
    if not isinstance(operation, str) or operation not in {
        "health",
        "preflight",
        "auth_status",
        "self_test",
        *review_operations,
    }:
        raise SafetyError("Audit preparation cannot sign, merge or run arbitrary operations")
    if operation not in review_operations and set(body) != {"operation"}:
        raise SafetyError("Closed owner audit preparation operation required")
    if operation in {"preflight", "self_test"} and peer != deployment.settings["operator_sid"]:
        raise SafetyError("Owner-only audit authentication preparation")
    deployment.require_private_state()
    check_profile(deployment, deployment.state / "home")
    vault = WindowsAppVault()
    if any(vault.get(role, ROLES[role][2]) is not None for role in ROLES):
        raise SafetyError("App credentials accessible to audit account; hold")
    if operation == "preflight":
        require_private_crash_policy(deployment, configure=True)
        return preflight(deployment, deadline=deadline, cancelled=lambda: False)
    if operation == "health":
        try:
            require_private_crash_policy(deployment)
            privacy = True
        except (SafetyError, OSError):
            privacy = False
        return {
            "role": "audit",
            "identity": deployment.identity,
            "isolated_account": True,
            "app_keys_absent": True,
            "app_state_denied": True,
            "profile_writes_denied": True,
            "log_writes_denied": True,
            "account_crash_reporting_disabled": privacy,
            "activated": False,
        }
    require_private_crash_policy(deployment)
    if operation in review_operations:
        from loop_engine.audit_runtime import review_request

        return review_request(deployment, peer, body, deadline=deadline)
    if operation == "self_test":
        from loop_engine.audit_runtime import fixed_self_test

        return fixed_self_test(deployment, deadline=deadline)
    from loop_engine.audit_auth_state import AuthState

    authentication = AuthState(deployment.state / "home")
    if authentication.check() == "pristine":
        return {"role": "audit", "authenticated": False, "activated": False}
    if authentication.check() != "enrolled":
        raise SafetyError("Real audit authentication lifecycle required")
    authentication.begin("use")
    result = ProcessRunner().run(
        auth_command(deployment.runtime / "codex.exe", "login", "status"),
        deployment.state,
        timeout=min(15, deadline - time.monotonic()),
        model=True,
        output_limit=8192,
        active_process_limit=1,
    )
    authenticated = (
        result.outcome == "exit"
        and result.returncode == 0
        and result.stderr.strip().splitlines()[-1:] == ["Logged in using ChatGPT"]
    )
    if authenticated:
        authentication.finish("enrolled")
    return {
        "role": "audit",
        "authenticated": authenticated,
        "activated": False,
    }
