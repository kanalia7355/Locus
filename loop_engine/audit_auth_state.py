"""Nonsecret, fail-closed lifecycle for the audit account's encrypted login.

Read Windows credential headers only, never expose/copy their secret blobs.
Unknown or interrupted state must be reconciled before calling the auth CLI.
"""

import ctypes
import hashlib
import sys
from collections.abc import Callable
from pathlib import Path

from loop_engine.app_credentials import WindowsAppVault, _Credential
from loop_engine.audit_packet import canonical, decode
from loop_engine.security import SafetyError, atomic_text, reparse


def key_metadata(home: Path, *, direct: bool = False) -> str | None:
    if sys.platform != "win32":
        raise SafetyError("Audit key existence requires Windows credential metadata")
    # Rust std::fs::canonicalize retains the Windows extended path prefix.
    canonical_home = str(home.resolve())
    if not canonical_home.startswith("\\\\?\\"):
        canonical_home = "\\\\?\\" + canonical_home
    short = hashlib.sha256(canonical_home.encode()).hexdigest()[:16]
    target = f"cli|{short}.Codex Auth" if direct else f"secrets|{short}.codex"
    vault = WindowsAppVault()
    pointer = ctypes.POINTER(_Credential)()
    if not vault._api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
        if vault._last_error() == 1168:
            return None
        raise SafetyError("Audit credential metadata unavailable")
    try:
        header = pointer.contents
        if header.Type != 1 or header.TargetName != target or not header.CredentialBlobSize:
            raise SafetyError("Unexpected audit credential header")
        written = header.LastWritten
        return f"{written.dwHighDateTime}:{written.dwLowDateTime}:{header.CredentialBlobSize}"
    finally:
        vault._api.CredFree(pointer)


class AuthState:
    def __init__(self, home: Path, *, metadata: Callable[..., str | None] = key_metadata):
        self.home = home
        self.journal = home.parent / (home.name + "-authentication.json")
        self.metadata = metadata

    def artifacts(self) -> str | None:
        directory = self.home / "secrets"
        if reparse(directory) or not directory.is_dir():
            raise SafetyError("Fixed private authentication directory required")
        files = list(directory.iterdir())
        if any(p.name != "codex_auth.age" or reparse(p) or not p.is_file() for p in files):
            raise SafetyError("Uncertain authentication temporary/artifact; preserve state")
        if (self.home / "auth.json").exists() or self.metadata(self.home, direct=True) is not None:
            raise SafetyError("Unexpected plaintext/direct authentication; preserve state")
        stamp = self.metadata(self.home)
        if bool(files) != (stamp is not None):
            raise SafetyError("Missing authentication key/ciphertext; preserve state")
        if files:
            with files[0].open("rb") as stream:
                if not stream.read(24).startswith(b"age-encryption.org/v1\n"):
                    raise SafetyError("Expected encrypted authentication envelope")
            if not 0 < files[0].stat().st_size <= 1024 * 1024:
                raise SafetyError("Authentication ciphertext size exceeded")
        return stamp

    def check(self) -> str:
        if reparse(self.journal) or not self.journal.is_file():
            raise SafetyError("Protected authentication lifecycle missing")
        record = decode(self.journal.read_bytes(), 4096)
        if (
            set(record) != {"phase", "key_metadata"}
            or not isinstance(record["phase"], str)
            or record["phase"]
            not in {
                "pristine",
                "enrolled",
                "probe_ready",
                "probe_cleared",
            }
        ):
            raise SafetyError("Interrupted authentication; explicit reconciliation required")
        stamp = self.artifacts()
        if stamp != record["key_metadata"] or (record["phase"] == "pristine") != (stamp is None):
            raise SafetyError("Authentication lifecycle mismatch; preserve state")
        return str(record["phase"])

    def require_active(self) -> None:
        record = decode(self.journal.read_bytes(), 4096)
        if (
            set(record) != {"phase", "key_metadata"}
            or record["phase"] != "active_use"
            or record["key_metadata"] is None
            or self.artifacts() != record["key_metadata"]
        ):
            raise SafetyError("Active authentication binding changed; preserve state")

    def begin(self, operation: str) -> None:
        phase = self.check()
        allowed = {
            "enrol": {"pristine"},
            "probe": {"pristine"},
            "probe_clear": {"probe_ready"},
            "use": {"enrolled", "probe_ready", "probe_cleared"},
        }
        if phase not in allowed.get(operation, set()):
            raise SafetyError("Authentication lifecycle does not permit operation")
        atomic_text(
            self.journal,
            canonical({"phase": "active_" + operation, "key_metadata": self.artifacts()}).decode(),
        )

    def finish(self, phase: str) -> None:
        record = decode(self.journal.read_bytes(), 4096)
        allowed = {
            "active_enrol": {"enrolled"},
            "active_probe": {"probe_ready"},
            "active_probe_clear": {"probe_cleared"},
            "active_use": {"enrolled", "probe_ready", "probe_cleared"},
        }
        previous = record.get("phase")
        if not isinstance(previous, str) or phase not in allowed.get(previous, set()):
            raise SafetyError("Authentication transition rejected")
        stamp = self.artifacts()
        if stamp is None or (
            record["key_metadata"] is not None and stamp != record["key_metadata"]
        ):
            raise SafetyError("Authentication key changed; preserve state")
        atomic_text(self.journal, canonical({"phase": phase, "key_metadata": stamp}).decode())
