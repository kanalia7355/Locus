"""Versioned policy configuration with hard limits and no unsafe fallback."""

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from loop_engine.schemas import validate
from loop_engine.security import SafetyError, fingerprint, reject_secrets

DEFAULT: dict[str, Any] = {
    "version": 1,
    "loop": {
        "max_attempts_per_task": 3,
        "max_review_cycles": 2,
        "max_concurrent_tasks": 1,
        "max_runtime_minutes": 360,
        "max_tasks_per_run": 20,
        "task_timeout_minutes": 30,
    },
    "approval": {"mode": "deferred", "require_preapproval_for_high_risk": True},
    "security": {
        "allow_production_changes": False,
        "allow_destructive_operations": False,
        "allow_unrestricted_execution": False,
        "allow_model_execution": False,
        "sandbox_executor": "unavailable",
    },
    "github": {
        "enabled": False,
        "repository": "",
        "base": "main",
        "remote": "origin",
        "auto_merge": "off",
        "protect_default_branch": True,
        "required_checks": [],
        "auto_merge_allowed_paths": [],
        "delivery": "local",
    },
    "verification": {},
}


def load(path: Path) -> dict[str, Any]:
    if path.is_symlink() or path.stat().st_size > 65536:
        raise SafetyError("Configuration must be a regular file below64KiB")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    validate("config", data)
    reject_secrets(data)
    return data  # type: ignore[no-any-return]


def default() -> dict[str, Any]:
    return deepcopy(DEFAULT)


def policy_hash(config: dict[str, Any]) -> str:
    return fingerprint(config)
