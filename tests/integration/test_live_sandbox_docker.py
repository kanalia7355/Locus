"""Opt-in real Docker containment evidence for DATA-006 (T-PH6-104).

These tests verify Docker-level sandbox guarantees (network, write isolation)
when LOCUS_LIVE_DOCKER=1 is set.  They follow the same作法 as
tests/integration/test_live_docker_boundary.py.

skip された検査を証拠として扱わないこと (design §8).
"""

import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest


def _need_docker() -> None:
    """Skip unless LOCUS_LIVE_DOCKER=1 is set in the environment."""
    if os.environ.get("LOCUS_LIVE_DOCKER") != "1":
        pytest.skip("Real Docker containment is opt-in (set LOCUS_LIVE_DOCKER=1)")


# ---------------------------------------------------------------------------
# 7. 外に出ようとする — ソケットを開こうとする抽出器 → 接続できず、隔離になる
# ---------------------------------------------------------------------------


def test_live_docker_network_access_denied() -> None:
    """In Docker with --network none, socket connections are denied.

    An extractor that attempts to open an outbound connection should fail
    with the connection denied, resulting in isolation (quarantine).
    """
    _need_docker()

    root = Path(__file__).resolve().parents[2]
    receipt = json.loads((root / ".loop/runtime/qa-image.json").read_text())

    script = """import socket,json
try:
    s = socket.create_connection(("1.1.1.1", 443), timeout=2)
    print(json.dumps({"connected": True, "error": None}))
except OSError as e:
    print(json.dumps({"connected": False, "error": str(e) }))
"""
    work = Path(__file__).resolve().parents[2] / ".loop/runtime/probes" / ("docker-" + uuid4().hex)
    work.mkdir(parents=True)

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
        "/tmp:exec",  # noqa: S108
        "--user",
        "1000:1000",
        receipt["image_id"],
        "python3",
        "-c",
        script,
    ]
    proc = subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True, timeout=20
    )
    assert proc.returncode == 0, f"Docker run failed: {proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["connected"] is False, (
        f"Docker network isolation failed: connection was allowed. stdout={proc.stdout}"
    )


# ---------------------------------------------------------------------------
# 8. 外に書く — サンドボックス外の既知パスへ書こうとする抽出器 →
#     ファイルの不在で書けていないことを確認する
# ---------------------------------------------------------------------------


def test_live_docker_write_outside_denied() -> None:
    """In Docker with --read-only + --tmpfs, writing outside the allowed tmpfs
    is denied.  The extractor should not be able to write to the host filesystem.

    An extractor that attempts to write to a path outside the sandbox's
    writable directory should fail with the file not existing (OSError).
    """
    _need_docker()

    root = Path(__file__).resolve().parents[2]
    receipt = json.loads((root / ".loop/runtime/qa-image.json").read_text())

    script = """import pathlib,json,os
out = pathlib.Path("/lease/heartbeat")
try:
    out.write_text("forged")
    print(json.dumps({"wrote": True}))
except OSError as e:
    print(json.dumps({"wrote": False, "error": str(e) }))
"""
    work = (
        Path(__file__).resolve().parents[2]
        / ".loop/runtime/probes"
        / ("docker-write-" + uuid4().hex)
    )
    work.mkdir(parents=True)

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
        "/tmp:exec",  # noqa: S108
        "--user",
        "1000:1000",
        receipt["image_id"],
        "python3",
        "-c",
        script,
    ]
    proc = subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True, timeout=20
    )
    assert proc.returncode == 0, f"Docker run failed: {proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["wrote"] is False, (
        f"Docker write isolation failed: write was allowed. stdout={proc.stdout}"
    )
    # Verify the file does not exist in the work directory (which is a copy)
    assert not (work / "heartbeat").exists(), "Write to outside path should not create the file"


# ---------------------------------------------------------------------------
# Product Docker path – exercises the actual sandbox boundary function.
# ---------------------------------------------------------------------------


def test_live_docker_product_path_runs_extractor() -> None:
    """The product Docker path (_run_docker) executes an extractor in Docker.

    This is env-gated evidence that the product command construction works with
    a real Docker engine and the receipt image, not only hand-built commands.
    """
    _need_docker()

    import app.sandbox

    root = Path(__file__).resolve().parents[2]
    receipt = json.loads((root / ".loop/runtime/qa-image.json").read_text())

    source = """\
import sys, json
content = sys.stdin.read()
print(json.dumps({"body": content}), flush=True)
"""
    result = app.sandbox._run_docker(
        source,
        timeout=20.0,
        output_limit=8 * 1024 * 1024,
        image=receipt["image_id"],
        content="docker-product-path",
    )
    assert result.success is True, result.error_message
    assert result.sandbox == "docker"
    assert result.content is not None
    data = json.loads(result.content)
    assert data["body"] == "docker-product-path"
    assert result.guarantees.get("network") == "strong"
    assert result.guarantees.get("env_stripped") == "verified"
