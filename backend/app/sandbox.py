# ruff: noqa: S603, S108
"""Child-process and Docker execution boundary for document extraction.

Runs extractors in an isolated subprocess with real-time and output-byte limits,
a stripped environment, and guarantees tracking.  The subprocess path does NOT
claim network isolation, memory/pids limits on Windows (where `resource` is
unavailable).  The Docker path provides strong guarantees and is opt-in.

Key invariants (design DOCUMENT_EXTRACTION_BOUNDARY.md §5):
- Subprocess guarantees are weak on Windows (no resource module, no cgroups).
- Docker guarantees are strong but opt-in; CI defaults to subprocess.
- Records which backend was used so operators can see sandbox: docker / subprocess.
- Never claim network isolation from subprocess.
"""

import json
import os
import subprocess
import sys
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
# resolve DLLs; PYTHONUNBUFFERED ensures output is flushed promptly.
_MINIMAL_ENV_KEYS: tuple[str, ...] = (
    "PATH",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "PYTHONUNBUFFERED",
)


def _make_minimal_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key in _MINIMAL_ENV_KEYS:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env["PYTHONUNBUFFERED"] = "1"
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
    begin = __import__("time").time()
    stdin_data = content or ""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_make_minimal_env(),
            cwd=cwd,
        )
        exit_code = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        all_output = stdout + stderr
        output_bytes = len(all_output.encode("utf-8"))
        _ = __import__("time").time() - begin

        if output_bytes > output_limit:
            all_output = all_output[:output_limit] + "\n..."
            exit_code = 1

        guarantees = dict(SUBPROCESS_GUARANTEES)
        guarantees["wall_time"] = "verified"
        guarantees["output_bytes"] = "verified" if output_bytes <= output_limit else "truncated"
        guarantees["env_stripped"] = "verified"

        guarantees["memory"] = "unverified"
        guarantees["cpu"] = "unverified"

        guarantees["network"] = "unverified"

        error_message = None
        body_missing = False
        if exit_code == 0 and output_bytes <= output_limit:
            try:
                parsed = json.loads(stdout)
                body = parsed.get("body") if isinstance(parsed, dict) else None
            except Exception:
                body = None
            if body is None or body == "":
                body_missing = True

        if exit_code != 0 or body_missing:
            cands = []
            if output_bytes > output_limit:
                cands.append("出力バイト数上限超過")
            if body_missing and output_bytes <= output_limit and exit_code == 0:
                cands.append("抽出本文が空です")
            if exit_code < 0:
                cands.append(f"シグナル終了 ({-exit_code})")
            elif exit_code != 0:
                cands.append(f"異常終了 (exit_code={exit_code})")
            error_message = "; ".join(cands)[:200] if cands else "抽出本文が空です"

        success = exit_code == 0 and output_bytes <= output_limit and not body_missing
        return SandboxResult(
            success=success,
            content=stdout if success else None,
            sandbox="subprocess",
            guarantees=guarantees,
            exit_code=exit_code,
            error_message=error_message,
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(
            success=False,
            content=None,
            sandbox="subprocess",
            guarantees={**SUBPROCESS_GUARANTEES, "wall_time": "timed_out"},
            exit_code=-1,
            error_message="実時間上限超過",
        )


# ---------------------------------------------------------------------------
# _run_docker – opt-in strong guarantees.
# ---------------------------------------------------------------------------


def _run_docker(
    script: str,
    *,
    timeout: float = 30.0,
    output_limit: int = 8 * 1024 * 1024,
    image: str = "ubuntu:22.04",
    content: str | None = None,
) -> SandboxResult:
    stdin_data = content or ""
    # Docker contract: the target image must provide `python3` on PATH.
    # We intentionally do not pass the host sys.executable path into the
    # container because that absolute host path does not exist in the image.
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "1024",
        f"--memory={512 * 1024 * 1024}",
        f"--cpus={1.0}",
        "--tmpfs",
        "/tmp:exec",
        "--user",
        "1000:1000",
        image,
        "python3",
        "-c",
        script,
    ]
    begin = __import__("time").time()
    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_make_minimal_env(),
        )
        exit_code = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        all_output = stdout + stderr
        output_bytes = len(all_output.encode("utf-8"))
        _ = __import__("time").time() - begin

        if output_bytes > output_limit:
            all_output = all_output[:output_limit] + "\n..."
            exit_code = 1

        guarantees = dict(DOCKER_GUARANTEES)
        guarantees["wall_time"] = "verified"
        guarantees["output_bytes"] = "verified" if output_bytes <= output_limit else "truncated"

        error_message = None
        body_missing = False
        if exit_code == 0 and output_bytes <= output_limit:
            try:
                parsed = json.loads(stdout)
                body = parsed.get("body") if isinstance(parsed, dict) else None
            except Exception:
                body = None
            if body is None or body == "":
                body_missing = True

        if exit_code != 0 or body_missing:
            cands = []
            if output_bytes > output_limit:
                cands.append("出力バイト数上限超過")
            if body_missing and output_bytes <= output_limit and exit_code == 0:
                cands.append("抽出本文が空です")
            if exit_code < 0:
                cands.append(f"シグナル終了 ({-exit_code})")
            elif exit_code != 0:
                cands.append(f"異常終了 (exit_code={exit_code})")
            error_message = "; ".join(cands)[:200] if cands else "抽出本文が空です"

        success = exit_code == 0 and output_bytes <= output_limit and not body_missing
        return SandboxResult(
            success=success,
            content=stdout if success else None,
            sandbox="docker",
            guarantees=guarantees,
            exit_code=exit_code,
            error_message=error_message,
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(
            success=False,
            content=None,
            sandbox="docker",
            guarantees={**DOCKER_GUARANTEES, "wall_time": "timed_out"},
            exit_code=-1,
            error_message="実時間上限超過",
        )
    except FileNotFoundError:
        return _run_subscript(
            script,
            timeout=timeout,
            output_limit=output_limit,
            content=content,
        )


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
) -> SandboxResult:
    """Resolve format → extractor source → run in sandbox.

    Returns a SandboxResult whose .content holds the extracted body (or None on
    failure) and .guarantees tells the operator what containment was provided.
    """
    source = _resolve_extractor(format_name)
    if source is None:
        backend = "docker" if use_docker else "subprocess"
        gua = dict(DOCKER_GUARANTEES) if use_docker else dict(SUBPROCESS_GUARANTEES)
        return SandboxResult(
            success=False,
            content=None,
            sandbox=backend,
            guarantees={**gua, "network": "unverified" if not use_docker else "strong"},
            exit_code=1,
            error_message="サポートされていない形式です",
        )

    script = _build_extractor_script(source, content)
    if use_docker:
        return _run_docker(script, timeout=timeout, output_limit=output_limit, content=content)
    else:
        return _run_subscript(script, timeout=timeout, output_limit=output_limit, content=content)
