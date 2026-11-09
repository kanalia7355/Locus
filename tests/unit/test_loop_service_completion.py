"""Service registration recovery: synthetic credentials, inventory and OS lookups."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from loop_engine.service_bundle import BundleError, completion_request, completion_script
from loop_engine.service_identity import ROLES

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="Actual Windows PowerShell required")


def _functions() -> str:
    source = (ROOT / "scripts/Install-LocusLoopServices.ps1").read_text(encoding="utf-8")
    return source[source.index("function Assert-RegularPath") : source.index("\ntry {\n")]


def _powershell(code: str) -> subprocess.CompletedProcess[bytes]:
    executable = shutil.which("powershell.exe")
    assert executable
    prefix = """$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
foreach($name in @('Microsoft.PowerShell.Management','Microsoft.PowerShell.Utility',
    'Microsoft.PowerShell.Security')) {
    Import-Module (Join-Path $PSHOME ('Modules/'+$name+'/'+$name+'.psd1'))
}
"""
    return subprocess.run(  # noqa: S603 — fixed interpreter, test source and synthetic fixtures
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "& ([scriptblock]::Create([Console]::In.ReadToEnd()))",
        ],
        input=(prefix + code).encode(),
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_completion_pins_require_distinct_local_role_identities() -> None:
    review = "S-1-5-21-1-2-3-1001"
    merge = "S-1-5-21-1-2-3-1002"
    assert completion_request("a" * 64, review, merge)["merge_sid"] == merge
    for digest, left, right in (("bad", review, merge), ("a" * 64, review, review)):
        with pytest.raises(BundleError):
            completion_request(digest, left, right)
    with pytest.raises(BundleError):
        completion_request("a" * 64, review, "S-1-5-18")


def _generated() -> bytes:
    return completion_script(
        (ROOT / "scripts/Install-LocusLoopServices.ps1").read_bytes(),
        (ROOT / "scripts/Complete-LocusLoopServices.ps1").read_bytes(),
    )


def test_completion_uses_exact_shared_definitions_without_template_fallback() -> None:
    generated = _generated()
    assert b"# LOCUS_SHARED_" not in generated
    assert b"function Assert-ServiceCompletion" in generated
    with pytest.raises(BundleError):
        completion_script((ROOT / "scripts/Install-LocusLoopServices.ps1").read_bytes(), b"invalid")


def test_completion_bytes_are_identical_for_lf_and_windows_crlf() -> None:
    installer = (ROOT / "scripts/Install-LocusLoopServices.ps1").read_text(encoding="utf-8")
    template = (ROOT / "scripts/Complete-LocusLoopServices.ps1").read_text(encoding="utf-8")
    assert completion_script(installer.encode(), template.encode()) == completion_script(
        installer.replace("\n", "\r\n").encode(), template.replace("\n", "\r\n").encode()
    )


@WINDOWS
def test_generated_completion_helper_parses_without_execution() -> None:
    literal = _generated().decode().replace("'", "''")
    result = _powershell(
        "$source='" + literal + "'; $t=$null; $e=$null;"
        "[Management.Automation.Language.Parser]::ParseInput($source,[ref]$t,[ref]$e)|Out-Null;"
        "if($e.Count){throw 'Invalid completion syntax'}"
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


@WINDOWS
def test_actual_credential_username_is_preserved_for_both_installation_paths() -> None:
    for filename in ("Install-LocusLoopServices.ps1", "Complete-LocusLoopServices.ps1"):
        source = (ROOT / "scripts" / filename).read_text(encoding="utf-8")
        assignment = next(line for line in source.splitlines() if "$credentials[$role] =" in line)
        probe = (
            """
$credentials=@{}
foreach($role in @('review','merge')) {
    $account='locus_loop_'+$role
    $item=[pscustomobject]@{account=$account}
    $secure=[Security.SecureString]::new(); $secure.AppendChar([char]120); $secure.MakeReadOnly()
"""
            + assignment
            + r"""
    if($credentials[$role].UserName -cne ('.\'+$account)){throw 'Service username lost'}
    if(-not $credentials[$role].Password.IsReadOnly()){throw 'Mutable service credential'}
}
'credential_identities_passed'
"""
        )
        result = _powershell(probe)
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        assert b"credential_identities_passed" in result.stdout


@WINDOWS
def test_setup_diagnostic_excludes_exception_messages_and_reports_native_code() -> None:
    result = _powershell(
        _functions() + "\nWrite-SafeSetupFailure 'synthetic_stage' "
        "([ComponentModel.Win32Exception]::new(5,'opaque diagnostic sentinel'))"
    )
    assert result.returncode == 0
    assert b"opaque diagnostic sentinel" not in result.stderr + result.stdout
    report = json.loads(result.stderr)
    assert report["native_error_code"] == 5
    assert report["stage"] == "synthetic_stage"
    assert "message" not in report


def _fixture(directory: Path, case: str) -> dict[str, object]:
    operator = "S-1-5-21-11-22-33-1000"
    review = "S-1-5-21-11-22-33-1001"
    merge = "S-1-5-21-11-22-33-1002"
    private = {"S-1-5-18": 2032127, "S-1-5-32-544": 2032127}
    readers = {**private, operator: 0x1200A9, review: 0x1200A9, merge: 0x1200A9}
    acl: dict[str, dict[str, int]] = {}
    old_manifest = {
        "protocol": "locus-service-bundle-v1",
        "source_clean": True,
        "python_version": "3.14.10",
        "operator_sid": operator,
        "project_root": r"C:\synthetic-project",
        "files": {"pkg/a.txt": hashlib.sha256(b"synthetic").hexdigest()},
    }
    old_raw = json.dumps(old_manifest).encode()
    old_hash = hashlib.sha256(old_raw).hexdigest()
    active = {
        **old_manifest,
        "partial_recovery": {"previous_manifest_sha256": old_hash, "review_sid": review},
    }
    active_raw = json.dumps(active).encode()
    active_hash = hashlib.sha256(active_raw).hexdigest()
    root = directory / "deployment"
    root.mkdir(parents=True)
    acl[str(root)] = readers
    runtimes = root / "runtimes"
    runtimes.mkdir()
    acl[str(runtimes)] = readers
    for digest, raw, rules in ((old_hash, old_raw, private), (active_hash, active_raw, readers)):
        runtime = runtimes / digest
        (runtime / "pkg").mkdir(parents=True)
        (runtime / "pkg/a.txt").write_bytes(b"synthetic")
        manifest_path = runtimes / (digest + ".manifest.json")
        manifest_path.write_bytes(raw)
        for path in (runtime, runtime / "pkg", runtime / "pkg/a.txt", manifest_path):
            acl[str(path)] = rules
    settings = {
        "protocol": "locus-services-v1",
        "mode": "active" if case == "mode" else "prepare",
        "runtime_root": str(runtimes / active_hash),
        "operator_sid": operator,
        "project_root": old_manifest["project_root"],
        "roles": {
            role: {
                "service": values[0],
                "account": values[1],
                "app_id": values[2],
                "installation_id": values[3],
                "sid": review if role == "review" else merge,
            }
            for role, values in ROLES.items()
        },
    }
    if case == "role":
        settings["roles"]["merge"]["app_id"] = 1  # type: ignore[index]
    settings_path = root / "settings.json"
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    acl[str(settings_path)] = readers
    intent = {
        "protocol": "locus-partial-recovery-v1",
        "manifest_sha256": active_hash,
        "previous_manifest_sha256": old_hash,
        "review_sid": review,
    }
    if case == "partial_intent":
        intent["review_sid"] = merge
    intent_path = root / "partial-recovery-intent.json"
    intent_path.write_text(json.dumps(intent), encoding="utf-8")
    acl[str(intent_path)] = private
    state = root / "state"
    state.mkdir()
    acl[str(state)] = readers
    for role, identity in (("review", review), ("merge", merge)):
        role_state = state / role
        role_state.mkdir()
        canary = role_state / "isolation-canary.txt"
        canary.write_text(
            "changed" if case == "canary" else "synthetic role isolation canary", encoding="utf-8"
        )
        rules = {**private, operator: 0x1200A9, identity: 0x1301BF}
        acl[str(role_state)] = rules
        acl[str(canary)] = rules
    if case == "active_manifest":
        (runtimes / (active_hash + ".manifest.json")).write_bytes(active_raw + b" ")
    if case == "old_manifest":
        (runtimes / (old_hash + ".manifest.json")).write_bytes(old_raw + b" ")
    if case == "runtime":
        (runtimes / active_hash / "pkg/a.txt").write_bytes(b"changed")
    if case == "directory":
        (runtimes / active_hash / "unexpected").mkdir()
    if case == "state_data":
        (state / "merge/credential-import-intent.json").write_bytes(b"preserve")
    if case == "completion_intent":
        (root / "service-completion-intent.json").write_bytes(b"preserve")
    return {
        "root": str(root),
        "profiles": str(directory / "profiles"),
        "case": case,
        "expected_acl": acl,
        "new": {
            "operator_sid": operator,
            "project_root": old_manifest["project_root"],
            "service_completion": completion_request(active_hash, review, merge),
        },
    }


@WINDOWS
def test_completion_preflight_preserves_unknown_or_used_state(tmp_path: Path) -> None:
    failures = {
        "valid": "",
        "mode": "Completion settings differ",
        "role": "Completion role differs",
        "active_manifest": "Active completion manifest changed",
        "old_manifest": "Old completion manifest changed",
        "runtime": "Completion runtime changed",
        "directory": "Completion directory inventory differs",
        "state_data": "Nonempty completion state preserved",
        "canary": "Completion state canary differs",
        "completion_intent": "Unknown completion state or prior completion intent preserved",
        "partial_intent": "Partial recovery intent differs",
        "existing_service": "Existing completion service preserved",
        "profile": "Partial Review identity differs",
        "used": "Partial Review identity differs",
        "wrong_sid": "Partial Review identity differs",
        "grouped": "Grouped Review account preserved",
        "acl": "Sealed ACL rejected",
    }
    fixtures = []
    for case, reason in failures.items():
        fixture = _fixture(tmp_path / case, case)
        fixture["expected_failure"] = reason
        fixtures.append(fixture)
    literal = json.dumps(fixtures).replace("'", "''")
    probe = (
        "$fixtures='"
        + literal
        + "' | ConvertFrom-Json\n"
        + r"""
function Assert-SealedAcl([string]$Path, $Rules) {
    if($fixture.case -eq 'acl'){throw 'Sealed ACL rejected'}
    $expected=$fixture.expected_acl.PSObject.Properties[$Path]
    if($null -eq $expected -or $Rules.Count -ne @($expected.Value.PSObject.Properties).Count){
        throw 'ACL policy differs'
    }
    foreach($identity in $Rules.Keys) {
        $entry=$expected.Value.PSObject.Properties[$identity]
        if($null -eq $entry -or $entry.Value -ne $Rules[$identity]){throw 'ACL policy differs'}
    }
}
function Find-LocalUser([string]$Name) {
    $identity=$fixture.new.service_completion.review_sid; $last=$null
    if($Name -eq 'locus_loop_merge'){$identity=$fixture.new.service_completion.merge_sid}
    if($fixture.case -eq 'wrong_sid'){$identity='S-1-5-21-11-22-33-1009'}
    if($fixture.case -eq 'used'){$last=[datetime]'2026-01-01'}
    return [pscustomobject]@{Name=$Name;SID=[pscustomobject]@{Value=$identity};
        Enabled=$true;LastLogon=$last}
}
function Get-Service {
    [CmdletBinding()]param([string]$Name)
    if($fixture.case -eq 'existing_service'){return [pscustomobject]@{Name=$Name}}
    $record=[Management.Automation.ErrorRecord]::new([Exception]::new('synthetic absence'),
        'NoServiceFoundForGivenName',[Management.Automation.ErrorCategory]::ObjectNotFound,$Name)
    $PSCmdlet.ThrowTerminatingError($record)
}
function Get-ItemProperty {return [pscustomobject]@{ProfilesDirectory=$fixture.profiles}}
function Test-Path([string]$LiteralPath) {
    if($LiteralPath.StartsWith('Registry::')){return ($fixture.case -eq 'profile')}
    return Microsoft.PowerShell.Management\Test-Path -LiteralPath $LiteralPath
}
function Get-CimInstance {}
function Get-LocalGroup {if($fixture.case -eq 'grouped'){return 'synthetic-group'}}
function Get-LocalGroupMember {
    return [pscustomobject]@{SID=[pscustomobject]@{Value=$fixture.new.service_completion.merge_sid}}
}
$passed=0
foreach($fixture in $fixtures) {
    $blocked=$false; $failure=''; $result=$null
    try {$result=Assert-ServiceCompletion $fixture.new $fixture.root}
    catch {$blocked=$true; $failure=$_.Exception.Message}
    if($fixture.case -eq 'valid') {
        if($blocked){throw ('Valid completion rejected: '+$failure)}
        if($result.mode -cne 'prepare'){throw 'Completion activation changed'}
    } elseif(-not $blocked -or -not $failure.StartsWith($fixture.expected_failure)) {
        throw ('Wrong completion result for '+$fixture.case+': '+$failure)
    }
    $passed++
}
@{scenarios_passed=$passed} | ConvertTo-Json -Compress
"""
    )
    result = _powershell(_functions() + "\n" + probe)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert json.loads(result.stdout)["scenarios_passed"] == len(fixtures)
