"""Synthetic local sandbox diagnostics; these never certify a complete model boundary."""

import sys
import tempfile
from pathlib import Path
from typing import Any

from loop_engine.codex_runner import codex_binary
from loop_engine.process import ProcessRunner


def sandbox_probe(root: Path) -> dict[str, Any]:
    binary = codex_binary()
    if not binary:
        return {"live_ready": False, "reason": "codex_unavailable"}
    runtime = root.resolve() / ".loop/runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sandbox-probe-", dir=runtime) as name:
        container = Path(name).resolve()
        if not container.is_relative_to(runtime):
            raise ValueError("Probe path escaped runtime")
        workspace = container / "workspace"
        workspace.mkdir()
        sentinel = container / "synthetic-control.txt"
        sentinel.write_text("synthetic boundary probe", encoding="utf-8")
        code = (
            "from pathlib import Path\nprint('PROBE_STARTED')\n"
            f"p = Path({str(sentinel)!r})\n"
            "try:\n    p.read_text()\n    print('CONTROL_READ_ALLOWED')\n"
            "except PermissionError:\n    print('CONTROL_READ_DENIED')\n"
        )
        script = workspace / "probe.py"
        script.write_text(code, encoding="utf-8")
        outcome = ProcessRunner().run(
            [
                binary,
                "sandbox",
                "-P",
                ":read-only",
                "-C",
                str(workspace),
                "--",
                sys.executable,
                str(script),
            ],
            workspace,
            timeout=15,
        )
        return {
            "live_ready": False,
            "command_outcome": outcome.outcome,
            "exit_code": outcome.returncode,
            "probe_started": "PROBE_STARTED" in outcome.stdout,
            "control_read_was_allowed": "CONTROL_READ_ALLOWED" in outcome.stdout,
            "control_read_was_denied": "CONTROL_READ_DENIED" in outcome.stdout,
            "reason": "Complete filesystem/network/tool/credential isolation proof unavailable",
            "model_called": False,
        }
