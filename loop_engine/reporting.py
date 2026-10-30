"""Human-readable output generated exclusively from persistent state."""

from pathlib import Path

from loop_engine.security import atomic_text, fingerprint
from loop_engine.state_store import StateStore


def progress(state: StateStore) -> str:
    lines = [
        "# Loop progress",
        "",
        "SQLite state is authoritative.",
        "",
        "| Task | State | Attempts | Title |",
        "|---|---|---|---|",
    ]
    for task in state.tasks():
        title = task.title.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {task.id} | {task.status} | {task.attempts}/{task.max_attempts} | {title} |"
        )
    lines += [
        "",
        f"Control: {state.metadata('control', 'stopped')}",
        "",
        "Monetary caps are not guaranteed; time/task/attempt limits apply.",
    ]
    return "\n".join(lines) + "\n"


def write_report(state: StateStore, root: Path) -> str:
    data = progress(state)
    relative = ".loop/progress.md"
    path = root / relative
    owned = state.metadata("owned_files", {})
    if path.exists() and owned.get(relative) == fingerprint(path.read_text(encoding="utf-8")):
        atomic_text(path, data)
        state.set_metadata("owned_files", {**owned, relative: fingerprint(data)})
    else:
        state.event("report.user_file_preserved")
    from loop_engine.approval import ApprovalQueue

    decisions = ["# Loop decisions", "", "SQLite is authoritative.", ""]
    decisions += [
        f"- {item['id']} · {item['status']} · {item['category']}: {item['question']}"
        for item in ApprovalQueue(state).decisions()
    ]
    target = root / ".loop/decisions.md"
    owned = state.metadata("owned_files", {})
    if target.exists() and owned.get(".loop/decisions.md") == fingerprint(
        target.read_text(encoding="utf-8")
    ):
        rendered = "\n".join(decisions) + "\n"
        atomic_text(target, rendered)
        state.set_metadata("owned_files", {**owned, ".loop/decisions.md": fingerprint(rendered)})
    return data
