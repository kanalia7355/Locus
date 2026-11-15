"""Deterministic gates a job must pass before anything is committed.

Models do not get to assert that they stayed in scope or that tests passed: the
controller checks the diff and runs the commands itself. A gate that cannot run
reports `ran=False` and is treated as a failure, never as a pass.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Never writable by a job, whatever its task file says: the harness heart, the
# retired engine, the owner's specifications, CI definitions and packaging.
# `docs/agent/CONSTRAINTS.md` §5-1/§5-2/§5-3 and `AGENTS.md`.
PROTECTED = (
    ".pi/",
    ".loop/",
    "loop_engine/",
    "docs/plans/",
    "docs/planning/",
    "docs/governance/",
    "docs/agent/",
    ".github/",
    "pyproject.toml",
    ".gitattributes",
)


@dataclass
class Gate:
    """One check: whether it ran, whether it passed, and the evidence."""

    name: str
    ran: bool
    passed: bool
    detail: str

    @property
    def green(self) -> bool:
        return self.ran and self.passed


GIT = shutil.which("git") or "git"


def changed_files(worktree: Path) -> list[str]:
    """Every path git reports as added, modified, renamed or untracked."""
    result = subprocess.run(  # noqa: S603 — resolved git path, no shell
        [GIT, "status", "--porcelain=1", "-z", "--untracked-files=all"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    if result.returncode:
        return []
    names: list[str] = []
    entries = [entry for entry in result.stdout.split("\0") if entry]
    for entry in entries:
        if len(entry) < 4:
            continue
        name = entry[3:]
        # A rename reports `old -> new`; git -z splits them, so take what is here.
        names.append(name.strip().replace("\\", "/"))
    return names


def within_scope(names: list[str], allowed: list[str]) -> Gate:
    """Changed paths must be inside the task's allowed paths and never protected."""
    normalised = [name.replace("\\", "/") for name in allowed]
    protected = [name for name in names if name.startswith(PROTECTED)]
    if protected:
        return Gate("scope", True, False, f"protected paths touched: {sorted(protected)}")
    if not normalised:
        return Gate("scope", True, False, "the task declares no allowed paths")
    outside = [
        name
        for name in names
        if not any(
            name == entry or name.startswith(entry.rstrip("/") + "/") for entry in normalised
        )
    ]
    if outside:
        return Gate("scope", True, False, f"outside allowed_paths: {sorted(outside)}")
    return Gate("scope", True, True, f"{len(names)} changed path(s) within scope")


def run_command(name: str, command: str, *, cwd: Path, timeout: float) -> Gate:
    """Run a recorded verification command and keep its real exit code."""
    if not command.strip():
        return Gate(name, False, False, "no command recorded")
    try:
        result = subprocess.run(  # noqa: S602 — recorded repository command, shell needed for &&
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Gate(name, False, False, f"timed out after {timeout:.0f}s")
    except OSError as error:
        return Gate(name, False, False, str(error))
    tail = "\n".join((result.stdout or "").strip().splitlines()[-12:])
    errors = "\n".join((result.stderr or "").strip().splitlines()[-12:])
    detail = f"exit {result.returncode}\n{tail}\n{errors}".strip()
    return Gate(name, True, result.returncode == 0, detail)


def python_gates(worktree: Path, names: list[str], *, python: str, timeout: float) -> list[Gate]:
    """Lint, format and secret-scan gates, run only when they apply."""
    gates: list[Gate] = []
    if any(name.endswith(".py") for name in names):
        quoted = shlex.quote(python)
        gates.append(
            run_command(
                "python-lint",
                f"{quoted} -m ruff check backend tests scripts jobloop",
                cwd=worktree,
                timeout=timeout,
            )
        )
        gates.append(
            run_command(
                "python-format",
                f"{quoted} -m ruff format --check backend tests scripts jobloop",
                cwd=worktree,
                timeout=timeout,
            )
        )
    if names:
        gates.append(
            run_command(
                "secret-scan",
                f"{shlex.quote(python)} scripts/secret_scan.py",
                cwd=worktree,
                timeout=timeout,
            )
        )
    return gates
