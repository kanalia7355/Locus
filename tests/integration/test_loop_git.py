import shutil
import subprocess
from pathlib import Path

import pytest
from test_loop_foundation import task

from loop_engine.cli import initialize
from loop_engine.git_manager import GitManager
from loop_engine.security import SafetyError, fingerprint


def git(root: Path, *args: str) -> str:
    executable = shutil.which("git")
    if not executable:
        pytest.skip("Git is unavailable")
    return subprocess.run(  # noqa: S603 — fixed test fixture Git argv
        [executable, *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",  # noqa: S607
    ).stdout.strip()  # noqa: S603,S607


def test_worktree_scope_and_idempotent_commit_in_isolated_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "--local", "user.name", "Loop Fixture")
    git(tmp_path, "config", "--local", "user.email", "fixture@example.invalid")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.txt").write_text("before\n")
    git(tmp_path, "add", "--", "src/app.txt")
    git(tmp_path, "commit", "-m", "test: initialize fixture")
    state = initialize(tmp_path, "Fixture")
    work = task()
    state.import_plan("Fixture", "hash", [work])
    manager = GitManager(tmp_path, state)
    # Test-owned fixture contains no executable hooks or attributes. This is not live policy proof.
    monkeypatch.setattr(manager, "_safe_configuration", lambda *unused: None)
    directory = manager.prepare(work)
    assert directory != tmp_path and git(tmp_path, "branch", "--show-current") == "main"
    (directory / "src/app.txt").write_text("after\n")
    snapshot = manager.snapshot(work, directory)
    binding = fingerprint(snapshot)
    state.checkpoint(
        work.id, {**state.get_checkpoint(work.id), "snapshot": snapshot, "binding": binding}
    )
    first = manager.finalize(work, directory, binding)
    second = manager.finalize(work, directory, binding)
    assert first == second
    assert manager.snapshot(work, directory) == snapshot
    assert (tmp_path / "src/app.txt").read_text() == "before\n"
    (directory / "outside.txt").write_text("out of scope")
    with pytest.raises(SafetyError):
        manager.snapshot(work, directory)


def test_unborn_repository_is_not_silently_committed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git(tmp_path, "init", "-b", "main")
    state = initialize(tmp_path, "Fixture")
    manager = GitManager(tmp_path, state)
    monkeypatch.setattr(manager, "_safe_configuration", lambda *unused: None)
    with pytest.raises(SafetyError):
        manager.prepare(task())
