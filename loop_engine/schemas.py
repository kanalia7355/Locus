"""Closed JSON contracts. No remote references or model-supplied schemas."""

from typing import Any

from jsonschema import Draft202012Validator

Json = dict[str, Any]
STATES = [
    "planned",
    "ready",
    "running",
    "verifying",
    "reviewing",
    "completed",
    "blocked",
    "awaiting_approval",
    "failed",
    "cancelled",
]


def obj(properties: Json, required: list[str] | None = None) -> Json:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }


def text(maximum: int = 4000) -> Json:
    return {"type": "string", "maxLength": maximum}


def strings(maximum: int = 100) -> Json:
    return {"type": "array", "items": text(), "maxItems": maximum, "uniqueItems": True}


TASK = obj(
    {
        "id": {"type": "string", "pattern": "^TASK-[0-9]{3,6}$"},
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
        "status": {"enum": STATES},
        "priority": {"type": "integer", "minimum": 0, "maximum": 100},
        "dependencies": strings(),
        "acceptance_criteria": {**strings(), "minItems": 1},
        "verification_profile": text(100),
        "attempts": {"type": "integer", "minimum": 0, "maximum": 3},
        "max_attempts": {"type": "integer", "minimum": 1, "maximum": 3},
        "risk_level": {"enum": ["low", "medium", "high"]},
        "requires_approval": {"type": "boolean"},
        "review_required": {"type": "boolean"},
        "allowed_paths": {**strings(), "minItems": 1},
        "branch": {"type": ["string", "null"]},
        "worktree": {"type": ["string", "null"]},
        "last_error": {"type": ["string", "null"]},
        "version": {"type": "integer", "minimum": 0},
    }
)
DECISION = obj(
    {
        "id": text(100),
        "task_id": {"type": ["string", "null"]},
        "category": {
            "enum": [
                "architecture",
                "dependency",
                "security",
                "publication",
                "merge",
                "recovery",
                "scope",
            ]
        },
        "risk": {"enum": ["low", "medium", "high"]},
        "question": text(),
        "options": {"const": ["approve", "reject", "revise"]},
        "status": {"enum": ["pending", "approved", "rejected", "revise"]},
        "blocking_tasks": strings(200),
        "target_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    }
)
APPROVAL_REQUEST = obj({"category": DECISION["properties"]["category"], "question": text()})
RESULT = obj(
    {
        "task_id": TASK["properties"]["id"],
        "status": {"enum": ["implemented", "blocked", "failed"]},
        "summary": text(),
        "files_changed": strings(1000),
        "tests_added": strings(1000),
        "issues": strings(),
        "approval_requests": {"type": "array", "items": APPROVAL_REQUEST, "maxItems": 20},
    }
)
FINDING = obj(
    {
        "severity": {"enum": ["critical", "high", "medium", "low", "info"]},
        "file": text(1000),
        "finding": text(),
        "evidence": text(),
        "recommended_action": text(),
        "blocking": {"type": "boolean"},
    }
)
REVIEW = obj(
    {
        "task_id": TASK["properties"]["id"],
        "disposition": {"enum": ["pass", "fail", "needs_decision"]},
        "findings": {"type": "array", "items": FINDING, "maxItems": 100},
    }
)
PLAN = obj(
    {
        "requirements": text(30000),
        "nonfunctional_requirements": strings(),
        "architecture": text(30000),
        "constraints": strings(),
        "risks": strings(),
        "tasks": {"type": "array", "items": TASK, "minItems": 1, "maxItems": 200},
        "decisions": {"type": "array", "items": APPROVAL_REQUEST, "maxItems": 100},
    }
)
COMMAND = obj(
    {
        "name": {"type": "string", "minLength": 1, "maxLength": 100},
        "level": {"enum": ["static", "functional", "security", "alignment"]},
        "argv": {"type": "array", "items": text(1000), "minItems": 1, "maxItems": 100},
        "required": {"type": "boolean"},
    }
)
CONFIG = obj(
    {
        "version": {"const": 1},
        "qa": obj(
            {
                "local_verification": {"const": True},
                "independent_review": {"const": True},
                "repair_failed_checks": {"const": True},
                "require_configured_checks": {"const": True},
            }
        ),
        "loop": obj(
            {
                "max_attempts_per_task": {"type": "integer", "minimum": 1, "maximum": 3},
                "max_review_cycles": {"type": "integer", "minimum": 0, "maximum": 2},
                "max_concurrent_tasks": {"const": 1},
                "max_runtime_minutes": {"type": "number", "exclusiveMinimum": 0, "maximum": 360},
                "max_tasks_per_run": {"type": "integer", "minimum": 1, "maximum": 20},
                "task_timeout_minutes": {"type": "number", "exclusiveMinimum": 0, "maximum": 30},
            }
        ),
        "approval": obj(
            {"mode": {"const": "deferred"}, "require_preapproval_for_high_risk": {"const": True}}
        ),
        "security": obj(
            {
                "allow_production_changes": {"const": False},
                "allow_destructive_operations": {"const": False},
                "allow_unrestricted_execution": {"const": False},
                "allow_model_execution": {"type": "boolean"},
                "sandbox_executor": {"enum": ["codex", "unavailable"]},
            }
        ),
        "github": obj(
            {
                "enabled": {"type": "boolean"},
                "repository": text(200),
                "base": text(200),
                "remote": {"const": "origin"},
                "auto_merge": {"enum": ["off", "safe"]},
                "protect_default_branch": {"const": True},
                "required_checks": strings(),
                "auto_merge_allowed_paths": strings(),
                "delivery": {"enum": ["local", "pull_request", "merged"]},
            }
        ),
        "verification": {
            "type": "object",
            "propertyNames": {"pattern": "^[a-zA-Z0-9_-]{1,100}$"},
            "additionalProperties": {"type": "array", "items": COMMAND, "maxItems": 100},
        },
    }
)
SCHEMAS = {
    "task": TASK,
    "result": RESULT,
    "decision": DECISION,
    "review": REVIEW,
    "plan": PLAN,
    "config": CONFIG,
}


def validate(name: str, value: Any) -> None:
    errors = sorted(
        Draft202012Validator(SCHEMAS[name]).iter_errors(value), key=lambda e: str(e.path)
    )
    if errors:
        # Never include instance values: JSON Schema's default messages can echo credentials.
        paths = ["/".join(str(part) for part in error.path) or "root" for error in errors[:8]]
        raise ValueError(f"Invalid {name} schema at: {', '.join(paths)}")
