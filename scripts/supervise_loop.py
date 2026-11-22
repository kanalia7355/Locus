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
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))


def now() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def heartbeat(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{now()} {line}\n")
    print(f"{now()} {line}", flush=True)


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


def main() -> int:
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
    arguments = parser.parse_args()

    state = ROOT / ".jobloop"
    stop = state / "stop"
    beat = state / "supervisor.log"
    python = str(
        ROOT / (".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python")
    )

    phases = arguments.phases or ["phase-6-extensions"]
    heartbeat(beat, f"supervisor started for {', '.join(phases)}")
    cycle = 0
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
            worked = worked or "idle - no actionable job is left" not in output
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
            heartbeat(beat, f"cycle {cycle} idle everywhere :: {told[:600]}")
        time.sleep(arguments.pause)
    heartbeat(beat, "supervisor stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
