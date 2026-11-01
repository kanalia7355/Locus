"""Read SCM ownership/configuration before trusting an isolated service endpoint."""

import ctypes
import json
import sys
from collections.abc import Callable
from ctypes import wintypes as w
from typing import Any

from loop_engine.security import SafetyError
from loop_engine.service_identity import DEPLOYMENT_ROOT, ROLES, Deployment
from loop_engine.windows_pipe import Native


class _Config(ctypes.Structure):
    _fields_ = [
        ("kind", w.DWORD),
        ("start", w.DWORD),
        ("error", w.DWORD),
        ("binary", w.LPWSTR),
        ("group", w.LPWSTR),
        ("tag", w.DWORD),
        ("dependencies", w.LPWSTR),
        ("account", w.LPWSTR),
        ("display", w.LPWSTR),
    ]


class _Status(ctypes.Structure):
    _fields_ = [
        (name, w.DWORD)
        for name in ("kind", "state", "accepted", "exit", "specific", "checkpoint", "hint")
    ]


def require_registration(
    deployment: Deployment, role: str, facts: dict[str, Any]
) -> dict[str, Any]:
    if role not in ROLES:
        raise SafetyError("Fixed preparation role required")
    item = deployment.settings["roles"][role]
    expected_binary = (
        f'"{deployment.runtime / "python.exe"}" -I -B '
        f'"{deployment.runtime / "service_bootstrap.py"}" --role {role} '
        f"--manifest-hash {deployment.identity}"
    )
    wanted = {
        "S-1-5-18": 0xF01FF,
        "S-1-5-32-544": 0xF01FF,
        deployment.settings["operator_sid"]: 0x200B5,
    }
    entries = facts["entries"]
    actual = {identity: mask for identity, mask, flags in entries if flags == 0}
    if (
        facts["owner"] != "S-1-5-18"
        or len(entries) != len(wanted)
        or actual != wanted
        or facts["kind"] != 0x10
        or facts["start"] != 3
        or facts["state"] != 4
        or facts["binary"] != expected_binary
        or facts["account"] != ".\\" + item["account"]
        or facts["unsafe_access"] is not False
    ):
        raise SafetyError(
            "Service registration ownership, rights, identity or configuration differs"
        )
    return {
        "role": role,
        "identity": deployment.identity,
        "system_owned": True,
        "exact_control_acl": True,
        "operator_cannot_reconfigure": True,
        "running": True,
    }


def _inspect_registration(deployment: Deployment, role: str) -> dict[str, Any]:
    if role not in ROLES:
        raise SafetyError("Fixed preparation role required")
    native = Native()
    if native.current_sid() != deployment.settings["operator_sid"]:
        raise SafetyError("Configured nonprivileged operator required")
    api = native.advapi
    api.OpenSCManagerW.argtypes, api.OpenSCManagerW.restype = (
        [w.LPCWSTR, w.LPCWSTR, w.DWORD],
        w.HANDLE,
    )
    api.OpenServiceW.argtypes, api.OpenServiceW.restype = [w.HANDLE, w.LPCWSTR, w.DWORD], w.HANDLE
    api.CloseServiceHandle.argtypes, api.CloseServiceHandle.restype = [w.HANDLE], w.BOOL
    api.QueryServiceConfigW.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    api.QueryServiceConfigW.restype = w.BOOL
    api.QueryServiceStatus.argtypes, api.QueryServiceStatus.restype = (
        [w.HANDLE, ctypes.POINTER(_Status)],
        w.BOOL,
    )
    manager = api.OpenSCManagerW(None, None, 1)
    if not manager:
        raise SafetyError("Local SCM read unavailable")
    handle = None
    try:
        name = ROLES[role][0]
        handle = api.OpenServiceW(manager, name, 0x20005)  # READ_CONTROL/config/status only.
        if not handle:
            raise SafetyError("Preparation service not registered or not readable")
        owner, _, entries = native.security(handle, kind=2)  # SE_SERVICE; no SACL read.
        size = w.DWORD()
        api.QueryServiceConfigW(handle, None, 0, ctypes.byref(size))
        if not ctypes.sizeof(_Config) <= size.value <= 65536:
            raise SafetyError("Service configuration size unavailable")
        buffer = ctypes.create_string_buffer(size.value)
        if not api.QueryServiceConfigW(handle, buffer, len(buffer), ctypes.byref(size)):
            raise SafetyError("Service configuration read failed")
        config = ctypes.cast(buffer, ctypes.POINTER(_Config)).contents
        status = _Status()
        if not api.QueryServiceStatus(handle, ctypes.byref(status)):
            raise SafetyError("Service status read failed")
        unsafe = False
        for mask in (2, 0x10000, 0x40000, 0x80000):  # Probe each right; never invoke a mutation.
            probe = api.OpenServiceW(manager, name, mask)
            if probe:
                api.CloseServiceHandle(probe)
                unsafe = True
            elif native.error() != 5:
                raise SafetyError("Service negative capability probe inconclusive")
        return require_registration(
            deployment,
            role,
            {
                "owner": owner,
                "entries": entries,
                "kind": config.kind,
                "start": config.start,
                "binary": config.binary,
                "account": config.account,
                "state": status.state,
                "unsafe_access": unsafe,
            },
        )
    finally:
        if handle:
            api.CloseServiceHandle(handle)
        api.CloseServiceHandle(manager)


def inspect_registration(
    deployment: Deployment,
    role: str,
    *,
    timeout: float = 15,
    cancelled: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    from loop_engine.planning import bounded_json
    from loop_engine.process import ProcessRunner

    if role not in ROLES or not 0 < timeout <= 300 or cancelled():
        raise SafetyError("Bounded active registration inspection required")
    result = ProcessRunner().run(
        [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "loop_engine.service_inspection",
            "--role",
            role,
            "--identity",
            deployment.identity,
        ],
        DEPLOYMENT_ROOT,
        timeout=min(15, timeout),
        cancelled=cancelled,
        output_limit=4096,
    )
    if result.outcome != "exit" or result.returncode:
        raise SafetyError("Owned registration inspection unavailable, cancelled or timed out")
    document = bounded_json(result.stdout, maximum=4096)
    expected = {
        "role": role,
        "identity": deployment.identity,
        "system_owned": True,
        "exact_control_acl": True,
        "operator_cannot_reconfigure": True,
        "running": True,
    }
    if document != expected or any(
        type(document[key]) is not bool for key in expected if key not in {"role", "identity"}
    ):
        raise SafetyError("Complete registration inspection response required")
    return expected


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=tuple(ROLES), required=True)
    parser.add_argument("--identity", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(_inspect_registration(Deployment(args.identity), args.role)))
        return 0
    except Exception:
        print('{"status":"blocked","reason":"registration_not_verified"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
