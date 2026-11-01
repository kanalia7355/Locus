"""Read machine dump/debug policies; configure only the new account's WER opt-out."""

import sys

from loop_engine.audit_identity import AuditDeployment
from loop_engine.security import SafetyError


def require_private_crash_policy(deployment: AuditDeployment, *, configure: bool = False) -> None:
    deployment.require_role("audit")
    if sys.platform != "win32":
        raise SafetyError("Windows audit privacy policy required")
    import winreg

    reporting = r"Software\Microsoft\Windows\Windows Error Reporting"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        policy = r"Software\Policies\Microsoft\Windows\Windows Error Reporting"
        try:
            with winreg.OpenKey(hive, policy) as key:
                try:
                    value, kind = winreg.QueryValueEx(key, "Disabled")
                except FileNotFoundError:
                    pass
                else:
                    if kind != winreg.REG_DWORD or value != 1:
                        raise SafetyError("Required crash reporting conflicts with audit privacy")
        except FileNotFoundError:
            pass
        try:
            with winreg.OpenKey(hive, reporting + r"\LocalDumps") as key:
                # Global values or either dedicated executable enable collection.
                if winreg.QueryInfoKey(key)[1]:
                    raise SafetyError("Automatic local dumps configured; hold audit authentication")
                for image in ("codex.exe", "python.exe"):
                    try:
                        with winreg.OpenKey(key, image):
                            raise SafetyError("Audit executable dumps configured")
                    except FileNotFoundError:
                        pass
        except FileNotFoundError:
            pass
    # This SID was created for audits, not the operator's existing profile. Do
    # not override an explicit administrator preference; absence may initialize.
    opener = winreg.CreateKeyEx if configure else winreg.OpenKey
    try:
        with opener(
            winreg.HKEY_CURRENT_USER,
            reporting,
            0,
            winreg.KEY_READ | (winreg.KEY_SET_VALUE if configure else 0),
        ) as key:
            try:
                value, kind = winreg.QueryValueEx(key, "Disabled")
            except FileNotFoundError:
                if not configure:
                    raise SafetyError(
                        "Audit-account crash privacy policy not initialized"
                    ) from None
                winreg.SetValueEx(key, "Disabled", 0, winreg.REG_DWORD, 1)
            else:
                if kind != winreg.REG_DWORD or value != 1:
                    raise SafetyError("Existing audit-account crash policy requires reconciliation")
    except FileNotFoundError:
        raise SafetyError("Audit-account crash privacy policy not initialized") from None
    for prefix in (
        r"Software\Microsoft\Windows NT\CurrentVersion\SilentProcessExit",
        r"Software\Microsoft\Windows NT\CurrentVersion\Image File Execution Options",
    ):
        for image in ("codex.exe", "python.exe"):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, prefix + "\\" + image) as key:
                    for name in ("Debugger", "GlobalFlag", "ReportingMode", "MonitorProcess"):
                        try:
                            value, _ = winreg.QueryValueEx(key, name)
                        except FileNotFoundError:
                            continue
                        if value not in (0, "0", "0x0", "", None):
                            raise SafetyError("Audit executable debug/dump monitor configured")
            except FileNotFoundError:
                pass
