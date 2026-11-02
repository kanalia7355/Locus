"""Exercise actual peer-check logic through synthetic Windows API tables."""

import ctypes
import socket
import struct
from types import SimpleNamespace
from typing import Any

import pytest

import loop_engine.windows_tcp_peer as peer_module
from loop_engine.security import SafetyError


class Function:
    def __init__(self, call: Any):
        self.call = call

    def __call__(self, *args: Any) -> Any:
        return self.call(*args)


@pytest.mark.parametrize("failure", ["pid", "sid", "no_connection"])
def test_real_tcp_owner_checker_rejects_synthetic_kernel_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    expected = "S-1-5-21-111-222-333-1001"

    # Windows DWORD is 32-bit even when CI's host ctypes.c_ulong is 64-bit.
    # Simulate the Windows API ABI, not the Linux host's wintypes aliases.
    class Row(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint32)
            for name in (
                "state",
                "local_address",
                "local_port",
                "remote_address",
                "remote_port",
                "pid",
            )
        ]

    monkeypatch.setattr(peer_module, "_Row", Row)
    monkeypatch.setattr(
        peer_module,
        "w",
        SimpleNamespace(
            DWORD=ctypes.c_uint32,
            ULONG=ctypes.c_uint32,
            BOOL=ctypes.c_int32,
            HANDLE=ctypes.c_void_p,
        ),
    )
    opened = []
    closed = []

    def table(buffer: Any, size: Any, *_: Any) -> int:
        count = 0 if failure == "no_connection" else 1
        size._obj.value = 4 + ctypes.sizeof(peer_module._Row) * count
        if buffer is None:
            return 122
        ctypes.memmove(buffer, struct.pack("<I", count), 4)
        if count:
            row = peer_module._Row()
            row.state = 5
            row.local_address = row.remote_address = struct.unpack(
                "<I", socket.inet_aton("127.0.0.1")
            )[0]
            row.local_port, row.remote_port = socket.htons(4444), socket.htons(5555)
            row.pid = 999 if failure == "pid" else 123
            ctypes.memmove(ctypes.addressof(buffer) + 4, ctypes.byref(row), ctypes.sizeof(row))
        return 0

    def open_process(*args: Any) -> int:
        opened.append(args[-1])
        return 321

    def token(handle: Any, access: Any, output: Any) -> bool:
        output._obj.value = 456
        return True

    native = SimpleNamespace(
        kernel=SimpleNamespace(
            OpenProcess=Function(open_process), CloseHandle=lambda value: closed.append(value)
        ),
        advapi=SimpleNamespace(OpenProcessToken=Function(token)),
        token_sid=lambda _: "S-1-5-21-111-222-333-1002",
    )
    monkeypatch.setattr(peer_module, "Native", lambda: native)
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *a, **k: SimpleNamespace(GetExtendedTcpTable=Function(table)),
        raising=False,
    )
    connection = SimpleNamespace(
        getsockname=lambda: ("127.0.0.1", 5555), getpeername=lambda: ("127.0.0.1", 4444)
    )
    with pytest.raises(SafetyError):
        peer_module.require_loopback_peer(connection, expected, expected_pid=123)
    assert opened == ([123] if failure == "sid" else [])
    if failure == "sid":
        assert len(closed) == 2


@pytest.mark.parametrize("failure", ["job", "creation", "exited"])
def test_retained_process_checker_reads_job_creation_and_exit_state(failure: str) -> None:
    def in_job(process: Any, job: Any, result: Any) -> bool:
        result._obj.value = failure != "job"
        return True

    def exit_code(process: Any, result: Any) -> bool:
        result._obj.value = 0 if failure == "exited" else 259
        return True

    def times(process: Any, created: Any, *_: Any) -> bool:
        created._obj.dwLowDateTime = 2 if failure == "creation" else 1
        created._obj.dwHighDateTime = 0
        return True

    peer = object.__new__(peer_module.OwnedCliPeer)
    peer.process, peer.creation = 321, 1
    peer.job = SimpleNamespace(handle=777)
    peer.native = SimpleNamespace(
        kernel=SimpleNamespace(
            IsProcessInJob=Function(in_job),
            GetExitCodeProcess=Function(exit_code),
            GetProcessTimes=Function(times),
        )
    )
    with pytest.raises(SafetyError, match="lifetime"):
        peer._require_active()
