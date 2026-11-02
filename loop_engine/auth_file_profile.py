"""Metadata-only admission of an explicitly registered EXISTING auth file.

No credential data access, parsing, copy, export, config write or auth operation.
The official CLI alone may later consume the file under separate live permission.
"""

import ctypes
import re
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
            info.attributes & ~allowed
            or info.links != 1
            or not 0 < size <= 65536
            or (info.index_high << 32) | info.index_low == 0
        ):
            raise SafetyError("Existing auth file attributes/links/size rejected")
        final = ctypes.create_unicode_buffer(32768)
        length = kernel.GetFinalPathNameByHandleW(handle, final, len(final), 0)
        if (
            not 0 < length < len(final)
            or final.value.casefold() != ("\\\\?\\" + str(path)).casefold()
        ):
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
    finally:
        kernel.CloseHandle(handle)


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


def inspect_existing(home: Path, sid: str) -> dict[str, Any]:
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
    protection = {"auth_file": fingerprint(observed["security"])}
    for label, path in (("home", home), ("config", home / "config.toml")):
        security = file_security(path)
        private_acl(security, sid)
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
