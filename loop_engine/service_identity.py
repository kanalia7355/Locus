"""System-owned deployment documents and immutable service runtime checks."""

import ctypes
import hashlib
import json
import os
import re
import sys
from ctypes import wintypes as w
from pathlib import Path, PureWindowsPath
from typing import Any

from loop_engine.security import SafetyError, reparse
from loop_engine.windows_pipe import Native, sid

DEPLOYMENT_ROOT = Path("C:/ProgramData/LocusLoopServicesV1")
SYSTEM = "S-1-5-18"
ADMINISTRATORS = "S-1-5-32-544"
READ_EXECUTE = 0x1200A9
FULL_CONTROL = 0x1F01FF
ROLES = {
    "review": ("LocusLoopReviewV1", "locus_loop_review", 5555922, 177234377),
    "merge": ("LocusLoopMergeV1", "locus_loop_merge", 5556060, 177236244),
}


class _FileAttributes(ctypes.Structure):
    _fields_ = [("attributes", w.DWORD), ("tag", w.DWORD)]


def require_sealed_acl(owner: str, control: int, entries: list[tuple[str, int, int]]) -> None:
    if owner != SYSTEM or not control & 0x1000:
        raise SafetyError("System-owned protected service deployment required")
    seen = set()
    for identity, mask, flags in entries:
        if identity in seen or flags:
            raise SafetyError("Unexpected deployment ACL entry")
        seen.add(identity)
        if identity in {SYSTEM, ADMINISTRATORS}:
            if mask != FULL_CONTROL:
                raise SafetyError("Unexpected deployment administrative rights")
        else:
            sid(identity)
            if mask != READ_EXECUTE:
                raise SafetyError("Deployment readers must not be writers")
    if not {SYSTEM, ADMINISTRATORS} <= seen:
        raise SafetyError("Deployment ownership/recovery principals missing")


def protected_bytes(path: Path, *, maximum: int = 4_000_000) -> bytes:
    native = Native()
    path = path.absolute()
    if any(reparse(part) for part in (path, *path.parents)):
        raise SafetyError("Reparse deployment path rejected")
    kernel = native.kernel
    kernel.GetFileInformationByHandleEx.argtypes = [
        w.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        w.DWORD,
    ]
    kernel.GetFileInformationByHandleEx.restype = w.BOOL
    kernel.GetFinalPathNameByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]
    kernel.GetFinalPathNameByHandleW.restype = w.DWORD
    handle = kernel.CreateFileW(str(path), 0x20081, 1, None, 3, 0x200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise SafetyError("Protected deployment document unavailable")
    try:
        attributes = _FileAttributes()
        final = ctypes.create_unicode_buffer(32768)
        size = kernel.GetFinalPathNameByHandleW(handle, final, len(final), 0)
        if (
            not kernel.GetFileInformationByHandleEx(
                handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes)
            )
            or attributes.attributes & 0x410  # No reparse point or directory.
            or not 0 < size < len(final)
            or os.path.normcase(final.value.removeprefix("\\\\?\\")) != os.path.normcase(str(path))
        ):
            raise SafetyError("Deployment file identity unavailable")
        require_sealed_acl(*native.security(handle))
        result = bytearray()
        while True:
            data, count = ctypes.create_string_buffer(65536), w.DWORD()
            if not kernel.ReadFile(handle, data, len(data), ctypes.byref(count), None):
                raise SafetyError("Protected deployment read failed")
            if not count.value:
                break
            result.extend(data.raw[: count.value])
            if len(result) > maximum:
                raise SafetyError("Protected deployment size exceeded")
        return bytes(result)
    finally:
        kernel.CloseHandle(handle)


def validate_settings(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value)
        != {"protocol", "mode", "project_root", "runtime_root", "operator_sid", "roles"}
        or value["protocol"] != "locus-services-v1"
        or value["mode"] != "prepare"
        or not isinstance(value["roles"], dict)
        or set(value["roles"]) != set(ROLES)
    ):
        raise SafetyError("Unsupported service configuration; activation is not implemented")
    if any(
        not isinstance(value[key], str) for key in ("operator_sid", "project_root", "runtime_root")
    ):
        raise SafetyError("Invalid deployment identity fields")
    identities = {sid(value["operator_sid"])}
    runtime = PureWindowsPath(value["runtime_root"])
    if runtime.parent != PureWindowsPath(str(DEPLOYMENT_ROOT)) / "runtimes" or not re.fullmatch(
        r"[a-f0-9]{64}", runtime.name
    ):
        raise SafetyError("Fixed versioned service location required")
    project = PureWindowsPath(value["project_root"])
    if not project.is_absolute() or str(project).startswith("\\\\"):
        raise SafetyError("Local project scope required")
    for role, (service, account, app_id, installation) in ROLES.items():
        record = value["roles"][role]
        if (
            not isinstance(record, dict)
            or set(record) != {"sid", "service", "account", "app_id", "installation_id"}
            or record["service"] != service
            or record["account"] != account
            or type(record["app_id"]) is not int
            or record["app_id"] != app_id
            or type(record["installation_id"]) is not int
            or record["installation_id"] != installation
        ):
            raise SafetyError("Fixed role/App identity required")
        if not isinstance(record["sid"], str):
            raise SafetyError("Invalid service account identity")
        identities.add(sid(record["sid"]))
    if len(identities) != 3:
        raise SafetyError("Operator and both services must have different identities")
    return dict(value)


class Deployment:
    def __init__(self, manifest_hash: str | None = None) -> None:
        settings = protected_bytes(DEPLOYMENT_ROOT / "settings.json")
        self.settings = validate_settings(json.loads(settings))
        self.runtime = Path(self.settings["runtime_root"])
        self.identity = self.runtime.name
        raw = protected_bytes(self.runtime.parent / (self.identity + ".manifest.json"))
        if hashlib.sha256(raw).hexdigest() != self.identity or (
            manifest_hash is not None and manifest_hash != self.identity
        ):
            raise SafetyError("Service artifact identity changed")
        self.manifest = json.loads(raw)
        if (
            not isinstance(self.manifest, dict)
            or self.manifest.get("protocol") != "locus-service-bundle-v1"
            or self.manifest.get("python_version") != "3.14.10"
            or self.manifest.get("source_clean") is not True
        ):
            raise SafetyError("Uncommitted service artifacts cannot be deployed")

    def require_role(self, role: str) -> None:
        if role not in ROLES or Native().current_sid() != self.settings["roles"][role]["sid"]:
            raise SafetyError("Isolated service account required")
        if Path(sys.executable).absolute() != self.runtime / "python.exe":
            raise SafetyError("Pinned service interpreter required")
        if (
            sys.version.split()[0] != "3.14.10"
            or not sys.flags.isolated
            or not sys.dont_write_bytecode
        ):
            raise SafetyError("Isolated patched service runtime required")
        expected = self.manifest.get("files", {})
        if not isinstance(expected, dict) or not expected or len(expected) > 5000:
            raise SafetyError("Complete artifact file inventory required")
        actual = {
            path.relative_to(self.runtime).as_posix()
            for path in self.runtime.rglob("*")
            if path.is_file()
        }
        if actual != set(expected):
            raise SafetyError("Service runtime file inventory changed")
        for name, digest in expected.items():
            if not re.fullmatch(r"[A-Za-z0-9_./-]+", name) or ".." in name:
                raise SafetyError("Invalid service artifact path")
            data = protected_bytes(self.runtime / name, maximum=64_000_000)
            if hashlib.sha256(data).hexdigest() != digest:
                raise SafetyError("Pinned service code/dependency changed")

    def clients(self, role: str) -> set[str]:
        values = {self.settings["operator_sid"]}
        if role == "merge":
            values.add(self.settings["roles"]["review"]["sid"])
        return values

    def state_directory(self, role: str) -> Path:
        if role not in ROLES:
            raise SafetyError("Fixed preparation role required")
        return DEPLOYMENT_ROOT / "state" / role
