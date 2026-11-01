"""Synthetic migration and crash recovery; no live project policy is changed."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

import loop_engine.policy_migration as module
from loop_engine.approval import ApprovalQueue
from loop_engine.cli import initialize
from loop_engine.models import Task
from loop_engine.planning import source_snapshot
from loop_engine.policy_migration import PolicyMigration
from loop_engine.security import SafetyError, fingerprint
from loop_engine.state_store import StateStore


def fixture(root: Path) -> tuple[StateStore, dict]:
    state = initialize(root, "Synthetic local-only Goal")
    config = yaml.safe_load((root / ".loop/config.yaml").read_text())
    config["github"]["base"] = "feat/validation"
    (root / ".loop/config.yaml").write_text(yaml.safe_dump(config))
    old = source_snapshot(root)
    state.import_plan(
        old["goal.md"],
        fingerprint(old),
        [Task("TASK-001", "Original task", ["preserve attempts"], "repository", ["backend/**"])],
        metadata={"spec_hash": fingerprint(old), "spec_snapshot": old},
    )
    state.set_metadata("control", "stopped")
    state.set_metadata("run_budget", {"consumed_seconds": 314, "tasks": ["TASK-001"]})
    with state.transaction() as db:
        db.execute("UPDATE tasks SET status='completed', attempts=3 WHERE id='TASK-001'")
    proposed = deepcopy(old)
    proposed["policy"]["github"]["base"] = "main"
    proposed["policy"]["development"]["allowed_paths"] = ["backend/**"]
    return state, proposed


def approve(state: StateStore, proposal: dict) -> None:
    ApprovalQueue(state).resolve(
        [
            {
                "id": proposal["decision_id"],
                "action": "approve",
                "target_hash": proposal["target_hash"],
                "reason": "synthetic operator decision",
            }
        ],
        "unit-test-operator",
    )


def test_exact_approval_and_preserved_task_budget_and_history(tmp_path: Path) -> None:
    state, proposed = fixture(tmp_path)
    migration = PolicyMigration(tmp_path, state)
    old_files = {path.name: path.read_bytes() for path in (tmp_path / ".loop").glob("*.md")}
    config_bytes = (tmp_path / ".loop/config.yaml").read_bytes()
    before_task, budget = state.task("TASK-001").document(), state.metadata("run_budget")
    plan = migration.prepare(proposed)
    with pytest.raises(SafetyError, match="operator approval"):
        migration.apply(plan["id"])
    assert (tmp_path / ".loop/config.yaml").read_bytes() == config_bytes
    approve(state, plan)
    assert migration.apply(plan["id"]) == fingerprint(proposed)
    assert migration.apply(plan["id"]) == fingerprint(proposed)
    assert state.task("TASK-001").document() == before_task
    assert state.metadata("run_budget") == budget
    assert state.metadata("policy_migration_pending") is None
    backup = tmp_path / ".loop/runtime/migrations" / plan["id"] / "old"
    assert (backup / "config.yaml").read_bytes() == config_bytes
    for name in module.SOURCE_FILES:
        assert (backup / name).read_bytes() == old_files[name]
    with state.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM goals").fetchone()[0] == 2


def test_interrupted_replace_resumes_without_resetting_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, proposed = fixture(tmp_path)
    # Make several approved document replacements so the injected interruption
    # occurs after a real partial source migration, not just before the first file.
    proposed["requirements.md"] += "\nOwner-reviewed runtime clarification.\n"
    proposed["architecture.md"] += "\nOwner-reviewed integration clarification.\n"
    migration = PolicyMigration(tmp_path, state)
    plan = migration.prepare(proposed)
    approve(state, plan)
    link = module.os.link
    count = 0

    def interrupt(source: Path, target: Path) -> None:
        nonlocal count
        if target.parent == tmp_path / ".loop":
            count += 1
            if count == 2:
                raise OSError("synthetic interrupted migration")
        link(source, target)

    monkeypatch.setattr(module.os, "link", interrupt)
    with pytest.raises(OSError):
        migration.apply(plan["id"])
    assert state.metadata("policy_migration_pending") == plan["id"]
    monkeypatch.setattr(module.os, "link", link)
    assert migration.apply(plan["id"]) == fingerprint(proposed)
    assert state.task("TASK-001").attempts == 3


def test_concurrent_edit_is_captured_and_restored_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, proposed = fixture(tmp_path)
    proposed["requirements.md"] += "\napproved clarification\n"
    migration = PolicyMigration(tmp_path, state)
    plan = migration.prepare(proposed)
    approve(state, plan)
    rename = module.os.rename
    path = tmp_path / ".loop/requirements.md"

    def racing_edit(source: Path, target: Path) -> None:
        if source == path:
            path.write_text("concurrent user edit")
        rename(source, target)

    monkeypatch.setattr(module.os, "rename", racing_edit)
    with pytest.raises(SafetyError, match="Concurrent user edit"):
        migration.apply(plan["id"])
    assert path.read_text() == "concurrent user edit"
    assert state.task("TASK-001").attempts == 3


def test_supported_legacy_configuration_preserves_original_bytes(tmp_path: Path) -> None:
    state, _ = fixture(tmp_path)
    path = tmp_path / ".loop/config.yaml"
    config = yaml.safe_load(path.read_text())
    config["github"]["base_branch"] = config["github"].pop("base")
    del config["development"]
    del config["qa"]
    del config["approval"]["routine_publication"]
    path.write_text(yaml.safe_dump(config))
    original = path.read_bytes()
    old = source_snapshot(tmp_path)
    state.set_metadata("spec_hash", fingerprint(old))
    state.set_metadata("spec_snapshot", old)
    proposed = deepcopy(old)
    proposed["policy"]["github"]["base"] = "main"
    migration = PolicyMigration(tmp_path, state)
    plan = migration.prepare(proposed)
    approve(state, plan)
    assert migration.apply(plan["id"]) == fingerprint(proposed)
    backup = tmp_path / ".loop/runtime/migrations" / plan["id"] / "old/config.yaml"
    assert backup.read_bytes() == original


def test_interrupted_backup_publication_retries_from_intact_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, proposed = fixture(tmp_path)
    migration = PolicyMigration(tmp_path, state)
    plan = migration.prepare(proposed)
    approve(state, plan)
    link = module.os.link

    def interrupt(source: Path, target: Path) -> None:
        raise OSError("synthetic interruption before backup publication")

    monkeypatch.setattr(module.os, "link", interrupt)
    with pytest.raises(OSError):
        migration.apply(plan["id"])
    monkeypatch.setattr(module.os, "link", link)
    assert migration.apply(plan["id"]) == fingerprint(proposed)


def test_interrupted_new_staging_write_resumes_from_retained_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, proposed = fixture(tmp_path)
    migration = PolicyMigration(tmp_path, state)
    plan = migration.prepare(proposed)
    approve(state, plan)
    fsync, count = module.os.fsync, 0

    def interrupt(descriptor: int) -> None:
        nonlocal count
        count += 1
        if count == 6:  # Five complete backups precede the new config's staging write.
            raise OSError("synthetic interrupted staging write")
        fsync(descriptor)

    monkeypatch.setattr(module.os, "fsync", interrupt)
    with pytest.raises(OSError):
        migration.apply(plan["id"])
    assert state.metadata("policy_migration_pending") == plan["id"]
    monkeypatch.setattr(module.os, "fsync", fsync)
    assert migration.apply(plan["id"]) == fingerprint(proposed)
    assert state.task("TASK-001").attempts == 3


def test_reparse_source_is_rejected_without_touching_external_target(tmp_path: Path) -> None:
    state, proposed = fixture(tmp_path)
    migration = PolicyMigration(tmp_path, state)
    plan = migration.prepare(proposed)
    approve(state, plan)
    path = tmp_path / ".loop/requirements.md"
    held, external = tmp_path / "held-original.txt", tmp_path / "external.txt"
    external.write_text("external user content")
    path.rename(held)
    try:
        path.symlink_to(external)
    except OSError:
        held.rename(path)
        pytest.skip("This Windows account cannot create a synthetic symlink")
    with pytest.raises(SafetyError):
        migration.apply(plan["id"])
    assert external.read_text() == "external user content"


@pytest.mark.parametrize("mutation", ["acceptance", "tests", "attempts", "repository"])
def test_migration_cannot_relax_acceptance_or_required_controls(
    tmp_path: Path, mutation: str
) -> None:
    state, proposed = fixture(tmp_path)
    if mutation == "acceptance":
        proposed["acceptance.md"] += "relaxed"
    elif mutation == "tests":
        proposed["policy"]["verification"] = {"weakened": []}
    elif mutation == "attempts":
        proposed["policy"]["loop"]["max_attempts_per_task"] = 2
    else:
        proposed["policy"]["github"]["repository"] = "other/repository"
    with pytest.raises(SafetyError):
        PolicyMigration(tmp_path, state).prepare(proposed)


def test_unknown_source_change_is_preserved_and_not_overwritten(tmp_path: Path) -> None:
    state, proposed = fixture(tmp_path)
    migration = PolicyMigration(tmp_path, state)
    plan = migration.prepare(proposed)
    approve(state, plan)
    path = tmp_path / ".loop/requirements.md"
    path.write_text("unexpected user work")
    with pytest.raises(SafetyError, match="before backup"):
        migration.apply(plan["id"])
    assert path.read_text() == "unexpected user work"
