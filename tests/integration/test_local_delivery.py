"""Real Git + local bare transport; GitHub URL identity alone is mocked."""

from dataclasses import replace
from pathlib import Path
from time import time
from typing import Any
from unittest.mock import Mock

import pytest
import yaml
from test_loop_foundation import task
from test_loop_git import git

from loop_engine.cli import initialize
from loop_engine.config import default
from loop_engine.controller import Controller
from loop_engine.development import LocalSnapshot
from loop_engine.git_manager import GitManager
from loop_engine.local_delivery import LocalDelivery, validate_policy
from loop_engine.planning import source_snapshot
from loop_engine.security import SafetyError, fingerprint


def fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, ...]:
    root = tmp_path / "project"
    root.mkdir()
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", str(remote))
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Loop Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    (root / ".gitignore").write_text(".loop/\n")
    (root / "src").mkdir()
    (root / "src/app.txt").write_text("before\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "test: initialize fixture")
    git(root, "branch", "loop/development")
    git(root, "remote", "add", "origin", str(remote))
    state = initialize(root, "Fixture")
    work = task()
    state.import_plan("Fixture", "hash", [work, replace(task(2), dependencies=[work.id])])
    manager = GitManager(root, state, "refs/heads/loop/development")
    original = manager._git

    def transport(args: list[str], *a: Any, **kw: Any) -> str:
        if args[:2] == ["remote", "get-url"]:
            return "https://github.com/fixture/repository.git"
        return original(args, *a, **kw)

    monkeypatch.setattr(manager, "_git", transport)
    policy = {
        **default()["github"],
        "enabled": True,
        "base": "loop/development",
        "repository": "fixture/repository",
        "delivery": "local_commit_push",
    }
    publisher = LocalDelivery(root, state, manager, policy)
    directory = manager.prepare(work)
    (directory / "src/app.txt").write_text("after\n")
    snapshot = manager.snapshot(work, directory)
    state.checkpoint(
        work.id,
        {
            **state.get_checkpoint(work.id),
            "verified": True,
            "snapshot": snapshot,
            "binding": fingerprint(snapshot),
            "verification": {"passed": True},
        },
    )
    return root, remote, state, work, manager, publisher


@pytest.mark.parametrize(
    "interruption", [None, "add", "commit", "update-ref", "push", "integrated_head", "pushed_head"]
)
def test_commit_integrate_push_reconciles_without_duplicate_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interruption: str | None
) -> None:
    root, remote, state, work, manager, publisher = fixture(tmp_path, monkeypatch)
    baseline = git(root, "rev-parse", "main")
    original_git, original_checkpoint = manager._git, state.checkpoint
    fired = False

    def fail_git(args: list[str], *a: Any, **kw: Any) -> str:
        nonlocal fired
        result = original_git(args, *a, **kw)
        if args[0] == interruption and not fired:
            fired = True
            raise RuntimeError("simulated controller crash after Git mutation")
        return result

    def fail_checkpoint(identity: str, value: dict[str, Any]) -> None:
        nonlocal fired
        original_checkpoint(identity, value)
        if (
            interruption in {"integrated_head", "pushed_head"}
            and value.get(interruption)
            and not fired
        ):
            fired = True
            raise RuntimeError("simulated controller crash after checkpoint")

    monkeypatch.setattr(manager, "_git", fail_git)
    monkeypatch.setattr(state, "checkpoint", fail_checkpoint)
    if interruption:
        with pytest.raises(RuntimeError):
            publisher.deliver(work, state.get_checkpoint(work.id), cancelled=lambda: False)
    first = publisher.deliver(work, state.get_checkpoint(work.id), cancelled=lambda: False)
    assert publisher.deliver(work, state.get_checkpoint(work.id), cancelled=lambda: False) == first
    head = first["pushed_head"]
    assert git(remote, "rev-parse", "refs/heads/loop/development") == head
    assert git(root, "rev-parse", "loop/development") == head
    assert git(root, "rev-parse", "main") == baseline
    assert git(root, "rev-list", "--count", f"{baseline}..{head}") == "1"
    assert git(root, "log", "-1", "--format=%s", head) == "feat: implement TASK-001"
    assert git(root, "branch", "--show-current") == "main"
    if interruption is None:
        # Migration of an old PR-only completed task: its commit already exists
        # in the approved base, but it has no local integration receipt yet.
        checkpoint = state.get_checkpoint(work.id)
        checkpoint.pop("integrated_head")
        state.checkpoint(work.id, checkpoint)
        with state.transaction() as db:
            db.execute("UPDATE tasks SET status='completed', attempts=3 WHERE id=?", (work.id,))
    next_task = replace(task(2), dependencies=[work.id])
    directory = manager.prepare(next_task)
    assert git(directory, "rev-parse", "HEAD") == head
    assert (directory / "src/app.txt").read_text() == "after\n"


def test_historical_completed_commit_outside_base_cannot_satisfy_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, remote, state, work, manager, publisher = fixture(tmp_path, monkeypatch)
    checkpoint = state.get_checkpoint(work.id)
    manager.finalize(work, Path(checkpoint["workspace"]), checkpoint["binding"])
    with state.transaction() as db:
        db.execute("UPDATE tasks SET status='completed', attempts=3 WHERE id=?", (work.id,))
    with pytest.raises(SafetyError):
        manager.prepare(replace(task(2), dependencies=[work.id]))
    assert not (root / ".loop/runtime/worktrees/TASK-002").exists()


@pytest.mark.parametrize("failure", ["qa", "source", "remote", "push"])
def test_unsafe_or_failed_delivery_never_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    root, remote, state, work, manager, publisher = fixture(tmp_path, monkeypatch)
    checkpoint = state.get_checkpoint(work.id)
    if failure == "qa":
        state.checkpoint(work.id, {**checkpoint, "verification": {"passed": False}})
    elif failure == "source":
        (Path(checkpoint["workspace"]) / "src/app.txt").write_text("unverified\n")
    elif failure == "remote":
        git(root, "push", "origin", "main:refs/heads/loop/development")
        # An unexpected published OID (different from the verified task base).
        git(root, "commit", "--allow-empty", "-m", "test: external change")
        git(root, "push", "origin", "main:refs/heads/loop/development")
    else:
        original = manager._git

        def reject(args: list[str], *a: Any, **kw: Any) -> str:
            if args[0] == "push":
                raise SafetyError("simulated transport rejection")
            return original(args, *a, **kw)

        monkeypatch.setattr(manager, "_git", reject)
    with pytest.raises(SafetyError):
        publisher.deliver(work, state.get_checkpoint(work.id), cancelled=lambda: False)
    assert not state.get_checkpoint(work.id).get("pushed_head")
    if failure in {"qa", "source", "remote"}:
        assert not state.get_checkpoint(work.id).get("committed_head")


def test_policy_cannot_target_main_or_enable_merge() -> None:
    policy = {**default()["github"], "enabled": True, "repository": "fixture/repository"}
    with pytest.raises(SafetyError):
        validate_policy(policy)
    with pytest.raises(SafetyError):
        validate_policy({**policy, "base": "loop/development", "auto_merge": "safe"})


def test_unapproved_fetch_url_is_rejected_before_external_lookup(tmp_path: Path) -> None:
    manager = Mock()
    manager._git.side_effect = [
        "https://github.com/fixture/repository.git",
        "https://unapproved.invalid/repository.git",
    ]
    policy = {
        **default()["github"],
        "enabled": True,
        "base": "loop/development",
        "repository": "fixture/repository",
    }
    publisher = LocalDelivery(tmp_path, Mock(), manager, policy)
    with pytest.raises(SafetyError, match="destination"):
        publisher._remote_head(lambda: False)
    assert manager._git.call_count == 2  # Neither ls-remote nor Push was invoked.


def test_commit_subprocess_honors_controller_cancellation(tmp_path: Path) -> None:
    manager = GitManager(tmp_path, Mock())
    manager.operation_cancelled = lambda: True
    manager.process = Mock()
    with pytest.raises(SafetyError, match="cancelled"):
        manager._git(["commit", "-m", "feat: must not run"])
    manager.process.run.assert_not_called()


@pytest.mark.parametrize("crash_after_push", [False, True])
def test_controller_retries_local_qa_then_pushes_two_dependent_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_after_push: bool
) -> None:
    from test_loop_controller import ReviewFixture, VerifyFixture, WorkerFixture

    root, remote, state, work, manager, publisher = fixture(tmp_path, monkeypatch)
    config = default()
    config["github"] = publisher.policy
    config["development"]["enabled"] = False
    (root / ".loop/config.yaml").write_text(yaml.safe_dump(config))
    state.set_metadata("spec_hash", fingerprint(source_snapshot(root)))
    for item in state.tasks():
        state.transition(item.id, "planned", "ready", version=item.version)

    class Worker(WorkerFixture):
        def execute(self, task: Any, context: Any, workspace: Path, **kw: Any) -> dict[str, Any]:
            if task.id == "TASK-002":
                assert (workspace / "src/app.txt").read_text() == "TASK-001\n"
                assert state.task("TASK-001").status == "completed"
                assert git(remote, "rev-parse", publisher.ref) == git(
                    workspace, "rev-parse", "HEAD"
                )
            (workspace / "src/app.txt").write_text(
                "bad\n" if task.id == work.id and task.attempts == 1 else task.id + "\n"
            )
            return super().execute(task, context, workspace, **kw)

    class Verify(VerifyFixture):
        def run(self, profile: str, workspace: Path, *a: Any, **kw: Any) -> dict[str, Any]:
            self.fail = profile if (workspace / "src/app.txt").read_text() == "bad\n" else ""
            return super().run(profile, workspace, *a, **kw)

    assessed: list[str | None] = []

    class Development:
        def cycle(self, *, expected_merge: str | None, **kw: Any) -> str:
            assessed.append(expected_merge)
            snapshots = LocalSnapshot(root, manager, "fixture/repository", "loop/development")
            snapshots.configure(time() + 30, lambda: False)
            directory, snapshot = snapshots.refresh(expected_merge)
            assert snapshots.stable(directory, snapshot["head"])
            if expected_merge:
                assert git(remote, "rev-parse", publisher.ref) == expected_merge
            return "continue"

    controller = Controller(
        root, state, Worker(), Verify(), ReviewFixture(), manager, publisher, Development()
    )
    original_delivery = publisher.deliver
    fired = False

    def crash_before_completion(task: Any, checkpoint: Any, **kw: Any) -> dict[str, Any]:
        nonlocal fired
        result = original_delivery(task, checkpoint, **kw)
        if crash_after_push and not fired:
            fired = True
            raise RuntimeError("simulated crash after Push, before task completion")
        return result

    monkeypatch.setattr(publisher, "deliver", crash_before_completion)
    if crash_after_push:
        with pytest.raises(RuntimeError):
            controller.run(duration_seconds=180)
        assert state.task(work.id).status == "awaiting_approval"
        assert state.task("TASK-002").attempts == 0
    assert controller.run(duration_seconds=180) == "idle"
    assert all(item.status == "completed" for item in state.tasks())
    assert state.task(work.id).attempts == 2
    assert len([head for head in assessed if head]) == 2
    assert git(root, "rev-list", "--count", "main..loop/development") == "2"
    assert git(remote, "rev-parse", publisher.ref) == git(root, "rev-parse", publisher.ref)
    assert controller.run(resume=True, duration_seconds=180) == "idle"
    assert git(root, "rev-list", "--count", "main..loop/development") == "2"
