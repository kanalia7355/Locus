"""Exact-record recovery and diagnostic limits; synthetic credentials/IO only."""

import hashlib
import http.client
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import loop_engine.audit_reconciliation as recovery
import loop_engine.audit_runtime as runtime
from loop_engine.audit_auth_state import AuthState
from loop_engine.audit_failure import AuditFailure, validate_diagnostic
from loop_engine.audit_packet import canonical
from loop_engine.audit_transport import AuditRelay
from loop_engine.audit_upgrade import upgrade_source
from loop_engine.process import ProcessResult, ProcessRunner
from loop_engine.security import SafetyError


def fixture(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "secrets").mkdir(parents=True)
    (home / "secrets/codex_auth.age").write_bytes(b"age-encryption.org/v1\nsynthetic-ciphertext")
    state = AuthState(home, metadata=lambda _, direct=False: None if direct else "synthetic-header")
    original = canonical({"phase": "active_use", "key_metadata": "synthetic-header"})
    state.journal.write_bytes(original)
    trial = tmp_path / "synthetic-model-proof.json"
    trial.write_bytes(canonical({"phase": "started", "identity": "b" * 64}))
    deployment = SimpleNamespace(
        state=tmp_path,
        runtime=tmp_path / "runtime",
        identity="a" * 64,
        state_identity="b" * 64,
        require_role=lambda _: None,
    )
    approval = {
        "protocol": "locus-audit-reconciliation-v1",
        "identity": deployment.identity,
        "previous_identity": deployment.state_identity,
        "authentication": hashlib.sha256(original).hexdigest(),
        "trial": hashlib.sha256(trial.read_bytes()).hexdigest(),
        "diagnostic_inference": True,
    }
    monkeypatch.setattr(recovery, "protected_bytes", lambda _: canonical(approval))
    monkeypatch.setattr(recovery, "AuthState", lambda _: state)
    return state, deployment, approval, original


class StatusProcess:
    def __init__(self, success=True):
        self.success = success
        self.calls = []

    def run(self, argv, cwd, **options):
        self.calls.append(argv)
        assert argv[-2:] == ["login", "status"] and "--enable" in argv
        assert options["active_process_limit"] == 1
        return ProcessResult(
            "exit",
            0 if self.success else 1,
            stderr="Logged in using ChatGPT" if self.success else "untrusted failure",
        )


def test_exact_status_reconciliation_preserves_original_and_never_calls_provider(
    tmp_path, monkeypatch
):
    state, deployment, approval, original = fixture(tmp_path, monkeypatch)
    process = StatusProcess()
    result = recovery.reconcile_auth(deployment, deadline=time.monotonic() + 20, process=process)
    assert result["authenticated"] and result["provider_request_sent"] is False
    assert state.check() == "enrolled" and len(process.calls) == 1
    saved = json.loads((tmp_path / "auth-reconciliation.json").read_bytes())
    assert saved["previous_record"] == json.loads(original)
    assert saved["permit"] == approval
    with pytest.raises(SafetyError):
        recovery.reconcile_auth(deployment, deadline=time.monotonic() + 20, process=process)
    assert len(process.calls) == 1


@pytest.mark.parametrize(
    "failure", ["changed_auth", "changed_trial", "wrong_identity", "missing_key"]
)
def test_mismatched_recovery_never_invokes_auth_cli(tmp_path, monkeypatch, failure):
    state, deployment, approval, original = fixture(tmp_path, monkeypatch)
    if failure == "changed_auth":
        approval["authentication"] = "f" * 64
    if failure == "changed_trial":
        approval["trial"] = "f" * 64
    if failure == "wrong_identity":
        approval["identity"] = "f" * 64
    if failure == "missing_key":
        state.metadata = lambda *_, **__: None
    process = StatusProcess()
    with pytest.raises(SafetyError):
        recovery.reconcile_auth(deployment, deadline=time.monotonic() + 20, process=process)
    assert process.calls == [] and state.journal.read_bytes() == original
    assert not (tmp_path / "auth-reconciliation.json").exists()


def test_failed_status_stays_held_without_retry_or_cache_changes(tmp_path, monkeypatch):
    state, deployment, _, original = fixture(tmp_path, monkeypatch)
    process = StatusProcess(False)
    with pytest.raises(SafetyError):
        recovery.reconcile_auth(deployment, deadline=time.monotonic() + 20, process=process)
    assert state.journal.read_bytes() == original
    with pytest.raises(FileExistsError):
        recovery.reconcile_auth(deployment, deadline=time.monotonic() + 20, process=process)
    assert len(process.calls) == 1


def test_diagnostic_failure_is_durable_once_and_does_not_replay_original(tmp_path, monkeypatch):
    _, deployment, _, _ = fixture(tmp_path, monkeypatch)
    original = (tmp_path / "synthetic-model-proof.json").read_bytes()
    calls = []

    class FailedModel:
        def __init__(self, _):
            pass

        def review(self, *args, **kwargs):
            calls.append(True)
            raise AuditFailure("upstream_response", "policy", 403)

    monkeypatch.setattr(runtime, "RuntimeModel", FailedModel)
    with pytest.raises(AuditFailure):
        runtime.fixed_self_test(deployment, deadline=time.monotonic() + 20, diagnostic=True)
    with pytest.raises(SafetyError):
        runtime.fixed_self_test(deployment, deadline=time.monotonic() + 20, diagnostic=True)
    assert calls == [True]
    assert (tmp_path / "synthetic-model-proof.json").read_bytes() == original
    assert json.loads((tmp_path / "transport-model-failure.json").read_bytes()) == {
        "stage": "upstream_response",
        "reason": "policy",
        "http_status": 403,
    }


def test_diagnostics_reject_arbitrary_messages_and_invalid_status():
    for value in (
        {"stage": "credential-value", "reason": "network", "http_status": None},
        {"stage": "upstream_headers", "reason": "network", "http_status": True},
        {"stage": "upstream_headers", "reason": "network", "http_status": 403, "raw": "secret"},
    ):
        with pytest.raises(SafetyError):
            validate_diagnostic(value)


@pytest.mark.parametrize("failure", ["status", "timeout"])
def test_relay_diagnostic_reveals_only_stage_and_status_without_retry(monkeypatch, failure):
    calls = []

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            calls.append(True)

        def getresponse(self):
            if failure == "timeout":
                raise TimeoutError("synthetic-secret-error-must-not-leak")
            return SimpleNamespace(status=403)

        def close(self):
            pass

    monkeypatch.setattr("loop_engine.audit_transport.http.client.HTTPSConnection", FakeConnection)
    with AuditRelay(
        "synthetic",
        deadline=time.monotonic() + 10,
        cancelled=lambda: False,
        forwarding=True,
        peer_authorized=lambda _: True,
    ) as relay:
        client = http.client.HTTPConnection("127.0.0.1", relay.server.server_port, timeout=5)
        try:
            client.request(
                "POST",
                "/responses",
                body=json.dumps({"model": "synthetic", "tools": [], "store": False, "input": []}),
                headers={"Authorization": "Bearer synthetic-invalid-value"},
            )
            with pytest.raises(http.client.RemoteDisconnected):
                client.getresponse()
        finally:
            client.close()
        diagnostic = AuditFailure(relay.stage, relay.failure_reason, relay.http_status).diagnostic
    assert calls == [True]
    assert diagnostic == {
        "stage": "upstream_response" if failure == "status" else "upstream_headers",
        "reason": "policy" if failure == "status" else "timeout",
        "http_status": 403 if failure == "status" else None,
    }
    assert "synthetic-secret" not in json.dumps(diagnostic)


def test_upgrade_source_has_no_password_account_or_auth_reset_operation():
    root = Path(__file__).resolve().parents[2]
    script = upgrade_source(
        *[
            (root / name).read_bytes()
            for name in (
                "scripts/Install-LocusLoopServices.ps1",
                "scripts/Install-LocusLoopAudit.template.ps1",
                "scripts/Upgrade-LocusLoopAudit.template.ps1",
            )
        ]
    ).decode()
    for forbidden in (
        "New-LocalUser",
        "Set-LocalUser",
        "New-Service",
        "Remove-Item",
        "::NewPassword(",
    ):
        assert forbidden not in script
    assert "ChangeServiceConfig(service,0xffffffff,0xffffffff,0xffffffff,binary,null," in script
    assert "IntPtr.Zero,IntPtr.Zero,null,null,null)" in script
    assert script.index("'audit-runtime-upgrade-intent.json'),") < script.index("Stop-Service")
    assert "settings.before-" in script and "profile_runtime" in script


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell/native compiler required")
def test_upgrade_parses_and_native_configuration_call_compiles_without_execution(tmp_path):
    root = Path(__file__).resolve().parents[2]
    raw = upgrade_source(
        *[
            (root / name).read_bytes()
            for name in (
                "scripts/Install-LocusLoopServices.ps1",
                "scripts/Install-LocusLoopAudit.template.ps1",
                "scripts/Upgrade-LocusLoopAudit.template.ps1",
            )
        ]
    )
    script = tmp_path / "upgrade.ps1"
    script.write_bytes(raw)
    inspector = tmp_path / "inspect.ps1"
    inspector.write_text(
        "param($Path)\n$t=$null;$e=$null\n"
        "$ast=[Management.Automation.Language.Parser]::ParseFile($Path,[ref]$t,[ref]$e)\n"
        "if($e.Count){throw 'Upgrade syntax invalid'}\n"
        "$nodes=$ast.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst] "
        "-and $n.GetCommandName() -eq 'Add-Type'},$true)\n"
        "if($nodes.Count -ne 1){throw 'Native helper boundary differs'}\n"
        "Add-Type -TypeDefinition $nodes[0].CommandElements[2].Value\n'compiled-only'\n",
        encoding="utf-8",
    )
    result = ProcessRunner().run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(inspector), str(script)],
        tmp_path,
        timeout=30,
    )
    assert result.returncode == 0 and result.outcome == "exit", result.stderr
    assert "compiled-only" in result.stdout
