"""Synthetic extractor boundary tests for DATA-006 (T-PH6-104).

These tests verify that document extraction via the sandbox child process
respectes isolation guarantees.  They use only synthetic (harmless) extractors
and synthetic file content — no real PDF/Office/OCR libraries, no real
malware, no real credentials.

See DOCUMENT_EXTRACTION_BOUNDARY.md §8 for the full acceptance criteria.
"""

import json
import os
import time

import app.sandbox

# ---------------------------------------------------------------------------
# Synthetic extractor source code strings keyed by test format name.
# ---------------------------------------------------------------------------

INFINITE_LOOP_SOURCE = """\
import sys, json
# Synthetic infinite-loop extractor – will be killed by timeout.
content = sys.stdin.read()
body = content if content else None
print(json.dumps({"body": body}), flush=True)
while True:
    pass
"""

OUTPUT_FLOOD_SOURCE = """\
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
"""

ENV_READER_SOURCE = """\
import sys, json, os
# Synthetic extractor that reads a specific environment variable.
# Used to verify that parent env vars do not leak into extraction output.
env_key = "EXTRACTED_VAR"
env_value = os.environ.get(env_key, "(not set)")
# Put the observed value in body so a leak is observable through the normal
# extraction result channel (and not masked by null-body failure handling).
body = env_value
print(json.dumps({"body": body}), flush=True)
"""

PLAINTEXT_SOURCE = """\
import sys, json
content = sys.stdin.read()
body = content if content else None
print(json.dumps({"body": body}), flush=True)
"""

STDERR_DIAGNOSTIC_SOURCE = """\
import sys, json
sys.stderr.write("diagnostic: synthetic stderr line\\n")
sys.stderr.flush()
content = sys.stdin.read()
body = content if content else None
print(json.dumps({"body": body}), flush=True)
"""

# ---------------------------------------------------------------------------
# Helper: run an extractor script directly in the sandbox subprocess.
# ---------------------------------------------------------------------------


def _run_extractor_direct(
    source: str,
    content: str = "",
    timeout: float = 30.0,
    output_limit: int = 8 * 1024 * 1024,
    set_env: dict | None = None,
) -> tuple:
    """Run *source* as an extractor in a child Python process and return
    (success, content, guarantees, exit_code, error_message, sandbox).

    This is a lightweight wrapper around :func:`app.sandbox._run_subscript`
    so the acceptance-test suite can test the boundary directly without
    starting the HTTP server or calling :meth:`Service.process_next`.
    """
    # Build a minimal environment: always use the module's _make_minimal_env,
    # then overlay any user-supplied environment variables.
    base_env = {
        "PATH": os.getenv("PATH", ""),
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    if set_env:
        base_env.update(set_env)

    # Patch _make_minimal_env temporarily so _run_subscript uses our env.
    original_make = app.sandbox._make_minimal_env

    def _make_custom_env():
        return dict(base_env)

    app.sandbox._make_minimal_env = _make_custom_env
    try:
        result = app.sandbox._run_subscript(
            source,
            timeout=timeout,
            output_limit=output_limit,
            content=content,
        )
    finally:
        app.sandbox._make_minimal_env = original_make

    return (
        result.success,
        result.content,
        result.guarantees,
        result.exit_code,
        result.error_message,
        result.sandbox,
    )


# ---------------------------------------------------------------------------
# 1. 無限ループ — 実時間上限で殺され、隔離になる
# ---------------------------------------------------------------------------


def test_extractor_infinite_loop_isolated() -> None:
    """Test that an infinite-loop extractor is killed by the timeout,
    the extraction fails, and the sandbox reports the timeout guarantee.

    This test does NOT go through :meth:`Service.process_next`; it calls
    the sandbox boundary directly.
    """
    source = INFINITE_LOOP_SOURCE
    success, content, guarantees, exit_code, error_message, sandbox = _run_extractor_direct(
        source, timeout=2.0, output_limit=8 * 1024 * 1024
    )
    # The extractor should have been killed after the wall-time limit.
    assert success is False, f"Expected failure, got success={success}"
    assert error_message == "実時間上限超過", f"Expected timeout error, got: {error_message}"
    assert guarantees["wall_time"] == "timed_out", (
        f"Expected wall_time='timed_out', got {guarantees['wall_time']}"
    )
    # No body content should be produced.
    assert content is None, f"Expected no content on timeout, got {content!r}"
    assert sandbox == "subprocess"


# ---------------------------------------------------------------------------
# 2. 出力で殴る — 際限なく標準出力へ書く抽出器 → 出力上限で打ち切られ、隔離になる
# ---------------------------------------------------------------------------


def test_extractor_output_flood_isolated() -> None:
    """Test that an output-flood extractor triggers the output-byte limit
    cutoff, the extraction fails, and the sandbox reports the truncation.

    This test does NOT go through :meth:`Service.process_next`; it calls
    the sandbox boundary directly.
    """
    source = OUTPUT_FLOOD_SOURCE
    success, content, guarantees, exit_code, error_message, sandbox = _run_extractor_direct(
        source,
        timeout=10.0,
        output_limit=1 * 1024 * 1024,  # 1 MiB to trigger quickly
    )
    # The extractor should have been cut off after exceeding output_limit.
    assert success is False, f"Expected failure, got success={success}"
    assert "出力バイト数上限超過" in error_message, (
        f"Expected output flood error containing '出力バイト数上限超過', got: {error_message}"
    )
    assert guarantees["output_bytes"] == "truncated", (
        f"Expected output_bytes='truncated', got {guarantees['output_bytes']}"
    )
    # No body content should be produced when the output is truncated.
    assert content is None, f"Expected no content on flood, got {content!r}"
    assert sandbox == "subprocess"


# ---------------------------------------------------------------------------
# 3. 正常系 — 正しい抽出器は本文を返し、sandbox の種別が結果に残る
# ---------------------------------------------------------------------------


def test_extractor_normal_returns_content() -> None:
    """Test that a normal plaintext extractor returns the document body
    and the sandbox type is recorded in the result.

    This test does NOT go through :meth:`Service.process_next`; it calls
    the sandbox boundary directly.
    """
    source = PLAINTEXT_SOURCE
    synthetic = "成膜条件Aは処理温度180°C、処理時間30分。"
    success, content, guarantees, exit_code, error_message, sandbox = _run_extractor_direct(
        source, content=synthetic, timeout=5.0, output_limit=8 * 1024 * 1024
    )
    assert success is True, f"Expected success, got success={success}: {error_message}"
    # The content should be a JSON string with a "body" key.
    assert content is not None, "Expected content on success"
    data = json.loads(content)
    assert "body" in data, f"Expected 'body' key in extracted JSON, got {data}"
    assert data["body"] == synthetic, f"Expected body '{synthetic}', got '{data['body']}'"
    # Sandbox kind should be recorded (subprocess by default).
    assert sandbox == "subprocess", f"Expected sandbox='subprocess', got {sandbox!r}"
    assert guarantees["wall_time"] == "verified", (
        f"wall_time should be verified, got: {guarantees['wall_time']}"
    )
    assert guarantees["output_bytes"] == "verified", (
        f"output_bytes should be verified, got: {guarantees['output_bytes']}"
    )


# ---------------------------------------------------------------------------
# 4. 記録が嘘をつかない — 子プロセス系統で走ったとき、取り込み記録が
#     ネットワーク遮断・メモリ上限を主張していないこと
# ---------------------------------------------------------------------------


def test_extractor_guarantees_honest() -> None:
    """Test that a subprocess extractions does NOT claim strong network
    isolation or memory/cpu limits per ADR-0006 and §5.

    This test does NOT go through :meth:`Service.process_next`; it calls
    the sandbox boundary directly.
    """
    source = PLAINTEXT_SOURCE
    success, content, guarantees, exit_code, error_message, sandbox = _run_extractor_direct(
        source, content="honest data", timeout=5.0, output_limit=8 * 1024 * 1024
    )
    assert success is True, f"Expected success, got: {error_message}"
    assert sandbox == "subprocess"

    # Subprocess must NOT claim network isolation
    assert guarantees.get("network") != "strong", (
        f"Subprocess should not claim 'strong' network isolation, got: {guarantees.get('network')}"
    )
    # Subprocess must NOT claim memory limit on Windows (resource module unavailable)
    assert guarantees.get("memory") != "strong", (
        f"Subprocess should not claim 'strong' memory isolation, got: {guarantees.get('memory')}"
    )
    # Subprocess must NOT claim cpu limit on Windows (resource module unavailable)
    assert guarantees.get("cpu") != "strong", (
        f"Subprocess should not claim 'strong' cpu isolation, got: {guarantees.get('cpu')}"
    )
    # Verified guarantees ARE present
    assert guarantees.get("wall_time") == "verified", (
        f"wall_time should be verified, got: {guarantees.get('wall_time')}"
    )
    assert guarantees.get("output_bytes") == "verified", (
        f"output_bytes should be verified, got: {guarantees.get('output_bytes')}"
    )
    assert guarantees.get("env_stripped") == "verified", (
        f"env_stripped should be verified, got: {guarantees.get('env_stripped')}"
    )


# ---------------------------------------------------------------------------
# 5. 環境変数を持ち出す — 親の環境変数が子プロセスに漏れず、返り値にも現れない
# ---------------------------------------------------------------------------


def test_extractor_env_exfiltration_blocked() -> None:
    """A synthetic extractor that reads a planted parent env var must not be
    able to observe it, and the key/value must not appear in the sandbox
    result (content, error_message, guarantees).

    This is the §8.3 / ruling item 2 check: the boundary must actually strip
    the parent environment, not just claim env_stripped=verified.
    """
    key = "EXTRACTED_VAR"
    sentinel = "SENTINEL_ENV_EXFIL_7f3c9a"
    old = os.environ.get(key)
    os.environ[key] = sentinel
    try:
        result = app.sandbox._run_subscript(
            ENV_READER_SOURCE,
            timeout=5.0,
            output_limit=8 * 1024 * 1024,
            content="",
        )
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old

    haystacks = [
        result.content or "",
        result.error_message or "",
        json.dumps(result.guarantees, ensure_ascii=False),
    ]
    for haystack in haystacks:
        assert key not in haystack, (
            f"env key leaked into sandbox result: {key!r} found in {haystack!r}"
        )
        assert sentinel not in haystack, (
            f"env value leaked into sandbox result: {sentinel!r} found in {haystack!r}"
        )

    # The extractor should still run cleanly; it just must not see the secret.
    assert result.success is True, (
        f"Expected clean extraction with stripped env, got: {result.error_message}"
    )
    assert result.guarantees.get("env_stripped") == "verified"


# ---------------------------------------------------------------------------
# 6. 親が落ちない — 子プロセスが異常終了しても本体プロセスは生きている
# ---------------------------------------------------------------------------


def test_extractor_abnormal_exit_parent_alive() -> None:
    """A child extractor that exits abnormally must not crash the parent.

    The sandbox must report failure, keep the parent process alive, and record
    the subprocess sandbox kind.
    """
    source = """\
import sys
sys.stderr.write("synthetic child failure\\n")
sys.exit(2)
"""
    success, content, guarantees, exit_code, error_message, sandbox = _run_extractor_direct(
        source, content="", timeout=5.0, output_limit=8 * 1024 * 1024
    )
    assert sandbox == "subprocess"
    assert success is False
    assert exit_code == 2
    assert content is None
    assert error_message is not None
    assert "異常終了" in error_message
    # Reaching these assertions proves the parent process is still alive.


# ---------------------------------------------------------------------------
# 7. 成功時 content は stdout の JSON のみ — stderr 診断が混ざっても壊れない
# ---------------------------------------------------------------------------


def test_extractor_stderr_diagnostic_does_not_corrupt_content() -> None:
    """A successful extractor may write diagnostics to stderr.

    The sandbox contract (§3) carries the JSON result on stdout, so success
    content must be stdout alone and remain parseable as JSON even when stderr
    contains diagnostics.
    """
    synthetic = "stderr-separated-body"
    success, content, guarantees, exit_code, error_message, sandbox = _run_extractor_direct(
        STDERR_DIAGNOSTIC_SOURCE,
        content=synthetic,
        timeout=5.0,
        output_limit=8 * 1024 * 1024,
    )
    assert success is True, f"Expected success, got: {error_message}"
    assert sandbox == "subprocess"
    assert error_message is None
    assert exit_code == 0
    assert content is not None
    data = json.loads(content)
    assert data["body"] == synthetic
    assert guarantees.get("output_bytes") == "verified"


# ---------------------------------------------------------------------------
# 8. 出力上限は事後ではなく実行中に効く — 親の読み取り量と子孫プロセスの殺害
# ---------------------------------------------------------------------------


def test_extractor_output_limit_bounds_parent_read_bytes() -> None:
    """An extractor emitting far more than output_limit must be cut off mid-run
    so the parent never buffers the full stream in memory (T-PH6-130 AC1).

    Asserting failure alone is insufficient because post-hoc counting also fails
    after buffering everything; this test observes the actual bytes read by the
    parent and asserts they stay bounded near output_limit.
    """
    limit = 64 * 1024  # 64 KiB
    # Emit 16 MiB (256x limit) in small chunks so post-hoc buffering would read
    # all 16 MiB while in-flight enforcement cuts off shortly after 64 KiB.
    flood_source = """\
import sys
chunk = "x" * 16384
for _ in range(1024):
    sys.stdout.write(chunk)
    sys.stdout.flush()
"""
    result = app.sandbox._run_subscript(
        flood_source,
        timeout=15.0,
        output_limit=limit,
        content="",
    )
    assert result.success is False
    assert result.content is None
    assert result.guarantees["output_bytes"] == "truncated"
    assert result.error_message is not None
    assert "出力バイト数上限超過" in result.error_message
    assert result.bytes_read is not None
    assert result.bytes_read > limit
    # Must stay within limit + small pipe/read granularity slack, far below 16 MiB.
    assert result.bytes_read <= limit + 256 * 1024, (
        f"Parent buffered {result.bytes_read} bytes for output_limit={limit}; "
        "cutoff did not stop reading in flight"
    )


def test_extractor_output_limit_kills_grandchild_process_tree() -> None:
    """When an extractor spawns a grandchild holding stdout and exceeds output_limit,
    killing the process tree terminates the grandchild promptly without waiting for
    wall-time timeout (T-PH6-130 ID1).
    """
    limit = 64 * 1024
    tree_flood_source = """\
import subprocess, sys
# Grandchild inherits stdout/stderr and sleeps long after the parent floods stdout.
subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
chunk = "y" * 16384
for _ in range(256):
    sys.stdout.write(chunk)
    sys.stdout.flush()
"""
    started = time.monotonic()
    result = app.sandbox._run_subscript(
        tree_flood_source,
        timeout=20.0,
        output_limit=limit,
        content="",
    )
    elapsed = time.monotonic() - started
    assert result.success is False
    assert result.content is None
    assert result.guarantees["output_bytes"] == "truncated"
    # If only the direct child was killed, the surviving grandchild would hold the
    # stdout pipe open and block reader.join / drain. Tree kill finishes well before timeout.
    assert elapsed < 4.5, f"Process tree was not killed promptly (elapsed={elapsed:.2f}s)"


def test_extractor_stderr_flood_also_bounded_in_flight() -> None:
    """Unbounded stderr shares the output_limit budget with stdout and is cut off
    in flight with bounded parent reads.
    """
    limit = 64 * 1024
    stderr_flood_source = """\
import sys
chunk = "e" * 16384
for _ in range(1024):
    sys.stderr.write(chunk)
    sys.stderr.flush()
"""
    result = app.sandbox._run_subscript(
        stderr_flood_source,
        timeout=15.0,
        output_limit=limit,
        content="",
    )
    assert result.success is False
    assert result.content is None
    assert result.guarantees["output_bytes"] == "truncated"
    assert result.bytes_read is not None
    assert limit < result.bytes_read <= limit + 256 * 1024


# ---------------------------------------------------------------------------
# 9. Docker 経路の誠実さ (T-PH6-129) — docker エンジン未実証の環境で strong を主張しない
# ---------------------------------------------------------------------------


def test_docker_unavailable_on_host_does_not_claim_strong_guarantees() -> None:
    """When extract_with_sandbox(..., use_docker=True) runs on this host where no
    Docker daemon is reachable, it falls back cleanly: sandbox is not 'docker'
    and guarantees for network/memory/cpu do not claim 'strong' (T-PH6-129 AC1).

    Note: Docker containment is unverified on this host.
    """
    synthetic = "docker不在時の退避本文"
    result = app.sandbox.extract_with_sandbox("plaintext", synthetic, use_docker=True)
    assert result.sandbox != "docker", f"Expected fallback sandbox, got {result.sandbox!r}"
    assert result.sandbox == "subprocess"
    assert result.guarantees.get("network") != "strong"
    assert result.guarantees.get("memory") != "strong"
    assert result.guarantees.get("cpu") != "strong"
    assert result.guarantees.get("write_out_of_tmp") != "strong"
    assert result.success is True, (
        f"Fallback subprocess should extract cleanly: {result.error_message}"
    )
    assert result.content is not None
    assert json.loads(result.content)["body"] == synthetic


def test_docker_unsupported_format_without_engine_does_not_claim_strong() -> None:
    """Unsupported format with use_docker=True must also not claim docker/strong
    when Docker did not actually run.
    """
    result = app.sandbox.extract_with_sandbox("unknown_format", "data", use_docker=True)
    assert result.success is False
    assert result.sandbox != "docker"
    assert result.guarantees.get("network") != "strong"
    assert result.guarantees.get("memory") != "strong"
    assert result.guarantees.get("cpu") != "strong"


def test_docker_spawn_or_daemon_failure_does_not_claim_strong(monkeypatch) -> None:
    """Even when docker info appears to pass or fails mid-flight, a docker invocation
    that cannot start a container (spawn_failed or exit 125/126/127) must never
    claim sandbox='docker' or strong guarantees.
    """
    monkeypatch.setattr(app.sandbox.shutil, "which", lambda _name: "docker")

    # Case A: docker info fails -> falls back to subprocess without claiming strong.
    calls: list[list[str]] = []
    real_run_process = app.sandbox._run_process

    def fake_run_info_fails(command: list[str], stdin_data: bytes, **kwargs):
        calls.append(list(command))
        if len(command) >= 2 and command[1] == "info":
            return app.sandbox._Outcome(exit_code=1, stdout="", stderr="pipe unavailable")
        return real_run_process(command, stdin_data, **kwargs)

    monkeypatch.setattr(app.sandbox, "_run_process", fake_run_info_fails)
    fallback = app.sandbox._run_docker(PLAINTEXT_SOURCE, content="from-fallback")
    assert fallback.sandbox == "subprocess"
    assert fallback.guarantees.get("network") != "strong"
    assert fallback.guarantees.get("memory") != "strong"
    assert fallback.guarantees.get("cpu") != "strong"
    assert fallback.success is True

    # Case B: docker info succeeds, but docker run fails before container starts (exit 125).
    def fake_run_daemon_error(command: list[str], stdin_data: bytes, **kwargs):
        if len(command) >= 2 and command[1] == "info":
            return app.sandbox._Outcome(exit_code=0, stdout="ok", stderr="")
        return app.sandbox._Outcome(exit_code=125, stdout="", stderr="docker daemon error")

    monkeypatch.setattr(app.sandbox, "_run_process", fake_run_daemon_error)
    failed_start = app.sandbox._run_docker(PLAINTEXT_SOURCE, content="no-start")
    assert failed_start.success is False
    assert failed_start.sandbox != "docker"
    assert failed_start.guarantees.get("network") != "strong"
    assert failed_start.guarantees.get("memory") != "strong"
    assert failed_start.guarantees.get("cpu") != "strong"


def test_docker_argv_has_no_host_paths_and_sets_entrypoint_interactive_and_user() -> None:
    """_docker_argv builds the container command statically without starting an engine:
    - no host absolute paths (such as sys.executable) appear anywhere in argv (AC2)
    - includes -i / --interactive so stdin reaches the extractor
    - overrides ENTRYPOINT via --entrypoint and keeps --user 1000:1000
    - uses an explicit container interpreter (e.g. python3) rather than positional python3
      swallowed by an image supervisor entrypoint.
    """
    import pathlib
    import sys

    argv = app.sandbox._docker_argv(
        app.sandbox.DEFAULT_DOCKER_IMAGE,
        app.sandbox.DEFAULT_DOCKER_INTERPRETER,
        "print(1)",
    )
    assert argv[0] == "docker"
    assert argv[1] == "run"

    # Host absolute paths (Windows drive paths or host sys.executable) must never appear.
    # Note: '/tmp:exec' is an internal container tmpfs mount specification, not a host path.
    for token in argv:
        assert sys.executable not in token, f"sys.executable leaked into argv: {token!r}"
        assert not pathlib.PureWindowsPath(token).is_absolute(), (
            f"Windows host absolute path leaked into argv: {token!r}"
        )
        assert "\\" not in token or token == "print(1)", (
            f"Backslash path leaked into argv: {token!r}"
        )

    # Interactive stdin forwarding must be enabled.
    assert "-i" in argv or "--interactive" in argv

    # Non-root container user must be preserved.
    assert "--user" in argv
    user_idx = argv.index("--user")
    assert argv[user_idx + 1] == "1000:1000"

    # Image ENTRYPOINT must be overridden explicitly with the container interpreter,
    # and the args after the image are ["-c", script] (no positional interpreter).
    assert "--entrypoint" in argv
    ep_idx = argv.index("--entrypoint")
    assert argv[ep_idx + 1] == "python3"

    image_idx = argv.index(app.sandbox.DEFAULT_DOCKER_IMAGE)
    assert argv[image_idx + 1 :] == ["-c", "print(1)"]

    # Containment flags vocabulary check.
    for expected in (
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "--tmpfs",
    ):
        assert expected in argv, f"Missing expected docker flag {expected!r} in {argv!r}"
    assert any(tok.startswith("--memory") for tok in argv)
    assert any(tok.startswith("--cpus") for tok in argv)


def test_docker_client_env_preserves_connection_vars_without_leaking_secrets(monkeypatch) -> None:
    """Docker CLI client env keeps DOCKER_HOST / DOCKER_CERT_PATH / DOCKER_TLS_VERIFY /
    DOCKER_CONFIG so remote/custom daemons remain reachable, while unrelated host
    environment variables are excluded.
    """
    monkeypatch.setenv("DOCKER_HOST", "npipe:////./pipe/custom_docker")
    monkeypatch.setenv("DOCKER_TLS_VERIFY", "1")
    monkeypatch.setenv("DOCKER_CERT_PATH", "/certs/client")
    monkeypatch.setenv("DOCKER_CONFIG", "/cfg/docker")
    monkeypatch.setenv("EXTRACTED_VAR", "SENTINEL_MUST_NOT_ENTER_DOCKER_CLIENT_ENV")

    client_env = app.sandbox._make_docker_client_env()
    assert client_env.get("DOCKER_HOST") == "npipe:////./pipe/custom_docker"
    assert client_env.get("DOCKER_TLS_VERIFY") == "1"
    assert client_env.get("DOCKER_CERT_PATH") == "/certs/client"
    assert client_env.get("DOCKER_CONFIG") == "/cfg/docker"
    assert "EXTRACTED_VAR" not in client_env
