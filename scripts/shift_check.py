"""The four checks that open an orchestrator shift, as one command.

A checklist spread over four commands does not get run on a tired wake-up, and
each of these four exists because skipping it cost hours. One command, ten
lines of output, and a verdict line that says whether the shift has work.

Read `.agents/skills/orchestrator-shift/SKILL.md` for why each check is here.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))


def run(*command: str, quiet: bool = False) -> str:
    """Run a command and return its output.

    `quiet` keeps stderr out: git writes `warning: LF will be replaced by CRLF`
    there on this checkout, and folding that into a `--name-only` listing made
    this script report five conflicted files called `warning:`, `in`, `the`.
    """
    result = subprocess.run(  # noqa: S603 — fixed commands, no shell
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    if quiet:
        return result.stdout or ""
    return (result.stdout or "") + (result.stderr or "")


def stranded_merge() -> str:
    """A half-finished merge makes every later job report a dirty branch."""
    if (ROOT / ".git" / "MERGE_HEAD").exists():
        head = (ROOT / ".git" / "MERGE_HEAD").read_text(encoding="utf-8").strip()[:12]
        return f"FAIL  a merge is in progress ({head}); every later job will report a dirty branch"
    conflicted = run("git", "diff", "--name-only", "--diff-filter=U", quiet=True).split()
    if conflicted:
        return f"FAIL  unresolved conflicts: {', '.join(conflicted[:5])}"
    return "ok    no merge left in progress"


def processes() -> list[tuple[int, int, str, str, bool]]:
    """`(pid, parent, name, created, is_session)` for the loop's own processes.

    Queried by image name. Matching on the command line alone returns the
    querying shell itself, which is how a dead loop was reported as alive for
    seventeen hours on 2026-11-18.
    """
    if sys.platform != "win32":
        return []
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe' or Name = 'opencode.exe'\" "
        "| ForEach-Object { "
        "'{0}|{1}|{2}|{3}|{4}' -f $_.ProcessId, $_.ParentProcessId, $_.Name, "
        "$_.CreationDate.ToString('s'), $_.CommandLine }"
    )
    found: list[tuple[int, int, str, str, bool]] = []
    for line in run("powershell", "-NoProfile", "-Command", script).splitlines():
        parts = line.split("|", 4)
        if len(parts) < 5 or not parts[0].strip().isdigit():
            continue
        pid, parent, name, created, command = parts
        if "jobloop" in command or "supervise_loop" in command or name.strip() == "opencode.exe":
            # `run --standalone` is a job session; `serve --service` is the
            # long-lived helper the user's own shell started, and it is
            # parentless by nature — reporting it as an orphan every time would
            # train the reader to ignore this check.
            session = "run --standalone" in command
            found.append((int(pid), int(parent), name.strip(), created.strip(), session))
    return found


def orphans(live: list[tuple[int, int, str, str, bool]]) -> str:
    """A job session whose parent is gone writes where nobody reads."""
    alive = {pid for pid, _, _, _, _ in live}
    loose = [
        (pid, created)
        for pid, parent, name, created, session in live
        if session and parent not in alive
    ]
    if not loose:
        return "ok    no orphaned worker"
    named = ", ".join(f"{pid} (started {created[:16]})" for pid, created in loose[:4])
    return f"FAIL  orphaned worker session: {named} — taskkill /PID <id> /T /F"


def supervisor(live: list[tuple[int, int, str, str, bool]]) -> str:
    running = [pid for pid, _, name, _, _ in live if name == "python.exe"]
    beat = ROOT / ".jobloop" / "supervisor.log"
    age = ""
    if beat.is_file():
        last = beat.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1:]
        if last:
            stamp = last[0].split(" ", 1)[0]
            try:
                minutes = (datetime.now(JST) - datetime.fromisoformat(stamp)).total_seconds() / 60
                age = f", last heartbeat {minutes:.0f} min ago"
            except ValueError:
                age = ""
    if not running:
        return f"FAIL  no jobloop or supervisor process{age}"
    return f"ok    {len(running)} loop process(es) alive{age}"


def main() -> int:
    live = processes()
    checks = [stranded_merge(), orphans(live), supervisor(live)]
    busy = (ROOT / ".jobloop" / "orchestrator-busy").exists()
    checks.append(
        "WARN  .jobloop/orchestrator-busy is set — containment is unverified while it is"
        if busy
        else "ok    orchestrator-busy is clear"
    )
    print("\n".join(checks))
    print("\n--- open stops " + "-" * 50)
    print(run(sys.executable, "-m", "jobloop", "diagnose").strip())
    print("\n--- queue " + "-" * 55)
    phases = sorted(
        path.name
        for path in (ROOT / "progress").iterdir()
        if (path / "PROGRESS.md").is_file() and path.name.startswith("phase-")
    )
    ready = blocked = 0
    for phase in phases:
        lines = run(sys.executable, "-m", "jobloop", "--phase", phase, "status").splitlines()
        here = sum(1 for line in lines if line.startswith(" * "))
        stuck = sum(1 for line in lines if " blocked " in line)
        ready += here
        blocked += stuck
        if here or stuck:
            print(f"{phase:<22} ready {here:<3} blocked {stuck}")
    failing = [check for check in checks if check.startswith("FAIL")]
    print()
    if failing:
        print(f"VERDICT  this shift has work: {len(failing)} check(s) failing")
        return 1
    if blocked:
        print(f"VERDICT  this shift has work: {blocked} job(s) blocked")
        return 1
    if not ready:
        print("VERDICT  nothing ready and nothing blocked — the queue is genuinely empty")
        return 0
    print("VERDICT  quiet tick: the loop is working and nothing is waiting on you")
    return 0


if __name__ == "__main__":
    sys.exit(main())
