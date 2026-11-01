"""One-shot completion of the exact unused, pre-auth audit partial installation."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from loop_engine.audit_bundle import installer_source
from loop_engine.audit_packet import canonical
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError
from loop_engine.service_bundle import admin_command
from loop_engine.service_identity import Deployment
from loop_engine.windows_pipe import Native


def completion_source(
    original: bytes,
    template: bytes,
    guards: bytes,
    *,
    previous_bundle: Path,
    active_hash: str,
    audit_sid: str,
) -> bytes:
    if not re.fullmatch(r"[a-f0-9]{64}", active_hash) or not re.fullmatch(
        r"S-1-5-21(?:-[0-9]+){4}", audit_sid
    ):
        raise SafetyError("Exact audit recovery identities required")
    script = installer_source(original, template).decode()

    def change(old: str, new: str) -> None:
        nonlocal script
        if script.count(old) != 1:
            raise SafetyError("Reviewed audit completion source boundary changed")
        script = script.replace(old, new)

    # The outer command pins this helper's bytes. Preserve and independently
    # validate the existing deployment's original manifest, not a replacement.
    change("$installStage = 'package_validation'", "$installStage = 'completion_preflight'")
    change(
        "try {\n    if ([IntPtr]::Size -ne 8)",
        guards.decode().replace("\r\n", "\n")
        + "\ntry {\n    $Bundle = '"
        + str(previous_bundle).replace("'", "''")
        + "'\n    $ManifestSha256 = '"
        + active_hash
        + "'\n    if ([IntPtr]::Size -ne 8)",
    )
    change(
        "if (Test-Path -LiteralPath $deploymentRoot) { "
        "throw 'Existing or partial audit deployment preserved' }",
        "Assert-AuditPartial $deploymentRoot $manifest $ManifestSha256 '" + audit_sid + "'",
    )
    change(
        "if ($null -ne (Find-LocalUser 'locus_loop_audit')) { "
        "throw 'Existing audit account preserved' }",
        "",
    )
    change(
        "    public static void PrepareIdentity(byte[] sid) {",
        """
    [DllImport("advapi32.dll")] static extern uint LsaEnumerateAccountRights(
        IntPtr policy, byte[] sid, out IntPtr rights, out uint count);
    [DllImport("advapi32.dll")] static extern uint LsaFreeMemory(IntPtr value);
    public static void RequireUnusedAuditRights(string sidText) {
        var sid = new System.Security.Principal.SecurityIdentifier(sidText);
        var binary = new byte[sid.BinaryLength]; sid.GetBinaryForm(binary,0);
        var attributes = new Attributes { Length=(uint)Marshal.SizeOf(typeof(Attributes)) };
        IntPtr policy, values=IntPtr.Zero;
        if(LsaOpenPolicy(IntPtr.Zero,ref attributes,0x800,out policy)!=0)
            throw new InvalidOperationException();
        try {
            uint count;
            if(LsaEnumerateAccountRights(policy,binary,out values,out count)!=0 || count!=3)
                throw new InvalidOperationException();
            var wanted = new System.Collections.Generic.HashSet<string>(StringComparer.Ordinal) {
                "SeServiceLogonRight","SeDenyInteractiveLogonRight","SeDenyRemoteInteractiveLogonRight"
            };
            for(int i=0;i<(int)count;i++) {
                var text=(Text)Marshal.PtrToStructure(IntPtr.Add(values,
                    i*Marshal.SizeOf(typeof(Text))),typeof(Text));
                if(text.Length>512 || text.Length%2!=0 ||
                    !wanted.Remove(Marshal.PtrToStringUni(text.Buffer,text.Length/2)))
                    throw new InvalidOperationException();
            }
            if(wanted.Count!=0) throw new InvalidOperationException();
        } finally { if(values!=IntPtr.Zero)LsaFreeMemory(values);LsaClose(policy); }
    }
    public static void PrepareIdentity(byte[] sid) {""",
    )
    change(
        "    [LocusAuditBootstrapNativeV1]::EnableRestore()",
        "    $installStage = 'completion_account_rights'\n"
        "    [LocusAuditBootstrapNativeV1]::RequireUnusedAuditRights('" + audit_sid + "')\n"
        "    [LocusAuditBootstrapNativeV1]::EnableRestore()",
    )
    start = script.index("    $installStage = 'private_deployment'")
    end = script.index("    $installStage = 'audit_account'", start)
    script = (
        script[:start]
        + """    $installStage = 'completion_intent'
    $runtimeParent = Join-Path $deploymentRoot 'runtimes'
    $targetRuntime = Join-Path $runtimeParent $ManifestSha256
    $installedManifest = Join-Path $runtimeParent ($ManifestSha256 + '.manifest.json')
    $intentPath = Join-Path $deploymentRoot 'audit-completion-intent.json'
    [LocusAuditBootstrapNativeV1]::WritePrivate($intentPath,
        '{"automatic_replay":false,"protocol":"locus-audit-completion-v1"}')
"""
        + script[end:]
    )
    change(
        "$user = New-LocalUser -Name 'locus_loop_audit' -Password $secure "
        "-AccountNeverExpires -PasswordNeverExpires",
        "$user = Find-LocalUser 'locus_loop_audit'\n        Assert-UnusedAuditAccount $user '"
        + audit_sid
        + "'\n        Set-LocalUser -SID $user.SID -Password $secure -PasswordNeverExpires $true",
    )
    return script.encode()


def build_completion(
    root: Path, previous_bundle: Path, active_hash: str, audit_sid: str
) -> dict[str, Any]:
    root, previous_bundle = root.resolve(), previous_bundle.resolve()
    app = Deployment()
    if Native().current_sid() != app.settings["operator_sid"] or audit_sid in {
        app.settings["operator_sid"],
        *(app.settings["roles"][role]["sid"] for role in ("review", "merge")),
    }:
        raise SafetyError("Existing operator and separate audit identity required")
    raw = (previous_bundle / "manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != active_hash:
        raise SafetyError("Original audit manifest changed")
    old = json.loads(raw)
    if old.get("protocol") != "locus-audit-bundle-v1" or old.get("app_manifest") != app.identity:
        raise SafetyError("Existing audit/App deployment binding required")
    process = ProcessRunner()

    def git(arguments: list[str]) -> str:
        result = process.run(["git", *arguments], root, timeout=20, output_limit=1_000_000)
        if result.outcome != "exit" or result.returncode:
            raise SafetyError("Committed recovery source unavailable")
        return result.stdout

    if git(["status", "--porcelain"]):
        raise SafetyError("Review and commit audit completion before packaging")
    commit = git(["rev-parse", "HEAD"]).strip()
    sources = [
        git(["show", commit + ":" + name]).encode()
        for name in (
            "scripts/Install-LocusLoopServices.ps1",
            "scripts/Install-LocusLoopAudit.template.ps1",
            "scripts/Complete-LocusLoopAudit.preflight.ps1",
        )
    ]
    script = completion_source(
        *sources, previous_bundle=previous_bundle, active_hash=active_hash, audit_sid=audit_sid
    )
    directory = root / ".loop/runtime/audit-completions" / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "Complete-LocusLoopAudit.ps1").write_bytes(script)
    manifest = {
        "protocol": "locus-audit-completion-v1",
        "source_commit": commit,
        "source_clean": True,
        "active_manifest": active_hash,
        "audit_sid": audit_sid,
        "installer_sha256": hashlib.sha256(script).hexdigest(),
    }
    payload = canonical(manifest)
    (directory / "manifest.json").write_bytes(payload)
    package = {
        "bundle": str(directory),
        "manifest_sha256": hashlib.sha256(payload).hexdigest(),
        "active_manifest": active_hash,
        "source_commit": commit,
        "activated": False,
    }
    (directory / "admin-command.txt").write_text(
        admin_command(package).replace(
            "Install-LocusLoopServices.ps1", "Complete-LocusLoopAudit.ps1"
        ),
        encoding="utf-8",
    )
    return package


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--previous-bundle", type=Path, required=True)
    parser.add_argument("--active-manifest", required=True)
    parser.add_argument("--audit-sid", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build_completion(Path.cwd(), args.previous_bundle, args.active_manifest, args.audit_sid)
        )
    )
