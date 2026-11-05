"""Bounded real capability checks; receipts invalidate when the runtime changes."""

import json
import os
import sqlite3
import sys
import tomllib
from pathlib import Path
from uuid import uuid4

from loop_engine.codex_runner import codex_binary
from loop_engine.security import SafetyError, fingerprint, reparse, within
from loop_engine.toolless_boundary import ToollessBoundary


def runtime_identity(root: Path) -> str:
    names = sorted(
        path.relative_to(root / "loop_engine").as_posix()
        for path in (root / "loop_engine").rglob("*.py")
    )
    names.append("container_runtime/Dockerfile")
    return fingerprint(
        {
            "source": {
                name: (root / "loop_engine" / name).read_text(encoding="utf-8") for name in names
            },
            "client": json.loads(within(root, ".loop/runtime/codex-client.json").read_text()),
            "image": json.loads(within(root, ".loop/runtime/qa-image.json").read_text()),
            "binary": codex_binary(root),
        }
    )


def boundary_for(root: Path) -> ToollessBoundary:
    receipt = json.loads(within(root, ".loop/runtime/qa-image.json").read_text())
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    settings = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
    policy = None
    path = root / ".loop/runtime/state.sqlite3"
    if path.is_file():
        if any(reparse(part) for part in (path, *path.parents)):
            raise SafetyError("Profile metadata reparse boundary")
        # Admission reads only existing nonsecret metadata, never initializes or
        # approves a profile. The full profile remains bound by the live permit.
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            row = db.execute("SELECT value FROM metadata WHERE key='c_min_auth_profile'").fetchone()
        profile = json.loads(row[0]) if row else None
        if isinstance(profile, dict):
            policy = profile.get("notification_policy")
    return ToollessBoundary(
        root,
        receipt["image_id"],
        list(settings.get("mcp_servers", {})),
        notification_policy=policy,
    )


def probe(root: Path) -> dict[str, object]:
    boundary = boundary_for(root)
    work = within(root, ".loop/runtime/probes/runtime-" + uuid4().hex)
    work.mkdir(parents=True)
    (work / "canary.txt").write_text("synthetic")
    tool_surface = boundary.probe(work)
    code = """import os,socket,json,pathlib
d={'uid':os.getuid(),'daemon_absent':not pathlib.Path('/var/run/docker.sock').exists()}
try:
 socket.create_connection(('1.1.1.1',443),timeout=1);d['network_denied']=False
except OSError:
 d['network_denied']=True
try:
 pathlib.Path('/lease/heartbeat').write_text('forged');d['lease_denied']=False
except OSError:
 d['lease_denied']=True
pathlib.Path('canary.txt').write_text('disposable QA copy')
print(json.dumps(d))
"""
    result = boundary.docker.run([sys.executable, "-c", code], work, timeout=20)
    expected = {"uid": 1000, "daemon_absent": True, "network_denied": True, "lease_denied": True}
    qa = (
        result.outcome == "exit"
        and result.returncode == 0
        and json.loads(result.stdout) == expected
    )
    qa = qa and (work / "canary.txt").read_text() == "synthetic"
    timed = boundary.docker.run(
        [sys.executable, "-c", "import time;time.sleep(60)"], work, timeout=2
    )
    passed = tool_surface["passed"] and qa and timed.outcome == "timeout"
    receipt = {
        "passed": bool(passed),
        "identity": runtime_identity(root),
        "tool_surface": tool_surface,
        "qa": qa,
        "timeout": timed.outcome,
        "merge_authorized": False,
    }
    within(root, ".loop/runtime/live-runtime.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    return receipt


def require_receipt(root: Path) -> None:
    receipt = json.loads(within(root, ".loop/runtime/live-runtime.json").read_text())
    if not isinstance(receipt, dict):
        raise SafetyError("Runtime receipt must be an object")
    surface = receipt.get("tool_surface", {})
    if (
        receipt.get("passed") is not True
        or receipt.get("identity") != runtime_identity(root)
        or not isinstance(surface, dict)
        or surface.get("surface_version") != 3
        or surface.get("protocol") != "c-min-lite-v3"
        or surface.get("response_gate_verified") is not True
        or surface.get("auth_profile_verified") is not True
        or surface.get("live_path_verified") is not True
        or surface.get("passed") is not True
        or surface.get("no_tools") is not True
        or surface.get("fresh_request") is not True
    ):
        raise SafetyError("Runtime changed or live containment checks have not passed")
