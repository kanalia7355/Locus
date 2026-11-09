"""Authenticated, bounded preparation client. No owner OAuth transfer."""

import base64
import time
from collections.abc import Callable
from typing import Any

from loop_engine.app_credentials import WindowsAppVault
from loop_engine.security import SafetyError, fingerprint
from loop_engine.service_identity import ROLES, Deployment
from loop_engine.windows_pipe import request


class ServiceClient:
    def __init__(self, deployment: Deployment | None = None) -> None:
        self.deployment = deployment or Deployment()

    def call(
        self,
        role: str,
        body: dict[str, Any],
        *,
        timeout: float = 120,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> dict[str, Any]:
        if role not in ROLES or not 0 < timeout <= 300:
            raise SafetyError("Fixed role and bounded service window required")
        if cancelled():
            raise SafetyError("Service request cancelled before registration check")
        from loop_engine.service_inspection import inspect_registration

        deadline = time.monotonic() + timeout
        inspect_registration(self.deployment, role, timeout=timeout, cancelled=cancelled)
        remaining = deadline - time.monotonic()
        if remaining <= 0 or cancelled():
            raise SafetyError("Service registration check exceeded request window")
        answer = request(
            "Locus-" + role + "-v1",
            self.deployment.settings["roles"][role]["sid"],
            self.deployment.clients(role),
            {"deadline_monotonic": deadline, "body": body},
            timeout=remaining,
            cancelled=cancelled,
        )
        if answer.get("status") in {"blocked", "uncertain"}:
            return answer
        return answer

    def provision(self, role: str) -> dict[str, Any]:
        health = self.call(role, {"operation": "health"})
        if health.get("key_present") is True:
            return self.call(role, {"operation": "verify"})
        if health.get("credential_import_held") is True:
            raise SafetyError("Uncertain credential import is held; do not resend key material")
        if health.get("isolated_account") is not True or health.get("activated") is not False:
            raise SafetyError("Demonstrated inactive service identity required before key transfer")
        value = WindowsAppVault().get(role, ROLES[role][2])
        if value is None:
            raise SafetyError("Existing development credential unavailable; no key file fallback")
        return self.call(
            role, {"operation": "provision", "key_base64": base64.b64encode(value).decode("ascii")}
        )


class ServicePolicyObserver:
    def __init__(
        self, client: ServiceClient, *, timeout: float, cancelled: Callable[[], bool]
    ) -> None:
        self.client, self.deadline, self.cancelled = client, time.monotonic() + timeout, cancelled

    def observe(self) -> dict[str, Any]:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0 or self.cancelled():
            raise SafetyError("Policy observation cancelled or time-limited")
        result = self.client.call(
            "merge", {"operation": "policy"}, timeout=min(remaining, 300), cancelled=self.cancelled
        )
        if set(result) != {
            "facts",
            "policy_hash",
            "issues",
            "merge_authorized",
            "atomic_base_binding",
        }:
            raise SafetyError("Authenticated complete policy observation unavailable")
        if result["merge_authorized"] is not False or result["atomic_base_binding"] is not False:
            raise SafetyError("Policy observer cannot authorize merging")
        if (
            not isinstance(result["facts"], dict)
            or result["facts"].get("repository") != "kanalia7355/Locus"
            or fingerprint(result["facts"]) != result["policy_hash"]
        ):
            raise SafetyError("Authenticated policy response binding mismatch")
        return result
