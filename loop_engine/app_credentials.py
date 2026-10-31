"""Windows Credential Manager only; never a plaintext/file fallback."""

import ctypes
import sys
from ctypes import wintypes
from typing import Any

from loop_engine.security import SafetyError


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class WindowsAppVault:
    """Account-local vault, deliberately unavailable on other platforms.

    This is storage protection, not isolation from other processes of the same
    Windows user. The signer still requires an isolated trusted service account
    before activation; a vault alone does not attest that boundary.
    """

    _api: Any
    _last_error: Any

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise SafetyError("Windows credential manager required; no file fallback")
        api: Any = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self._last_error = ctypes.get_last_error
        api.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_Credential)),
        ]
        api.CredReadW.restype = wintypes.BOOL
        api.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        api.CredFree.restype = None
        self._api = api

    @staticmethod
    def _target(role: str, app_id: int) -> str:
        if role not in {"review", "merge"} or type(app_id) is not int or app_id <= 0:
            raise SafetyError("Invalid credential identity")
        return f"Locus/Apps/{role}/{app_id}"

    def put(self, role: str, app_id: int, value: bytes) -> None:
        target = self._target(role, app_id)
        if not value or len(value) > 2560:
            raise SafetyError("Credential exceeds supported vault limit")
        # Never silently replace/rotate an existing key.
        if self.get(role, app_id) is not None:
            raise SafetyError("Credential exists; explicit rotation procedure required")
        blob = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
        credential = _Credential()
        credential.Type, credential.Persist = 1, 2
        credential.TargetName = target
        credential.UserName = "Locus GitHub App"
        credential.CredentialBlobSize = len(value)
        credential.CredentialBlob = blob
        try:
            if not self._api.CredWriteW(ctypes.byref(credential), 0):
                raise SafetyError("Credential manager write failed")
        finally:
            ctypes.memset(blob, 0, len(value))

    def get(self, role: str, app_id: int) -> bytes | None:
        target = self._target(role, app_id)
        pointer = ctypes.POINTER(_Credential)()
        if not self._api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
            if self._last_error() == 1168:
                return None
            raise SafetyError("Credential manager read failed")
        try:
            return ctypes.string_at(
                pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize
            )
        finally:
            self._api.CredFree(pointer)
