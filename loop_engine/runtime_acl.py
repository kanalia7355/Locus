"""Owner-registered read-only runtime ACL admission, never credential admission."""

import ctypes
import re
from ctypes import wintypes as w
from pathlib import Path
from typing import Any

from loop_engine.auth_file_profile import private_acl
from loop_engine.security import SafetyError
from loop_engine.windows_pipe import Native

VERSION = "c-min-readonly-runtime-v1"
# Public owner-approved proposal integrity reference, not authentication material.
# pragma: allowlist nextline secret
APPROVAL = "e100391c12ca9bb434fb817a5a3999ea5e7e489316d12df6382c5f1f107ea000"
RX = 0x1200A9


def policy(value: Any) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "approval", "group_sid"}
        or value["version"] != VERSION
        or value["approval"] != APPROVAL
        or not isinstance(value["group_sid"], str)
        or not re.fullmatch(r"S-1-5-21(?:-[0-9]{1,10}){4}", value["group_sid"])
        or any(int(x) > 0xFFFFFFFF for x in value["group_sid"].split("-")[4:])
    ):
        raise SafetyError("Exact approved runtime ACL policy required")
    return dict(value)


def local_sandbox_group() -> str:
    """Resolve only the local machine's named alias; no credentials or account writes."""
    native = Native()
    get_name = native.kernel.GetComputerNameW
    get_name.argtypes, get_name.restype = [w.LPWSTR, ctypes.POINTER(w.DWORD)], w.BOOL
    name, length = ctypes.create_unicode_buffer(256), w.DWORD(256)
    if not get_name(name, ctypes.byref(length)) or not name.value:
        raise SafetyError("Local machine identity unavailable")
    lookup = native.advapi.LookupAccountNameW
    lookup.argtypes = [
        w.LPCWSTR,
        w.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(w.DWORD),
        w.LPWSTR,
        ctypes.POINTER(w.DWORD),
        ctypes.POINTER(w.DWORD),
    ]
    lookup.restype = w.BOOL
    account = name.value + "\\CodexSandboxUsers"
    size, domain_size, kind = w.DWORD(), w.DWORD(), w.DWORD()
    lookup(
        None, account, None, ctypes.byref(size), None, ctypes.byref(domain_size), ctypes.byref(kind)
    )
    if not 0 < size.value <= 68 or not 0 < domain_size.value <= 256:
        raise SafetyError("Registered local sandbox alias unavailable")
    data, domain = (
        ctypes.create_string_buffer(size.value),
        ctypes.create_unicode_buffer(domain_size.value),
    )
    if (
        not lookup(
            None,
            account,
            data,
            ctypes.byref(size),
            domain,
            ctypes.byref(domain_size),
            ctypes.byref(kind),
        )
        or kind.value != 4  # SidTypeAlias, never an arbitrary user/domain group.
        or domain.value.casefold() != name.value.casefold()
    ):
        raise SafetyError("Local sandbox group identity differs")
    return native.string_sid(data)


class RuntimeAcl:
    def __init__(self, home: Path, owner: str, registered: Any) -> None:
        self.home, self.owner = home, owner
        self.group = policy(registered)["group_sid"]
        if self.group in {owner, "S-1-5-18", "S-1-5-32-544"}:
            raise SafetyError("Runtime group cannot be a trusted credential principal")

    def validate(
        self, path: Path, directory: bool, security: tuple[str, int, list[tuple[str, int, int]]]
    ) -> None:
        base = self.home / "tmp/arg0-windows"
        fresh = path if directory else path.parent
        exact_fresh = fresh.parent == base and re.fullmatch(r"codex-arg0[A-Za-z0-9]{6}", fresh.name)
        if not (
            directory
            and path in {self.home, self.home / "tmp", base}
            or exact_fresh
            and (directory or path.name in {".lock", "apply_patch.bat", "applypatch.bat"})
        ):
            raise SafetyError("Unassessed runtime ACL path")
        owner, control, entries = security
        groups = [(mask, flags) for sid, mask, flags in entries if sid == self.group]
        if any(
            type(mask) is not int
            or type(flags) is not int
            or mask & ~RX
            or mask <= 0
            or flags & ~0x1F
            for mask, flags in groups
        ):
            raise SafetyError("Runtime sandbox group has unapproved rights or flags")
        if len(groups) > 1:
            raise SafetyError("Duplicate runtime sandbox grants")
        if path == self.home and (not control & 0x1000 or groups != [(RX, 0)]):
            raise SafetyError("Runtime home requires protected non-inheriting group RX")
        private_acl(
            (
                owner,
                control,
                [(sid, mask, flags) for sid, mask, flags in entries if sid != self.group],
            ),
            self.owner,
        )
