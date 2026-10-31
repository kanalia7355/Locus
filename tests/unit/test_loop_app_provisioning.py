"""Masked adoption safety with ephemeral keys and a simulated App API."""

import json
from pathlib import Path
from typing import Any

import pytest

import loop_engine.app_provisioning as adoption
from loop_engine.security import SafetyError


class Vault:
    def __init__(self) -> None:
        self.items: dict[tuple[str, int], bytes] = {}

    def get(self, role: str, app_id: int) -> bytes | None:
        return self.items.get((role, app_id))

    def put(self, role: str, app_id: int, value: bytes) -> None:
        assert (role, app_id) not in self.items
        self.items[role, app_id] = value


class Client:
    calls: list[str] = []

    def __init__(self, *args: Any) -> None:
        self.calls = []

    def call(self, method: str, path: str) -> dict[str, Any]:
        assert method == "GET"
        self.calls.append(path)
        if path.endswith("/protection"):
            return {"required_status_checks": {"strict": True}}
        return {"name": "main"}


def test_public_receipt_only_after_authenticated_read(tmp_path: Path) -> None:
    vault = Vault()
    result = adoption.provision(
        tmp_path, "merge", 123, 456, vault, value=b"synthetic-in-memory-value", make_client=Client
    )  # type: ignore[arg-type]
    path = tmp_path / ".loop/runtime/app-installations/merge-123.json"
    document = json.loads(path.read_text())
    assert document["permissions"]["administration"] == "read"
    assert document["activated"] is False and result["authenticated"] is True
    assert "synthetic-in-memory-value" not in path.read_text()
    assert set(document) == {
        "role",
        "app_id",
        "installation_id",
        "repository_id",
        "repository",
        "permissions",
        "activated",
    }
    # Re-running uses the existing key without interactive input/replacement.
    assert (
        adoption.provision(tmp_path, "merge", 123, 456, vault, make_client=Client)["authenticated"]
        is True
    )  # type: ignore[arg-type]
    assert len(vault.items) == 1


def test_failed_authentication_never_stores_key_or_receipt(tmp_path: Path) -> None:
    class Denied(Client):
        def call(self, method: str, path: str) -> dict[str, Any]:
            raise SafetyError("Installation scope denied")

    vault = Vault()
    with pytest.raises(SafetyError, match="scope denied"):
        adoption.provision(
            tmp_path, "merge", 123, 456, vault, value=b"synthetic-input", make_client=Denied
        )  # type: ignore[arg-type]
    assert not vault.items
    assert not list(tmp_path.rglob("*.json"))


def test_conflicting_metadata_and_key_replacement_are_denied(tmp_path: Path) -> None:
    vault = Vault()
    vault.items["review", 123] = b"existing-synthetic-input"
    with pytest.raises(SafetyError, match="rotation"):
        adoption.provision(
            tmp_path, "review", 123, 456, vault, value=b"replacement", make_client=Client
        )  # type: ignore[arg-type]
    path = tmp_path / ".loop/runtime/app-installations/review-123.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"operator_note":"preserve"}')
    with pytest.raises(SafetyError, match="metadata differs"):
        adoption.provision(tmp_path, "review", 123, 456, vault, make_client=Client)  # type: ignore[arg-type]
    assert path.read_text() == '{"operator_note":"preserve"}'
    assert vault.items["review", 123] == b"existing-synthetic-input"


def test_noninteractive_input_never_calls_password_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adoption.sys.stdin, "isatty", lambda: False)
    calls = []
    with pytest.raises(SafetyError, match="Interactive local terminal"):
        adoption.masked_private_key(lambda prompt: calls.append(prompt) or "not-called")
    assert not calls


def test_mask_failure_never_falls_back_to_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    import warnings

    monkeypatch.setattr(adoption.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(adoption.sys.stderr, "isatty", lambda: True)

    def unavailable(prompt: str) -> str:
        warnings.warn("mask unavailable", adoption.getpass.GetPassWarning, stacklevel=1)
        raise AssertionError("plaintext fallback must not be reached")

    with pytest.raises(SafetyError, match="Masked key input unavailable"):
        adoption.masked_private_key(unavailable)


def test_cli_failure_reports_public_stage_without_raw_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import loop_engine.app_credentials as credentials
    from loop_engine.cli import main
    from loop_engine.github_app import AppConnectionError

    monkeypatch.setattr(credentials, "WindowsAppVault", Vault)

    def denied(*args: Any, **kwargs: Any) -> Any:
        raise AppConnectionError("installation", "http_rejected", 401)

    monkeypatch.setattr(adoption, "provision", denied)
    assert (
        main(
            [
                "--project",
                str(tmp_path),
                "app-provision",
                "review",
                "--app-id",
                "123",
                "--installation-id",
                "456",
            ]
        )
        == 2
    )
    report = json.loads(capsys.readouterr().err)
    assert report == {
        "authenticated": False,
        "stage": "installation",
        "reason": "http_rejected",
        "http_status": 401,
    }
