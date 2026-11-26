"""Opt-in live Docker sandbox checks for DATA-006 / T-PH6-129.

These checks exercise the product sandbox path (`extract_with_sandbox(..., use_docker=True)`)
when `LOCUS_LIVE_DOCKER=1` is set on a machine with a running Docker daemon.
On hosts without a Docker daemon (including this development machine), Docker
containment is unverified: skipped checks are NEVER evidence that containment works
(DOCUMENT_EXTRACTION_BOUNDARY.md §5, §8).
"""

import json
import os
from pathlib import Path
from uuid import uuid4

import app.sandbox
import pytest


def _need_docker() -> str:
    """Skip unless LOCUS_LIVE_DOCKER=1 is set; return the target Docker image."""
    if os.environ.get("LOCUS_LIVE_DOCKER") != "1":
        pytest.skip(
            "Live Docker check is opt-in (set LOCUS_LIVE_DOCKER=1); "
            "skip is not evidence of containment"
        )
    receipt_path = Path(__file__).resolve().parents[2] / ".loop/runtime/qa-image.json"
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        image_id = receipt.get("image_id")
        if isinstance(image_id, str) and image_id:
            return image_id
    return app.sandbox.DEFAULT_DOCKER_IMAGE


# ---------------------------------------------------------------------------
# 7. 外に出ようとする — ソケットを開こうとする抽出器 → 接続できず、隔離になる
# ---------------------------------------------------------------------------


def test_live_docker_network_access_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    """Through extract_with_sandbox(..., use_docker=True), outbound socket
    connections inside the container are denied (--network none) and cause
    the extraction to fail (quarantine).

    Note: Unverified when skipped without LOCUS_LIVE_DOCKER=1.
    """
    image = _need_docker()

    probe_source = """\
import socket, json, sys
sys.stdin.read()
s = socket.create_connection(("1.1.1.1", 443), timeout=2)
s.close()
print(json.dumps({"body": "unexpectedly-connected"}), flush=True)
"""
    monkeypatch.setitem(app.sandbox.EXTRACTOR_SOURCE, "net_probe", probe_source)
    result = app.sandbox.extract_with_sandbox(
        "net_probe",
        "probe-input",
        timeout=20.0,
        use_docker=True,
        docker_image=image,
    )
    assert result.sandbox == "docker", (
        f"Expected live Docker execution (not subprocess fallback), got sandbox={result.sandbox!r}"
    )
    assert result.success is False, "Outbound socket connection must fail under --network none"
    assert result.content is None
    assert result.guarantees.get("network") == "strong"


# ---------------------------------------------------------------------------
# 8. 外に書く — サンドボックス外の既知パスへ書こうとする抽出器 →
#     失敗し、ホスト側にもファイルが存在しないことを確認する
# ---------------------------------------------------------------------------


def test_live_docker_write_outside_denied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Through extract_with_sandbox(..., use_docker=True), writing outside the
    container's /tmp tmpfs fails under --read-only, and no file appears on the
    host filesystem.

    Note: Unverified when skipped without LOCUS_LIVE_DOCKER=1.
    """
    image = _need_docker()

    host_probe = tmp_path / ("outside-" + uuid4().hex + ".txt")
    write_probe_source = f"""\
import pathlib, json, sys
sys.stdin.read()
# Attempt both a container root-fs write and the host probe path.
for target in ("/etc/locus_forged_probe", {host_probe.as_posix()!r}):
    pathlib.Path(target).write_text("forged", encoding="utf-8")
print(json.dumps({{"body": "unexpectedly-wrote"}}), flush=True)
"""
    monkeypatch.setitem(app.sandbox.EXTRACTOR_SOURCE, "write_probe", write_probe_source)
    result = app.sandbox.extract_with_sandbox(
        "write_probe",
        "probe-input",
        timeout=20.0,
        use_docker=True,
        docker_image=image,
    )
    assert result.sandbox == "docker", (
        f"Expected live Docker execution (not subprocess fallback), got sandbox={result.sandbox!r}"
    )
    assert result.success is False, "Write outside /tmp must fail under --read-only"
    assert result.content is None
    assert not host_probe.exists(), "Extractor must not create files on the host filesystem"


# ---------------------------------------------------------------------------
# Product Docker path – normal extraction round-trip via extract_with_sandbox
# ---------------------------------------------------------------------------


def test_live_docker_product_path_runs_extractor() -> None:
    """extract_with_sandbox(..., use_docker=True) passes stdin to the container
    extractor and returns its JSON output when a live Docker daemon is present.

    Note: Unverified when skipped without LOCUS_LIVE_DOCKER=1.
    """
    image = _need_docker()

    result = app.sandbox.extract_with_sandbox(
        "plaintext",
        "docker-product-path",
        timeout=20.0,
        output_limit=8 * 1024 * 1024,
        use_docker=True,
        docker_image=image,
    )
    assert result.success is True, result.error_message
    assert result.sandbox == "docker"
    assert result.content is not None
    data = json.loads(result.content)
    assert data["body"] == "docker-product-path"
    assert result.guarantees.get("network") == "strong"
    assert result.guarantees.get("env_stripped") == "verified"
