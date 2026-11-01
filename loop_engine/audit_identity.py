"""Separate SYSTEM-sealed audit deployment. No App vault or signing capability.

Its fixed namespace and protocol do not change existing preparation deployments.
The audit account's own generated state is private, while its source is sealed.
"""

import ctypes
import hashlib
import json
import os
import sys
from ctypes import wintypes as w
from pathlib import Path, PureWindowsPath
from typing import Any

from loop_engine.audit_packet import hash_value
from loop_engine.security import SafetyError, reparse
from loop_engine.service_identity import (
    DEPLOYMENT_ROOT,
    Deployment,
    _FileAttributes,
    protected_bytes,
    require_sealed_acl,
)
from loop_engine.windows_pipe import Native, sid

AUDIT_ROOT = Path("C:/ProgramData/LocusLoopAuditV1")
AUDIT_SERVICE = "LocusLoopAuditV1"
AUDIT_ACCOUNT = "locus_loop_audit"
BINARY_LIMIT = 512 * 1024 * 1024
# Public integrity pin for the already approved installed CLI0.166.0.
# pragma: allowlist nextline secret
CODEX_SHA256 = "9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42"


def require_private_acl(
    owner: str, control: int, entries: list[tuple[str, int, int]], audit_sid: str
) -> None:
    wanted = {
        ("S-1-5-18", 0x1F01FF, 0),
        ("S-1-5-32-544", 0x1F01FF, 0),
        (audit_sid, 0x1301BF, 3),
    }
    if owner != "S-1-5-18" or not control & 0x1000 or len(entries) != 3 or set(entries) != wanted:
        raise SafetyError("Exact SYSTEM-owned audit-private state ACL required")


def validate_settings(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "protocol",
            "mode",
            "project_root",
            "runtime_root",
            "operator_sid",
            "review_sid",
            "merge_sid",
            "audit_sid",
            "app_manifest",
            "model",
            "reasoning_effort",
        }
        or value["protocol"] != "locus-audit-service-v1"
        or value["mode"] != "prepare"
    ):
        raise SafetyError("Closed preparation-only audit settings required")
    identities = set()
    for name in ("operator_sid", "review_sid", "merge_sid", "audit_sid"):
        if not isinstance(value[name], str):
            raise SafetyError("Invalid audit account identity")
        identities.add(sid(value[name]))
    if len(identities) != 4:
        raise SafetyError("Audit, Review, Merge and operator identities must differ")
    hash_value(value["app_manifest"])
    if not isinstance(value["runtime_root"], str) or not isinstance(value["project_root"], str):
        raise SafetyError("Audit paths must be fixed local paths")
    runtime = PureWindowsPath(value["runtime_root"])
    if runtime.parent != PureWindowsPath(str(AUDIT_ROOT)) / "runtimes":
        raise SafetyError("Fixed audit runtime location required")
    hash_value(runtime.name)
    project = PureWindowsPath(value["project_root"])
    if not project.is_absolute() or str(project).startswith("\\\\"):
        raise SafetyError("Local audit project scope required")
    model = value["model"]
    import re

    if not isinstance(model, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,79}", model):
        raise SafetyError("Pinned audit model identifier required")
    if value["reasoning_effort"] is not None and (
        not isinstance(value["reasoning_effort"], str)
        or value["reasoning_effort"]
        not in {
            None,
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }
    ):
        raise SafetyError("Pinned audit reasoning policy required")
    return dict(value)


class SealedExecutable:
    """Hold a read-only/no-write/no-delete-sharing handle throughout execution.

    Hash in bounded chunks, including the installed372MB CLI. Do not raise the
    small-source reader's allocation limit or trust a hash of different bytes.
    """

    def __init__(self, path: Path, expected: str) -> None:
        hash_value(expected)
        self.native = Native()
        self.handle: Any = None
        path = path.absolute()
        if any(reparse(p) for p in (path, *path.parents)):
            raise SafetyError("Reparse executable rejected")
        kernel = self.native.kernel
        kernel.GetFileInformationByHandleEx.argtypes = [
            w.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            w.DWORD,
        ]
        kernel.GetFileInformationByHandleEx.restype = w.BOOL
        kernel.GetFinalPathNameByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]
        kernel.GetFinalPathNameByHandleW.restype = w.DWORD
        self.handle = kernel.CreateFileW(str(path), 0x20081, 1, None, 3, 0x200000, None)
        if self.handle == ctypes.c_void_p(-1).value:
            self.handle = None
            raise SafetyError("Pinned executable unavailable")
        try:
            attributes = _FileAttributes()
            final = ctypes.create_unicode_buffer(32768)
            length = kernel.GetFinalPathNameByHandleW(self.handle, final, len(final), 0)
            if (
                not kernel.GetFileInformationByHandleEx(
                    self.handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes)
                )
                or attributes.attributes & 0x410
                or not 0 < length < len(final)
                or os.path.normcase(final.value.removeprefix("\\\\?\\"))
                != os.path.normcase(str(path))
            ):
                raise SafetyError("Executable file identity changed")
            require_sealed_acl(*self.native.security(self.handle))
            sha = hashlib.sha256()
            total = 0
            buffer, count = ctypes.create_string_buffer(65536), w.DWORD()
            while True:
                if not kernel.ReadFile(self.handle, buffer, len(buffer), ctypes.byref(count), None):
                    raise SafetyError("Pinned executable read failed")
                if not count.value:
                    break
                total += count.value
                if total > BINARY_LIMIT:
                    raise SafetyError("Pinned executable limit exceeded")
                sha.update(buffer.raw[: count.value])
            if sha.hexdigest() != expected:
                raise SafetyError("Pinned executable hash changed")
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.handle is not None:
            self.native.kernel.CloseHandle(self.handle)
            self.handle = None


class AuditDeployment(Deployment):
    """Structural compatibility with the existing fixed SCM/pipe host."""

    def __init__(self, manifest_hash: str | None = None) -> None:
        raw_settings = protected_bytes(AUDIT_ROOT / "settings.json")
        self.audit_settings = validate_settings(json.loads(raw_settings))
        self.settings = dict(self.audit_settings)
        self.settings["roles"] = {
            "audit": {
                "sid": self.settings["audit_sid"],
                "account": AUDIT_ACCOUNT,
                "service": AUDIT_SERVICE,
            }
        }
        self.runtime = Path(self.settings["runtime_root"])
        self.identity = self.runtime.name
        if manifest_hash is not None and manifest_hash != self.identity:
            raise SafetyError("Audit service artifact changed")
        raw = protected_bytes(self.runtime.parent / (self.identity + ".manifest.json"))
        if hashlib.sha256(raw).hexdigest() != self.identity:
            raise SafetyError("Audit artifact manifest changed")
        self.manifest = json.loads(raw)
        if (
            not isinstance(self.manifest, dict)
            or self.manifest.get("protocol") != "locus-audit-bundle-v1"
            or self.manifest.get("source_clean") is not True
            or self.manifest.get("python_version") != "3.14.10"
            or self.manifest.get("codex_sha256") != CODEX_SHA256
            or self.manifest.get("files", {}).get("codex.exe") != CODEX_SHA256
        ):
            raise SafetyError("Pinned clean audit source required")
        self.leases: list[SealedExecutable] = []

    def require_role(self, role: str) -> None:
        if role != "audit" or Native().current_sid() != self.settings["audit_sid"]:
            raise SafetyError("Dedicated audit account required")
        if (
            Path(sys.executable).absolute() != self.runtime / "python.exe"
            or sys.version.split()[0] != "3.14.10"
            or not sys.flags.isolated
            or not sys.dont_write_bytecode
        ):
            raise SafetyError("Pinned isolated audit interpreter required")
        # Administrator packaging binds the existing App identities. The audit
        # account need not gain access to the App deployment or either state tree.
        # The operator/Review client separately compares current App registration
        # before connecting; changed SIDs cannot authenticate on this fixed pipe.
        expected = self.manifest.get("files")
        if not isinstance(expected, dict) or not 0 < len(expected) <= 5000:
            raise SafetyError("Complete audit artifact inventory required")
        actual = set()
        for item in self.runtime.rglob("*"):
            if reparse(item):
                raise SafetyError("Reparse audit inventory entry rejected")
            if item.is_file():
                actual.add(item.relative_to(self.runtime).as_posix())
        if actual != set(expected):
            raise SafetyError("Audit runtime inventory changed")
        if not self.leases:
            try:
                from loop_engine.security import relative_path

                for name, wanted in expected.items():
                    relative_path(name)
                    self.leases.append(SealedExecutable(self.runtime / name, wanted))
            except BaseException:
                self.close()
                raise

    def clients(self, role: str) -> set[str]:
        if role != "audit":
            raise SafetyError("Fixed audit role required")
        return {self.settings["operator_sid"], self.settings["review_sid"]}

    def close(self) -> None:
        for lease in self.leases:
            lease.close()
        self.leases.clear()

    @property
    def state(self) -> Path:
        return AUDIT_ROOT / "state"

    def state_directory(self, role: str) -> Path:
        if role != "audit":
            raise SafetyError("Fixed audit role required")
        return self.state

    def require_private_state(self) -> None:
        native = Native()
        if not self.state.is_dir() or any(
            reparse(part) for part in (self.state, *self.state.parents)
        ):
            raise SafetyError("Private audit state namespace changed")
        handle = native.kernel.CreateFileW(str(self.state), 0x20000, 3, None, 3, 0x2200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise SafetyError("Audit state permissions unavailable")
        try:
            require_private_acl(*native.security(handle), self.settings["audit_sid"])
        finally:
            native.kernel.CloseHandle(handle)
        # Real denied-access probes, not assertions in an activation receipt.
        for role in ("review", "merge"):
            try:
                (DEPLOYMENT_ROOT / "state" / role / "isolation-canary.txt").read_bytes()
            except PermissionError:
                continue
            raise SafetyError("Audit account can read App service state")
