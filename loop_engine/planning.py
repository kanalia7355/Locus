"""Immutable-source planning and strict, bounded plan import."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from loop_engine.config import load
from loop_engine.locking import ProjectLock
from loop_engine.models import Task
from loop_engine.schemas import validate
from loop_engine.security import SafetyError, create_text, fingerprint, reject_secrets, within
from loop_engine.state_store import StateStore

SOURCE_FILES = ("goal.md", "requirements.md", "architecture.md", "acceptance.md")


def bounded_json(raw: str, *, maximum: int = 1_000_000) -> Any:
    if len(raw.encode("utf-8")) > maximum:
        raise ValueError("Structured output size limit exceeded")
    reject_secrets(raw)

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, value in values:
            if key in data:
                raise ValueError("Duplicate JSON object key")
            data[key] = value
        return data

    try:
        data = json.loads(raw, object_pairs_hook=pairs)
    except (RecursionError, json.JSONDecodeError) as error:
        raise ValueError("Invalid structured JSON") from error
    stack = [(data, 0)]
    while stack:
        value, depth = stack.pop()
        if depth > 32:
            raise ValueError("Structured output nesting limit exceeded")
        if isinstance(value, dict):
            stack.extend((entry, depth + 1) for entry in value.values())
        elif isinstance(value, list):
            stack.extend((entry, depth + 1) for entry in value)
        elif isinstance(value, float) and not __import__("math").isfinite(value):
            raise ValueError("Non-finite JSON numbers are forbidden")
    return data


def read_json(path: Path, maximum: int = 1_000_000) -> Any:
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("Structured file size limit exceeded before decoding")
    return bounded_json(raw.decode("utf-8"), maximum=maximum)


def source_snapshot(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in SOURCE_FILES:
        path = within(root, ".loop/" + name)
        if path.stat().st_size > 64_000:
            raise SafetyError("Specification file exceeds approved context limit")
        result[name] = path.read_text(encoding="utf-8")
    result["policy"] = load(root / ".loop/config.yaml")
    reject_secrets(result)
    return result


class Planner(Protocol):
    def plan(self, context: dict[str, Any], root: Path) -> dict[str, Any]: ...


def import_plan(root: Path, state: StateStore, proposal: dict[str, Any]) -> str:
    with ProjectLock(within(root, ".loop/runtime/controller.lock")):
        validate("plan", proposal)
        reject_secrets(proposal)
        snapshot = source_snapshot(root)
        if not snapshot["goal.md"].strip():
            raise ValueError("A nonempty human Goal is required")
        tasks = [Task.from_dict(data) for data in proposal["tasks"]]
        binding = fingerprint(snapshot)
        decisions = []
        for request in proposal["decisions"]:
            decisions.append(
                {
                    "id": "DEC-" + uuid4().hex[:16],
                    "task_id": None,
                    "category": request["category"],
                    "risk": "medium",
                    "question": request["question"],
                    "options": ["approve", "reject", "revise"],
                    "status": "pending",
                    "blocking_tasks": [task.id for task in tasks],
                    "target_hash": fingerprint({"goal": binding, "request": request}),
                }
            )
        # Reject non-initial versions before normalizing initial states.
        if any(task.version for task in tasks):
            raise ValueError("Initial task versions must be zero")
        tasks = [
            replace(task, status="ready") if task.status == "planned" else task for task in tasks
        ]
        goal_id = state.import_plan(
            snapshot["goal.md"],
            binding,
            tasks,
            metadata={"spec_snapshot": snapshot, "spec_hash": binding, "plan_proposal": proposal},
            decisions=decisions,
        )
        # Generated proposals never replace the user's original specification.
        create_text(root / ".loop/requirements.proposed.md", proposal["requirements"])
        create_text(root / ".loop/architecture.proposed.md", proposal["architecture"])
        return goal_id
