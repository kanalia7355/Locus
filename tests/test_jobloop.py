"""The job loop must be boringly deterministic: no model gets to decide anything.

These tests use fake workers, so no provider is contacted.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from jobloop import controller as controller_module
from jobloop import gates, prompts, tasks, worker
from jobloop import roster as roster_module
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


def test_containment_rate_rests_a_model_but_needs_enough_dispatches(tmp_path: Path) -> None:
    from jobloop.roster import CONTAINMENT_MIN_DISPATCHES, CONTAINMENT_RATE, COOLDOWN_SECONDS

    assert CONTAINMENT_MIN_DISPATCHES == 5
    assert CONTAINMENT_RATE == 0.5
    roster = Roster(models=["a-free", "b-free"], state_file=tmp_path / "r.json", now=1000.0)
    for _ in range(6):
        roster.mark_dispatched("a-free")
    report = {}
    for _ in range(4):
        report = roster.mark_containment_stop("a-free", orchestrator_busy=False)
    assert report["rested"] is True
    assert report["dispatches"] == 6
    assert report["containment_stops"] == 4
    assert roster.pick() == "b-free", "rested model is cooled down like usage exhaustion"
    later = Roster(
        models=["a-free", "b-free"],
        state_file=tmp_path / "r.json",
        now=1000.0 + COOLDOWN_SECONDS + 1,
    )
    assert later.pick() == "a-free", "containment rest uses the normal cooldown window"

    few = Roster(models=["c-free", "d-free"], state_file=tmp_path / "few.json", now=1000.0)
    for _ in range(4):
        few.mark_dispatched("c-free")
    for _ in range(4):
        report = few.mark_containment_stop("c-free", orchestrator_busy=False)
    assert report["rested"] is False, "not enough dispatches: denominator is too small"
    assert few.pick() == "c-free"


def test_orchestrator_busy_containment_stops_never_count(tmp_path: Path) -> None:
    roster = Roster(models=["a-free"], state_file=tmp_path / "r.json", now=1000.0)
    for _ in range(10):
        roster.mark_dispatched("a-free")
    for _ in range(10):
        report = roster.mark_containment_stop("a-free", orchestrator_busy=True)
        assert report["counted"] is False
        assert report["rested"] is False
    assert roster.pick() == "a-free"
    dispatches, stops = roster.containment_stats("a-free")
    assert dispatches == 10
    assert stops == 0


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


def test_waiting_for_a_reviewer_does_not_re_run_the_gates(tmp_path: Path) -> None:
    # A resume runs the job's whole gate suite, and with the roster empty that
    # work is thrown away one step later. Measured 2026-11-22: `T-PH8-302`
    # re-ran its gates twice every two minutes for an hour to reach a reviewer
    # that was never there. Waiting has to cost nothing.
    directory = phase_with_task(tmp_path, TASK.replace("status: todo", "status: review"))
    controller = controller_for(tmp_path, ["only-free"])
    (controller.settings.workspace_root / "T-JOB-1").mkdir(parents=True)
    import jobloop.gates as module

    original = module.changed_files
    module.changed_files = lambda _tree: pytest.fail("the gates must not run")  # type: ignore[assignment]
    try:
        task = tasks.load_phase(directory).tasks[0]
        controller.set_fields(task, model="only-free")
        outcome = controller.resume(tasks.load_phase(directory).tasks[0])
    finally:
        module.changed_files = original
    assert outcome.state == "no-reviewer", outcome.detail
    assert tasks.load_phase(directory).tasks[0].status == "review", "it stays resumable"

    # And one such answer ends the cycle: nothing else in it can get further.
    controller.dispatch = lambda *_a, **_k: pytest.fail("no dispatch either")  # type: ignore[assignment]
    outcomes = controller.run(minutes=1, max_jobs=5)
    assert [outcome.state for outcome in outcomes] == ["no-reviewer"], outcomes


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

    # Test data in `tests/test_jobloop.py` itself must not shield loose scratch
    # files (e.g. `test_output.txt` when `tests/test_jobloop.py` is in scope),
    # while real usages (imports or `open(...)` calls) in test files still do.
    self_test_text = Path(__file__).read_text(encoding="utf-8")
    assert gates.litter(
        ["tests/test_jobloop.py", "test_output.txt"],
        ["tests/test_jobloop.py"],
        contents={"tests/test_jobloop.py": self_test_text},
    ) == ["test_output.txt"]
    assert (
        gates.litter(
            ["helper.py"],
            ["tests/test_api.py"],
            contents={"tests/test_api.py": "import helper\n"},
        )
        == []
    )
    assert (
        gates.litter(
            ["attack_pattern.txt"],
            ["tests/test_api.py"],
            contents={"tests/test_api.py": 'open("attack_pattern.txt").read()\n'},
        )
        == []
    )


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
        # can see that the top bar scrolled away or text ran off the edge. It is
        # the whole `e2e/` suite, not one file: see the comment in `frontend_gates`.
        "frontend-test:e2e",
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

    # Records and planning are not an escape. The owner writes task drafts into
    # `progress/` whenever they like, and `T-PH6-127` was accused on 2026-11-22
    # because `progress/phase-storage-connect/tasks/T-STC-005.md` appeared while
    # it ran. The marker cannot cover that: the owner does not run shifts.
    assert Controller.bookkeeping("?? progress/phase-x/tasks/T-A-1.md")
    assert Controller.bookkeeping(" M docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html")
    # Product code appearing in the main checkout still is an escape.
    assert not Controller.bookkeeping("?? backend/app/service.py")
    assert not Controller.bookkeeping(" M frontend/src/App.tsx")
    assert not Controller.bookkeeping("?? progress-notes.txt"), "prefix, not substring"

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


def test_a_path_in_the_body_is_told_apart_from_one_in_the_frontmatter(tmp_path: Path) -> None:
    # Task files are CRLF, so `"\n---\n"` never matched before CRLF
    # normalisation, and `head` became the whole file. `T-PH7-201` was blocked
    # on 2026-11-22 by a path inside a ruling because of that one `\r`.
    # With T-PH9-406, both body and frontmatter occurrences of the main-checkout
    # root are redacted via self-repair rather than left in the job file.
    root = str(tmp_path)
    directory = phase_with_task(tmp_path, TASK + f"\n## ORCHESTRATOR RULING\n\nsee {root}\n")
    path = directory / "tasks" / "T-JOB-1.md"
    path.write_bytes(path.read_bytes().decode("utf-8").replace("\n", "\r\n").encode("utf-8"))
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.dispatch = lambda *_args, **_kwargs: pytest.fail("must not dispatch")  # type: ignore[assignment]
    outcome = controller.run_job(tasks.load_phase(directory).tasks[0])
    assert outcome.state == "self-repaired", outcome.detail
    assert root not in path.read_bytes().decode("utf-8"), "the body occurrence is redacted"


def test_a_job_naming_the_main_checkout_is_never_dispatched(tmp_path: Path) -> None:
    # Sanitising the brief is not enough: the worker opens its own job file.
    # On 2026-11-16 one read the absolute interpreter path out of `test_cmd`,
    # ran that interpreter, and went on to edit the checkout it belonged to.
    # With the T-PH9-406 fix, the absolute path in the job file (including
    # backslash or forward-slash forms in frontmatter) is redacted by
    # self-repair before any worker is dispatched.
    root = str(tmp_path)
    slash_root = root.replace("\\", "/")
    directory = phase_with_task(
        tmp_path, TASK.replace("test_cmd: ", f"test_cmd: {slash_root}/.venv/bin/python ")
    )
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    dispatched: list[str] = []
    controller.dispatch = lambda model, prompt, **_: dispatched.append(model)  # type: ignore[assignment]
    outcome = controller.run_job(tasks.load_phase(directory).tasks[0])
    assert outcome.state == "self-repaired"
    assert not dispatched, "the worker must never be started"
    record = (directory / "tasks" / "T-JOB-1.md").read_bytes().decode("utf-8")
    for form in {root, slash_root, root.replace("/", "\\")}:
        assert form not in record, "the absolute checkout path must not remain in the job file"
    assert controller.points_outside(tasks.load_phase(directory).tasks[0]) == ""


def test_containment_record_omits_absolute_repository_root(tmp_path: Path) -> None:
    # The worker reads its own job file. An absolute path there teaches it the
    # main checkout's location — the same escape route this ticket closes.
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path / "ws"  # type: ignore[assignment]
    (tmp_path / "ws").mkdir()
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- done", model
    )
    seen: list[str] = []

    def dirt(path: Path) -> str:
        seen.append(str(path))
        return "" if len(seen) == 1 else " M backend/app/service.py abc123\n"

    controller.dirt = dirt  # type: ignore[assignment]
    outcome = controller.run_job(controller.select())
    assert outcome.state == "escalated" and "outside its workspace" in outcome.detail
    root = str(controller.settings.repository)
    body = (controller.settings.phase_directory / "tasks" / "T-JOB-1.md").read_text(
        encoding="utf-8"
    )
    decisions = (controller.settings.phase_directory / "OWNER_DECISIONS.md").read_text(
        encoding="utf-8"
    )
    for form in {root, root.replace("\\", "/"), root.replace("/", "\\")}:
        assert form not in body, "the job record must not name the checkout"
        assert form not in decisions, "the owner decision must not name the checkout"
    assert "marker=.jobloop/orchestrator-busy present=False" in decisions


def test_containment_record_keeps_present_for_both_marker_states(tmp_path: Path) -> None:
    # present=True/False is how a reader tells "the operator was editing" from
    # "the worker escaped". Dropping it loses the first fact the record is read for.
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path / "ws"  # type: ignore[assignment]
    (tmp_path / "ws").mkdir()
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- done", model
    )
    seen = {"n": 0}

    def dirt(_path: Path) -> str:
        seen["n"] += 1
        return "" if seen["n"] == 1 else " M backend/app/service.py abc123\n"

    controller.dirt = dirt  # type: ignore[assignment]

    # Marker absent: a real containment stop records present=False.
    outcome = controller.run_job(controller.select())
    assert outcome.state == "escalated"
    decisions = (controller.settings.phase_directory / "OWNER_DECISIONS.md").read_text(
        encoding="utf-8"
    )
    assert "marker=.jobloop/orchestrator-busy present=False" in decisions

    # Marker present: the comparison is suspended, and the record still says the
    # marker was there.
    busy_directory = phase_with_task(tmp_path / "busy", TASK)
    busy = controller_for(tmp_path / "busy", ["a-free", "b-free"])
    busy.workspace = lambda task: tmp_path / "busy-ws"  # type: ignore[assignment]
    (tmp_path / "busy-ws").mkdir()
    busy.operator_busy = lambda: True  # type: ignore[assignment]
    busy.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED,
        "REPORT\n- done\n\nSTATUS\n- needs-owner-decision: which retry budget applies?",
        model,
    )
    busy_seen = {"n": 0}

    def busy_dirt(_path: Path) -> str:
        busy_seen["n"] += 1
        return "" if busy_seen["n"] == 1 else " M backend/app/service.py abc123\n"

    busy.dirt = busy_dirt  # type: ignore[assignment]
    busy_outcome = busy.run_job(busy.select())
    assert busy_outcome.state == "escalated"
    busy_body = (busy_directory / "tasks" / "T-JOB-1.md").read_text(encoding="utf-8")
    assert "marker=.jobloop/orchestrator-busy present=True" in busy_body


def _repository_root_for_scan(checkout: Path) -> Path:
    """Resolve the repository root whose absolute path must never appear in records.

    In the main checkout (and on CI) that is `checkout` itself. Inside a job
    workspace (`<parent>/.jobloop-<name>/workspaces/<job>`), `origin` points at
    the main checkout, which is the root workers must never be taught.
    """
    if checkout.parent.name == "workspaces" and checkout.parents[1].name.startswith(".jobloop-"):
        origin = git(checkout, "remote", "get-url", "origin", check=False).strip()
        if origin and Path(origin).is_dir():
            return Path(origin).resolve()
    return checkout.resolve()


def _tracked_offenders_for_root(
    checkout: Path,
    root: Path,
    *,
    excluded_test_fixtures: dict[str, str],
) -> list[str]:
    """Tracked non-protected files whose text contains `root` in any slash form."""
    forms = {
        str(root),
        str(root).replace("\\", "/"),
        str(root).replace("/", "\\"),
    }
    listed = git(checkout, "ls-files", "-z")
    tracked = [entry for entry in listed.split("\0") if entry]
    offenders: list[str] = []
    for rel in tracked:
        normalized = rel.replace("\\", "/")
        if normalized.startswith(gates.PROTECTED):
            continue
        if normalized in excluded_test_fixtures:
            continue
        text = (checkout / rel).read_bytes().decode("utf-8", "replace")
        if any(form in text for form in forms):
            offenders.append(normalized)
    return offenders


def test_tracked_files_do_not_record_absolute_repository_root(tmp_path: Path) -> None:
    # Self-prove the guard in both directions first: a tracked non-protected
    # file containing the runtime-computed root fails, while a protected file
    # and the two named fixture paths do not.
    probe = tmp_path / "repo"
    probe.mkdir()
    git(probe, "init", "-b", "main")
    git(probe, "config", "user.email", "t@example.invalid")
    git(probe, "config", "user.name", "t")
    probe_root = probe.resolve()
    (probe / "docs").mkdir()
    (probe / "docs" / "plans").mkdir()
    (probe / "progress" / "phase-x").mkdir(parents=True)
    (probe / "tests").mkdir()
    (probe / "docs" / "plans" / "PLAN.md").write_text(f"protected {probe_root}\n", encoding="utf-8")
    (probe / "tests" / "test_selfrepair.py").write_text(
        f"REPO = {probe_root!r}\n", encoding="utf-8"
    )
    (probe / "progress" / "phase-x" / "OWNER_DECISIONS.md").write_text(
        f"marker={probe_root}/.jobloop/orchestrator-busy present=False\n",
        encoding="utf-8",
    )
    git(probe, "add", "-A")
    git(probe, "commit", "-m", "seed")

    # Excluded one path at a time with reasons (no directory/prefix wildcards):
    excluded_test_fixtures = {
        # Models real dev-server command lines to prove port-release safety.
        "tests/test_release_test_ports.py": "command-line fixture for is_ours()",
        # Holds the synthetic `REPO` constant used to unit-test path redaction.
        "tests/test_selfrepair.py": "REPO constant fixture for selfrepair unit tests",
    }
    assert _tracked_offenders_for_root(
        probe, probe_root, excluded_test_fixtures=excluded_test_fixtures
    ) == ["progress/phase-x/OWNER_DECISIONS.md"]

    # Scan the repository. If running inside an un-rebased job workspace whose
    # `progress/` snapshot predates the latest rulings on the main checkout,
    # cross-check those `progress/` files directly against the main checkout.
    checkout = Path(__file__).resolve().parents[1]
    root = _repository_root_for_scan(checkout)
    offenders = _tracked_offenders_for_root(
        checkout, root, excluded_test_fixtures=excluded_test_fixtures
    )
    if offenders and checkout != root and all(p.startswith("progress/") for p in offenders):
        live = _tracked_offenders_for_root(
            root, root, excluded_test_fixtures=excluded_test_fixtures
        )
        offenders = [p for p in offenders if not p.startswith("progress/")] + [
            p for p in live if p.startswith("progress/")
        ]
    assert offenders == [], (
        "tracked files contain the repository root absolute path:\n" + "\n".join(offenders)
    )


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


def test_containment_judgement_still_stops_and_clean_runs_still_pass(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- done", model
    )

    clean_calls = {"n": 0}

    def clean_dirt(_path: Path) -> str:
        clean_calls["n"] += 1
        return "same\n"

    controller.dirt = clean_dirt  # type: ignore[assignment]
    clean_outcome = controller.run_job(controller.select())
    assert "outside its workspace" not in clean_outcome.detail

    dirty_base = tmp_path / "dirty"
    phase_with_task(dirty_base)
    dirty_controller = controller_for(dirty_base, ["a-free", "b-free"])
    dirty_controller.workspace = lambda task: dirty_base  # type: ignore[assignment]
    dirty_controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- done", model
    )
    dirty_seen = {"n": 0}

    def dirty_dirt(_path: Path) -> str:
        dirty_seen["n"] += 1
        return "before\n" if dirty_seen["n"] == 1 else "before\n M escaped.py x\n"

    dirty_controller.dirt = dirty_dirt  # type: ignore[assignment]
    dirty_outcome = dirty_controller.run_job(dirty_controller.select())
    assert dirty_outcome.state == "escalated"
    assert "outside its workspace" in dirty_outcome.detail


def test_containment_rest_is_readable_in_log_and_diagnose(tmp_path: Path) -> None:
    from jobloop import diagnose

    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- done", model
    )
    for _ in range(5):
        controller.roster.mark_dispatched("a-free")
    for _ in range(2):
        controller.roster.mark_containment_stop("a-free", orchestrator_busy=False)

    seen = {"n": 0}

    def dirty_dirt(_path: Path) -> str:
        seen["n"] += 1
        return "before\n" if seen["n"] == 1 else "before\n M leaked.py abc123\n"

    controller.dirt = dirty_dirt  # type: ignore[assignment]
    outcome = controller.run_job(controller.select())
    assert outcome.state == "escalated"
    assert "outside its workspace" in outcome.detail

    log = (controller.settings.state_directory / "supervisor.log").read_text(encoding="utf-8")
    assert "containment a-free: 3/6 stops/dispatches" in log
    assert "rested" in log

    report = diagnose.report([])
    assert "containment a-free: 3/6 stops/dispatches" in report
    assert "rested" in report


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

    # The brief's own wording, not the angle-bracket placeholder. `T-PH6-127`
    # escalated on 2026-11-22 with "` followed by the real question you need
    # answered." while its report ended `ready-for-review` and the work was done.
    assert controller_module.placeholder("` followed by the real question you need answered.")
    assert controller_module.placeholder("needs-owner-decision: written out in full")
    # And a real question still gets through, however it is phrased.
    assert not controller_module.placeholder(
        "May I widen allowed_paths to include frontend/e2e/a11y.spec.ts?"
    )
    assert not controller_module.placeholder(
        "既存テストが 2 件落ちますが、表明を直すべきか製品を直すべきか判断してください。"
    )


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
    # The guarantees here are unchanged: no review happens, nothing is approved,
    # nothing is committed, and the prohibition on self-review is cited. What
    # changed on 2026-11-22 is where the job waits. Escalating set `blocked`,
    # which needs a person — for a condition that resolves by itself when a
    # cooldown expires. Four jobs sat in it while `available models: none`.
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["only-free"])
    task = controller.select()
    assert task is not None
    # The implementer used the only model, so there is nobody left to review it.
    outcome = controller.review(task, tmp_path, "only-free", [])
    assert outcome.state == "no-reviewer" and "cooldown" in outcome.detail
    waiting = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    assert waiting.status == "review", "it waits where the next cycle will find it"
    assert waiting.status != "done", "and it is certainly not approved"
    assert not (controller.settings.phase_directory / "OWNER_DECISIONS.md").exists(), (
        "a wait is not a question for the owner"
    )
    body = task.path.read_text(encoding="utf-8")
    assert "WAITING FOR A REVIEWER" in body, "the wait has to be visible in the record"
    assert "5-5" in body, "the prohibition on self-review must still be cited"


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


def test_dirty_branch_report_separates_foreign_and_names_owner(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    # Another ticket owns the stray product file.
    other = tmp_path / "progress" / "phase-7-production" / "tasks"
    other.mkdir(parents=True)
    (other / "T-PH7-211.md").write_text(
        "---\n"
        "id: T-PH7-211\n"
        "phase: phase-7-production\n"
        "status: doing\n"
        "attempts: 1\n"
        "allowed_paths: backend/app/storage.py, tests/test_storage_seam.py\n"
        "test_cmd: python -m pytest -q\n"
        "---\n\n# body\n",
        encoding="utf-8",
    )
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    status_text = (
        " M docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html\n"
        " M progress/phase-7-production/OWNER_DECISIONS.md\n"
        " M progress/phase-7-production/tasks/T-PH7-202.md\n"
        " M progress/phase-7-production/tasks/T-PH7-211.md\n"
        " M progress/phase-ai-connect/tasks/T-AIC-005.md\n"
        " M progress/phase-7-production/PROGRESS.md\n"
        "?? tests/test_storage_seam.py"
    )

    def fake_git(repository: Path, *arguments: str, check: bool = True) -> str:
        if arguments[0] == "status":
            return status_text
        return ""

    import jobloop.controller as module

    original = module.git
    module.git = fake_git  # type: ignore[assignment]
    try:
        task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
        body = controller.commit_progress_records(task)
    finally:
        module.git = original

    assert "foreign" in body.lower()
    foreign_heading = "foreign (判定に使った未コミットのパス):"
    other_heading = "not used for decision (判定に使っていない: progress/ と平易化ページ):"
    assert foreign_heading in body
    assert other_heading in body
    foreign_section = body.split(foreign_heading, 1)[1].split(other_heading, 1)[0]
    foreign_lines = [line for line in foreign_section.splitlines() if line.strip()]
    assert foreign_lines == ["?? tests/test_storage_seam.py  → T-PH7-211 の許可パス"]
    # The bookkeeping lines are still reported, but not as the reason for the stop.
    other_section = body.split(other_heading, 1)[1]
    assert "docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html" in other_section
    assert other_section.count("progress/") == 5


def test_dirty_branch_still_stops_on_foreign_and_commits_bookkeeping_only(tmp_path: Path) -> None:
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
        # Bookkeeping + guide only: still committed, never a stop.
        status_text = (
            " M progress/phase-test/tasks/T-JOB-1.md\n"
            " M progress/phase-7-production/OWNER_DECISIONS.md\n"
            " M docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html"
        )
        assert controller.commit_progress_records(task) == ""
        assert any("commit" in arguments for arguments in added)
        # Any foreign path still stops the merge.
        added.clear()
        status_text = " M progress/phase-test/tasks/T-JOB-1.md\n?? tests/test_storage_seam.py"
        body = controller.commit_progress_records(task)
        assert "foreign" in body.lower()
        assert "tests/test_storage_seam.py" in body
        assert not any("commit" in arguments for arguments in added)
    finally:
        module.git = original


def test_dirty_branch_names_unknown_foreign_path(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    status_text = "?? backend/app/mystery.py"

    def fake_git(repository: Path, *arguments: str, check: bool = True) -> str:
        if arguments[0] == "status":
            return status_text
        return ""

    import jobloop.controller as module

    original = module.git
    module.git = fake_git  # type: ignore[assignment]
    try:
        task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
        body = controller.commit_progress_records(task)
    finally:
        module.git = original

    assert "?? backend/app/mystery.py  → どの票の許可パスにも無い" in body


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
    # The swept paths must also leave the list the scope gate reads. Sweeping
    # from inside the comprehension's condition ran it once per path: the first
    # call deleted and returned the scratch, the rest returned nothing, and the
    # filter kept exactly what had been removed. `T-PH6-125` was stopped on
    # 2026-11-22 for eight paths its own record shows as already deleted.
    body = (tmp_path / "progress" / "phase-test" / "tasks" / "T-JOB-1.md").read_text(
        encoding="utf-8"
    )
    scope_stop = (
        body[body.find("outside allowed_paths") :] if "outside allowed_paths" in body else ""
    )
    assert "check_select3.py" not in scope_stop and "pytest_out.txt" not in scope_stop, (
        "a swept path must not be named in a scope stop"
    )
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


def test_a_reviewer_that_cannot_be_run_is_passed_over_not_retried_for_ever(
    tmp_path: Path,
) -> None:
    # Measured 2026-11-22: `ollama/gemma3:4b` ranks first and answered
    # `unavailable`, so the roster handed it out again on every cycle for an
    # hour while two working `opencode` models sat untried. `T-PH6-104` and
    # `T-PH8-302` churned, nothing escalated, and `diagnose` saw a healthy queue.
    phase_with_task(tmp_path)
    tree = reviewable_worktree(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "broken-free", "c-free"])
    asked: list[str] = []

    def dispatch(model: str, prompt: str, **_: object) -> worker.Result:
        asked.append(model)
        if model == "broken-free":
            return worker.Result(worker.Ending.UNAVAILABLE, "", model, ["cannot route"])
        return worker.Result(worker.Ending.COMPLETED, "VERDICT\n- CHANGES_REQUIRED", model)

    controller.dispatch = dispatch  # type: ignore[assignment]
    task = controller.select()
    assert task is not None
    outcome = controller.review(task, tree, "a-free", [])

    assert asked == ["broken-free", "c-free"], "the next model is reached in the same pass"
    assert outcome.state == "changes-required", "and that review is the one that counts"
    assert "broken-free" not in controller.roster.available(), "put on cooldown, not re-picked"

    # And when every model is only unreachable, the job waits — it is not
    # accused of something it did not do. Folding "could not be run" into the
    # same list as "wrote to the worktree" made the escalation say
    # `ollama/gemma3:4b` had written to the worktree when it had only ever
    # answered `unavailable` (seen 2026-11-22 08:32 on `T-PH6-104`).
    phase_with_task(tmp_path / "all-broken")
    alone = controller_for(tmp_path / "all-broken", ["a-free", "b-free"])
    alone.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.UNAVAILABLE, "", model, ["cannot route"]
    )
    waiting = alone.select()
    assert waiting is not None
    second = tmp_path / "ws2"
    second.mkdir(parents=True, exist_ok=True)
    result = alone.review(waiting, reviewable_worktree(second), "a-free", [])
    assert result.state == "no-reviewer", result.detail
    assert not (alone.settings.phase_directory / "OWNER_DECISIONS.md").exists()
    body = waiting.path.read_text(encoding="utf-8")
    assert "WAITING FOR A REVIEWER" in body
    assert "wrote to the worktree" not in body, "no model is blamed for that here"


def test_an_implementer_that_cannot_be_run_keeps_its_attempt(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.UNAVAILABLE, "", model, ["the CLI crashed"]
    )
    outcome = controller.run_job(controller.select())
    assert outcome.state == "rotated" and "could not be run" in outcome.detail
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    assert task.attempts == 0, "a model that never ran the job has not failed it"
    assert not (controller.settings.phase_directory / "OWNER_DECISIONS.md").exists()


def test_a_model_that_keeps_failing_to_start_waits_longer_each_time(tmp_path: Path) -> None:
    """One outage is a wait; the seventeenth is a broken provider.

    `controller.UNAVAILABLE_COOLDOWN` is right for a single outage — a CLI that
    briefly lost its route is back in minutes, and six hours would throw away a
    working model. It is wrong for a repetition: a provider that fails for a new
    reason every time is never matched by `cooldown_for`'s known strings, so on
    2026-11-22 the roster picked it up again every fifteen minutes and
    `ollama/gemma3:4b` reached 17 observations, the highest in the roster.
    Counting matches no strings, so the next unknown reason is covered too.
    """
    base = controller_module.UNAVAILABLE_COOLDOWN
    state = tmp_path / "roster.json"
    waits = [
        Roster(models=["a-free"], state_file=state, now=1000.0 + attempt).mark_unavailable(
            "a-free", base_seconds=base
        )
        for attempt in range(8)
    ]
    assert waits[0] == base, "a first failure keeps the short rest"
    assert waits[1] > waits[0] and waits[2] > waits[1], "a repetition has to stretch the wait"
    assert waits[2] >= 4 * base, "a few failures in a row must be clearly longer, not a nudge"
    assert waits[-1] == roster_module.COOLDOWN_SECONDS, "it stops at the exhaustion period"
    assert all(wait <= roster_module.COOLDOWN_SECONDS for wait in waits), (
        "a dead provider is rested, never removed: six hours is four tries a day"
    )
    # It really does come back, rather than resting for ever.
    assert (
        Roster(models=["a-free"], state_file=state, now=1000.0 + 7 + waits[-1]).pick() == "a-free"
    )
    # `observations` keeps counting both kinds of rest, as every existing record
    # in `.jobloop/roster.json` already does.
    exhausted = Roster(models=["a-free"], state_file=state, now=1000.0)
    exhausted.mark_exhausted("a-free")
    recorded = (tmp_path / "roster.json").read_text(encoding="utf-8")
    assert '"observations": 9.0' in recorded, recorded


def test_answering_a_job_forgets_the_failure_streak(tmp_path: Path) -> None:
    """The wait has to come back down, or it only ever grows.

    A model that was unavailable twice and then answered is not broken. This is
    the half of the design that cannot be left out: without a reset the streak
    would describe the model's whole history, and a model that had one bad
    afternoon would spend the rest of the phase resting six hours at a time.
    """
    base = controller_module.UNAVAILABLE_COOLDOWN
    state = tmp_path / "roster.json"
    early = Roster(models=["a-free"], state_file=state, now=1000.0)
    early.mark_unavailable("a-free", base_seconds=base)
    long_wait = early.mark_unavailable("a-free", base_seconds=base)
    assert long_wait > base

    early.mark_responded("a-free")
    after = Roster(models=["a-free"], state_file=state, now=1000.0 + long_wait)
    assert after.mark_unavailable("a-free", base_seconds=base) == base, (
        "a model that answered must start from the short wait again"
    )


def test_the_controller_forgets_the_streak_when_the_model_answers(tmp_path: Path) -> None:
    """The reset has to be on the dispatch paths, not only in the roster.

    `mark_responded` is only worth having if the controller calls it where a
    reply actually arrives, for the implementer and for the reviewer.
    """
    phase_with_task(tmp_path)
    base = controller_module.UNAVAILABLE_COOLDOWN
    state = tmp_path / ".jobloop" / "roster.json"
    early = Roster(models=["a-free", "b-free"], state_file=state, now=1000.0)
    early.mark_unavailable("a-free", base_seconds=base)
    long_wait = early.mark_unavailable("a-free", base_seconds=base)
    early.mark_unavailable("b-free", base_seconds=base)
    early.mark_unavailable("b-free", base_seconds=base)

    later = Roster(models=["a-free", "b-free"], state_file=state, now=1000.0 + long_wait)
    controller = Controller(settings_for(tmp_path), later, clock=lambda: 0.0)
    dispatched: list[str] = []

    def implement(model: str, prompt: str, **_: object) -> worker.Result:
        dispatched.append(model)
        return worker.Result(worker.Ending.COMPLETED, "REPORT\nnothing changed", model)

    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = implement  # type: ignore[assignment]
    outcome = controller.run_job(controller.select())
    assert dispatched == ["a-free"], "the model with the streak is the one that answers"
    assert outcome.state == "attempt-failed", outcome.detail
    assert controller.roster.mark_unavailable("a-free", base_seconds=base) == base, (
        "the implementer answered, so its streak is over"
    )

    phase_with_task(tmp_path / "review")
    tree = reviewable_worktree(tmp_path / "review")
    reviewer_roster = Roster(
        models=["a-free", "b-free"],
        state_file=tmp_path / "review" / ".jobloop" / "roster.json",
        now=1000.0,
    )
    reviewer_roster.mark_unavailable("b-free", base_seconds=base)
    reviewer_wait = reviewer_roster.mark_unavailable("b-free", base_seconds=base)
    reviewer_later = Roster(
        models=["a-free", "b-free"],
        state_file=tmp_path / "review" / ".jobloop" / "roster.json",
        now=1000.0 + reviewer_wait,
    )
    alone = Controller(settings_for(tmp_path / "review"), reviewer_later, clock=lambda: 0.0)
    reviewed: list[str] = []

    def verdict_for(model: str, prompt: str, **_: object) -> worker.Result:
        reviewed.append(model)
        return worker.Result(worker.Ending.COMPLETED, "VERDICT\n- CHANGES_REQUIRED", model)

    alone.dispatch = verdict_for  # type: ignore[assignment]
    asked = alone.select()
    assert asked is not None
    alone.review(asked, tree, "a-free", [])
    assert reviewed == ["b-free"], "the reviewer with the streak is the one that answers"
    assert alone.roster.mark_unavailable("b-free", base_seconds=base) == base, (
        "the reviewer answered, so its streak is over too"
    )


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


def test_the_escalation_names_the_budget_that_actually_ran_out(tmp_path: Path) -> None:
    """Two opposite situations used to be recorded with the same sentence.

    `review cycles` spent means the implementer and the reviewer are pushing at
    each other over the same artifact; `attempts` spent means the work itself
    kept failing. On 2026-11-22 `T-PH7-205` escalated as "review cycle limit
    reached" with `review_cycles: 1` — it was the attempt budget — and the shift
    opened the review looking for an approval the pattern had missed, which was
    the wrong evidence to read first.
    """
    spent = TASK.replace("attempts: 0", "attempts: 2").replace(
        "status: todo", "status: todo\nreview_cycles: 0"
    )
    phase_with_task(tmp_path, spent)
    tree = reviewable_worktree(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])

    def dispatch(model: str, prompt: str, **_: object) -> worker.Result:
        return worker.Result(
            worker.Ending.COMPLETED,
            "VERDICT\n- CHANGES_REQUIRED\n\nFINDINGS\n- High, do it again",
            model,
        )

    controller.dispatch = dispatch  # type: ignore[assignment]
    task = controller.select()
    assert task is not None
    outcome, _ = controller.review_once(task, tree, "a-free", [])

    # One review cycle only, but the third attempt is gone: say so.
    assert outcome.state == "escalated"
    assert "attempt limit reached after a review" in outcome.detail
    assert "review cycle limit reached" not in outcome.detail
    record = (
        (controller.settings.phase_directory / "tasks" / "T-JOB-1.md").read_bytes().decode("utf-8")
    )
    assert "attempts 3/3" in record and "review cycles 1/2" in record


def test_the_brief_asks_for_the_same_scan_the_gate_runs(tmp_path: Path) -> None:
    """The brief promised a command the controller does not run.

    `test_the_secret_scan_gate_asks_about_this_change_only` pins the gate to the
    job's own changed paths, but the brief still printed the bare full-tree
    form. On 2026-11-22 `T-STC-001` finished all of its work, ran the brief's
    version, found two potential secrets in another phase's records — written
    there by the orchestrator that morning — and stopped to ask, because it
    could not touch files outside its scope to clear them. It was right to ask;
    it should never have been told to look.
    """
    task = tasks.load_phase(phase_with_task(tmp_path)).tasks[0]
    brief = prompts.implementer_brief(task, attempt=1, repository="/workspaces/T-JOB-1")

    assert "python scripts/secret_scan.py <only the files you changed>" in brief
    assert "\n  python scripts/secret_scan.py\n" not in brief, "the full-tree form is a trap"
    assert "is not yours and must not stop you" in brief


def test_a_dispatch_is_visible_in_the_console_not_only_in_the_log(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The console the owner watches has to show that work is happening.

    `supervise_loop.py` prints at cycle boundaries, and a cycle's budget is
    forty-five minutes. On 2026-11-22 the window showed nothing for ten minutes
    while `T-PH6-127` ran normally, and the owner had to ask whether the loop had
    stopped. Per-job lines went to `.jobloop/supervisor.log` only.
    """
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free"])
    controller.note("T-JOB-1: dispatching (light)")

    beat = controller.settings.state_directory / "supervisor.log"
    written = beat.read_text(encoding="utf-8")
    shown = capsys.readouterr().out

    assert "run :: T-JOB-1: dispatching (light)" in written
    assert "run :: T-JOB-1: dispatching (light)" in shown, "the console is the live view"
    # One line, same text in both, so "when did anything last happen" keeps one answer.
    assert shown.strip() == written.strip()


def test_containment_is_judged_on_paths_and_never_on_diff_content(tmp_path: Path) -> None:
    """The evidence has to name a file, and only a path can be classified.

    `dirt` used to include `git diff HEAD`, so the comparison ran over diff body
    lines. On 2026-11-22 at 18:49 `T-PH6-127` was accused with evidence that was
    fragments of the orchestrator's own edit to `Controller.note` — no filename
    anywhere in it, and nothing `bookkeeping` could exclude, because it reads a
    line as a status code plus a path.
    """
    repository = tmp_path / "main"
    repository.mkdir()
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "t@example.invalid")
    git(repository, "config", "user.name", "t")
    (repository / "module.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (repository / "progress").mkdir()
    (repository / "progress" / "PROGRESS.md").write_text("# plan\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "first")

    def appeared(before: str, now: str) -> list[str]:
        return sorted(set(now.splitlines()) - set(before.splitlines()))

    clean = Controller.dirt(repository)
    assert clean.strip() == ""

    def paths(lines: list[str]) -> list[str]:
        return [Controller.changed_path(line) for line in lines]

    # An edit to a tracked file: one entry, and it names the file.
    (repository / "module.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    lines = appeared(clean, Controller.dirt(repository))
    assert paths(lines) == ["module.py"], lines
    assert not any("return 2" in line for line in lines), "content must not reach the evidence"

    # The same edit under `progress/` is the owner writing records, not an escape.
    (repository / "progress" / "PROGRESS.md").write_text("# plan\n\n- more\n", encoding="utf-8")
    records = appeared(clean, Controller.dirt(repository))
    assert "progress/PROGRESS.md" in paths(records)
    kept = paths([line for line in records if not Controller.bookkeeping(line)])
    assert kept == ["module.py"], kept

    # A deletion in the main checkout is an escape too, and porcelain reports it.
    git(repository, "checkout", "--", ".")
    (repository / "module.py").unlink()
    assert paths(appeared(clean, Controller.dirt(repository))) == ["module.py"]

    # The detection that porcelain alone would lose: a file that is *already*
    # dirty and edited again keeps the same status line, so without the digest a
    # reviewer editing it — or a worker hiding behind the orchestrator's own
    # uncommitted mess — is invisible.
    git(repository, "checkout", "--", ".")
    (repository / "module.py").write_text("def f():\n    return 3\n", encoding="utf-8")
    already = Controller.dirt(repository)
    (repository / "module.py").write_text("def f():\n    return 4\n", encoding="utf-8")
    again = appeared(already, Controller.dirt(repository))
    assert paths(again) == ["module.py"], again

    # A path with a space keeps its whole name when the digest column is dropped.
    assert Controller.changed_path("?? progress/my notes.md abcdef0123456789") == (
        "progress/my notes.md"
    )
    assert Controller.changed_path("?? progress/my notes.md") == "progress/my notes.md"


def test_a_resume_sees_work_that_is_already_committed(tmp_path: Path) -> None:
    """A clean tree is not an empty workspace.

    `T-PH6-104` sat at `nothing-to-resume - the workspace has no changes` on
    every cycle from 19:11 on 2026-11-22, with a reviewed commit intact in its
    clone: an earlier merge had failed, so the work was committed rather than
    dirty, and `changed_files` only reports what is uncommitted. The same shape
    wasted `T-PH6-123`'s attempts and `T-PH6-116`'s whole budget.
    """
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    repository = controller.settings.repository
    git(repository, "init", "-b", controller.settings.integration_branch)
    git(repository, "config", "user.email", "t@example.invalid")
    git(repository, "config", "user.name", "t")
    (repository / "seed.txt").write_text("seed\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "base")

    tree = controller.settings.workspace_root / "T-JOB-1"
    tree.parent.mkdir(parents=True, exist_ok=True)
    git(tree.parent, "clone", "--quiet", str(repository), tree.name)
    git(tree, "config", "user.email", "w@example.invalid")
    git(tree, "config", "user.name", "w")

    # Nothing at all: still nothing to resume, and it says so about both.
    assert controller.committed_but_unmerged(tree) == []

    # The worker's work, committed rather than left dirty.
    (tree / "backend").mkdir()
    (tree / "backend" / "app").mkdir()
    (tree / "backend" / "app" / "service.py").write_text("x = 1\n", encoding="utf-8")
    git(tree, "add", "-A")
    git(tree, "commit", "-m", "the reviewed work")

    assert gates.changed_files(tree) == [], "git status sees nothing, which was the trap"
    assert controller.committed_but_unmerged(tree) == ["backend/app/service.py"]

    # Measured from the merge base, not between the two tips. A tree comparison
    # also reports every file the branch gained since the clone was made: the
    # first version of this used `FETCH_HEAD..HEAD` and the scope gate failed
    # `T-PH6-104` at 19:30 on 2026-11-22 for `.claude/skills/README.md` and
    # `backend/app/connectors/`, which its worker had never seen.
    (repository / "unrelated.py").write_text("y = 2\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "someone else's merged work")
    assert controller.committed_but_unmerged(tree) == ["backend/app/service.py"], (
        "another job's merged files are not this job's change"
    )


def test_a_model_that_cannot_do_the_work_rests_as_long_as_a_spent_one() -> None:
    """`unavailable` covers an outage and an incapability, and they differ.

    `ollama/gemma3:4b` answered `registry.ollama.ai/library/gemma3:4b does not
    support tools` — the same answer every time, since `opencode run` needs
    tools. The short cooldown meant it was picked, failed and rested every
    fifteen minutes: ninety-six attempts a day that could never succeed, and the
    highest observation count in the roster by 2026-11-22 evening.
    """
    assert (
        controller_module.cooldown_for(
            [
                "provider.invalid-request",
                "registry.ollama.ai/library/gemma3:4b does not support tools",
            ]
        )
        == roster_module.COOLDOWN_SECONDS
    )

    # A real outage keeps the short rest: a CLI that briefly lost its route to a
    # provider may come back in minutes, and resting it six hours would throw
    # away a working model.
    for transient in (
        ["opencode executable not found"],
        ["connection reset by peer"],
        ["provider.invalid-request: malformed request body"],
        [],
    ):
        assert (
            controller_module.cooldown_for(transient) == controller_module.UNAVAILABLE_COOLDOWN
        ), transient


def test_a_cycle_commits_its_own_records_even_when_nothing_was_delivered(
    tmp_path: Path,
) -> None:
    """`deliver` was the only caller, so every other outcome left the tree dirty.

    The loop writes a job's status and evidence into the main checkout as it
    goes. A cycle that only rotated, escalated or found no model committed none
    of it, and the next job that *did* reach delivery escalated with "integration
    branch is dirty" over records the loop had written itself — `T-PH6-104` at
    18:54 on 2026-11-22. The end-of-run push then pushed nothing, because
    nothing had been committed.
    """
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, [])
    repository = controller.settings.repository
    git(repository, "init", "-b", controller.settings.integration_branch)
    git(repository, "config", "user.email", "t@example.invalid")
    git(repository, "config", "user.name", "t")
    # The real repository ignores the loop's own state directory
    # (`.gitignore:57`). Without it the roster file reads as a foreign path and
    # nothing is ever committed — which is how this test first failed.
    (repository / ".gitignore").write_text(".jobloop/\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "the phase and its task")
    assert not Controller.dirt(repository).strip()

    # What a rotation leaves behind: an edited record, no delivery.
    record = controller.settings.phase_directory / "tasks" / "T-JOB-1.md"
    record.write_text(record.read_text(encoding="utf-8") + "\n## ROTATED\n", encoding="utf-8")
    assert Controller.dirt(repository).strip(), "the record really is uncommitted"

    # No models, so the cycle ends without delivering anything.
    controller.run(minutes=0.2, max_jobs=1)
    assert not Controller.dirt(repository).strip(), "the cycle must not leave its own dirt"
    assert "record this cycle" in git(repository, "log", "-1", "--format=%s")

    # A person's uncommitted file still stops the merge rather than being swept.
    (repository / "mine.txt").write_text("the orchestrator is mid-edit\n", encoding="utf-8")
    record.write_text(record.read_text(encoding="utf-8") + "\n## AGAIN\n", encoding="utf-8")
    controller.run(minutes=0.2, max_jobs=1)
    left = Controller.dirt(repository)
    assert "mine.txt" in left, "never stage a path outside progress/"
    assert "T-JOB-1.md" in left, "and do not commit the records around it either"


# --- supervisor idle cooldown cap (T-PH9-408) --------------------------------


def load_supervise_loop():
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "supervise_loop", root / "scripts" / "supervise_loop.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_idle_wait_wakes_for_the_earliest_provided_cooldown(tmp_path: Path) -> None:
    """AC1: when backoff would sleep through a cooldown expiry, wake for it."""
    module = load_supervise_loop()
    now = 1_000_000.0
    state_file = tmp_path / "roster.json"
    state_file.write_text(
        json.dumps({"opencode/a-free": {"cooldown_until": now + 180}}),
        encoding="utf-8",
    )
    waiting = module.idle_wait(
        120.0, 10, state_file=state_file, models=["opencode/a-free"], now=now
    )
    assert module.backoff(120.0, 10) == 1200.0
    assert waiting == 180.0 + module.IDLE_COOLDOWN_MARGIN


def test_idle_wait_keeps_backoff_when_no_near_cooldown(tmp_path: Path) -> None:
    """AC2: do not poll faster when no provided cooldown is near."""
    module = load_supervise_loop()
    now = 1_000_000.0
    pause, idle_rounds = 120.0, 10
    expected = module.backoff(pause, idle_rounds)
    assert expected == 1200.0

    far = tmp_path / "far.json"
    far.write_text(
        json.dumps({"opencode/a-free": {"cooldown_until": now + 3600}}),
        encoding="utf-8",
    )
    assert (
        module.idle_wait(pause, idle_rounds, state_file=far, models=["opencode/a-free"], now=now)
        == expected
    )

    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    assert (
        module.idle_wait(pause, idle_rounds, state_file=empty, models=["opencode/a-free"], now=now)
        == expected
    )

    none_provided = tmp_path / "none.json"
    none_provided.write_text(
        json.dumps({"opencode/a-free": {"cooldown_until": now + 180}}),
        encoding="utf-8",
    )
    assert (
        module.idle_wait(pause, idle_rounds, state_file=none_provided, models=[], now=now)
        == expected
    )

    stale = tmp_path / "stale.json"
    stale.write_text(
        json.dumps({"opencode/old-free": {"cooldown_until": now + 180}}),
        encoding="utf-8",
    )
    assert (
        module.idle_wait(
            pause,
            idle_rounds,
            state_file=stale,
            models=["opencode/new-free"],
            now=now,
        )
        == expected
    )


def test_idle_wait_ignores_corrupted_cooldown_entries(tmp_path: Path) -> None:
    """Corrupted roster entries must not crash the supervisor; fall back to backoff."""
    module = load_supervise_loop()
    now = 1_000_000.0
    pause, idle_rounds = 120.0, 10
    expected = module.backoff(pause, idle_rounds)

    bad_number = tmp_path / "bad-number.json"
    bad_number.write_text(
        json.dumps({"opencode/a-free": {"cooldown_until": "not-a-number"}}),
        encoding="utf-8",
    )
    assert (
        module.idle_wait(
            pause, idle_rounds, state_file=bad_number, models=["opencode/a-free"], now=now
        )
        == expected
    )

    bad_entry = tmp_path / "bad-entry.json"
    bad_entry.write_text(json.dumps({"opencode/a-free": 42}), encoding="utf-8")
    assert (
        module.idle_wait(
            pause, idle_rounds, state_file=bad_entry, models=["opencode/a-free"], now=now
        )
        == expected
    )


def test_idle_wait_skips_nonfinite_cooldown_and_uses_nearest_finite(tmp_path: Path) -> None:
    """AC1/AC3: NaN or Infinity cooldown must not hide a real finite cooldown."""
    module = load_supervise_loop()
    now = 1_000_000.0
    pause, idle_rounds = 120.0, 10
    expected_backoff = module.backoff(pause, idle_rounds)

    broken_first = tmp_path / "nan-then-finite.json"
    broken_first.write_text(
        json.dumps(
            {
                "opencode/a-free": {"cooldown_until": float("nan")},
                "opencode/b-free": {"cooldown_until": now + 180},
            }
        ),
        encoding="utf-8",
    )
    waiting = module.idle_wait(
        pause,
        idle_rounds,
        state_file=broken_first,
        models=["opencode/a-free", "opencode/b-free"],
        now=now,
    )
    assert waiting == 180.0 + module.IDLE_COOLDOWN_MARGIN

    infinities = tmp_path / "inf-then-finite.json"
    infinities.write_text(
        json.dumps(
            {
                "opencode/a-free": {"cooldown_until": float("inf")},
                "opencode/b-free": {"cooldown_until": float("-inf")},
                "opencode/c-free": {"cooldown_until": now + 180},
            }
        ),
        encoding="utf-8",
    )
    assert (
        module.idle_wait(
            pause,
            idle_rounds,
            state_file=infinities,
            models=["opencode/a-free", "opencode/b-free", "opencode/c-free"],
            now=now,
        )
        == 180.0 + module.IDLE_COOLDOWN_MARGIN
    )

    # AC3 (both directions on normal rosters): near cooldown caps wait, far cooldown keeps backoff.
    normal_near = tmp_path / "normal-near.json"
    normal_near.write_text(
        json.dumps({"opencode/a-free": {"cooldown_until": now + 180}}),
        encoding="utf-8",
    )
    assert (
        module.idle_wait(
            pause, idle_rounds, state_file=normal_near, models=["opencode/a-free"], now=now
        )
        == 180.0 + module.IDLE_COOLDOWN_MARGIN
    )
    normal_far = tmp_path / "normal-far.json"
    normal_far.write_text(
        json.dumps({"opencode/a-free": {"cooldown_until": now + 3600}}),
        encoding="utf-8",
    )
    assert (
        module.idle_wait(
            pause, idle_rounds, state_file=normal_far, models=["opencode/a-free"], now=now
        )
        == expected_backoff
    )


def test_unreadable_roster_does_not_crash_and_records_fact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2/AC4: undecodable roster is treated as empty and recorded in stderr and heartbeat."""
    module = load_supervise_loop()
    now = 1_000_000.0
    pause, idle_rounds = 120.0, 10
    expected = module.backoff(pause, idle_rounds)

    roster_file = tmp_path / "roster.json"
    roster_file.write_bytes(b"\xff\xfe\x00not-utf8")

    roster = Roster(models=["opencode/a-free"], state_file=roster_file, now=now)
    assert roster._state() == {}
    err = capsys.readouterr().err
    assert "roster unreadable" in err.lower()
    assert str(roster_file) in err or roster_file.name in err

    capsys.readouterr()
    assert (
        module.idle_wait(
            pause, idle_rounds, state_file=roster_file, models=["opencode/a-free"], now=now
        )
        == expected
    )
    err = capsys.readouterr().err
    assert "roster unreadable" in err.lower()

    # Also verify supervisor's idle cycle records the unreadable roster fact into heartbeat.
    monkeypatch.setattr(module, "ROOT", tmp_path)
    state_dir = tmp_path / ".jobloop"
    state_dir.mkdir()
    (state_dir / "roster.json").write_bytes(b"\xff\xfe\x00not-utf8")
    waits: list[float] = []
    monkeypatch.setattr(module.time, "sleep", lambda seconds: waits.append(seconds))
    monkeypatch.setattr(module, "stream", lambda argv: (0, "-: idle - no actionable job is left\n"))
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: type("R", (), {"stdout": "", "stderr": "", "returncode": 0})(),
    )
    import jobloop.cli as cli

    monkeypatch.setattr(cli, "installed_models", lambda executable=None: ["opencode/a-free"])
    monkeypatch.setattr(cli, "agy_installed_models", lambda executable=None: [])
    module.main(["--phase", "p", "--pause", "120", "--cycles", "1"])
    assert sum(waits) == pytest.approx(240.0)
    beat_text = (state_dir / "supervisor.log").read_text(encoding="utf-8")
    assert "roster unreadable" in beat_text.lower()


def test_roster_available_skips_non_dict_and_unparseable_entries(tmp_path: Path) -> None:
    """Roster.available() must skip non-dict entries and non-numeric cooldown_until values."""
    state_file = tmp_path / "roster.json"
    state_file.write_text(
        json.dumps(
            {
                "a-free": 42,
                "b-free": {"cooldown_until": "soon"},
                "c-free": {
                    "dispatches": "bad",
                    "containment_stops": "bad",
                    "cooldown_until": 500.0,
                },
                "d-free": {"cooldown_until": 500.0},
            }
        ),
        encoding="utf-8",
    )
    roster = Roster(
        models=["a-free", "b-free", "c-free", "d-free", "e-free"],
        state_file=state_file,
        now=1000.0,
    )
    available = roster.available()
    assert "a-free" not in available, "non-dict entry must be skipped"
    assert "b-free" not in available, "string cooldown_until must be skipped"
    assert "c-free" in available, "bad containment counters must not crash available()"
    assert "d-free" in available, "expired finite cooldown must remain available"
    assert "e-free" in available, "unrecorded model must remain available"


def test_roster_available_skips_nonfinite_cooldown_including_neg_inf(tmp_path: Path) -> None:
    """Roster.available() must skip NaN, +inf, and -inf cooldown_until entries.

    `-inf` is the observable check for `math.isfinite`: without `isfinite`,
    `-inf > now` is False (or `-inf <= now` is True), which would falsely treat
    `-inf` as expired and available.
    """
    state_file = tmp_path / "roster.json"
    state_file.write_text(
        json.dumps(
            {
                "nan-free": {"cooldown_until": float("nan")},
                "posinf-free": {"cooldown_until": float("inf")},
                "neginf-free": {"cooldown_until": float("-inf")},
                "ok-free": {"cooldown_until": 1500.0},
            }
        ),
        encoding="utf-8",
    )
    roster = Roster(
        models=["nan-free", "posinf-free", "neginf-free", "ok-free"],
        state_file=state_file,
        now=2000.0,
    )
    available = roster.available()
    assert available == ["ok-free"]


def test_roster_pick_and_mutations_with_broken_entries_do_not_crash(tmp_path: Path) -> None:
    """Roster.pick() (including agy second-tier roles) and writers survive broken entries."""
    state_file = tmp_path / "roster.json"
    state_file.write_text(
        json.dumps(
            {
                "opencode/a-free": 42,
                "opencode/b-free": {"cooldown_until": "soon"},
                "agy/gemini-4-carbon-low": {"cooldown_until": float("-inf")},
                "agy/gemini-4-argon-low": {"cooldown_until": 1500.0},
            }
        ),
        encoding="utf-8",
    )
    models = eligible(
        [
            "opencode/a-free",
            "opencode/b-free",
            "agy/gemini-4-carbon-low",
            "agy/gemini-4-argon-low",
        ]
    )
    roster = Roster(models=models, state_file=state_file, now=2000.0)
    assert roster.pick(role="review") == "agy/gemini-4-argon-low"
    assert roster.pick(role="implement") == "agy/gemini-4-argon-low"

    # Mutating methods and stats also must not crash on broken existing entries.
    assert roster.containment_stats("opencode/a-free") == (0, 0)
    assert roster.containment_summary() == ""
    roster.mark_responded("opencode/a-free")
    roster.mark_dispatched("opencode/a-free")
    assert roster.containment_stats("opencode/a-free") == (1, 0)

    all_broken = tmp_path / "all-broken.json"
    all_broken.write_text(
        json.dumps({"a-free": 42, "b-free": {"cooldown_until": "soon"}}),
        encoding="utf-8",
    )
    empty_pick = Roster(models=["a-free", "b-free"], state_file=all_broken, now=1000.0)
    assert empty_pick.pick() is None


def test_idle_rounds_reset_after_work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC4: a cycle that attempted work resets idle_rounds to 0."""
    module = load_supervise_loop()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    state = tmp_path / ".jobloop"
    state.mkdir()
    (state / "roster.json").write_text("{}", encoding="utf-8")
    waits: list[float] = []
    cycle_waits: list[float] = []
    monkeypatch.setattr(module.time, "sleep", lambda seconds: waits.append(seconds))
    monkeypatch.setattr(module, "heartbeat", lambda *args, **kwargs: None)
    outputs = iter(
        [
            (0, "-: idle - no actionable job is left\n"),
            (0, "T-JOB-1: delivered - abc merged into loop/local-development\n"),
            (0, "-: idle - no actionable job is left\n"),
        ]
    )

    def fake_stream(argv: list[str]) -> tuple[int, str]:
        if waits:
            cycle_waits.append(sum(waits))
            waits.clear()
        return next(outputs)

    monkeypatch.setattr(module, "stream", fake_stream)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: type("R", (), {"stdout": "", "stderr": "", "returncode": 0})(),
    )
    import jobloop.cli as cli

    monkeypatch.setattr(cli, "installed_models", lambda executable=None: [])
    module.main(
        [
            "--phase",
            "p",
            "--pause",
            "120",
            "--cycles",
            "3",
            "--minutes",
            "0.1",
            "--max-jobs",
            "1",
        ]
    )
    if waits:
        cycle_waits.append(sum(waits))
    # idle -> backoff(120,1)=240, worked -> pause=120, idle after reset -> 240
    assert cycle_waits == [pytest.approx(240.0), pytest.approx(120.0), pytest.approx(240.0)]


# --- second tier: agy (owner decision 2026-11-25, E2) ------------------------


def test_the_second_tier_comes_after_every_free_model_and_only_assigned_families() -> None:
    # The owner assigned three families and a role each. `agy models` also reports
    # Neon, Claude and GPT entries; a model nobody assigned is a model nobody chose,
    # so it must not enter the roster by accident.
    ranked = eligible(
        [
            "opencode/iceman-free",
            "agy/gemini-4-carbon-medium",
            "ollama/gemma3:4b",
            "agy/gemini-4-neon-high",
            "agy/claude-opus-5-5-high",
            "agy/gemini-4-argon-low",
            "agy/gemini-4-hydrogen-low",
            "agy/gemini-4-carbon-low",
        ]
    )
    first = [name for name in ranked if not name.startswith("agy/")]
    second = [name for name in ranked if name.startswith("agy/")]
    assert ranked == first + second, "the free tier must be exhausted before agy is reached"
    assert set(first) == {"opencode/iceman-free", "ollama/gemma3:4b"}
    assert "agy/gemini-4-neon-high" not in ranked, "an unassigned family must stay out"
    assert "agy/claude-opus-5-5-high" not in ranked, "an unassigned model must stay out"
    assert second.index("agy/gemini-4-carbon-low") < second.index("agy/gemini-4-carbon-medium"), (
        "within one family the cheaper effort is tried first"
    )


def test_the_second_tier_keeps_the_owners_role_assignment(tmp_path: Path) -> None:
    models = eligible(
        [
            "opencode/iceman-free",
            "agy/gemini-4-carbon-low",
            "agy/gemini-4-argon-low",
            "agy/gemini-4-hydrogen-low",
        ]
    )
    state = tmp_path / "roster.json"
    roster = Roster(models=models, state_file=state, now=1000.0)
    # A free model carries no role, so it answers every role and still comes first.
    assert roster.pick(role="implement") == "opencode/iceman-free"
    assert roster.pick(role="review") == "opencode/iceman-free"
    roster.mark_exhausted("opencode/iceman-free")
    spent = Roster(models=models, state_file=state, now=1000.0)
    assert spent.pick(role="implement") == "agy/gemini-4-carbon-low", "Carbon implements"
    assert spent.pick(role="review") == "agy/gemini-4-argon-low", "Argon reviews"
    assert spent.pick(role="light") == "agy/gemini-4-hydrogen-low", "Hydrogen takes light work"
    # The assignment exists so that implementation and review are different
    # families: asking for a reviewer must never hand back the implementing one.
    assert spent.pick_reviewer("agy/gemini-4-carbon-low") == "agy/gemini-4-argon-low"


def test_an_agy_result_line_is_read_and_a_spent_allowance_rotates() -> None:
    # The measured shape (2026-11-25): the last `result` event carries everything.
    ok = json.dumps(
        {
            "event": "result",
            "result": {
                "status": "SUCCESS",
                "response": "PONG\n",
                "usage": {"total_tokens": 16050},
            },
        }
    )
    text, errors, tokens, status = worker.read_agy_result('{"event":"init"}\n' + ok)
    assert text.strip() == "PONG"
    assert errors == []
    assert tokens == 16050
    assert status == "SUCCESS"

    spent = json.dumps(
        {
            "event": "result",
            "result": {"status": "ERROR", "response": "", "error": "usage limit reached"},
        }
    )
    result = worker.run_agy(
        "agy/gemini-4-carbon-low",
        "brief",
        cwd=Path("."),
        timeout=5.0,
        executable="agy",
        runner=lambda *a, **k: subprocess.CompletedProcess(a[0], 0, spent, ""),
    )
    assert result.rotate, "a spent allowance must not consume the job's attempt"
    assert result.ending is worker.Ending.EXHAUSTED


def test_an_agy_brief_travels_on_stdin_because_print_needs_its_own_argument(
    tmp_path: Path,
) -> None:
    # Measured 2026-11-25: `--print` takes its prompt as the flag's argument, and a
    # whole job brief exceeds the Windows command line. So the prompt goes in as one
    # NDJSON message on stdin, which needs an empty `--print=` to switch print mode on.
    seen: dict[str, object] = {}

    def fake(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        seen["command"] = command
        seen["input"] = options.get("input")
        seen["cwd"] = options.get("cwd")
        answer = json.dumps(
            {"event": "result", "result": {"status": "SUCCESS", "response": "done"}}
        )
        return subprocess.CompletedProcess(command, 0, answer, "")

    brief = "x" * 40000
    result = worker.run_agy(
        "agy/gemini-4-argon-low",
        brief,
        cwd=tmp_path,
        timeout=5.0,
        executable="agy",
        runner=fake,
    )
    command = seen["command"]
    assert isinstance(command, list)
    assert "--print=" in command, "print mode has to be on without taking the prompt"
    assert not any(part.startswith("--print=") and len(part) > 8 for part in command), (
        "the brief must not be passed on the command line"
    )
    assert "--model" in command and "gemini-4-argon-low" in command, (
        "the provider prefix is the roster's, not the CLI's"
    )
    assert "--dangerously-skip-permissions" in command, "an unattended session cannot be prompted"
    sent = seen["input"]
    assert isinstance(sent, str)
    message = json.loads(sent.strip())
    assert message["event"] == "user", "the stream input key is `event`, not `type`"
    assert message["message"]["content"][0]["text"] == brief
    assert seen["cwd"] == str(tmp_path), "agy takes the process's working directory"
    assert result.ending is worker.Ending.COMPLETED


def test_agy_model_discovery_prefixes_ids_and_skips_the_progress_line() -> None:
    from jobloop.cli import agy_installed_models

    printed = (
        "Fetching available models...\n"
        "gemini-4-carbon-medium\tGemini 4 Carbon (Medium)\n"
        "gemini-4-argon-low\tGemini 4 Argon (Low)\n"
    )
    import jobloop.cli as cli_module

    original = cli_module.subprocess.run
    try:
        cli_module.subprocess.run = (  # type: ignore[assignment]
            lambda *a, **k: subprocess.CompletedProcess(a[0], 0, printed, "")
        )
        found = agy_installed_models(executable="agy")
    finally:
        cli_module.subprocess.run = original  # type: ignore[assignment]
    assert found == ["agy/gemini-4-carbon-medium", "agy/gemini-4-argon-low"], (
        "every other part of the loop identifies a model by provider/id"
    )


def test_the_record_names_the_cli_that_actually_ran_the_session(tmp_path: Path) -> None:
    # The assignee was the fixed string `opencode`. With the second tier in place
    # (owner E2, 2026-11-25) a job can be run by `agy`, and `T-PH9-406` was in fact
    # dispatched to it at 20:34 that evening. A record that still said `opencode`
    # would send the next reader to the wrong log and the wrong process list.
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["agy/gemini-4-carbon-low"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED,
        "REPORT\n- done\n\nTEST\n- passed\n\nSTATUS\nready-for-review\n",
        model,
        [],
    )
    controller.run_job(controller.select())
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    assert task.fields["model"] == "agy/gemini-4-carbon-low"
    assert task.fields["assignee"] == "agy", "the assignee is the provider, not a fixed string"


def test_a_role_is_a_preference_so_a_spent_family_never_stalls_the_queue(tmp_path: Path) -> None:
    # Found by the test above, not by reading: asking for `light` when only the
    # Carbon family is available returned None, and the controller reported
    # `no-model` with a usable model sitting right there. The owner assigned roles
    # so that work gets done; a preference that stops work is not what was asked.
    roster = Roster(
        models=["agy/gemini-4-carbon-low"],
        state_file=tmp_path / "roster.json",
        now=1000.0,
    )
    assert roster.pick(role="light") == "agy/gemini-4-carbon-low"
    assert roster.pick(role="review") == "agy/gemini-4-carbon-low"
    # The guarantee that does hold absolutely is that a reviewer is never the
    # implementer — that one comes from `exclude`, not from the role.
    assert roster.pick_reviewer("agy/gemini-4-carbon-low") is None

    both = Roster(
        models=["agy/gemini-4-carbon-low", "agy/gemini-4-hydrogen-low"],
        state_file=tmp_path / "both.json",
        now=1000.0,
    )
    assert both.pick(role="light") == "agy/gemini-4-hydrogen-low", (
        "with the assigned family available, the assignment is what decides"
    )


# --- conflicted workspace commits (T-PH9-414) --------------------------------


def conflicted_workspace(tmp_path: Path) -> tuple[Controller, Path, str, str]:
    """A repository and workspace whose reviewed commit conflicts with the moved branch."""
    phase_with_task(tmp_path, TASK.replace("backend/app/service.py", "shared.txt"))
    repository = tmp_path
    git(repository, "init", "-b", "loop/local-development", check=False)
    git(repository, "config", "user.email", "t@example.invalid")
    git(repository, "config", "user.name", "t")
    (repository / ".gitignore").write_text(".jobloop/\n", encoding="utf-8")
    (repository / "shared.txt").write_text("base\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "--date=2026-11-24T12:31:00+09:00", "-m", "base")
    base = git(repository, "rev-parse", "HEAD").strip()

    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.settings.python = sys.executable
    controller.settings.push = False
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    tree = controller.workspace(task)
    git(tree, "config", "user.email", "w@example.invalid")
    git(tree, "config", "user.name", "w")
    (tree / "shared.txt").write_text("the job's own change\n", encoding="utf-8")

    # The integration branch moves ahead in two commits, one of them conflicting,
    # and one touching an unrelated file that must not appear in the job's diffstat.
    (repository / "shared.txt").write_text("someone else's change\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "conflicting merge on integration")
    (repository / "other_job.py").write_text("unrelated = True\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "unrelated job merged later")

    outcome = controller.deliver(
        tasks.load_phase(controller.settings.phase_directory).tasks[0],
        tree,
        "a-free",
        "b-free",
        [],
    )
    assert outcome.state == "escalated" and "merge conflicted" in outcome.detail
    head = git(tree, "rev-parse", "HEAD").strip()
    return controller, tree, base, head


def test_merge_conflict_escalation_records_base_behind_own_diffstat_and_ref(
    tmp_path: Path,
) -> None:
    """AC4: conflict escalation records base date, commits behind, own stat, and ref."""
    controller, tree, base, head = conflicted_workspace(tmp_path)
    decisions = (controller.settings.phase_directory / "OWNER_DECISIONS.md").read_text(
        encoding="utf-8"
    )
    assert f"commit={head}" in decisions
    assert base[:7] in decisions, "the merge-base commit must be named"
    assert "2026-11-24" in decisions and "12:31" in decisions, "base commit date/time must be shown"
    assert "behind=" in decisions or "behind" in decisions
    # 2 commits on integration branch + 1 progress commit recorded by deliver = 3 commits behind.
    behind = git(tree, "rev-list", "--count", "HEAD..FETCH_HEAD").strip()
    assert int(behind) >= 2
    assert f"{behind} commit" in decisions or f"behind={behind}" in decisions
    assert "shared.txt" in decisions, "merge-base..HEAD diffstat must show this job's file"
    assert "other_job.py" not in decisions, (
        "diffstat must be merge-base..HEAD, never FETCH_HEAD..HEAD"
    )
    assert "stale/T-JOB-1-" in decisions, "the preservation ref name must be recorded"
    tag = next(
        part.split("=", 1)[-1].strip().strip("`")
        for line in decisions.splitlines()
        for part in line.split()
        if "stale/T-JOB-1-" in part
    )
    shown = git(tree, "show", tag)
    assert "the job's own change" in shown
    task_record = (controller.settings.phase_directory / "tasks" / "T-JOB-1.md").read_text(
        encoding="utf-8"
    )
    assert base[:7] in task_record and "2026-11-24" in task_record
    assert f"behind={behind}" in task_record
    assert "shared.txt" in task_record and "other_job.py" not in task_record
    assert f"preserved_ref={tag}" in task_record


def test_already_conflicted_ahead_commit_does_not_rerun_gates_on_next_cycle(
    tmp_path: Path,
) -> None:
    """AC1: when behind > 0 and ahead > 0 and HEAD is already recorded as conflicted, skip gates."""
    controller, _tree, _base, _head = conflicted_workspace(tmp_path)
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    # Simulate an operator putting the job back into `review` without advancing the base.
    controller.set_fields(task, status="review", model="a-free")

    import jobloop.gates as gates_module

    original_within = gates_module.within_scope
    original_run = gates_module.run_command
    gates_module.within_scope = lambda *_a, **_k: pytest.fail(  # type: ignore[assignment]
        "scope gate must not run for an ahead commit already recorded as conflicted"
    )
    gates_module.run_command = lambda *_a, **_k: pytest.fail(  # type: ignore[assignment]
        "gates must not be re-run for an ahead commit already recorded as conflicted"
    )
    try:
        outcome = controller.resume(tasks.load_phase(controller.settings.phase_directory).tasks[0])
        assert outcome.state == "escalated" and "merge conflicted" in outcome.detail
        assert tasks.load_phase(controller.settings.phase_directory).tasks[0].status == "blocked"

        # Simulate an operator putting the job back into `doing` without advancing the base
        # (the exact 2026-11-24 16:30 ruling on T-PH9-406): `run_job` / `run` must not
        # dispatch a worker or re-run gates on the same conflicted commit either.
        controller.set_fields(task, status="doing", model="a-free")
        controller.dispatch = lambda *_a, **_k: pytest.fail("must not dispatch on stale conflict")  # type: ignore[assignment]
        outcomes = controller.run(minutes=0.2, max_jobs=3)
        assert outcomes[0].state == "escalated" and "merge conflicted" in outcomes[0].detail
        assert tasks.load_phase(controller.settings.phase_directory).tasks[0].status == "blocked"
    finally:
        gates_module.within_scope = original_within
        gates_module.run_command = original_run


def test_unconflicted_ahead_commit_still_runs_gates_on_resume(tmp_path: Path) -> None:
    """Neighbouring case: an ahead commit with no prior conflict record still runs its gates."""
    phase_with_task(tmp_path, TASK.replace("backend/app/service.py", "shared.txt"))
    repository = tmp_path
    git(repository, "init", "-b", "loop/local-development", check=False)
    git(repository, "config", "user.email", "t@example.invalid")
    git(repository, "config", "user.name", "t")
    (repository / ".gitignore").write_text(".jobloop/\n", encoding="utf-8")
    (repository / "shared.txt").write_text("base\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "base")

    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.settings.python = sys.executable
    controller.settings.push = False
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    tree = controller.workspace(task)
    git(tree, "config", "user.email", "w@example.invalid")
    git(tree, "config", "user.name", "w")
    (tree / "shared.txt").write_text("clean ahead change\n", encoding="utf-8")
    git(tree, "add", "-A")
    git(tree, "commit", "-m", "reviewed work")

    # Integration moves on a different file, so behind=1 and ahead=1, with no conflict record.
    (repository / "other.txt").write_text("other\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "non-conflicting move")

    controller.set_fields(task, status="review", model="a-free")
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "VERDICT\n- APPROVED\n\nFINDINGS\n- none", model
    )
    outcome = controller.resume(tasks.load_phase(controller.settings.phase_directory).tasks[0])
    assert outcome.state == "delivered", outcome.detail


def test_advancing_base_preserves_commit_as_ref_and_reaches_zero_behind_zero_ahead(
    tmp_path: Path,
) -> None:
    """AC2 & AC3: advancing the base saves the job's commit in a ref and leaves behind=0/ahead=0."""
    controller, tree, _base, head = conflicted_workspace(tmp_path)
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]

    # Without an explicit instruction/call to advance the base, refresh() still refuses!
    controller.refresh(task, tree)
    assert git(tree, "rev-parse", "HEAD").strip() == head, (
        "unattended refresh() must still refuse to reset an ahead workspace"
    )

    ref = controller.advance_base(task, tree)
    assert ref.startswith("stale/T-JOB-1-")
    assert git(tree, "rev-parse", f"{ref}^{{commit}}").strip() == head
    shown = git(tree, "show", ref)
    assert "+the job's own change" in shown

    # After advancing the base, refresh() sees behind=0 and ahead=0.
    controller.refresh(tasks.load_phase(controller.settings.phase_directory).tasks[0], tree)
    behind = git(tree, "rev-list", "--count", "HEAD..FETCH_HEAD").strip()
    ahead = git(tree, "rev-list", "--count", "FETCH_HEAD..HEAD").strip()
    assert behind == "0" and ahead == "0"
    assert (tree / "shared.txt").read_text(encoding="utf-8") == "someone else's change\n"


def test_timeout_does_not_spend_attempt_and_rests_model_for_rotation(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    seen: list[str] = []

    def dispatch(model: str, prompt: str, **_: object) -> worker.Result:
        seen.append(model)
        return worker.Result(worker.Ending.TIMEOUT, "", model, ["no reply within 1800s"])

    controller.dispatch = dispatch  # type: ignore[assignment]

    first = controller.run_job(controller.select())
    assert first.state == "rotated"
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    assert task.attempts == 0, "a timed-out dispatch must not spend an attempt"
    body = task.path.read_text(encoding="utf-8")
    assert "## TIMEOUT (" in body
    assert "timed out after " in body and "s (" in body
    assert f"consecutive 1/{controller_module.TIMEOUT_ESCALATE_LIMIT}" in body

    second = controller.run_job(controller.select())
    assert second.state == "rotated"
    assert seen == ["a-free", "b-free"], (
        "timed-out model must be rested so the next dispatch rotates"
    )


def test_completed_reply_failing_acceptance_still_spends_attempt(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "done", model, []
    )
    outcome = controller.run_job(controller.select())
    assert outcome.state == "attempt-failed"
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    assert task.attempts == 1


def test_consecutive_timeouts_escalate_at_limit(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    models = [f"m{i}-free" for i in range(controller_module.TIMEOUT_ESCALATE_LIMIT)]
    controller = controller_for(tmp_path, models)
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.TIMEOUT, "", model, ["no reply within 1800s"]
    )

    for idx in range(controller_module.TIMEOUT_ESCALATE_LIMIT - 1):
        outcome = controller.run_job(controller.select())
        assert outcome.state == "rotated"
        assert f"consecutive {idx + 1}/{controller_module.TIMEOUT_ESCALATE_LIMIT}" in outcome.detail

    final = controller.run_job(controller.select())
    assert final.state == "escalated"
    assert "timeout limit reached" in final.detail
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    assert task.attempts == 0
    assert task.status == "blocked"
    decisions = (controller.settings.phase_directory / "OWNER_DECISIONS.md").read_text(
        encoding="utf-8"
    )
    assert "timeout limit reached" in decisions


def test_mypy_strict_passes_on_jobloop_and_rejects_no_any_return(tmp_path: Path) -> None:
    """`python -m mypy jobloop` must pass with 0 errors and reject `no-any-return`."""
    from mypy import api as mypy_api

    root = Path(__file__).resolve().parents[1]
    bad = tmp_path / "bad_return.py"
    bad.write_text(
        "from typing import Any\n\ndef f(x: Any) -> str:\n    return x\n",
        encoding="utf-8",
    )
    bad_out, _bad_err, bad_code = mypy_api.run(
        ["--config-file", str(root / "pyproject.toml"), str(bad)]
    )
    assert bad_code != 0
    assert "no-any-return" in bad_out

    clean_out, clean_err, clean_code = mypy_api.run(
        ["--config-file", str(root / "pyproject.toml"), str(root / "jobloop")]
    )
    assert clean_code == 0, clean_out + clean_err
    assert "Success: no issues found" in clean_out


# --- repeated exhaustion cooldown (T-PH9-409) --------------------------------


def test_repeated_exhaustion_right_after_cooldown_doubles_up_to_daily_cap(
    tmp_path: Path,
) -> None:
    """AC1, AC2 & AC3 (cap): immediate re-exhaustion after cooldown doubles up to 24h."""
    base = roster_module.COOLDOWN_SECONDS
    window = roster_module.EXHAUSTION_RETRY_WINDOW_SECONDS
    cap = roster_module.EXHAUSTION_COOLDOWN_CAP
    assert window == 30 * 60
    assert cap == 24 * 60 * 60

    state = tmp_path / "roster.json"
    now = 1_000_000.0
    waits: list[float] = []
    for step in range(6):
        roster = Roster(models=["a-free"], state_file=state, now=now)
        roster.mark_exhausted("a-free")
        recorded = json.loads(state.read_text(encoding="utf-8"))["a-free"]
        wait = float(recorded["cooldown_until"]) - now
        waits.append(wait)
        # Try again shortly after cooldown expires (within EXHAUSTION_RETRY_WINDOW_SECONDS).
        now = float(recorded["cooldown_until"]) + (window / 2 if step % 2 == 0 else 25.0)

    # AC1: 2nd cooldown right after expiry is longer than the 1st.
    assert waits[0] == base
    assert waits[1] > waits[0]
    # AC2: 3 consecutive immediate exhaustions double each time (6h -> 12h -> 24h).
    assert waits[1] == 2 * base
    assert waits[2] == 4 * base
    # AC3 (cap): never exceeds EXHAUSTION_COOLDOWN_CAP (tried at least once a day).
    assert waits[3] == cap
    assert all(wait <= cap for wait in waits)
    assert Roster(models=["a-free"], state_file=state, now=now).pick() == "a-free"


def test_exhaustion_after_retry_window_resets_to_normal_cooldown(tmp_path: Path) -> None:
    """AC3 (elapsed window): exhaustion well after cooldown expiry returns to normal 6h."""
    base = roster_module.COOLDOWN_SECONDS
    window = roster_module.EXHAUSTION_RETRY_WINDOW_SECONDS
    state = tmp_path / "roster.json"

    t0 = 1_000_000.0
    first = Roster(models=["a-free"], state_file=state, now=t0)
    first.mark_exhausted("a-free")
    until_1 = float(json.loads(state.read_text(encoding="utf-8"))["a-free"]["cooldown_until"])
    assert until_1 - t0 == base

    # Immediate re-exhaustion stretches cooldown to 12h.
    t1 = until_1 + 60.0
    second = Roster(models=["a-free"], state_file=state, now=t1)
    second.mark_exhausted("a-free")
    until_2 = float(json.loads(state.read_text(encoding="utf-8"))["a-free"]["cooldown_until"])
    assert until_2 - t1 == 2 * base

    # Exhaustion well after cooldown expiry (beyond EXHAUSTION_RETRY_WINDOW_SECONDS)
    # represents normal allowance consumption, so it resets back to 6h.
    t2 = until_2 + window + 1.0
    third = Roster(models=["a-free"], state_file=state, now=t2)
    third.mark_exhausted("a-free")
    until_3 = float(json.loads(state.read_text(encoding="utf-8"))["a-free"]["cooldown_until"])
    assert until_3 - t2 == base


def test_working_model_resets_exhaustion_streak_and_attempts_stay_zero(
    tmp_path: Path,
) -> None:
    """AC3 (responded) & AC4: answering resets stretched cooldown; exhaustion spends 0 attempts."""
    base = roster_module.COOLDOWN_SECONDS
    state = tmp_path / ".jobloop" / "roster.json"

    # Build an exhaustion streak on both implementer and reviewer models.
    t0 = 1_000_000.0
    for model in ("a-free", "b-free"):
        r1 = Roster(models=["a-free", "b-free"], state_file=state, now=t0)
        r1.mark_exhausted(model)
        u1 = float(json.loads(state.read_text(encoding="utf-8"))[model]["cooldown_until"])
        r2 = Roster(models=["a-free", "b-free"], state_file=state, now=u1 + 25.0)
        r2.mark_exhausted(model)
        u2 = float(json.loads(state.read_text(encoding="utf-8"))[model]["cooldown_until"])
        assert u2 - (u1 + 25.0) == 2 * base

    # Wait for stretched cooldowns to expire, then let `a-free` answer a job as implementer.
    ready_time = t0 + base + 25.0 + 2 * base + 10.0
    phase_with_task(tmp_path)
    controller = Controller(
        settings_for(tmp_path),
        Roster(models=["a-free", "b-free"], state_file=state, now=ready_time),
        clock=lambda: 0.0,
    )
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- nothing changed", model
    )
    outcome = controller.run_job(controller.select())
    assert outcome.state == "attempt-failed" and outcome.model == "a-free"

    # Now `a-free` hits exhaustion immediately: because it answered a job, cooldown is 6h again.
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.EXHAUSTED, "", model, ["free usage quota exceeded"]
    )
    rotated = controller.run_job(controller.select())
    assert rotated.state == "rotated" and rotated.model == "a-free"
    task_after_rotate = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    assert task_after_rotate.attempts == 1, "AC4: exhaustion must not consume an attempt"
    recorded_a = json.loads(state.read_text(encoding="utf-8"))["a-free"]
    assert float(recorded_a["cooldown_until"]) - ready_time == base

    # Also verify `b-free` resets its exhaustion streak when answering as a reviewer.
    phase_with_task(tmp_path / "rev")
    tree = reviewable_worktree(tmp_path / "rev")
    rev_controller = Controller(
        settings_for(tmp_path / "rev"),
        Roster(models=["a-free", "b-free"], state_file=state, now=ready_time + 5.0),
        clock=lambda: 0.0,
    )
    rev_controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "VERDICT\n- CHANGES_REQUIRED", model
    )
    rev_task = rev_controller.select()
    assert rev_task is not None
    rev_outcome = rev_controller.review(rev_task, tree, "c-free", [])
    assert rev_outcome.reviewer == "b-free"

    rev_controller.roster.mark_exhausted("b-free")
    recorded_b = json.loads(state.read_text(encoding="utf-8"))["b-free"]
    assert float(recorded_b["cooldown_until"]) - (ready_time + 5.0) == base


# --- single supervisor lock and responsive stop (T-PH9-413) ------------------


def test_second_supervisor_refuses_when_live_pid_holds_lock(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1 & AC4: live PID in lock stops a second launch and logs/prints the PID."""
    module = load_supervise_loop()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    state = tmp_path / ".jobloop"
    state.mkdir()
    lock = state / module.LOCK_FILENAME
    lock.write_text("42424\n", encoding="utf-8")
    monkeypatch.setattr(module, "pid_alive", lambda pid: pid == 42424)
    monkeypatch.setattr(
        module, "stream", lambda argv: pytest.fail("second supervisor must not start a cycle")
    )

    code = module.main(["--phase", "p", "--cycles", "1"])

    out = capsys.readouterr().out
    assert code != 0
    assert "42424" in out
    assert "refused" in out.lower() or "already running" in out.lower()
    assert lock.read_text(encoding="utf-8").strip() == "42424", (
        "live holder's lock must stay intact"
    )
    beat_text = (state / "supervisor.log").read_text(encoding="utf-8")
    assert "42424" in beat_text
    assert "supervisor started" not in beat_text


def test_supervisor_stop_during_long_wait_exits_within_one_step_and_records_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2 & AC4: placing `.jobloop/stop` during a 1200s wait exits after ~one step, not 1200s."""
    module = load_supervise_loop()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    state = tmp_path / ".jobloop"
    state.mkdir()
    (state / "roster.json").write_text("{}", encoding="utf-8")
    stop = state / "stop"

    step = module.STOP_POLL_SECONDS
    assert 0 < step <= 15.0

    slept: list[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) == 2:
            stop.write_text("stop\n", encoding="utf-8")

    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    monkeypatch.setattr(module, "stream", lambda argv: (0, "-: idle - no actionable job is left\n"))
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: type("R", (), {"stdout": "", "stderr": "", "returncode": 0})(),
    )
    import jobloop.cli as cli

    monkeypatch.setattr(cli, "installed_models", lambda executable=None: [])

    code = module.main(["--phase", "p", "--pause", "600", "--cycles", "0"])

    assert code == 0
    assert sum(slept) == pytest.approx(2 * step)
    assert sum(slept) < 1200.0
    assert not (state / module.LOCK_FILENAME).exists()
    beat_text = (state / "supervisor.log").read_text(encoding="utf-8")
    assert ".jobloop/stop" in beat_text


def test_supervisor_takes_over_stale_lock_cleans_up_on_all_exits_and_keeps_full_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3: stale PID is reclaimed; normal/stop/exception exits remove lock; full wait unchanged."""
    module = load_supervise_loop()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    state = tmp_path / ".jobloop"
    state.mkdir()
    (state / "roster.json").write_text("{}", encoding="utf-8")
    lock = state / module.LOCK_FILENAME

    # 1) Stale PID in lock is reclaimed, full idle_wait total stays intact, normal exit cleans lock.
    lock.write_text("99999999\n", encoding="utf-8")
    monkeypatch.setattr(module, "pid_alive", lambda pid: False)
    slept: list[float] = []
    seen_lock_during_cycle: list[str] = []

    def fake_stream(argv: list[str]) -> tuple[int, str]:
        seen_lock_during_cycle.append(lock.read_text(encoding="utf-8").strip())
        return (0, "-: idle - no actionable job is left\n")

    monkeypatch.setattr(module.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(module, "stream", fake_stream)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: type("R", (), {"stdout": "", "stderr": "", "returncode": 0})(),
    )
    import jobloop.cli as cli

    monkeypatch.setattr(cli, "installed_models", lambda executable=None: [])

    assert module.main(["--phase", "p", "--pause", "120", "--cycles", "1"]) == 0
    assert seen_lock_during_cycle == [str(module.os.getpid())]
    # idle_rounds=1 with pause=120 -> backoff(120, 1) = 240.0 total sleep preserved!
    assert sum(slept) == pytest.approx(240.0)
    assert all(chunk <= module.STOP_POLL_SECONDS for chunk in slept)
    assert not lock.exists(), "normal exit must remove the lock"

    # 2) Pre-existing `.jobloop/stop` exit removes the lock and logs the stop marker exit.
    (state / "stop").write_text("", encoding="utf-8")
    assert module.main(["--phase", "p", "--cycles", "0"]) == 0
    assert not lock.exists(), "stop exit must remove the lock"
    (state / "stop").unlink()

    # 3) Unhandled exception during cycle removes the lock too.
    def boom_stream(argv: list[str]) -> tuple[int, str]:
        assert lock.is_file()
        raise RuntimeError("boom in stream")

    monkeypatch.setattr(module, "stream", boom_stream)
    with pytest.raises(RuntimeError, match="boom in stream"):
        module.main(["--phase", "p", "--cycles", "1"])
    assert not lock.exists(), "exception exit must remove the lock"


def test_pid_alive_distinguishes_live_and_exited_processes() -> None:
    """Real OS liveness probe sees our own PID and spawned child, and false after child exits."""
    module = load_supervise_loop()
    assert module.pid_alive(module.os.getpid()) is True
    assert module.pid_alive(0) is False
    assert module.pid_alive(-5) is False

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    try:
        assert module.pid_alive(child.pid) is True
    finally:
        child.terminate()
        child.wait(timeout=5)
    assert module.pid_alive(child.pid) is False


# --- second-tier agy worker visibility in shift_check (T-PH9-417) ------------


def load_shift_check():
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "shift_check", root / "scripts" / "shift_check.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_shift_check_processes_queries_and_classifies_agy_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1 & AC2: `processes()` queries `agy.EXE`, classifies job sessions, and excludes helpers."""
    check = load_shift_check()
    queries: list[tuple[str, ...]] = []
    fake_wmi = "\n".join(
        [
            (
                "45224|48460|python.exe|2026-11-26T02:42:53|"
                r"C:\Locus\.venv\Scripts\python.exe scripts/supervise_loop.py"
            ),
            (
                "5472|44240|agy.EXE|2026-11-26T05:12:41|"
                r"C:\agy\bin\agy.EXE --model gemini-4-carbon-low "
                "--input-format stream-json --output-format stream-json "
                "--dangerously-skip-permissions --disable-slash-commands --print="
            ),
            (
                "13668|24620|opencode.exe|2026-11-23T19:30:05|"
                r"C:\opencode\bin\opencode.exe serve --service"
            ),
            (
                "7001|44240|opencode.exe|2026-11-26T05:00:00|"
                r"C:\opencode\bin\opencode.exe run --standalone --model opencode/a-free"
            ),
            (
                "8001|99999|agy.EXE|2026-11-26T04:00:00|"
                r"C:\agy\bin\agy.EXE remote-control start"
            ),
            (
                "8002|99999|agy.EXE|2026-11-26T04:01:00|"
                r"C:\agy\bin\agy.EXE"
            ),
        ]
    )

    def fake_run(*command: str, quiet: bool = False) -> str:
        queries.append(command)
        return fake_wmi

    monkeypatch.setattr(check.sys, "platform", "win32")
    monkeypatch.setattr(check, "run", fake_run)

    found = check.processes()
    assert queries, "processes() must run the WMI query on win32"
    joined_query = " ".join(queries[0]).lower()
    assert "agy.exe" in joined_query, "WMI filter must include agy.EXE"
    assert "opencode.exe" in joined_query and "python.exe" in joined_query

    by_pid = {pid: (parent, name, created, kind) for pid, parent, name, created, kind in found}
    assert 5472 in by_pid and by_pid[5472][1] == "agy.EXE"
    assert by_pid[5472][3] == "agy_session"
    assert by_pid[13668][3] == "serve_service"
    assert by_pid[7001][3] == "run_standalone"
    # Non-worker agy invocations (daemon / interactive session) are not job sessions.
    assert by_pid.get(8001, (0, "", "", None))[3] != "agy_session"
    assert by_pid.get(8002, (0, "", "", None))[3] != "agy_session"


def test_shift_check_orphans_and_liveness_handle_agy_workers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2, AC3 & AC4: fake process list with `agy.EXE` proves orphan and liveness checks."""
    check = load_shift_check()
    monkeypatch.setattr(check, "ROOT", tmp_path)

    # 1) Live parent for agy.EXE + parentless `serve --service` => no orphan, worker alive.
    monkeypatch.setattr(check, "running", lambda pid: pid == 44240)
    live_healthy = [
        (45224, 48460, "python.exe", "2026-11-26T02:42:53", None),
        (13668, 24620, "opencode.exe", "2026-11-23T19:30:05", "serve_service"),
        (5472, 44240, "agy.EXE", "2026-11-26T05:12:41", "agy_session"),
    ]
    assert check.orphans(live_healthy) == "ok    no orphaned worker"
    sup_with_agy = check.supervisor(live_healthy)
    assert sup_with_agy.startswith("ok"), sup_with_agy
    assert "1 loop process(es) alive" in sup_with_agy
    assert "1 worker(s) alive" in sup_with_agy

    # Without any active worker (only the owner's `serve --service`), active worker count is 0.
    live_idle = [
        (45224, 48460, "python.exe", "2026-11-26T02:42:53", None),
        (13668, 24620, "opencode.exe", "2026-11-23T19:30:05", "serve_service"),
    ]
    sup_idle = check.supervisor(live_idle)
    assert sup_idle == "ok    1 loop process(es) alive"

    # When python died while an agy worker is still running, worker count is still shown on FAIL.
    sup_dead_with_worker = check.supervisor(
        [(5472, 44240, "agy.EXE", "2026-11-26T05:12:41", "agy_session")]
    )
    assert sup_dead_with_worker.startswith("FAIL"), sup_dead_with_worker
    assert "1 worker(s) alive" in sup_dead_with_worker

    # 2) Dead parent for `agy.EXE` => orphaned worker reported; `serve --service` stays excluded.
    monkeypatch.setattr(check, "running", lambda pid: False)
    orphan_line = check.orphans(live_healthy)
    assert orphan_line.startswith("FAIL  orphaned worker session:"), orphan_line
    assert "5472" in orphan_line
    assert "2026-11-26T05:12" in orphan_line
    assert "13668" not in orphan_line, "`serve --service` exclusion must remain intact"


def test_all_models_rotated_then_no_model_resets_frontmatter(tmp_path: Path) -> None:
    # When all eligible models fail during rotation (including UNAVAILABLE such
    # as "does not support tools") and no-model is reached, the task's
    # frontmatter (`status`, `assignee`, `model`) must remain its pre-dispatch
    # state. When a later model in the rotation succeeds, `model` and `assignee`
    # must record that succeeding model.
    directory = phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["ollama/gemma3:4b", "opencode/b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]

    task = tasks.load_phase(directory).tasks[0]
    original_fields = dict(task.fields)

    def rotating_dispatch(model: str, prompt: str, **_: object) -> worker.Result:  # type: ignore[assignment]
        during = tasks.load_phase(directory).tasks[0]
        assert during.fields.get("status") == "doing"
        assert during.fields.get("model") == model
        assert during.fields.get("assignee") == model.split("/", 1)[0]
        if model == "ollama/gemma3:4b":
            return worker.Result(
                worker.Ending.UNAVAILABLE,
                "",
                model,
                ["does not support tools"],
            )
        return worker.Result(
            worker.Ending.OUTAGE,
            "",
            model,
            ["provider outage"],
        )

    controller.dispatch = rotating_dispatch
    outcome1 = controller.run_job(controller.select())
    assert outcome1.state == "rotated", outcome1.detail
    outcome2 = controller.run_job(controller.select())
    assert outcome2.state == "rotated", outcome2.detail
    outcome3 = controller.run_job(controller.select())
    assert outcome3.state == "no-model", outcome3.detail

    task = tasks.load_phase(directory).tasks[0]
    for key in ("status", "assignee", "model"):
        got = task.fields.get(key)
        exp = original_fields.get(key)
        assert got == exp, f"{key} was not preserved: got {got!r}, expected {exp!r}"

    # AC3: when a later model in the rotation succeeds, `model` and `assignee`
    # record that succeeding model.
    directory2 = phase_with_task(tmp_path / "ac3")
    controller2 = controller_for(tmp_path / "ac3", ["ollama/gemma3:4b", "opencode/b-free"])
    controller2.workspace = lambda task: tmp_path / "ac3"  # type: ignore[assignment]

    def second_succeeds(model: str, prompt: str, **_: object) -> worker.Result:  # type: ignore[assignment]
        if model == "ollama/gemma3:4b":
            return worker.Result(
                worker.Ending.UNAVAILABLE,
                "",
                model,
                ["does not support tools"],
            )
        return worker.Result(
            worker.Ending.COMPLETED,
            "REPORT\n- done\n\nTEST\n- passed\n\nSTATUS\nready-for-review\n",
            model,
            [],
        )

    controller2.dispatch = second_succeeds
    assert controller2.run_job(controller2.select()).state == "rotated"
    outcome = controller2.run_job(controller2.select())
    assert outcome.model == "opencode/b-free"
    task2 = tasks.load_phase(directory2).tasks[0]
    assert task2.fields.get("model") == "opencode/b-free"
    assert task2.fields.get("assignee") == "opencode"


def test_tool_incompatible_models_excluded_from_pick(tmp_path: Path) -> None:
    """AC: models that do not support tool calls are excluded from `pick` candidates.

    When a model fails with "does not support tools", it is marked tool-incompatible
    and excluded from future `pick` / `pick_reviewer` candidates. This prevents the
    model from consuming an attempt on a job it can never complete.
    """
    from jobloop.roster import Roster

    # Use only free models that support tools
    roster = Roster(
        models=["opencode/glm-5.3-flash-free", "ollama/gemma3:4b"],
        state_file=tmp_path / "roster.json",
        now=1000.0,
    )

    # Before marking, both models are eligible and pick can select either
    model = roster.pick()
    assert model in {"opencode/glm-5.3-flash-free", "ollama/gemma3:4b"}

    # Mark gemma3:4b as tool-incompatible (simulating a dispatch failure)
    roster.mark_tool_incompatible("ollama/gemma3:4b")

    # After marking, pick should exclude the tool-incompatible model
    model = roster.pick()
    assert model == "opencode/glm-5.3-flash-free", (
        f"Expected opencode/glm-5.3-flash-free, got {model}"
    )

    # pick_reviewer should also exclude the tool-incompatible model
    reviewer = roster.pick_reviewer("opencode/glm-5.3-flash-free")
    assert reviewer is None, (
        f"Expected None (only one model left, and it's the implementer), got {reviewer}"
    )


def test_tool_incompatible_attempts_not_consumed(tmp_path: Path) -> None:
    """AC: selecting a model that later proves tool-incompatible does not consume an attempt.

    When a model is dispatched and returns "does not support tools", the job must
    keep its attempt (the attempt survives, same as EXHAUSTED / OUTAGE rotation).
    The controller records this via `rotated` state, not `attempt-failed`.
    """
    from jobloop import worker

    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["ollama/gemma3:4b", "a-free", "b-free"])

    # Dispatch gemma3:4b and make it fail with "does not support tools"
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(
        worker.Ending.UNAVAILABLE,
        "",
        model,
        ["provider.invalid-request: registry.ollama.ai/library/gemma3:4b does not support tools"],
    )

    outcome = controller.run_job(controller.select())
    assert outcome.state == "rotated", f"Expected rotated, got {outcome.state}"
    assert "does not support tools" in outcome.detail

    # The attempt must NOT have been consumed
    task = tasks.load_phase(controller.settings.phase_directory).tasks[0]
    assert task.attempts == 0, f"Expected attempts 0, got {task.attempts}"

    # The model should be marked tool-incompatible and excluded from future picks
    assert "ollama/gemma3:4b" not in controller.roster.available()
    assert controller.roster.pick() == "a-free"


def test_tool_incompatible_not_counted_as_cooling(tmp_path: Path) -> None:
    """AC: excluded tool-incompatible models are not counted as "cooling" in shift_check.

    In shift_check's inventory, unusable models should not appear as "on cooldown"
    (i.e., they should not contribute to the count of models waiting to return).
    They are permanently excluded, not temporarily rested.
    """
    from jobloop.roster import Roster

    # Create a roster with a tool-incompatible model and a tool-capable model
    roster = Roster(
        models=["opencode/flint-40b-free", "ollama/gemma3:4b"],
        state_file=tmp_path / "roster.json",
        now=1000.0,
    )

    # Mark gemma3:4b as tool-incompatible
    roster.mark_tool_incompatible("ollama/gemma3:4b")

    # Check available() - the tool-incompatible model should NOT be listed
    available = roster.available()
    assert "ollama/gemma3:4b" not in available, (
        f"Tool-incompatible model should not be in available(), got {available}"
    )

    # The capable model should still be available
    assert "opencode/flint-40b-free" in available, (
        f"Capable model should be in available(), got {available}"
    )

    # Verify it is persisted without a cooldown_until timestamp (not counted as cooling)
    state = json.loads((tmp_path / "roster.json").read_text(encoding="utf-8"))
    assert state["ollama/gemma3:4b"].get("tool_incompatible") == 1.0
    assert "cooldown_until" not in state["ollama/gemma3:4b"]
