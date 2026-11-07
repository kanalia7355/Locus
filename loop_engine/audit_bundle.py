"""Build the audited new-account preparation package; never runs its installer."""

import hashlib
import json
import os
import shutil
import tomllib
from pathlib import Path
from typing import Any

from loop_engine.audit_execution import contract_artifacts
from loop_engine.audit_identity import CODEX_SHA256
from loop_engine.audit_packet import canonical
from loop_engine.audit_profile import FEATURES
from loop_engine.codex_runner import codex_binary
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError, reject_secrets, reparse
from loop_engine.service_bundle import admin_command, build
from loop_engine.service_identity import Deployment
from loop_engine.windows_pipe import Native


def installer_source(original: bytes, template: bytes) -> bytes:
    original_text = original.decode().replace("\r\n", "\n")
    template_text = template.decode().replace("\r\n", "\n")
    helpers = original_text.split("function Assert-RegularPath", 1)[1].split(
        "function Assert-PrivateAcl", 1
    )[0]
    helpers = "function Assert-RegularPath" + helpers
    native = original_text.split("Add-Type -TypeDefinition @'\n", 1)[1].split("\n'@", 1)[0]
    replacements = {
        "LocusBootstrapNativeV1": "LocusAuditBootstrapNativeV1",
        "input.Length>64000000": "input.Length>536870912",
        "ProtectService(string name, string operatorSid)": (
            "ProtectService(string name, string operatorSid, string reviewSid)"
        ),
        'string sddl="O:SYD:P(A;;0xf01ff;;;SY)(A;;0xf01ff;;;BA)(A;;0x200b5;;;"+operatorSid+")";': (
            'string sddl="O:SYD:P(A;;0xf01ff;;;SY)(A;;0xf01ff;;;BA)(A;;0x200b5;;;"+operatorSid+'
            '")(A;;0x20005;;;"+reviewSid+")";'
        ),
    }
    for old, new in replacements.items():
        if native.count(old) != 1:
            raise SafetyError("Reviewed native helper source boundary changed")
        native = native.replace(old, new)
    for name, value in (("__READONLY_HELPERS__", helpers), ("__NATIVE_HELPER__", native)):
        if template_text.count(name) != 1:
            raise SafetyError("Reviewed audit installer template boundary changed")
        template_text = template_text.replace(name, value)
    return template_text.encode()


def file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def build_audit(root: Path) -> dict[str, Any]:
    root = root.resolve()
    app = Deployment()
    if Native().current_sid() != app.settings["operator_sid"]:
        raise SafetyError("Existing operator identity required for audit packaging")
    binary_name = codex_binary(root)
    if binary_name is None:
        raise SafetyError("Previously verified native client required")
    binary = Path(binary_name)
    if reparse(binary) or file_hash(binary) != CODEX_SHA256:
        raise SafetyError("Existing approved Codex client changed")
    owner_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    config = tomllib.loads((owner_home / "config.toml").read_text(encoding="utf-8"))
    if config.get("model_provider", "openai") != "openai":
        raise SafetyError("Custom model provider is outside this approved audit package")
    providers = config.get("model_providers", {})
    if (
        not isinstance(providers, dict)
        or providers.get("openai")
        or any(config.get(key) for key in ("openai_base_url", "chatgpt_base_url", "profile"))
    ):
        raise SafetyError("Custom provider/profile policy needs reconciliation, not substitution")
    model = config.get("model")
    import re

    if not isinstance(model, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,79}", model):
        raise SafetyError("Current approved model policy unavailable")
    reasoning = config.get("model_reasoning_effort")
    if reasoning is not None and (
        not isinstance(reasoning, str)
        or reasoning not in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
    ):
        raise SafetyError("Current reasoning policy unavailable")
    with (owner_home / "models_cache.json").open("rb") as stream:
        catalog = stream.read(8 * 1024 * 1024 + 1)
    if not 0 < len(catalog) <= 8 * 1024 * 1024:
        raise SafetyError("Public model catalog size exceeded")
    reject_secrets(catalog.decode("utf-8"))
    process = ProcessRunner()
    snapshot = process.run(["git", "rev-parse", "HEAD"], root, timeout=15)
    if snapshot.outcome != "exit" or snapshot.returncode:
        raise SafetyError("Committed audit source unavailable")
    commit = snapshot.stdout.strip()
    source = process.run(
        ["git", "show", commit + ":scripts/Install-LocusLoopAudit.template.ps1"],
        root,
        timeout=15,
    )
    if source.outcome != "exit" or source.returncode:
        raise SafetyError("Committed audit installer unavailable")
    # Reuse the already verified CPython/wheel/source builder. It requires a clean
    # tree and captures immutable commit bytes. Its old installer is never run.
    base = build(root)
    if base["source_commit"] != commit:
        raise SafetyError("Audit source changed during package construction")
    directory = Path(base["bundle"])
    runtime = directory / "runtime"
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    original = (directory / "Install-LocusLoopServices.ps1").read_bytes()
    installer = installer_source(original, source.stdout.encode())
    (directory / "Install-LocusLoopAudit.ps1").write_bytes(installer)
    shutil.copyfile(binary, runtime / "codex.exe")
    if file_hash(runtime / "codex.exe") != CODEX_SHA256:
        raise SafetyError("Staged audit client changed")
    (runtime / "models.json").write_bytes(catalog)  # Public catalog only; no auth cache.
    contracts = runtime / "contracts"
    contracts.mkdir()
    for name, raw in contract_artifacts().items():
        (contracts / name).write_bytes(raw)
    files = {
        path.relative_to(runtime).as_posix(): file_hash(path)
        for path in runtime.rglob("*")
        if path.is_file()
    }
    manifest.update(
        protocol="locus-audit-bundle-v1",
        app_manifest=app.identity,
        review_sid=app.settings["roles"]["review"]["sid"],
        merge_sid=app.settings["roles"]["merge"]["sid"],
        codex_sha256=CODEX_SHA256,
        model=model,
        reasoning_effort=reasoning,
        disabled_features=list(FEATURES),
        files=files,
        installer_sha256=hashlib.sha256(installer).hexdigest(),
    )
    # Preserve the base package manifest in this newly generated namespace.
    manifest_path.rename(directory / "preparation-base.manifest.json")
    raw = canonical(manifest)
    manifest_path.write_bytes(raw)
    package = {
        "bundle": str(directory),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "source_commit": commit,
        "activated": False,
    }
    command = admin_command(package).replace(
        "Install-LocusLoopServices.ps1", "Install-LocusLoopAudit.ps1"
    )
    (directory / "admin-command.txt").write_text(command, encoding="utf-8")
    return package


if __name__ == "__main__":
    try:
        print(json.dumps(build_audit(Path.cwd()), indent=2))
    except Exception:
        print('{"status":"blocked","reason":"audit_package_failed","activated":false}')
        raise SystemExit(2) from None
