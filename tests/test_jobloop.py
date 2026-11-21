"""The job loop must be boringly deterministic: no model gets to decide anything.

These tests use fake workers, so no provider is contacted.
"""

import subprocess
import sys
import time
from pathlib import Path

import pytest

from jobloop import controller as controller_module
from jobloop import gates, prompts, tasks, worker
from jobloop.controller import Controller, Settings, git
from jobloop.roster import Roster, eligible

TASK = """---
id: T-JOB-1
phase: phase-test
status: todo
assignee: unassigned
model: -
weight: light
updated: 2026-11-15T10:00:00+09:00
attempts: 0
allowed_paths: backend/app/service.py, tests/test_api.py
test_cmd: python -c "print('ok')"
---

# Task `T-JOB-1`: 合成ジョブ

## TASK DEFINITION (Assigned by Orchestrator)

- **Acceptance Criteria**: 1. 何かを変える。

## REPORT

- Implemented by:
"""


def phase_with_task(tmp_path: Path, text: str = TASK) -> Path:
    directory = tmp_path / "progress" / "phase-test"
    (directory / "tasks").mkdir(parents=True)
    (directory / "tasks" / "T-JOB-1.md").write_text(text, encoding="utf-8", newline="")
    return directory


# --- task protocol -----------------------------------------------------------


def test_task_reading_rejects_files_that_break_the_protocol(tmp_path: Path) -> None:
    broken = tmp_path / "broken.md"
    broken.write_text("id: T-1\n", encoding="utf-8")
    with pytest.raises(tasks.TaskFormatError):
        tasks.parse(broken)
    unclosed = tmp_path / "unclosed.md"
    unclosed.write_text("---\nid: T-1\nstatus: todo\n", encoding="utf-8")
    with pytest.raises(tasks.TaskFormatError):
        tasks.parse(unclosed)
    nested = tmp_path / "nested.md"
    nested.write_text("---\nid: T-1\nlist:\n  - a\n---\n", encoding="utf-8")
    with pytest.raises(tasks.TaskFormatError):
        tasks.parse(nested)
    unknown = tmp_path / "unknown.md"
    unknown.write_text(
        "---\nid: T-1\nphase: p\nstatus: shipped\nattempts: 0\n---\n", encoding="utf-8"
    )
    with pytest.raises(tasks.TaskFormatError):
        tasks.parse(unknown)


def test_updating_a_task_keeps_the_body_and_the_line_endings(tmp_path: Path) -> None:
    path = phase_with_task(tmp_path) / "tasks" / "T-JOB-1.md"
    path.write_bytes(TASK.replace("\n", "\r\n").encode("utf-8"))
    before = path.read_bytes().decode("utf-8")
    updated = tasks.update_fields(
        path,
        {"status": "doing", "reviewer": "opencode/other"},
        timestamp="2026-11-15T11:00:00+09:00",
    )
    # Read bytes: read_text would translate the endings and hide a rewrite.
    after = path.read_bytes().decode("utf-8")
    assert updated.status == "doing" and updated.reviewer == "opencode/other"
    assert updated.fields["updated"] == "2026-11-15T11:00:00+09:00"
    assert "\r\n" in after and "\n" not in after.replace("\r\n", "")
    assert "# Task `T-JOB-1`: 合成ジョブ" in after
    assert before.count("## REPORT") == after.count("## REPORT")
    tasks.append_section(path, "ATTEMPT 1", "evidence")
    final = path.read_bytes().decode("utf-8")
    assert "## ATTEMPT 1" in final and "\n" not in final.replace("\r\n", "")


def test_an_undecided_scope_is_not_an_open_scope(tmp_path: Path) -> None:
    path = (
        phase_with_task(
            tmp_path,
            TASK.replace(
                "allowed_paths: backend/app/service.py, tests/test_api.py",
                "allowed_paths: (未確定)",
            ),
        )
        / "tasks"
        / "T-JOB-1.md"
    )
    task = tasks.parse(path)
    assert task.allowed_paths == []
    assert not task.actionable


def test_attempt_limit_and_status_stop_a_job_being_picked_up(tmp_path: Path) -> None:
    directory = phase_with_task(tmp_path, TASK.replace("attempts: 0", "attempts: 3"))
    assert not tasks.load_phase(directory).tasks[0].actionable
    directory = phase_with_task(
        tmp_path / "second", TASK.replace("status: todo", "status: blocked")
    )
    assert not tasks.load_phase(directory).tasks[0].actionable


def test_a_job_waits_for_the_result_it_builds_on(tmp_path: Path) -> None:
    # The controller picks the lightest job first, so a light job written against
    # a heavier one's result would be dispatched before that result exists.
    directory = phase_with_task(tmp_path)
    (directory / "tasks" / "T-JOB-2.md").write_text(
        TASK.replace("T-JOB-1", "T-JOB-2").replace(
            "attempts: 0", "attempts: 0\ndepends_on: T-JOB-1"
        ),
        encoding="utf-8",
        newline="",
    )
    phase = tasks.load_phase(directory)
    second = next(task for task in phase.tasks if task.id == "T-JOB-2")
    assert second.actionable, "it is actionable on its own terms"
    assert phase.unmet(second) == ["T-JOB-1"] and not phase.ready(second)
    (directory / "tasks" / "T-JOB-1.md").write_text(
        TASK.replace("status: todo", "status: done"), encoding="utf-8", newline=""
    )
    done = tasks.load_phase(directory)
    assert done.ready(next(task for task in done.tasks if task.id == "T-JOB-2"))


def test_only_an_unanswered_decision_counts_as_waiting_on_the_owner(tmp_path: Path) -> None:
    # Answered requests stay in the file forever — they are the record of why the
    # code looks the way it does — so the file's existence cannot be the signal.
    directory = phase_with_task(tmp_path)
    phase = tasks.load_phase(directory)
    assert phase.open_decisions == []
    phase.decisions_file.write_text(
        "# Owner decisions\n\n"
        "## T-JOB-1 — scope (2026-01-01)\n\n"
        "**Question**: widen the scope?\n\n"
        "**Answer** (2026-01-02): no, split the job.\n\n"
        "## T-JOB-2 — limit (2026-01-03)\n\n"
        "**Question**: raise the wait limit?\n\n"
        "**Context**\n\nmeasured 35s per answer\n",
        encoding="utf-8",
        newline="",
    )
    assert tasks.load_phase(directory).open_decisions == ["T-JOB-2 — limit (2026-01-03)"]


# --- roster ------------------------------------------------------------------


def test_only_free_and_local_models_are_eligible_best_first() -> None:
    ranked = eligible(
        [
            "openai/gpt-6.1-sol",
            "opencode/iceman-free",
            "opencode/glm-5.3-flash-free",
            "opencode/big-pickle",
            "ollama/gemma3:4b",
            "opencode/brand-new-free",
        ]
    )
    assert "openai/gpt-6.1-sol" not in ranked, "a paid route must never enter the roster"
    assert "opencode/big-pickle" not in ranked, "only documented free identifiers are eligible"
    assert ranked[0] == "opencode/glm-5.3-flash-free"
    assert set(ranked) == {
        "opencode/glm-5.3-flash-free",
        "opencode/iceman-free",
        "ollama/gemma3:4b",
        "opencode/brand-new-free",
    }


def test_exhausted_models_rotate_and_a_reviewer_is_never_the_implementer(tmp_path: Path) -> None:
    models = ["a-free", "b-free"]
    roster = Roster(models=models, state_file=tmp_path / "roster.json", now=1000.0)
    assert roster.pick() == "a-free"
    assert roster.pick_reviewer("a-free") == "b-free"
    roster.mark_exhausted("a-free")
    assert roster.pick() == "b-free"
    assert roster.pick_reviewer("b-free") is None, "self-review must not be offered"
    later = Roster(models=models, state_file=tmp_path / "roster.json", now=1000.0 + 7 * 3600)
    assert later.pick() == "a-free", "cooldown has to expire"


def test_a_picked_model_is_recorded_under_the_identifier_the_cli_accepts() -> None:
    # The reviewer field is the evidence of independence, so it must name a model
    # that exists. Roster ids already carry their provider; a caller that adds one
    # writes `opencode/opencode/...`, which matches nothing.
    picked = eligible(["opencode/glm-5.3-flash-free", "ollama/gemma3:4b", "openai/gpt-5"])
    assert picked == ["opencode/glm-5.3-flash-free", "ollama/gemma3:4b"]
    for name in picked:
        assert name.count("/") == 1 and name.split("/")[0] in {"opencode", "ollama"}


# --- worker classification ---------------------------------------------------


def test_worker_distinguishes_exhaustion_from_failure() -> None:
    stream = (
        '{"type":"text","part":{"type":"text","text":"hello"}}\n'
        '{"type":"step_finish","part":{"type":"step-finish","tokens":{"input":3,"output":2}}}\n'
    )
    text, errors, tokens = worker.read_stream(stream)
    assert text == "hello" and not errors and tokens == 5
    assert worker.classify(["AI_APICallError: usage limit reached"]) is worker.Ending.EXHAUSTED
    assert worker.classify(["401 unauthorized"]) is worker.Ending.UNAVAILABLE
    assert worker.classify(["segfault"]) is worker.Ending.UNAVAILABLE


def test_worker_reports_the_ending_the_cli_actually_had(tmp_path: Path) -> None:
    class Completed:
        def __init__(self, code: int, out: str, err: str) -> None:
            self.returncode, self.stdout, self.stderr = code, out, err

    def quota(*_args, **_kwargs):
        return Completed(1, "", "Error: free usage quota exceeded for today")

    result = worker.run(
        "a-free", "do it", cwd=tmp_path, timeout=5, executable="opencode", runner=quota
    )
    assert result.ending is worker.Ending.EXHAUSTED and result.rotate

    def crash(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="opencode", timeout=5)

    assert (
        worker.run(
            "a-free", "do it", cwd=tmp_path, timeout=5, executable="opencode", runner=crash
        ).ending
        is worker.Ending.TIMEOUT
    )

    def answered(*args, **kwargs):
        # The brief is piped, never passed as an argument: a Windows command
        # line cannot hold a whole job text.
        assert "do it" in kwargs["input"]
        assert "do it" not in args[0]
        # Without --standalone the CLI reuses a background service rooted
        # elsewhere, and the worker edits the main checkout instead of its
        # worktree. This flag is the isolation.
        assert "--standalone" in args[0]
        assert kwargs["cwd"] == str(tmp_path)
        return Completed(0, '{"type":"text","part":{"type":"text","text":"REPORT\\nok"}}', "")

    good = worker.run(
        "a-free", "do it", cwd=tmp_path, timeout=5, executable="opencode", runner=answered
    )
    assert good.ending is worker.Ending.COMPLETED and "REPORT" in good.text


def test_a_resume_whose_gates_fail_goes_back_for_an_attempt_instead_of_spinning(
    tmp_path: Path,
) -> None:
    # `stranded()` resumes anything left in `review`, and a resume spends no
    # attempt. If a failing gate left the status at `review`, every later cycle
    # would resume the same job and re-run the same failing checks for ever.
    directory = phase_with_task(tmp_path, TASK.replace("status: todo", "status: review"))
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    tree = controller.settings.workspace_root / "T-JOB-1"
    tree.mkdir(parents=True)
    controller.dispatch = lambda *_args, **_kwargs: pytest.fail(  # type: ignore[assignment]
        "a resume must not dispatch a worker"
    )
    import jobloop.gates as gates_module

    original = gates_module.changed_files
    gates_module.changed_files = lambda _tree: ["frontend/src/App.tsx"]  # out of scope
    try:
        outcome = controller.resume(tasks.load_phase(directory).tasks[0])
    finally:
        gates_module.changed_files = original
    assert outcome.state == "gates-failed"
    task = tasks.load_phase(directory).tasks[0]
    assert task.status == "doing", "it must not stay resumable on a failing gate"
    assert task.attempts == 0, "a resume still spends no attempt"
    assert controller.stranded() == []


def test_an_approval_written_the_way_models_write_it_is_read_as_an_approval() -> None:
    # Measured 2026-11-20: `T-PH6-113`'s reviewer replied `**APPROVED**` with
    # `none` under FINDINGS. The pattern did not allow the asterisks, so the
    # approval was read as "changes required", the cycle limit tripped, and the
    # job was blocked with the word APPROVED sitting in its own record.
    for accepted in (
        "VERDICT\n- `APPROVED`\n",
        "## VERDICT\n\n**APPROVED**\n\n## FINDINGS\n- none\n",
        "VERDICT\n- APPROVED\n",
        "> APPROVED\n",
        "### APPROVED.\n",
    ):
        assert controller_module.APPROVAL.search(accepted), accepted

    for refused in (
        "VERDICT\n- CHANGES_REQUIRED\n",
        "- NOT APPROVED\n",
        "**APPROVED** with reservations\n",
        "I would have APPROVED this if the test existed\n",
        "APPROVED_WITH_CHANGES\n",
    ):
        assert not controller_module.APPROVAL.search(refused), refused


def test_a_provider_outage_rotates_and_never_spends_an_attempt(tmp_path: Path) -> None:
    # Measured 2026-11-20 03:08–03:16: the free endpoint answered
    # `404 Upstream request failed: Endpoint is unavailable` and five untouched
    # jobs went to `attempts 3/3` in eight minutes, each escalated as "three
    # attempts did not satisfy the acceptance criteria". None had been attempted.
    outage = [
        '{"type": "provider.invalid-request", "message": "Upstream request failed: '
        'Endpoint is unavailable.", "status": 404}'
    ]
    assert worker.classify(outage) is worker.Ending.OUTAGE
    assert worker.Result(worker.Ending.OUTAGE, "", "a-free").rotate, "the attempt must survive"
    # Usage exhaustion keeps its own wording: both rotate, and the record has to
    # say which happened, because only one of them means "come back tomorrow".
    spent = worker.Result(worker.Ending.EXHAUSTED, "", "a-free")
    assert spent.why_rotate != worker.Result(worker.Ending.OUTAGE, "", "a-free").why_rotate
    # A model that merely writes the words has not caused an outage: `classify`
    # only ever sees the CLI's own error text, and a real failure is not prose.
    assert worker.classify(["the handler returns 404 when the endpoint is unavailable"]) is (
        worker.Ending.OUTAGE
    ), "matched on CLI text only, which is why the brief is never passed to it"

    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.OUTAGE, "", model, ["Upstream request failed: Endpoint is unavailable."]
    )
    outcome = controller.run_job(controller.select())
    assert outcome.state == "rotated" and "endpoint is unavailable" in outcome.detail
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    assert task.attempts == 0, "an outage is the provider's failure, not the job's"
    assert task.status != "blocked"
    assert not (controller.settings.phase_directory / "OWNER_DECISIONS.md").exists()


def test_redirected_command_output_is_removed_and_recorded_not_escalated(tmp_path: Path) -> None:
    # Six jobs in three days were stopped by the same habit, three of them after
    # the brief was changed to forbid it in so many words. The instruction does
    # not take, so the loop stops losing jobs to it — loudly, never silently.
    allowed = ["backend/app/service.py", "tests/test_api.py"]
    work = {"backend/app/service.py": "from app.formats import table\n"}
    # Redirected output and one-off probes: nothing in the change mentions them.
    assert gates.litter(
        [
            "test_output.txt",
            "frontend/appearance_output.txt",
            "check_select3.py",
            "debug_test.py",
            "backend/app/service.py",
        ],
        allowed,
        contents=work,
    ) == ["check_select3.py", "debug_test.py", "frontend/appearance_output.txt", "test_output.txt"]

    # The neighbouring cases that must still stop the job.
    named = {"backend/app/service.py": "from app.connectors.base import Connector\n"}
    assert gates.litter(["backend/app/connectors/base.py"], allowed, contents=named) == [], (
        "a module the change imports is real work, and a scope drawn too narrowly"
    )
    assert gates.litter(["docs/plans/NOTES.md"], allowed, contents=work) == [], (
        "a protected path is never swept, whatever it is called"
    )
    assert gates.litter(["notes.txt"], [*allowed, "notes.txt"], contents=work) == [], (
        "a file the job was told to produce is its output, not its litter"
    )
    # A name that merely collides with an identifier is not a reference.
    # Measured 2026-11-22: `attack_pattern.txt` survived the sweep because the
    # job's own test contained `def test_attack_pattern_visible(...)`, and the
    # job then stopped for a file nothing read.
    collision = {"tests/test_api.py": "def test_attack_pattern_visible(service):\n    pass\n"}
    assert gates.litter(["attack_pattern.txt"], allowed, contents=collision) == [
        "attack_pattern.txt"
    ]
    # Named in full, it is the change's own data and must be kept.
    reads = {"tests/test_api.py": 'open("attack_pattern.txt").read()\n'}
    assert gates.litter(["attack_pattern.txt"], allowed, contents=reads) == []

    # Scratch may not vouch for scratch. Measured 2026-11-22: `T-PH7-211`'s
    # worker saved `git status` output into `git_status.txt`, that listing named
    # its eight sibling scratch files, and the whole set survived the sweep.
    circular = {
        "backend/app/service.py": "nothing to do with any of it\n",
        "git_status.txt": "?? debug_output.txt\n?? test_output.txt\n?? git_status.txt\n",
    }
    assert gates.litter(
        ["backend/app/service.py", "git_status.txt", "debug_output.txt", "test_output.txt"],
        allowed,
        contents=circular,
    ) == ["debug_output.txt", "git_status.txt", "test_output.txt"]
    # An in-scope file that could not be read might be the one that references
    # the loose path, so nothing is swept at all. Stopping the job is
    # recoverable; deleting a worker's real file is not.
    assert gates.litter(["backend/app/service.py", "helper.py"], allowed, contents={}) == [], (
        "an unread change disables sweeping entirely"
    )
    assert gates.litter(["helper.py"], allowed, contents={}) == ["helper.py"]

    # The controller only ever deletes what git does not track, so a committed
    # `.txt` the job edited cannot be swept away by this.
    tree = reviewable_worktree(tmp_path)
    (tree / "committed.txt").write_text("real content", encoding="utf-8")
    git(tree, "add", "committed.txt")
    git(tree, "commit", "-m", "a tracked text file")
    (tree / "committed.txt").write_text("edited by the job", encoding="utf-8")
    (tree / "test_output.txt").write_text("pytest said things", encoding="utf-8")
    changed = gates.changed_files(tree)
    loose = set(
        gates.litter(changed, allowed, contents=Controller.texts(tree, changed))
    ) & Controller.untracked(tree)
    assert loose == {"test_output.txt"}, "a tracked file is never swept"
    Controller.discard(tree, loose)
    assert not (tree / "test_output.txt").exists()
    assert (tree / "committed.txt").read_text(encoding="utf-8") == "edited by the job"


def test_a_timed_out_session_stops_writing_and_does_not_wedge_the_controller(
    tmp_path: Path,
) -> None:
    # Measured 2026-11-20: `opencode run` is a launcher, so killing only the
    # direct child left seven processes running. They went on writing scratch
    # files into `T-PH7-211`'s workspace for another twenty-two minutes, and
    # because they held the inherited stdout handle the controller's own drain
    # never returned — one cycle overshot its 90-minute budget by two hours with
    # the supervisor reporting nothing.
    marks = tmp_path / "grandchild.log"
    grandchild = (
        "import time\n"
        f"p = open({str(marks)!r}, 'a')\n"
        "while True:\n"
        "    p.write('x'); p.flush(); time.sleep(0.05)\n"
    )
    launcher = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
        "time.sleep(600)\n"
    )
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        worker.bounded(
            [sys.executable, "-c", launcher],
            cwd=str(tmp_path),
            input="",
            timeout=3,
            text=True,
            encoding="utf-8",
        )
    spent = time.monotonic() - started
    assert spent < 40, f"the drain blocked for {spent:.0f}s behind a surviving grandchild"
    size = marks.stat().st_size if marks.exists() else 0
    time.sleep(2)
    after = marks.stat().st_size if marks.exists() else 0
    assert after == size, "a killed session must not keep writing into the workspace"


# --- gates -------------------------------------------------------------------


def test_scope_gate_blocks_protected_and_out_of_scope_paths() -> None:
    allowed = ["backend/app/service.py", "tests/"]
    assert gates.within_scope(["backend/app/service.py", "tests/test_api.py"], allowed).green
    assert not gates.within_scope(["frontend/src/App.tsx"], allowed).green
    for protected in (".pi/harness/state.json", "docs/plans/PHASE_STATUS.md", "pyproject.toml"):
        gate = gates.within_scope([protected], allowed + [protected])
        assert not gate.green, f"{protected} must never be writable by a job"
        assert "protected" in gate.detail
    assert not gates.within_scope(["backend/app/service.py"], []).green


def test_controller_built_gates_do_not_depend_on_shell_quoting(tmp_path: Path) -> None:
    # A Windows interpreter path contains a drive letter and backslashes; a
    # shell-quoted form of it fails, so these gates must use an argument vector.
    spaced = tmp_path / "with space"
    spaced.mkdir()
    gate = gates.run_argv("echo", [sys.executable, "-c", "print(1)"], cwd=spaced, timeout=60)
    assert gate.green and "exit 0" in gate.detail
    missing = gates.run_argv("missing", ["definitely-not-a-binary"], cwd=spaced, timeout=60)
    assert not missing.ran and not missing.passed


def test_a_bare_python_is_bound_to_the_controllers_own_interpreter() -> None:
    # The job file must not name an interpreter by absolute path; the worker
    # reads that file and treats the checkout it points at as the project.
    bound = gates.with_interpreter(
        "python -m pytest tests/test_api.py -q", r"C:\x\.venv\python.exe"
    )
    assert bound == r'"C:\x\.venv\python.exe" -m pytest tests/test_api.py -q'
    # Anything that is not a leading bare interpreter is left alone.
    for command in ("npm --prefix frontend run test", "pythonx -m pytest", "./x/python -m pytest"):
        assert gates.with_interpreter(command, "P") == command


def test_a_frontend_job_is_typechecked_and_a_backend_job_is_not(tmp_path: Path) -> None:
    # `vitest` transpiles without typechecking, so a frontend job whose only gate
    # is its test command can land a type error with every check green.
    assert gates.frontend_gates(tmp_path, ["backend/app/service.py"], timeout=5) == []
    built = gates.frontend_gates(tmp_path, ["frontend/src/api.ts"], timeout=5)
    assert [gate.name for gate in built] == [
        "frontend-typecheck",
        "frontend-lint",
        # Unit tests render components; only this one lays out a real page and
        # can see that the top bar scrolled away or text ran off the edge.
        "frontend-test:appearance",
    ]


def test_a_gate_that_cannot_run_is_a_failure_not_a_pass(tmp_path: Path) -> None:
    assert not gates.run_command("empty", "   ", cwd=tmp_path, timeout=5).ran
    failing = gates.run_command("boom", "exit 3", cwd=tmp_path, timeout=60)
    assert failing.ran and not failing.passed and "exit 3" in failing.detail
    passing = gates.run_command("fine", "exit 0", cwd=tmp_path, timeout=60)
    assert passing.green


# --- controller --------------------------------------------------------------


def settings_for(tmp_path: Path) -> Settings:
    return Settings(repository=tmp_path, phase="phase-test", python="python")


def controller_for(tmp_path: Path, models: list[str]) -> Controller:
    roster = Roster(models=models, state_file=tmp_path / ".jobloop" / "roster.json", now=1000.0)
    return Controller(settings_for(tmp_path), roster, clock=lambda: 0.0)


def test_job_workspaces_live_outside_the_repository(tmp_path: Path) -> None:
    # A workspace inside the repository is not isolated: a session started there
    # resolves its project root to the main checkout and edits it.
    settings = settings_for(tmp_path)
    root = settings.workspace_root.resolve()
    assert settings.repository.resolve() not in root.parents
    assert root != settings.repository.resolve()


def test_a_commit_in_the_main_checkout_is_not_mistaken_for_an_escape(tmp_path: Path) -> None:
    # The operator commits to the main checkout while the loop runs — a ruling,
    # a fix to the loop itself. Every one of those moves HEAD, and judging
    # containment on HEAD blocked two innocent jobs on 2026-11-17 whose workers
    # had written only inside their own clones.
    repository = tmp_path / "main"
    repository.mkdir()
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "t@example.invalid")
    git(repository, "config", "user.name", "t")
    (repository / "a.txt").write_text("one", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "first")

    before_dirt = Controller.dirt(repository)
    before_print = Controller.fingerprint(repository)
    (repository / "a.txt").write_text("two", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "operator")

    assert Controller.fingerprint(repository) != before_print, "HEAD moved, as it should"
    assert Controller.dirt(repository) == before_dirt, "a clean commit is not an escape"
    # A worker leaving a file behind still is.
    (repository / "escaped.py").write_text("x = 1", encoding="utf-8")
    assert Controller.dirt(repository) != before_dirt

    # Containment is judged on what *appeared*. The operator committing
    # mid-dispatch makes its own uncommitted work vanish, and comparing whole
    # strings called that an escape too: `T-PH7-201` was blamed at 05:56 on
    # 2026-11-22 for exactly that, with `appeared:` empty in its own record.
    def appeared(before: str, now: str) -> list[str]:
        return sorted(set(now.splitlines()) - set(before.splitlines()))

    dirty = Controller.dirt(repository)
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "the operator commits its ruling")
    cleaned = Controller.dirt(repository)
    assert cleaned != dirty, "the dirt really did change"
    assert appeared(dirty, cleaned) == [], "nothing appeared, so nobody escaped"
    (repository / "escaped-again.py").write_text("x = 2", encoding="utf-8")
    assert appeared(cleaned, Controller.dirt(repository)) != [], "and a real escape still shows"


def test_a_job_left_in_review_is_picked_up_again(tmp_path: Path) -> None:
    # Review is not a resting state. A run that ends mid-review leaves the job
    # there, and `actionable` covers only todo/doing — so nothing ever collects
    # it. Three jobs sat that way through 239 idle cycles on 2026-11-19.
    directory = phase_with_task(tmp_path, TASK.replace("status: todo", "status: review"))
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    assert not tasks.load_phase(directory).tasks[0].actionable
    assert controller.select() is None, "nothing would be chosen for a new attempt"
    # Without its workspace there is nothing to resume, so it is not claimed.
    assert controller.stranded() == []
    (controller.settings.workspace_root / "T-JOB-1").mkdir(parents=True)
    assert [task.id for task in controller.stranded()] == ["T-JOB-1"]

    # A spent attempt budget must not hide it. Requiring `attempts < 3` here made
    # `review` plus `attempts 3/3` an invisible state, and three jobs sat in it
    # with finished work: `T-PH6-104`, `T-PH8-303`, `T-PH8-302`. A resume spends
    # no attempt, so the limit has nothing to say about it.
    spent = phase_with_task(
        tmp_path / "spent",
        TASK.replace("status: todo", "status: review").replace("attempts: 0", "attempts: 3"),
    )
    other = Controller(
        Settings(repository=tmp_path / "spent", phase="phase-test", python="python"),
        Roster(models=["a-free"], state_file=tmp_path / "spent" / "r.json", now=0.0),
        clock=lambda: 0.0,
    )
    (other.settings.workspace_root / "T-JOB-1").mkdir(parents=True)
    assert not tasks.load_phase(spent).tasks[0].actionable, "no new attempt is allowed"
    assert [task.id for task in other.stranded()] == ["T-JOB-1"], "but the review still finishes"


def test_a_job_naming_the_main_checkout_is_never_dispatched(tmp_path: Path) -> None:
    # Sanitising the brief is not enough: the worker opens its own job file.
    # On 2026-11-16 one read the absolute interpreter path out of `test_cmd`,
    # ran that interpreter, and went on to edit the checkout it belonged to.
    root = str(tmp_path)
    directory = phase_with_task(
        tmp_path, TASK.replace("test_cmd: ", f"test_cmd: {root}/.venv/bin/python ")
    )
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    dispatched: list[str] = []
    controller.dispatch = lambda model, prompt, **_: dispatched.append(model)  # type: ignore[assignment]
    outcome = controller.run_job(tasks.load_phase(directory).tasks[0])
    assert outcome.state == "escalated" and "another checkout" in outcome.detail
    assert not dispatched, "the worker must never be started"
    assert tasks.load_phase(directory).tasks[0].status == "blocked"


def test_a_worker_that_edits_the_main_checkout_is_escalated(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- done", model
    )
    seen: list[str] = []

    def dirt(path: Path) -> str:
        # The main checkout has files in it that were not there before.
        seen.append(str(path))
        return f"state-{len(seen)}"

    controller.dirt = dirt  # type: ignore[assignment]
    outcome = controller.run_job(controller.select())
    assert outcome.state == "escalated" and "outside its workspace" in outcome.detail
    decisions = (controller.settings.phase_directory / "OWNER_DECISIONS.md").read_text(
        encoding="utf-8"
    )
    assert "restore the checkout" in decisions


def test_no_path_to_another_checkout_survives_in_a_brief(tmp_path: Path) -> None:
    # A job's own test command names an interpreter in the main checkout. Left in
    # the brief, a worker reads it as "the project is over there" and edits it.
    outside = "D:\\team\\Locus"
    text = TASK.replace(
        "test_cmd: python -c \"print('ok')\"",
        "test_cmd: " + outside + "\\.venv\\Scripts\\python.exe -m pytest tests/test_api.py -q",
    )
    task = tasks.load_phase(phase_with_task(tmp_path, text)).tasks[0]
    brief = prompts.implementer_brief(
        task, attempt=1, repository="/workspaces/T-JOB-1", outside=outside
    )
    assert outside not in brief
    assert outside.replace("\\", "/") not in brief
    assert "/workspaces/T-JOB-1" in brief
    review = prompts.reviewer_brief(
        task,
        diff="d",
        evidence="- ran " + outside + "/scripts/secret_scan.py",
        repository="/workspaces/T-JOB-1",
        outside=outside,
    )
    assert outside not in review and outside.replace("\\", "/") not in review


def test_the_shown_command_names_an_interpreter_the_workspace_actually_has() -> None:
    # Rewriting the main checkout's path into the workspace is right for every
    # path except the interpreter: the workspace has no `.venv`, so the brief then
    # instructs the worker to run a binary that does not exist.
    outside = "C:\\Users\\x\\Locus"
    shown = prompts.shown_command(
        outside + "\\.venv\\Scripts\\python.exe -m pytest tests/test_api.py -q",
        outside,
        "/workspaces/T-JOB-1",
    )
    assert shown == "python.exe -m pytest tests/test_api.py -q"
    assert "/workspaces/T-JOB-1" not in shown and outside not in shown
    # A path that is not the leading interpreter is still rewritten, not stripped.
    assert prompts.shown_command(
        "python -m pytest " + outside + "/tests/test_api.py", outside, "/ws"
    ) == ("python -m pytest /ws/tests/test_api.py")


def test_the_reviewer_is_told_that_quoted_findings_are_history(tmp_path: Path) -> None:
    # A weak reviewer restated the previous round's findings, all three already
    # fixed. The brief has to say the diff is the evidence, not the job text.
    task = tasks.load_phase(phase_with_task(tmp_path)).tasks[0]
    review = prompts.reviewer_brief(task, diff="d", evidence="e", repository="/ws")
    assert "history" in review
    assert "Re-check every finding" in review


def test_the_brief_names_the_workspace_not_the_main_checkout(tmp_path: Path) -> None:
    # A brief that names the main checkout invites the worker to edit it, which
    # is how three containment failures happened on 2026-11-15.
    task = tasks.load_phase(phase_with_task(tmp_path)).tasks[0]
    brief = prompts.implementer_brief(task, attempt=1, repository="/workspaces/T-JOB-1")
    assert "/workspaces/T-JOB-1" in brief
    assert "nothing outside it is yours to change" in brief
    assert "containment failure" in brief
    review = prompts.reviewer_brief(task, diff="d", evidence="e", repository="/workspaces/T-JOB-1")
    assert "/workspaces/T-JOB-1" in review


def test_usage_exhaustion_rotates_without_spending_an_attempt(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.EXHAUSTED, "", model, ["quota"]
    )
    outcome = controller.run_job(controller.select())
    assert outcome.state == "rotated"
    assert tasks.load_phase(controller.settings.phase_directory).tasks[0].attempts == 0
    assert controller.roster.pick() == "b-free"


def test_a_worker_asking_for_a_decision_escalates_instead_of_guessing(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED,
        "REPORT\n- unclear\n\nSTATUS\n- needs-owner-decision: which format wins?",
        model,
    )
    outcome = controller.run_job(controller.select())
    assert outcome.state == "escalated" and "which format wins?" in outcome.detail
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    assert task.status == "blocked"
    decisions = (controller.settings.phase_directory / "OWNER_DECISIONS.md").read_text(
        encoding="utf-8"
    )
    assert "which format wins?" in decisions and "T-JOB-1" in decisions


def test_an_echoed_status_template_is_a_failed_attempt_not_a_decision(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED,
        "REPORT\n- nothing\n\nSTATUS\n- needs-owner-decision: <the question>",
        model,
    )
    outcome = controller.run_job(controller.select())
    assert outcome.state == "attempt-failed" and "echoed" in outcome.detail
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    assert task.status == "doing" and task.attempts == 1
    assert not (controller.settings.phase_directory / "OWNER_DECISIONS.md").exists()


def test_three_failed_attempts_stop_and_ask_the_owner(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- nothing", model
    )
    states = []
    for _ in range(3):
        task = controller.select()
        assert task is not None
        states.append(controller.run_job(task).state)
    assert states == ["attempt-failed", "attempt-failed", "escalated"]
    assert controller.select() is None, "a blocked job must not be picked up again"


def test_no_second_model_means_no_review_and_no_commit(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["only-free"])
    task = controller.select()
    assert task is not None
    # The implementer used the only model, so there is nobody left to review it.
    outcome = controller.review(task, tmp_path, "only-free", [])
    assert outcome.state == "escalated" and "reviewer" in outcome.detail
    assert tasks.load_phase(controller.settings.phase_directory).tasks[0].status == "blocked"
    decisions = (controller.settings.phase_directory / "OWNER_DECISIONS.md").read_text(
        encoding="utf-8"
    )
    assert "5-5" in decisions, "the prohibition on self-review must be cited"


def reviewable_worktree(tmp_path: Path) -> Path:
    """A committed worktree with one uncommitted change, as a review sees it."""
    tree = tmp_path / "ws"
    tree.mkdir()
    git(tree, "init", "-b", "main")
    git(tree, "config", "user.email", "t@example.invalid")
    git(tree, "config", "user.name", "t")
    (tree / "a.txt").write_text("one", encoding="utf-8")
    git(tree, "add", "-A")
    git(tree, "commit", "-m", "first")
    (tree / "a.txt").write_text("under review", encoding="utf-8")
    return tree


def test_a_conflicting_merge_is_aborted_and_never_left_in_the_checkout(tmp_path: Path) -> None:
    # The worst stop this loop has had. On 2026-11-20 `T-PH6-113`'s reviewed work
    # no longer applied, the merge conflicted, and `MERGE_HEAD` plus two `UU`
    # files were left in the main checkout. Every later job then reported "the
    # integration branch is dirty": eleven jobs blocked, seven hours idle, and
    # the job itself recorded as `done` with its change nowhere in the branch.
    phase_with_task(tmp_path)
    repository = tmp_path
    git(repository, "init", "-b", "loop/local-development", check=False)
    git(repository, "config", "user.email", "t@example.invalid")
    git(repository, "config", "user.name", "t")
    (repository / "shared.txt").write_text("base\n", encoding="utf-8")
    # The loop's own state is ignored here as it is in the real repository;
    # otherwise it reads as a person's uncommitted edit and stops the merge
    # before the conflict this test is about.
    (repository / ".gitignore").write_text(".jobloop/\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "base")

    # Outside the repository, like a real workspace: a clone inside it would be
    # an untracked directory and the merge would stop on that instead.
    tree = tmp_path.parent / f"{tmp_path.name}-ws"
    git(repository, "clone", "--local", str(repository), str(tree))
    git(tree, "config", "user.email", "t@example.invalid")
    git(tree, "config", "user.name", "t")
    git(tree, "checkout", "-B", "loop/T-JOB-1")
    (tree / "shared.txt").write_text("the job's line\n", encoding="utf-8")

    # The branch moved underneath the job, in the same place.
    (repository / "shared.txt").write_text("someone else's line\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "the branch moved")

    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.settings.push = False
    outcome = controller.deliver(
        tasks.load_phase(controller.settings.phase_directory).tasks[0], tree, "a-free", "b-free", []
    )

    assert outcome.state == "escalated" and "merge conflicted" in outcome.detail
    assert not (repository / ".git" / "MERGE_HEAD").exists(), "no merge may be left in progress"
    assert not git(repository, "diff", "--name-only", "--diff-filter=U", check=False).strip()
    assert (repository / "shared.txt").read_text(encoding="utf-8") == "someone else's line\n"
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    assert task.status == "blocked", "and certainly not `done`"


def test_every_phases_records_count_as_the_loops_own_bookkeeping(tmp_path: Path) -> None:
    # One supervisor walks several phases through one checkout, so phase-7's
    # records from the previous pass are uncommitted when phase-6 comes to merge.
    # Sweeping only the running phase read those as a person's edit and blocked
    # five jobs on 2026-11-20/21.
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    status_text = ""
    added: list[tuple[str, ...]] = []

    def fake_git(repository: Path, *arguments: str, check: bool = True) -> str:
        if arguments[0] == "status":
            return status_text
        added.append(arguments)
        return ""

    import jobloop.controller as module

    original = module.git
    module.git = fake_git  # type: ignore[assignment]
    try:
        task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
        status_text = (
            " M progress/phase-test/tasks/T-JOB-1.md\n"
            " M progress/phase-7-production/OWNER_DECISIONS.md\n"
            " M docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html"
        )
        assert controller.commit_progress_records(task) == "", (
            "another phase's records are the loop's own, not a person's"
        )
        assert any("commit" in arguments for arguments in added)
        # A person's edit still stops the merge.
        added.clear()
        status_text = " M progress/phase-test/tasks/T-JOB-1.md\n M backend/app/service.py"
        assert "backend/app/service.py" in controller.commit_progress_records(task)
        assert not any("commit" in arguments for arguments in added)
    finally:
        module.git = original


def test_a_stale_workspace_is_taken_to_the_current_branch_before_a_new_attempt(
    tmp_path: Path,
) -> None:
    # A clone is made once and kept, so a job that waits days starts from a base
    # that has moved. That drift is what made `T-PH6-113`'s merge conflict.
    phase_with_task(tmp_path)
    repository = tmp_path
    git(repository, "init", "-b", "loop/local-development", check=False)
    git(repository, "config", "user.email", "t@example.invalid")
    git(repository, "config", "user.name", "t")
    (repository / "a.txt").write_text("base\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "base")

    controller = controller_for(tmp_path, ["a-free", "b-free"])
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    tree = controller.workspace(task)
    assert (tree / "a.txt").read_text(encoding="utf-8") == "base\n"

    (repository / "a.txt").write_text("moved on\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "the branch moved")

    controller.workspace(task)
    assert (tree / "a.txt").read_text(encoding="utf-8") == "moved on\n"
    body = (tmp_path / "progress" / "phase-test" / "tasks" / "T-JOB-1.md").read_text(
        encoding="utf-8"
    )
    assert "WORKSPACE REBASED" in body, "a reset the job did not ask for has to be recorded"

    # Work in progress is never thrown away for the sake of a fresh base.
    (tree / "a.txt").write_text("the job is mid-attempt\n", encoding="utf-8")
    (repository / "b.txt").write_text("and the branch moved again\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "again")
    controller.workspace(task)
    assert (tree / "a.txt").read_text(encoding="utf-8") == "the job is mid-attempt\n"


def test_the_secret_scan_gate_asks_about_this_change_only(tmp_path: Path) -> None:
    # A full-tree scan failed `T-PH7-201` on 2026-11-22 for a finding in
    # `T-PH7-222`'s recorded report: another job's prose, in a file the attempt
    # never touched, and prose about passwords rather than a password. A gate
    # that fails a job for someone else's file is attributing blame at random.
    changed = ["backend/app/service.py", "tests/test_api.py"]
    import jobloop.gates as module

    seen: list[list[str]] = []

    def record(name: str, argv: list[str], **_: object) -> gates.Gate:
        seen.append(argv)
        return gates.Gate(name, True, True, "")

    original = module.run_argv
    module.run_argv = record  # type: ignore[assignment]
    try:
        module.python_gates(tmp_path, changed, python="python", timeout=5)
    finally:
        module.run_argv = original
    secret = next(argv for argv in seen if any("secret_scan.py" in part for part in argv))
    assert secret[-2:] == ["backend/app/service.py", "tests/test_api.py"], secret
    assert "progress" not in " ".join(secret), "no other job's records are in scope"
    # The controller's own copy, aimed at the worktree. The workspace's copy is
    # whatever base that clone was made from: a fix at 04:35 on 2026-11-22 still
    # failed `T-PH7-201` at 05:10 because its clone predated the fix.
    script = next(part for part in secret if "secret_scan.py" in part)
    assert Path(script).is_file(), script
    assert str(tmp_path) not in script, "the instrument must not come from the workspace"
    assert secret[secret.index("--root") + 1] == str(tmp_path), secret


def test_scratch_is_swept_before_a_worker_can_trip_over_it(tmp_path: Path) -> None:
    # Sweeping only after a dispatch left the previous attempt's scratch in the
    # workspace, and the next worker stopped to ask about files it was forbidden
    # to touch: `T-PH6-126` about 26 of them, `T-PH7-222` about an
    # `attack_pattern.txt` that was failing the secret scan. Both questions were
    # the loop's own to answer.
    phase_with_task(tmp_path)
    tree = reviewable_worktree(tmp_path)
    (tree / "check_select3.py").write_text("print('probe')\n", encoding="utf-8")
    (tree / "pytest_out.txt").write_text("1 failed\n", encoding="utf-8")
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tree  # type: ignore[assignment]
    seen: list[str] = []

    def dispatch(model: str, prompt: str, **_: object) -> worker.Result:
        # What the worker sees when it starts, which is the whole point.
        seen.extend(sorted(path.name for path in tree.iterdir() if path.is_file()))
        return worker.Result(worker.Ending.COMPLETED, "REPORT\n- did the work", model)

    controller.dispatch = dispatch  # type: ignore[assignment]
    controller.run_job(tasks.load_phase(controller.settings.phase_directory).tasks[0])

    assert "check_select3.py" not in seen and "pytest_out.txt" not in seen
    assert "a.txt" in seen, "and the work itself is still there"
    body = (tmp_path / "progress" / "phase-test" / "tasks" / "T-JOB-1.md").read_text(
        encoding="utf-8"
    )
    assert "WORKER LITTER REMOVED" in body, "a silent sweep teaches the next worker nothing"


def test_a_workspace_holding_its_own_commit_is_never_reset(tmp_path: Path) -> None:
    # `deliver` commits the reviewed work *before* it tries to merge, so a job
    # blocked at the merge has its work in a commit and a perfectly clean tree.
    # Checking only the tree discarded five reviewed commits on 2026-11-21.
    phase_with_task(tmp_path)
    repository = tmp_path
    git(repository, "init", "-b", "loop/local-development", check=False)
    git(repository, "config", "user.email", "t@example.invalid")
    git(repository, "config", "user.name", "t")
    (repository / ".gitignore").write_text(".jobloop/\n", encoding="utf-8")
    (repository / "a.txt").write_text("base\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "base")

    controller = controller_for(tmp_path, ["a-free", "b-free"])
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    tree = controller.workspace(task)

    # The job finishes its work and the controller commits it, as `deliver` does.
    (tree / "delivered.py").write_text("x = 1\n", encoding="utf-8")
    git(tree, "config", "user.email", "t@example.invalid")
    git(tree, "config", "user.name", "t")
    git(tree, "add", "-A")
    git(tree, "commit", "-m", "the reviewed work")
    reviewed = git(tree, "rev-parse", "HEAD").strip()
    assert not Controller.dirt(tree).strip(), "a committed job leaves a clean tree"

    # Meanwhile the integration branch moves on, so the workspace is behind.
    (repository / "a.txt").write_text("moved on\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "the branch moved")

    controller.workspace(task)
    assert git(tree, "rev-parse", "HEAD").strip() == reviewed, "the job's commit must survive"
    assert (tree / "delivered.py").is_file()
    body = (tmp_path / "progress" / "phase-test" / "tasks" / "T-JOB-1.md").read_text(
        encoding="utf-8"
    )
    assert "WORKSPACE NOT REBASED" in body, "and the reader has to be told why it is stale"


def test_a_reviewer_that_writes_its_review_to_a_file_is_replaced_not_escalated(
    tmp_path: Path,
) -> None:
    # Measured 2026-11-19: `T-PH6-113`'s reviewer left `review_output.md` and
    # touched nothing else, and the job went to a person for a ruling that could
    # only ever be "try another model". The verdict is still void — a model that
    # ignored "create no file" is not one to take a verdict from, and `deliver`
    # runs `git add -A`, so the stray file would be committed with the work.
    phase_with_task(tmp_path)
    tree = reviewable_worktree(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free", "c-free"])
    asked: list[str] = []

    def dispatch(model: str, prompt: str, **_: object) -> worker.Result:
        asked.append(model)
        if model == "b-free":
            (tree / "review_output.md").write_text("VERDICT\n- APPROVED", encoding="utf-8")
            return worker.Result(worker.Ending.COMPLETED, "written to review_output.md", model)
        return worker.Result(worker.Ending.COMPLETED, "VERDICT\n- CHANGES_REQUIRED", model)

    controller.dispatch = dispatch  # type: ignore[assignment]
    task = controller.select()
    assert task is not None
    outcome = controller.review(task, tree, "a-free", [])

    assert asked == ["b-free", "c-free"], "the next model reviews it, with no human in between"
    assert not (tree / "review_output.md").exists(), "the stray file must not reach the commit"
    assert (tree / "a.txt").read_text(encoding="utf-8") == "under review", "work untouched"
    assert outcome.state == "changes-required", "the replacement review is the one that counts"
    body = (tmp_path / "progress" / "phase-test" / "tasks" / "T-JOB-1.md").read_text(
        encoding="utf-8"
    )
    assert "REVIEWER WROTE TO DISK" in body, "a discarded verdict has to leave a trace"
    assert "b-free" in body
    assert not (controller.settings.phase_directory / "OWNER_DECISIONS.md").exists()


def test_a_reviewer_that_edits_the_work_still_stops_the_job(tmp_path: Path) -> None:
    # The neighbouring case that must keep stopping: a reviewer that changed the
    # code under review has poisoned the review, and no re-review can undo that
    # — the next model would be reviewing the reviewer's edit.
    phase_with_task(tmp_path)
    tree = reviewable_worktree(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free", "c-free"])
    asked: list[str] = []

    def dispatch(model: str, prompt: str, **_: object) -> worker.Result:
        asked.append(model)
        (tree / "a.txt").write_text("the reviewer fixed it", encoding="utf-8")
        return worker.Result(worker.Ending.COMPLETED, "VERDICT\n- APPROVED", model)

    controller.dispatch = dispatch  # type: ignore[assignment]
    task = controller.select()
    assert task is not None
    outcome = controller.review(task, tree, "a-free", [])

    assert asked == ["b-free"], "no second model is tried on a poisoned worktree"
    assert outcome.state == "escalated" and "modified the worktree" in outcome.detail
    assert tasks.load_phase(controller.settings.phase_directory).tasks[0].status == "blocked"


def test_every_reviewer_writing_to_disk_ends_as_a_question_not_a_loop(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    tree = reviewable_worktree(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free", "c-free"])
    asked: list[str] = []

    def dispatch(model: str, prompt: str, **_: object) -> worker.Result:
        asked.append(model)
        (tree / f"{model}-notes.md").write_text("verdict", encoding="utf-8")
        return worker.Result(worker.Ending.COMPLETED, "VERDICT\n- APPROVED", model)

    controller.dispatch = dispatch  # type: ignore[assignment]
    task = controller.select()
    assert task is not None
    outcome = controller.review(task, tree, "a-free", [])

    assert asked == ["b-free", "c-free"], "each model is tried once, then the loop gives up"
    assert outcome.state == "escalated"
    decisions = (controller.settings.phase_directory / "OWNER_DECISIONS.md").read_text(
        encoding="utf-8"
    )
    assert "wrote to the worktree" in decisions and "b-free" in decisions and "c-free" in decisions


def test_only_the_controllers_own_records_are_swept_into_a_commit(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    commands: list[tuple[str, ...]] = []

    def fake_git(repository: Path, *arguments: str, check: bool = True) -> str:
        commands.append(arguments)
        if arguments[0] == "status":
            return status_text
        return ""

    import jobloop.controller as module

    original = module.git
    module.git = fake_git  # type: ignore[assignment]
    try:
        task = controller.select()
        assert task is not None
        status_text = (
            " M progress/phase-test/tasks/T-JOB-1.md\n?? progress/phase-test/OWNER_DECISIONS.md"
        )
        assert controller.commit_progress_records(task) == ""
        assert any("commit" in arguments for arguments in commands)
        commands.clear()
        # A person's uncommitted work is never swept into the loop's commit.
        status_text = " M backend/app/service.py"
        assert "backend/app/service.py" in controller.commit_progress_records(task)
        assert not any("commit" in arguments for arguments in commands)
    finally:
        module.git = original  # type: ignore[assignment]


def test_the_implementer_brief_states_the_boundary_and_the_skills(tmp_path: Path) -> None:
    task = tasks.load_phase(phase_with_task(tmp_path)).tasks[0]
    brief = prompts.implementer_brief(task, attempt=1, repository="repo")
    for expected in (
        "allowed_paths",
        "docs/plans/",
        "Never delete, skip, relax or rewrite an existing test",
        "needs-owner-decision",
        ".agents/skills/verification-before-completion/SKILL.md",
        task.test_command,
        "authoritative",
        "合成ジョブ",
    ):
        assert expected in brief
    review = prompts.reviewer_brief(
        task, diff="--- a\n+++ b", evidence="- scope: ok", repository="repo"
    )
    assert "read-only" in review and "APPROVED" in review and "do not commit" in review.lower()
