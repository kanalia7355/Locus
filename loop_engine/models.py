"""Task contracts and transitions independent of any target framework."""

from dataclasses import asdict, dataclass, field
from typing import Any

from loop_engine.schemas import validate
from loop_engine.security import allowed, fingerprint, reject_secrets, relative_path

TRANSITIONS: dict[str, set[str]] = {
    "planned": {"ready", "awaiting_approval", "blocked", "cancelled"},
    "ready": {"running", "awaiting_approval", "blocked", "cancelled"},
    "running": {"verifying", "ready", "blocked", "awaiting_approval", "failed", "cancelled"},
    "verifying": {"reviewing", "ready", "blocked", "awaiting_approval", "failed", "cancelled"},
    "reviewing": {"completed", "ready", "blocked", "awaiting_approval", "failed", "cancelled"},
    "blocked": {"ready", "awaiting_approval", "cancelled"},
    "awaiting_approval": {"ready", "blocked", "cancelled", "completed"},
    "failed": {"blocked", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


@dataclass
class Task:
    id: str
    title: str
    acceptance_criteria: list[str]
    verification_profile: str
    allowed_paths: list[str]
    status: str = "planned"
    priority: int = 50
    dependencies: list[str] = field(default_factory=list)
    attempts: int = 0
    max_attempts: int = 3
    risk_level: str = "medium"
    requires_approval: bool = False
    review_required: bool = True
    branch: str | None = None
    worktree: str | None = None
    last_error: str | None = None
    version: int = 0

    def document(self) -> dict[str, Any]:
        data = asdict(self)
        validate("task", data)
        reject_secrets(data)
        for path in self.allowed_paths:
            relative_path(path)
        return data

    def specification_hash(self) -> str:
        data = self.document()
        for key in ("status", "attempts", "branch", "worktree", "last_error", "version"):
            data.pop(key)
        return fingerprint(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        validate("task", data)
        result = cls(**data)
        result.document()
        return result


def validate_graph(tasks: list[Task]) -> None:
    by_id = {task.id: task for task in tasks}
    if len(by_id) != len(tasks):
        raise ValueError("Duplicate task IDs")
    visited: set[str] = set()
    active: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id not in by_id:
            raise ValueError("Unknown task dependency")
        if task_id in active:
            raise ValueError("Cyclic task dependencies")
        if task_id in visited:
            return
        active.add(task_id)
        for dependency in by_id[task_id].dependencies:
            visit(dependency)
        active.remove(task_id)
        visited.add(task_id)

    for task in tasks:
        task.document()
        visit(task.id)


def check_result(task: Task, result: dict[str, Any]) -> None:
    validate("result", result)
    reject_secrets(result)
    if result["task_id"] != task.id:
        raise ValueError("Worker returned another task ID")
    if any(not allowed(path, task.allowed_paths) for path in result["files_changed"]):
        raise ValueError("Worker reported out-of-scope files")
