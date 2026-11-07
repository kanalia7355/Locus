"""Build a sealed audit-only runtime update, preserving credentials and state."""

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from loop_engine.audit_bundle import build_audit, installer_source
from loop_engine.audit_identity import AUDIT_ROOT, AuditDeployment
from loop_engine.audit_packet import canonical, hash_value
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError
from loop_engine.service_bundle import admin_command
from loop_engine.service_identity import protected_bytes


def upgrade_source(original: bytes, audit_template: bytes, upgrade_template: bytes) -> bytes:
    full = installer_source(original, audit_template).decode()
    native = re.findall(r"Add-Type -TypeDefinition @'\n(.*?)\n'@", full, re.DOTALL)
    if len(native) != 1:
        raise SafetyError("Reviewed audit helper boundary changed")
    code = native[0].replace("LocusAuditBootstrapNativeV1", "LocusAuditUpgradeNativeV1")
    marker = "    public static void PrepareIdentity(byte[] sid) {"
    if code.count(marker) != 1:
        raise SafetyError("Reviewed audit native boundary changed")
    code = code.replace(
        marker,
        """
    [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    static extern bool ChangeServiceConfig(IntPtr service,uint type,uint start,uint error,
        string binary,string group,IntPtr tag,IntPtr dependencies,
        string user,string password,string display);
    public static void UpdateAuditBinary(string binary) {
        IntPtr manager=OpenSCManager(null,null,1);
        if(manager==IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        try {
            IntPtr service=OpenService(manager,"LocusLoopAuditV1",2);
            if(service==IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
            try {
                if(!ChangeServiceConfig(service,0xffffffff,0xffffffff,0xffffffff,binary,null,
                    IntPtr.Zero,IntPtr.Zero,null,null,null))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
            } finally { CloseServiceHandle(service); }
        } finally { CloseServiceHandle(manager); }
    }
"""
        + marker,
    )
    text = original.decode().replace("\r\n", "\n")
    helpers = (
        "function Assert-RegularPath"
        + text.split("function Assert-RegularPath", 1)[1].split("function Assert-PrivateAcl", 1)[0]
    )
    result = upgrade_template.decode().replace("\r\n", "\n")
    for name, value in (("__READONLY_HELPERS__", helpers), ("__NATIVE_HELPER__", code)):
        if result.count(name) != 1:
            raise SafetyError("Reviewed upgrade template boundary changed")
        result = result.replace(name, value)
    return result.encode()


def build_upgrade(root: Path, authentication: str, trial: str) -> dict[str, Any]:
    hash_value(authentication)
    hash_value(trial)
    root = root.resolve()
    old = AuditDeployment()
    if "profile_runtime" in old.audit_settings:
        raise SafetyError("Further upgrades need a separate reviewed migration")
    raw_settings = protected_bytes(AUDIT_ROOT / "settings.json")
    payload = build_audit(root)  # Requires clean committed source; no installer execution.
    bundle = Path(payload["bundle"])
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    if any(
        manifest.get(key) != old.manifest.get(key)
        for key in ("codex_sha256", "model", "reasoning_effort", "disabled_features")
    ):
        raise SafetyError("Diagnostic upgrade cannot change authentication/model/tool policy")
    process = ProcessRunner()

    def source(name: str) -> bytes:
        result = process.run(
            ["git", "show", payload["source_commit"] + ":" + name],
            root,
            timeout=20,
            output_limit=1_000_000,
        )
        if result.outcome != "exit" or result.returncode:
            raise SafetyError("Committed upgrade source unavailable")
        return result.stdout.encode()

    script = upgrade_source(
        source("scripts/Install-LocusLoopServices.ps1"),
        source("scripts/Install-LocusLoopAudit.template.ps1"),
        source("scripts/Upgrade-LocusLoopAudit.template.ps1"),
    )
    directory = root / ".loop/runtime/audit-upgrades" / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    target = directory / "payload"
    target.mkdir()
    shutil.copytree(bundle / "runtime", target / "runtime")
    shutil.copyfile(bundle / "manifest.json", target / "manifest.json")
    (directory / "Upgrade-LocusLoopAudit.ps1").write_bytes(script)
    plan = {
        "protocol": "locus-audit-runtime-upgrade-v1",
        "source_clean": True,
        "source_commit": payload["source_commit"],
        "active_manifest": old.identity,
        "payload_manifest": payload["manifest_sha256"],
        "settings_sha256": hashlib.sha256(raw_settings).hexdigest(),
        "authentication": authentication,
        "trial": trial,
        "installer_sha256": hashlib.sha256(script).hexdigest(),
    }
    raw = canonical(plan)
    (directory / "manifest.json").write_bytes(raw)
    package = {
        "bundle": str(directory),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "runtime_manifest": payload["manifest_sha256"],
        "activated": False,
    }
    (directory / "admin-command.txt").write_text(
        admin_command(package).replace(
            "Install-LocusLoopServices.ps1", "Upgrade-LocusLoopAudit.ps1"
        ),
        encoding="utf-8",
    )
    return package


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--authentication", required=True)
    parser.add_argument("--trial", required=True)
    args = parser.parse_args()
    print(json.dumps(build_upgrade(Path.cwd(), args.authentication, args.trial)))
