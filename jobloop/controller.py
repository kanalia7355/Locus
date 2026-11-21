"""Drive one job at a time: dispatch, verify, review, commit, or ask the owner.

The loop is deterministic; the models are not trusted with any decision that has
consequences. Every path out of a job is recorded in the job file, and the only
path that reaches a commit is: in scope, verification green, independent review
approved by a different model.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import time
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobloop import gates, prompts, selfrepair, worker
from jobloop.roster import Roster
from jobloop.tasks import ATTEMPT_LIMIT, REVIEW_CYCLE_LIMIT, Task, load_phase

JST = timezone(timedelta(hours=9))
GIT = shutil.which("git") or "git"
SLUG = re.compile(r"[^a-z0-9]+")


@dataclass
class Settings:
    repository: Path
    phase: str
    python: str
    integration_branch: str = "loop/local-development"
    # A worker reads the files it touches, writes a test, and runs the whole
    # verification command itself — on a job touching `App.tsx` (1979 lines) the
    # frontend suite alone is ~25s and the reading dwarfs it. 900s was chosen to
    # fit a foreground tool call, not from measurement, and it timed out two jobs
    # on 2026-11-17 while a trivial prompt to the same model answered in a second.
    # The loop runs in the background now, so the budget can match the work.
    worker_timeout: float = 1800.0
    gate_timeout: float = 1800.0
    review_timeout: float = 1200.0
    push: bool = False

    @property
    def phase_directory(self) -> Path:
        return self.repository / "progress" / self.phase

    @property
    def state_directory(self) -> Path:
        return self.repository / ".jobloop"

    @property
    def workspace_root(self) -> Path:
        """Job workspaces live outside the repository, and are clones, not worktrees.

        A linked worktree's `.git` is a file pointing back into the main
        repository, so a session started inside one resolves its project root to
        the main checkout and edits it — observed three times on 2026-11-15, with
        the worktree left untouched. A local clone has its own `.git` and no link
        back, which is what actually isolates a worker.
        """
        return self.repository.parent / f".jobloop-{self.repository.name}" / "workspaces"


@dataclass
class Outcome:
    """What happened to one job, in the controller's own words."""

    task_id: str
    state: str
    detail: str
    model: str = ""
    reviewer: str = ""
    gates: list[gates.Gate] = field(default_factory=list)

    @property
    def line(self) -> str:
        return f"{self.task_id}: {self.state} - {self.detail}"


def git(repository: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(  # noqa: S603 — resolved git path, no shell
        [GIT, *arguments],
        cwd=str(repository),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


# A verdict is one line that says only APPROVED. Markdown emphasis is part of
# how models write a heading answer, and refusing it threw away a real approval:
# on 2026-11-20 `T-PH6-113`'s reviewer replied `**APPROVED**` with `none` under
# FINDINGS, the old pattern did not match the asterisks, and the job was blocked
# at the review cycle limit as though changes were still required.
# Leading bullets and quote marks are allowed; trailing prose is not, so
# "NOT APPROVED" or "APPROVED with reservations" still counts as changes.
APPROVAL = re.compile(r"^[\s>#*_`-]*APPROVED[\s*_`.]*$", re.MULTILINE)


def placeholder(text: str) -> str | bool:
    """True when a reported question is the brief's own placeholder, not a question."""
    stripped = text.strip()
    return (
        len(stripped) < 12
        or (stripped.startswith("<") and stripped.endswith(">"))
        or "<the question>" in stripped
        or stripped in {"the question", "<question>"}
    )


def slug(text: str) -> str:
    return SLUG.sub("-", text.lower()).strip("-")[:40]


class Controller:
    def __init__(self, settings: Settings, roster: Roster, *, clock: object | None = None) -> None:
        self.settings = settings
        self.roster = roster
        self.clock = clock if callable(clock) else time.monotonic
        self.dispatch = worker.run

    # --- job selection -------------------------------------------------------

    def jobs(self) -> list[Task]:
        return load_phase(self.settings.phase_directory).tasks

    def points_outside(self, task: Task) -> str:
        """The main-checkout path a worker would find by reading its own job file.

        Sanitising the brief is not enough: the brief tells the worker the job
        file is in its workspace, the worker opens it, and an absolute path in
        the frontmatter reads as "the project is over there". On 2026-11-15 a
        worker said so in its own report — it ran the interpreter from the main
        checkout because the workspace had no `.venv` — and on 2026-11-16 the
        `T-PH6-103` worker went further and edited the main checkout. The path
        must not be in the file at all.
        """
        text = task.path.read_bytes().decode("utf-8")
        root = str(self.settings.repository)
        for form in {root, root.replace("\\", "/"), root.replace("/", "\\")}:
            if form in text:
                return form
        return ""

    def select(self) -> Task | None:
        """The next job the controller may spend an attempt on, lightest first."""
        order = {"light": 0, "medium": 1, "heavy": 2}
        phase = load_phase(self.settings.phase_directory)
        ready = [task for task in phase.tasks if phase.ready(task)]
        return min(ready, key=lambda task: (order.get(task.weight, 3), task.id), default=None)

    # --- recording -----------------------------------------------------------

    def now(self) -> str:
        return datetime.now(JST).replace(microsecond=0).isoformat()

    def record(self, task: Task, heading: str, body: str) -> None:
        from jobloop.tasks import append_section

        # Redact the main checkout's path. Gate output quotes real commands, and
        # a recorded failure once wrote `C:\...\Locus\.venv\...` into the job
        # file — which `points_outside` then refused to dispatch. The loop was
        # poisoning itself with its own evidence.
        root = str(self.settings.repository)
        for form in {root, root.replace("\\", "/"), root.replace("/", "\\")}:
            body = body.replace(form, "<repository>")
        append_section(task.path, heading, body)

    def set_fields(self, task: Task, **updates: str) -> Task:
        from jobloop.tasks import update_fields

        return update_fields(task.path, dict(updates), timestamp=self.now())

    @staticmethod
    def reread(task: Task) -> Task:
        """Re-read a job from disk, after `record` appended to the file it came from."""
        from jobloop.tasks import parse

        return parse(task.path)

    def sweep(self, task: Task, tree: Path) -> set[str]:
        """Delete the scratch a worker left behind, and say so. Returns what went.

        Called twice per attempt, and the first call is the one that matters.
        Running it only after a dispatch left the previous attempt's scratch
        sitting in the workspace, where the *next* worker found files it was
        forbidden to touch and stopped to ask about them — `T-PH6-126` asked
        about 26 of them and `T-PH7-222` about an `attack_pattern.txt` that was
        failing the secret scan. Both questions were the loop's to answer, and
        the answer is to have swept before the worker ever saw them.
        """
        names = gates.changed_files(tree)
        readable = self.texts(tree, [*names, *self.in_scope_files(tree, task.allowed_paths)])
        dropped = set(gates.litter(names, task.allowed_paths, contents=readable))
        dropped &= self.untracked(tree)
        if not dropped:
            return set()
        self.discard(tree, dropped)
        self.record(
            task,
            f"WORKER LITTER REMOVED ({self.now()})",
            f"{len(dropped)} file(s) outside `allowed_paths` that nothing in the change "
            f"refers to were deleted: {', '.join(sorted(dropped))}.\n"
            "These are command output and one-off probes — a worker reading a result by "
            "writing it to a file. The brief forbids it in so many words, so this is a "
            "deviation and not a scope drawn too narrowly; it is recorded here rather than "
            "stopping the job because the instruction has not taken with these models and "
            "nine jobs have been lost to it. Nothing inside `allowed_paths` was touched, "
            "and no scope or acceptance criterion was changed.",
        )
        return dropped

    @staticmethod
    def in_scope_files(worktree: Path, allowed: list[str]) -> list[str]:
        """Every file the job may write, expanded from `allowed_paths`.

        The reference check reads these and not only the changed files: a worker
        can add a module outside its scope and import it from a file it was
        allowed to touch but did not change, and that import has to count.
        """
        found: list[str] = []
        for entry in allowed:
            target = worktree / entry.replace("\\", "/").rstrip("/")
            if target.is_file():
                found.append(entry.replace("\\", "/").rstrip("/"))
            elif target.is_dir():
                found.extend(
                    path.relative_to(worktree).as_posix()
                    for path in target.rglob("*")
                    if path.is_file() and ".git" not in path.parts
                )
        return found

    @staticmethod
    def texts(worktree: Path, names: list[str]) -> dict[str, str]:
        """Read the changed files, so a path can be told from a reference to it.

        Unreadable or binary files come back empty: a file whose text cannot be
        read simply mentions nothing, which is the safe direction — the loop then
        treats a loose path as real work and stops the job rather than deleting it.
        """
        found: dict[str, str] = {}
        for name in names:
            path = worktree / name
            if not path.exists():
                # Deleted in this change: it has no text, and it cannot be the
                # file that references anything.
                found[name] = ""
                continue
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            try:
                found[name] = path.read_bytes().decode("utf-8", errors="replace")
            except OSError:
                continue
        return found

    @staticmethod
    def untracked(worktree: Path) -> set[str]:
        """Paths git does not track, so a reviewer's own output can be told apart."""
        lines = git(
            worktree, "status", "--porcelain=1", "--untracked-files=all", check=False
        ).splitlines()
        return {line[3:].strip() for line in lines if line.startswith("??")}

    @staticmethod
    def discard(worktree: Path, names: set[str]) -> None:
        """Delete paths inside `worktree`, refusing anything that points out of it."""
        for name in sorted(names):
            target = (worktree / name).resolve()
            if worktree.resolve() not in target.parents:
                continue
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink()

    def repair(self, task: Task, repair: selfrepair.Repair) -> None:
        """Undo one of the loop's own messes, and say in the job file that it did.

        A silent recovery is worse than the stop it replaces: the next person to
        read the file would see a job that simply worked, with no sign that the
        checks had to be cleaned up around it.
        """
        if repair.action == "clean":
            for name in repair.paths:
                target = self.settings.repository / name
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                elif target.exists():
                    target.unlink(missing_ok=True)
        elif repair.action == "redact":
            text = task.path.read_bytes().decode("utf-8")
            for form in repair.paths:
                text = text.replace(form, "<repository>")
            task.path.write_bytes(text.encode("utf-8"))
        # "sweep" needs nothing here: the page is committed with the records.
        self.record(
            task,
            f"SELF-REPAIR ({self.now()})",
            f"{repair.line}\n\npaths: {', '.join(repair.paths) or '(none)'}\n\n"
            "This was the loop's own doing, so the attempt was not charged and the "
            "job was put back in the queue. No scope was widened and no acceptance "
            "criterion was touched.",
        )

    def escalate(self, task: Task, category: str, question: str, context: str) -> Outcome:
        """Stop the job and write the owner a decision request.

        Unless the stop is one the loop caused itself and knows how to undo —
        then it undoes it, records that it did, and asks for nothing.
        """
        mend = selfrepair.classify(category, context, repository=str(self.settings.repository))
        if mend is not None:
            self.repair(task, mend)
            return Outcome(task.id, "self-repaired", mend.line)
        said = selfrepair.describe(category, context)
        if said:
            question = f"{question} — {said}"
        file = self.settings.phase_directory / "OWNER_DECISIONS.md"
        if not file.exists():
            file.write_text(
                "# Owner decisions requested by the job loop\n\n"
                "Each entry is a judgement the controller refused to make itself.\n",
                encoding="utf-8",
            )
        entry = (
            f"\n## {task.id} — {category} ({self.now()})\n\n"
            f"**Question**: {question}\n\n"
            f"**Context**\n\n{context.strip()}\n"
        )
        with file.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        self.set_fields(task, status="blocked")
        self.record(task, f"OWNER DECISION REQUESTED ({self.now()})", f"{category}: {question}")
        return Outcome(task.id, "escalated", f"{category}: {question}")

    # --- worktrees -----------------------------------------------------------

    def workspace(self, task: Task) -> Path:
        """A per-job local clone of the integration branch, outside the repository."""
        path = self.settings.workspace_root / task.id
        if path.is_dir():
            self.refresh(task, path)
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        git(
            self.settings.repository,
            "clone",
            "--local",
            "--single-branch",
            "--branch",
            self.settings.integration_branch,
            str(self.settings.repository),
            str(path),
        )
        git(path, "checkout", "-B", self.branch_for(task))
        self.share_installed_dependencies(path)
        return path

    def refresh(self, task: Task, worktree: Path) -> None:
        """Bring an existing workspace up to the integration branch.

        A clone is made once and then kept, so a job that waits days in the queue
        starts from a base that has moved under it. `T-PH6-113`'s workspace was
        three days and ten merges behind when its reviewed work was finally
        merged, and `App.tsx` conflicted — which is how a conflicted merge came
        to sit in the main checkout at all.

        Two things have to be true before anything is reset, and the first
        version of this only checked one of them.

        A clean tree is not enough. `deliver` commits the reviewed work *before*
        it tries to merge, so a job that was blocked at the merge has its work in
        a commit and a perfectly clean tree. Resetting that discarded five
        reviewed commits on 2026-11-21 — `T-PH6-104`, `T-PH7-201`, `T-PH7-223`,
        `T-PH8-301`, `T-PH8-302` — each of them work a free model had already
        got through the gates and a reviewer. So: clean tree **and** no commit the
        integration branch does not already have.
        """
        if self.dirt(worktree).strip():
            return
        git(worktree, "fetch", str(self.settings.repository), self.settings.integration_branch)
        behind = git(worktree, "rev-list", "--count", "HEAD..FETCH_HEAD", check=False).strip()
        ahead = git(worktree, "rev-list", "--count", "FETCH_HEAD..HEAD", check=False).strip()
        if not behind or behind == "0":
            return
        if ahead and ahead != "0":
            self.record(
                task,
                f"WORKSPACE NOT REBASED ({self.now()})",
                f"The workspace is {behind} commit(s) behind "
                f"`{self.settings.integration_branch}` but {ahead} commit(s) ahead of it, so it "
                "was left alone: those commits are this job's own work and a reset would "
                "destroy them. If they no longer apply, the merge will say so.",
            )
            return
        # Clean tree, so nothing of the job's own is lost by taking the new base.
        git(worktree, "reset", "--hard", "FETCH_HEAD", check=False)
        git(worktree, "checkout", "-B", self.branch_for(task), check=False)
        self.record(
            task,
            f"WORKSPACE REBASED ({self.now()})",
            f"The workspace was {behind} commit(s) behind "
            f"`{self.settings.integration_branch}` and had no work in progress, so it was "
            "reset onto the current branch. Nothing of this job's own was discarded.",
        )

    @staticmethod
    def branch_for(task: Task) -> str:
        return f"loop/{task.id}-{slug(task.section('Task definition') or task.id)}"

    def share_installed_dependencies(self, worktree: Path) -> None:
        """Link the installed, ignored dependency trees into a fresh worktree.

        A worktree is a clean checkout, so `node_modules` is absent and every
        frontend check would fail for a reason that has nothing to do with the
        job. Linking the already-installed tree keeps the gates meaningful
        without a network install. A failure here is not fatal: the affected
        gate then reports its own real failure.
        """
        # `.venv` too: `frontend/playwright.config.ts` resolves the interpreter
        # as `../.venv/Scripts/python.exe`, so without it the browser checks
        # cannot start their API fixture and every frontend job fails with
        # "the specified path was not found" — nothing to do with the change.
        for relative in ("frontend/node_modules", ".venv"):
            source = self.settings.repository / relative
            target = worktree / relative
            if not source.is_dir() or target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.symlink_to(source, target_is_directory=True)
            except OSError:
                # Windows without developer mode refuses symlinks; a junction
                # needs no privilege and behaves the same for reads.
                shell = shutil.which("cmd") or "cmd"
                subprocess.run(  # noqa: S603 — resolved shell path, mklink is a builtin
                    [shell, "/c", "mklink", "/J", str(target), str(source)],
                    capture_output=True,
                    timeout=120,
                    check=False,
                )

    @staticmethod
    def fingerprint(worktree: Path) -> str:
        """Hash the working state so a read-only reviewer can be held to it.

        An empty string means there is no signal to compare (the path is not a
        repository); callers must treat that as unverified, never as unchanged.
        """
        head = git(worktree, "rev-parse", "HEAD", check=False).strip()
        if not head:
            return ""
        return hashlib.sha256((head + Controller.dirt(worktree)).encode("utf-8")).hexdigest()

    def note(self, line: str) -> None:
        """Append one heartbeat line, in the supervisor's own format and file.

        Same file so that "when did anything last happen" has one answer; the
        writes are single short lines in append mode, which is what a log can
        take from two processes.
        """
        beat = self.settings.state_directory / "supervisor.log"
        with suppress(OSError):
            beat.parent.mkdir(parents=True, exist_ok=True)
            with beat.open("a", encoding="utf-8") as handle:
                handle.write(f"{self.now()} run :: {line}\n")

    def operator_busy(self) -> bool:
        """True while a person is editing the main checkout alongside the loop.

        Containment is judged by whether the main checkout changed during a
        dispatch, which cannot tell a worker's escape from the operator writing a
        ruling, repairing the loop or saving a report. That ambiguity blamed
        innocent jobs twice on 2026-11-17: three workers had written only inside
        their own clones and were blocked anyway.

        Suspending the comparison is worse than a perfect check and better than a
        false accusation, so it is suspended **and said out loud** — the job file
        records that containment went unverified for that cycle. The marker lives
        under `.jobloop/`, which git ignores, so creating it cannot itself look
        like an escape.
        """
        return (self.settings.state_directory / "orchestrator-busy").is_file()

    @staticmethod
    def dirt(worktree: Path) -> str:
        """Everything in the checkout that is not committed, as one string.

        Containment has to be judged on this and not on `fingerprint`, which also
        covers `HEAD`. The operator commits to the main checkout while the loop
        runs — recording a ruling, fixing the loop — and every one of those moved
        `HEAD` and was reported as "the worker wrote outside its workspace".
        That happened to `T-PH6-109` and `T-PH6-111` on 2026-11-17: both workers
        had written only inside their own clones, and both were blocked anyway.

        An escaped worker leaves files behind, so uncommitted changes are the
        signal that matters. A worker that wrote *and committed* in the main
        checkout would slip past this, but it is told not to commit, and every
        real escape so far left the tree dirty.
        """
        diff = git(worktree, "diff", "HEAD", check=False)
        untracked = git(worktree, "status", "--porcelain=1", "--untracked-files=all", check=False)
        return diff + untracked

    # --- one job -------------------------------------------------------------

    def run_job(self, task: Task) -> Outcome:
        leak = self.points_outside(task)
        if leak:
            head = task.path.read_bytes().decode("utf-8").split("\n---\n", 1)[0]
            return self.escalate(
                task,
                "the job file names another checkout",
                "The job file contains an absolute path to the main checkout, which a "
                "worker reads as the project root. Replace it with a relative path "
                "(use the bare name `python` in `test_cmd`) before dispatching.",
                # Say where it was found: in the frontmatter it is the ticket
                # being wrong and must be fixed by a person; further down it is
                # the controller's own recorded evidence, which it may redact.
                f"found={leak}\nfile={task.path.name}\n"
                f"frontmatter={'yes' if leak in head else 'no'}",
            )
        model = self.roster.pick()
        if not model:
            return Outcome(task.id, "no-model", "every eligible free model is on cooldown")
        tree = self.workspace(task)
        # Before the brief is built, not only after the worker returns: the next
        # worker must not find a previous attempt's scratch and stop to ask about
        # files it is forbidden to touch.
        self.sweep(task, tree)
        attempt = task.attempts + 1
        brief = prompts.implementer_brief(
            task,
            attempt=attempt,
            repository=str(tree),
            outside=str(self.settings.repository),
        )
        # Containment is verified, not assumed: a worker that edits the main
        # checkout has escaped, whatever its report says. Judge that on the
        # uncommitted state only — see `dirt`, and the two jobs this wrongly
        # blocked on 2026-11-17 when the operator committed mid-run.
        outside = self.dirt(self.settings.repository)
        result = self.dispatch(model, brief, cwd=tree, timeout=self.settings.worker_timeout)
        after = self.dirt(self.settings.repository)
        # Judge on what *appeared*, not on inequality. An escaping worker leaves
        # new uncommitted paths behind; nothing a worker does makes the
        # operator's own pre-existing mess disappear. Comparing the whole string
        # made the opposite direction an accusation too: on 2026-11-22
        # `T-PH7-201` was blamed at 05:56 because the orchestrator *committed*
        # mid-dispatch, so the dirt it had been carrying went away. The evidence
        # added an hour earlier is what settled it — the record said
        # `appeared:` and then nothing at all.
        moved = sorted(set(after.splitlines()) - set(outside.splitlines()))
        if moved and not self.operator_busy():
            return self.escalate(
                task,
                "worker wrote outside its workspace",
                "The main checkout changed while the job ran, so this work is unreviewable. "
                "Inspect and restore the checkout before the job is retried.",
                f"model={model}\nworkspace={tree}\n"
                f"marker={self.settings.state_directory / 'orchestrator-busy'} "
                f"present={self.operator_busy()}\n"
                f"appeared:\n" + "\n".join(moved[:25]),
            )
        if self.operator_busy():
            self.record(
                task,
                f"CONTAINMENT UNVERIFIED ({self.now()})",
                "The operator was editing the main checkout during this cycle, so the "
                "containment comparison was suspended. The worker's isolation was not "
                "verified for this attempt.",
            )
        if result.rotate:
            # Neither usage exhaustion (PROTOCOL §5.4) nor a provider outage is a
            # failed attempt: in both the model never received the job. Keeping
            # the two apart matters only in what the record says — the model is
            # put on cooldown either way, and the job keeps its attempt.
            self.roster.mark_exhausted(model)
            return Outcome(task.id, "rotated", f"{model} {result.why_rotate}", model=model)
        task = self.set_fields(task, status="doing", assignee="opencode", model=model)
        if result.ending is not worker.Ending.COMPLETED:
            return self.failed_attempt(
                task, model, f"{result.ending.value}: {'; '.join(result.errors[:3])}"
            )
        asked = re.search(r"needs-owner-decision:\s*(.+)", result.text)
        question = asked.group(1).strip() if asked else ""
        if question and not placeholder(question):
            return self.escalate(
                task,
                "worker stopped for a decision",
                question[:400],
                result.text[-2000:],
            )
        if question:
            # The brief was echoed instead of answered: that is a failed attempt,
            # not a decision for the owner.
            return self.failed_attempt(
                task, model, f"the worker echoed the status template: {question[:120]}"
            )
        names = [name for name in gates.changed_files(tree) if name not in self.sweep(task, tree)]
        if not names:
            return self.failed_attempt(task, model, "the worker changed nothing")
        checks = [gates.within_scope(names, task.allowed_paths)]
        if checks[0].green:
            checks.append(
                gates.run_command(
                    "task-verification",
                    task.test_command,
                    cwd=tree,
                    timeout=self.settings.gate_timeout,
                    python=self.settings.python,
                )
            )
            checks.extend(
                gates.python_gates(
                    tree, names, python=self.settings.python, timeout=self.settings.gate_timeout
                )
            )
            checks.extend(
                gates.frontend_gates(
                    tree, names, timeout=self.settings.gate_timeout, python=self.settings.python
                )
            )
        self.record(
            task,
            f"ATTEMPT {attempt} — implementation by {model} ({self.now()})",
            result.text.strip()[:6000]
            + "\n\n### Controller gates\n\n"
            + "\n".join(
                f"- `{gate.name}`: {'green' if gate.green else 'FAILED'}" for gate in checks
            ),
        )
        failed = [gate for gate in checks if not gate.green]
        if failed:
            if any(gate.name == "scope" for gate in failed):
                return self.escalate(
                    task,
                    "out-of-scope change",
                    "The worker needed paths outside allowed_paths; "
                    "widen the scope or split the job.",
                    failed[0].detail,
                )
            return self.failed_attempt(
                task,
                model,
                "; ".join(f"{gate.name}: {gate.detail[:200]}" for gate in failed),
            )
        return self.review(task, tree, model, checks)

    def resume(self, task: Task) -> Outcome:
        """Re-check an existing workspace and carry on, without a new attempt.

        Used after the owner or the orchestrator rules on an escalation: the work
        is already in the workspace, so re-dispatching would throw it away and
        spend an attempt on a question that has been answered.
        """
        tree = self.settings.workspace_root / task.id
        if not tree.is_dir():
            return Outcome(task.id, "no-workspace", f"{tree} does not exist")
        model = task.model or "unknown"
        names = gates.changed_files(tree)
        if not names:
            return Outcome(task.id, "nothing-to-resume", "the workspace has no changes")
        checks = [gates.within_scope(names, task.allowed_paths)]
        if checks[0].green:
            checks.append(
                gates.run_command(
                    "task-verification",
                    task.test_command,
                    cwd=tree,
                    timeout=self.settings.gate_timeout,
                    python=self.settings.python,
                )
            )
            checks.extend(
                gates.python_gates(
                    tree, names, python=self.settings.python, timeout=self.settings.gate_timeout
                )
            )
            checks.extend(
                gates.frontend_gates(
                    tree, names, timeout=self.settings.gate_timeout, python=self.settings.python
                )
            )
        self.record(
            task,
            f"RESUMED GATES ({self.now()})",
            "\n".join(
                f"- `{gate.name}`: {'green' if gate.green else 'FAILED — ' + gate.detail[:300]}"
                for gate in checks
            ),
        )
        failed = [gate for gate in checks if not gate.green]
        if failed:
            # Hand it back for a real attempt. Leaving it in `review` would make
            # the next cycle resume it again, re-running the same failing gates
            # for ever without ever spending an attempt — a resume is a free
            # re-check, not a second way to be stuck.
            self.set_fields(task, status="doing")
            return Outcome(
                task.id,
                "gates-failed",
                "; ".join(f"{gate.name}: {gate.detail[:160]}" for gate in failed),
                model=model,
            )
        task = self.set_fields(task, status="review")
        return self.review(task, tree, model, checks)

    def failed_attempt(self, task: Task, model: str, detail: str) -> Outcome:
        attempts = task.attempts + 1
        task = self.set_fields(task, attempts=str(attempts), status="doing")
        if attempts >= ATTEMPT_LIMIT:
            return self.escalate(
                task,
                "attempt limit reached",
                "Three attempts did not satisfy the acceptance criteria; "
                "the job needs a human decision.",
                detail,
            )
        return Outcome(task.id, "attempt-failed", detail, model=model)

    # --- review --------------------------------------------------------------

    def review(self, task: Task, tree: Path, model: str, checks: list[gates.Gate]) -> Outcome:
        refused: tuple[str, ...] = ()
        while True:
            outcome, again = self.review_once(task, tree, model, checks, refused=refused)
            if again is None:
                return outcome
            refused += (again,)
            task = self.reread(task)

    def review_once(
        self,
        task: Task,
        tree: Path,
        model: str,
        checks: list[gates.Gate],
        *,
        refused: tuple[str, ...] = (),
    ) -> tuple[Outcome, str | None]:
        """One review pass. The second element names a reviewer to try after, if any."""
        reviewer = self.roster.pick(exclude=(model, *refused))
        if not reviewer:
            why = (
                "Every other free model wrote to the worktree instead of replying, "
                f"so no verdict stands ({', '.join(refused)}). "
                "Decide whether to wait for usage to reset."
                if refused
                else "No second free model is available, and self-review is prohibited "
                "(CONSTRAINTS.md §5-5). Decide whether to wait for usage to reset."
            )
            return (
                self.escalate(
                    task, "no independent reviewer available", why, f"implementer={model}"
                ),
                None,
            )
        # Roster ids already carry their provider (`opencode/...`, `ollama/...`), and
        # the reviewer field is the evidence that a *different* model reviewed this
        # job, so it has to name a model that actually exists.
        task = self.set_fields(task, status="review", reviewer=reviewer)
        # Mark new files as intent-to-add first: `git diff` omits untracked files,
        # so a reviewer was shown a change with its new tests missing.
        git(tree, "add", "--intent-to-add", "--all", check=False)
        diff = git(tree, "diff", "HEAD", check=False)[:120000]
        evidence = "\n".join(f"- {gate.name}: {gate.detail[:300]}" for gate in checks)
        before = self.fingerprint(tree)
        untracked = self.untracked(tree)
        verdict = self.dispatch(
            reviewer,
            prompts.reviewer_brief(
                task,
                diff=diff,
                evidence=evidence,
                repository=str(tree),
                outside=str(self.settings.repository),
            ),
            cwd=tree,
            timeout=self.settings.review_timeout,
        )
        if verdict.rotate:
            self.roster.mark_exhausted(reviewer)
            return (
                Outcome(task.id, "rotated", f"{reviewer} {verdict.why_rotate}", model=model),
                None,
            )
        if self.fingerprint(tree) != before:
            stray = self.untracked(tree) - untracked
            self.discard(tree, stray)
            if stray and self.fingerprint(tree) == before:
                # A reviewer that wrote its review to a file instead of replying
                # has not touched the work: `T-PH6-113`'s reviewer left
                # `review_output.md` and nothing else on 2026-11-19. The verdict
                # is still void — a model that ignored "create no file" is not
                # one to take a verdict from, and `deliver` runs `git add -A`, so
                # a stray file would be committed with the work. Discard it,
                # say so, and try the next model instead of waiting for a person.
                self.record(
                    task,
                    f"REVIEWER WROTE TO DISK — verdict discarded ({self.now()})",
                    f"`{reviewer}` created {', '.join(sorted(stray))} instead of replying.\n"
                    "The read-only rule was broken, so its verdict is void. The files "
                    "were deleted, the work under review was not touched, and the job "
                    "is being re-reviewed by a different model.",
                )
                return Outcome(
                    task.id, "reviewer-refused", f"{reviewer} wrote to disk", model=model
                ), reviewer
            return (
                self.escalate(
                    task,
                    "reviewer modified the worktree",
                    "The read-only reviewer changed files, so its verdict is void. "
                    "Decide whether to re-review with another model.",
                    f"reviewer={reviewer}",
                ),
                None,
            )
        if verdict.ending is not worker.Ending.COMPLETED:
            return (
                Outcome(
                    task.id,
                    "review-unavailable",
                    f"{reviewer}: {verdict.ending.value}",
                    model=model,
                    reviewer=reviewer,
                ),
                None,
            )
        self.record(
            task,
            f"REVIEW by {reviewer} ({self.now()})",
            verdict.text.strip()[:6000],
        )
        approved = bool(APPROVAL.search(verdict.text))
        if not approved:
            cycles = int(task.fields.get("review_cycles", "0")) + 1
            task = self.set_fields(
                task, status="doing", review_cycles=str(cycles), attempts=str(task.attempts + 1)
            )
            if cycles >= REVIEW_CYCLE_LIMIT or task.attempts >= ATTEMPT_LIMIT:
                return (
                    self.escalate(
                        task,
                        "review cycle limit reached",
                        "The reviewer still requires changes at the cycle limit.",
                        verdict.text[-2000:],
                    ),
                    None,
                )
            return (
                Outcome(
                    task.id,
                    "changes-required",
                    "reviewer requires changes",
                    model=model,
                    reviewer=reviewer,
                ),
                None,
            )
        return self.deliver(task, tree, model, reviewer, checks), None

    # --- delivery ------------------------------------------------------------

    def deliver(
        self, task: Task, tree: Path, model: str, reviewer: str, checks: list[gates.Gate]
    ) -> Outcome:
        """Commit the reviewed work and fast-forward it into the integration branch."""
        subject = (
            f"{self.commit_type(task)}({self.commit_scope(task)}): {self.commit_summary(task)}"
        )
        git(tree, "add", "-A")
        if git(tree, "status", "--porcelain=1", check=False).strip():
            git(
                tree,
                "-c",
                "user.name=locus-jobloop",
                "-c",
                "user.email=jobloop@localhost",
                "commit",
                "-m",
                subject[:100],
            )
        # Nothing staged means a previous run already committed this reviewed
        # work; its existing head is what gets merged.
        head = git(tree, "rev-parse", "HEAD").strip()
        status = self.commit_progress_records(task)
        if status:
            return self.escalate(
                task,
                "integration branch is dirty",
                "The main checkout has uncommitted changes, so the reviewed commit was not merged. "
                "Decide how to integrate it.",
                f"commit={head}\n{status[:1000]}",
            )
        branch = git(tree, "rev-parse", "--abbrev-ref", "HEAD").strip()
        # The workspace is a separate clone, so its commit is fetched before it
        # can be merged.
        git(self.settings.repository, "fetch", str(tree), branch)
        merged = git(
            self.settings.repository,
            "merge",
            "--no-ff",
            "-m",
            f"merge(job): {task.id}",
            "FETCH_HEAD",
            check=False,
        )
        if (self.settings.repository / ".git" / "MERGE_HEAD").exists():
            # A conflicted merge left in the checkout is the worst stop this loop
            # has: every later job then reports "the integration branch is dirty"
            # and the queue dies whole. `T-PH6-113` did exactly that on
            # 2026-11-20 and took eleven jobs and seven hours with it.
            git(self.settings.repository, "merge", "--abort", check=False)
            return self.escalate(
                task,
                "the merge conflicted",
                "The reviewed work no longer applies to the integration branch, so the merge "
                "was aborted and nothing was committed. Decide whether the job redoes its "
                "work on the current branch.",
                f"commit={head}\nbranch={branch}\n{merged[-800:]}",
            )
        broken = self.loop_still_works()
        if broken:
            # A job that repairs the loop can also break it, and a broken
            # controller takes every later job with it. The merge is not pushed
            # until its own suite passes in the checkout it will run from.
            git(self.settings.repository, "reset", "--hard", "HEAD~1", check=False)
            return self.escalate(
                task,
                "the merge broke the loop",
                "The merged change left the loop's own suite failing, so the merge was rolled "
                "back. The fix has to keep the controller working.",
                f"commit={head}\n{broken[:900]}",
            )
        # `done` is written only once the work is actually in the branch. It used
        # to be set before the merge, so a conflict left a job recorded as done
        # whose change was nowhere.
        self.set_fields(task, status="done", attempts=str(task.attempts + 1))
        if self.settings.push:
            git(self.settings.repository, "push", "origin", self.settings.integration_branch)
        return Outcome(
            task.id,
            "delivered",
            f"{head[:7]} merged into {self.settings.integration_branch}",
            model=model,
            reviewer=reviewer,
            gates=checks,
        )

    def loop_still_works(self) -> str:
        """Empty unless the merge just landed changed the loop and broke it.

        Only runs when the merge touched `jobloop/` or `scripts/`, which is what
        a `phase-9-loop-health` job does by definition. The gates already ran in
        the workspace, but a merge is a different tree: it combines this change
        with everything that landed while the job was out, and that combination
        is what the next cycle will actually import.
        """
        changed = git(
            self.settings.repository, "diff", "--name-only", "HEAD~1", "HEAD", check=False
        ).splitlines()
        touched = [
            name for name in changed if name.replace("\\", "/").startswith(("jobloop/", "scripts/"))
        ]
        if not touched:
            return ""
        check = gates.run_command(
            "loop-suite",
            "python -m pytest tests/test_jobloop.py tests/test_diagnose.py "
            "tests/test_selfrepair.py -q",
            cwd=self.settings.repository,
            timeout=self.settings.gate_timeout,
            python=self.settings.python,
        )
        return "" if check.green else f"{', '.join(touched)}\n{check.detail[:700]}"

    def commit_progress_records(self, task: Task) -> str:
        """Commit the controller's own records; report anything else still dirty.

        The controller writes a job's status and evidence into the main checkout
        as the cycle runs, so by delivery time that checkout is dirty with its own
        bookkeeping. Those records are committed here; any other uncommitted path
        belongs to a person and stops the merge instead of being swept up.
        """
        # Porcelain output is column-oriented: the first two characters are the
        # status codes, so the lines must not be stripped before they are read.
        status = git(self.settings.repository, "status", "--porcelain=1", check=False)
        lines = [line for line in status.splitlines() if line.strip()]
        if not lines:
            return ""
        # Every phase's records are the loop's own, not just the phase being run.
        # One supervisor now walks several phases through one checkout, so
        # phase-7's bookkeeping from the previous pass is sitting uncommitted
        # when phase-6 comes to merge — and it was read as "a person is editing
        # this checkout". That alone blocked five jobs on 2026-11-20/21.
        records = "progress/"
        # The loop regenerates this page whenever it raises a question, so it
        # is the loop's own record, not a person's edit. Leaving it out made a
        # reviewed commit unmergeable on 2026-11-19.
        guide = "docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html"
        paths = [line[3:].strip().strip('"').replace("\\", "/") for line in lines]
        foreign = [path for path in paths if not path.startswith(records) and path != guide]
        if foreign:
            return "\n".join(lines)
        git(self.settings.repository, "add", "--", records, guide)
        git(
            self.settings.repository,
            "-c",
            "user.name=locus-jobloop",
            "-c",
            "user.email=jobloop@localhost",
            "commit",
            "-m",
            f"docs(progress): record the {task.id} cycle"[:100],
        )
        return ""

    @staticmethod
    def commit_type(task: Task) -> str:
        text = task.body.lower()
        if "test" in task.id.lower():
            return "test"
        for keyword, kind in (
            ("修復", "fix"),
            ("不具合", "fix"),
            ("監査", "test"),
            ("実測", "feat"),
        ):
            if keyword in text:
                return kind
        return "feat"

    @staticmethod
    def commit_scope(task: Task) -> str:
        return slug(task.id) or "job"

    @staticmethod
    def commit_summary(task: Task) -> str:
        for line in task.body.splitlines():
            if line.startswith("# Task"):
                return line.split(":", 1)[-1].strip().replace("`", "")[:60] or task.id
        return task.id

    # --- bounded run ---------------------------------------------------------

    def stranded(self) -> list[Task]:
        """Jobs stuck in `review` with their work still sitting in a workspace.

        Review is not a resting state: the cycle either approves and merges or
        comes back for changes. A run that ends mid-review leaves the job there
        with no way back into the queue.

        The attempt limit does not gate this, because a resume spends no attempt.
        It used to, and that made `review` plus `attempts 3/3` an invisible
        state: `T-PH6-104`, `T-PH8-303` and then `T-PH8-302` each sat in it with
        finished work nobody would ever look at again. Resuming is still
        bounded — if the gates fail, the job goes back to `doing`, and *there*
        the attempt limit stops it.
        """
        return [
            task
            for task in self.jobs()
            if task.status == "review" and (self.settings.workspace_root / task.id).is_dir()
        ]

    def run(self, *, minutes: float, max_jobs: int = 20) -> list[Outcome]:
        deadline = self.clock() + minutes * 60
        outcomes: list[Outcome] = []
        while len(outcomes) < max_jobs and self.clock() < deadline:
            # `.jobloop/stop` is checked between jobs, not only between cycles.
            # The supervisor checks it per cycle, and a cycle lasts up to its
            # whole minute budget: on 2026-11-22 a shift that needed the queue
            # paused waited eight minutes and gave up, because the run was
            # mid-cycle with fifty minutes left. A job already dispatched still
            # finishes — this stops the *next* one.
            if (self.settings.repository / ".jobloop" / "stop").is_file():
                outcomes.append(Outcome("-", "paused", "`.jobloop/stop` is present"))
                break
            # A job left in `review` is stranded: `actionable` covers only
            # `todo` and `doing`, so nothing ever picks it up again. Three jobs
            # sat that way through 239 idle cycles on 2026-11-19 while the
            # supervisor reported the queue as empty. Resume them first — the
            # work is in the workspace, so re-dispatching would throw it away.
            stranded = self.stranded()
            if stranded:
                outcome = self.resume(stranded[0])
                outcomes.append(outcome)
                if outcome.state == "no-model":
                    break
                continue
            task = self.select()
            if task is None:
                outcomes.append(Outcome("-", "idle", "no actionable job is left"))
                break
            # One line per job, so a cycle is not silent for its whole budget.
            # The supervisor writes only when a cycle ends, and a cycle can run
            # for an hour: every shift so far has had to work out from process
            # lists and file timestamps whether a long quiet stretch meant work
            # or a wedge. "last heartbeat 33 min ago" should not be ambiguous.
            self.note(f"{task.id}: dispatching ({task.weight or 'unweighted'})")
            outcome = self.run_job(task)
            self.note(outcome.line[:300])
            outcomes.append(outcome)
            if outcome.state == "no-model":
                break
        return outcomes
