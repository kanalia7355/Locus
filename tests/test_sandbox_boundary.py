"""Synthetic extractor boundary tests for DATA-006 (T-PH6-104).

These tests verify that document extraction via the sandbox child process
respectes isolation guarantees.  They use only synthetic (harmless) extractors
and synthetic file content — no real PDF/Office/OCR libraries, no real
malware, no real credentials.

See DOCUMENT_EXTRACTION_BOUNDARY.md §8 for the full acceptance criteria.
"""

import json
import os

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
    base_env = {"PATH": os.getenv("PATH", ""), "PYTHONUNBUFFERED": "1"}
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
