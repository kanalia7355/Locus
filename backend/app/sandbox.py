# ruff: noqa: S603, S108
"""Child-process and Docker execution boundary for document extraction.

Runs extractors in an isolated child process with real-time and output-byte
limits, a stripped environment, and explicit guarantee tracking. The extractor
code is never imported into the backend process.

The subprocess path does NOT claim network isolation or memory/pids limits on
Windows (where ``resource`` is unavailable). The Docker path is opt-in and only
claims strong containment when a Docker container actually ran and reported an
extractor exit code; on hosts without a reachable Docker daemon, Docker
containment is unverified and falls back to subprocess guarantees
(DOCUMENT_EXTRACTION_BOUNDARY.md §5).
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from contextlib import suppress
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Guarantee tracking – what the boundary actually promises
# ---------------------------------------------------------------------------

SUBPROCESS_GUARANTEES: dict[str, str] = {
    "wall_time": "verified",
    "output_bytes": "verified",
    "env_stripped": "verified",
    "network": "unverified",
    "memory": "unverified",
    "cpu": "unverified",
    "write_out_of_tmp": "△",
}

DOCKER_GUARANTEES: dict[str, str] = {
    "wall_time": "verified",
    "output_bytes": "verified",
    "env_stripped": "verified",
    "network": "strong",
    "memory": "strong",
    "cpu": "strong",
    "write_out_of_tmp": "strong",
}

# ---------------------------------------------------------------------------
# Minimal environment passed to the extractor subprocess
# ---------------------------------------------------------------------------

# Allowlist only: do not pass the full parent environment to extractors.
# PATH is needed to locate the Python interpreter; SYSTEMROOT/COMSPEC/PATHEXT
# are the minimum Windows requires for a child python process to start and
# resolve DLLs. The UTF-8 variables matter: without them a child launched from
# a UTF-8-mode parent falls back to the Windows code page and corrupts text.
_MINIMAL_ENV_KEYS: tuple[str, ...] = (
    "PATH",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
)

# Docker CLI connection environment variables (separate from the extractor env
# inside the container). Preserving these lets the host docker client reach a
# daemon configured via DOCKER_HOST / TLS / DOCKER_CONFIG without leaking the
# full parent environment into either the CLI or the container.
_DOCKER_CLIENT_ENV_KEYS: tuple[str, ...] = (
    "PATH",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "HOME",
    "USERPROFILE",
    "DOCKER_HOST",
    "DOCKER_CERT_PATH",
    "DOCKER_TLS_VERIFY",
    "DOCKER_CONFIG",
    "DOCKER_CONTEXT",
)

# Explicit container image and interpreter contract: the image must provide the
# paired Python interpreter on its container PATH. Never pass host sys.executable.
DEFAULT_DOCKER_IMAGE: str = "python:3.13-slim"
DEFAULT_DOCKER_INTERPRETER: str = "python3"
DOCKER_CLIENT_FAILURE_EXIT_CODES: frozenset[int] = frozenset({125, 126, 127})


def _make_minimal_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key in _MINIMAL_ENV_KEYS:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _make_docker_client_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key in _DOCKER_CLIENT_ENV_KEYS:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    return env


# ---------------------------------------------------------------------------
# SandboxResult – result from running an extractor inside the sandbox
# ---------------------------------------------------------------------------


@dataclass
class SandboxResult:
    success: bool
    content: str | None
    sandbox: str  # "docker" or "subprocess"
    guarantees: dict[str, str]
    exit_code: int | None
    error_message: str | None
    bytes_read: int | None = None


@dataclass
class _Outcome:
    """Raw process outcome before it is interpreted as a sandbox result."""

    exit_code: int | None
    stdout: str
    stderr: str
    bytes_read: int = 0
    exceeded: bool = False
    timed_out: bool = False
    spawn_failed: bool = False


# ---------------------------------------------------------------------------
# Process execution with a streamed output budget
# ---------------------------------------------------------------------------


def _terminate(process: subprocess.Popen[bytes]) -> None:
    """Kill the child process and its entire descendant tree."""
    if sys.platform == "win32":
        root = os.environ.get("SystemRoot", r"C:\Windows")
        with suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                [rf"{root}\System32\taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
                timeout=10,
            )
    else:
        with suppress(OSError, ProcessLookupError):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    with suppress(OSError, ValueError):
        process.kill()


def _run_process(
    command: list[str],
    stdin_data: bytes,
    *,
    timeout: float,
    output_limit: int,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> _Outcome:
    """Run one bounded child, cutting stdout/stderr at ``output_limit``.

    Reading is incremental: an extractor that writes forever is killed when the
    budget runs out instead of filling the parent's memory first.
    """
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            creationflags=creationflags,
            start_new_session=sys.platform != "win32",
        )
    except OSError:
        return _Outcome(None, "", "", spawn_failed=True)

    budget = [output_limit]
    total_read = [0]
    lock = threading.Lock()
    exceeded = threading.Event()
    stdout = bytearray()
    stderr = bytearray()
    chunk_size = max(1, min(65536, output_limit))

    def consume(stream: object, sink: bytearray) -> None:
        assert hasattr(stream, "read")
        try:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    return
                should_kill = False
                with lock:
                    total_read[0] += len(chunk)
                    allowed = min(len(chunk), budget[0])
                    sink.extend(chunk[:allowed])
                    budget[0] -= allowed
                    if allowed < len(chunk) and not exceeded.is_set():
                        exceeded.set()
                        should_kill = True
                if should_kill:
                    _terminate(process)
                    return
                if exceeded.is_set():
                    return
        except (OSError, ValueError):
            return

    def write_stdin() -> None:
        assert process.stdin is not None
        with suppress(OSError, ValueError):
            process.stdin.write(stdin_data)
            process.stdin.flush()
        with suppress(OSError, ValueError):
            process.stdin.close()

    readers = [
        threading.Thread(target=consume, args=(process.stdout, stdout), daemon=True),
        threading.Thread(target=consume, args=(process.stderr, stderr), daemon=True),
        threading.Thread(target=write_stdin, daemon=True),
    ]
    for reader in readers:
        reader.start()

    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate(process)
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)

    for reader in readers:
        reader.join(timeout=5)
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            with suppress(OSError, ValueError):
                stream.close()

    return _Outcome(
        exit_code=process.returncode,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        bytes_read=total_read[0],
        exceeded=exceeded.is_set(),
        timed_out=timed_out,
    )


def _interpret(outcome: _Outcome, sandbox: str, guarantees: dict[str, str]) -> SandboxResult:
    base = dict(guarantees)
    if outcome.spawn_failed:
        return SandboxResult(
            success=False,
            content=None,
            sandbox=sandbox,
            guarantees=base,
            exit_code=None,
            error_message="解析環境を起動できませんでした",
            bytes_read=outcome.bytes_read,
        )
    if outcome.timed_out:
        return SandboxResult(
            success=False,
            content=None,
            sandbox=sandbox,
            guarantees={**base, "wall_time": "timed_out"},
            exit_code=-1,
            error_message="実時間上限超過",
            bytes_read=outcome.bytes_read,
        )

    base["wall_time"] = "verified"
    base["output_bytes"] = "truncated" if outcome.exceeded else "verified"

    body_missing = False
    if outcome.exit_code == 0 and not outcome.exceeded:
        try:
            parsed = json.loads(outcome.stdout)
            body = parsed.get("body") if isinstance(parsed, dict) else None
        except (TypeError, ValueError):
            body = None
        if body is None or body == "":
            body_missing = True

    candidates: list[str] = []
    if outcome.exceeded:
        candidates.append("出力バイト数上限超過")
    if outcome.exit_code is not None and outcome.exit_code < 0:
        candidates.append(f"シグナル終了 ({-outcome.exit_code})")
    elif outcome.exit_code not in (0, None) and not outcome.exceeded:
        candidates.append(f"異常終了 (exit_code={outcome.exit_code})")
    if body_missing:
        candidates.append("抽出本文が空です")

    success = outcome.exit_code == 0 and not outcome.exceeded and not body_missing
    return SandboxResult(
        success=success,
        content=outcome.stdout if success else None,
        sandbox=sandbox,
        guarantees=base,
        exit_code=outcome.exit_code,
        error_message="; ".join(candidates)[:200] if candidates else None,
        bytes_read=outcome.bytes_read,
    )


# ---------------------------------------------------------------------------
# _run_subscript – run a script in a child Python process with limits.
# ---------------------------------------------------------------------------


def _run_subscript(
    script: str,
    *,
    timeout: float = 30.0,
    output_limit: int = 8 * 1024 * 1024,
    cwd: str | None = None,
    content: str | None = None,
) -> SandboxResult:
    environment = _make_minimal_env()
    with tempfile.TemporaryDirectory(prefix="locus-extract-") as workdir:
        environment.setdefault("TEMP", workdir)
        environment.setdefault("TMP", workdir)
        outcome = _run_process(
            [sys.executable, "-c", script],
            (content or "").encode("utf-8"),
            timeout=timeout,
            output_limit=output_limit,
            cwd=cwd or workdir,
            env=environment,
        )
    return _interpret(outcome, "subprocess", SUBPROCESS_GUARANTEES)


# ---------------------------------------------------------------------------
# _run_docker – opt-in Docker path (unverified when no Docker engine runs).
# ---------------------------------------------------------------------------


def _docker_argv(
    image: str = DEFAULT_DOCKER_IMAGE,
    interpreter: str = DEFAULT_DOCKER_INTERPRETER,
    script: str = "",
) -> list[str]:
    """Build the container argv without host paths or starting a Docker engine.

    Uses ``docker`` by program name (resolved via ``PATH`` in the client env so
    no host absolute path enters ``argv``), ``-i`` so stdin reaches the
    extractor, ``--user 1000:1000`` for non-root execution, and
    ``--entrypoint <interpreter>`` so an image supervisor ENTRYPOINT cannot
    intercept or swallow the interpreter argument.
    """
    if not image or not interpreter:
        raise ValueError("image and interpreter must be non-empty")
    return [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "1024",
        "--memory=512m",
        "--cpus=1",
        "--tmpfs",
        "/tmp:exec",
        "--user",
        "1000:1000",
        "--entrypoint",
        interpreter,
        "--env",
        "PYTHONUNBUFFERED=1",
        "--env",
        "PYTHONIOENCODING=utf-8",
        "--env",
        "PYTHONUTF8=1",
        image,
        "-c",
        script,
    ]


def _docker_daemon_available(client_env: dict[str, str], timeout: float = 5.0) -> bool:
    """Return True only when the Docker CLI and reachable daemon both respond."""
    if shutil.which("docker") is None:
        return False
    probe = _run_process(
        ["docker", "info"],
        b"",
        timeout=min(timeout, 5.0),
        output_limit=65536,
        env=client_env,
    )
    return not probe.spawn_failed and not probe.timed_out and probe.exit_code == 0


def _run_docker(
    script: str,
    *,
    timeout: float = 30.0,
    output_limit: int = 8 * 1024 * 1024,
    image: str = DEFAULT_DOCKER_IMAGE,
    interpreter: str = DEFAULT_DOCKER_INTERPRETER,
    content: str | None = None,
) -> SandboxResult:
    client_env = _make_docker_client_env()
    if not _docker_daemon_available(client_env, timeout=timeout):
        return _run_subscript(
            script,
            timeout=timeout,
            output_limit=output_limit,
            content=content,
        )
    cmd = _docker_argv(image, interpreter, script)
    outcome = _run_process(
        cmd,
        (content or "").encode("utf-8"),
        timeout=timeout,
        output_limit=output_limit,
        env=client_env,
    )
    # Only claim DOCKER_GUARANTEES (strong) when the container actually ran and
    # returned a real process exit code (not spawn failure or docker CLI/daemon
    # invocation errors 125/126/127).
    container_ran = (
        not outcome.spawn_failed
        and outcome.exit_code is not None
        and outcome.exit_code not in DOCKER_CLIENT_FAILURE_EXIT_CODES
    )
    if not container_ran:
        return _interpret(outcome, "subprocess", SUBPROCESS_GUARANTEES)
    return _interpret(outcome, "docker", DOCKER_GUARANTEES)


# ---------------------------------------------------------------------------
# Extractor source code – never imported by the main process.
# These are tiny scripts that receive content on stdin and write JSON to stdout.
# ---------------------------------------------------------------------------

PLAINTEXT_EXTRACTOR_SOURCE: str = """\
import sys, json
content = sys.stdin.read()
body = content if content else None
print(json.dumps({"body": body}), flush=True)
"""

EXTRACTOR_SOURCE: dict[str, str] = {
    "plaintext": PLAINTEXT_EXTRACTOR_SOURCE,
    "infinite_loop": """\
import sys, json
# Synthetic infinite-loop extractor – will be killed by timeout.
# It never returns cleanly, so the pipeline quarantines it.
content = sys.stdin.read()
body = content if content else None
print(json.dumps({"body": body}), flush=True)
while True:
    pass
""",
    "output_flood": """\
import sys, json
# Synthetic output-flood extractor – writes unbounded stdout,
# triggering the output-byte limit cutoff and quarantine.
content = sys.stdin.read()
body = content if content else None
# Write a large amount of data to exceed output_limit
extra = "z" * (25 * 1024 * 1024)  # 25 MiB extra output
sys.stdout.write(extra)
sys.stdout.flush()
print(json.dumps({"body": body}), flush=True)
""",
    "env_reader": """\
import sys, json, os
# Synthetic extractor that reads a specific environment variable.
# Used to verify that parent env vars do not leak into extraction output.
env_key = "EXTRACTED_VAR"
env_value = os.environ.get(env_key, "(not set)")
# Put the observed value in body so a leak is observable through the normal
# extraction result channel (and not masked by null-body failure handling).
body = env_value
print(json.dumps({"body": body}), flush=True)
""",
}


# ---------------------------------------------------------------------------
# _resolve_extractor – look up extractor source by format name.
# This is safe to import from the main process because it only reads a
# module-level constant dict; it never imports a parser library.
# ---------------------------------------------------------------------------


def _resolve_extractor(format_name: str) -> str | None:
    """Return the extractor source code string for a given format name, or None."""
    return EXTRACTOR_SOURCE.get(format_name)


# ---------------------------------------------------------------------------
# _build_extractor_script – construct a runnable Python script from source.
# ---------------------------------------------------------------------------


def _build_extractor_script(source: str, content: str) -> str:
    # The source code already reads from stdin and outputs JSON.
    # We just pass the source through; the subprocess will execute it.
    # The source (e.g. PLAINTEXT_EXTRACTOR_SOURCE) already handles stdin.
    return source


# ---------------------------------------------------------------------------
# extract_with_sandbox – high-level entrypoint.
# ---------------------------------------------------------------------------


def extract_with_sandbox(
    format_name: str,
    content: str,
    *,
    timeout: float = 30.0,
    output_limit: int = 8 * 1024 * 1024,
    use_docker: bool = False,
    docker_image: str = DEFAULT_DOCKER_IMAGE,
    docker_interpreter: str = DEFAULT_DOCKER_INTERPRETER,
) -> SandboxResult:
    """Resolve format → extractor source → run in sandbox.

    Returns a SandboxResult whose .content holds the extractor JSON output (or
    None on failure) and .guarantees tells the operator what containment was
    actually provided. Strong Docker guarantees are reported only when a Docker
    container actually executed and returned an exit code.
    """
    source = _resolve_extractor(format_name)
    if source is None:
        return SandboxResult(
            success=False,
            content=None,
            sandbox="subprocess",
            guarantees=dict(SUBPROCESS_GUARANTEES),
            exit_code=1,
            error_message="サポートされていない形式です",
        )

    script = _build_extractor_script(source, content)
    if use_docker:
        return _run_docker(
            script,
            timeout=timeout,
            output_limit=output_limit,
            image=docker_image,
            interpreter=docker_interpreter,
            content=content,
        )
    return _run_subscript(script, timeout=timeout, output_limit=output_limit, content=content)
