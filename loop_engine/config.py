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
    "approval": {
        "mode": "deferred",
        "require_preapproval_for_high_risk": True,
        "routine_publication": False,
    },
    "qa": {
        "local_verification": True,
        "independent_review": True,
        "repair_failed_checks": True,
        "require_configured_checks": True,
    },
    "development": {
        "enabled": True,
        "max_cycles_per_run": 20,
        "stagnation_limit": 3,
        "evaluation_timeout_minutes": 10,
        "allowed_paths": [],
    },
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
    if not isinstance(data, dict):
        raise SafetyError("Configuration must be an object")
    # Additive v1 migration, in memory only. Never rewrite user configuration.
    data.setdefault("qa", deepcopy(DEFAULT["qa"]))
    data.setdefault("development", deepcopy(DEFAULT["development"]))
    data.setdefault("approval", {}).setdefault("routine_publication", False)
    for section, aliases in {
        "github": {"base_branch": "base"},
        "security": {"allow_unrestricted_codex_execution": "allow_unrestricted_execution"},
    }.items():
        for alias, canonical in aliases.items():
            if alias in data.get(section, {}):
                value = data[section].pop(alias)
                if canonical in data[section] and data[section][canonical] != value:
                    raise SafetyError("Conflicting configuration aliases")
                data[section][canonical] = value
    github = data.get("github", {})
    for key, expected in {
        "create_pr": True,
        "require_current_head_checks": True,
        "bypass_protection": False,
    }.items():
        if key in github and github.pop(key) is not expected:
            raise SafetyError("Unsafe or unsupported GitHub policy")
    validate("config", data)
    reject_secrets(data)
    return data


def default() -> dict[str, Any]:
    return deepcopy(DEFAULT)


def policy_hash(config: dict[str, Any]) -> str:
    return fingerprint(config)
