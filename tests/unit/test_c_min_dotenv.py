"""Reject native startup dotenv before any content/auth read; synthetic profiles only."""

from pathlib import Path

import pytest

from loop_engine.c_min_runtime import verify_profile
from loop_engine.security import SafetyError
from loop_engine.state_store import StateStore


@pytest.mark.parametrize("artifact", ["file", "directory"])
def test_unassessed_dotenv_rejected_without_opening_it_or_auth(tmp_path, monkeypatch, artifact):
    home = tmp_path / "synthetic-home"
    home.mkdir()
    (home / "config.toml").write_text('cli_auth_credentials_store="keyring"\n')
    dotenv = home / ".env"
    if artifact == "file":
        dotenv.write_text("UNASSESSED=value\n")
    else:
        dotenv.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    state = StateStore(tmp_path / "state.db")
    state.set_metadata(
        "c_min_auth_profile",
        dict.fromkeys(
            (
                "home",
                "backend",
                "config_hash",
                "key_metadata",
                "ciphertext_identity",
                "sid",
                "protection",
            )
        ),
    )
    text, raw = Path.read_text, Path.read_bytes

    def guarded_text(path, *args, **kwargs):
        assert path.name not in {".env", "auth.json", "codex_auth.age"}
        return text(path, *args, **kwargs)

    def guarded_raw(path, *args, **kwargs):
        assert path.name not in {".env", "auth.json", "codex_auth.age"}
        return raw(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_text)
    monkeypatch.setattr(Path, "read_bytes", guarded_raw)
    monkeypatch.setattr(
        "loop_engine.c_min_runtime.key_metadata",
        lambda *_args, **_kwargs: pytest.fail("Credential metadata must not load"),
    )
    with pytest.raises(SafetyError, match="dotenv"):
        verify_profile(state)
    assert dotenv.exists()  # Preserve, never delete/rename/repair the owner's input.
