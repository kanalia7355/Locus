"""The secret gate must pass the named synthetic fixtures and nothing else.

A test that proves an API key never reaches an audit record has to plant a
key-shaped literal. On 2026-11-22 the gate failed `T-AIC-005` for exactly that,
so the fixtures below are allowed by exact value. The dangerous direction is the
one pinned hardest: a literal that merely *looks* synthetic must still fail,
because the moment this gate accepts a pattern it stops being a gate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scripts" / "secret_scan.py"


def planted(value: str) -> str:
    """One line of synthetic source with `value` assigned to a secret-ish name.

    Assembled at run time, and the values below are assembled too, so no line of
    *this* file is itself a key-shaped literal. The first version of this test
    put the whole literal in the source and the repository-wide scan then
    flagged the test that proves the scan works — a self-inflicted finding, and
    the gate was right both times.
    """
    return "KEY" + " = " + '"' + value + '"' + "\n"


def scan(directory: Path, name: str, body: str) -> subprocess.CompletedProcess[str]:
    """Run the real entry point against one file in its own root."""
    (directory / name).write_text(body, encoding="utf-8")
    return subprocess.run(  # noqa: S603 — fixed argument vector, no shell
        [sys.executable, str(SCANNER), "--root", str(directory), name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )


ALLOWED = "sk-" + "synthetic-{}-" + "not-a-real-key"


@pytest.mark.parametrize("index", ["01", "02", "03", "04"])
def test_the_named_synthetic_key_passes(tmp_path: Path, index: str) -> None:
    result = scan(tmp_path, "test_credentials.py", planted(ALLOWED.format(index)))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "literal",
    [
        "sk-" + "live-" + "SUPERSECRET",  # what T-AIC-005 actually planted
        "sk-" + "test-" + "injected-key",  # and its second value
        ALLOWED.format("05"),  # one past the closed set
        ALLOWED.format("01") + "-x",  # not the exact value
    ],
)
def test_anything_outside_the_closed_set_still_fails(tmp_path: Path, literal: str) -> None:
    """The waiver is by exact value, so looking synthetic is not enough.

    `sk-synthetic-05-...` and the suffixed variant are here because an anchorless
    or wildcarded rule would accept both, and that is the shape of mistake that
    turns this gate into decoration.
    """
    result = scan(tmp_path, "test_credentials.py", f'SECRET = "{literal}"\n')
    assert result.returncode != 0, (
        f"{literal!r} was waved through: " + result.stdout + result.stderr
    )
