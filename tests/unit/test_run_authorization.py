"""Synthetic Controller state; no actual auth, remote, or model execution."""

import time

import pytest
import yaml
from test_loop_foundation import task as make_task

from loop_engine import run_authorization as run
from loop_engine.approval import ApprovalQueue
from loop_engine.cli import initialize
from loop_engine.config import default
from loop_engine.controller import Controller
from loop_engine.model_invocations import InvocationJournal
from loop_engine.security import SafetyError, fingerprint
from loop_engine.state_store import StateStore


class FakeGit:
    def __init__(self, root, state):
        self.root, self.state = root, state

    def _git(self, args, cwd=None):
        cwd = cwd or self.root
        if args[:2] == ["merge-base", "--is-ancestor"]:
            assert args[2] == "head"
            return ""
        if args[0] == "symbolic-ref":
            return "loop/TASK-001-fixture"
        if args[0] == "status":
            return ""
        if args[:2] == ["rev-parse", "--git-common-dir"] or "--git-common-dir" in args:
            return "synthetic-common"
        if "--show-toplevel" in args:
            return str(cwd)
        if args[-1] == "HEAD" and "evaluations" not in cwd.parts:
            return "head"
        return self.state.metadata("local_published_head", "head")

    def snapshot(self, task, workspace):
        return {
            "base": "head",
            "branch": "loop/TASK-001-fixture",
            "paths": [],
            "diff_hash": "synthetic-diff",
        }


def fixture(tmp_path, monkeypatch):
    state = initialize(tmp_path, "Synthetic bounded Goal")
    cfg = default()
    cfg["development"]["allowed_paths"] = run.PATHS
    cfg["github"].update(
        enabled=True,
        delivery="local_commit_push",
        base="loop/local-development",
        repository="fixture/repo",
    )
    (tmp_path / ".loop/config.yaml").write_text(yaml.safe_dump(cfg))
    work = make_task()
    work.allowed_paths = ["backend", "tests"]
    state.import_plan("Synthetic Goal", "spec", [work], metadata={"spec_hash": "spec"})
    state.transition(work.id, "planned", "ready", version=state.task(work.id).version)
    identity = {
        "spec": "spec",
        "profile": "profile",
        "runtime": "runtime",
        "control": "control",
        "common": "synthetic-common",
    }
    monkeypatch.setattr(run, "identity", lambda root, state: dict(identity))
    monkeypatch.setattr(run, "GitManager", FakeGit)
    monkeypatch.setattr(
        run, "files", lambda root, git, control_only: "control" if control_only else "source"
    )
    monkeypatch.setattr("loop_engine.runtime_diagnostics.require_receipt", lambda root: None)
    return state, identity


def approve(state, scope):
    queue = ApprovalQueue(state)
    decision = next(d for d in queue.decisions() if d["target_hash"] == fingerprint(scope))
    queue.resolve(
        [
            {
                "id": decision["id"],
                "action": "approve",
                "target_hash": fingerprint(scope),
                "reason": "Synthetic database only; not actual permission",
            }
        ],
        "fixture",
    )


def start(root, state):
    scope = run.prepare(root, state, 1800)
    approve(state, scope)
    budget = run.adopt(root, state, resume=False, duration=1800)
    state.set_metadata("control", "running")
    return scope, budget


def worker(root, state):
    budget = state.metadata("run_budget")
    state.set_metadata("run_budget", {**budget, "tasks": ["TASK-001"]})
    task, execution = state.claim("TASK-001", state.metadata("run_budget")["id"], 3)
    workspace = root / ".loop/runtime/worktrees/TASK-001"
    workspace.mkdir(parents=True)
    state.checkpoint(
        task.id, {"workspace": str(workspace), "base": "head", "branch": "loop/TASK-001-fixture"}
    )
    snapshot = FakeGit(root, state).snapshot(task, workspace)
    owner = {
        "role": "worker",
        "schema": "proposal",
        "owner_id": execution,
        "attempt": task.attempts,
        "spec": "spec",
        "binding": fingerprint(
            {"task": task.specification_hash(), "source": fingerprint(snapshot), "base": "head"}
        ),
    }
    return workspace, owner


def test_preparation_is_durable_idempotent_and_not_a_live_grant(tmp_path, monkeypatch):
    state, identity = fixture(tmp_path, monkeypatch)
    original_request = ApprovalQueue.request
    monkeypatch.setattr(
        ApprovalQueue, "request", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash"))
    )
    with pytest.raises(RuntimeError):
        Controller.prepare_run(tmp_path, state)
    persisted = state.metadata("c_min_run_proposal")
    monkeypatch.setattr(ApprovalQueue, "request", original_request)
    assert Controller.prepare_run(tmp_path, state) == persisted
    assert state.metadata("control") == "stopped" and state.metadata("run_budget") is None
    assert state.task("TASK-001").attempts == 0
    with pytest.raises(SafetyError, match="authorization"):
        run.adopt(tmp_path, state, resume=False, duration=1800)
    approve(state, persisted)
    budget = run.adopt(tmp_path, state, resume=False, duration=1800)
    assert budget["id"] == persisted["id"]
    assert budget["deadline"] - budget["started"] == 1800
    budget["consumed_seconds"] = 31
    budget["tasks"] = ["TASK-001"]
    state.set_metadata("run_budget", budget)
    assert run.adopt(tmp_path, state, resume=True, duration=1800) == budget
    with pytest.raises(SafetyError):
        run.adopt(tmp_path, state, resume=False, duration=1800)
    with pytest.raises(SafetyError):
        run.adopt(tmp_path, state, resume=True, duration=7200)
    identity["profile"] = "changed"
    with pytest.raises(SafetyError):
        run.adopt(tmp_path, state, resume=True, duration=1800)


def test_normal_receipt_cannot_be_replaced_by_a_trial_or_offline_approval(tmp_path, monkeypatch):
    state, _ = fixture(tmp_path, monkeypatch)
    scope = run.prepare(tmp_path, state, 1800)
    approve(state, scope)
    monkeypatch.setattr(
        "loop_engine.runtime_diagnostics.require_receipt",
        lambda root: (_ for _ in ()).throw(SafetyError("no normal proof")),
    )
    with pytest.raises(SafetyError, match="normal proof"):
        run.adopt(tmp_path, state, resume=False, duration=1800)
    assert state.metadata("run_budget") is None and state.metadata("control") == "stopped"


def test_call_binding_owns_task_and_durable_reservation_and_cannot_replay(tmp_path, monkeypatch):
    state, _ = fixture(tmp_path, monkeypatch)
    scope, _ = start(tmp_path, state)
    workspace, owner = worker(tmp_path, state)
    binding = run.call_binding(tmp_path, state, workspace, owner, "artifact")
    journal = InvocationJournal(state)
    call = journal.claim(owner, "artifact", time.time() + 60)
    run.reserve_binding(state, call, binding)
    run.reserve_binding(state, call, binding)
    run.recheck(state, call, binding)
    for field in ("role", "schema", "owner_id", "attempt", "spec", "binding"):
        changed = {**owner, field: 2 if field == "attempt" else "wrong"}
        with pytest.raises(SafetyError):
            run.call_binding(tmp_path, state, workspace, changed, "artifact")
    with pytest.raises(SafetyError):
        run.call_binding(tmp_path, state, tmp_path, owner, "artifact")
    with state.transaction() as db:
        db.execute("UPDATE model_run_bindings SET document='{}' WHERE invocation=?", (call,))
    with pytest.raises(SafetyError):
        run.recheck(state, call, binding)
    journal.advance(call, "prepared", "launch_reserved")
    journal.hold(call)
    with pytest.raises(SafetyError):
        journal.claim(owner, "artifact", time.time() + 60)
    state.set_metadata("control", "stopped")
    with pytest.raises(SafetyError):
        run.prepare(tmp_path, state, 1800)
    assert scope["id"] == state.metadata("run_budget")["id"]


def test_scope_revocation_and_deadline_drift_stop_an_active_call(tmp_path, monkeypatch):
    state, _ = fixture(tmp_path, monkeypatch)
    _, budget = start(tmp_path, state)
    workspace, owner = worker(tmp_path, state)
    binding = run.call_binding(tmp_path, state, workspace, owner, "artifact")
    assert run.active(state, binding)
    state.set_metadata("run_budget", {**budget, "deadline": budget["deadline"] + 1})
    assert not run.active(state, binding)
    with pytest.raises(SafetyError):
        run.call_binding(tmp_path, state, workspace, owner, "artifact")
    state.set_metadata("run_budget", budget)
    state.set_metadata("control", "paused")
    assert not run.active(state, binding)


def test_evaluator_and_reviewer_require_their_own_exact_state_and_evidence(tmp_path, monkeypatch):
    state, _ = fixture(tmp_path, monkeypatch)
    scope, _ = start(tmp_path, state)
    workspace, owner = worker(tmp_path, state)
    execution = owner["owner_id"]
    state.finish_execution(execution, "returned", {})
    state.transition("TASK-001", "running", "verifying", version=state.task("TASK-001").version)
    state.transition("TASK-001", "verifying", "reviewing", version=state.task("TASK-001").version)
    review = {**owner, "role": "reviewer", "schema": "review"}
    with pytest.raises(SafetyError):
        run.call_binding(tmp_path, state, workspace, review, "artifact")
    verification = {"passed": True, "fixture": "verification"}
    state.evidence("verification_results", execution, verification)
    task = state.task("TASK-001")
    review["binding"] = fingerprint(
        {
            "task": task.specification_hash(),
            "source_specification": "spec",
            "snapshot": FakeGit(tmp_path, state).snapshot(task, workspace),
            "verification": verification,
        }
    )
    assert (
        run.call_binding(tmp_path, state, workspace, review, "review-artifact")["owner"] == review
    )
    state.transition("TASK-001", "reviewing", "completed", version=state.task("TASK-001").version)
    state.set_metadata(
        "development_budget", {"run": scope["id"], "cycles": 1, "started": time.time()}
    )
    evaluation = tmp_path / ".loop/runtime/evaluations/head"
    evaluation.mkdir(parents=True)
    evaluator = {
        "role": "evaluator",
        "schema": "evaluation",
        "owner_id": scope["id"] + ":1",
        "attempt": 1,
        "spec": "spec",
        "binding": "spec:head",
    }
    assert run.call_binding(tmp_path, state, evaluation, evaluator, "evaluation-artifact")
    state.set_metadata("development_budget", {"run": scope["id"], "cycles": 21})
    with pytest.raises(SafetyError):
        run.call_binding(tmp_path, state, evaluation, {**evaluator, "attempt": 21}, "artifact")


def test_expiry_and_exhausted_attempts_never_reset(tmp_path, monkeypatch):
    state, _ = fixture(tmp_path, monkeypatch)
    scope = run.prepare(tmp_path, state, 1800)
    approve(state, scope)
    monkeypatch.setattr(
        run.time, "time", lambda: state.metadata("c_min_run_activation")["start_until"] + 1
    )
    with pytest.raises(SafetyError):
        run.adopt(tmp_path, state, resume=False, duration=1800)
    assert state.task("TASK-001").attempts == 0


def test_readonly_state_can_neither_initialize_nor_modify(tmp_path):
    path = tmp_path / "state.sqlite3"
    with pytest.raises(ValueError):
        StateStore(path, readonly=True)
    state = StateStore(path)
    state.set_metadata("sentinel", {"unchanged": True})
    readonly = StateStore(path, readonly=True)
    assert readonly.metadata("sentinel") == {"unchanged": True}
    import sqlite3

    with pytest.raises(sqlite3.OperationalError):
        readonly.set_metadata("sentinel", {})
    assert state.metadata("sentinel") == {"unchanged": True}


def test_controller_adopts_prepared_identity_and_resume_keeps_attempts_and_deadline(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    state, _ = fixture(tmp_path, monkeypatch)
    scope = Controller.prepare_run(tmp_path, state)
    seen = []

    def execute(*args, **kwargs):
        seen.append(state.metadata("run_budget")["id"])
        assert state.metadata("control") == "running"
        raise SafetyError("synthetic worker stop, no model called")

    spaces = SimpleNamespace(
        prepare=lambda task: tmp_path, snapshot=lambda *args: {"base": "head", "paths": []}
    )
    controller = Controller(tmp_path, state, SimpleNamespace(execute=execute), None, None, spaces)
    monkeypatch.setattr(controller, "_context", lambda: {})
    with pytest.raises(SafetyError):
        controller.run(duration_seconds=1800)
    assert not seen and state.metadata("control") == "stopped"
    approve(state, scope)
    assert controller.run(duration_seconds=1800) == "idle"
    assert seen == [scope["id"]] and state.task("TASK-001").attempts == 1
    before = state.metadata("run_budget")
    assert controller.run(resume=True, duration_seconds=1800) == "idle"
    after = state.metadata("run_budget")
    assert after["id"] == before["id"] and after["deadline"] == before["deadline"]
    assert after["tasks"] == before["tasks"]
    assert after["consumed_seconds"] >= before["consumed_seconds"]
    assert state.task("TASK-001").attempts == 1


def test_exhausted_task_cannot_be_reclaimed_by_the_prepared_run(tmp_path, monkeypatch):
    state, _ = fixture(tmp_path, monkeypatch)
    scope, _ = start(tmp_path, state)
    for _ in range(3):
        task, execution = state.claim("TASK-001", scope["id"], 3)
        state.finish_execution(execution, "failed", {})
        state.transition(task.id, "running", "ready", version=state.task(task.id).version)
    with pytest.raises(ValueError):
        state.claim("TASK-001", scope["id"], 3)
    assert state.task("TASK-001").attempts == 3
    state.set_metadata("control", "stopped")
    assert run.prepare(tmp_path, state, 1800)["id"] == scope["id"]
    assert state.task("TASK-001").attempts == 3


def test_preparation_cannot_exceed_a_lower_configured_runtime_ceiling(tmp_path, monkeypatch):
    state, _ = fixture(tmp_path, monkeypatch)
    path = tmp_path / ".loop/config.yaml"
    config = yaml.safe_load(path.read_text())
    config["loop"]["max_runtime_minutes"] = 10
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(SafetyError, match="ceiling"):
        run.prepare(tmp_path, state, 1800)
    assert state.metadata("c_min_run_proposal") is None


def test_auth_probe_requires_separate_actual_scope_approval(tmp_path, monkeypatch):
    state, _ = fixture(tmp_path, monkeypatch)
    scope = run.prepare(tmp_path, state, 1800)
    assert not run.auth_probe_authorized(tmp_path)
    approve(state, scope)
    assert run.auth_probe_authorized(tmp_path)
    state.set_metadata("c_min_run_proposal", {**scope, "auth": "not-approved"})
    assert not run.auth_probe_authorized(tmp_path)


def test_normal_run_waits_without_clock_then_activation_window_is_not_renewed(
    tmp_path, monkeypatch
):
    state, _ = fixture(tmp_path, monkeypatch)
    clock = [1000.0]
    monkeypatch.setattr(run.time, "time", lambda: clock[0])
    scope = run.prepare(tmp_path, state, 1800)
    assert "start_until" not in scope and "latest_deadline" not in scope
    clock[0] += 86400 * 7
    assert run.prepare(tmp_path, state, 1800) == scope
    assert state.metadata("c_min_run_activation") is None
    approve(state, scope)
    activation = state.metadata("c_min_run_activation")
    assert activation["approved_at"] == clock[0]
    assert activation["start_until"] == clock[0] + scope["start_window"]
    clock[0] += 10
    budget = run.adopt(tmp_path, state, resume=False, duration=1800)
    assert budget["started"] == clock[0] and budget["deadline"] == clock[0] + 1800
    clock[0] += 181
    assert run.adopt(tmp_path, state, resume=True, duration=None) == budget
    assert state.metadata("c_min_run_activation") == activation
    clock[0] = budget["deadline"] + 1
    with pytest.raises(SafetyError):
        run.adopt(tmp_path, state, resume=True, duration=1800)
    assert state.metadata("run_budget") == budget


def test_normal_owner_activation_rolls_back_on_decision_failure(tmp_path, monkeypatch):
    state, _ = fixture(tmp_path, monkeypatch)
    scope = run.prepare(tmp_path, state, 1800)
    original = state._event

    def failure(db, kind, *args):
        if kind == "approval.resolved":
            raise RuntimeError("synthetic decision commit failure")
        return original(db, kind, *args)

    monkeypatch.setattr(state, "_event", failure)
    with pytest.raises(RuntimeError):
        approve(state, scope)
    assert state.metadata("c_min_run_activation") is None
    assert ApprovalQueue(state).status(None, "scope", fingerprint(scope)) == "pending"


def test_matching_budget_and_row_edits_cannot_extend_original_duration(tmp_path, monkeypatch):
    state, _ = fixture(tmp_path, monkeypatch)
    _, budget = start(tmp_path, state)
    with state.transaction() as db:
        db.execute("UPDATE c_min_runs SET deadline=deadline+1 WHERE id=?", (budget["id"],))
    state.set_metadata("run_budget", {**budget, "deadline": budget["deadline"] + 1})
    state.set_metadata("control", "stopped")
    with pytest.raises(SafetyError, match="timestamps"):
        run.adopt(tmp_path, state, resume=True, duration=1800)
