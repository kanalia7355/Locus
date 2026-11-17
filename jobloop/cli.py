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
        unmet = phase.unmet(task)
        mark = "*" if phase.ready(task) else " "
        waiting = f"  waits for {', '.join(unmet)}" if unmet else ""
        print(
            f" {mark} {task.id:<12} {task.status:<8} attempts {task.attempts}/{ATTEMPT_LIMIT}"
            f"  {task.weight or '-':<7} {task.model or '-'}{waiting}"
        )
    print(f"available models: {', '.join(controller.roster.available()) or 'none'}")
    unanswered = phase.open_decisions
    if unanswered:
        location = phase.decisions_file.relative_to(ROOT).as_posix()
        print(f"{len(unanswered)} owner decision(s) unanswered in {location}")
        for heading in unanswered:
            print(f"   ? {heading}")
    return 0


def explain(controller: Controller) -> int:
    """Rewrite the open questions as a page the owner can decide from.

    The loop writes `OWNER_DECISIONS.md` for itself — requirement ids, paths,
    failure modes. Asking an owner to answer from that is asking them to read the
    loop's notes. `scripts/explain_decisions.py` hands the same text to Hydrogen
    and gets back one plain-language page. A failure here never fails the run:
    the questions are already recorded, this is only how they are presented.
    """
    script = ROOT / "scripts" / "explain_decisions.py"
    result = subprocess.run(  # noqa: S603 — repository script, resolved interpreter
        [controller.settings.python, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1200,
        check=False,
    )
    print((result.stdout or result.stderr).strip()[:2000])
    return result.returncode


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
    commands.add_parser("explain", help="rewrite open owner questions as a plain-language page")
    one = commands.add_parser("run-one", help="run the next job through one full cycle")
    one.add_argument(
        "--push", action="store_true", help="push the integration branch after merging"
    )
    again = commands.add_parser(
        "resume-one",
        help="re-check an existing workspace after a ruling, without a new attempt",
    )
    again.add_argument("task", help="task id, for example T-PH5-101")
    again.add_argument("--push", action="store_true")
    run = commands.add_parser("run", help="run jobs until the deadline or the queue empties")
    run.add_argument("--minutes", type=float, default=60.0)
    run.add_argument("--max-jobs", type=int, default=20)
    # Pushing is the default for an unattended run. It was opt-in, and the
    # consequence was 30 commits sitting only on this machine for a day —
    # work that looked done but was nowhere anyone else could see it.
    run.add_argument("--no-push", dest="push", action="store_false", default=True)
    arguments = parser.parse_args(argv)
    controller = build(arguments)
    if arguments.command == "status":
        return report(controller)
    if arguments.command == "doctor":
        return doctor(controller)
    if arguments.command == "explain":
        return explain(controller)
    if arguments.command == "plan":
        task = controller.select()
        print(f"next: {task.id} ({task.weight})" if task else "next: nothing actionable")
        return 0
    if arguments.command == "resume-one":
        wanted = [task for task in controller.jobs() if task.id == arguments.task]
        if not wanted:
            print(f"no job named {arguments.task}")
            return 1
        outcome = controller.resume(wanted[0])
        print(outcome.line)
        return 0 if outcome.state in {"delivered", "escalated"} else 1
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
    if arguments.push:
        # Not only after a merge: a run that produced nothing but rulings and
        # loop repairs still has commits, and they belong on the remote too.
        branch = controller.settings.integration_branch
        try:
            git(controller.settings.repository, "push", "origin", branch)
            print(f"pushed {branch}")
        except RuntimeError as error:
            print(f"push failed: {error}")
    escalated = [outcome for outcome in outcomes if outcome.state == "escalated"]
    if escalated:
        print(f"\n{len(escalated)} job(s) need an owner decision:")
        for outcome in escalated:
            print(f"  - {outcome.line}")
        # An unattended run can stop overnight on a question. Leave it already
        # written in language the owner can answer from, not in the loop's own.
        explain(controller)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
