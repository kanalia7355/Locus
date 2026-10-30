"""Fail-closed paths, snapshots, secret guards and restrictive subprocess environments."""

import fnmatch
import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any

PROTECTED = (
    ".git",
    ".loop",
    ".agents",
    ".codex",
    ".github",
    "AGENTS.md",
    "CLAUDE.md",
    "scripts/verify.py",
    "pyproject.toml",
)
SENSITIVE = (".env", "storage", "uploads", "auth.json", "credentials", "id_rsa", "id_ed25519")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
    ),
    re.compile(r"(?i)(?:password|secret|api[_-]?key|access[_-]?token)\s*[=:]\s*['\"]?[^\s'\"]{8,}"),
)


class SafetyError(ValueError):
    pass


def reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(
            getattr(path.lstat(), "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
        )
    except FileNotFoundError:
        return False


def reject_secrets(value: Any) -> None:
    data = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if any(pattern.search(data) for pattern in SECRET_PATTERNS):
        raise SafetyError("Potential credential content rejected; value was not logged")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def relative_path(value: str) -> str:
    if not value or "\\" in value or "\x00" in value or ":" in value:
        raise SafetyError("Unsafe relative path")
    path = PurePosixPath(value)
    reserved = {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
    if (
        path.is_absolute()
        or not path.parts
        or any(
            part.casefold() in {"..", ".git"}
            or part.endswith((".", " "))
            or part.split(".")[0].casefold() in reserved
            for part in path.parts
        )
    ):
        raise SafetyError("Unsafe relative path")
    if str(path) != value or any(ord(char) < 32 for char in value):
        raise SafetyError("Non-canonical relative path")
    return value


def within(root: Path, relative: str) -> Path:
    relative_path(relative)
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise SafetyError("Path escapes project boundary")
    current = path
    while current != root:
        if reparse(current):
            raise SafetyError("Symlink paths are not allowed")
        current = current.parent
    return path


def protected(path: str) -> bool:
    relative_path(path)
    path = path.casefold()
    parts = PurePosixPath(path).parts
    return any(
        path == item.casefold() or path.startswith(item.casefold() + "/") for item in PROTECTED
    ) or ("tests" in parts or path.endswith((".lock", "package.json", "requirements.txt")))


def sensitive(path: str) -> bool:
    parts = PurePosixPath(path.casefold()).parts
    return any(part in SENSITIVE or part.startswith(".env.") for part in parts)


def allowed(path: str, scopes: list[str]) -> bool:
    relative_path(path)
    return not sensitive(path) and any(
        path == scope
        or path.startswith(scope.rstrip("/") + "/")
        or fnmatch.fnmatchcase(path, scope)
        for scope in scopes
    )


def safe_environment(*, model: bool = False) -> dict[str, str]:
    keep = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "LANG",
        "LC_ALL",
    }
    if model:
        keep.add("CODEX_HOME")
    result = {key: value for key, value in os.environ.items() if key.upper() in keep}
    result.update({"PYTHONUTF8": "1", "GIT_TERMINAL_PROMPT": "0", "GH_PROMPT_DISABLED": "1"})
    return result


def atomic_text(path: Path, data: str) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise SafetyError("Refusing to write through symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def create_text(path: Path, data: str) -> bool:
    """Exclusive initialization: never replace a concurrently created user file."""
    if reparse(path) or reparse(path.parent):
        raise SafetyError("Refusing initialization through a reparse point")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return True
    except FileExistsError:
        return False
