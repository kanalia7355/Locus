"""Tests for main-checkout containment classification in jobloop.controller."""

from pathlib import Path

from jobloop import worker
from tests.test_jobloop import controller_for, phase_with_task


def test_main_checkout_untracked_litter_is_swept_and_recorded(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free"])
    ws = tmp_path / "ws"
    ws.mkdir()
    controller.workspace = lambda _task: ws  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED,
        "REPORT\n- done\n\nSTATUS\n- needs-owner-decision: which retry budget applies?",
        model,
    )

    seen = {"n": 0}

    def dirt(_path: Path) -> str:
        seen["n"] += 1
        return "" if seen["n"] == 1 else "?? REPORT -\n"

    discarded: list[tuple[Path, set[str]]] = []
    controller.dirt = dirt  # type: ignore[assignment]
    controller.discard = lambda tree, names: discarded.append((tree, set(names)))  # type: ignore[assignment]

    outcome = controller.run_job(controller.select())
    assert outcome.state != "escalated" or "outside its workspace" not in outcome.detail
    assert discarded == [(controller.settings.repository, {"REPORT"})]

    body = (controller.settings.phase_directory / "tasks" / "T-JOB-1.md").read_text(
        encoding="utf-8"
    )
    assert "MAIN CHECKOUT LITTER REMOVED" in body
    assert "model=a-free" in body
    assert "1 untracked file(s)" in body
    assert "REPORT" in body


def test_main_checkout_tracked_change_still_stops_job(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free"])
    ws = tmp_path / "ws"
    ws.mkdir()
    controller.workspace = lambda _task: ws  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED, "REPORT\n- done", model
    )

    seen = {"n": 0}

    def dirt(_path: Path) -> str:
        seen["n"] += 1
        if seen["n"] == 1:
            return ""
        return " M scripts/shift_check.py abc123\n M tests/test_jobloop.py def456\n"

    discarded: list[tuple[Path, set[str]]] = []
    controller.dirt = dirt  # type: ignore[assignment]
    controller.discard = lambda tree, names: discarded.append((tree, set(names)))  # type: ignore[assignment]

    outcome = controller.run_job(controller.select())
    assert outcome.state == "escalated"
    assert "worker wrote outside its workspace" in outcome.detail
    assert discarded == []


def test_main_checkout_litter_not_swept_when_orchestrator_busy(tmp_path: Path) -> None:
    phase_with_task(tmp_path)
    controller = controller_for(tmp_path, ["a-free"])
    ws = tmp_path / "ws"
    ws.mkdir()
    controller.workspace = lambda _task: ws  # type: ignore[assignment]
    controller.operator_busy = lambda: True  # type: ignore[assignment]
    controller.dispatch = lambda model, prompt, **_: worker.Result(  # type: ignore[assignment]
        worker.Ending.COMPLETED,
        "REPORT\n- done\n\nSTATUS\n- needs-owner-decision: which retry budget applies?",
        model,
    )

    seen = {"n": 0}

    def dirt(_path: Path) -> str:
        seen["n"] += 1
        return "" if seen["n"] == 1 else "?? REPORT -\n"

    discarded: list[tuple[Path, set[str]]] = []
    controller.dirt = dirt  # type: ignore[assignment]
    controller.discard = lambda tree, names: discarded.append((tree, set(names)))  # type: ignore[assignment]

    outcome = controller.run_job(controller.select())
    assert outcome.state == "escalated"
    assert "outside its workspace" not in outcome.detail
    assert discarded == []

    body = (controller.settings.phase_directory / "tasks" / "T-JOB-1.md").read_text(
        encoding="utf-8"
    )
    assert "CONTAINMENT UNVERIFIED" in body
    assert "MAIN CHECKOUT LITTER REMOVED" not in body
