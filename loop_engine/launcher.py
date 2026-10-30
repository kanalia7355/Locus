"""Skill entrypoint: inspect durable state and request one bounded controller."""

from pathlib import Path
from typing import Any

from loop_engine.locking import ProjectLock


def launch(root: Path) -> dict[str, Any]:
    from loop_engine.cli import doctor, open_state, parser, run

    health = doctor(root)
    try:
        with ProjectLock(root / ".loop/runtime/controller.lock"):
            pass
    except RuntimeError:
        return {"status": "already_running"}
    goal = root / ".loop/goal.md"
    if not goal.is_file() or not goal.read_text(encoding="utf-8").strip():
        return {
            "status": "goal_required",
            "next": "Specify outcome, allowed paths and acceptance criteria.",
        }
    state = open_state(root)
    unfinished = [task for task in state.tasks() if task.status not in {"completed", "cancelled"}]
    if not unfinished:
        return {
            "status": "plan_required_or_complete",
            "next": "Review Goal and loop plan --file; no worker started.",
        }
    if not health["ready_for_live_execution"]:
        return {"status": "execution_boundary_unverified", "doctor": health}
    args = parser().parse_args(["--project", str(root), "resume", "--background"])
    outcome = run(args)
    return {
        "status": "launch_requested" if outcome == 0 else "launch_failed",
        "exit_code": outcome,
        "log": ".loop/runtime/logs/controller.log",
    }
