from pathlib import Path

import pytest
from test_loop_foundation import task

from loop_engine.security import SafetyError, allowed, create_text, protected, relative_path
from loop_engine.state_store import StateStore


def test_windows_aliases_and_sensitive_paths_are_denied() -> None:
    for path in (".GIT/config", "src./file", "src /file", "CON.txt", "NUL", "src/LPT1.log"):
        with pytest.raises(SafetyError):
            relative_path(path)
    for path in (".ENV", "Storage/secret.txt", "src/.ENV.production"):
        assert not allowed(path, ["*"])
    assert protected("Agents.MD")


def test_unsettled_execution_and_aba_transition_are_rejected(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.sqlite3")
    state.import_plan("goal", "hash", [task(1, status="ready"), task(2, status="ready")])
    observed = state.task("TASK-001")
    running, execution = state.claim(observed.id, "run", 3)
    with pytest.raises(ValueError, match="reconciled"):
        state.transition(running.id, "running", "ready", version=running.version)
    # Simulate a legacy/crash-corrupted task status while its execution is still unsettled.
    with state.transaction() as db:
        db.execute("UPDATE tasks SET status='ready' WHERE id=?", (running.id,))
    with pytest.raises(ValueError, match="single-task"):
        StateStore(state.path).claim("TASK-002", "run", 3)
    state.finish_execution(execution, "failed", {"code": "reconciled"})
    current = state.task(running.id)
    with pytest.raises(ValueError, match="Concurrent"):
        state.transition(observed.id, "ready", "blocked", version=observed.version)
    state.transition(current.id, "ready", "blocked", version=current.version)


def test_exclusive_initializer_never_replaces_existing_content(tmp_path: Path) -> None:
    path = tmp_path / "goal.md"
    assert create_text(path, "first")
    assert not create_text(path, "second")
    assert path.read_text() == "first"
