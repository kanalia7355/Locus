"""Adopt existing Apps through masked local input; no CI-secret extraction."""

import getpass
import json
import sys
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from loop_engine.app_onboarding import PERMISSIONS
from loop_engine.github_app import AppConnectionError, GitHubApp
from loop_engine.security import SafetyError, create_text, within

REPOSITORY_ID = 1440108668


class ProvisioningVault(Protocol):
    def put(self, role: str, app_id: int, value: bytes) -> None: ...
    def get(self, role: str, app_id: int) -> bytes | None: ...


def masked_private_key(reader: Callable[[str], str] = getpass.getpass) -> bytes:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise SafetyError("Interactive local terminal required; no plaintext input fallback")
    lines: list[str] = []
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            for _ in range(64):
                line = reader("PEM line (hidden): ")
                if len(line) > 256:
                    raise AppConnectionError("key", "input_line_too_long")
                if not line:
                    raise SafetyError("Incomplete or oversized key input")
                lines.append(line)
                if sum(len(value) + 1 for value in lines) > 2560:
                    raise SafetyError("Key exceeds supported credential manager limit")
                if line.startswith("-----END "):
                    return ("\n".join(lines) + "\n").encode("ascii")
        except (getpass.GetPassWarning, EOFError, UnicodeError):
            raise SafetyError("Masked key input unavailable or invalid") from None
    raise SafetyError("Key input line limit exceeded")


class _InputKey:
    def __init__(self, role: str, app_id: int, value: bytes) -> None:
        self.role, self.app_id, self.value = role, app_id, value

    def get(self, role: str, app_id: int) -> bytes | None:
        return self.value if (role, app_id) == (self.role, self.app_id) else None


def provision(
    root: Path,
    role: str,
    app_id: int,
    installation_id: int,
    vault: ProvisioningVault,
    *,
    value: bytes | None = None,
    make_client: Callable[..., GitHubApp] = GitHubApp,
) -> dict[str, object]:
    """Authenticate before storing. Only public IDs are written to the receipt.

    Existing vault items are validated without prompting/overwriting. Conflicting
    metadata never replaces an existing receipt. A receipt-write failure does
    not delete a successfully stored credential; rerunning uses that item.
    """
    if role not in PERMISSIONS or any(
        type(v) is not int or v <= 0 for v in (app_id, installation_id)
    ):
        raise SafetyError("Invalid provisioning identity")
    root = root.resolve()
    path = within(root, f".loop/runtime/app-installations/{role}-{app_id}.json")
    public: dict[str, object] = {
        "role": role,
        "app_id": app_id,
        "installation_id": installation_id,
        "repository_id": REPOSITORY_ID,
        "repository": "kanalia7355/Locus",
        "permissions": PERMISSIONS[role],
        "activated": False,
    }
    if path.exists() and (path.stat().st_size > 4096 or json.loads(path.read_text()) != public):
        raise SafetyError("Existing App provisioning metadata differs")
    existing = vault.get(role, app_id)
    if existing is not None and value is not None:
        raise SafetyError("Existing key requires explicit rotation, not replacement")
    pem = existing if existing is not None else value
    if pem is None:
        pem = masked_private_key()
    if not pem or len(pem) > 2560:
        raise SafetyError("Credential size rejected")
    client = make_client(role, app_id, installation_id, REPOSITORY_ID, _InputKey(role, app_id, pem))
    # This performs actual App/installation/scope/repository authentication;
    # the operation itself is read-only, even for the Merge App.
    branch = client.call("GET", "/repos/kanalia7355/Locus/branches/main")
    if not isinstance(branch, dict) or branch.get("name") != "main":
        raise SafetyError("Main identity not observed")
    if role == "merge":
        policy = client.call("GET", "/repos/kanalia7355/Locus/branches/main/protection")
        if not isinstance(policy, dict) or "required_status_checks" not in policy:
            raise SafetyError("Merge policy read not authenticated")
    if existing is None:
        vault.put(role, app_id, pem)
    if not create_text(path, json.dumps(public, indent=2) + "\n"):
        if json.loads(path.read_text()) != public:
            raise SafetyError("App metadata publication conflict; stored key retained")
    return {**public, "authenticated": True}
