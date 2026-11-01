"""Exercise real PowerShell capability guard and the recovery-only source boundary."""

import json
import sys
from pathlib import Path

import pytest

from loop_engine.audit_completion import completion_source
from loop_engine.audit_profile import FEATURES
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError

ROOT = Path(__file__).resolve().parents[2]


def sources():
    return [
        (ROOT / name).read_bytes()
        for name in (
            "scripts/Install-LocusLoopServices.ps1",
            "scripts/Install-LocusLoopAudit.template.ps1",
            "scripts/Complete-LocusLoopAudit.preflight.ps1",
        )
    ]


def generated():
    return completion_source(
        *sources(),
        previous_bundle=Path("C:/synthetic/previous"),
        active_hash="a" * 64,
        audit_sid="S-1-5-21-1-2-3-1008",
    )


def test_completion_reuses_original_runtime_and_never_recreates_account():
    script = generated().decode()
    assert "New-LocalUser" not in script and "Remove-" not in script
    assert "::CopyPinned($source" not in script
    assert script.index("Assert-AuditPartial $deploymentRoot") < script.index("::NewPassword()")
    assert script.index("::WritePrivate($intentPath") < script.index("Set-LocalUser -SID")
    assert "Assert-UnusedAuditAccount $user 'S-1-5-21-1-2-3-1008'" in script
    assert "Authentication/state already exists; preserve without reset" in script
    assert "audit-completion-intent.json" in script
    with pytest.raises(SafetyError):
        completion_source(
            *sources(),
            previous_bundle=Path("C:/synthetic"),
            active_hash="bad",
            audit_sid="S-1-5-21-1-2-3-1008",
        )


@pytest.mark.skipif(sys.platform != "win32", reason="Actual PowerShell runtime required")
def test_actual_installer_feature_guard_accepts_fixed_versioned_features(tmp_path):
    template = sources()[1].decode().replace("\r\n", "\n")
    start = template.index("    foreach ($feature in $manifest.disabled_features)")
    end = template.index("\n    if ($files.Count", start)
    guard = template[start:end]
    # Run the actual installer guard, not a Python regex copy. No installer
    # account/filesystem/service operation is executed in this diagnostic.
    code = "$ErrorActionPreference='Stop'\nfunction Validate($manifest) {\n" + guard + "\n}\n"
    code += (
        "$manifest = "
        + "'"
        + json.dumps({"disabled_features": list(FEATURES)})
        + "' | ConvertFrom-Json\n"
    )
    code += "Validate $manifest\nforeach($bad in @('UPPER','x.y','x;command','')) {\n"
    code += "$rejected=$false;try {Validate @{disabled_features=@($bad)}} catch {$rejected=$true}\n"
    code += "if(-not $rejected){throw 'Unsafe feature accepted'}\n}\n'fixed-features-pass'\n"
    path = tmp_path / "feature-runtime.ps1"
    path.write_text(code, encoding="utf-8")
    result = ProcessRunner().run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(path)],
        tmp_path,
        timeout=20,
    )
    assert result.outcome == "exit" and result.returncode == 0, result.stderr
    assert "fixed-features-pass" in result.stdout
    assert start < template.index("::MakeDirectory($deploymentRoot)")


@pytest.mark.skipif(sys.platform != "win32", reason="Actual PowerShell runtime required")
def test_generated_completion_parses_and_native_code_compiles_without_execution(tmp_path):
    path = tmp_path / "completion.ps1"
    path.write_bytes(generated())
    inspector = tmp_path / "inspect.ps1"
    inspector.write_text(
        "param($Path)\n$t=$null;$e=$null\n"
        "$ast=[Management.Automation.Language.Parser]::ParseFile($Path,[ref]$t,[ref]$e)\n"
        "if($e.Count){throw 'Completion syntax invalid'}\n"
        "$nodes=$ast.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst] "
        "-and $n.GetCommandName() -eq 'Add-Type'},$true)\n"
        "if($nodes.Count -ne 1){throw 'Native helper boundary changed'}\n"
        "Add-Type -TypeDefinition $nodes[0].CommandElements[2].Value\n'compiled-only'\n",
        encoding="utf-8",
    )
    result = ProcessRunner().run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(inspector), str(path)],
        tmp_path,
        timeout=30,
    )
    assert result.outcome == "exit" and result.returncode == 0, result.stderr
    assert "compiled-only" in result.stdout
