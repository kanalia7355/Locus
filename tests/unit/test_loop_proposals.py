from pathlib import Path

import pytest
from test_loop_foundation import task

from loop_engine.proposals import apply_proposal
from loop_engine.security import SafetyError


def proposal(names: list[str]) -> dict:
    return {
        "result": {
            "task_id": "TASK-001",
            "status": "implemented",
            "summary": "Add bounded source",
            "files_changed": names,
            "tests_added": [],
            "issues": [],
            "approval_requests": [],
        },
        "edits": [{"path": name, "old": None, "new": "synthetic\n"} for name in names],
    }


@pytest.mark.parametrize(
    "name",
    [
        "../outside.txt",
        "src/../../outside.txt",
        ".git/config",
        "scripts/verify.py",
        "src/.codex/config.toml",
        "src/AGENTS.md",
        "src/.gitattributes",
        "src/package-lock.json",
    ],
)
def test_invalid_edit_set_does_not_apply_earlier_valid_edit(tmp_path: Path, name: str) -> None:
    work = task()
    with pytest.raises((SafetyError, ValueError)):
        apply_proposal(work, tmp_path, proposal(["src/valid.txt", name]))
    assert not (tmp_path / "src/valid.txt").exists()


def test_ambiguous_replacement_and_new_file_overwrite_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    path = tmp_path / "src/existing.txt"
    path.write_text("repeat repeat")
    value = proposal(["src/existing.txt"])
    with pytest.raises(SafetyError):
        apply_proposal(task(), tmp_path, value)
    value["edits"][0].update(old="repeat", new="replacement")
    with pytest.raises(SafetyError):
        apply_proposal(task(), tmp_path, value)
    assert path.read_text() == "repeat repeat"


def test_exact_replacement_and_new_test_creation(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    path = tmp_path / "src/existing.txt"
    path.write_text("before\n")
    value = proposal(["src/existing.txt", "tests/test_new.py"])
    value["edits"][0].update(old="before", new="after")
    assert apply_proposal(task(), tmp_path, value)["status"] == "implemented"
    assert path.read_text() == "after\n"
    assert (tmp_path / "tests/test_new.py").exists()


def test_source_and_result_mismatch_never_writes(tmp_path: Path) -> None:
    value = proposal(["src/new.txt"])
    value["result"]["files_changed"] = []
    with pytest.raises(SafetyError):
        apply_proposal(task(), tmp_path, value)
    assert not (tmp_path / "src/new.txt").exists()


def test_quoted_credential_key_is_rejected_before_writing(tmp_path: Path) -> None:
    value = proposal(["src/data.json"])
    value["edits"][0]["new"] = '{"password": "' + "untrusted-literal-value" + '"}'
    with pytest.raises(SafetyError):
        apply_proposal(task(), tmp_path, value)
    assert not (tmp_path / "src/data.json").exists()
