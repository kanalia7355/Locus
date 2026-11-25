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


def litter(names: list[str], allowed: list[str], *, contents: dict[str, str]) -> list[str]:
    """Scratch files a worker left behind: not referenced, not in scope, not kept.

    Free models work by writing: command output into `pytest_out.txt`, one-off
    probes into `check_select3.py`, a retry into `fix_test2.py`. Nine jobs in
    four days were stopped by it, three of them *after* the brief was changed to
    forbid it in so many words. The instruction does not take, so the loop stops
    losing jobs to it — the files are deleted and recorded as the deviation they
    are, rather than costing a person a ruling each time.

    The discriminator is reference, not file extension. A file the delivered
    change never mentions cannot be part of the change: nothing imports
    `check_select3.py`, which is exactly what makes it scratch. A path that *is*
    named by something in scope is real work in the wrong place — a scope drawn
    too narrowly — and must keep stopping the job.

    `contents` holds the text of the in-scope files — the changed ones and the
    rest of `allowed_paths`, since an import can come from a file the job was
    allowed to touch but did not change. Every changed in-scope path must have an
    entry: a missing one means a file could not be read, and then nothing is
    swept at all, because the unread file might be the one that references the
    loose path. Stopping a job is recoverable; deleting a worker's file is not.
    """
    normalised = [name.replace("\\", "/") for name in allowed]
    inside = [
        name
        for name in names
        if any(name == entry or name.startswith(entry.rstrip("/") + "/") for entry in normalised)
    ]
    if any(name not in contents for name in inside):
        return []

    # Only in-scope text may vouch for a loose path. Reading the whole of
    # `contents` let the scratch vouch for itself: `T-PH7-211`'s worker saved
    # `git status` output into `git_status.txt`, that listing named all eight of
    # its sibling scratch files, and the set protected itself from the sweep.
    def within(name: str) -> bool:
        return any(
            name == entry or name.startswith(entry.rstrip("/") + "/") for entry in normalised
        )

    referenced = "\n".join(
        _referenced_text(name, text) for name, text in contents.items() if within(name)
    )
    loose = [name for name in names if name not in inside and not name.startswith(PROTECTED)]
    return sorted(name for name in loose if not mentioned(name, referenced))


_TEST_IMPORT = re.compile(r"^\s*(?:import|from)\s+.+$", re.MULTILINE)
_TEST_FILE_CALL = re.compile(r"""\b(?:open|Path)\s*\(\s*["']([^"']+)["']""")


def _is_test_file(name: str) -> bool:
    """Whether `name` is a Python test file whose string literals may be test data."""
    if not name.endswith(".py"):
        return False
    file_name = Path(name).name
    return (
        name.startswith("tests/")
        or "/tests/" in name
        or file_name.startswith("test_")
        or file_name.endswith("_test.py")
    )


def _referenced_text(name: str, text: str) -> str:
    """Extract text that can vouch for a loose path.

    Non-test files (production code, configuration) are checked in full.
    Python test files often contain scratch filenames as test data (e.g.
    `tests/test_jobloop.py` listing `"test_output.txt"`), so only actual
    usages — `import`/`from` statements and `open(...)`/`Path(...)` calls —
    are extracted from test files.
    """
    if not _is_test_file(name):
        return text
    parts = _TEST_IMPORT.findall(text) + _TEST_FILE_CALL.findall(text)
    return "\n".join(parts)


# Extensions whose files are referred to without the extension, because the
# language names a module and not a file. Everything else — output, data, notes —
# has to be named in full to count as referenced.
IMPORTABLE = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs")


def mentioned(name: str, text: str) -> bool:
    """Whether `text` refers to `name` by path, by file name or as a module.

    The bare stem counts only for importable sources, because an import names
    the module: `from app.connectors.base import Connector` contains neither
    `backend/app/connectors/base.py` nor `base.py`, and that file is real work.

    For anything else the full file name is required. Accepting the stem there
    protected `attack_pattern.txt` on 2026-11-22 — not because anything read it,
    but because the job's own test happened to contain a function called
    `test_attack_pattern_visible`. A coincidence of naming is not a reference,
    and the job stopped for a file nobody wanted.
    """
    if name in text or Path(name).name in text:
        return True
    stem = Path(name).stem
    return name.lower().endswith(IMPORTABLE) and len(stem) > 2 and stem in text


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


def frontend_gates(
    worktree: Path, names: list[str], *, timeout: float, python: str = ""
) -> list[Gate]:
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
    built: list[Gate] = []
    # Only when the workspace actually has it: a clone taken before this script
    # existed must not fail on a preflight convenience. Real checks still treat
    # "could not run" as a failure; this one is housekeeping, not evidence.
    if python and (worktree / "scripts" / "release_test_ports.py").is_file():
        # Playwright starts its own servers on fixed ports and does not always
        # take them down when a run aborts. One orphan then fails every later
        # frontend job on "port already in use" — a gate that poisons itself.
        built.append(
            run_argv(
                "frontend-free-ports",
                [python, "scripts/release_test_ports.py"],
                cwd=worktree,
                timeout=timeout,
            )
        )
    return built + [
        # Run from `frontend/`, not from the root with `--prefix`: npm does not
        # move the script's working directory, so Playwright wrote its artefacts
        # to a root `test-results/` that `.gitignore` does not cover. The scope
        # gate then reported them as an out-of-scope change and blocked three
        # jobs on 2026-11-17 for files the gate itself had created.
        run_argv(
            f"frontend-{script}",
            [npm, "run", script],
            cwd=worktree / "frontend",
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
        # The job's own changed files, not the whole tree. A full-tree scan
        # failed `T-PH7-201` on 2026-11-22 for a finding in `T-PH7-222`'s
        # recorded report — another job's prose, in a file this attempt never
        # touched, and not a credential at all. CI still scans everything; a
        # gate has to answer "did *this change* introduce a secret".
        #
        # The *controller's* copy of the script, pointed at the worktree with
        # `--root`. The workspace's own copy is whatever base that clone was
        # made from, so fixing the instrument there fixes nothing until the
        # clone moves — and a job editing `scripts/` could change the instrument
        # that judges it.
        gates.append(
            run_argv(
                "secret-scan",
                [
                    python,
                    str(Path(__file__).resolve().parents[1] / "scripts" / "secret_scan.py"),
                    "--root",
                    str(worktree),
                    *sorted(names),
                ],
                cwd=worktree,
                timeout=timeout,
            )
        )
    return gates
