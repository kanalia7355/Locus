"""Legacy notification commands are executable hooks, not model tools."""

from types import SimpleNamespace

import pytest

from loop_engine.security import SafetyError
from loop_engine.toolless_boundary import ToollessBoundary, configured_hooks


@pytest.mark.parametrize("value", [["synthetic-callback"], "unknown", True, False, {}, 0])
def test_nonempty_or_invalid_notify_is_not_an_implicit_callback_permission(value):
    assert configured_hooks({"notify": value})
    assert configured_hooks({"profiles": {"synthetic": {"notify": value}}})


@pytest.mark.parametrize("value", [None, []])
def test_no_notification_command_keeps_original_empty_hook_policy(value):
    assert not configured_hooks({"notify": value, "features": {"hooks": True}})
    assert configured_hooks({"hooks": {"SessionStart": ["synthetic-callback"]}})


def test_binding_rejects_notify_without_launching_or_rewriting_it(tmp_path, monkeypatch):
    from pathlib import Path

    home = tmp_path / "synthetic-home"
    home.mkdir()
    config = home / "config.toml"
    text = 'notify=["synthetic-callback"]\n'
    config.write_text(text)
    catalog = tmp_path / "catalog.json"
    catalog.write_text("{}")
    binary = tmp_path / "synthetic-cli"
    binary.write_bytes(b"SYNTHETIC_NOT_EXECUTABLE")
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr("loop_engine.toolless_boundary.codex_binary", lambda root: str(binary))
    # Exclude machine policy and ancestor configuration outside this fixture.
    # No installed user profile/AGENTS/config is evidence for an isolated test.
    original_exists = Path.exists
    monkeypatch.setattr(
        Path,
        "exists",
        lambda path: (
            False if path == Path("C:/ProgramData/OpenAI/Codex") else original_exists(path)
        ),
    )
    monkeypatch.setattr(Path, "is_file", lambda path: path in {config, catalog})
    monkeypatch.setattr(Path, "is_dir", lambda path: False)
    monkeypatch.setattr(
        "loop_engine.process.ProcessRunner.run", lambda *a, **k: pytest.fail("callback/CLI launch")
    )
    boundary = object.__new__(ToollessBoundary)
    boundary.root, boundary.catalog = tmp_path, catalog
    boundary.native = SimpleNamespace(settings=lambda *args: [])
    with pytest.raises(SafetyError, match="lifecycle hooks require assessment"):
        boundary._binding(tmp_path)
    assert config.read_text() == text
