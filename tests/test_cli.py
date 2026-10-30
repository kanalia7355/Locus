import sys
from pathlib import Path

import pytest
from app import cli
from app.service import Service


def test_interactive_cli_provision_assign_and_fixed_synthetic_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "cli.sqlite3"
    monkeypatch.setattr(cli, "Service", lambda unused: Service(path))
    passwords = iter(["Synthetic-cli-temporary-01!", "Synthetic-cli-temporary-01!"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda unused: next(passwords))
    commands = [
        ["project", "--project", "development"],
        ["provision", "--username", "cli-admin", "--system-admin"],
        ["assign", "--username", "cli-admin", "--role", "project_lead"],
        ["seed-synthetic", "--username", "cli-admin"],
    ]
    for args in commands:
        monkeypatch.setattr(sys, "argv", ["app.cli", *args])
        cli.main()
    output = capsys.readouterr().out
    assert "Synthetic-cli-temporary" not in output
    svc = Service(path)
    try:
        token, user = svc.login("cli-admin", "Synthetic-cli-temporary-01!", "127.0.0.1")
        assert user["must_rotate"]
        actor = svc.authenticate(token, allow_rotation=True)
        changed = svc.rotate(actor, "Synthetic-cli-temporary-01!", "Synthetic-cli-permanent-01!")
        actor = svc.authenticate(changed)
        docs = svc.documents(actor, "development")
        assert len(docs) == 1
        assert docs[0]["status"] == "ready"
        assert "合成サンプル" in svc.chunks(actor, docs[0]["id"])[0]["text"]
    finally:
        svc.close()


def test_cli_rejects_password_mismatch_before_account_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "cli.sqlite3"
    monkeypatch.setattr(cli, "Service", lambda unused: Service(path))
    passwords = iter(["Synthetic-cli-temporary-01!", "mismatch"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda unused: next(passwords))
    monkeypatch.setattr(sys, "argv", ["app.cli", "provision", "--username", "cli-admin"])
    with pytest.raises(SystemExit):
        cli.main()
    svc = Service(path)
    try:
        with svc.db() as db:
            assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    finally:
        svc.close()
