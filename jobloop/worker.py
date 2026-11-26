"""Run one bounded OpenCode session and classify how it ended.

The distinction that matters to the controller is between "this model is out of
usage" (rotate, keep the attempt) and "this model failed the job" (spend an
attempt). Everything else — auth problems, timeouts, a crashed CLI — is reported
as unavailable rather than being guessed into either bucket.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Ending(StrEnum):
    COMPLETED = "completed"
    EXHAUSTED = "exhausted"
    OUTAGE = "outage"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    MISROUTED = "misrouted"


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
# The provider did not run the job at all. Measured 2026-11-20 03:08–03:16: the
# free endpoint answered `404 Upstream request failed: Endpoint is unavailable`
# and five jobs went from untouched to `attempts 3/3` in eight minutes, each
# escalated as "three attempts did not satisfy the acceptance criteria". None of
# them had been attempted. An outage is the provider's failure, not the job's.
OUTAGE_MARKERS = (
    "endpoint is unavailable",
    "upstream request failed",
    "server_error",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "connection refused",
    "econnrefused",
    "socket hang up",
    "fetch failed",
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
        """The model never got to the job, so the attempt must survive."""
        return self.ending in {Ending.EXHAUSTED, Ending.OUTAGE, Ending.MISROUTED}

    @property
    def why_rotate(self) -> str:
        if self.ending is Ending.EXHAUSTED:
            return "is out of usage"
        if self.ending is Ending.MISROUTED:
            return "was routed to the wrong working directory"
        return "endpoint is unavailable"


def classify(errors: list[str]) -> Ending:
    joined = " ".join(errors).lower()
    if any(marker in joined for marker in EXHAUSTION_MARKERS):
        return Ending.EXHAUSTED
    if any(marker in joined for marker in OUTAGE_MARKERS):
        return Ending.OUTAGE
    if any(marker in joined for marker in AUTH_MARKERS):
        return Ending.UNAVAILABLE
    return Ending.UNAVAILABLE


def _expand_short_name(path: str) -> str:
    """Expand a Windows 8.3 short name to its long form where possible.

    Returns `path` unchanged on non-Windows systems, when the path does not
    exist, or when the OS cannot resolve it. Only directory metadata is read.
    """
    if sys.platform != "win32" or not path:
        return path
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetLongPathNameW(path, buf, len(buf))
        if 0 < length < len(buf):
            return buf.value
    except (OSError, AttributeError, ValueError):
        pass
    return path


def normalize_session_path(path: str) -> str:
    """Normalise a session-reported directory for comparison.

    Case, separators, `.`/`..`, and Windows 8.3 short names are folded so that
    two spellings of the same location compare equal, and only a genuinely
    different location is treated as a misroute.
    """
    if not path:
        return ""
    expanded = _expand_short_name(path)
    return os.path.normcase(os.path.normpath(os.path.abspath(expanded)))


def _same_directory(left: str, right: str) -> bool:
    """Whether two paths name the same directory, normalising Windows spelling.

    A worker that reports `C:\repo` and one that reports `C:/repo` are in the
    same place; a worker that reports a different checkout is not. Normalising
    case and separators covers (a) and (b); `realpath` resolves short names and
    symlinks where the filesystem can answer, and the normalised comparison
    still holds when it cannot.
    """
    if not left or not right:
        return False

    if normalize_session_path(left) == normalize_session_path(right):
        return True
    try:
        left_real = normalize_session_path(os.path.realpath(_expand_short_name(left)))
        right_real = normalize_session_path(os.path.realpath(_expand_short_name(right)))
        return left_real == right_real
    except OSError:
        return False


def reported_directory(stream: str) -> str | None:
    """The working directory a session reported, if any event carried one.

    OpenCode's `--format json` stream is the only evidence we have before the
    controller inspects the worktree. `agy` reports its worktree in an init
    event; OpenCode may report a directory on session/init-shaped events. A
    failed probe on 2026-11-26 produced only `type:error` with no directory, so
    absence is reported as None rather than guessed. The scan is defensive:
    any event that carries a directory/cwd/workdir string is considered.
    """
    for line in stream.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        found = _directory_from_event(event)
        if found:
            return found
    return None


_SESSION_CWD_TYPES = {
    "session.created",
    "session.updated",
    "session.init",
    "init",
}


def _directory_from_event(event: dict[str, Any]) -> str | None:
    """Pull a working-directory string out of one JSON event, wherever it sits."""
    kind = event.get("type")
    if isinstance(kind, str) and kind.strip() and kind not in _SESSION_CWD_TYPES:
        return None
    for key in ("directory", "cwd", "workdir"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for container_key in ("part", "session", "properties", "info"):
        raw = event.get(container_key)
        if not isinstance(raw, dict):
            continue
        for key in ("directory", "cwd", "workdir"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        # One level deeper covers shapes like properties.session.directory.
        for nested_key in ("session", "info", "part"):
            nested = raw.get(nested_key)
            if not isinstance(nested, dict):
                continue
            for key in ("directory", "cwd", "workdir"):
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return None


# Alias for the escaped attempt's naming; same behaviour.
_session_directory_from_event = _directory_from_event


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


def kill_tree(process: subprocess.Popen[str]) -> None:
    """Kill the session and everything it started.

    `opencode run` is a launcher: it spawns `opencode serve --stdio`, which spawns
    the tools. Killing only the direct child leaves that subtree running, and it
    keeps the inherited stdout handle open — so the parent's own drain never
    returns. Measured on 2026-11-20: `T-PH7-211`'s session timed out at 23:44,
    its seven surviving processes went on writing scratch files into the
    workspace until 00:06, and the controller sat wedged behind the pipe for
    twenty-five minutes with the supervisor reporting nothing at all.
    """
    if sys.platform == "win32":
        root = os.environ.get("SystemRoot", r"C:\Windows")
        subprocess.run(  # noqa: S603 — fixed OS utility, no shell
            [rf"{root}\System32\taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            timeout=60,
        )
    else:
        with suppress(OSError):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    with suppress(OSError):
        process.kill()


def bounded(
    command: list[str],
    *,
    cwd: str,
    input: str,  # noqa: A002 — mirrors subprocess.run's signature for `runner`
    timeout: float,
    **options: Any,
) -> subprocess.CompletedProcess[str]:
    """`subprocess.run`, except a timeout takes the whole process tree with it.

    Raises `subprocess.TimeoutExpired`, like the call it replaces.
    """
    options.pop("capture_output", None)
    creation = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    process = subprocess.Popen(  # noqa: S603 — fixed CLI, no shell
        command,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creation,
        start_new_session=sys.platform != "win32",
        **options,
    )
    try:
        out, err = process.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(process)
        # The handles are closed now, so this drain cannot block for long; a
        # second expiry is still possible and still means the same thing.
        with suppress(subprocess.TimeoutExpired):
            process.communicate(timeout=30)
        raise
    return subprocess.CompletedProcess(command, process.returncode, out, err)


AGY_PREFIX = "agy/"


def read_agy_result(stream: str) -> tuple[str, list[str], int, str]:
    """Collect the answer, errors, token use and status from agy's NDJSON stream.

    agy's shape is simpler than OpenCode's: the last `{"event":"result"}` line
    carries the whole answer, a status and the usage. Measured 2026-11-25 against
    `agy --model gemini-4-hydrogen-low --input-format stream-json
    --output-format stream-json --print=''`.
    """
    text = ""
    errors: list[str] = []
    tokens = 0
    status = ""
    for line in stream.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("{"):
            # The CLI talking, which is where its own failures appear.
            errors.append(line)
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(line)
            continue
        if event.get("event") != "result":
            continue
        raw = event.get("result")
        result: dict[str, Any] = raw if isinstance(raw, dict) else {}
        status = str(result.get("status", ""))
        if isinstance(result.get("response"), str):
            text = str(result["response"])
        failure = result.get("error")
        if isinstance(failure, str) and failure.strip():
            errors.append(failure)
        counted = result.get("usage")
        usage: dict[str, Any] = counted if isinstance(counted, dict) else {}
        tokens = int(str(usage.get("total_tokens", 0) or 0))
    return text, errors, tokens, status


def run_agy(
    model: str,
    prompt: str,
    *,
    cwd: Path,
    timeout: float,
    executable: str | None = None,
    runner: object | None = None,
) -> Result:
    """Run one bounded agy session in `cwd` (second tier; owner decision E2).

    Two things differ from OpenCode and both were measured, not assumed:
    `--print` *requires* its prompt as the flag's own argument, so a brief that
    exceeds the Windows command line has to arrive on stdin — which means
    `--print=''` plus `--input-format stream-json`, one NDJSON message. And agy
    takes the process's working directory, so there is no `--standalone`
    equivalent to forget: the session's `init` event reported the worktree.
    """
    binary = executable or shutil.which("agy")
    if not binary:
        return Result(Ending.UNAVAILABLE, "", model, ["agy executable not found"])
    command = [
        binary,
        "--model",
        model.removeprefix(AGY_PREFIX),
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--dangerously-skip-permissions",
        "--disable-slash-commands",
        "--print=",
    ]
    message = json.dumps(
        {
            "event": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
        },
        ensure_ascii=False,
    )
    execute: Any = runner if callable(runner) else bounded
    try:
        completed = execute(  # noqa: S603 — fixed CLI, no shell
            command,
            cwd=str(cwd),
            input=message + "\n",
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
    text, errors, tokens, status = read_agy_result(completed.stdout or "")
    stderr = (completed.stderr or "").strip()
    if stderr:
        errors.extend(stderr.splitlines())
    if status == "SUCCESS" and text.strip():
        # A session that answered and also logged noise still answered.
        return Result(Ending.COMPLETED, text, model, errors=errors, tokens=tokens)
    return Result(classify(errors), text, model, errors=errors or ["empty reply"], tokens=tokens)


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
    if model.startswith(AGY_PREFIX):
        return run_agy(
            model, prompt, cwd=cwd, timeout=timeout, executable=executable, runner=runner
        )
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
    execute: Any = runner if callable(runner) else bounded
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
    reported = reported_directory(completed.stdout or "")
    if reported and not _same_directory(reported, str(cwd)):
        return Result(
            Ending.MISROUTED,
            text,
            model,
            errors=errors
            + [f"session reported working directory {reported!r}, expected {str(cwd)!r}"],
            tokens=tokens,
        )
    if completed.returncode == 0 and text.strip() and not errors:
        return Result(Ending.COMPLETED, text, model, tokens=tokens)
    if completed.returncode == 0 and text.strip():
        # A session that answered and also logged noise still answered.
        return Result(Ending.COMPLETED, text, model, errors=errors, tokens=tokens)
    return Result(classify(errors), text, model, errors=errors or ["empty reply"], tokens=tokens)
