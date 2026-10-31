"""Opt-in real Docker containment evidence; skipped CI is never live proof."""

import json
import os
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest

from loop_engine.docker_boundary import DockerBoundary


@pytest.fixture
def boundary() -> tuple[DockerBoundary, Path]:
    if os.environ.get("LOCUS_LIVE_DOCKER") != "1":
        pytest.skip("Real Docker containment is opt-in")
    root = Path(__file__).resolve().parents[2]
    receipt = json.loads((root / ".loop/runtime/qa-image.json").read_text())
    workspace = root / ".loop/runtime/probes" / ("live-" + uuid4().hex)
    workspace.mkdir(parents=True)
    return DockerBoundary(root, receipt["image_id"]), workspace


def test_source_identity_network_and_control_isolation(
    boundary: tuple[DockerBoundary, Path],
) -> None:
    executor, work = boundary
    script = """import os,socket,pathlib,json
d={'uid':os.getuid(),'socket_absent':not pathlib.Path('/var/run/docker.sock').exists()}
try:
 socket.create_connection(('1.1.1.1',443),timeout=1);d['network_denied']=False
except OSError:
 d['network_denied']=True
try:
 pathlib.Path('/lease/heartbeat').write_text('forged');d['lease_denied']=False
except OSError:
 d['lease_denied']=True
pathlib.Path('result.txt').write_text('source-only')
print(json.dumps(d))
"""
    result = executor.run([sys.executable, "-c", script], work, timeout=20)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "uid": 1000,
        "socket_absent": True,
        "network_denied": True,
        "lease_denied": True,
    }
    assert not (work / "result.txt").exists()  # QA writes stay in its disposable copy.


def test_timeout_stops_setsid_grandchild_while_executor_stays_alive(
    boundary: tuple[DockerBoundary, Path],
) -> None:
    executor, work = boundary
    code = (
        "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',"
        '"import time,pathlib;time.sleep(4);'
        "pathlib.Path('escaped.txt').write_text('bad')\"],start_new_session=True);"
        "time.sleep(60)"
    )
    result = executor.run([sys.executable, "-c", code], work, timeout=2)
    assert result.outcome == "timeout"
    time.sleep(4)
    assert not (work / "escaped.txt").exists()
    assert all(
        (path / "settled").exists()
        for path in executor.leases.iterdir()
        if (path / "active").exists()
    )
    assert (
        executor.run([sys.executable, "-c", "print('next')"], work, timeout=15).stdout.strip()
        == "next"
    )


def test_readonly_role_cannot_change_source(boundary: tuple[DockerBoundary, Path]) -> None:
    executor, work = boundary
    executor.readonly = True
    result = executor.run(
        [sys.executable, "-c", "from pathlib import Path;Path('forbidden.txt').write_text('bad')"],
        work,
        timeout=15,
    )
    assert result.returncode != 0
    assert not (work / "forbidden.txt").exists()


@pytest.mark.parametrize("kind", ["cancelled", "output_limit"])
def test_early_stop_reconciles_container_before_reuse(
    boundary: tuple[DockerBoundary, Path], kind: str
) -> None:
    executor, work = boundary
    stop = threading.Event()
    timer = threading.Timer(2, stop.set)
    timer.start()
    try:
        result = executor.run(
            [sys.executable, "-c", "import time;print('x'*50000,flush=True);time.sleep(60)"],
            work,
            timeout=20,
            cancelled=stop.is_set if kind == "cancelled" else lambda: False,
            output_limit=1000 if kind == "output_limit" else 100000,
        )
    finally:
        timer.cancel()
    assert result.outcome == kind
    assert all(
        (path / "settled").exists()
        for path in executor.leases.iterdir()
        if (path / "active").exists()
    )
    assert (
        executor.run([sys.executable, "-c", "print('settled')"], work, timeout=15).returncode == 0
    )


def test_sensitive_files_are_rejected_before_any_container_starts(
    boundary: tuple[DockerBoundary, Path],
) -> None:
    from loop_engine.security import SafetyError

    executor, work = boundary
    (work / ".env").write_text("synthetic value only")
    with pytest.raises(SafetyError):
        executor.run([sys.executable, "-c", "print('must not run')"], work, timeout=15)
