"""The opening check must not die on a character the console cannot encode.

On 2026-11-22 `shift_check.py` raised `UnicodeEncodeError` the moment it had
something to report: a Japanese Windows console gives Python a cp932 stdout,
cp932 has no em dash, and the stop record it was relaying contained one. The
shift's one opening command failed exactly when it mattered.
"""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
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
