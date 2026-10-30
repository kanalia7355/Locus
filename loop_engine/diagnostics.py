"""Synthetic local sandbox diagnostics; these never certify a complete model boundary."""

import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from loop_engine.process import ProcessRunner


def sandbox_probe(root: Path) -> dict[str, Any]:
    binary = shutil.which("codex.cmd") or shutil.which("codex")
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
            f"from pathlib import Path; p=Path({str(sentinel)!r}); "
            'print("CONTROL_READ_ALLOWED" if p.read_text() else "UNPROVEN")'
        )
        outcome = ProcessRunner().run(
            [
                binary,
                "sandbox",
                "-c",
                'sandbox_mode="read-only"',
                "-C",
                str(workspace),
                "--",
                sys.executable,
                "-c",
                code,
            ],
            workspace,
            timeout=15,
        )
        return {
            "live_ready": False,
            "command_outcome": outcome.outcome,
            "exit_code": outcome.returncode,
            "control_read_was_allowed": "CONTROL_READ_ALLOWED" in outcome.stdout,
            "reason": "Complete filesystem/network/tool/credential isolation proof unavailable",
            "model_called": False,
        }
