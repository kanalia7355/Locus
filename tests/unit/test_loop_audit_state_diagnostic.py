"""Actual diagnostic body on synthetic data only, never protected deployment."""

import json
import sys
from pathlib import Path

import pytest

from loop_engine.process import ProcessRunner


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell runtime required")
def test_read_only_diagnostic_filters_nonsecret_record_fields(tmp_path):
    from loop_engine.windows_pipe import Native

    fixture = tmp_path / "synthetic"
    state = fixture / "state"
    for name in ("home", "probe-home"):
        (state / name / "secrets").mkdir(parents=True)
        (state / name / "secrets/codex_auth.age").write_bytes(b"synthetic-ciphertext")
    (fixture / "settings.json").write_text(
        json.dumps(
            {
                "protocol": "locus-audit-service-v1",
                "mode": "prepare",
                "operator_sid": Native().current_sid(),
            }
        )
    )
    (state / "home-authentication.json").write_text(
        json.dumps({"phase": "active_use", "key_metadata": "synthetic-field-must-not-be-displayed"})
    )
    (state / "synthetic-model-proof.json").write_text(json.dumps({"phase": "started"}))
    (state / "keyring-probe.json").write_text(json.dumps({"phase": "unrecognized-value"}))
    source = (
        Path(__file__).resolve().parents[2] / "scripts/Inspect-LocusLoopAuditState.ps1"
    ).read_text()
    # Execute the actual body solely against this generated synthetic namespace.
    # The production admin requirement and protected namespace are not changed.
    body = "\n".join(line for line in source.splitlines() if not line.startswith("#Requires"))
    # Keep param first; marker is synthetic diagnostic output, never state data.
    body = body.replace(
        "Set-StrictMode -Version Latest",
        "[Console]::Error.WriteLine('locus-test-script-entered')\nSet-StrictMode -Version Latest",
        1,
    )
    body = body.replace(
        "'C:\\ProgramData\\LocusLoopAuditV1'", "'" + str(fixture).replace("'", "''") + "'"
    )
    body = body.replace('@"C:\\ProgramData\\LocusLoopAuditV1\\state"', '@"' + str(state) + '"')
    script = tmp_path / "synthetic-diagnostic.ps1"
    body += (
        "\n$rejected=$false;try {[LocusAuditRecordReaderV1]::Read('auth.json')}"
        " catch {$rejected=$true};if(-not $rejected){throw 'Credential filename admitted'}\n"
    )
    script.write_text(body, encoding="utf-8")
    before = {p: p.read_bytes() for p in fixture.rglob("*") if p.is_file()}
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "$ErrorActionPreference='Stop'; $global:LASTEXITCODE=0; "
        "[Console]::Error.WriteLine('locus-test-host-entered'); "
        '$env:PSModulePath="$PSHOME\\Modules"; '
        "[Console]::Error.WriteLine('locus-test-modules-start'); "
        'Import-Module "$PSHOME\\Modules\\Microsoft.PowerShell.Utility" -ErrorAction Stop; '
        'Import-Module "$PSHOME\\Modules\\Microsoft.PowerShell.Management" -ErrorAction Stop; '
        "[Console]::Error.WriteLine('locus-test-modules-ready'); & '"
        + str(script).replace("'", "''")
        + "'; exit $LASTEXITCODE",
    ]
    result = ProcessRunner().run(command, tmp_path, timeout=20)
    assert result.outcome == "exit" and result.returncode == 0, result
    assert "locus-test-script-entered" in result.stderr
    assert "locus-test-modules-ready" in result.stderr
    response = json.loads(result.stdout)
    assert response["state_changed"] is False and response["credential_values_accessed"] is False
    assert response["provider_request_sent"] is False
    phases = {entry["record"]: entry["phase"] for entry in response["records"]}
    assert phases["home-authentication.json"] == "active_use"
    assert phases["synthetic-model-proof.json"] == "started"
    assert phases["keyring-probe.json"] == "unknown"
    assert "synthetic-field-must-not-be-displayed" not in result.stdout
    assert before == {p: p.read_bytes() for p in fixture.rglob("*") if p.is_file()}
    # Reject an oversized nonsecret fixture with useful, bounded diagnostics,
    # without forwarding file contents or changing anything.
    (state / "home-authentication.json").write_bytes(b"x" * 9000)
    before = {p: p.read_bytes() for p in fixture.rglob("*") if p.is_file()}
    rejected = ProcessRunner().run(
        command,
        tmp_path,
        timeout=20,
    )
    assert rejected.outcome == "exit" and rejected.returncode == 2, rejected
    assert "locus-test-modules-ready" in rejected.stderr
    failure = json.loads(rejected.stdout)
    assert failure["stage"] == "nonsecret_record_read"
    assert failure["record"] == "home-authentication.json"
    assert 0 < len(failure["error_chain"]) <= 8
    assert all(set(entry) == {"error_type", "hresult"} for entry in failure["error_chain"])
    assert "x" * 20 not in rejected.stdout
    assert before == {p: p.read_bytes() for p in fixture.rglob("*") if p.is_file()}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell runtime required")
def test_connection_preparation_reads_two_records_and_acl_only(tmp_path):
    import hashlib

    from loop_engine.windows_pipe import Native

    fixture = tmp_path / "synthetic"
    state = fixture / "state"
    state.mkdir(parents=True)
    operator = fixture / "operator"
    home = operator / ".codex"
    home.mkdir(parents=True)
    # Synthetic canaries only. Production code never reads these file contents.
    (home / "auth.json").write_text("synthetic-credential-must-never-appear")
    (home / "config.toml").write_text("synthetic-config-must-never-appear")
    (fixture / "settings.json").write_text(
        json.dumps(
            {
                "protocol": "locus-audit-service-v1",
                "mode": "prepare",
                "operator_sid": Native().current_sid(),
            }
        )
    )
    for name in ("synthetic-model-proof.json", "transport-model-proof.json"):
        (state / name).write_text(
            json.dumps({"phase": "started", "private": "record-secret-canary"})
        )
    source = (
        Path(__file__).resolve().parents[2] / "scripts/Inspect-LocusLoopAuditState.ps1"
    ).read_text()
    body = "\n".join(line for line in source.splitlines() if not line.startswith("#Requires"))
    body = body.replace(
        "'C:\\ProgramData\\LocusLoopAuditV1'", "'" + str(fixture).replace("'", "''") + "'"
    )
    body = body.replace('@"C:\\ProgramData\\LocusLoopAuditV1\\state"', '@"' + str(state) + '"')
    body = body.replace(
        "[Environment]::GetFolderPath('UserProfile')", "'" + str(operator).replace("'", "''") + "'"
    )
    # Grant a synthetic orphan SID only inside this newly created test tree.
    setup = (
        "$testPath='" + str(home).replace("'", "''") + "'; "
        "$testAcl=Get-Acl -LiteralPath $testPath; "
        "$testSid=[Security.Principal.SecurityIdentifier]::new('S-1-5-21-1-2-3-9999'); "
        "$testRule=[Security.AccessControl.FileSystemAccessRule]::new($testSid, "
        "[Security.AccessControl.FileSystemRights]::ReadAndExecute, "
        "[Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit', "
        "[Security.AccessControl.PropagationFlags]::None, "
        "[Security.AccessControl.AccessControlType]::Allow); "
        "$testAcl.AddAccessRule($testRule); Set-Acl -LiteralPath $testPath -AclObject $testAcl; "
    )
    body = body.replace(
        "Set-StrictMode -Version Latest", setup + "\nSet-StrictMode -Version Latest", 1
    )
    script = tmp_path / "synthetic-preparation.ps1"
    script.write_text(body, encoding="utf-8")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    manifest = {
        "protocol": "locus-connection-preparation-diagnostic-v1",
        "mutations_allowed": False,
        "operator_sid": Native().current_sid(),
        "operator_home": str(home),
    }
    manifest_path = bundle / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(script),
        "-ConnectionPreparation",
        "-Bundle",
        str(bundle),
        "-ManifestSha256",
        digest,
    ]
    before = {p: p.read_bytes() for p in fixture.rglob("*") if p.is_file()}
    result = ProcessRunner().run(command, tmp_path, timeout=20)
    assert result.outcome == "exit" and result.returncode == 0, result
    response = json.loads(result.stdout)
    assert response["operation"] == "read_only_connection_preparation"
    assert not response["state_changed"] and not response["credential_values_accessed"]
    assert not response["provider_request_sent"]
    assert response["budget"]["remaining_trials_verified"] is False
    assert response["budget"]["additional_slots_granted"] == 0
    assert {r["record"] for r in response["records"]} == {
        "synthetic-model-proof.json",
        "transport-model-proof.json",
    }
    for entry in response["records"]:
        assert (
            entry["record_sha256"]
            == hashlib.sha256((state / entry["record"]).read_bytes()).hexdigest()
        )
    assert any(
        e["sid"] == "S-1-5-21-1-2-3-9999" and e["validator_principal_rejection"]
        for target in response["acl"]
        for e in target["entries"]
    )
    for canary in (
        "synthetic-credential-must-never-appear",
        "synthetic-config-must-never-appear",
        "record-secret-canary",
    ):
        assert canary not in result.stdout + result.stderr
    assert before == {p: p.read_bytes() for p in fixture.rglob("*") if p.is_file()}
    # Manifest changes stop before either protected-record or ACL inspection.
    manifest["operator_home"] = str(tmp_path)
    manifest_path.write_text(json.dumps(manifest))
    denied = ProcessRunner().run(command, tmp_path, timeout=20)
    assert denied.returncode == 2 and json.loads(denied.stdout)["stage"] == "manifest_validation"
    outside_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    outside = ProcessRunner().run(command[:-1] + [outside_digest], tmp_path, timeout=20)
    assert outside.returncode == 2
    assert json.loads(outside.stdout)["stage"] == "operator_acl_metadata"
    manifest_path.write_bytes(b"x" * 9000)
    oversized = ProcessRunner().run(command, tmp_path, timeout=20)
    assert oversized.returncode == 2
    assert json.loads(oversized.stdout)["stage"] == "manifest_validation"
    assert "x" * 20 not in oversized.stdout
