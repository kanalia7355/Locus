"""Synthetic policy/installer/owner UI checks; no accounts, login or service writes."""

import json
import socket
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from loop_engine.audit_bundle import installer_source
from loop_engine.audit_enrollment import DEVICE_URL, Enrollment
from loop_engine.audit_identity import AUDIT_ROOT, validate_settings
from loop_engine.audit_profile import profile_text
from loop_engine.audit_transport import AuditRelay, validate_inference
from loop_engine.process import ProcessResult, ProcessRunner
from loop_engine.security import SafetyError

ROOT = Path(__file__).resolve().parents[2]


def settings():
    return {
        "protocol": "locus-audit-service-v1",
        "mode": "prepare",
        "project_root": "C:/Users/synthetic/Locus",
        "runtime_root": str(AUDIT_ROOT / "runtimes" / ("a" * 64)),
        "operator_sid": "S-1-5-21-1-2-3-1001",
        "review_sid": "S-1-5-21-1-2-3-1002",
        "merge_sid": "S-1-5-21-1-2-3-1003",
        "audit_sid": "S-1-5-21-1-2-3-1004",
        "app_manifest": "b" * 64,
        "model": "synthetic-model",
        "reasoning_effort": None,
    }


def test_closed_separate_settings_and_fixed_profile():
    value = settings()
    assert validate_settings(value) == value
    profile = profile_text(Path(value["runtime_root"]), value["model"])
    assert 'cli_auth_credentials_store="keyring"' in profile
    assert "secret_auth_storage=true" in profile
    assert "shell_tool=false" in profile
    assert "responses_websockets=false" in profile
    assert "blocked-logs" in profile
    for field, changed in (
        ("audit_sid", value["operator_sid"]),
        ("mode", "active"),
        ("runtime_root", "C:/outside/" + "a" * 64),
        ("model", "model; command"),
        ("app_manifest", "../x"),
    ):
        with pytest.raises(SafetyError):
            validate_settings({**value, field: changed})
    with pytest.raises(SafetyError):
        validate_settings({**value, "provider": "unapproved"})


def test_installer_deterministic_line_endings_and_separate_scope():
    original = (ROOT / "scripts/Install-LocusLoopServices.ps1").read_bytes()
    template = (ROOT / "scripts/Install-LocusLoopAudit.template.ps1").read_bytes()
    result = installer_source(original, template)
    assert result == installer_source(
        original.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"), template
    )
    assert b"__NATIVE_HELPER__" not in result and b"__READONLY_HELPERS__" not in result
    assert b"input.Length>536870912" in result
    assert b"0x20005;;;" in result
    assert b"New-LocalUser -Name 'locus_loop_audit'" in result
    assert b"Remove-LocalUser" not in result and b"Set-LocalUser" not in result
    assert b"Set-Content" not in result and b"Remove-Item" not in result
    assert b"PSCredential]::new('.\\locus_loop_audit',$secure)" in result
    with pytest.raises((SafetyError, IndexError)):
        installer_source(original.replace(b"input.Length>64000000", b"input.Length>1"), template)


def test_inference_empty_or_missing_tools_is_zero_capability():
    value = {"model": "synthetic", "input": [], "tools": [], "store": False}
    assert validate_inference(json.dumps(value).encode(), "synthetic") == value
    value.pop("tools")
    assert validate_inference(json.dumps(value).encode(), "synthetic") == value
    for field, changed in (
        ("tools", [{"type": "shell"}]),
        ("store", True),
        ("model", "different"),
        ("previous_response_id", "old"),
    ):
        with pytest.raises(SafetyError):
            validate_inference(json.dumps({**value, field: changed}).encode(), "synthetic")
    with pytest.raises(SafetyError):
        validate_inference(b'{"model":"synthetic","model":"synthetic"}', "synthetic")


def test_rejecting_relay_verifies_peer_and_never_forwards():
    import http.client

    with AuditRelay(
        "synthetic",
        deadline=time.monotonic() + 5,
        cancelled=lambda: False,
        peer_authorized=lambda _: True,
    ) as relay:
        client = http.client.HTTPConnection("127.0.0.1", relay.server.server_port, timeout=2)
        try:
            client.request(
                "POST",
                "/responses",
                json.dumps({"model": "synthetic", "input": [], "store": False}),
            )
            response = client.getresponse()
            assert response.status == 400
            assert relay.accepted and relay.observed.is_set()
            assert relay.connection is None
        finally:
            client.close()
    with AuditRelay("synthetic", deadline=time.monotonic() + 5, cancelled=lambda: False) as relay:
        client = http.client.HTTPConnection("127.0.0.1", relay.server.server_port, timeout=2)
        try:
            with pytest.raises((OSError, http.client.HTTPException)):
                client.request("POST", "/responses", b"{}")
                client.getresponse()
            assert not relay.used and not relay.accepted
        finally:
            client.close()


class LoginProcess:
    def __init__(self, existing="Not logged in"):
        self.existing = existing
        self.calls = []
        self.completed = threading.Event()
        self.code_sent = threading.Event()

    def run(self, argv, cwd, **options):
        self.calls.append(argv)
        if "--device-auth" not in argv:
            if len(self.calls) == 1:
                return ProcessResult(
                    "exit",
                    0 if self.existing == "Logged in using ChatGPT" else 1,
                    stderr=self.existing,
                )
            return ProcessResult("exit", 0, stderr="Logged in using ChatGPT")
        options["output_observer"](
            0, ("untrusted ignored text\n" + DEVICE_URL + "\nABCD-EFGH\n").encode()
        )
        self.code_sent.set()
        assert self.completed.wait(3)
        return ProcessResult("exit", 0)


class FakeAuthentication:
    def __init__(self, phase="pristine"):
        self.phase = phase

    def check(self):
        return self.phase

    def begin(self, operation):
        self.phase = "active_" + operation

    def finish(self, phase):
        self.phase = phase


def test_private_enrollment_preserves_existing_login_and_bounds_status(tmp_path):
    process = LoginProcess(existing="Logged in using ChatGPT")
    manager = Enrollment(
        tmp_path / "client.exe",
        tmp_path,
        preflight=lambda: None,
        stopped=lambda: False,
        process=process,
        authentication=FakeAuthentication("enrolled"),
    )
    manager.start(time.monotonic() + 10)
    manager.thread.join(3)
    assert manager.poll() == {"status": "authenticated", "authenticated": True, "activated": False}
    assert len(process.calls) == 1 and "--device-auth" not in process.calls[0]
    with pytest.raises(SafetyError):
        manager.start(time.monotonic() + 10)


def test_private_enrollment_only_exposes_allowlisted_code_while_waiting(tmp_path):
    process = LoginProcess()
    manager = Enrollment(
        tmp_path / "client.exe",
        tmp_path,
        preflight=lambda: None,
        stopped=lambda: False,
        process=process,
        authentication=FakeAuthentication(),
    )
    manager.start(time.monotonic() + 10)
    assert process.code_sent.wait(3)
    answer = manager.poll()
    assert answer == {
        "status": "waiting_for_owner",
        "authenticated": False,
        "activated": False,
        "verification_uri": DEVICE_URL,
        "user_code": "ABCD-EFGH",
    }
    assert "untrusted" not in json.dumps(answer)
    process.completed.set()
    manager.thread.join(3)
    assert manager.poll()["authenticated"] is True
    assert "user_code" not in manager.poll()
    assert not list(tmp_path.iterdir())


def test_uncertain_existing_auth_is_not_cleared(tmp_path):
    process = LoginProcess(existing="Error checking login status")
    manager = Enrollment(
        tmp_path / "client.exe",
        tmp_path,
        preflight=lambda: None,
        stopped=lambda: False,
        process=process,
        authentication=FakeAuthentication("enrolled"),
    )
    manager.start(time.monotonic() + 10)
    manager.thread.join(3)
    assert manager.poll()["status"] == "held"
    assert len(process.calls) == 1


def test_owner_ui_cannot_run_in_captured_output(monkeypatch):
    import loop_engine.audit_client as module

    monkeypatch.setattr(
        module,
        "sys",
        SimpleNamespace(
            stdin=SimpleNamespace(isatty=lambda: False),
            stdout=SimpleNamespace(isatty=lambda: False),
        ),
    )
    with pytest.raises(SafetyError, match="private interactive"):
        module.enroll_owner()


def test_process_observer_streams_short_output_before_child_exits(tmp_path):
    observed = threading.Event()
    result = ProcessRunner().run(
        [sys.executable, "-c", "import time;print('synthetic-ui-ready',flush=True);time.sleep(30)"],
        tmp_path,
        timeout=10,
        cancelled=observed.is_set,
        output_observer=lambda channel, block: observed.set() if channel == 0 else None,
    )
    assert observed.is_set()
    assert result.outcome == "cancelled" and result.elapsed < 5


@pytest.mark.skipif(sys.platform != "win32", reason="Windows active-process job limit required")
def test_single_process_job_denies_tool_subprocesses(tmp_path):
    marker = tmp_path / "child-must-not-run.txt"
    script = (
        "import subprocess,sys;\n"
        "try:\n"
        " subprocess.run([sys.executable,'-c',"
        "\"from pathlib import Path;Path('child-must-not-run.txt')"
        ".write_text('bad')\"],check=True)\n"
        "except OSError:\n print('child-denied')\n"
    )
    result = ProcessRunner().run(
        [getattr(sys, "_base_executable", sys.executable), "-c", script],
        tmp_path,
        timeout=10,
        active_process_limit=1,
    )
    assert result.outcome == "exit" and result.returncode == 0
    assert "child-denied" in result.stdout and not marker.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows kernel TCP owner API required")
def test_kernel_tcp_peer_accepts_same_sid_and_denies_other_sid():
    from loop_engine.windows_pipe import Native
    from loop_engine.windows_tcp_peer import require_loopback_peer

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    done = threading.Event()

    def connect():
        with socket.create_connection(listener.getsockname()):
            done.wait(5)

    thread = threading.Thread(target=connect)
    thread.start()
    connection, _ = listener.accept()
    try:
        assert require_loopback_peer(connection, Native().current_sid())
        with pytest.raises(SafetyError, match="another account"):
            require_loopback_peer(connection, "S-1-5-21-1-2-3-1007")
    finally:
        done.set()
        connection.close()
        listener.close()
        thread.join(5)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell parser/compiler required")
def test_generated_admin_script_parses_and_native_helper_compiles_without_mutation(tmp_path):
    source = installer_source(
        (ROOT / "scripts/Install-LocusLoopServices.ps1").read_bytes(),
        (ROOT / "scripts/Install-LocusLoopAudit.template.ps1").read_bytes(),
    )
    path = tmp_path / "generated.ps1"
    path.write_bytes(source)
    inspector = tmp_path / "inspect.ps1"
    inspector.write_text(
        "param([string]$Source)\n$ErrorActionPreference='Stop'\n"
        "$tokens=$null;$errors=$null\n"
        "$ast=[Management.Automation.Language.Parser]::ParseFile($Source,[ref]$tokens,[ref]$errors)\n"
        "if($errors.Count){throw 'Generated installer syntax failed'}\n"
        "$nodes=$ast.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst] "
        "-and $n.GetCommandName() -eq 'Add-Type'},$true)\n"
        "if($nodes.Count -ne 1){throw 'Unexpected native helper count'}\n"
        "Add-Type -TypeDefinition $nodes[0].CommandElements[2].Value\n"
        "Write-Output 'parsed-and-compiled-no-mutation'\n",
        encoding="utf-8",
    )
    result = ProcessRunner().run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(inspector), str(path)],
        tmp_path,
        timeout=30,
        output_limit=8192,
    )
    assert result.outcome == "exit" and result.returncode == 0, result.stderr
    assert "parsed-and-compiled-no-mutation" in result.stdout
