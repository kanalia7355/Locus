"""Complete only the two pending configuration switches of a pinned audit upgrade."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from loop_engine.audit_identity import AUDIT_ROOT, AuditDeployment
from loop_engine.audit_packet import canonical, hash_value
from loop_engine.audit_upgrade import upgrade_source
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError
from loop_engine.service_bundle import admin_command
from loop_engine.service_identity import protected_bytes


def completion_source(original: bytes, audit: bytes, upgrade: bytes, completion: bytes) -> bytes:
    full = upgrade_source(original, audit, upgrade).decode()
    native = re.findall(r"Add-Type -TypeDefinition @'\n(.*?)\n'@", full, re.DOTALL)
    if len(native) != 1:
        raise SafetyError("Reviewed native upgrade boundary changed")
    code = native[0].replace("LocusAuditUpgradeNativeV1", "LocusAuditUpgradeCompletionNativeV1")
    text = original.decode().replace("\r\n", "\n")
    helpers = (
        "function Assert-RegularPath"
        + text.split("function Assert-RegularPath", 1)[1].split("function Assert-PrivateAcl", 1)[0]
    )
    result = completion.decode().replace("\r\n", "\n")
    for name, value in (("__READONLY_HELPERS__", helpers), ("__NATIVE_HELPER__", code)):
        if result.count(name) != 1:
            raise SafetyError("Reviewed upgrade completion template changed")
        result = result.replace(name, value)
    return result.encode()


def build(root: Path, previous_bundle: Path, upgrade_hash: str) -> dict[str, Any]:
    hash_value(upgrade_hash)
    root = root.resolve()
    previous_bundle = previous_bundle.resolve()
    original = (previous_bundle / "manifest.json").read_bytes()
    if hashlib.sha256(original).hexdigest() != upgrade_hash:
        raise SafetyError("Original upgrade package changed")
    prior = json.loads(original)
    deployed = AuditDeployment()
    if prior.get("protocol") != "locus-audit-runtime-upgrade-v1" or deployed.identity != prior.get(
        "active_manifest"
    ):
        raise SafetyError("Exact incomplete upgrade required")
    raw_settings = protected_bytes(AUDIT_ROOT / "settings.json")
    if hashlib.sha256(raw_settings).hexdigest() != prior["settings_sha256"]:
        raise SafetyError("Existing settings changed; preserve without replay")
    staged = protected_bytes(AUDIT_ROOT / "settings.upgrade.json")
    permit = protected_bytes(AUDIT_ROOT / "reconciliation-permit.json")
    process = ProcessRunner()

    def git(arguments: list[str]) -> str:
        outcome = process.run(["git", *arguments], root, timeout=20, output_limit=1_000_000)
        if outcome.outcome != "exit" or outcome.returncode:
            raise SafetyError("Committed completion source required")
        return outcome.stdout

    if git(["status", "--porcelain"]):
        raise SafetyError("Review and commit completion before packaging")
    commit = git(["rev-parse", "HEAD"]).strip()
    sources = [
        git(["show", commit + ":" + name]).encode()
        for name in (
            "scripts/Install-LocusLoopServices.ps1",
            "scripts/Install-LocusLoopAudit.template.ps1",
            "scripts/Upgrade-LocusLoopAudit.template.ps1",
            "scripts/Complete-LocusLoopAuditUpgrade.template.ps1",
        )
    ]
    script = completion_source(*sources)
    directory = root / ".loop/runtime/audit-upgrade-completions" / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "Complete-LocusLoopAuditUpgrade.ps1").write_bytes(script)
    plan = {
        "protocol": "locus-audit-upgrade-completion-v1",
        "source_clean": True,
        "source_commit": commit,
        "active_manifest": prior["active_manifest"],
        "next_manifest": prior["payload_manifest"],
        "old_settings": prior["settings_sha256"],
        "new_settings": hashlib.sha256(staged).hexdigest(),
        "permit_hash": hashlib.sha256(permit).hexdigest(),
        "upgrade_helper": upgrade_hash,
        "installer_sha256": hashlib.sha256(script).hexdigest(),
    }
    raw = canonical(plan)
    (directory / "manifest.json").write_bytes(raw)
    package = {
        "bundle": str(directory),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "runtime_manifest": prior["payload_manifest"],
        "activated": False,
    }
    (directory / "admin-command.txt").write_text(
        admin_command(package).replace(
            "Install-LocusLoopServices.ps1", "Complete-LocusLoopAuditUpgrade.ps1"
        ),
        encoding="utf-8",
    )
    return package


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--previous-bundle", type=Path, required=True)
    parser.add_argument("--upgrade-manifest", required=True)
    args = parser.parse_args()
    print(json.dumps(build(Path.cwd(), args.previous_bundle, args.upgrade_manifest)))
