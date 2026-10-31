"""Bounded text proposals; only the Controller may apply source changes."""

from pathlib import Path, PurePosixPath
from typing import Any

from loop_engine.models import Task, check_result
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError, allowed, atomic_text, reject_secrets, within

CONTROL = (
    ".git",
    ".gitattributes",
    ".gitmodules",
    ".lfsconfig",
    ".loop",
    ".agents",
    ".codex",
    ".github",
    "AGENTS.md",
    "CLAUDE.md",
    "CODEX.md",
    "loop_engine",
    "scripts",
    "docs/governance",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
)


def editable(name: str, task: Task) -> bool:
    folded = name.casefold()
    forbidden = {
        ".gitignore",
        ".gitattributes",
        ".gitmodules",
        ".lfsconfig",
        ".codex",
        ".agents",
        ".loop",
        ".github",
        "agents.md",
        "claude.md",
        "codex.md",
        "package.json",
        "package-lock.json",
        "pyproject.toml",
        "conftest.py",
        ".npmrc",
        ".pypirc",
        "eslint.config.js",
        "vite.config.ts",
        "vitest.config.ts",
        "playwright.config.ts",
    }
    if any(
        part in forbidden or part.startswith("tsconfig") for part in PurePosixPath(folded).parts
    ):
        return False
    return (
        allowed(name, task.allowed_paths)
        and not any(
            folded == prefix.casefold() or folded.startswith(prefix.casefold() + "/")
            for prefix in CONTROL
        )
        and not folded.endswith((".lock", "package.json", "requirements.txt"))
    )


def source_bundle(task: Task, workspace: Path) -> dict[str, str]:
    result = ProcessRunner().run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        workspace,
        timeout=15,
    )
    if result.returncode != 0 or result.outcome != "exit":
        raise SafetyError("Source inventory unavailable")
    files = {}
    for name in sorted(set(filter(None, result.stdout.split("\0")))):
        if not allowed(name, task.allowed_paths):
            continue
        path = within(workspace, name)
        if not path.is_file():
            continue
        if path.stat().st_size > 64_000:
            raise SafetyError("Approved source file exceeds model context limit")
        value = path.read_text(encoding="utf-8")
        reject_secrets(value)
        files[name] = value
    if len(files) > 40 or sum(len(value.encode()) for value in files.values()) > 300_000:
        raise SafetyError("Approved source bundle exceeds model context limit")
    return files


def apply_proposal(task: Task, workspace: Path, proposal: dict[str, Any]) -> dict[str, Any]:
    """Validate the entire edit set before writing; no deletions, fuzzy patches or tools."""
    from loop_engine.schemas import validate

    validate("proposal", proposal)
    reject_secrets(proposal)
    result = proposal["result"]
    check_result(task, result)
    pending: dict[Path, str] = {}
    names = []
    for edit in proposal["edits"]:
        name = edit["path"]
        if not editable(name, task) or name in names:
            raise SafetyError("Duplicate or protected proposal path")
        path = within(workspace, name)
        before, after = edit["old"], edit["new"]
        if before is None:
            if path.exists() or not after:
                raise SafetyError("New-file proposal would overwrite existing data")
            if (workspace / ".git").exists():
                visible = ProcessRunner().run(
                    ["git", "check-ignore", "--quiet", "--no-index", "--", name],
                    workspace,
                    timeout=10,
                )
                if visible.outcome != "exit" or visible.returncode != 1:
                    raise SafetyError("New source path is ignored or cannot be inventoried")
            value = after
        else:
            if not path.is_file() or path.stat().st_size > 64_000 or not before or before == after:
                raise SafetyError("Invalid exact source replacement")
            value = path.read_text(encoding="utf-8")
            if value.count(before) != 1:
                raise SafetyError("Source replacement is ambiguous or stale")
            value = value.replace(before, after, 1)
        reject_secrets(value)
        pending[path] = value
        names.append(name)
    if (
        sorted(names) != sorted(result["files_changed"])
        or (result["status"] != "implemented" and names)
        or (result["status"] == "implemented" and not names)
    ):
        raise SafetyError("Proposal edits and result disagree")
    for path, value in pending.items():
        atomic_text(path, value)
    return dict(result)
