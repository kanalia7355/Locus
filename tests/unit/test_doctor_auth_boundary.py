"""Doctor must not load operator authentication to diagnose a missing boundary."""

from types import SimpleNamespace

import pytest
import yaml

from loop_engine.cli import doctor, initialize
from loop_engine.security import SafetyError


@pytest.mark.parametrize("error", [SafetyError("stale"), FileNotFoundError("missing")])
def test_unverified_doctor_never_launches_authentication(tmp_path, monkeypatch, error):
    initialize(tmp_path)
    calls = []
    monkeypatch.setattr("loop_engine.cli.shutil.which", lambda name: name)
    monkeypatch.setattr("loop_engine.codex_runner.codex_binary", lambda root: "pinned-codex")

    def version(argv, **kwargs):
        assert argv[1:] == ["--version"]
        return SimpleNamespace(returncode=0, stdout="synthetic version")

    def run(self, argv, *args, **kwargs):
        calls.append(argv)
        assert argv[0] != "pinned-codex", "unapproved operator auth access"
        return SimpleNamespace(outcome="exit", returncode=0, stdout="synthetic head")

    def rejected(root):
        raise error

    monkeypatch.setattr("loop_engine.cli.subprocess.run", version)
    monkeypatch.setattr("loop_engine.process.ProcessRunner.run", run)
    monkeypatch.setattr("loop_engine.runtime_diagnostics.require_receipt", rejected)
    result = doctor(tmp_path)
    assert result["codex"]["authenticated"] is None
    assert result["codex"]["authentication_probe"] == "not_run_execution_boundary_unverified"
    assert result["ready_for_live_execution"] is False
    assert not any("login" in argv for argv in calls)


@pytest.mark.parametrize("authenticated", [False, True])
def test_verified_boundary_still_requires_existing_authentication_check(
    tmp_path, monkeypatch, authenticated
):
    initialize(tmp_path)
    config_path = tmp_path / ".loop/config.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["security"]["allow_model_execution"] = True
    config["security"]["sandbox_executor"] = "proposal-docker"
    config_path.write_text(yaml.safe_dump(config))
    calls = []
    monkeypatch.setattr("loop_engine.cli.shutil.which", lambda name: name)
    monkeypatch.setattr("loop_engine.codex_runner.codex_binary", lambda root: "pinned-codex")
    monkeypatch.setattr(
        "loop_engine.cli.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="synthetic version"),
    )

    def run(self, argv, *args, **kwargs):
        calls.append(argv)
        code = 0 if argv[0] != "pinned-codex" or authenticated else 1
        return SimpleNamespace(outcome="exit", returncode=code, stdout="synthetic head")

    monkeypatch.setattr("loop_engine.process.ProcessRunner.run", run)
    monkeypatch.setattr("loop_engine.runtime_diagnostics.require_receipt", lambda root: None)
    monkeypatch.setattr(
        "loop_engine.runtime_diagnostics.boundary_for",
        lambda root: SimpleNamespace(docker=SimpleNamespace(audit_evidence=lambda root: True)),
    )
    result = doctor(tmp_path)
    assert ["pinned-codex", "login", "status"] in calls
    assert result["codex"]["authenticated"] is authenticated
    assert result["ready_for_live_execution"] is authenticated
