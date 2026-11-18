"""Keep the job loop running when nobody is watching.

`jobloop run` is bounded on purpose: it stops at its minute budget, at its job
limit, or when nothing in the queue is actionable. Every one of those is a
normal ending, and every one of them leaves the machine idle until a person
notices. On 2026-11-18 that was seventeen hours — and the check that was
supposed to catch it reported the loop as alive, because the query matched its
own command line.

This supervisor restarts the loop after each ending and writes a heartbeat that
cannot lie: a timestamp, the exit code, and what the queue looked like.

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", default="phase-6-extensions")
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

    heartbeat(beat, f"supervisor started for {arguments.phase}")
    cycle = 0
    while not stop.is_file():
        cycle += 1
        if arguments.cycles and cycle > arguments.cycles:
            heartbeat(beat, f"stopping after {arguments.cycles} cycle(s)")
            break
        started = time.monotonic()
        result = subprocess.run(  # noqa: S603 — repository entry point, no shell
            [
                python,
                "-m",
                "jobloop",
                "--phase",
                arguments.phase,
                "run",
                "--minutes",
                str(arguments.minutes),
                "--max-jobs",
                str(arguments.max_jobs),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        spent = time.monotonic() - started
        tail = "; ".join((result.stdout or "").strip().splitlines()[-3:]) or "(no output)"
        heartbeat(
            beat, f"cycle {cycle} ended after {spent:.0f}s exit={result.returncode} :: {tail}"
        )
        if result.returncode != 0 and (result.stderr or "").strip():
            heartbeat(
                beat, f"cycle {cycle} stderr :: {result.stderr.strip().splitlines()[-1][:300]}"
            )
        if stop.is_file():
            break
        time.sleep(arguments.pause)
    heartbeat(beat, "supervisor stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
