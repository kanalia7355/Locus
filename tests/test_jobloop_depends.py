from __future__ import annotations

from pathlib import Path

from jobloop.tasks import Phase, Task


def _make_task(
    task_id: str,
    status: str = "todo",
    depends_on: list[str] | None = None,
) -> Task:
    fields = {
        "id": task_id,
        "status": status,
        "weight": "light",
        "attempts": "0",
        "allowed_paths": "jobloop/tasks.py",
        "test_cmd": "python -m pytest -q",
    }
    if depends_on:
        fields["depends_on"] = ", ".join(depends_on)
    return Task(
        path=Path(f"{task_id}.md"),
        fields=fields,
        body="",
        newline="\n",
    )


def test_same_phase_done_dependency_is_ready() -> None:
    dep = _make_task("T-PH9-001", status="done")
    task = _make_task("T-PH9-002", status="todo", depends_on=["T-PH9-001"])
    phase = Phase(directory=Path("progress/phase-9"), tasks=[dep, task])

    assert phase.unmet(task) == []
    assert phase.ready(task) is True


def test_same_phase_todo_dependency_waits_without_unresolvable_marker() -> None:
    dep = _make_task("T-PH9-001", status="todo")
    task = _make_task("T-PH9-002", status="todo", depends_on=["T-PH9-001"])
    phase = Phase(directory=Path("progress/phase-9"), tasks=[dep, task])

    assert phase.unmet(task) == ["T-PH9-001"]
    assert phase.ready(task) is False


def test_missing_and_cross_phase_dependencies_are_marked_unresolvable() -> None:
    typo_task = _make_task("T-PH9-002", status="todo", depends_on=["T-PH9-9999"])
    cross_phase_task = _make_task("T-PH9-003", status="todo", depends_on=["T-PH6-127"])
    phase = Phase(directory=Path("progress/phase-9"), tasks=[typo_task, cross_phase_task])

    typo_unmet = phase.unmet(typo_task)
    assert len(typo_unmet) == 1
    assert typo_unmet[0] != "T-PH9-9999"
    assert "T-PH9-9999" in typo_unmet[0]
    assert "not in phase" in typo_unmet[0]
    assert phase.ready(typo_task) is False

    cross_unmet = phase.unmet(cross_phase_task)
    assert len(cross_unmet) == 1
    assert cross_unmet[0] != "T-PH6-127"
    assert "T-PH6-127" in cross_unmet[0]
    assert "not in phase" in cross_unmet[0]
    assert phase.ready(cross_phase_task) is False
