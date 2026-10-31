"""Deterministic command evidence; missing required verification can never pass."""

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loop_engine.checks import sanitized
from loop_engine.codex_runner import Boundary, UnprovenBoundary
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError, fingerprint


class Verifier:
    def __init__(
        self,
        profiles: dict[str, Any],
        *,
        boundary: Boundary | None = None,
        process: ProcessRunner | None = None,
    ) -> None:
        self.profiles = profiles
        self.boundary = boundary or UnprovenBoundary()
        self.process = process or ProcessRunner()

    def run(
        self,
        profile: str,
        workspace: Path,
        control_root: Path,
        *,
        timeout: float,
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]:
        commands = self.profiles.get(profile, [])
        if getattr(self.boundary, "requires_image_audit", False) and not any(
            command["required"] and command["argv"] == ["{image-audit}"] for command in commands
        ):
            commands = []  # A missing dependency gate is unavailable, never successful QA.
        deadline = time.monotonic() + timeout
        results: list[dict[str, Any]] = []
        if not commands or not any(command["required"] for command in commands):
            return {
                "passed": False,
                "status": "unavailable",
                "checks": [],
                "profile_hash": fingerprint(commands),
            }
        for command in commands:
            try:
                self.boundary.require(workspace, control_root)
                configured = [
                    sys.executable if value == "{python}" else value for value in command["argv"]
                ]
                supervised = getattr(self.boundary, "run", None)
                argv = configured if supervised else self.boundary.command(configured, workspace)
                outcome = (
                    supervised(
                        argv,
                        workspace,
                        timeout=max(0, deadline - time.monotonic()),
                        cancelled=cancelled,
                    )
                    if supervised
                    else self.process.run(
                        argv,
                        workspace,
                        timeout=max(0, deadline - time.monotonic()),
                        cancelled=cancelled,
                    )
                )
            except SafetyError:
                results.append(
                    {
                        "name": command["name"],
                        "level": command["level"],
                        "required": command["required"],
                        "status": "skipped",
                        "exit_code": None,
                    }
                )
                continue
            success = outcome.outcome == "exit" and outcome.returncode == 0
            results.append(
                {
                    "name": command["name"],
                    "level": command["level"],
                    "required": command["required"],
                    "status": "passed" if success else "failed",
                    "exit_code": outcome.returncode,
                    "outcome": outcome.outcome,
                    "elapsed_seconds": outcome.elapsed,
                    "failure_context": None
                    if success
                    else sanitized(outcome.stdout + "\n" + outcome.stderr),
                }
            )
        passed = all(result["status"] == "passed" for result in results if result["required"])
        return {
            "passed": passed,
            "status": "passed" if passed else "failed",
            "checks": results,
            "profile_hash": fingerprint(commands),
        }
