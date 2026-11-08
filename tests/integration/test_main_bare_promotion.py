"""Real temporary bare-repository CAS transactions, never GitHub/main of Locus."""

import pytest
from test_local_delivery import fixture as delivery_fixture
from test_loop_git import git
from test_main_integration import fixture as main_fixture

from loop_engine.main_integration import SOURCE, TARGET, MainIntegration, atomic_payload
from loop_engine.process import ProcessRunner
from loop_engine.reviewer import review_binding
from loop_engine.security import SafetyError, fingerprint
from scripts.check_commit_subjects import verify


@pytest.mark.parametrize("interruption", ["none", "race", "lost_reply"])
def test_actual_bare_atomic_refs_guard_and_preserve_development(
    tmp_path, monkeypatch, interruption
):
    root, bare, state, work, manager, publisher = delivery_fixture(tmp_path, monkeypatch)
    cp = state.get_checkpoint(work.id)
    state.set_metadata("spec_hash", "spec")
    cp["binding"] = review_binding(work, "spec", cp["snapshot"], cp["verification"])
    state.checkpoint(work.id, cp)
    state.evidence(
        "reviews",
        work.id,
        {"task_id": work.id, "disposition": "pass", "findings": []},
        cp["binding"],
    )
    published = publisher.deliver(work, cp, cancelled=lambda: False)
    head = published["pushed_head"]
    cp = state.get_checkpoint(work.id)
    before = git(root, "rev-parse", "main")
    git(bare, "update-ref", TARGET, before)
    git(bare, "update-ref", SOURCE, head)
    other = tmp_path / "other"
    other.mkdir()
    _, _, _, policy, ci, _, _ = main_fixture(other)
    ci["sha"] = head
    for run in ci["runs"]:
        run["sha"] = head
        for job in run["jobs"]:
            job["sha"] = head
    state.set_metadata("run_budget", {"id": "run", "deadline": __import__("time").time() + 180})
    state.set_metadata(
        "main_range_review",
        {
            "before": before,
            "sha": head,
            "binding": cp["binding"],
            "policy": fingerprint(policy),
            "passed": True,
        },
    )

    class Bare:
        offline = True
        calls = 0

        def refs(self):
            return {ref: git(bare, "rev-parse", ref) for ref in (SOURCE, TARGET)}

        def checks(self, sha):
            assert sha == head
            return ci

        def update_refs(self, old, new):
            self.calls += 1
            payload = atomic_payload("node1", old, new)
            assert all(u["force"] is False for u in payload["refUpdates"])
            if interruption == "race":
                # A competing local writer rewinds the simulated source before CAS.
                git(bare, "update-ref", SOURCE, before, head)
            result = ProcessRunner().run(
                ["git", "update-ref", "--stdin"],
                bare,
                timeout=20,
                stdin=(
                    f"start\nverify {SOURCE} {new}\nupdate {TARGET} {new} {old}\nprepare\ncommit\n"
                ),
            )
            if result.outcome != "exit" or result.returncode != 0:
                raise SafetyError("atomic bare comparison rejected")
            if interruption == "lost_reply":
                raise OSError("synthetic disconnect after actual atomic update")

    backend = Bare()
    promotion = MainIntegration(state, manager, policy, backend)
    if interruption == "race":
        with pytest.raises(SafetyError):
            promotion.deliver(work, cp, cancelled=lambda: False)
        assert git(bare, "rev-parse", TARGET) == before
        assert git(bare, "rev-parse", "refs/heads/loop/development") == head
    elif interruption == "lost_reply":
        with pytest.raises(OSError):
            promotion.deliver(work, cp, cancelled=lambda: False)
        publisher.promotion = promotion
        manager.operation_cancelled = lambda: True
        original = manager._git

        def observe_only(args, *a, **kw):
            assert args[0] not in {"push", "commit", "merge", "update-ref", "add"}
            return original(args, *a, **kw)

        monkeypatch.setattr(manager, "_git", observe_only)
        assert publisher.deliver(work, cp, cancelled=lambda: True)["main_head"] == head
        assert manager.operation_cancelled()
        assert git(bare, "rev-parse", TARGET) == head
        # Actual Controller stop path observes the receipt without completing task/next task.
        from types import SimpleNamespace

        from loop_engine.controller import Controller

        with state.connect() as db:
            db.execute("UPDATE tasks SET status='awaiting_approval' WHERE id=?", (work.id,))
        controller = SimpleNamespace(publisher=publisher, state=state, cancelled=lambda: True)
        Controller._deliver(controller, state.task(work.id))
        assert state.task(work.id).status == "awaiting_approval"
        assert state.task("TASK-002").attempts == 0
    else:
        assert promotion.deliver(work, cp, cancelled=lambda: False)["complete"]
        assert promotion.deliver(work, cp, cancelled=lambda: False)["complete"]
        assert git(bare, "rev-parse", TARGET) == head
    assert backend.calls == 1
    assert git(root, "rev-parse", "main") == before


def _subject_repo(root):
    git(root, "init", "-b", "loop/fixture")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "commit", "--allow-empty", "-m", "test: initial fixture")
    return git(root, "rev-parse", "HEAD")


def test_push_subject_validation_checks_real_range_and_rejects_bad_subject(tmp_path):
    _subject_repo(tmp_path)
    before = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "commit", "--allow-empty", "-m", "fix(ci): check actual commit")
    after = git(tmp_path, "rev-parse", "HEAD")
    assert verify(tmp_path, before, after) == 1
    git(tmp_path, "commit", "--allow-empty", "-m", "invalid subject")
    with pytest.raises(ValueError, match="non-Conventional"):
        verify(tmp_path, before, git(tmp_path, "rev-parse", "HEAD"))
    with pytest.raises(ValueError, match="mismatched"):
        verify(tmp_path, before, after)


def test_push_subject_validation_skips_merge_commit_but_checks_siblings(tmp_path):
    before = _subject_repo(tmp_path)
    git(tmp_path, "checkout", "-b", "loop/side")
    git(tmp_path, "commit", "--allow-empty", "-m", "fix: side commit")
    git(tmp_path, "checkout", "loop/fixture")
    git(tmp_path, "commit", "--allow-empty", "-m", "feat: sibling commit")
    git(tmp_path, "merge", "--no-ff", "loop/side", "-m", "Merge branch 'loop/side'")

    assert verify(tmp_path, before, git(tmp_path, "rev-parse", "HEAD")) == 2


def test_oversized_push_range_falls_back_to_local_development_base(tmp_path):
    origin_main = _subject_repo(tmp_path)
    tree = git(tmp_path, "rev-parse", "HEAD^{tree}")
    parent = origin_main
    branch_base = None
    for index in range(201):
        parent = git(
            tmp_path,
            "commit-tree",
            tree,
            "-p",
            parent,
            "-m",
            f"test: generated commit {index}",
        )
        if index == 199:
            branch_base = parent
    assert branch_base is not None
    git(tmp_path, "update-ref", "refs/remotes/origin/main", origin_main)
    git(tmp_path, "update-ref", "refs/remotes/origin/loop/local-development", branch_base)
    git(tmp_path, "update-ref", "HEAD", parent)

    assert verify(tmp_path, origin_main, parent) == 1


def test_empty_branch_local_push_range_succeeds_with_note(tmp_path, capsys):
    head = _subject_repo(tmp_path)
    git(tmp_path, "update-ref", "refs/remotes/origin/loop/local-development", head)

    assert verify(tmp_path, head, head) == 0
    assert "No new commits in the branch-local Push range" in capsys.readouterr().out
