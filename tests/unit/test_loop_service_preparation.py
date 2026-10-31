"""Preparation boundaries, public artifacts and fixed operations; no real keys."""

import base64
import json
import re
import shutil
import subprocess
import sys
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

import loop_engine.service_worker as worker
from loop_engine.security import SafetyError
from loop_engine.service_bundle import WHEEL_HASHES, BundleError, compatible, extract
from loop_engine.service_identity import (
    ADMINISTRATORS,
    FULL_CONTROL,
    READ_EXECUTE,
    ROLES,
    SYSTEM,
    Deployment,
    protected_bytes,
    require_sealed_acl,
    validate_settings,
)

OPERATOR = "S-1-5-21-11-22-33-1001"
REVIEW = "S-1-5-21-11-22-33-1002"
MERGE = "S-1-5-21-11-22-33-1003"


def settings() -> dict[str, Any]:
    return {
        "protocol": "locus-services-v1",
        "mode": "prepare",
        "project_root": "C:\\Users\\owner\\Locus",
        "runtime_root": "C:\\ProgramData\\LocusLoopServicesV1\\runtimes\\" + "a" * 64,
        "operator_sid": OPERATOR,
        "roles": {
            role: {
                "service": values[0],
                "account": values[1],
                "app_id": values[2],
                "installation_id": values[3],
                "sid": REVIEW if role == "review" else MERGE,
            }
            for role, values in ROLES.items()
        },
    }


def test_fixed_roles_and_preparation_cannot_be_changed_into_activation() -> None:
    value = settings()
    assert validate_settings(value)["mode"] == "prepare"
    for defect in ("active", "same_sid", "app", "path"):
        changed = deepcopy(value)
        if defect == "active":
            changed["mode"] = "active"
        elif defect == "same_sid":
            changed["roles"]["review"]["sid"] = OPERATOR
        elif defect == "app":
            changed["roles"]["merge"]["app_id"] = 999
        else:
            changed["runtime_root"] = "C:\\Users\\owner\\mutable-runtime"
        with pytest.raises(SafetyError):
            validate_settings(changed)


def test_system_owner_and_readonly_role_code_are_required() -> None:
    entries = [
        (SYSTEM, FULL_CONTROL, 0),
        (ADMINISTRATORS, FULL_CONTROL, 0),
        (REVIEW, READ_EXECUTE, 0),
    ]
    require_sealed_acl(SYSTEM, 0x1004, entries)
    with pytest.raises(SafetyError, match="System-owned"):
        require_sealed_acl(OPERATOR, 0x1004, entries)
    with pytest.raises(SafetyError, match="writers"):
        require_sealed_acl(SYSTEM, 0x1004, [*entries[:2], (REVIEW, FULL_CONTROL, 0)])


@pytest.mark.skipif(sys.platform != "win32", reason="Actual Windows file ACLs required")
def test_unprivileged_file_is_not_a_deployment_proof(tmp_path: Path) -> None:
    path = tmp_path / "forged-settings.json"
    path.write_text(json.dumps(settings()))
    with pytest.raises(SafetyError):
        protected_bytes(path)


@pytest.mark.parametrize("name", ["../escape.py", "C:stream", "\\\\server\\share", "site.pth"])
def test_wheel_path_escape_and_import_hooks_are_rejected(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(name, "synthetic")
    target = tmp_path / "target"
    target.mkdir()
    with pytest.raises(BundleError):
        extract(archive, target, wheel=True)
    assert not list(target.iterdir())


def test_wheel_extraction_never_replaces_an_existing_file(tmp_path: Path) -> None:
    archive, target = tmp_path / "fixture.zip", tmp_path / "target"
    target.mkdir()
    (target / "module.py").write_text("existing user work")
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("module.py", "new bytes")
    with pytest.raises(FileExistsError):
        extract(archive, target, wheel=True)
    assert (target / "module.py").read_text() == "existing user work"


def test_wrong_abi_or_architecture_never_selected() -> None:
    assert compatible("package-1.0-cp314-cp314-win_amd64.whl")
    assert not compatible("package-1.0-cp313-cp313-win_amd64.whl")
    assert not compatible("package-1.0-cp314-cp314-win_arm64.whl")
    assert all(len(bytes.fromhex(value)) == 32 for value in WHEEL_HASHES.values())


class PreparedDeployment:
    def __init__(self) -> None:
        self.settings, self.identity = settings(), "a" * 64
        self.claimed: list[str] = []

    def require_role(self, role: str) -> None:
        self.claimed.append(role)

    def clients(self, role: str) -> set[str]:
        return {OPERATOR, REVIEW} if role == "merge" else {OPERATOR}


@pytest.mark.parametrize("operation", ["merge", "publish", "activate", "request", "delete_ref"])
def test_preparation_exposes_no_live_write_or_api_proxy(operation: str) -> None:
    deployment = PreparedDeployment()
    with pytest.raises(SafetyError, match="No publication/merge"):
        worker.dispatch(cast(Deployment, deployment), "merge", OPERATOR, {"operation": operation})
    assert deployment.claimed == ["merge"]


def test_review_identity_cannot_provision_merge_credentials() -> None:
    with pytest.raises(SafetyError, match="Operator-only"):
        worker.dispatch(
            cast(Deployment, PreparedDeployment()),
            "merge",
            REVIEW,
            {"operation": "provision", "key_base64": "synthetic"},
        )


def test_unrelated_sid_cannot_dispatch_even_read_operations() -> None:
    with pytest.raises(SafetyError, match="Unauthorized"):
        worker.dispatch(
            cast(Deployment, PreparedDeployment()), "review", MERGE, {"operation": "health"}
        )


def test_uncertain_credential_import_never_writes_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Vault:
        def get(self, role: str, app_id: int) -> None:
            return None

    calls = []

    def uncertain(*args: Any, **kwargs: Any) -> Any:
        calls.append(True)
        raise OSError("synthetic uncertain credential write")

    monkeypatch.setattr(worker, "WindowsAppVault", Vault)
    monkeypatch.setattr(worker, "provision", uncertain)
    monkeypatch.setattr(worker, "DEPLOYMENT_ROOT", tmp_path)
    state = tmp_path / "state/review"
    state.mkdir(parents=True)
    encoded = base64.b64encode(b"synthetic-not-a-real-key").decode()
    body = {"operation": "provision", "key_base64": encoded}
    with pytest.raises(OSError):
        worker.dispatch(cast(Deployment, PreparedDeployment()), "review", OPERATOR, body)
    with pytest.raises(SafetyError, match="reconciliation"):
        worker.dispatch(cast(Deployment, PreparedDeployment()), "review", OPERATOR, body)
    assert len(calls) == 1
    assert encoded not in (state / "credential-import-intent.json").read_text()


def test_client_does_not_read_or_resend_a_key_after_uncertain_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import loop_engine.service_client as module

    client = module.ServiceClient(cast(Deployment, PreparedDeployment()))

    def health(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"key_present": False, "credential_import_held": True}

    def forbidden() -> Any:
        raise AssertionError("No secret should be read after a held import")

    monkeypatch.setattr(client, "call", health)
    monkeypatch.setattr(module, "WindowsAppVault", forbidden)
    with pytest.raises(SafetyError, match="do not resend"):
        client.provision("review")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell C# compilation required")
def test_native_installer_helpers_compile_without_calling_them() -> None:
    script = Path(__file__).resolve().parents[2] / "scripts/Install-LocusLoopServices.ps1"
    match = re.search(r"Add-Type -TypeDefinition @'\n(.*?)\n'@", script.read_text(), re.DOTALL)
    assert match
    executable = shutil.which("powershell.exe")
    assert executable
    result = subprocess.run(  # noqa: S603 — compiles only, never invokes privileged methods
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$ErrorActionPreference='Stop';Add-Type -TypeDefinition ([Console]::In.ReadToEnd())",
        ],
        input=match[1].encode(),
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell parser required")
def test_installer_parses_without_executing_privileged_actions() -> None:
    script = Path(__file__).resolve().parents[2] / "scripts/Install-LocusLoopServices.ps1"
    command = (
        "$tokens=$null;$syntaxErrors=$null;"
        "$path=[Console]::In.ReadToEnd();"
        "[System.Management.Automation.Language.Parser]::ParseFile($path,"
        "[ref]$tokens,[ref]$syntaxErrors)|Out-Null;"
        "if($syntaxErrors.Count){exit 1}"
    )
    executable = shutil.which("powershell.exe")
    assert executable
    result = subprocess.run(  # noqa: S603 — fixed parser, no script execution
        [executable, "-NoProfile", "-NonInteractive", "-Command", command],
        input=str(script).encode(),
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0
