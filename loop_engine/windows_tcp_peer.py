"""Authenticate a loopback TCP writer by kernel TCP owner PID and process SID.

The ephemeral audit relay must not accept another local user's fake capability
probe or inference. No headers, tokens or process command lines are inspected.
"""

import ctypes
import socket
import struct
from ctypes import wintypes as w
from typing import Any

from loop_engine.security import SafetyError
from loop_engine.windows_pipe import Native, sid


class OwnedCliPeer:
    """Retain the exact suspended CLI identity through the relay's lifetime."""

    def __init__(self, binary: str) -> None:
        self.binary = binary
        self.native = Native()
        self.pid: int | None = None
        self.process: Any = None
        self.job: Any = None
        self.creation: int | None = None
        self.owner = self.native.current_sid()

    def bind(self, pid: int, job: Any) -> None:
        from pathlib import Path

        if self.process is not None:
            raise SafetyError("Owned CLI already bound")
        kernel = self.native.kernel
        kernel.OpenProcess.restype = w.HANDLE
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            raise SafetyError("Owned CLI identity unavailable")
        self.process, self.pid, self.job = handle, pid, job
        try:
            kernel.QueryFullProcessImageNameW.argtypes = [
                w.HANDLE,
                w.DWORD,
                w.LPWSTR,
                ctypes.POINTER(w.DWORD),
            ]
            name, size = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
            if (
                not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size))
                or Path(name.value).resolve() != Path(self.binary).resolve()
            ):
                raise SafetyError("Owned process image differs")
            self.creation = self._creation()
            self._require_active()
        except BaseException:
            self.close()
            raise

    def _creation(self) -> int:
        kernel = self.native.kernel
        kernel.GetProcessTimes.argtypes = [w.HANDLE, *([ctypes.POINTER(w.FILETIME)] * 4)]
        values = [w.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(self.process, *(ctypes.byref(x) for x in values)):
            raise SafetyError("Owned process time unavailable")
        return int(values[0].dwHighDateTime) << 32 | int(values[0].dwLowDateTime)

    def _require_active(self) -> None:
        kernel = self.native.kernel
        inside, code = w.BOOL(), w.DWORD()
        kernel.IsProcessInJob.argtypes = [w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)]
        kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
        if (
            not self.process
            or not self.job
            or not self.job.handle
            or not kernel.IsProcessInJob(self.process, self.job.handle, ctypes.byref(inside))
            or not inside.value
            or not kernel.GetExitCodeProcess(self.process, ctypes.byref(code))
            or code.value != 259
            or self._creation() != self.creation
        ):
            raise SafetyError("Owned CLI lifetime changed")

    def __call__(self, connection: socket.socket) -> bool:
        self._require_active()
        if self.pid is None:
            raise SafetyError("CLI peer not bound")
        require_loopback_peer(connection, self.owner, expected_pid=self.pid)
        self._require_active()
        return True

    def close(self) -> None:
        if self.process:
            self.native.kernel.CloseHandle(self.process)
            self.process = None


class _Row(ctypes.Structure):
    _fields_ = [
        (name, w.DWORD)
        for name in ("state", "local_address", "local_port", "remote_address", "remote_port", "pid")
    ]


def require_loopback_peer(
    connection: socket.socket,
    expected_sid: str,
    *,
    expected_pid: int | None = None,
) -> bool:
    sid(expected_sid)
    local, remote = connection.getsockname(), connection.getpeername()
    if local[0] != "127.0.0.1" or remote[0] != "127.0.0.1":
        raise SafetyError("Only local audit client accepted")
    native = Native()
    ip = vars(ctypes)["WinDLL"]("iphlpapi", use_last_error=True)
    ip.GetExtendedTcpTable.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(w.DWORD),
        w.BOOL,
        w.ULONG,
        ctypes.c_int,
        w.ULONG,
    ]
    ip.GetExtendedTcpTable.restype = w.DWORD
    size = w.DWORD()
    if ip.GetExtendedTcpTable(None, ctypes.byref(size), False, 2, 5, 0) != 122:
        raise SafetyError("Local TCP identity table unavailable")
    if not 4 <= size.value <= 2 * 1024 * 1024:
        raise SafetyError("Local TCP table limit exceeded")
    buffer = ctypes.create_string_buffer(size.value)
    if ip.GetExtendedTcpTable(buffer, ctypes.byref(size), False, 2, 5, 0):
        raise SafetyError("Local TCP identity changed")
    count = ctypes.cast(buffer, ctypes.POINTER(w.DWORD))[0]
    if 4 + count * ctypes.sizeof(_Row) > size.value:
        raise SafetyError("Local TCP identity table truncated")
    pids = []
    for index in range(count):
        row = _Row.from_buffer_copy(buffer, 4 + index * ctypes.sizeof(_Row))
        if (
            row.state == 5
            and socket.inet_ntoa(struct.pack("<I", row.local_address)) == remote[0]
            and socket.inet_ntoa(struct.pack("<I", row.remote_address)) == local[0]
            and socket.ntohs(row.local_port & 65535) == remote[1]
            and socket.ntohs(row.remote_port & 65535) == local[1]
        ):
            pids.append(row.pid)
    if len(pids) != 1 or pids[0] <= 0:
        raise SafetyError("Unique connected audit client required")
    if expected_pid is not None and pids[0] != expected_pid:
        raise SafetyError("Connected client is not the owned CLI")
    native.kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    native.kernel.OpenProcess.restype = w.HANDLE
    process = native.kernel.OpenProcess(0x1000, False, pids[0])
    if not process:
        raise SafetyError("Audit client process identity unavailable")
    token = w.HANDLE()
    try:
        if not native.advapi.OpenProcessToken(process, 8, ctypes.byref(token)):
            raise SafetyError("Audit client token unavailable")
        if native.token_sid(token) != expected_sid:
            raise SafetyError("Audit client belongs to another account")
        return True
    finally:
        if token:
            native.kernel.CloseHandle(token)
        native.kernel.CloseHandle(process)
