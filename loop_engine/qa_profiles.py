"""Suggest only commands backed by actual project files; never silently enable."""

from pathlib import Path
from typing import Any


def detect(root: Path) -> dict[str, Any]:
    commands: list[dict[str, Any]] = []
    if (root / "scripts/verify_loop.py").is_file() and (root / "loop_engine").is_dir():
        commands.append(
            {
                "name": "engine-format-lint-types-tests-secrets-dependencies",
                "level": "security",
                "argv": ["{python}", "scripts/verify_loop.py", "--audit"],
                "required": True,
            }
        )
        commands.append(
            {
                "name": "engine-wheel-build",
                "level": "static",
                "argv": [
                    "{python}",
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--no-build-isolation",
                    "--wheel-dir",
                    ".loop/runtime/wheels",
                    ".",
                ],
                "required": True,
            }
        )
    if (root / "scripts/verify.py").is_file() and (root / "backend/app").is_dir():
        commands.append(
            {
                "name": "application-format-lint-types-unit-integration-build-e2e-security",
                "level": "functional",
                "argv": ["{python}", "scripts/verify.py", "--e2e", "--audit"],
                "required": True,
            }
        )
    return {
        "detected": {"repository": commands} if commands else {},
        "enabled": False,
        "independent_architecture_and_goal_review": "required separately",
    }
