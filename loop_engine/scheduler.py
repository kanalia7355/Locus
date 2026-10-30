"""Deterministic serial scheduling; pending decisions block only their dependency closure."""

from loop_engine.models import Task
from loop_engine.state_store import StateStore


class Scheduler:
    def __init__(self, state: StateStore) -> None:
        self.state = state

    def next_ready_task(self) -> Task | None:
        tasks = self.state.tasks()
        completed = {task.id for task in tasks if task.status == "completed"}
        eligible = [
            task
            for task in tasks
            if task.status == "ready"
            and set(task.dependencies) <= completed
            and task.attempts < task.max_attempts
        ]
        return (
            min(
                eligible,
                key=lambda task: (
                    -task.priority,
                    {"low": 0, "medium": 1, "high": 2}[task.risk_level],
                    task.id,
                ),
            )
            if eligible
            else None
        )
