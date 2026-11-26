"""The four checks that open an orchestrator shift, as one command.

A checklist spread over four commands does not get run on a tired wake-up, and
each of these four exists because skipping it cost hours. One command, ten
lines of output, and a verdict line that says whether the shift has work.

Read `.agents/skills/orchestrator-shift/SKILL.md` for why each check is here.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))


def installed_models() -> list[str]:
    """Every model identifier the loop can reach, for quota counting.

    Both tiers, because the roster the controller builds has both: counting only
    the first one made this check report `0 available` on 2026-11-25 while the
    second tier was in fact answering. A check that cannot see what the loop uses
    reports a dead loop as dead when it is working — the same class of lie as
    matching on `CommandLine`, which reported a dead loop as alive for 17 hours.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from jobloop.cli import agy_installed_models
    from jobloop.cli import installed_models as cli_installed_models

    return cli_installed_models() + agy_installed_models()


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


def say(text: str = "", stream: TextIO | None = None) -> None:
    """Print a line that the console's own encoding may not be able to carry.

    A Japanese Windows console hands Python a cp932 stdout, and cp932 has no em
    dash. On 2026-11-22 this script died with `UnicodeEncodeError` *inside the
    open-stops section*, at the moment it had something to report: the stop
    record it was relaying carried an em dash, and so does the
    `genuinely empty` verdict below. The whole point of this script is to be the
    one command a tired shift runs, so it must never fail on the shape of a
    character. Replace what the console cannot encode and keep going.
    """
    out = sys.stdout if stream is None else stream
    try:
        out.write(text + "\n")
    except UnicodeEncodeError:
        encoding = getattr(out, "encoding", None) or "utf-8"
        out.write(text.encode(encoding, "replace").decode(encoding, "replace") + "\n")


def stranded_merge() -> str:
    """A half-finished merge makes every later job report a dirty branch."""
    if (ROOT / ".git" / "MERGE_HEAD").exists():
        head = (ROOT / ".git" / "MERGE_HEAD").read_text(encoding="utf-8").strip()[:12]
        return f"FAIL  a merge is in progress ({head}); every later job will report a dirty branch"
    conflicted = run("git", "diff", "--name-only", "--diff-filter=U", quiet=True).split()
    if conflicted:
        return f"FAIL  unresolved conflicts: {', '.join(conflicted[:5])}"
    return "ok    no merge left in progress"


WORKER_SESSION_SHAPES: dict[str, str] = {
    "run_standalone": "run --standalone",
    "serve_stdio": "serve --stdio",
    "agy_session": "agy --input-format stream-json",
}


def processes() -> list[tuple[int, int, str, str, str | None]]:
    """`(pid, parent, name, created, kind)` for the loop's own processes.

    Queried by image name. Matching on the command line alone returns the
    querying shell itself, which is how a dead loop was reported as alive for
    seventeen hours on 2026-11-18.

    `kind` is one of ``"run_standalone"``, ``"serve_stdio"``, ``"serve_service"``
    for an ``opencode.exe`` worker, ``"agy_session"`` for a second-tier
    ``agy.EXE`` worker, otherwise ``None``. ``serve --service`` is the
    long-lived helper the user's own shell started (parentless by nature) —
    never report it as an orphan. ``agy.EXE`` has no running resident helper by
    default (measured: ``agy remote-control status`` is unregistered), and its
    loop-dispatched sessions always carry ``--input-format stream-json``, so
    interactive or subcommand invocations (``remote-control``, ``acp``,
    ``mic-serve``) are left as ``None`` rather than treated as job sessions.
    """
    if sys.platform != "win32":
        return []
    script = (
        "Get-CimInstance Win32_Process -Filter "
        "\"Name = 'python.exe' or Name = 'opencode.exe' or Name = 'agy.EXE'\" "
        "| ForEach-Object { "
        "'{0}|{1}|{2}|{3}|{4}' -f $_.ProcessId, $_.ParentProcessId, $_.Name, "
        "$_.CreationDate.ToString('s'), $_.CommandLine }"
    )
    found: list[tuple[int, int, str, str, str | None]] = []
    for line in run("powershell", "-NoProfile", "-Command", script).splitlines():
        parts = line.split("|", 4)
        if len(parts) < 5 or not parts[0].strip().isdigit():
            continue
        pid, parent, name, created, command = parts
        image = name.strip()
        lower_image = image.lower()
        if (
            "jobloop" in command
            or "supervise_loop" in command
            or lower_image in {"opencode.exe", "agy.exe"}
        ):
            kind: str | None = None
            if lower_image == "opencode.exe":
                if "serve --service" in command:
                    kind = "serve_service"
                elif "serve --stdio" in command:
                    kind = "serve_stdio"
                elif "run --standalone" in command:
                    kind = "run_standalone"
            elif lower_image == "agy.exe":
                if "--input-format stream-json" in command and "--print" in command:
                    kind = "agy_session"
            elif lower_image == "python.exe":
                if "supervise_loop" in command:
                    kind = f"supervisor:{command.strip()}"
                elif "jobloop" in command:
                    kind = "jobloop_run"
            found.append((int(pid), int(parent), image, created.strip(), kind))
    return found


def running(pid: int) -> bool:
    """Whether a process id exists at all, whatever its image name is."""
    if sys.platform != "win32":
        return True
    found = run(
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' | Measure-Object).Count",
    )
    return "0" not in found.split()


def orphans(live: list[tuple[int, int, str, str, str | None]]) -> str:
    """A job session whose parent is gone writes where nobody reads.

    The parent is looked up by id, not searched for in the list above. Testing
    membership of a list filtered to `python.exe`/`opencode.exe`/`agy.EXE`
    called every live worker an orphan, because npm launches `opencode` through
    a `cmd.exe` shim that the filter never collected. On 2026-11-22 that false
    positive told the orchestrator to `taskkill` a worker that was eleven
    minutes into its job — a check that destroys work is worse than no check.
    """
    loose: list[tuple[int, str, str]] = []  # (pid, created, shape)
    for pid, parent, _name, created, kind in live:
        if kind not in WORKER_SESSION_SHAPES:
            continue
        if not running(parent):
            loose.append((pid, created, WORKER_SESSION_SHAPES[kind]))
    if not loose:
        return "ok    no orphaned worker"
    named = ", ".join(
        f"{pid} ({shape}, started {created[:16]})" for pid, created, shape in loose[:4]
    )
    return f"FAIL  orphaned worker session: {named} — taskkill /PID <id> /T /F"


def supervisor(live: list[tuple[int, int, str, str, str | None]]) -> str:
    sup_by_pid = {
        pid: (parent, kind)
        for pid, parent, name, _, kind in live
        if name.lower() == "python.exe" and kind != "jobloop_run"
    }
    loop_pids = [
        pid
        for pid, (parent, kind) in sup_by_pid.items()
        if not (parent in sup_by_pid and sup_by_pid[parent][1] == kind)
    ]
    workers = [pid for pid, _, _, _, kind in live if kind in WORKER_SESSION_SHAPES]
    worker_note = f", {len(workers)} worker(s) alive" if workers else ""
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
    if not loop_pids:
        return f"FAIL  no jobloop or supervisor process{worker_note}{age}"
    pid_note = f" (pids: {', '.join(str(pid) for pid in loop_pids)})" if len(loop_pids) >= 2 else ""
    return f"ok    {len(loop_pids)} loop process(es) alive{pid_note}{worker_note}{age}"


def churn() -> str:
    """Work that repeats without finishing, which no open stop reports.

    A job can be resumed every cycle and get no further: on 2026-11-22
    `T-PH6-104` and `T-PH8-302` were handed a reviewer that answered
    `unavailable`, which escalates nothing, so `diagnose` saw an empty queue of
    stops and this script printed `quiet tick` while two jobs span for an hour.
    "Nothing is waiting on a decision" is not the same as "something is moving".
    """
    beat = ROOT / ".jobloop" / "supervisor.log"
    if not beat.is_file():
        return "ok    no repeating outcome in the log"
    # Bounded by time, not by line count. A line window keeps re-reporting
    # churn that has already been fixed, which is the trap `diagnose` avoids
    # with its dates: a stop older than its repair is not news.
    since = (datetime.now(JST) - timedelta(hours=1)).isoformat()
    recent = [
        line
        for line in beat.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-400:]
        if line[:25] >= since
    ]
    # `rotated` and `no-reviewer` are left out: both are bounded, cheap
    # reactions to an empty roster that end the cycle in about two seconds.
    # `no-reviewer` was in this list for twenty minutes on 2026-11-22, added
    # while it still re-ran a job's whole gate suite every two minutes. Once
    # that was fixed the repetition became what a correct wait looks like, and
    # a check that fails on correct behaviour trains the reader to ignore it.
    counted: dict[str, int] = {}
    latest: dict[str, str] = {}
    for line in recent:
        # Count the per-job lines only. A cycle's closing line repeats every
        # outcome it saw, so each event was counted twice and `T-PH6-104` was
        # reported as `x6` for three occurrences on 2026-11-22. An inflated
        # count is not a false alarm by itself, but it makes the number useless
        # for deciding whether something is getting worse.
        if " run :: " not in line:
            continue
        for mark in ("review-unavailable", "gates-failed", "nothing-to-resume"):
            if mark in line:
                for part in line.split("::")[-1].split(";"):
                    if mark in part:
                        job = part.strip().split(":")[0].strip()
                        counted[f"{job} {mark}"] = counted.get(f"{job} {mark}", 0) + 1
                        latest[f"{job} {mark}"] = max(latest.get(f"{job} {mark}", ""), line[:25])
    # Twice is already a repeat. The threshold was three, and the churn that
    # prompted this check sat at two for an hour — read by a person, not by this.
    repeating = {key: count for key, count in counted.items() if count >= 2}
    if not repeating:
        return "ok    no repeating outcome in the log"
    # Say when it last happened, and stop failing once it has stopped. The hour
    # window cannot tell that a cause was repaired inside it, so on 2026-11-22
    # this still reported `T-PH6-104 nothing-to-resume x4` for twenty-eight
    # minutes after the controller fix that ended it — the `diagnose` trap of
    # re-reporting a stop that predates its own repair. A mark that has not
    # recurred for a quarter of an hour, across roughly seven cycles, is
    # history; the count and the time are still printed either way.
    freshest = max(latest.get(key, "") for key in repeating)
    stale = freshest < (datetime.now(JST) - timedelta(minutes=15)).isoformat()
    named = ", ".join(
        f"{key} x{count} (last {latest.get(key, '?')[11:16]})"
        for key, count in sorted(repeating.items())[:4]
    )
    if stale:
        return f"ok    a repeat stopped more than 15 min ago: {named}"
    return f"FAIL  the same outcome keeps repeating: {named}"


def quota() -> str:
    """Report model availability among models currently provided by the CLI.

    The denominator is the provided/eligible set, not every model ever recorded
    in roster.json. Models only present in the record are not counted in the
    main number because Roster.available() intersects recorded cooldowns with
    the currently provided models.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from jobloop.roster import Roster, eligible, preferred_divergence

    now = time.time()
    raw_installed = installed_models()
    provided = eligible(raw_installed)
    state_file = ROOT / ".jobloop" / "roster.json"
    roster = Roster(models=provided, state_file=state_file, now=now)
    available = roster.available()
    provided_count = len(provided)
    available_count = len(available)
    resting_count = provided_count - available_count

    line = (
        f"ok    提供 {provided_count} 件のうち {resting_count} 件が冷却中、"
        f"使えるのは {available_count} 件"
    )
    if resting_count > 0:
        try:
            recorded = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            recorded = {}
        if isinstance(recorded, dict):
            available_set = set(available)
            resting_left = {
                name: entry["cooldown_until"] - now
                for name, entry in recorded.items()
                if name in set(provided)
                and name not in available_set
                and isinstance(entry, dict)
                and entry.get("cooldown_until", 0) - now > 0
            }
            if resting_left:
                soonest = min(resting_left.values()) / 60
                line += f", soonest back in {soonest:.0f} min"
    missing, unlisted = preferred_divergence(raw_installed)
    if not missing and not unlisted:
        line += "\nok    PREFERRED と提供無料枠の乖離なし"
    else:
        parts: list[str] = []
        if missing:
            parts.append(f"PREFERRED のみ {len(missing)} 件 ({', '.join(missing)})")
        if unlisted:
            parts.append(f"未登録の無料枠 {len(unlisted)} 件 ({', '.join(unlisted)})")
        line += f"\nok    PREFERRED 乖離: {'; '.join(parts)}"
    return line


def main() -> int:
    live = processes()
    checks = [stranded_merge(), orphans(live), supervisor(live), churn(), quota()]
    busy = (ROOT / ".jobloop" / "orchestrator-busy").exists()
    checks.append(
        "WARN  .jobloop/orchestrator-busy is set — containment is unverified while it is"
        if busy
        else "ok    orchestrator-busy is clear"
    )
    say("\n".join(checks))
    say("\n--- open stops " + "-" * 50)
    say(run(sys.executable, "-m", "jobloop", "diagnose").strip())
    say("\n--- queue " + "-" * 55)
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
            say(f"{phase:<22} ready {here:<3} blocked {stuck}")
    failing = [check for check in checks if check.startswith("FAIL")]
    say()
    if failing:
        say(f"VERDICT  this shift has work: {len(failing)} check(s) failing")
        return 1
    if blocked:
        say(f"VERDICT  this shift has work: {blocked} job(s) blocked")
        return 1
    if not ready:
        say("VERDICT  nothing ready and nothing blocked — the queue is genuinely empty")
        return 0
    say("VERDICT  quiet tick: the loop is working and nothing is waiting on you")
    return 0


if __name__ == "__main__":
    sys.exit(main())
