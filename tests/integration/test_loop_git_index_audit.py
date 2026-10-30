from pathlib import Path

import pytest
from test_loop_foundation import task
from test_loop_git import git

from loop_engine.cli import initialize
from loop_engine.git_manager import GitManager
from loop_engine.security import SafetyError


def test_hidden_staged_out_of_scope_content_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "--local", "user.name", "Fixture")
    git(tmp_path, "config", "--local", "user.email", "fixture@example.invalid")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.txt").write_text("before\n")
    (tmp_path / "outside.txt").write_text("original\n")
    git(tmp_path, "add", "--", "src/app.txt", "outside.txt")
    git(tmp_path, "commit", "-m", "test: baseline")
    state = initialize(tmp_path, "Fixture")
    work = task()
    state.import_plan("Fixture", "hash", [work])
    manager = GitManager(tmp_path, state)
    monkeypatch.setattr(manager, "_safe_configuration", lambda *unused: None)
    directory = manager.prepare(work)
    (directory / "outside.txt").write_text("hidden staged payload\n")
    git(directory, "add", "--", "outside.txt")
    (directory / "outside.txt").write_text("original\n")
    (directory / "src/app.txt").write_text("allowed change\n")
    with pytest.raises(SafetyError):
        manager.snapshot(work, directory)
