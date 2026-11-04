"""Metadata-only admission of an explicitly registered EXISTING auth file.

No credential data access, parsing, copy, export, config write or auth operation.
The official CLI alone may later consume the file under separate live permission.
"""

import ctypes
import re
import threading
from pathlib import Path
from typing import Any

from loop_engine.security import SafetyError, fingerprint, reparse
from loop_engine.windows_pipe import Native


class _Time(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


class _Info(ctypes.Structure):
    _fields_ = [
        ("attributes", ctypes.c_uint32),
        ("created", _Time),
        ("accessed", _Time),
        ("written", _Time),
        ("volume", ctypes.c_uint32),
        ("size_high", ctypes.c_uint32),
        ("size_low", ctypes.c_uint32),
        ("links", ctypes.c_uint32),
        ("index_high", ctypes.c_uint32),
        ("index_low", ctypes.c_uint32),
    ]


def _metadata(path: Path) -> dict[str, Any]:
    """READ_CONTROL|FILE_READ_ATTRIBUTES only; never FILE_READ_DATA/GENERIC_READ."""
    from ctypes import wintypes as w

    if any(reparse(part) for part in (path, *path.parents)):
        raise SafetyError("Existing auth path traverses reparse boundary")
    native = Native()
    kernel = native.kernel
    kernel.GetDriveTypeW.argtypes = [w.LPCWSTR]
    kernel.GetDriveTypeW.restype = w.UINT
    if not re.fullmatch(r"[A-Za-z]:", path.drive) or kernel.GetDriveTypeW(path.anchor) != 3:
        raise SafetyError("Existing auth file must be on the local fixed drive")
    handle = kernel.CreateFileW(str(path), 0x20080, 7, None, 3, 0x2200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise SafetyError("Existing auth metadata unavailable")
    try:
        return _held_metadata(native, handle, path)
    finally:
        kernel.CloseHandle(handle)


def _held_metadata(
    native: Any, handle: Any, path: Path, *, directory: bool = False, empty: bool = False
) -> dict[str, Any]:
    from ctypes import wintypes as w

    kernel = native.kernel

    kernel.GetFileType.argtypes = [w.HANDLE]
    kernel.GetFileType.restype = w.DWORD
    kernel.GetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.POINTER(_Info)]
    kernel.GetFileInformationByHandle.restype = w.BOOL
    kernel.GetFinalPathNameByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]
    kernel.GetFinalPathNameByHandleW.restype = w.DWORD
    info = _Info()
    if kernel.GetFileType(handle) != 1 or not kernel.GetFileInformationByHandle(
        handle, ctypes.byref(info)
    ):
        raise SafetyError("Regular existing auth metadata required")
    allowed = 0x1 | 0x2 | 0x4 | 0x20 | 0x80 | 0x800 | 0x2000 | 0x4000
    size = (info.size_high << 32) | info.size_low
    if (
        info.attributes & ~(allowed | (0x10 if directory else 0))
        or info.links != 1
        or bool(info.attributes & 0x10) != directory
        or (not directory and not (0 <= size <= 65536 if empty else 0 < size <= 65536))
        or (info.index_high << 32) | info.index_low == 0
    ):
        raise SafetyError("Existing auth file attributes/links/size rejected")
    final = ctypes.create_unicode_buffer(32768)
    length = kernel.GetFinalPathNameByHandleW(handle, final, len(final), 0)
    if not 0 < length < len(final) or final.value.casefold() != ("\\\\?\\" + str(path)).casefold():
        raise SafetyError("Existing auth handle path identity differs")
    security = native.security(handle, kind=1)
    if any(reparse(part) for part in (path, *path.parents)):
        raise SafetyError("Existing auth path changed during metadata query")
    return {
        "identity": {
            "volume": info.volume,
            "index": (info.index_high << 32) | info.index_low,
            "size": size,
            "created": (info.created.high << 32) | info.created.low,
            "written": (info.written.high << 32) | info.written.low,
            "attributes": info.attributes,
            "links": info.links,
        },
        "security": security,
    }


def private_acl(security: tuple[str, int, list[tuple[str, int, int]]], sid: str) -> None:
    """Conservative effective allow-only DACL; Native rejects deny/object/unknown ACEs."""
    owner, control, entries = security
    trusted = {sid, "S-1-5-18", "S-1-5-32-544"}
    if owner != sid or not control & 4 or not entries:
        raise SafetyError("Existing auth/profile owner or DACL is not established")
    readable = False
    for identity, mask, flags in entries:
        if identity not in trusted or flags & ~0x1F:
            raise SafetyError("Existing auth/profile grants an unapproved principal")
        if identity == sid and not flags & 8 and mask & (1 | 0x80000000 | 0x10000000):
            readable = True
    if not readable:
        raise SafetyError("Existing auth/profile lacks operator data-read permission")


def inspect_existing(home: Path, sid: str, runtime: Any = None) -> dict[str, Any]:
    from loop_engine.c_min_runtime import file_security

    # This narrow exception is for the existing local operator profile, not
    # arbitrary shared/network credential directories selected by model output.
    operator_home = Path.home().absolute()
    if not home.is_relative_to(operator_home) or any(
        reparse(p) for p in (home / "auth.json", home, *home.parents)
    ):
        raise SafetyError("Existing auth home is outside the private operator profile")
    observed = _metadata(home / "auth.json")
    private_acl(observed["security"], sid)
    if runtime is not None and not observed["security"][1] & 0x1000:
        raise SafetyError("Credential DACL must be protected")
    protection = {"auth_file": fingerprint(observed["security"])}
    for label, path in (("home", home), ("config", home / "config.toml")):
        security = file_security(path)
        if label == "home" and runtime is not None:
            runtime.validate(path, True, security)
        else:
            private_acl(security, sid)
            if runtime is not None and not security[1] & 0x1000:
                raise SafetyError("Config DACL must be protected")
        protection[label] = fingerprint(security)
    trusted = {sid, "S-1-5-18", "S-1-5-32-544"}
    dangerous = 0x10000000 | 0x40000000 | 0xD0156
    for parent in home.parents:
        if not parent.is_relative_to(operator_home):
            break
        security = file_security(parent)
        if security[0] not in trusted or not security[1] & 4:
            raise SafetyError("Auth ancestor owner/DACL is not trusted")
        for identity, mask, flags in security[2]:
            if flags & ~0x1F or (not flags & 8 and identity not in trusted and mask & dangerous):
                raise SafetyError("Auth ancestor can be changed by an unapproved principal")
        protection["ancestor:" + str(parent)] = fingerprint(security)
    if _metadata(home / "auth.json") != observed:
        raise SafetyError("Auth metadata changed during inspection")
    return {"file_identity": observed["identity"], "protection": protection}


# Unknown process settlement retains leases until this controller exits. There
# is no production reset/retry API; the durable invocation is held as well.
_QUARANTINE: list[Any] = []
# Public owner-approved offline capability scope, never a live invocation permit.
# pragma: allowlist nextline secret
LEASE_APPROVAL = "4adfaee16009ab0c9112ef0e974d3243b338013e8a910d4eba16cf1f3e0307c4"


class CredentialLease:
    """No-data, no-delete handles through the complete contained CLI call.

    FILE_EXECUTE/TRAVERSE is solely the Windows sharing-class capability. These
    handles are never executed, mapped, transferred or used for file contents.
    """

    def __init__(self, home: Path, sid: str, expected: dict[str, Any], runtime: Any = None):
        if expected.get("lease_approval") != LEASE_APPROVAL:
            raise SafetyError("Explicit credential lifetime capability approval required")
        if _QUARANTINE:
            raise SafetyError("Unsettled credential lifetime requires owner reconciliation")
        self.native, self.home, self.sid, self.runtime = Native(), home, sid, runtime
        self.lock = threading.RLock()
        self.held: list[tuple[Path, Any, bool, dict[str, Any]]] = []
        self.failed, self.unsettled, self.closed = False, False, False
        try:
            paths = [(home, True), (home / "auth.json", False), (home / "config.toml", False)]
            if runtime is not None:
                paths += [(home / "tmp", True), (home / "tmp/arg0-windows", True)]
            for path, directory in paths:
                if any(reparse(p) for p in (path, *path.parents)):
                    raise SafetyError("Credential lifetime reparse boundary")
                from ctypes import wintypes as w

                kernel = self.native.kernel
                kernel.GetDriveTypeW.argtypes, kernel.GetDriveTypeW.restype = [w.LPCWSTR], w.UINT
                if (
                    not re.fullmatch(r"[A-Za-z]:", path.drive)
                    or kernel.GetDriveTypeW(path.anchor) != 3
                ):
                    raise SafetyError("Local fixed credential lifetime required")
                handle = kernel.CreateFileW(str(path), 0x200A0, 3, None, 3, 0x2200000, None)
                if handle == ctypes.c_void_p(-1).value:
                    raise SafetyError("Credential metadata lease unavailable")
                self.held.append((path, handle, directory, {}))
                observed = self._observe(path, handle, directory)
                self.held[-1] = (path, handle, directory, observed)
                label = (
                    "auth_file"
                    if path.name == "auth.json"
                    else "config"
                    if path.name == "config.toml"
                    else "home"
                    if path == home
                    else None
                )
                if (
                    label is not None
                    and fingerprint(observed["security"]) != expected["protection"][label]
                ):
                    raise SafetyError("Registered credential protection differs")
                if path.name == "auth.json" and observed["identity"] != expected["file_identity"]:
                    raise SafetyError("Registered credential identity differs")
            self.check()
        except BaseException:
            self.close()
            raise

    def _observe(self, path: Path, handle: Any, directory: bool) -> dict[str, Any]:
        value = _held_metadata(
            self.native, handle, path, directory=directory, empty=path.name == "config.toml"
        )
        if directory and self.runtime is not None:
            self.runtime.validate(path, True, value["security"])
        else:
            private_acl(value["security"], self.sid)
            if self.runtime is not None and not value["security"][1] & 0x1000:
                raise SafetyError("Credential/config protection is not fixed")
        if directory:
            value["identity"] = {
                k: v for k, v in value["identity"].items() if k not in {"size", "written"}
            }
        return value

    def check(self) -> None:
        with self.lock:
            if self.failed or self.closed:
                raise SafetyError("Credential lease is no longer valid")
            try:
                for path, handle, directory, initial in self.held:
                    if self._observe(path, handle, directory) != initial:
                        raise SafetyError("Credential lifetime identity or ACL changed")
            except BaseException:
                self.failed = True
                raise

    def launch_started(self) -> None:
        self.check()
        self.unsettled = True

    def process_finished(self, settled: bool | None) -> None:
        if settled is not True:
            raise SafetyError("CLI process tree settlement is unknown")
        self.unsettled = False
        self.check()

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            if self.unsettled:
                if self not in _QUARANTINE:
                    _QUARANTINE.append(self)
                raise SafetyError("Credential handles retained for unknown CLI lifetime")
            for _, handle, _, _ in self.held:
                self.native.kernel.CloseHandle(handle)
            self.held.clear()
            self.closed = True
