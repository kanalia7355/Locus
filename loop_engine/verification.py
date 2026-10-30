"""Deterministic command evidence; missing required verification can never pass."""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
                argv = self.boundary.command(command["argv"], workspace)
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
            outcome = self.process.run(
                argv, workspace, timeout=max(0, deadline - time.monotonic()), cancelled=cancelled
            )
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
                }
            )
        passed = all(result["status"] == "passed" for result in results if result["required"])
        return {
            "passed": passed,
            "status": "passed" if passed else "failed",
            "checks": results,
            "profile_hash": fingerprint(commands),
        }
