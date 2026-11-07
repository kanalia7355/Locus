"""Exact local Git worktrees and source drift; no auth, network or model."""

import time
from dataclasses import replace

import pytest
import yaml
from test_loop_foundation import task
from test_loop_git import git
from test_run_authorization import approve

from loop_engine import run_authorization as run
from loop_engine.cli import initialize
from loop_engine.config import default
from loop_engine.git_manager import GitManager
from loop_engine.planning import source_snapshot
from loop_engine.security import SafetyError, fingerprint


def test_real_worktrees_bind_exact_source_and_only_confirmed_product_head_advances(
    tmp_path, monkeypatch
):
    root = tmp_path / "project"
    root.mkdir()
    state = initialize(root, "Synthetic Goal")
    cfg = default()
    cfg["development"]["allowed_paths"] = run.PATHS
    cfg["security"].update(allow_model_execution=True, sandbox_executor="proposal-docker")
    cfg["github"].update(
        enabled=True,
        delivery="local_commit_push",
        base="loop/local-development",
        repository="fixture/repo",
    )
    (root / ".loop/config.yaml").write_text(yaml.safe_dump(cfg))
    (root / ".gitignore").write_text(".loop/\n")
    (root / "control.txt").write_text("IMMUTABLE_CONTROL\n")
    (root / "backend").mkdir()
    (root / "backend/app.txt").write_text("before\n")
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Loop Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-m", "test: initialize synthetic run")
    git(root, "checkout", "-b", "loop/local-development")
    git(root, "remote", "add", "origin", "https://github.com/fixture/repo.git")
    spec = fingerprint(source_snapshot(root))
    state.import_plan(
        "Synthetic Goal",
        spec,
        [replace(task(), allowed_paths=["backend"], status="ready")],
        metadata={"spec_hash": spec},
    )
    state.set_metadata("c_min_auth_profile", {"synthetic": True})
    monkeypatch.setattr("loop_engine.c_min_runtime.verify_profile", lambda state: None)
    monkeypatch.setattr(
        "loop_engine.runtime_diagnostics.runtime_identity", lambda root: "synthetic-runtime"
    )
    monkeypatch.setattr("loop_engine.runtime_diagnostics.require_receipt", lambda root: None)
    (root / ".loop/runtime/qa-image.json").write_text("{}")
    monkeypatch.setattr("loop_engine.docker_boundary.image_audit_evidence", lambda *args: True)
    scope = run.prepare(root, state, 1800)
    approve(state, scope)
    budget = run.adopt(root, state, resume=False, duration=1800)
    budget["tasks"] = ["TASK-001"]
    state.set_metadata("run_budget", budget)
    state.set_metadata("control", "running")
    manager = GitManager(root, state, "refs/heads/loop/local-development")
    workspace = manager.prepare(state.task("TASK-001"))
    initial = manager.snapshot(state.task("TASK-001"), workspace)
    current, execution = state.claim("TASK-001", scope["id"], 3)
    owner = {
        "role": "worker",
        "schema": "proposal",
        "owner_id": execution,
        "attempt": 1,
        "spec": spec,
        "binding": fingerprint(
            {
                "task": current.specification_hash(),
                "source": fingerprint(initial),
                "base": initial["base"],
            }
        ),
    }
    before = run.call_binding(root, state, workspace, owner, "artifact")
    (workspace / "backend/app.txt").write_text("after\n")
    with pytest.raises(SafetyError, match="owner binding"):
        run.call_binding(root, state, workspace, owner, "artifact")
    state.finish_execution(execution, "returned", {})
    state.transition(current.id, "running", "verifying", version=state.task(current.id).version)
    state.transition(current.id, "verifying", "reviewing", version=state.task(current.id).version)
    verified = {"passed": True, "fixture": "synthetic QA"}
    state.evidence("verification_results", execution, verified)
    reviewer = {
        **owner,
        "role": "reviewer",
        "schema": "review",
        "binding": fingerprint(
            {
                "task": current.specification_hash(),
                "source_specification": spec,
                "snapshot": manager.snapshot(state.task(current.id), workspace),
                "verification": verified,
            }
        ),
    }
    reviewed = run.call_binding(root, state, workspace, reviewer, "review-artifact")
    assert reviewed["source"] != before["source"]
    (workspace / "control.txt").write_text("unapproved control change\n")
    with pytest.raises(SafetyError):
        run.call_binding(root, state, workspace, reviewer, "review-artifact")
    (workspace / "control.txt").write_text("IMMUTABLE_CONTROL\n")
    git(workspace, "add", "backend/app.txt")
    git(workspace, "commit", "-m", "fix: verified synthetic product")
    head = git(workspace, "rev-parse", "HEAD")
    git(root, "merge", "--ff-only", head)
    state.transition(current.id, "reviewing", "completed", version=state.task(current.id).version)
    evaluation = root / ".loop/runtime/evaluations" / head
    evaluation.parent.mkdir(parents=True)
    git(root, "worktree", "add", "--detach", str(evaluation), head)
    state.set_metadata(
        "development_budget", {"run": scope["id"], "cycles": 1, "started": time.time()}
    )
    evaluator = {
        "role": "evaluator",
        "schema": "evaluation",
        "owner_id": scope["id"] + ":1",
        "spec": spec,
        "binding": spec + ":" + head,
        "attempt": 1,
    }
    with pytest.raises(SafetyError, match="Unconfirmed"):
        run.call_binding(root, state, evaluation, evaluator, "evaluation-artifact")
    # Simulate the existing delivery adapter's authoritative confirmed-Push record;
    # local-delivery integration tests separately exercise the actual bare transport.
    state.set_metadata("local_published_head", head)
    advanced = run.call_binding(root, state, evaluation, evaluator, "evaluation-artifact")
    assert advanced["integrated_head"] == head
    assert advanced["integrated_head"] != before["integrated_head"]
    (evaluation / "backend/app.txt").write_text("unexpected post-snapshot drift\n")
    with pytest.raises(SafetyError):
        run.call_binding(root, state, evaluation, evaluator, "evaluation-artifact")
