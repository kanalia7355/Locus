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
    body = body.replace(
        "'C:\\ProgramData\\LocusLoopAuditV1'", "'" + str(fixture).replace("'", "''") + "'"
    )
    script = tmp_path / "synthetic-diagnostic.ps1"
    script.write_text(body, encoding="utf-8")
    before = {p: p.read_bytes() for p in fixture.rglob("*") if p.is_file()}
    result = ProcessRunner().run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(script)],
        tmp_path,
        timeout=20,
    )
    assert result.outcome == "exit" and result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["state_changed"] is False and response["credential_values_accessed"] is False
    assert response["provider_request_sent"] is False
    phases = {entry["record"]: entry["phase"] for entry in response["records"]}
    assert phases["home-authentication.json"] == "active_use"
    assert phases["synthetic-model-proof.json"] == "started"
    assert phases["keyring-probe.json"] == "unknown"
    assert "synthetic-field-must-not-be-displayed" not in result.stdout
    assert before == {p: p.read_bytes() for p in fixture.rglob("*") if p.is_file()}
