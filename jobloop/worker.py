"""Run one bounded OpenCode session and classify how it ended.

The distinction that matters to the controller is between "this model is out of
usage" (rotate, keep the attempt) and "this model failed the job" (spend an
attempt). Everything else — auth problems, timeouts, a crashed CLI — is reported
as unavailable rather than being guessed into either bucket.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Ending(StrEnum):
    COMPLETED = "completed"
    EXHAUSTED = "exhausted"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"


# Phrases providers use for a spent free allowance. Matched case-insensitively
# against the CLI's own error text only, never against model prose, so a model
# that merely writes "quota" in an answer cannot fake a rotation.
EXHAUSTION_MARKERS = (
    "quota",
    "usage limit",
    "rate limit exceeded",
    "insufficient",
    "credit",
    "billing",
    "payment required",
    "too many requests",
)
AUTH_MARKERS = ("unauthorized", "authentication", "forbidden", "login", "api key")


@dataclass
class Result:
    """What a session produced and how it ended."""

    ending: Ending
    text: str
    model: str
    errors: list[str] = field(default_factory=list)
    tokens: int = 0

    @property
    def rotate(self) -> bool:
        return self.ending is Ending.EXHAUSTED


def classify(errors: list[str]) -> Ending:
    joined = " ".join(errors).lower()
    if any(marker in joined for marker in EXHAUSTION_MARKERS):
        return Ending.EXHAUSTED
    if any(marker in joined for marker in AUTH_MARKERS):
        return Ending.UNAVAILABLE
    return Ending.UNAVAILABLE


def read_stream(stream: str) -> tuple[str, list[str], int]:
    """Collect assistant text, CLI errors and token use from the JSON stream."""
    text: list[str] = []
    errors: list[str] = []
    tokens = 0
    for line in stream.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("{"):
            # A non-JSON line is the CLI talking, which is where failures appear.
            errors.append(line)
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(line)
            continue
        kind = event.get("type")
        raw = event.get("part")
        part: dict[str, object] = raw if isinstance(raw, dict) else {}
        if kind == "text" and isinstance(part.get("text"), str):
            text.append(str(part["text"]))
        elif kind == "error":
            detail = event.get("error") or event.get("message") or ""
            errors.append(json.dumps(detail, ensure_ascii=False))
        elif kind == "step_finish":
            counted = part.get("tokens")
            usage: dict[str, object] = counted if isinstance(counted, dict) else {}
            tokens += int(str(usage.get("input", 0))) + int(str(usage.get("output", 0)))
    return "".join(text), errors, tokens


def run(
    model: str,
    prompt: str,
    *,
    cwd: Path,
    timeout: float,
    executable: str | None = None,
    runner: object | None = None,
) -> Result:
    """Execute one archived, auto-approved session in `cwd`.

    `runner` exists for tests: any callable with subprocess.run's signature.
    """
    binary = executable or shutil.which("opencode")
    if not binary:
        return Result(Ending.UNAVAILABLE, "", model, ["opencode executable not found"])
    # `--standalone` is what makes the worktree the session's working directory.
    # Without it the CLI reuses a background service whose directory is wherever
    # it was first started, and a worker edits the main checkout instead of its
    # own worktree — observed, not theoretical.
    #
    # The brief carries the whole job text, which exceeds the Windows command
    # line limit, so it is piped in rather than passed as an argument.
    command = [
        binary,
        "run",
        "--standalone",
        "--model",
        model,
        "--format",
        "json",
        "--archived",
        "--auto",
    ]
    execute: Any = runner if callable(runner) else subprocess.run
    try:
        completed = execute(  # noqa: S603 — fixed CLI, no shell
            command,
            cwd=str(cwd),
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return Result(Ending.TIMEOUT, "", model, [f"no reply within {timeout:.0f}s"])
    except OSError as error:
        return Result(Ending.UNAVAILABLE, "", model, [str(error)])
    text, errors, tokens = read_stream(completed.stdout or "")
    stderr = (completed.stderr or "").strip()
    if stderr:
        errors.extend(stderr.splitlines())
    if completed.returncode == 0 and text.strip() and not errors:
        return Result(Ending.COMPLETED, text, model, tokens=tokens)
    if completed.returncode == 0 and text.strip():
        # A session that answered and also logged noise still answered.
        return Result(Ending.COMPLETED, text, model, errors=errors, tokens=tokens)
    return Result(classify(errors), text, model, errors=errors or ["empty reply"], tokens=tokens)
