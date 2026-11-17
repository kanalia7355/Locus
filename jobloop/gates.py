"""Deterministic gates a job must pass before anything is committed.

Models do not get to assert that they stayed in scope or that tests passed: the
controller checks the diff and runs the commands itself. A gate that cannot run
reports `ran=False` and is treated as a failure, never as a pass.
"""

from __future__ import annotations

import re
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


def summarise(result: subprocess.CompletedProcess[str]) -> str:
    """Keep the exit code and the last lines of each stream as the evidence."""
    tail = "\n".join((result.stdout or "").strip().splitlines()[-12:])
    errors = "\n".join((result.stderr or "").strip().splitlines()[-12:])
    return f"exit {result.returncode}\n{tail}\n{errors}".strip()


INTERPRETER = re.compile(r"^(python3?|python3?\.exe)(?=\s|$)", re.IGNORECASE)


def with_interpreter(command: str, python: str) -> str:
    """Bind a bare leading `python` to the interpreter the controller runs with.

    A recorded command must not name an interpreter by absolute path: a worker
    reads its own job file, finds the path, and treats the checkout it points at
    as the project — which is how `T-PH6-103` came to edit the main checkout on
    2026-11-16. The file says `python`; the controller supplies the rest.
    """
    stripped = command.strip()
    found = INTERPRETER.match(stripped)
    if not found:
        return stripped
    return f'"{python}"{stripped[found.end() :]}'


def run_command(name: str, command: str, *, cwd: Path, timeout: float, python: str = "") -> Gate:
    """Run a recorded verification command and keep its real exit code."""
    if not command.strip():
        return Gate(name, False, False, "no command recorded")
    if python:
        command = with_interpreter(command, python)
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
    return Gate(name, True, result.returncode == 0, summarise(result))


def run_argv(name: str, argv: list[str], *, cwd: Path, timeout: float) -> Gate:
    """Run a fixed command without a shell, so no path needs quoting.

    The recorded `test_cmd` keeps its shell (it may chain with `&&`), but a gate
    the controller builds itself must not depend on how the host shell quotes a
    Windows path.
    """
    try:
        result = subprocess.run(  # noqa: S603 — fixed argument vector, no shell
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Gate(name, False, False, f"timed out after {timeout:.0f}s")
    except OSError as error:
        return Gate(name, False, False, str(error))
    return Gate(name, True, result.returncode == 0, summarise(result))


def frontend_gates(worktree: Path, names: list[str], *, timeout: float) -> list[Gate]:
    """Typecheck and lint the frontend, run only when the job touched it.

    `vitest` transpiles without typechecking, so a job whose only gate is its
    test command can land a type error with every check green — the reviewer on
    `T-PH6-101` flagged exactly that gap and could not close it itself, because a
    read-only reviewer may not run a command that writes `tsconfig.tsbuildinfo`.
    The controller can: that file is ignored by git, so it does not disturb the
    scope gate.
    """
    if not any(name.startswith("frontend/") for name in names):
        return []
    npm = shutil.which("npm")
    if not npm:
        return [Gate("frontend-typecheck", False, False, "npm is not installed")]
    return [
        run_argv(
            f"frontend-{script}",
            [npm, "--prefix", "frontend", "run", script],
            cwd=worktree,
            timeout=timeout,
        )
        # `appearance` drives the real screen in a browser and asserts the layout
        # invariants a person would otherwise have to notice by scrolling around
        # (nothing off the right edge, the top bar staying put, the message box
        # staying reachable, no emoji, every icon button named). Unit tests never
        # see these: they render components, not a laid-out page.
        # It binds 127.0.0.1:8000 and :5174, so a dev server left running on
        # those ports will fail this gate — stop them before an unattended run.
        for script in ("typecheck", "lint", "test:appearance")
    ]


def python_gates(worktree: Path, names: list[str], *, python: str, timeout: float) -> list[Gate]:
    """Lint, format and secret-scan gates, run only when they apply."""
    targets = ["backend", "tests", "scripts", "jobloop"]
    gates: list[Gate] = []
    if any(name.endswith(".py") for name in names):
        gates.append(
            run_argv(
                "python-lint",
                [python, "-m", "ruff", "check", *targets],
                cwd=worktree,
                timeout=timeout,
            )
        )
        gates.append(
            run_argv(
                "python-format",
                [python, "-m", "ruff", "format", "--check", *targets],
                cwd=worktree,
                timeout=timeout,
            )
        )
    if names:
        gates.append(
            run_argv(
                "secret-scan",
                [python, "scripts/secret_scan.py"],
                cwd=worktree,
                timeout=timeout,
            )
        )
    return gates
