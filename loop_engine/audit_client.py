"""Fixed audit preparation client; private device UI requires an owner's TTY."""

import json
import sys
import time
from collections.abc import Callable
from typing import Any

from loop_engine.audit_identity import AuditDeployment
from loop_engine.security import SafetyError
from loop_engine.service_identity import Deployment
from loop_engine.service_inspection import inspect_registration
from loop_engine.windows_pipe import request


class AuditClient:
    def __init__(self, deployment: AuditDeployment | None = None) -> None:
        self.deployment = deployment or AuditDeployment()

    def call(
        self,
        operation: str,
        *,
        timeout: float = 120,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> dict[str, Any]:
        if (
            operation
            not in {
                "health",
                "preflight",
                "auth_status",
                "self_test",
                "reconcile_auth",
                "diagnose_transport",
                "enroll_start",
                "enroll_poll",
                "enroll_cancel",
            }
            or not 0 < timeout <= 300
            or cancelled()
        ):
            raise SafetyError("Fixed bounded audit preparation operation required")
        app = Deployment(self.deployment.settings["app_manifest"])
        if (
            app.settings["operator_sid"] != self.deployment.settings["operator_sid"]
            or app.settings["roles"]["review"]["sid"] != self.deployment.settings["review_sid"]
            or app.settings["roles"]["merge"]["sid"] != self.deployment.settings["merge_sid"]
        ):
            raise SafetyError("Existing App deployment changed; preserve and reconcile")
        deadline = time.monotonic() + timeout
        inspect_registration(self.deployment, "audit", timeout=timeout, cancelled=cancelled)
        left = deadline - time.monotonic()
        if cancelled() or left <= 0:
            raise SafetyError("Audit preparation request cancelled/expired")
        return request(
            "Locus-audit-v1",
            self.deployment.settings["audit_sid"],
            self.deployment.clients("audit"),
            {"deadline_monotonic": deadline, "body": {"operation": operation}},
            timeout=left,
            cancelled=cancelled,
        )


def enroll_owner() -> dict[str, Any]:
    # Prevent Controller, CI or an ordinary captured tool call from collecting a
    # device code. The actual owner runs this command directly in their console.
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SafetyError("Owner authentication requires a private interactive console")
    client = AuditClient()
    deadline = time.monotonic() + 300
    shown = False
    answer = client.call("enroll_start", timeout=300)
    if answer.get("status") != "started":
        raise SafetyError("Private audit authentication did not start")
    try:
        while time.monotonic() < deadline:
            answer = client.call("enroll_poll", timeout=min(15, deadline - time.monotonic()))
            if answer.get("status") == "waiting_for_owner" and not shown:
                from loop_engine.audit_enrollment import DEVICE_URL

                if answer.get("verification_uri") != DEVICE_URL:
                    raise SafetyError("Unexpected owner authentication origin")
                import re

                code = answer.get("user_code")
                if not isinstance(code, str) or not re.fullmatch(
                    r"[A-Z0-9]{4}-[A-Z0-9]{4,5}", code
                ):
                    raise SafetyError("Invalid private owner authentication code")
                # This path is only the owner's console, never model logs/output.
                print(DEVICE_URL, flush=True)
                print(code, flush=True)
                shown = True
            if answer.get("status") in {"authenticated", "held"}:
                result = {"authenticated": answer.get("authenticated") is True, "activated": False}
                if answer.get("status") == "held":
                    stages = {
                        "preflight",
                        "existing_authentication",
                        "device_login",
                        "verification",
                    }
                    reasons = {
                        "preflight_failed",
                        "existing_login_unclassified",
                        "device_login_failed",
                        "device_auth_not_enabled",
                        "login_verification_failed",
                        "cancelled_or_expired",
                    }
                    if answer.get("stage") not in stages or answer.get("reason") not in reasons:
                        raise SafetyError("Invalid bounded owner authentication diagnostic")
                    return {
                        **result,
                        "stage": answer["stage"],
                        "reason": answer["reason"],
                        "http_status": answer.get("http_status")
                        if answer.get("http_status") in {401, 403, 404, 429, 500, 502, 503, None}
                        else None,
                    }
                return result
            time.sleep(0.5)
        raise SafetyError("Owner authentication window expired")
    finally:
        if answer.get("status") not in {"authenticated", "held"}:
            client.call("enroll_cancel", timeout=15)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation",
        choices=(
            "health",
            "preflight",
            "auth_status",
            "self_test",
            "enroll",
            "reconcile_auth",
            "diagnose_transport",
        ),
    )
    args = parser.parse_args()
    answer = (
        enroll_owner()
        if args.operation == "enroll"
        else AuditClient().call(
            args.operation,
            timeout=300 if args.operation in {"self_test", "diagnose_transport"} else 120,
        )
    )
    print(json.dumps(answer))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"blocked","activated":false}')
        raise SystemExit(2) from None
