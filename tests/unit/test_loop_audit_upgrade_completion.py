"""Exercise actual .NET replacement binding and the completion-only boundary."""

import sys
from pathlib import Path

import pytest

from loop_engine.audit_upgrade_completion import completion_source
from loop_engine.process import ProcessRunner

ROOT = Path(__file__).resolve().parents[2]


def source():
    return completion_source(
        *[
            (ROOT / name).read_bytes()
            for name in (
                "scripts/Install-LocusLoopServices.ps1",
                "scripts/Install-LocusLoopAudit.template.ps1",
                "scripts/Upgrade-LocusLoopAudit.template.ps1",
                "scripts/Complete-LocusLoopAuditUpgrade.template.ps1",
            )
        ]
    )


def test_completion_does_not_redeploy_or_touch_authentication():
    script = source().decode()
    for forbidden in (
        "::CopyPinned(",
        "::NewPassword(",
        "Set-LocalUser",
        "New-LocalUser",
        "New-Service",
        "Remove-Item",
        "home-authentication.json",
    ):
        assert forbidden not in script
    assert "Assert-SealedMetadata $staged $plan.new_settings" in script
    assert "Assert-SealedMetadata $backup $plan.old_settings" in script
    assert "$intent.helper -cne $plan.upgrade_helper" in script
    assert script.index("'audit-upgrade-completion-intent.json'),") < script.index("Stop-Service")
    assert "IntPtr.Zero,IntPtr.Zero,null,null,null)" in script


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell/.NET binding required")
def test_actual_upgrade_replace_statement_handles_null_backup(tmp_path):
    template = (ROOT / "scripts/Upgrade-LocusLoopAudit.template.ps1").read_text()
    line = next(
        line.strip()
        for line in template.splitlines()
        if line.strip().startswith("[IO.File]::Replace(")
    )
    script = tmp_path / "replace.ps1"
    # These are new generated synthetic files only. Execute the real statement
    # through Windows PowerShell5.1, not the parent shell's .NET runtime.
    script.write_text(
        "param($Root)\n$ErrorActionPreference='Stop'\n"
        "$staged=Join-Path $Root 'new.json';$settingsPath=Join-Path $Root 'old.json'\n"
        "[IO.File]::WriteAllText($staged,'synthetic-new')\n"
        "[IO.File]::WriteAllText($settingsPath,'synthetic-old')\n"
        "try {[IO.File]::Replace($staged,$settingsPath,$null);"
        "throw 'Expected original binding failure'}\n"
        "catch {if($_.Exception -isnot [Management.Automation.MethodInvocationException]){throw}}\n"
        + line
        + "\nif([IO.File]::ReadAllText($settingsPath) -cne 'synthetic-new'){"
        "throw 'Replacement failed'}\n"
        "'actual-replacement-passed'\n",
        encoding="utf-8",
    )
    result = ProcessRunner().run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(script), str(tmp_path)],
        tmp_path,
        timeout=20,
    )
    assert result.returncode == 0 and result.outcome == "exit", result.stderr
    assert "actual-replacement-passed" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell/native compiler required")
def test_completion_parses_and_compiles_without_privileged_execution(tmp_path):
    path = tmp_path / "completion.ps1"
    path.write_bytes(source())
    inspector = tmp_path / "inspect.ps1"
    inspector.write_text(
        "param($Path)\n$t=$null;$e=$null\n"
        "$ast=[Management.Automation.Language.Parser]::ParseFile($Path,[ref]$t,[ref]$e)\n"
        "if($e.Count){throw 'Syntax failed'}\n"
        "$nodes=$ast.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst] "
        "-and $n.GetCommandName() -eq 'Add-Type'},$true)\n"
        "if($nodes.Count -ne 1){throw 'Native boundary differs'}\n"
        "Add-Type -TypeDefinition $nodes[0].CommandElements[2].Value\n'compiled-only'\n",
        encoding="utf-8",
    )
    result = ProcessRunner().run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(inspector), str(path)],
        tmp_path,
        timeout=30,
    )
    assert result.returncode == 0 and result.outcome == "exit", result.stderr
    assert "compiled-only" in result.stdout
