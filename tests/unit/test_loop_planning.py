from pathlib import Path

import pytest
from test_loop_foundation import task

from loop_engine.approval import ApprovalQueue
from loop_engine.cli import initialize
from loop_engine.planning import bounded_json, import_plan, read_json, source_snapshot
from loop_engine.security import fingerprint


def proposal() -> dict[str, object]:
    return {
        "requirements": "Proposed requirements",
        "nonfunctional_requirements": ["No secrets"],
        "architecture": "Proposed architecture",
        "constraints": [],
        "risks": [],
        "tasks": [task().document()],
        "decisions": [],
    }


def test_goal_plan_import_preserves_acceptance_and_detects_change(tmp_path: Path) -> None:
    state = initialize(tmp_path, "Implement a tiny approved feature")
    acceptance = tmp_path / ".loop/acceptance.md"
    acceptance.write_text("User's original invariant")
    import_plan(tmp_path, state, proposal())
    assert state.task("TASK-001").status == "ready"
    assert acceptance.read_text() == "User's original invariant"
    assert state.metadata("spec_hash") == fingerprint(source_snapshot(tmp_path))
    acceptance.write_text("Weakened invariant")
    assert state.metadata("spec_hash") != fingerprint(source_snapshot(tmp_path))
    with pytest.raises(ValueError, match="immutable"):
        import_plan(tmp_path, state, proposal())


def test_bounded_json_rejects_duplicates_depth_and_oversized_results() -> None:
    for raw in ('{"a":1,"a":2}', "[" * 34 + "0" + "]" * 34, '{"n":NaN}'):
        with pytest.raises(ValueError):
            bounded_json(raw)
    with pytest.raises(ValueError):
        bounded_json('"' + "x" * 200 + '"', maximum=100)


def test_approval_hashes_human_batch_atomicity_and_rejection(tmp_path: Path) -> None:
    state = initialize(tmp_path, "Goal")
    queue = ApprovalQueue(state)
    binding = fingerprint({"scope": "one"})
    one = queue.request("TASK-001", "scope", binding, "Approve exact scope?", "high")
    assert queue.request("TASK-001", "scope", binding, "Approve exact scope?", "high") == one
    global_id = queue.request(None, "publication", binding, "Authorize repository?")
    assert queue.request(None, "publication", binding, "Authorize repository?") == global_id
    choice = {"id": one, "action": "approve", "target_hash": binding, "reason": "Reviewed scope"}
    with pytest.raises(ValueError):
        queue.resolve([choice, {**choice, "id": "missing"}], "human")
    assert queue.status("TASK-001", "scope", binding) == "pending"
    with pytest.raises(ValueError):
        queue.resolve([{**choice, "target_hash": fingerprint("changed")}], "human")
    queue.resolve([choice], "human")
    assert queue.status("TASK-001", "scope", binding) == "approved"
    assert queue.status("TASK-001", "scope", fingerprint("changed")) is None


def test_rejected_version_and_transaction_failure_leave_no_partial_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = initialize(tmp_path, "Goal")
    invalid = proposal()
    invalid["tasks"] = [task(version=1).document()]
    with pytest.raises(ValueError):
        import_plan(tmp_path, state, invalid)
    assert state.tasks() == []
    original_event = state._event

    def crash(*args: object) -> None:
        raise RuntimeError("Simulated crash before transaction commit")

    monkeypatch.setattr(state, "_event", crash)
    with pytest.raises(RuntimeError):
        import_plan(tmp_path, state, proposal())
    assert state.tasks() == [] and state.metadata("spec_hash") is None
    with state.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM goals").fetchone()[0] == 0
    monkeypatch.setattr(state, "_event", original_event)
    import_plan(tmp_path, state, proposal())


def test_large_plan_decisions_and_file_ingestion_limits(tmp_path: Path) -> None:
    state = initialize(tmp_path, "Goal")
    value = proposal()
    value["tasks"] = [task(index).document() for index in range(1, 102)]
    value["decisions"] = [{"category": "scope", "question": "Review scope?"}]
    import_plan(tmp_path, state, value)
    assert len(ApprovalQueue(state).decisions()[0]["blocking_tasks"]) == 101
    path = tmp_path / "oversize.json"
    path.write_bytes(b"x" * 101)
    with pytest.raises(ValueError):
        read_json(path, maximum=100)
    path.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        read_json(path)
