from pathlib import Path

import pytest
from test_loop_git import git

from loop_engine.cli import initialize
from loop_engine.git_manager import GitManager
from loop_engine.security import SafetyError


def test_standard_lfs_is_allowed_only_while_dormant(tmp_path: Path) -> None:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Fixture")
    git(tmp_path, "config", "user.email", "fixture@example.invalid")
    for key, value in {
        "clean": "git-lfs clean -- %f",
        "smudge": "git-lfs smudge -- %f",
        "process": "git-lfs filter-process",
        "required": "true",
    }.items():
        git(tmp_path, "config", "filter.lfs." + key, value)
    (tmp_path / "example.txt").write_text("synthetic")
    git(tmp_path, "add", "example.txt")
    git(tmp_path, "commit", "-m", "test: initialize source")
    manager = GitManager(tmp_path, initialize(tmp_path, "Fixture"))
    manager._safe_configuration()
    (tmp_path / ".gitattributes").write_text("*.txt filter=lfs\n")
    with pytest.raises(SafetyError):
        manager._safe_configuration()


def test_custom_filter_is_never_treated_as_standard_lfs(tmp_path: Path) -> None:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "filter.arbitrary.clean", "unexpected executable")
    with pytest.raises(SafetyError):
        GitManager(tmp_path, initialize(tmp_path, "Fixture"))._safe_configuration()
