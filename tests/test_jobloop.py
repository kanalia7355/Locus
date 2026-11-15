"""The job loop must be boringly deterministic: no model gets to decide anything.

These tests use fake workers, so no provider is contacted.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from jobloop import gates, prompts, tasks, worker
from jobloop.controller import Controller, Settings
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


def test_a_worker_that_edits_the_main_checkout_is_escalated(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free", "b-free"])
    controller.workspace = lambda task: tmp_path  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- done", model
    )
    seen: list[str] = []

    def fingerprint(path: Path) -> str:
        # The main checkout looks different after the worker ran.
        seen.append(str(path))
        return f"state-{len(seen)}"

    controller.fingerprint = fingerprint  # type: ignore[assignment]
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
