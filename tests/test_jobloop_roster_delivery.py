"""Tests for per-model delivery and failed-attempt counting in jobloop.roster."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from jobloop import gates, tasks, worker
from jobloop import roster as roster_module
from jobloop.controller import UNAVAILABLE_COOLDOWN, Controller, Settings, git
from jobloop.roster import COOLDOWN_SECONDS, Roster

TASK = """---
id: T-JOB-1
phase: phase-test
status: todo
assignee: unassigned
model: -
weight: light
updated: 2026-11-27T05:20:00+09:00
attempts: 0
allowed_paths: shared.txt
test_cmd: python -c "print('ok')"
---

# Task `T-JOB-1`: 合成引き渡しジョブ

## TASK DEFINITION (Assigned by Orchestrator)

- **Acceptance Criteria**: 1. `shared.txt` を更新する。

## REPORT

- Implemented by:
"""


def _setup_repo_and_phase(tmp_path: Path, text: str = TASK) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir(parents=True, exist_ok=True)
    git(repository, "init", "-b", "loop/local-development", check=False)
    git(repository, "config", "user.email", "t@example.invalid")
    git(repository, "config", "user.name", "t")
    (repository / ".gitignore").write_text(".jobloop/\n", encoding="utf-8")
    (repository / "shared.txt").write_text("base\n", encoding="utf-8")
    directory = repository / "progress" / "phase-test"
    (directory / "tasks").mkdir(parents=True)
    (directory / "tasks" / "T-JOB-1.md").write_text(text, encoding="utf-8", newline="")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "base")
    return repository


def _controller(repository: Path, models: list[str], *, now: float = 1000.0) -> Controller:
    settings = Settings(
        repository=repository, phase="phase-test", python=sys.executable, push=False
    )
    roster = Roster(
        models=models,
        state_file=repository / ".jobloop" / "roster.json",
        now=now,
    )
    return Controller(settings, roster, clock=lambda: 0.0)


def _fast_python_gates(worktree: Path, names: list[str], **_: object) -> list[gates.Gate]:
    return []


def test_delivered_and_failed_attempts_increment_and_persist_to_roster_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1: synthetic delivered increments `deliveries` by 1, failed attempt increments
    `failed_attempts` by 1, and both persist to `roster.json`."""
    monkeypatch.setattr(gates, "python_gates", _fast_python_gates)

    # 1) Failed attempt -> failed_attempts + 1, deliveries == 0, persisted to disk.
    fail_repo = _setup_repo_and_phase(tmp_path / "fail")
    fail_ctrl = _controller(fail_repo, ["opencode/a-free", "opencode/b-free"])
    fail_ctrl.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- nothing changed", model
    )
    task = fail_ctrl.select()
    assert task is not None
    fail_outcome = fail_ctrl.run_job(task)
    assert fail_outcome.state == "attempt-failed"

    reloaded_fail = Roster(
        models=["opencode/a-free", "opencode/b-free"],
        state_file=fail_repo / ".jobloop" / "roster.json",
        now=1000.0,
    )
    assert reloaded_fail.delivery_stats("opencode/a-free") == (0, 1)
    raw_fail = json.loads((fail_repo / ".jobloop" / "roster.json").read_text(encoding="utf-8"))
    assert raw_fail["opencode/a-free"]["failed_attempts"] == 1.0
    assert raw_fail["opencode/a-free"].get("deliveries", 0.0) == 0.0

    # 2) Delivered -> implementer's deliveries + 1, reviewer untouched, persisted to disk.
    ok_repo = _setup_repo_and_phase(tmp_path / "ok")
    ok_ctrl = _controller(ok_repo, ["opencode/a-free", "opencode/b-free"])

    def impl_and_approve(model: str, prompt: str, *, cwd: Path, **_: object) -> worker.Result:
        if model == "opencode/a-free":
            (cwd / "shared.txt").write_text("delivered content\n", encoding="utf-8")
            return worker.Result(
                worker.Ending.COMPLETED,
                "REPORT\n- done\n\nTEST\n- passed\n\nSTATUS\nready-for-review",
                model,
            )
        return worker.Result(
            worker.Ending.COMPLETED, "VERDICT\n- APPROVED\n\nFINDINGS\n- none", model
        )

    ok_ctrl.dispatch = impl_and_approve  # type: ignore[assignment]
    ok_task = ok_ctrl.select()
    assert ok_task is not None
    ok_outcome = ok_ctrl.run_job(ok_task)
    assert ok_outcome.state == "delivered", ok_outcome.detail

    reloaded_ok = Roster(
        models=["opencode/a-free", "opencode/b-free"],
        state_file=ok_repo / ".jobloop" / "roster.json",
        now=1000.0,
    )
    assert reloaded_ok.delivery_stats("opencode/a-free") == (1, 0)
    assert reloaded_ok.delivery_stats("opencode/b-free") == (0, 0)
    raw_ok = json.loads((ok_repo / ".jobloop" / "roster.json").read_text(encoding="utf-8"))
    assert raw_ok["opencode/a-free"]["deliveries"] == 1.0
    assert raw_ok["opencode/a-free"].get("failed_attempts", 0.0) == 0.0
    assert "deliveries" not in raw_ok.get("opencode/b-free", {})


def test_escalated_rotated_exhausted_and_unavailable_do_not_increment_delivery_counters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: `escalated` (worker decision, out-of-scope, containment, merge conflict),
    rotation (outage / misrouted), quota exhaustion, and CLI launch failure (unavailable /
    tool-incompatible / timeout) must increment neither `deliveries` nor `failed_attempts`."""
    monkeypatch.setattr(gates, "python_gates", _fast_python_gates)

    # 1) escalated: worker asks for owner decision
    esc_repo = _setup_repo_and_phase(tmp_path / "escalated")
    esc_ctrl = _controller(esc_repo, ["opencode/a-free", "opencode/b-free"])
    esc_ctrl.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED,
        "REPORT\n- ambiguous\n\nSTATUS\n- needs-owner-decision: should shared.txt use LF or CRLF?",
        model,
    )
    esc_outcome = esc_ctrl.run_job(esc_ctrl.select())  # type: ignore[arg-type]
    assert esc_outcome.state == "escalated"
    assert esc_ctrl.roster.delivery_stats("opencode/a-free") == (0, 0)

    # 2) escalated: out-of-scope edit
    scope_repo = _setup_repo_and_phase(tmp_path / "scope")
    scope_ctrl = _controller(scope_repo, ["opencode/a-free", "opencode/b-free"])

    def out_of_scope(model: str, prompt: str, *, cwd: Path, **_: object) -> worker.Result:
        (cwd / "shared.txt").write_text("import forbidden_mod\n", encoding="utf-8")
        (cwd / "forbidden_mod.py").write_text("x = 1\n", encoding="utf-8")
        return worker.Result(
            worker.Ending.COMPLETED, "REPORT\n- done\n\nSTATUS\nready-for-review", model
        )

    scope_ctrl.dispatch = out_of_scope  # type: ignore[assignment]
    scope_outcome = scope_ctrl.run_job(scope_ctrl.select())  # type: ignore[arg-type]
    assert scope_outcome.state == "escalated"
    assert scope_ctrl.roster.delivery_stats("opencode/a-free") == (0, 0)

    # 3) rotated (provider outage) & quota exhaustion & CLI launch failure & timeout
    rot_repo = _setup_repo_and_phase(tmp_path / "rotations")
    models = [
        "opencode/outage-free",
        "opencode/exhausted-free",
        "opencode/unavailable-free",
        "opencode/notools-free",
        "opencode/timeout-free",
    ]
    rot_ctrl = _controller(rot_repo, models)
    endings = {
        "opencode/outage-free": worker.Result(
            worker.Ending.OUTAGE, "", "opencode/outage-free", ["Endpoint is unavailable"]
        ),
        "opencode/exhausted-free": worker.Result(
            worker.Ending.EXHAUSTED, "", "opencode/exhausted-free", ["usage limit reached"]
        ),
        "opencode/unavailable-free": worker.Result(
            worker.Ending.UNAVAILABLE,
            "",
            "opencode/unavailable-free",
            ["opencode executable not found"],
        ),
        "opencode/notools-free": worker.Result(
            worker.Ending.UNAVAILABLE, "", "opencode/notools-free", ["does not support tools"]
        ),
        "opencode/timeout-free": worker.Result(
            worker.Ending.TIMEOUT, "", "opencode/timeout-free", ["no reply within 1800s"]
        ),
    }
    rot_ctrl.dispatch = lambda model, prompt, **_: endings[model]  # type: ignore[assignment]
    for expected_model in models:
        task = rot_ctrl.select()
        assert task is not None
        outcome = rot_ctrl.run_job(task)
        assert outcome.state == "rotated", (expected_model, outcome)

    reloaded_rot = Roster(
        models=models,
        state_file=rot_repo / ".jobloop" / "roster.json",
        now=1000.0,
    )
    for m in models:
        assert reloaded_rot.delivery_stats(m) == (0, 0), f"{m} must stay at (0, 0)"
    task_after = tasks.load_phase(rot_ctrl.settings.phase_directory).tasks[0]
    assert task_after.attempts == 0


def test_two_failed_attempts_then_delivery_and_attempt_limit_escalation_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2 failed attempts + 1 delivery records (1, 2); 3rd attempt hitting `escalated` does not
    increment on the `escalated` outcome itself (AC2: `escalated` increments neither counter)."""
    monkeypatch.setattr(gates, "python_gates", _fast_python_gates)

    # Case A: 2 failed attempts then 1 delivery -> (deliveries=1, failed_attempts=2),
    # distinguishing "3 tries to deliver 1" from "1 try to deliver 1" (1, 0).
    mixed_repo = _setup_repo_and_phase(tmp_path / "mixed")
    mixed_ctrl = _controller(mixed_repo, ["opencode/a-free", "opencode/b-free"])
    call_count = {"a": 0}

    def two_fails_then_deliver(model: str, prompt: str, *, cwd: Path, **_: object) -> worker.Result:
        if model == "opencode/a-free":
            call_count["a"] += 1
            if call_count["a"] <= 2:
                return worker.Result(worker.Ending.COMPLETED, "REPORT\n- nothing", model)
            (cwd / "shared.txt").write_text("finally done\n", encoding="utf-8")
            return worker.Result(
                worker.Ending.COMPLETED, "REPORT\n- done\n\nSTATUS\nready-for-review", model
            )
        return worker.Result(
            worker.Ending.COMPLETED, "VERDICT\n- APPROVED\n\nFINDINGS\n- none", model
        )

    mixed_ctrl.dispatch = two_fails_then_deliver  # type: ignore[assignment]
    assert mixed_ctrl.run_job(mixed_ctrl.select()).state == "attempt-failed"  # type: ignore[arg-type]
    assert mixed_ctrl.run_job(mixed_ctrl.select()).state == "attempt-failed"  # type: ignore[arg-type]
    assert mixed_ctrl.run_job(mixed_ctrl.select()).state == "delivered"  # type: ignore[arg-type]
    assert mixed_ctrl.roster.delivery_stats("opencode/a-free") == (1, 2)

    # Case B: 3rd attempt reaches ATTEMPT_LIMIT -> outcome is `escalated`, so the two
    # `attempt-failed` outcomes incremented `failed_attempts` to 2 and the `escalated`
    # outcome itself increments neither counter.
    three_repo = _setup_repo_and_phase(tmp_path / "three")
    three_ctrl = _controller(three_repo, ["opencode/a-free", "opencode/b-free"])
    three_ctrl.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- nothing", model
    )
    assert three_ctrl.run_job(three_ctrl.select()).state == "attempt-failed"  # type: ignore[arg-type]
    assert three_ctrl.run_job(three_ctrl.select()).state == "attempt-failed"  # type: ignore[arg-type]
    assert three_ctrl.roster.delivery_stats("opencode/a-free") == (0, 2)
    assert three_ctrl.run_job(three_ctrl.select()).state == "escalated"  # type: ignore[arg-type]
    assert three_ctrl.roster.delivery_stats("opencode/a-free") == (0, 2)


def test_legacy_roster_entries_without_new_keys_default_to_zero_without_error(
    tmp_path: Path,
) -> None:
    """AC3: legacy roster.json entries without new keys read cleanly with default 0."""
    state_file = tmp_path / "roster.json"
    legacy_payload = {
        "opencode/iceman-free": {
            "cooldown_until": 500.0,
            "dispatches": 27.0,
            "containment_stops": 2.0,
            "exhausted_streak": 1.0,
            "unavailable_streak": 0.0,
            "observations": 4.0,
        },
        "ollama/gemma3:4b": {
            "dispatches": 3.0,
            "observations": 17.0,
            "tool_incompatible": 1.0,
            "unavailable_streak": 5.0,
        },
    }
    state_file.write_text(json.dumps(legacy_payload), encoding="utf-8")

    roster = Roster(
        models=["opencode/iceman-free", "ollama/gemma3:4b", "opencode/unseen-free"],
        state_file=state_file,
        now=1000.0,
    )
    assert roster.available() == ["opencode/iceman-free", "opencode/unseen-free"]
    assert roster.pick() == "opencode/iceman-free"
    assert roster.delivery_stats("opencode/iceman-free") == (0, 0)
    assert roster.delivery_stats("ollama/gemma3:4b") == (0, 0)
    assert roster.delivery_stats("opencode/unseen-free") == (0, 0)

    # Subsequent increment starts cleanly from 0 and preserves existing keys.
    roster.mark_delivered("opencode/iceman-free")
    roster.mark_attempt_failed("opencode/iceman-free")
    assert roster.delivery_stats("opencode/iceman-free") == (1, 1)
    saved = json.loads(state_file.read_text(encoding="utf-8"))["opencode/iceman-free"]
    assert saved["dispatches"] == 27.0
    assert saved["observations"] == 4.0
    assert saved["deliveries"] == 1.0
    assert saved["failed_attempts"] == 1.0


def test_existing_roster_keys_preserve_exact_semantics_and_increments(tmp_path: Path) -> None:
    """AC4: `dispatches`, `observations`, `containment_stops`, `exhausted_streak`, and
    `unavailable_streak` increment and reset exactly as before."""
    state_file = tmp_path / "roster.json"
    t0 = 1_000_000.0
    roster = Roster(models=["opencode/a-free", "opencode/b-free"], state_file=state_file, now=t0)

    # dispatches increments only dispatches (not observations, deliveries, or failed_attempts).
    roster.mark_dispatched("opencode/a-free")
    roster.mark_dispatched("opencode/a-free")
    entry = json.loads(state_file.read_text(encoding="utf-8"))["opencode/a-free"]
    assert entry["dispatches"] == 2.0
    assert entry.get("observations", 0.0) == 0.0
    assert entry.get("containment_stops", 0.0) == 0.0

    # mark_delivered / mark_attempt_failed do NOT alter dispatches, observations, or streaks.
    roster.mark_delivered("opencode/a-free")
    roster.mark_attempt_failed("opencode/a-free")
    entry = json.loads(state_file.read_text(encoding="utf-8"))["opencode/a-free"]
    assert entry["dispatches"] == 2.0
    assert entry.get("observations", 0.0) == 0.0
    assert entry["deliveries"] == 1.0
    assert entry["failed_attempts"] == 1.0

    # containment_stops increments when orchestrator_busy=False, not when True;
    # observations increments by 1 when crossing containment threshold (>=5 dispatches, >=50%).
    for _ in range(4):
        roster.mark_dispatched("opencode/a-free")  # total 6 dispatches
    roster.mark_containment_stop("opencode/a-free", orchestrator_busy=True)
    assert roster.containment_stats("opencode/a-free") == (6, 0)
    for _ in range(3):
        roster.mark_containment_stop("opencode/a-free", orchestrator_busy=False)
    entry = json.loads(state_file.read_text(encoding="utf-8"))["opencode/a-free"]
    assert entry["dispatches"] == 6.0
    assert entry["containment_stops"] == 3.0
    assert entry["observations"] == 1.0

    # unavailable_streak & observations on mark_unavailable.
    r_unavail = Roster(models=["opencode/b-free"], state_file=state_file, now=t0)
    r_unavail.mark_unavailable("opencode/b-free", base_seconds=UNAVAILABLE_COOLDOWN)
    r_unavail.mark_unavailable("opencode/b-free", base_seconds=UNAVAILABLE_COOLDOWN)
    b_entry = json.loads(state_file.read_text(encoding="utf-8"))["opencode/b-free"]
    assert b_entry["unavailable_streak"] == 2.0
    assert b_entry["observations"] == 2.0

    # exhausted_streak & observations on mark_exhausted (immediate retry doubles streak).
    r_ex1 = Roster(models=["opencode/b-free"], state_file=state_file, now=t0)
    r_ex1.mark_exhausted("opencode/b-free")
    b_entry = json.loads(state_file.read_text(encoding="utf-8"))["opencode/b-free"]
    assert b_entry["exhausted_streak"] == 1.0
    assert b_entry["observations"] == 3.0

    r_ex2 = Roster(
        models=["opencode/b-free"],
        state_file=state_file,
        now=t0 + COOLDOWN_SECONDS + 10.0,
    )
    r_ex2.mark_exhausted("opencode/b-free")
    b_entry = json.loads(state_file.read_text(encoding="utf-8"))["opencode/b-free"]
    assert b_entry["exhausted_streak"] == 2.0
    assert b_entry["observations"] == 4.0

    # mark_responded resets streaks to 0 while leaving deliveries / failed_attempts intact.
    r_ex2.mark_delivered("opencode/b-free")
    r_ex2.mark_responded("opencode/b-free")
    b_entry = json.loads(state_file.read_text(encoding="utf-8"))["opencode/b-free"]
    assert b_entry["unavailable_streak"] == 0
    assert b_entry["exhausted_streak"] == 0
    assert b_entry["deliveries"] == 1.0
    assert "exhaustion_streak" not in b_entry


def test_recording_failure_never_stops_or_crashes_a_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Impl Detail 3: if roster counter persistence raises, the job still succeeds / returns."""
    monkeypatch.setattr(gates, "python_gates", _fast_python_gates)
    repo = _setup_repo_and_phase(tmp_path / "unwritable")
    ctrl = _controller(repo, ["opencode/a-free", "opencode/b-free"])

    def impl_and_approve(model: str, prompt: str, *, cwd: Path, **_: object) -> worker.Result:
        if model == "opencode/a-free":
            (cwd / "shared.txt").write_text("delivered despite broken meter\n", encoding="utf-8")
            return worker.Result(
                worker.Ending.COMPLETED, "REPORT\n- ok\n\nSTATUS\nready-for-review", model
            )
        return worker.Result(
            worker.Ending.COMPLETED, "VERDICT\n- APPROVED\n\nFINDINGS\n- none", model
        )

    ctrl.dispatch = impl_and_approve  # type: ignore[assignment]

    def broken_save(self: Roster, state: object) -> None:
        raise PermissionError("disk read-only")

    # Even if Roster._save raises during mark_delivered / mark_attempt_failed, neither
    # the roster helper nor the controller may crash the job.
    monkeypatch.setattr(roster_module.Roster, "mark_dispatched", lambda self, m: None)
    monkeypatch.setattr(roster_module.Roster, "mark_responded", lambda self, m: None)
    monkeypatch.setattr(roster_module.Roster, "_save", broken_save)

    # Direct calls to the roster meters must swallow save errors instead of raising.
    ctrl.roster.mark_delivered("opencode/a-free")
    ctrl.roster.mark_attempt_failed("opencode/a-free")

    task = ctrl.select()
    assert task is not None
    outcome = ctrl.run_job(task)
    assert outcome.state == "delivered", outcome.detail
    assert tasks.load_phase(ctrl.settings.phase_directory).tasks[0].status == "done"

    # Also verify failed_attempt path survives a broken meter.
    fail_repo = _setup_repo_and_phase(tmp_path / "unwritable-fail")
    fail_ctrl = _controller(fail_repo, ["opencode/a-free", "opencode/b-free"])
    fail_ctrl.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- nothing changed", model
    )
    fail_task = fail_ctrl.select()
    assert fail_task is not None
    fail_outcome = fail_ctrl.run_job(fail_task)
    assert fail_outcome.state == "attempt-failed"
    assert tasks.load_phase(fail_ctrl.settings.phase_directory).tasks[0].attempts == 1
