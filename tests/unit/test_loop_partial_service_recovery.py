"""Recovery pins and never-used-account guards; no identity changes or real keys."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from loop_engine.service_bundle import BundleError, recovery_request


def test_normal_bundle_does_not_request_account_adoption() -> None:
    assert recovery_request(None, None) is None


@pytest.mark.parametrize(
    ("manifest", "identity"),
    [
        (None, "S-1-5-21-1-2-3-1001"),
        ("a" * 64, None),
        ("../manifest", "S-1-5-21-1-2-3-1001"),
        ("a" * 63, "S-1-5-21-1-2-3-1001"),
        ("a" * 64, "S-1-1-0"),
        ("a" * 64, "S-1-5-18"),
        ("a" * 64, "S-1-5-21-1-2-3-4294967296"),
    ],
)
def test_recovery_requires_both_exact_pins(manifest: str | None, identity: str | None) -> None:
    with pytest.raises(BundleError):
        recovery_request(manifest, identity)


def test_recovery_metadata_is_part_of_the_hashed_manifest_input() -> None:
    result = recovery_request("a" * 64, "S-1-5-21-1-2-3-1001")
    assert result == {
        "previous_manifest_sha256": "a" * 64,
        "review_sid": "S-1-5-21-1-2-3-1001",
    }


@pytest.mark.skipif(sys.platform != "win32", reason="Actual PowerShell recovery guards required")
def test_only_exact_never_used_identity_is_eligible() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "scripts/Install-LocusLoopServices.ps1"
    ).read_text()
    functions = source[source.index("function Assert-RegularPath") : source.index("\ntry {\n")]
    # Execute pure guards only. No installer body, native helpers or OS changes.
    probe = r"""
$expected = 'S-1-5-21-11-22-33-1001'
function Fresh { return [pscustomobject]@{ Name='locus_loop_review';
    SID=[pscustomobject]@{Value=$expected}; Enabled=$true; LastLogon=$null } }
$user=Fresh
Assert-RecoveryAccount $user $expected $false $false
foreach($case in @('absent','name','sid','disabled','logon','profile','in_use')) {
    $user=Fresh; $profile=$false; $used=$false
    switch($case) {
        'absent' { $user=$null }
        'name' { $user.Name='unrelated_user' }
        'sid' { $user.SID.Value='S-1-5-21-11-22-33-1002' }
        'disabled' { $user.Enabled=$false }
        'logon' { $user.LastLogon=[datetime]'2026-01-01' }
        'profile' { $profile=$true }
        'in_use' { $used=$true }
    }
    $blocked=$false
    try { Assert-RecoveryAccount $user $expected $profile $used } catch { $blocked=$true }
    if(-not $blocked){throw 'Recovery guard accepted an unsafe identity'}
}
'guards_passed'
"""
    executable = shutil.which("powershell.exe")
    assert executable
    result = subprocess.run(  # noqa: S603 — fixed pure guards, input is repository source
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest;"
            " & ([scriptblock]::Create([Console]::In.ReadToEnd()))",
        ],
        input=(
            "Import-Module (Join-Path $PSHOME "
            "'Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1')\n"
            + functions
            + "\n"
            + probe
        ).encode(),
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0
    assert b"guards_passed" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Actual Windows ACL required")
def test_recovery_rejects_operator_owned_deployment(tmp_path: Path) -> None:
    source = (
        Path(__file__).resolve().parents[2] / "scripts/Install-LocusLoopServices.ps1"
    ).read_text()
    functions = source[source.index("function Assert-RegularPath") : source.index("\ntry {\n")]
    # A real operator-owned directory cannot be treated as a private SYSTEM deployment.
    literal = str(tmp_path).replace("'", "''")
    probe = (
        f"$blocked=$false; try {{ Assert-PrivateAcl '{literal}' }} catch {{$blocked=$true}};"
        "if(-not $blocked){throw 'Untrusted deployment accepted'}; 'acl_rejected'"
    )
    executable = shutil.which("powershell.exe")
    assert executable
    result = subprocess.run(  # noqa: S603 — reads only a synthetic directory ACL
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest;"
            " & ([scriptblock]::Create([Console]::In.ReadToEnd()))",
        ],
        input=(functions + "\n" + probe).encode(),
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0
    assert b"acl_rejected" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell preflight required")
@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "wrong_sid",
        "changed_manifest",
        "changed_file",
        "extra_file",
        "extra_directory",
        "intent",
        "foreign_root_file",
        "profile",
        "service_use",
        "grouped",
        "merge_exists",
        "used",
        "wrong_operator",
        "private_acl",
    ],
)
def test_complete_recovery_preflight_with_synthetic_inventory(tmp_path: Path, case: str) -> None:
    operator = "S-1-5-21-11-22-33-1000"
    review = "S-1-5-21-11-22-33-1001"
    payload = b"synthetic runtime content"
    old = {
        "protocol": "locus-service-bundle-v1",
        "source_clean": True,
        "operator_sid": operator,
        "project_root": r"C:\synthetic-project",
        "files": {"pkg/a.txt": hashlib.sha256(payload).hexdigest()},
    }
    raw = json.dumps(old).encode()
    identity = hashlib.sha256(raw).hexdigest()
    root = tmp_path / "deployment"
    runtime = root / "runtimes" / identity
    (runtime / "pkg").mkdir(parents=True)
    (runtime / "pkg/a.txt").write_bytes(payload)
    manifest = runtime.parent / (identity + ".manifest.json")
    manifest.write_bytes(raw + (b" " if case == "changed_manifest" else b""))
    if case == "changed_file":
        (runtime / "pkg/a.txt").write_bytes(b"changed")
    if case == "extra_file":
        (runtime / "unexpected.txt").write_bytes(b"preserve")
    if case == "extra_directory":
        (runtime / "unexpected-empty").mkdir()
    if case in {"intent", "foreign_root_file"}:
        name = "partial-recovery-intent.json" if case == "intent" else "unknown.txt"
        (root / name).write_bytes(b"preserve")
    source = (
        Path(__file__).resolve().parents[2] / "scripts/Install-LocusLoopServices.ps1"
    ).read_text()
    functions = source[source.index("function Assert-RegularPath") : source.index("\ntry {\n")]
    fixtures = {
        "root": str(root),
        "profiles": str(tmp_path / "profiles"),
        "case": case,
        "recovery": {"previous_manifest_sha256": identity, "review_sid": review},
        "new": {"operator_sid": operator, "project_root": old["project_root"]},
        "expected_failure": {
            "wrong_sid": "Partial Review identity differs",
            "changed_manifest": "Previous installed manifest changed",
            "changed_file": "Previous runtime changed",
            "extra_file": "Previous inventory differs",
            "extra_directory": "Previous directory inventory differs",
            "intent": "Unknown partial deployment contents preserved",
            "foreign_root_file": "Unknown partial deployment contents preserved",
            "profile": "Partial Review identity differs",
            "service_use": "Partial Review identity differs",
            "grouped": "Grouped Review account preserved",
            "merge_exists": "Existing Merge account preserved",
            "used": "Partial Review identity differs",
            "wrong_operator": "Previous deployment identity differs",
            "private_acl": "ACL denied",
        }.get(case, ""),
    }
    # Only ACL/account/registry/CIM lookups are mocked; inventory parsing and
    # hashing read the real synthetic tree. No installer mutation body is run.
    literal = json.dumps(fixtures).replace("'", "''")
    probe = (
        "$fixture = '"
        + literal
        + "' | ConvertFrom-Json\n"
        + r"""
function Assert-PrivateAcl([string]$Path) {
    if($fixture.case -eq 'private_acl'){throw 'ACL denied'}
    if(-not $Path.StartsWith($fixture.root)){throw 'Fixture path escaped'}
}
function Find-LocalUser([string]$Name) {
    if($Name -eq 'locus_loop_merge') {
        if($fixture.case -eq 'merge_exists'){return [pscustomobject]@{Name=$Name}}
        return $null
    }
    if($Name -ne 'locus_loop_review'){throw 'Unexpected account lookup'}
    $identity=$fixture.recovery.review_sid; $last=$null
    if($fixture.case -eq 'wrong_sid'){$identity='S-1-5-21-11-22-33-1002'}
    if($fixture.case -eq 'used'){$last=[datetime]'2026-01-01'}
    return [pscustomobject]@{Name=$Name; SID=[pscustomobject]@{Value=$identity};
        Enabled=$true; LastLogon=$last}
}
function Get-ItemProperty { return [pscustomobject]@{ProfilesDirectory=$fixture.profiles} }
function Test-Path([string]$LiteralPath) {
    if($LiteralPath.StartsWith('Registry::')){return ($fixture.case -eq 'profile')}
    return Microsoft.PowerShell.Management\Test-Path -LiteralPath $LiteralPath
}
function Get-CimInstance {
    if($fixture.case -eq 'service_use'){return [pscustomobject]@{StartName='.\locus_loop_review'}}
}
function Get-LocalGroup { if($fixture.case -eq 'grouped'){return 'synthetic-group'} }
function Get-LocalGroupMember {
    return [pscustomobject]@{SID=[pscustomobject]@{Value=$fixture.recovery.review_sid}}
}
if($fixture.case -eq 'wrong_operator'){$fixture.new.operator_sid='S-1-5-21-11-22-33-1009'}
$blocked=$false; $result=$null; $failure=''
try { $result=Assert-PartialRecovery $fixture.recovery $fixture.new $fixture.root }
catch { $blocked=$true; $failure=$_.Exception.Message }
if($fixture.case -eq 'valid') {
    if($blocked){throw ('Valid recovery rejected: ' + $failure)}
    if($result.SID.Value -ne $fixture.recovery.review_sid){throw 'Recovery SID changed'}
} elseif(-not $blocked) { throw 'Unsafe recovery accepted' }
elseif(-not $failure.StartsWith($fixture.expected_failure)) {
    throw ('Wrong preflight failure: ' + $failure)
}
'preflight_passed'
"""
    )
    executable = shutil.which("powershell.exe")
    assert executable
    result = subprocess.run(  # noqa: S603 — preflight only, synthetic inputs and mocked OS queries
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest;"
            " & ([scriptblock]::Create([Console]::In.ReadToEnd()))",
        ],
        input=(
            "Import-Module (Join-Path $PSHOME "
            "'Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1')\n"
            + functions
            + "\n"
            + probe
        ).encode(),
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert b"preflight_passed" in result.stdout
