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
from jobloop.roster import COOLDOWN_SECONDS, Roster
from jobloop.tasks import ATTEMPT_LIMIT, REVIEW_CYCLE_LIMIT, Task, load_phase, parse

JST = timezone(timedelta(hours=9))
GIT = shutil.which("git") or "git"
SLUG = re.compile(r"[^a-z0-9]+")
HEX = frozenset("0123456789abcdef")
# Three consecutive timeouts across rested models indicate the job itself likely
# exceeds the 1800s dispatch budget and needs a human to split it.
TIMEOUT_ESCALATE_LIMIT = 3


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

# How long a model that could not be run at all is passed over, the first time.
# Much shorter than the exhaustion cooldown: a spent free allowance comes back
# tomorrow, a CLI that cannot route to a provider may come back in minutes, and
# the point here is only to stop the roster handing out the same broken first
# choice. A repeat doubles it (`Roster.mark_unavailable`): one outage is a wait,
# the seventeenth is a broken provider.
UNAVAILABLE_COOLDOWN = 900.0

# A provider saying the model cannot do what the worker needs is not an outage.
# It is the same answer every time, so the short cooldown above is wrong for it:
# `ollama/gemma3:4b` answered
#   provider.invalid-request: registry.ollama.ai/library/gemma3:4b does not support tools
# and on 2026-11-22 it was therefore picked, failed and rested every fifteen
# minutes — ninety-six attempts a day that could never succeed. Rested for the
# full exhaustion period instead, so it is tried a few times a day rather than
# constantly, and a model that gains the capability still comes back.
#
# Only strings that have actually been observed belong here. A broad match like
# `does not support` would also swallow a transient bad request.
INCAPABLE = ("does not support tools",)


def cooldown_for(errors: list[str]) -> float:
    """How long to rest a model the CLI could not run."""
    joined = " ".join(errors).lower()
    if any(mark in joined for mark in INCAPABLE):
        return COOLDOWN_SECONDS
    return UNAVAILABLE_COOLDOWN


# Wording that only ever comes from the brief's own STATUS instruction. A reply
# containing it is the instruction leaking into the answer, not a question: on
# 2026-11-22 `T-PH6-127` escalated with "` followed by the real question you
# need answered." while its report ended `ready-for-review` and the work was
# done. Each phrase here is a literal fragment of `prompts.implementer_brief`.
ECHOED = (
    "followed by the real question",
    "written out in full",
    "never copy this instruction",
    "the real question you need answered",
)


def placeholder(text: str) -> str | bool:
    """True when a reported question is the brief's own placeholder, not a question."""
    stripped = text.strip()
    lowered = stripped.lower()
    return (
        len(stripped) < 12
        or (stripped.startswith("<") and stripped.endswith(">"))
        or "<the question>" in stripped
        or stripped in {"the question", "<question>"}
        or any(phrase in lowered for phrase in ECHOED)
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

    @staticmethod
    def consecutive_timeouts(task: Task) -> int:
        """Count consecutive TIMEOUT records since the last attempt or escalation."""
        count = 0
        for line in task.path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## TIMEOUT ("):
                count += 1
            elif line.startswith(("## ATTEMPT (", "## OWNER DECISION REQUESTED (")):
                count = 0
        return count

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
            # The file may spell the path with either separator; `points_outside`
            # reports whichever form it found, so replace all of them.
            for raw in repair.paths:
                for form in {raw, raw.replace("\\", "/"), raw.replace("/", "\\")}:
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
        root = str(self.settings.repository)
        for form in {root, root.replace("\\", "/"), root.replace("/", "\\")}:
            question = question.replace(form, "<repository>")
            context = context.replace(form, "<repository>")
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
        recorded = f"{category}: {question}"
        if category == "the merge conflicted":
            recorded = f"{recorded}\n\n{context.strip()}"
        self.record(task, f"OWNER DECISION REQUESTED ({self.now()})", recorded)
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

    def preserve_stale_commit(self, task: Task, worktree: Path) -> str:
        """Save `worktree`'s HEAD under a `stale/<id>-<MMDD>` tag without moving HEAD."""
        stamp = self.now()
        mmdd = stamp[5:7] + stamp[8:10]
        prefix = f"stale/{task.id}-{mmdd}"
        head = git(worktree, "rev-parse", "HEAD").strip()
        existing = {
            line.strip()
            for line in git(worktree, "tag", "--list", f"{prefix}*", check=False).splitlines()
            if line.strip()
        }
        ref = prefix
        suffix = 2
        while ref in existing:
            pointed = git(worktree, "rev-parse", f"{ref}^{{commit}}", check=False).strip()
            if pointed == head:
                return ref
            ref = f"{prefix}-{suffix}"
            suffix += 1
        git(worktree, "tag", ref, head)
        return ref

    def advance_base(self, task: Task, worktree: Path) -> str:
        """Preserve this job's own commits as a `stale/...` ref and move onto integration.

        Never called automatically by `refresh()`: whether an unattended job may
        abandon a conflicted base on its own is an open decision. This is the
        explicit path that replaces doing the tag-and-reset by hand, and it
        refuses a dirty tree so uncommitted work is never discarded.
        """
        if self.dirt(worktree).strip():
            raise RuntimeError(f"cannot advance {task.id}: workspace has uncommitted changes")
        git(worktree, "fetch", str(self.settings.repository), self.settings.integration_branch)
        behind = git(worktree, "rev-list", "--count", "HEAD..FETCH_HEAD", check=False).strip()
        ref = self.preserve_stale_commit(task, worktree)
        git(worktree, "reset", "--hard", "FETCH_HEAD")
        git(worktree, "checkout", "-B", self.branch_for(task))
        self.record(
            task,
            f"WORKSPACE BASE ADVANCED ({self.now()})",
            f"Preserved this job's previous commit at `{ref}` (`git show {ref}`) and reset "
            f"the workspace ({behind or '0'} commit(s) behind) onto "
            f"`{self.settings.integration_branch}`.",
        )
        return ref

    def already_conflicted_ahead(self, task: Task, worktree: Path) -> str:
        """Non-empty commit sha when `worktree` is behind & ahead and HEAD already conflicted."""
        if not self._has_conflict_record(task):
            return ""
        if self.dirt(worktree).strip():
            return ""
        with suppress(RuntimeError):
            git(worktree, "fetch", str(self.settings.repository), self.settings.integration_branch)
            behind = git(worktree, "rev-list", "--count", "HEAD..FETCH_HEAD", check=False).strip()
            ahead = git(worktree, "rev-list", "--count", "FETCH_HEAD..HEAD", check=False).strip()
            if not behind or behind == "0" or not ahead or ahead == "0":
                return ""
            head = git(worktree, "rev-parse", "HEAD", check=False).strip()
            if head and self._commit_recorded_as_conflicted(task, head):
                return head
        return ""

    def _has_conflict_record(self, task: Task) -> bool:
        """Fast disk-only check whether `task` has any recorded `the merge conflicted` entry."""
        decisions = self.settings.phase_directory / "OWNER_DECISIONS.md"
        if decisions.is_file():
            text = decisions.read_bytes().decode("utf-8", errors="replace")
            if "the merge conflicted" in text and task.id in text:
                return True
        for path in (task.path, self.settings.phase_directory / "tasks" / task.path.name):
            if path.is_file():
                body = path.read_bytes().decode("utf-8", errors="replace")
                if "the merge conflicted:" in body:
                    return True
        return False

    def _commit_recorded_as_conflicted(self, task: Task, head: str) -> bool:
        """True when `head` is already recorded under `the merge conflicted` for `task`."""
        decisions = self.settings.phase_directory / "OWNER_DECISIONS.md"
        if decisions.is_file():
            text = decisions.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
            for entry in re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]:
                header = entry.split("\n", 1)[0]
                if (
                    header.startswith(f"{task.id} ")
                    and "the merge conflicted" in header
                    and f"commit={head}" in entry
                ):
                    return True
        for path in (task.path, self.settings.phase_directory / "tasks" / task.path.name):
            if path.is_file():
                body = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
                for section in re.split(r"^##\s+", body, flags=re.MULTILINE)[1:]:
                    if "the merge conflicted:" in section and f"commit={head}" in section:
                        return True
        return False

    def conflict_measurements(self, task: Task, worktree: Path) -> tuple[str, str]:
        """Measure merge-base commit/date, commits behind, own diffstat, and save a `stale/` ref."""
        ref = self.preserve_stale_commit(task, worktree)
        git(worktree, "fetch", str(self.settings.repository), self.settings.integration_branch)
        behind = git(worktree, "rev-list", "--count", "HEAD..FETCH_HEAD", check=False).strip()
        base = git(worktree, "merge-base", "FETCH_HEAD", "HEAD", check=False).strip()
        base_date = (
            git(worktree, "show", "-s", "--format=%ai", base, check=False).strip()
            if base
            else "unknown"
        )
        stat = (
            git(worktree, "diff", "--stat", f"{base}..HEAD", check=False).strip()
            if base
            else "(merge-base unavailable)"
        )
        report = (
            f"base={base or 'unknown'} ({base_date})\n"
            f"behind={behind or '0'} commit(s) behind {self.settings.integration_branch}\n"
            f"preserved_ref={ref}\n"
            f"own_changes (merge-base..HEAD):\n{stat or '(none)'}"
        )
        return ref, report

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

    @staticmethod
    def bookkeeping(line: str) -> bool:
        """True for a porcelain line that cannot be a worker escaping.

        A worker escaping the workspace shows up as **product code** appearing in
        the main checkout. Records and planning do not: `progress/` is where the
        controller writes its own evidence, and where the owner writes task
        drafts whenever they like. On 2026-11-22 `T-PH6-127` was accused because
        the owner created `progress/phase-storage-connect/tasks/T-STC-005.md`
        while the job ran — the appeared-lines evidence named it exactly.

        The orchestrator marker cannot cover that: it is set by a shift, and the
        owner does not run shifts in their own repository. So the comparison is
        narrowed to what it is actually for. `commit_progress_records` already
        treats all of `progress/` as the loop's own, which is the same judgement.
        """
        return Controller.changed_path(line).startswith("progress/") or Controller.changed_path(
            line
        ) == ("docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html")

    @staticmethod
    def changed_path(line: str) -> str:
        """The path out of a `dirt` line, with the digest column removed.

        Written as its own step because the digest is appended, and a path may
        contain spaces: splitting blindly on whitespace would truncate
        `?? progress/my notes.md` to `progress/my`. Only a field that looks like
        a digest is dropped, so a line written by hand without one still parses.
        """
        body = line[3:].strip().strip('"')
        head, _, last = body.rpartition(" ")
        if head and (last in {"-", "?"} or (len(last) == 16 and all(c in HEX for c in last))):
            body = head.strip().strip('"')
        return body.replace("\\", "/")

    def note(self, line: str) -> None:
        """Append one heartbeat line, in the supervisor's own format and file.

        Same file so that "when did anything last happen" has one answer; the
        writes are single short lines in append mode, which is what a log can
        take from two processes.

        Printed as well as written. `supervise_loop.py` prints only at cycle
        boundaries and a cycle's budget is forty-five minutes, so the console the
        owner watches sat silent for ten minutes on 2026-11-22 while `T-PH6-127`
        ran normally — and the owner had to ask whether the loop had stopped.
        A dispatch is the thing that shows it has not.
        """
        stamped = f"{self.now()} run :: {line}"
        beat = self.settings.state_directory / "supervisor.log"
        with suppress(OSError):
            beat.parent.mkdir(parents=True, exist_ok=True)
            with beat.open("a", encoding="utf-8") as handle:
                handle.write(f"{stamped}\n")
        print(stamped, flush=True)  # noqa: T201 — the operator's only live view

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

    @property
    def busy_marker(self) -> str:
        """The orchestrator-busy marker as a record names it: repository-relative.

        The record is read by the next worker, so an absolute path here would
        teach it where the main checkout is — the escape route this ticket
        closes (T-PH9-406).
        """
        return (
            (self.settings.state_directory / "orchestrator-busy")
            .relative_to(self.settings.repository)
            .as_posix()
        )

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

        **One line per path: status, path, digest.** This used to return
        `git diff HEAD` as well, and the comparison then ran over diff *body*
        lines: on 2026-11-22 at 18:49 `T-PH6-127` was accused with evidence that
        read

            beat.parent.mkdir(parents=True, exist_ok=True)
            with beat.open("a", encoding="utf-8") as handle

        — fragments of the orchestrator's own edit to this very method. Three
        things were wrong with that. `bookkeeping` reads a line as a status code
        plus a path and cannot classify a fragment, so nothing could be excluded;
        a set difference over content lines is junk, since a shared context line
        in two unrelated edits cancels out; and the evidence named no file, which
        is the one thing a reader needs.

        Porcelain alone is not enough either, and dropping to it lost a real
        detection: a file that is *already* dirty keeps the same status line when
        its contents change, so a reviewer editing it — or a worker hiding behind
        the orchestrator's own uncommitted mess — became invisible. The digest
        restores that. Judgement and evidence stay at path granularity; the hash
        only decides whether that path's entry is the same entry.
        """
        porcelain = git(worktree, "status", "--porcelain=1", "--untracked-files=all", check=False)
        lines = []
        for entry in porcelain.splitlines():
            if not entry.strip():
                continue
            code, path = entry[:2], entry[3:].strip().strip('"')
            target = worktree / path.replace("\\", "/")
            try:
                digest = (
                    hashlib.sha256(target.read_bytes()).hexdigest()[:16]
                    if target.is_file()
                    else "-"
                )
            except OSError:
                digest = "?"
            lines.append(f"{code} {path} {digest}")
        return "".join(f"{line}\n" for line in lines)

    # --- one job -------------------------------------------------------------

    def run_job(self, task: Task) -> Outcome:
        leak = self.points_outside(task)
        if leak:
            # Normalise the endings before looking for the frontmatter. Task
            # files are CRLF, so `"\n---\n"` never matched and `head` became the
            # whole file: every path anywhere in the body was reported as being
            # in the frontmatter, `selfrepair` refused to redact it (redacting a
            # `test_cmd` would leave a broken command), and the job stopped.
            # `T-PH7-201` was blocked on 2026-11-22 by a path in a *ruling* —
            # prose written for a person — because of this one `\r`.
            whole = task.path.read_bytes().decode("utf-8").replace("\r\n", "\n")
            head = whole.split("\n---\n", 1)[0]
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
        # A light job goes to the second tier's light family when the first tier
        # is spent; a free model carries no role and is unaffected (owner E2).
        model = self.roster.pick(role="light" if task.weight == "light" else "implement")
        if not model:
            return Outcome(task.id, "no-model", "every eligible free model is on cooldown")
        tree = self.workspace(task)
        conflicted = self.already_conflicted_ahead(task, tree)
        if conflicted:
            return self.escalate(
                task,
                "the merge conflicted",
                "The workspace still holds a commit whose merge into the integration branch "
                "already conflicted, and `refresh()` refuses to discard ahead commits. "
                "Preserve and advance the workspace base before retrying.",
                f"commit={conflicted}\n" + self.conflict_measurements(task, tree)[1],
            )
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
        self.roster.mark_dispatched(model)
        started = time.monotonic()
        result = self.dispatch(model, brief, cwd=tree, timeout=self.settings.worker_timeout)
        elapsed = time.monotonic() - started
        after = self.dirt(self.settings.repository)
        # Judge on what *appeared*, not on inequality. An escaping worker leaves
        # new uncommitted paths behind; nothing a worker does makes the
        # operator's own pre-existing mess disappear. Comparing the whole string
        # made the opposite direction an accusation too: on 2026-11-22
        # `T-PH7-201` was blamed at 05:56 because the orchestrator *committed*
        # mid-dispatch, so the dirt it had been carrying went away. The evidence
        # added an hour earlier is what settled it — the record said
        # `appeared:` and then nothing at all.
        moved = [
            line
            for line in sorted(set(after.splitlines()) - set(outside.splitlines()))
            if not self.bookkeeping(line)
        ]
        if moved and not self.operator_busy():
            containment = self.roster.mark_containment_stop(
                model, orchestrator_busy=self.operator_busy()
            )
            containment_note = (
                f"containment {model}: {containment['containment_stops']}/"
                f"{containment['dispatches']} stops/dispatches"
            )
            if containment["rested"]:
                containment_note += f" -> rested {COOLDOWN_SECONDS / 3600:.0f}h"
                self.note(containment_note)
            return self.escalate(
                task,
                "worker wrote outside its workspace",
                "The main checkout changed while the job ran, so this work is unreviewable. "
                "Inspect and restore the checkout before the job is retried.",
                f"model={model}\nworkspace={task.id}\n"
                f"marker={self.busy_marker} present={self.operator_busy()}\n"
                f"{containment_note}\n"
                # Paths, not digests: the reader needs the filenames.
                f"appeared:\n"
                + "\n".join(f"{line[:2]} {self.changed_path(line)}" for line in moved[:25]),
            )
        if self.operator_busy():
            self.record(
                task,
                f"CONTAINMENT UNVERIFIED ({self.now()})",
                "The operator was editing the main checkout during this cycle, so the "
                "containment comparison was suspended. The worker's isolation was not "
                "verified for this attempt.\n\n"
                f"marker={self.busy_marker} present={self.operator_busy()}",
            )
        if result.rotate:
            # Neither usage exhaustion (PROTOCOL §5.4) nor a provider outage is a
            # failed attempt: in both the model never received the job. Keeping
            # the two apart matters only in what the record says — the model is
            # put on cooldown either way, and the job keeps its attempt.
            self.roster.mark_exhausted(model)
            return Outcome(task.id, "rotated", f"{model} {result.why_rotate}", model=model)
        # The assignee names the CLI that actually ran the session, not a fixed
        # string: with the second tier in place (owner E2, 2026-11-25) a job can be
        # run by `agy`, and a record that says `opencode` for it sends the next
        # reader to the wrong log and the wrong process list.
        task = self.set_fields(task, status="doing", assignee=model.split("/", 1)[0], model=model)
        if result.ending is worker.Ending.UNAVAILABLE:
            # The CLI could not run this model at all — a crash, an auth
            # problem, a provider it cannot route to. The job was never
            # attempted, so it keeps its attempt, and the model goes on a
            # cooldown so the next pass reaches a different one. That cooldown
            # doubles while the failure repeats, so a provider that is broken
            # for a reason nobody has seen yet is not picked up every fifteen
            # minutes for a day.
            rested = self.roster.mark_unavailable(model, base_seconds=cooldown_for(result.errors))
            return Outcome(
                task.id,
                "rotated",
                (
                    f"{model} could not be run: {'; '.join(result.errors[:2])}"
                    f" (rested {rested / 60:.0f} min)"
                )[:300],
                model=model,
            )
        if result.ending is worker.Ending.TIMEOUT:
            # No reply arrived within the budget, so the job's work was never
            # evaluated. Keep the attempt, rest the model so the next dispatch
            # reaches a different one, and escalate once consecutive timeouts
            # hit TIMEOUT_ESCALATE_LIMIT.
            rested = self.roster.mark_unavailable(model, base_seconds=cooldown_for(result.errors))
            count = self.consecutive_timeouts(task) + 1
            detail = (
                f"{model} timed out after {elapsed:.1f}s "
                f"(consecutive {count}/{TIMEOUT_ESCALATE_LIMIT}, rested {rested / 60:.0f} min)"
            )
            self.record(task, f"TIMEOUT ({self.now()})", detail)
            if count >= TIMEOUT_ESCALATE_LIMIT:
                return self.escalate(
                    task,
                    "timeout limit reached",
                    f"{count} consecutive dispatches timed out without a reply; "
                    "the job may need to be split.",
                    detail,
                )
            return Outcome(task.id, "rotated", detail[:300], model=model)
        if result.ending is not worker.Ending.COMPLETED:
            return self.failed_attempt(
                task, model, f"{result.ending.value}: {'; '.join(result.errors[:3])}"
            )
        # The model answered. Whatever the answer is worth, it is not evidence
        # that the provider is broken, so the failure streak starts over here —
        # this is the reset the old design was missing.
        self.roster.mark_responded(model)
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
        # Sweep once, then filter. Calling `sweep()` inside the comprehension's
        # condition ran it for every path: the first call deleted the scratch and
        # returned it, every later call found nothing and returned an empty set,
        # so the filter kept the very files that had just been removed. On
        # 2026-11-22 `T-PH6-125` was stopped for eight paths its own record shows
        # as already deleted — the scope gate was reading a list of ghosts.
        dropped = self.sweep(task, tree)
        names = [name for name in gates.changed_files(tree) if name not in dropped]
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
        conflicted = self.already_conflicted_ahead(task, tree)
        if conflicted:
            return self.escalate(
                task,
                "the merge conflicted",
                "The workspace still holds a commit whose merge into the integration branch "
                "already conflicted; not re-running the gates on an unchanged stale tree.",
                f"commit={conflicted}\n" + self.conflict_measurements(task, tree)[1],
            )
        # Check for a reviewer before re-running anything. A resume runs the
        # job's whole gate suite, and with the pool empty that work is thrown
        # away at the next step: on 2026-11-22 `T-PH8-302` re-ran its gates
        # twice every two minutes for an hour to reach a reviewer that was
        # never there. Waiting should cost nothing.
        if not self.roster.pick(exclude=(model,), role="review"):
            return Outcome(
                task.id,
                "no-reviewer",
                "every free model is on cooldown; not re-running the gates to find that out",
                model=model,
            )
        names = gates.changed_files(tree)
        if not names:
            # A clean tree is not an empty workspace. The work may already be
            # *committed* and waiting to merge, which is what a job in `review`
            # usually is: `T-PH6-104` sat at `nothing-to-resume - the workspace
            # has no changes` on every cycle from 19:11 on 2026-11-22 with
            # `8ca0bda` reviewed and intact in its clone, because the merge had
            # failed earlier and `changed_files` only reports what is uncommitted.
            # The same shape wasted `T-PH6-123`'s attempts and `T-PH6-116`'s
            # whole budget. Ask git what the integration branch does not have.
            names = self.committed_but_unmerged(tree)
            if not names:
                return Outcome(
                    task.id, "nothing-to-resume", "the workspace has no changes and no new commit"
                )
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

    def committed_but_unmerged(self, tree: Path) -> list[str]:
        """Paths changed by commits the integration branch does not have yet.

        A workspace whose work is committed looks empty to `changed_files`, which
        reads `git status`. The question a resume actually needs to ask is what
        this clone has that the branch does not, and that is a commit range.

        Measured from the **merge base**, not from `FETCH_HEAD`. A diff between
        two tips is a tree comparison, so `FETCH_HEAD..HEAD` also reports every
        file the branch has gained since this clone was made — with the sign
        flipped. The first version of this method did exactly that and the scope
        gate failed `T-PH6-104` at 19:30 on 2026-11-22 for
        `.claude/skills/README.md` and `backend/app/connectors/`, files its
        worker had never seen. From the common ancestor the answer is the job's
        own three files.
        """
        with suppress(RuntimeError):
            git(tree, "fetch", str(self.settings.repository), self.settings.integration_branch)
            ahead = git(tree, "rev-list", "--count", "FETCH_HEAD..HEAD", check=False).strip()
            if ahead and ahead != "0":
                base = git(tree, "merge-base", "FETCH_HEAD", "HEAD", check=False).strip()
                if not base:
                    return []
                listed = git(tree, "diff", "--name-only", f"{base}..HEAD", check=False)
                return [name.strip() for name in listed.splitlines() if name.strip()]
        return []

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
        # Two reasons to move on, kept apart on purpose. A model that broke the
        # read-only rule is a person's problem; one the CLI could not run at all
        # is a wait. Folding them into one list made the escalation say "wrote to
        # the worktree instead of replying" about `ollama/gemma3:4b`, which had
        # only ever answered `unavailable` — the record accusing a model of
        # something it did not do (seen 2026-11-22 08:32 on `T-PH6-104`).
        refused: tuple[str, ...] = ()
        unreachable: tuple[str, ...] = ()
        while True:
            outcome, again = self.review_once(
                task,
                tree,
                model,
                checks,
                refused=refused + unreachable,
                broke_the_rule=refused,
            )
            if again is None:
                return outcome
            if outcome.state == "review-unavailable":
                unreachable += (again,)
            else:
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
        broke_the_rule: tuple[str, ...] = (),
    ) -> tuple[Outcome, str | None]:
        """One review pass. The second element names a reviewer to try after, if any.

        `refused` is every model already tried, for any reason; `broke_the_rule`
        is the subset that wrote to the worktree. Only the second is a question
        for a person — the rest is a wait.
        """
        reviewer = self.roster.pick(exclude=(model, *refused), role="review")
        if not reviewer:
            if broke_the_rule:
                # Every model was tried and each broke the read-only rule. That
                # is a person's call: the models are reachable and still unusable.
                return (
                    self.escalate(
                        task,
                        "no independent reviewer available",
                        "Every free model that could be run wrote to the worktree instead of "
                        f"replying, so no verdict stands ({', '.join(broke_the_rule)}). "
                        "Decide whether to wait for usage to reset.",
                        f"implementer={model}",
                    ),
                    None,
                )
            # Nothing is available right now, which is a wait and not a decision:
            # the cooldowns expire by themselves. Escalating set `blocked`, and
            # on 2026-11-22 that left four jobs needing a human for a condition
            # that resolves on its own — `T-PH6-104`, `T-PH7-211`, `T-PH8-302`,
            # `T-PH8-303`, all while `available models: none`. The job stays in
            # `review` so the next cycle resumes it, and the record says so.
            # `review` is what `stranded()` looks for, so the next cycle resumes
            # this without spending an attempt. Left at `doing` it would be
            # re-dispatched as a fresh attempt and the work thrown away.
            task = self.set_fields(task, status="review")
            self.record(
                task,
                f"WAITING FOR A REVIEWER ({self.now()})",
                f"`{model}` implemented this, and no other free model is off cooldown, so "
                "there is nobody to review it. Self-review is prohibited (CONSTRAINTS.md "
                "§5-5). This is a wait, not a decision: the job stays in `review` and the "
                "next cycle tries again once a model is back. Nothing was approved, "
                "nothing was merged.",
            )
            return (
                Outcome(
                    task.id,
                    "no-reviewer",
                    "every free model is on cooldown; the job stays in review",
                    model=model,
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
        self.roster.mark_dispatched(reviewer)
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
            # Cool it down and try the next model, in this same pass. Without
            # the cooldown the roster picked the same first-ranked model every
            # time: on 2026-11-22 `ollama/gemma3:4b` answered `unavailable` for
            # `T-PH6-104` and `T-PH8-302` on every cycle for an hour, while two
            # working `opencode` models sat untried. Nothing escalated, so the
            # queue looked healthy and `diagnose` saw nothing at all. The rest
            # doubles while the failure repeats — see `Roster.mark_unavailable`.
            self.roster.mark_unavailable(reviewer, base_seconds=cooldown_for(verdict.errors))
            return (
                Outcome(
                    task.id,
                    "review-unavailable",
                    f"{reviewer}: {verdict.ending.value}",
                    model=model,
                    reviewer=reviewer,
                ),
                reviewer,
            )
        # The reviewer answered, so its failure streak is over: without this
        # reset a model that was unavailable once would rest longer every time.
        self.roster.mark_responded(reviewer)
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
            spent_cycles = cycles >= REVIEW_CYCLE_LIMIT
            if spent_cycles or task.attempts >= ATTEMPT_LIMIT:
                # Name the budget that actually ran out. Both branches used to
                # escalate as "review cycle limit reached", so on 2026-11-22
                # `T-PH7-205` was recorded that way with `review_cycles: 1` —
                # it was the attempt limit. The two have opposite readings: a
                # spent cycle budget means implementer and reviewer are pushing
                # at each other, a spent attempt budget means the work itself
                # kept failing. A shift sent to the wrong one reads the wrong
                # evidence first.
                return (
                    self.escalate(
                        task,
                        "review cycle limit reached"
                        if spent_cycles
                        else "attempt limit reached after a review",
                        f"The reviewer still requires changes, and the "
                        f"{'review cycle' if spent_cycles else 'attempt'} budget is spent "
                        f"(attempts {task.attempts}/{ATTEMPT_LIMIT}, "
                        f"review cycles {cycles}/{REVIEW_CYCLE_LIMIT}).",
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
            _ref, details = self.conflict_measurements(task, tree)
            return self.escalate(
                task,
                "the merge conflicted",
                "The reviewed work no longer applies to the integration branch, so the merge "
                "was aborted and nothing was committed. Decide whether the job redoes its "
                "work on the current branch.",
                f"commit={head}\nbranch={branch}\n{details}\n{merged[-800:]}",
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

    def commit_progress_records(self, task: Task | None = None) -> str:
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
            return self.format_dirty_branch(lines, paths, records, guide)
        # Only add what exists. `git add` has no `--ignore-unmatch`, so naming
        # the guide page in a checkout that has not generated it yet raises
        # `fatal: pathspec ... did not match any files` — harmless while
        # `deliver` was the only caller, because by then the page was always
        # there, and a crash now that every cycle commits its records.
        targets = [path for path in (records, guide) if (self.settings.repository / path).exists()]
        if not targets:
            return ""
        git(self.settings.repository, "add", "--", *targets)
        git(
            self.settings.repository,
            "-c",
            "user.name=locus-jobloop",
            "-c",
            "user.email=jobloop@localhost",
            "commit",
            "-m",
            (
                f"docs(progress): record the {task.id} cycle"
                if task
                else "docs(progress): record this cycle"
            )[:100],
        )
        return ""

    def format_dirty_branch(
        self, lines: list[str], paths: list[str], records: str, guide: str
    ) -> str:
        """Report dirty-branch state with foreign paths separated and attributed.

        Only foreign paths caused the stop; progress records and the regenerated
        plain guide are the loop's own bookkeeping and are shown separately so a
        reader does not mistake them for the reason the merge was refused.
        """
        foreign_lines: list[str] = []
        bookkeeping: list[str] = []
        for line, path in zip(lines, paths, strict=True):
            if path.startswith(records) or path == guide:
                bookkeeping.append(line)
            else:
                owners = self.owners_of_path(path)
                if owners:
                    note = f"  → {', '.join(owners)} の許可パス"
                else:
                    note = "  → どの票の許可パスにも無い"
                foreign_lines.append(f"{line}{note}")
        parts = [
            "foreign (判定に使った未コミットのパス):",
            *foreign_lines,
        ]
        if bookkeeping:
            parts.extend(
                [
                    "",
                    "not used for decision (判定に使っていない: progress/ と平易化ページ):",
                    *bookkeeping,
                ]
            )
        return "\n".join(parts)

    def owners_of_path(self, path: str) -> list[str]:
        """Task ids whose allowed_paths cover `path`, across every phase."""
        owners: list[str] = []
        progress = self.settings.repository / "progress"
        if not progress.is_dir():
            return owners
        for task_file in sorted(progress.glob("*/tasks/*.md")):
            try:
                task = parse(task_file)
            except Exception:  # noqa: S112 - a broken task file must not break the stop report
                continue
            for allowed in task.allowed_paths:
                entry = allowed.replace("\\", "/")
                if path == entry or path.startswith(entry.rstrip("/") + "/"):
                    owners.append(task.id)
                    break
        return owners

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
                # The resume branch needs the heartbeat too. Instrumenting only
                # the dispatch left a cycle that spends its whole budget on
                # resumes just as silent as before: measured 2026-11-22, the
                # phase-7 cycle ran 39 minutes without a line while resuming.
                self.note(f"{stranded[0].id}: resuming")
                outcome = self.resume(stranded[0])
                self.note(outcome.line[:300])
                outcomes.append(outcome)
                if outcome.state in {"no-model", "no-reviewer"}:
                    # Nothing else in this cycle can get further either: both
                    # mean the roster is empty. Carrying on resumed the same job
                    # again and again inside one cycle.
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
            if outcome.state in {"no-model", "no-reviewer"}:
                break
        # Commit this cycle's records before leaving, whatever the outcomes were.
        # `deliver` was the only caller, so a cycle that only rotated, escalated
        # or found no model left its own bookkeeping uncommitted — and the next
        # job that *did* reach delivery then escalated with "integration branch
        # is dirty" over records the loop had written itself. `T-PH6-104` was
        # stopped that way at 18:54 on 2026-11-22, and the end-of-run push in
        # `cli` pushed nothing because nothing had been committed. A person's
        # uncommitted files still stop the merge: `commit_progress_records`
        # refuses to stage anything outside `progress/` and the guide page.
        self.commit_progress_records()
        return outcomes
