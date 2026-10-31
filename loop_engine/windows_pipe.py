"""Local, SID-authenticated, bounded named-pipe messages. Never an API proxy.

Clients verify kernel-reported owner AND the complete protected DACL before
writing. Client grants exclude FILE_CREATE_PIPE_INSTANCE. The server identifies
the actual writer using an identification-only impersonation token. Neither
endpoint logs request/response contents. Production still needs isolated SIDs.
"""

import ctypes
import json
import re
import struct
import sys
import time
from collections.abc import Callable
from ctypes import wintypes as w
from typing import Any
from uuid import uuid4

from loop_engine.security import SafetyError

CLIENT_RIGHTS = 0x120183  # read/write data, attributes, READ_CONTROL, SYNCHRONIZE; never bit4
SERVER_RIGHTS = 0x1F01FF
MAX_MESSAGE = 65536


class ServiceIdentityLost(BaseException):
    """Fatal: a service host must exit rather than continue impersonating."""


class _Attributes(ctypes.Structure):
    _fields_ = [("length", w.DWORD), ("descriptor", ctypes.c_void_p), ("inherit", w.BOOL)]


class _AclSize(ctypes.Structure):
    _fields_ = [("count", w.DWORD), ("used", w.DWORD), ("free", w.DWORD)]


def pipe_name(name: str) -> str:
    if not re.fullmatch(r"Locus-(?:review-v1|merge-v1|test-[0-9a-f]{32})", name):
        raise SafetyError("Unsupported local service endpoint")
    return "\\\\.\\pipe\\" + name


def sid(value: str) -> str:
    if not re.fullmatch(
        r"S-1-(?:5-(?:21(?:-[0-9]{1,10}){4}|80(?:-[0-9]{1,10}){5})"
        r"|12-1(?:-[0-9]{1,10}){4})",
        value,
    ) or any(int(part) > 0xFFFFFFFF for part in value.split("-")[3:]):
        raise SafetyError("Invalid explicit service SID")
    return value


class Native:
    kernel: Any
    advapi: Any

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise SafetyError("Windows local service transport required")
        self.kernel = vars(ctypes)["WinDLL"]("kernel32", use_last_error=True)
        self.advapi = vars(ctypes)["WinDLL"]("advapi32", use_last_error=True)
        self.error: Callable[[], int] = vars(ctypes)["get_last_error"]
        signatures: list[tuple[Any, str, Any, list[Any]]] = [
            (self.kernel, "GetCurrentProcess", w.HANDLE, []),
            (self.kernel, "GetCurrentThread", w.HANDLE, []),
            (self.kernel, "CloseHandle", w.BOOL, [w.HANDLE]),
            (self.kernel, "LocalFree", ctypes.c_void_p, [ctypes.c_void_p]),
            (
                self.kernel,
                "CreateNamedPipeW",
                w.HANDLE,
                [
                    w.LPCWSTR,
                    w.DWORD,
                    w.DWORD,
                    w.DWORD,
                    w.DWORD,
                    w.DWORD,
                    w.DWORD,
                    ctypes.POINTER(_Attributes),
                ],
            ),
            (self.kernel, "ConnectNamedPipe", w.BOOL, [w.HANDLE, ctypes.c_void_p]),
            (self.kernel, "DisconnectNamedPipe", w.BOOL, [w.HANDLE]),
            (
                self.kernel,
                "CreateFileW",
                w.HANDLE,
                [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE],
            ),
            (
                self.kernel,
                "SetNamedPipeHandleState",
                w.BOOL,
                [w.HANDLE, ctypes.POINTER(w.DWORD), ctypes.c_void_p, ctypes.c_void_p],
            ),
            (
                self.kernel,
                "ReadFile",
                w.BOOL,
                [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p],
            ),
            (
                self.kernel,
                "WriteFile",
                w.BOOL,
                [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p],
            ),
            (
                self.advapi,
                "OpenProcessToken",
                w.BOOL,
                [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)],
            ),
            (
                self.advapi,
                "OpenThreadToken",
                w.BOOL,
                [w.HANDLE, w.DWORD, w.BOOL, ctypes.POINTER(w.HANDLE)],
            ),
            (
                self.advapi,
                "GetTokenInformation",
                w.BOOL,
                [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)],
            ),
            (
                self.advapi,
                "ConvertSidToStringSidW",
                w.BOOL,
                [ctypes.c_void_p, ctypes.POINTER(w.LPWSTR)],
            ),
            (
                self.advapi,
                "ConvertStringSecurityDescriptorToSecurityDescriptorW",
                w.BOOL,
                [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p],
            ),
            (
                self.advapi,
                "GetSecurityInfo",
                w.DWORD,
                [
                    w.HANDLE,
                    ctypes.c_int,
                    w.DWORD,
                    ctypes.POINTER(ctypes.c_void_p),
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p),
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p),
                ],
            ),
            (
                self.advapi,
                "GetSecurityDescriptorControl",
                w.BOOL,
                [ctypes.c_void_p, ctypes.POINTER(w.WORD), ctypes.POINTER(w.DWORD)],
            ),
            (
                self.advapi,
                "GetAclInformation",
                w.BOOL,
                [ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.c_int],
            ),
            (
                self.advapi,
                "GetAce",
                w.BOOL,
                [ctypes.c_void_p, w.DWORD, ctypes.POINTER(ctypes.c_void_p)],
            ),
            (self.advapi, "ImpersonateNamedPipeClient", w.BOOL, [w.HANDLE]),
            (self.advapi, "RevertToSelf", w.BOOL, []),
        ]
        for library, name, result, arguments in signatures:
            function = getattr(library, name)
            function.restype, function.argtypes = result, arguments

    def string_sid(self, pointer: Any) -> str:
        value = w.LPWSTR()
        if not self.advapi.ConvertSidToStringSidW(pointer, ctypes.byref(value)):
            raise SafetyError("Kernel SID unavailable")
        try:
            result = str(value.value)
            if not re.fullmatch(r"S-1-(?:[0-9]+-)+[0-9]+", result):
                raise SafetyError("Kernel SID unavailable")
            return result
        finally:
            self.kernel.LocalFree(value)

    def token_sid(self, token: Any) -> str:
        size = w.DWORD()
        self.advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if not 0 < size.value <= 65536:
            raise SafetyError("Token identity unavailable")
        data = ctypes.create_string_buffer(size.value)
        if not self.advapi.GetTokenInformation(token, 1, data, size, ctypes.byref(size)):
            raise SafetyError("Token identity unavailable")
        return self.string_sid(ctypes.cast(data, ctypes.POINTER(ctypes.c_void_p))[0])

    def current_sid(self) -> str:
        token = w.HANDLE()
        if not self.advapi.OpenProcessToken(
            self.kernel.GetCurrentProcess(), 8, ctypes.byref(token)
        ):
            raise SafetyError("Process identity unavailable")
        try:
            return self.token_sid(token)
        finally:
            self.kernel.CloseHandle(token)

    def peer_sid(self, handle: Any) -> str:
        if not self.advapi.ImpersonateNamedPipeClient(handle):
            raise SafetyError("Authenticated local writer unavailable")
        token = w.HANDLE()
        try:
            if not self.advapi.OpenThreadToken(
                self.kernel.GetCurrentThread(), 8, True, ctypes.byref(token)
            ):
                raise SafetyError("Writer token unavailable")
            return self.token_sid(token)
        finally:
            if token:
                self.kernel.CloseHandle(token)
            if not self.advapi.RevertToSelf():
                raise ServiceIdentityLost("Service identity restoration failed; stop service")

    def verify_acl(self, handle: Any, owner: str, clients: set[str]) -> None:
        wanted = {sid(value): CLIENT_RIGHTS for value in clients}
        wanted[sid(owner)] = SERVER_RIGHTS
        actual_owner, control, entries = self.security(handle)
        if actual_owner != owner or not control & 0x1000:
            raise SafetyError("Service endpoint owner or protected DACL mismatch")
        if len(entries) != len(wanted):
            raise SafetyError("Unexpected service endpoint principals")
        actual = {}
        for identity, mask, flags in entries:
            if flags or identity in actual:
                raise SafetyError("Unsupported service DACL entry")
            actual[identity] = mask
        if actual != wanted:
            raise SafetyError("Service endpoint grants unexpected rights")

    def security(self, handle: Any) -> tuple[str, int, list[tuple[str, int, int]]]:
        owner_pointer, acl, descriptor = (ctypes.c_void_p() for _ in range(3))
        if self.advapi.GetSecurityInfo(
            handle,
            6,
            5,
            ctypes.byref(owner_pointer),
            None,
            ctypes.byref(acl),
            None,
            ctypes.byref(descriptor),
        ):
            raise SafetyError("Service endpoint security unavailable")
        try:
            control, revision = w.WORD(), w.DWORD()
            if not acl or not self.advapi.GetSecurityDescriptorControl(
                descriptor, ctypes.byref(control), ctypes.byref(revision)
            ):
                raise SafetyError("Object security unavailable")
            info = _AclSize()
            if not self.advapi.GetAclInformation(acl, ctypes.byref(info), ctypes.sizeof(info), 2):
                raise SafetyError("Complete service DACL unavailable")
            if info.count > 64:
                raise SafetyError("Object DACL size exceeded")
            actual = []
            for index in range(info.count):
                ace = ctypes.c_void_p()
                if not self.advapi.GetAce(acl, index, ctypes.byref(ace)) or not ace.value:
                    raise SafetyError("Complete service DACL unavailable")
                header = ctypes.string_at(ace, 8)
                kind, flags, size, mask = struct.unpack("<BBHI", header)
                identity = self.string_sid(ace.value + 8)
                if kind != 0 or size < 12:
                    raise SafetyError("Unsupported service DACL entry")
                actual.append((identity, mask, flags))
            return self.string_sid(owner_pointer), control.value, actual
        finally:
            self.kernel.LocalFree(descriptor)


class Session:
    def __init__(
        self, native: Native, handle: Any, timeout: float, cancelled: Callable[[], bool]
    ) -> None:
        if not 0 < timeout <= 600:
            raise SafetyError("Invalid IPC time window")
        self.native, self.handle = native, handle
        self.deadline, self.cancelled = time.monotonic() + timeout, cancelled

    def check(self) -> None:
        if self.cancelled() or time.monotonic() >= self.deadline:
            raise SafetyError("Local service operation cancelled or timed out")

    def pause(self) -> None:
        self.check()
        time.sleep(min(0.01, max(0, self.deadline - time.monotonic())))

    def read(self, count: int) -> bytes:
        result = bytearray()
        while len(result) < count:
            self.check()
            data = ctypes.create_string_buffer(min(4096, count - len(result)))
            received = w.DWORD()
            ok = self.native.kernel.ReadFile(
                self.handle, data, len(data), ctypes.byref(received), None
            )
            if not ok and self.native.error() != 232:
                raise SafetyError("Local service read failed; no operation replay")
            if received.value:
                result.extend(data.raw[: received.value])
            else:
                self.pause()
        return bytes(result)

    def write(self, data: bytes) -> None:
        remaining = data
        while remaining:
            self.check()
            chunk = remaining[:4096]
            buffer, sent = ctypes.create_string_buffer(chunk), w.DWORD()
            if not self.native.kernel.WriteFile(
                self.handle, buffer, len(chunk), ctypes.byref(sent), None
            ):
                raise SafetyError("Local service write uncertain; no operation replay")
            remaining = remaining[sent.value :]
            if not sent.value:
                self.pause()

    def send(self, document: dict[str, Any]) -> None:
        data = json.dumps(document, separators=(",", ":")).encode("utf-8")
        if not 0 < len(data) <= MAX_MESSAGE:
            raise SafetyError("Local service message size exceeded")
        self.write(struct.pack("<I", len(data)) + data)

    def receive(self) -> dict[str, Any]:
        from loop_engine.planning import bounded_json

        length = struct.unpack("<I", self.read(4))[0]
        if not 0 < length <= MAX_MESSAGE:
            raise SafetyError("Local service message size exceeded")
        document = bounded_json(self.read(length).decode("utf-8"), maximum=MAX_MESSAGE)
        if not isinstance(document, dict):
            raise SafetyError("Invalid local service envelope")
        return document


def request(
    name: str,
    owner: str,
    clients: set[str],
    document: dict[str, Any],
    *,
    timeout: float,
    cancelled: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    endpoint, native = pipe_name(name), Native()
    session = Session(native, None, timeout, cancelled)
    handle = None
    try:
        while True:
            session.check()
            handle = native.kernel.CreateFileW(endpoint, CLIENT_RIGHTS, 0, None, 3, 0x110000, None)
            if handle != ctypes.c_void_p(-1).value:
                break
            if native.error() not in {2, 231}:
                raise SafetyError("Local service connection rejected")
            session.pause()
        session.handle = handle
        native.verify_acl(handle, sid(owner), clients)
        mode = w.DWORD(1)  # PIPE_NOWAIT: all loops observe one absolute deadline.
        if not native.kernel.SetNamedPipeHandleState(handle, ctypes.byref(mode), None, None):
            raise SafetyError("Bounded service transport unavailable")
        nonce = uuid4().hex
        session.send({"version": 1, "request_id": nonce, "body": document})
        response = session.receive()
        if (
            set(response) != {"version", "request_id", "ok", "body"}
            or type(response.get("version")) is not int
            or response["version"] != 1
            or response.get("request_id") != nonce
        ):
            raise SafetyError("Service reply identity mismatch")
        session.send({"ack": nonce})
        if response.get("ok") is not True or not isinstance(response.get("body"), dict):
            raise SafetyError("Service rejected the operation; no automatic replay")
        return dict(response["body"])
    finally:
        if handle and handle != ctypes.c_void_p(-1).value:
            native.kernel.CloseHandle(handle)


def serve_once(
    name: str,
    clients: set[str],
    handler: Callable[[str, dict[str, Any]], dict[str, Any]],
    *,
    timeout: float,
    cancelled: Callable[[], bool] = lambda: False,
) -> None:
    from loop_engine.planning import bounded_json

    endpoint, native = pipe_name(name), Native()
    owner = native.current_sid()
    grants = {sid(value): CLIENT_RIGHTS for value in clients}
    grants[owner] = SERVER_RIGHTS
    sddl = (
        "O:"
        + owner
        + "D:P"
        + "".join(f"(A;;0x{mask:x};;;{identity})" for identity, mask in sorted(grants.items()))
    )
    descriptor = ctypes.c_void_p()
    if not native.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), None
    ):
        raise SafetyError("Explicit service DACL unavailable")
    handle = None
    try:
        attributes = _Attributes(ctypes.sizeof(_Attributes), descriptor, False)
        handle = native.kernel.CreateNamedPipeW(
            endpoint,
            3 | 0x80000,
            1 | 8,
            1,
            MAX_MESSAGE + 4,
            MAX_MESSAGE + 4,
            1000,
            ctypes.byref(attributes),
        )
        if handle == ctypes.c_void_p(-1).value:
            raise SafetyError("Exclusive local endpoint unavailable")
        native.verify_acl(handle, owner, clients)
        session = Session(native, handle, timeout, cancelled)
        while not native.kernel.ConnectNamedPipe(handle, None):
            if native.error() == 535:
                break
            if native.error() != 536:
                raise SafetyError("Local connection unavailable")
            session.pause()
        session.deadline = time.monotonic() + timeout
        # A read is required before obtaining the token of the actual writer.
        length = struct.unpack("<I", session.read(4))[0]
        peer = native.peer_sid(handle)
        if peer not in clients or not 0 < length <= MAX_MESSAGE:
            raise SafetyError("Unapproved service caller or message")
        envelope = bounded_json(session.read(length).decode("utf-8"), maximum=MAX_MESSAGE)
        if (
            not isinstance(envelope, dict)
            or set(envelope) != {"version", "request_id", "body"}
            or type(envelope["version"]) is not int
            or envelope["version"] != 1
            or not isinstance(envelope["request_id"], str)
            or not re.fullmatch(r"[0-9a-f]{32}", envelope["request_id"])
            or not isinstance(envelope["body"], dict)
        ):
            raise SafetyError("Invalid service request")
        session.check()
        body = handler(peer, envelope["body"])
        session.check()
        session.send({"version": 1, "request_id": envelope["request_id"], "ok": True, "body": body})
        if session.receive() != {"ack": envelope["request_id"]}:
            raise SafetyError("Service reply receipt unknown")
    finally:
        if handle and handle != ctypes.c_void_p(-1).value:
            native.kernel.DisconnectNamedPipe(handle)
            native.kernel.CloseHandle(handle)
        native.kernel.LocalFree(descriptor)
