"""Closed, nonsecret audit diagnostics; never include native/model error text."""

from typing import Any

from loop_engine.security import SafetyError

STAGES = {
    "waiting_client",
    "local_request",
    "upstream_connect",
    "upstream_headers",
    "upstream_response",
    "upstream_stream",
    "response_validation",
    "complete",
}
REASONS = {"timeout", "tls", "network", "policy", "client_or_output_rejected"}


def validate_diagnostic(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value) != {"stage", "reason", "http_status"}
        or not isinstance(value["stage"], str)
        or value["stage"] not in STAGES
        or not isinstance(value["reason"], str)
        or value["reason"] not in REASONS
        or (
            value["http_status"] is not None
            and (type(value["http_status"]) is not int or not 100 <= value["http_status"] <= 599)
        )
    ):
        raise SafetyError("Invalid closed audit diagnostic")
    return dict(value)


class AuditFailure(SafetyError):
    def __init__(self, stage: str, reason: str, http_status: int | None = None):
        self.diagnostic = validate_diagnostic(
            {"stage": stage, "reason": reason, "http_status": http_status}
        )
        super().__init__("Audit held; inspect bounded diagnostic")
