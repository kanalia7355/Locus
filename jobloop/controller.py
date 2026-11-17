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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobloop import gates, prompts, worker
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

        append_section(task.path, heading, body)

    def set_fields(self, task: Task, **updates: str) -> Task:
        from jobloop.tasks import update_fields

        return update_fields(task.path, dict(updates), timestamp=self.now())

    def escalate(self, task: Task, category: str, question: str, context: str) -> Outcome:
        """Stop the job and write the owner a decision request."""
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
            return self.escalate(
                task,
                "the job file names another checkout",
                "The job file contains an absolute path to the main checkout, which a "
                "worker reads as the project root. Replace it with a relative path "
                "(use the bare name `python` in `test_cmd`) before dispatching.",
                f"found={leak}\nfile={task.path.name}",
            )
        model = self.roster.pick()
        if not model:
            return Outcome(task.id, "no-model", "every eligible free model is on cooldown")
        tree = self.workspace(task)
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
        if self.dirt(self.settings.repository) != outside:
            return self.escalate(
                task,
                "worker wrote outside its workspace",
                "The main checkout changed while the job ran, so this work is unreviewable. "
                "Inspect and restore the checkout before the job is retried.",
                f"model={model}\nworkspace={tree}",
            )
        if result.rotate:
            # Usage exhaustion is not a failed attempt (PROTOCOL §5.4).
            self.roster.mark_exhausted(model)
            return Outcome(task.id, "rotated", f"{model} is out of usage", model=model)
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
        names = gates.changed_files(tree)
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
        reviewer = self.roster.pick_reviewer(model)
        if not reviewer:
            return self.escalate(
                task,
                "no independent reviewer available",
                "No second free model is available, and self-review is prohibited "
                "(CONSTRAINTS.md §5-5). Decide whether to wait for usage to reset.",
                f"implementer={model}",
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
            return Outcome(task.id, "rotated", f"{reviewer} is out of usage", model=model)
        if self.fingerprint(tree) != before:
            return self.escalate(
                task,
                "reviewer modified the worktree",
                "The read-only reviewer changed files, so its verdict is void. "
                "Decide whether to re-review with another model.",
                f"reviewer={reviewer}",
            )
        if verdict.ending is not worker.Ending.COMPLETED:
            return Outcome(
                task.id,
                "review-unavailable",
                f"{reviewer}: {verdict.ending.value}",
                model=model,
                reviewer=reviewer,
            )
        self.record(
            task,
            f"REVIEW by {reviewer} ({self.now()})",
            verdict.text.strip()[:6000],
        )
        approved = bool(re.search(r"^\s*-?\s*`?APPROVED`?\s*$", verdict.text, re.MULTILINE))
        if not approved:
            cycles = int(task.fields.get("review_cycles", "0")) + 1
            task = self.set_fields(
                task, status="doing", review_cycles=str(cycles), attempts=str(task.attempts + 1)
            )
            if cycles >= REVIEW_CYCLE_LIMIT or task.attempts >= ATTEMPT_LIMIT:
                return self.escalate(
                    task,
                    "review cycle limit reached",
                    "The reviewer still requires changes at the cycle limit.",
                    verdict.text[-2000:],
                )
            return Outcome(
                task.id,
                "changes-required",
                "reviewer requires changes",
                model=model,
                reviewer=reviewer,
            )
        return self.deliver(task, tree, model, reviewer, checks)

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
        self.set_fields(task, status="done", attempts=str(task.attempts + 1))
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
        git(
            self.settings.repository,
            "merge",
            "--no-ff",
            "-m",
            f"merge(job): {task.id}",
            "FETCH_HEAD",
        )
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
        records = f"progress/{self.settings.phase}/"
        paths = [line[3:].strip().strip('"').replace("\\", "/") for line in lines]
        foreign = [path for path in paths if not path.startswith(records)]
        if foreign:
            return "\n".join(lines)
        git(self.settings.repository, "add", "--", records)
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

    def run(self, *, minutes: float, max_jobs: int = 20) -> list[Outcome]:
        deadline = self.clock() + minutes * 60
        outcomes: list[Outcome] = []
        while len(outcomes) < max_jobs and self.clock() < deadline:
            task = self.select()
            if task is None:
                outcomes.append(Outcome("-", "idle", "no actionable job is left"))
                break
            outcome = self.run_job(task)
            outcomes.append(outcome)
            if outcome.state == "no-model":
                break
        return outcomes
