"""The opening check must not die on a character the console cannot encode.

On 2026-11-22 `shift_check.py` raised `UnicodeEncodeError` the moment it had
something to report: a Japanese Windows console gives Python a cp932 stdout,
cp932 has no em dash, and the stop record it was relaying contained one. The
shift's one opening command failed exactly when it mattered.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
EM_DASH_LINE = "T-PH6-125 — attempt limit reached"


def load() -> object:
    """Import `scripts/shift_check.py`, which is a script and not a package."""
    spec = importlib.util.spec_from_file_location(
        "shift_check", ROOT / "scripts" / "shift_check.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cp932_stream() -> io.TextIOWrapper:
    """A stdout with the encoding a Japanese Windows console actually hands over."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp932", errors="strict", newline="")


def test_the_console_encoding_really_cannot_carry_an_em_dash() -> None:
    """The premise of the test below, pinned so it cannot quietly stop being true.

    Without this, a Python that silently started tolerating the character would
    turn the next test into one that passes for the wrong reason.
    """
    with pytest.raises(UnicodeEncodeError):
        cp932_stream().write(EM_DASH_LINE)


def test_say_survives_a_console_that_cannot_encode_the_text() -> None:
    stream = cp932_stream()
    load().say(EM_DASH_LINE, stream=stream)  # type: ignore[attr-defined]
    stream.flush()
    written = stream.buffer.getvalue().decode("cp932")  # type: ignore[attr-defined]
    # The line still reads; only the character the console lacks is substituted.
    assert written.startswith("T-PH6-125 ")
    assert written.rstrip().endswith("attempt limit reached")


def test_every_report_line_goes_through_say() -> None:
    """A bare `print` anywhere in the reporting path reopens the same hole.

    The helper is only a fix if nothing bypasses it, and the crash happened in
    one of ten call sites.
    """
    source = (ROOT / "scripts" / "shift_check.py").read_text(encoding="utf-8")
    assert "print(" not in source


def load_supervisor() -> object:
    spec = importlib.util.spec_from_file_location(
        "supervise_loop", ROOT / "scripts" / "supervise_loop.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_cycle_line_does_not_repeat_what_the_log_already_has() -> None:
    """`Controller.note` writes its own `run ::` lines to the same file.

    Folding the child's last three lines in verbatim repeated them: on
    2026-11-22 the cycle line for `T-STC-001` carried its `no-model` outcome
    three times over, which is also why a churn count read `x6` for three
    events.
    """
    tail_of = load_supervisor().tail_of  # type: ignore[attr-defined]
    output = "\n".join(
        [
            "2026-11-22T19:22:28+09:00 run :: T-STC-001: dispatching (medium)",
            "2026-11-22T19:22:28+09:00 run :: T-STC-001: no-model - every model is resting",
            "T-STC-001: no-model - every eligible free model is on cooldown",
            "pushed loop/local-development",
        ]
    )
    shown = tail_of(output)
    assert "run ::" not in shown, shown
    assert "pushed loop/local-development" in shown
    assert shown.count("no-model") == 1, shown
    assert tail_of("   \n\n") == "(no output)"


def test_stream_returns_the_output_and_the_exit_code(
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The tee has to keep both halves: what the console sees and what the log gets.

    `capture_output=True` kept the per-job lines out of the console for a whole
    cycle, and teaching `Controller.note` to print did not help on its own
    because the print went into the pipe. This is the plumbing that was missing.
    """
    module = load_supervisor()
    code, output = module.stream(  # type: ignore[attr-defined]
        [sys.executable, "-c", "print('first'); print('second'); raise SystemExit(3)"]
    )
    assert code == 3
    assert output.splitlines() == ["first", "second"]
    assert "first" in capfd.readouterr().out, "the console is the point"


def test_a_repeat_that_has_stopped_is_reported_but_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hour window cannot tell that a cause was repaired inside it.

    `T-PH6-104 nothing-to-resume x4` kept failing this check for twenty-eight
    minutes after the controller fix that ended it on 2026-11-22 — the same trap
    `diagnose` avoids with repair dates. The count and the time still print; only
    the verdict changes.
    """
    check = load()
    monkeypatch.setattr(check, "ROOT", tmp_path)  # type: ignore[arg-type]
    state = tmp_path / ".jobloop"
    state.mkdir()
    now = datetime.now(JST)

    def log(when: datetime, times: int) -> None:
        state.joinpath("supervisor.log").write_text(
            "".join(
                f"{(when).isoformat()} run :: T-A-1: nothing-to-resume - no changes\n"
                for _ in range(times)
            ),
            encoding="utf-8",
        )

    # Still happening: a failure, and it says when.
    log(now - timedelta(minutes=2), 3)
    fresh = check.churn()  # type: ignore[attr-defined]
    assert fresh.startswith("FAIL"), fresh
    assert "x3" in fresh and "last " in fresh

    # Stopped half an hour ago: still reported, no longer a failure.
    log(now - timedelta(minutes=30), 3)
    old = check.churn()  # type: ignore[attr-defined]
    assert old.startswith("ok"), old
    assert "x3" in old, old


def test_the_quota_line_never_claims_a_ready_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The roster is the union of every model ever seen, not what the CLI offers.

    The first version of this line said `2 ready` while `jobloop status` said
    `available models: none`, because two models the CLI had stopped offering
    were still in the file with expired cooldowns. Only `Roster.available`
    intersects the two, and this script cannot call it without invoking the CLI.
    """
    check = load()
    monkeypatch.setattr(check, "ROOT", tmp_path)  # type: ignore[arg-type]
    state = tmp_path / ".jobloop"
    state.mkdir()
    now = time.time()
    state.joinpath("roster.json").write_text(
        json.dumps(
            {
                "gone/from-the-cli-a": {"cooldown_until": now - 9999},
                "gone/from-the-cli-b": {"cooldown_until": now - 9999},
                "opencode/resting-free": {"cooldown_until": now + 600},
            }
        ),
        encoding="utf-8",
    )
    line = check.quota()  # type: ignore[attr-defined]
    assert "1 of 3 recorded models resting" in line, line
    assert "ready" not in line, "a ready count from this file cannot be true"
    assert "soonest back in 10 min" in line, line


def test_a_quota_outage_is_not_counted_as_work() -> None:
    """`worked` decided whether to back off, and `no-model` was reading as work.

    From 19:00 to 21:25 on 2026-11-22 the supervisor ran 47 full-rate cycles
    while every free model was resting, never reached its idle branch, and wrote
    4,197 `pushed` lines into the log — the noise that had made a real churn
    signal hard to find earlier that evening.
    """
    module = load_supervisor()
    did_work = module.did_work  # type: ignore[attr-defined]

    assert not did_work(
        "T-PH7-205: no-model - every eligible free model is on cooldown\n"
        "pushed loop/local-development"
    )
    assert not did_work("-: idle - no actionable job is left; pushed loop/local-development")
    assert not did_work(
        "T-PH6-104: no-reviewer - every free model is on cooldown\npushed loop/local-development"
    )
    assert not did_work("")
    # Announcements are not outcomes: these two lines are the whole of a cycle
    # that reached the reviewer check and stopped, and the first version of this
    # counted the `resuming` line as work.
    assert not did_work(
        "\n".join(
            [
                "2026-11-22T21:26:16+09:00 run :: T-PH6-104: resuming",
                "2026-11-22T21:26:16+09:00 run :: T-PH6-104: no-reviewer - every model is resting",
                "pushed loop/local-development",
            ]
        )
    )
    assert not did_work(
        "\n".join(
            [
                "T-STC-001: dispatching (medium)",
                "T-STC-001: rotated - opencode/x-free is out of usage",
            ]
        )
    )
    # A real outcome, however it ended, is work.
    assert did_work("T-PH6-125: delivered - e53dfd6 merged into loop/local-development")
    assert did_work("T-PH6-127: escalated - worker stopped for a decision")
    assert did_work("T-PH6-104: gates-failed - scope: outside allowed_paths")


def test_the_idle_wait_grows_but_stays_bounded() -> None:
    module = load_supervisor()
    backoff = module.backoff  # type: ignore[attr-defined]

    assert backoff(120.0, 0) == 120.0
    assert backoff(120.0, 1) == 240.0
    assert backoff(120.0, 3) == 960.0
    # Capped, so a cooldown that ends sooner than expected is not waited out.
    assert backoff(120.0, 10) == 1200.0
    assert backoff(120.0, 99) == 1200.0
