"""Windows SCM host; every request runs in an owned bounded child job."""

import ctypes
import json
import os
import sys
import threading
import time
from ctypes import wintypes as w
from typing import Any

from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError
from loop_engine.service_identity import DEPLOYMENT_ROOT, ROLES, Deployment
from loop_engine.windows_pipe import Native, ServiceIdentityLost, serve_once


def handle(
    deployment: Deployment,
    role: str,
    peer: str,
    document: dict[str, Any],
    stopped: threading.Event,
) -> dict[str, Any]:
    if set(document) != {"deadline_monotonic", "body"} or not isinstance(document["body"], dict):
        raise SafetyError("Bounded service request required")
    deadline = document["deadline_monotonic"]
    if type(deadline) not in {float, int} or not 0 < deadline - time.monotonic() <= 300:
        raise SafetyError("Service request deadline invalid or expired")
    from loop_engine.planning import bounded_json

    result = ProcessRunner().run(
        [
            sys.executable,
            "-I",
            "-B",
            str(deployment.runtime / "service_bootstrap.py"),
            "--role",
            role,
            "--worker",
            "--manifest-hash",
            deployment.identity,
        ],
        DEPLOYMENT_ROOT / "state" / role,
        stdin=json.dumps({"peer": peer, "body": document["body"]}),
        timeout=min(300, deadline - time.monotonic()),
        cancelled=stopped.is_set,
        output_limit=65536,
    )
    if result.outcome != "exit":
        return {
            "status": "uncertain",
            "reason": "owned_worker_not_completed",
            "automatic_replay": False,
            "activated": False,
        }
    if result.returncode != 0:
        # Worker emits only a sanitized fixed error/public auth diagnostic. Never
        # forward stderr, tracebacks, request bodies or arbitrary exceptions.
        try:
            diagnostic = bounded_json(result.stdout, maximum=65536)
            if isinstance(diagnostic, dict) and set(diagnostic) == {"connection_error"}:
                return {
                    "status": "blocked",
                    "connection_error": diagnostic["connection_error"],
                    "activated": False,
                }
        except ValueError:
            pass
        return {"status": "blocked", "reason": "service_operation_failed", "activated": False}
    answer = bounded_json(result.stdout, maximum=65536)
    if not isinstance(answer, dict):
        raise SafetyError("Bounded public worker result required")
    return answer


def serve(deployment: Deployment, role: str, stopped: threading.Event) -> None:
    deployment.require_role(role)
    failures = 0
    while not stopped.is_set():
        try:
            serve_once(
                "Locus-" + role + "-v1",
                deployment.clients(role),
                lambda peer, data: handle(deployment, role, peer, data, stopped),
                timeout=300,
                cancelled=stopped.is_set,
            )
            failures = 0
        except (SafetyError, OSError, ValueError) as error:
            # No remote operation is replayed. The bounded worker owns its own
            # durable mutation intents; preparation exposes only fixed reads/import.
            if not stopped.is_set():
                if str(error) != "Local service operation cancelled or timed out":
                    failures += 1
                if failures >= 3:
                    raise SafetyError(
                        "Repeated service boundary failure; stop without replay"
                    ) from None
                stopped.wait(0.2)


def scm(deployment: Deployment, role: str) -> None:
    deployment.require_role(role)
    native = Native()
    advapi = native.advapi
    callback = vars(ctypes)["WINFUNCTYPE"]
    main_type = callback(None, w.DWORD, ctypes.POINTER(w.LPWSTR))
    control_type = callback(w.DWORD, w.DWORD, w.DWORD, ctypes.c_void_p, ctypes.c_void_p)

    class Status(ctypes.Structure):
        _fields_ = [
            (name, w.DWORD)
            for name in (
                "kind",
                "state",
                "accepted",
                "exit_code",
                "service_exit",
                "checkpoint",
                "wait_hint",
            )
        ]

    class Entry(ctypes.Structure):
        _fields_ = [("name", w.LPWSTR), ("main", main_type)]

    advapi.RegisterServiceCtrlHandlerExW.argtypes = [w.LPCWSTR, control_type, ctypes.c_void_p]
    advapi.RegisterServiceCtrlHandlerExW.restype = w.HANDLE
    advapi.SetServiceStatus.argtypes = [w.HANDLE, ctypes.POINTER(Status)]
    advapi.SetServiceStatus.restype = w.BOOL
    advapi.StartServiceCtrlDispatcherW.argtypes = [ctypes.POINTER(Entry)]
    advapi.StartServiceCtrlDispatcherW.restype = w.BOOL
    stopped = threading.Event()
    status_handle: Any = None
    service_name = ROLES[role][0]

    def report(state: int, error: int = 0) -> None:
        status = Status(
            0x10,
            state,
            5 if state == 4 else 0,
            error,
            0,
            1 if state in {2, 3} else 0,
            15000 if state in {2, 3} else 0,
        )
        if not advapi.SetServiceStatus(status_handle, ctypes.byref(status)):
            stopped.set()

    def control(code: int, event: int, data: Any, context: Any) -> int:
        if code in {1, 5}:  # STOP or SHUTDOWN
            stopped.set()
            report(3)
        return 0

    controller = control_type(control)

    def service_main(count: int, arguments: Any) -> None:
        nonlocal status_handle
        status_handle = advapi.RegisterServiceCtrlHandlerExW(service_name, controller, None)
        if not status_handle:
            return
        failure = 0
        try:
            report(2)
            report(4)
            serve(deployment, role, stopped)
        except ServiceIdentityLost:
            os._exit(70)  # Kernel identity was not restored; no further service code is safe.
        except BaseException:
            # Including failed impersonation restoration: do not continue service
            # execution, leak callback exceptions or restart unknown operations.
            failure = 1
        finally:
            stopped.set()
            report(1, failure)

    main = main_type(service_main)
    table = (Entry * 2)(Entry(service_name, main), Entry(None, main_type()))
    if not advapi.StartServiceCtrlDispatcherW(table):
        raise SafetyError("Service must be started through its installed SCM identity")
