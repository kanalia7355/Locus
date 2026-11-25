"""Keep the job loop running when nobody is watching.

`jobloop run` is bounded on purpose: it stops at its minute budget, at its job
limit, or when nothing in the queue is actionable. Every one of those is a
normal ending, and every one of them leaves the machine idle until a person
notices. On 2026-11-18 that was seventeen hours — and the check that was
supposed to catch it reported the loop as alive, because the query matched its
own command line.

This supervisor restarts the loop after each ending and writes a heartbeat that
cannot lie: a timestamp, the exit code, and what the queue looked like.

`--phase` is repeatable, and each cycle walks the phases **one at a time**. That
is deliberate: every phase merges into the same integration branch in the same
checkout, so two of them running at once would be two processes doing git
operations on one repository. A phase with nothing actionable exits in about two
seconds, so walking all of them costs almost nothing and keeps the queue moving
to the next phase the moment one runs dry.

Stop it by creating `.jobloop/stop`. It is checked before every cycle, so the
loop finishes the job it is on rather than being cut off mid-flight.
"""

from __future__ import annotations

import argparse
import io
import math
import subprocess
import sys
import time
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
JST = timezone(timedelta(hours=9))


def now() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def heartbeat(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{now()} {line}\n")
    print(f"{now()} {line}", flush=True)


# Lines that do not amount to work: outcomes in which nothing was attempted, and
# the announcements that precede an outcome rather than being one. `dispatching`
# and `resuming` are here because they are printed *before* the model is chosen —
# a cycle whose only lines were `resuming` and `no-reviewer` was counted as work
# on the first attempt at this, and the supervisor kept polling at full rate.
# `rotated` is the same: a spent model is handed back and the next line is
# another dispatch.
#
# Deliberately a blocklist, not an allowlist of real outcomes. If a future
# outcome name is unknown here it reads as work, and the loop keeps its current
# full-rate cadence — the status quo. An allowlist would read it as nothing and
# back off while work was happening.
NON_EVENTS = (
    "idle - no actionable job is left",
    "no-model",
    "no-reviewer",
    "nothing-to-resume",
    ": dispatching",
    ": resuming",
    "rotated -",
)


def did_work(output: str) -> bool:
    """Whether a cycle actually attempted anything.

    This used to be `"idle - no actionable job is left" not in output`, which
    counted a quota outage as work: `no-model` is not the idle string, so from
    19:00 to 21:25 on 2026-11-22 the supervisor ran 47 full-rate cycles, never
    reached its idle branch, and wrote 4,197 `pushed` lines into the log — the
    noise that made a real churn signal hard to find earlier the same evening.
    """
    lines = [line for line in output.strip().splitlines() if line.strip()]
    events = [
        line
        for line in lines
        if "pushed " not in line and not any(mark in line for mark in NON_EVENTS)
    ]
    return bool(events)


def backoff(pause: float, idle_rounds: int) -> float:
    """How long to wait after `idle_rounds` consecutive walks that did nothing.

    Doubling, capped at ten times the configured pause. A six-hour cooldown does
    not need a visit every two minutes, and the first cycle that attempts
    anything resets the count — so the cost of being wrong is one longer wait,
    not a stalled queue.
    """
    return float(min(pause * (2.0**idle_rounds), pause * 10))


# A positive margin: waking exactly at expiry can miss by a few seconds of
# clock skew and waste another full backoff window, which is the bug this cap
# exists to prevent.
IDLE_COOLDOWN_MARGIN = 30.0


def cooldown_wait(
    state_file: Path, models: list[str], now: float, margin: float = IDLE_COOLDOWN_MARGIN
) -> float | None:
    """Seconds until the earliest provided-model cooldown expires, plus margin.

    Only models the CLI currently offers count. A stale record for a model no
    longer provided must not shorten the wait — that would be the same stale-
    record bug as T-PH9-407, in a different place. Returns None when no
    provided model is on cooldown, so the caller keeps its normal backoff.
    """
    if not models or margin <= 0:
        return None
    from jobloop.roster import Roster

    roster = Roster(models=models, state_file=state_file, now=now)
    state = roster._state()
    soonest: float | None = None
    for name in roster.models:
        entry = state.get(name)
        if not isinstance(entry, dict):
            continue
        try:
            until = float(entry.get("cooldown_until", 0))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(until):
            continue
        remaining = until - now
        if remaining <= 0:
            continue
        wait = remaining + margin
        if soonest is None or wait < soonest:
            soonest = wait
    return soonest


def idle_wait(
    pause: float,
    idle_rounds: int,
    *,
    state_file: Path,
    models: list[str],
    now: float,
    margin: float = IDLE_COOLDOWN_MARGIN,
) -> float:
    """Backoff, capped at the earliest provided-model cooldown expiry.

    When a provided model comes back before the backoff would wake, wait for
    that return instead of sleeping through it. When no cooldown is near — all
    far away, none recorded, or no provided models — the backoff is unchanged.
    """
    waiting = backoff(pause, idle_rounds)
    cap = cooldown_wait(state_file, models, now, margin=margin)
    if cap is not None:
        waiting = min(waiting, cap)
    return waiting


def tail_of(output: str) -> str:
    """The last few lines of a cycle's output, minus what is already in the log.

    `Controller.note` writes its own timestamped `run ::` lines to this same
    file, so folding the child's last three lines in verbatim repeated them: the
    cycle line for `T-STC-001` on 2026-11-22 carried its `no-model` outcome
    three times over. What belongs here is whatever the child said that the log
    does not already have.
    """
    lines = [
        line.strip()
        for line in output.strip().splitlines()
        if line.strip() and " run :: " not in line
    ]
    return "; ".join(lines[-3:]) or "(no output)"


def stream(argv: list[str]) -> tuple[int, str]:
    """Run a cycle, showing its output live and returning it as well.

    `capture_output=True` hid every per-job line from the console until the
    cycle ended — and a cycle's budget is forty-five minutes, so on 2026-11-22
    the owner watched the window sit silent for ten minutes and asked whether
    the loop had died. Teaching `Controller.note` to print did not help on its
    own: the print went into this pipe, not to the terminal. The output has to
    be read a line at a time and echoed as it arrives.
    """
    collected: list[str] = []
    with subprocess.Popen(  # noqa: S603 — repository entry point, no shell
        argv,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    ) as child:
        assert child.stdout is not None
        for line in child.stdout:
            collected.append(line.rstrip("\n"))
            print(line.rstrip("\n"), flush=True)
    return child.returncode, "\n".join(collected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        action="append",
        dest="phases",
        metavar="PHASE",
        help="repeatable; each cycle tries every phase in the order given",
    )
    parser.add_argument("--minutes", type=float, default=90.0, help="budget for one cycle")
    parser.add_argument("--max-jobs", type=int, default=6)
    parser.add_argument("--pause", type=float, default=120.0, help="seconds between cycles")
    parser.add_argument("--cycles", type=int, default=0, help="0 means keep going")
    arguments = parser.parse_args(argv)

    state = ROOT / ".jobloop"
    stop = state / "stop"
    beat = state / "supervisor.log"
    python = str(
        ROOT / (".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python")
    )

    phases = arguments.phases or ["phase-6-extensions"]
    heartbeat(beat, f"supervisor started for {', '.join(phases)}")
    cycle = 0
    idle_rounds = 0
    while not stop.is_file():
        cycle += 1
        if arguments.cycles and cycle > arguments.cycles:
            heartbeat(beat, f"stopping after {arguments.cycles} cycle(s)")
            break
        worked = False
        for phase in phases:
            if stop.is_file():
                break
            started = time.monotonic()
            code, output = stream(
                [
                    python,
                    "-m",
                    "jobloop",
                    "--phase",
                    phase,
                    "run",
                    "--minutes",
                    str(arguments.minutes),
                    "--max-jobs",
                    str(arguments.max_jobs),
                ]
            )
            worked = worked or did_work(output)
            spent = time.monotonic() - started
            heartbeat(
                beat,
                f"cycle {cycle} {phase} ended after {spent:.0f}s exit={code} :: {tail_of(output)}",
            )
        if stop.is_file():
            break
        if not worked:
            # Every phase found nothing to do, which with a queue full of blocked
            # jobs is the shape every multi-hour stall has taken. Ask why, in one
            # place: stops whose cause has since been repaired are restarted, and
            # a signature holding two or more jobs with no repair becomes a job.
            diagnosis = subprocess.run(  # noqa: S603 — repository entry point, no shell
                [python, "-m", "jobloop", "diagnose", "--file"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            told = "; ".join((diagnosis.stdout or "").strip().splitlines()) or "(nothing said)"
            idle_rounds += 1
            try:
                from jobloop.cli import installed_models
                from jobloop.roster import eligible

                models = eligible(installed_models())
            except Exception:
                models = []
            roster_err = io.StringIO()
            with redirect_stderr(roster_err):
                waiting = idle_wait(
                    arguments.pause,
                    idle_rounds,
                    state_file=state / "roster.json",
                    models=models,
                    now=time.time(),
                )
            err_line = "; ".join(roster_err.getvalue().strip().splitlines())
            if err_line:
                print(err_line, file=sys.stderr)
                told = f"{told}; {err_line}"
            heartbeat(
                beat,
                f"cycle {cycle} idle everywhere, waiting {waiting:.0f}s :: {told[:600]}",
            )
        else:
            idle_rounds = 0
            waiting = arguments.pause
        time.sleep(waiting)
    heartbeat(beat, "supervisor stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
