"""Exact, owner-approved invocation-only notification suppression."""

from typing import Any

from loop_engine.security import SafetyError, fingerprint

VERSION = "c-min-notify-suppression-v1"
# Public owner-approved design digest, not a credential.
# pragma: allowlist nextline secret
APPROVAL = "6b24d365fe1bfb04c43d7083ccdbac8a7d17385bf7bdbeb7f3437e45642a5a01"


def assess(raw: str, settings: dict[str, Any], policy: Any) -> dict[str, Any]:
    if policy is None:
        return settings
    if (
        not isinstance(policy, dict)
        or set(policy) != {"version", "approval", "config_hash"}
        or policy["version"] != VERSION
        or policy["approval"] != APPROVAL
        or policy["config_hash"] != fingerprint(raw)
    ):
        raise SafetyError("Exact approved notification policy/config required")
    command = settings.get("notify")
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(part, str) or not part or "\x00" in part for part in command)
    ):
        raise SafetyError("Assessed original notify must be a nonempty string array")
    return {key: value for key, value in settings.items() if key != "notify"}


def require_override(argv: list[str]) -> None:
    """No later config argument may reintroduce notify; trusted argv only."""
    values = []
    for index, value in enumerate(argv):
        if value.startswith("notify") and "=" in value:
            if index == 0 or argv[index - 1] not in {"-c", "--config"}:
                raise SafetyError("Unsupported notification override syntax")
            key, content = value.split("=", 1)
            if key.strip() != "notify":
                raise SafetyError("Unassessed nested notification override")
            values.append((argv[index - 1], content))
        if value.startswith(("-cnotify", "--config=notify")):
            raise SafetyError("Unsupported inline notification override")
    if not values or values[-1] != ("-c", "[]"):
        raise SafetyError("Final exact notification suppression override missing")
