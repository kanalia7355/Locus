"""Command line entry point: `python -m jobloop <command>`.

Commands are deliberately boring: inspect what the loop sees (`status`, `plan`,
`doctor`) and run bounded work (`run`, `run-one`). Nothing here can approve an
owner decision or reach `main`.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

from jobloop.controller import Controller, Settings, git
from jobloop.roster import Roster, eligible
from jobloop.tasks import ATTEMPT_LIMIT, load_phase

ROOT = Path(__file__).resolve().parents[1]


def installed_models(executable: str | None = None) -> list[str]:
    binary = executable or shutil.which("opencode")
    if not binary:
        return []
    result = subprocess.run(  # noqa: S603 — fixed CLI, no shell
        [binary, "models"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    if result.returncode:
        return []
    return [line.strip() for line in result.stdout.splitlines() if "/" in line]


def build(arguments: argparse.Namespace) -> Controller:
    settings = Settings(
        repository=ROOT,
        phase=arguments.phase,
        python=arguments.python,
        integration_branch=arguments.branch,
        push=getattr(arguments, "push", False),
    )
    roster = Roster(
        models=eligible(installed_models()),
        state_file=settings.state_directory / "roster.json",
        now=time.time(),
    )
    return Controller(settings, roster)


def report(controller: Controller) -> int:
    phase = load_phase(controller.settings.phase_directory)
    print(f"phase {phase.slug}: {len(phase.tasks)} job(s)")
    for task in phase.tasks:
        mark = "*" if task.actionable else " "
        print(
            f" {mark} {task.id:<12} {task.status:<8} attempts {task.attempts}/{ATTEMPT_LIMIT}"
            f"  {task.weight or '-':<7} {task.model or '-'}"
        )
    print(f"available models: {', '.join(controller.roster.available()) or 'none'}")
    if phase.decisions_file.is_file():
        print(f"owner decisions pending in {phase.decisions_file.relative_to(ROOT).as_posix()}")
    return 0


def doctor(controller: Controller) -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("opencode", bool(shutil.which("opencode")), "free worker CLI"))
    checks.append(
        ("models", bool(controller.roster.models), f"{len(controller.roster.models)} eligible")
    )
    checks.append(
        (
            "reviewer",
            len(controller.roster.available()) >= 2,
            "a second model is needed for independent review",
        )
    )
    checks.append(
        ("phase", controller.settings.phase_directory.is_dir(), str(controller.settings.phase))
    )
    checks.append(
        ("python", Path(controller.settings.python).is_file(), controller.settings.python)
    )
    branches = {
        line.strip()
        for line in git(ROOT, "branch", "--format=%(refname:short)", check=False).splitlines()
    }
    checks.append(
        (
            "branch",
            controller.settings.integration_branch in branches,
            controller.settings.integration_branch,
        )
    )
    for name, ok, detail in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {name:<10} {detail}")
    return 0 if all(ok for _, ok, _ in checks) else 1


def main(argv: list[str] | None = None) -> int:
    # The repository is full of Japanese text; a cp932 console must not turn a
    # report into a crash.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="jobloop", description=__doc__)
    parser.add_argument("--phase", default="phase-4-closeout")
    parser.add_argument("--branch", default="loop/local-development")
    parser.add_argument(
        "--python",
        default=str(
            ROOT / (".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python")
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="show what the loop sees")
    commands.add_parser("doctor", help="check the loop can run at all")
    commands.add_parser("plan", help="show the job the loop would pick next")
    one = commands.add_parser("run-one", help="run the next job through one full cycle")
    one.add_argument(
        "--push", action="store_true", help="push the integration branch after merging"
    )
    run = commands.add_parser("run", help="run jobs until the deadline or the queue empties")
    run.add_argument("--minutes", type=float, default=60.0)
    run.add_argument("--max-jobs", type=int, default=20)
    run.add_argument("--push", action="store_true")
    arguments = parser.parse_args(argv)
    controller = build(arguments)
    if arguments.command == "status":
        return report(controller)
    if arguments.command == "doctor":
        return doctor(controller)
    if arguments.command == "plan":
        task = controller.select()
        print(f"next: {task.id} ({task.weight})" if task else "next: nothing actionable")
        return 0
    if arguments.command == "run-one":
        task = controller.select()
        if task is None:
            print("nothing actionable")
            return 0
        outcome = controller.run_job(task)
        print(outcome.line)
        return 0 if outcome.state in {"delivered", "escalated"} else 1
    outcomes = controller.run(minutes=arguments.minutes, max_jobs=arguments.max_jobs)
    for outcome in outcomes:
        print(outcome.line)
    escalated = [outcome for outcome in outcomes if outcome.state == "escalated"]
    if escalated:
        print(f"\n{len(escalated)} job(s) need an owner decision:")
        for outcome in escalated:
            print(f"  - {outcome.line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
