"""Regression checks for opencode session working-directory containment.

The worker already passes `--standalone`; this file pins that flag in place and
proves the defensive path-comparison that stops a session routed to the wrong
directory from being treated as a fair attempt.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from jobloop import worker


def _completed(
    stdout: str, returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["opencode"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_same_directory_normalises_case_and_separators(tmp_path: Path) -> None:
    # AC4: (a) case differs, (b) separators differ, (c) truly different.
    base = tmp_path / "workspace"
    base.mkdir()
    as_upper = str(base).upper()
    as_mixed_slash = str(base).replace("\\", "/")

    assert worker._same_directory(str(base), as_upper), (
        "(a) case-only difference must be the same place"
    )
    assert worker._same_directory(str(base), as_mixed_slash), (
        "(b) separator difference must be the same place"
    )

    elsewhere = tmp_path / "other-checkout"
    elsewhere.mkdir()
    assert not worker._same_directory(str(base), str(elsewhere)), (
        "(c) a different directory must be stopped"
    )


def test_reported_directory_reads_defensive_event_shapes() -> None:
    # The orchestrator note names session.created/updated/init/init and
    # directory/cwd/workdir as the shapes to look for defensively.
    stream = "\n".join(
        [
            '{"type":"session.created","session":{"id":"s1","directory":"C:\\\\repo\\\\ws"}}',
            '{"type":"text","part":{"type":"text","text":"hello"}}',
        ]
    )
    assert worker.reported_directory(stream) == r"C:\repo\ws"

    nested = '{"type":"init","properties":{"cwd":"C:/repo/ws"}}'
    assert worker.reported_directory(nested) == "C:/repo/ws"

    assert worker.reported_directory('{"type":"error","error":"boom"}') is None


def test_misrouted_session_returns_misrouted_without_consuming_attempt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    main_checkout = tmp_path / "main-checkout"
    main_checkout.mkdir()

    def routed_elsewhere(*args, **kwargs):
        assert "--standalone" in args[0], "the isolation flag must still be passed"
        return _completed(
            '{"type":"session.created","session":{"directory":"'
            + str(main_checkout).replace("\\", "\\\\")
            + '"}}\n{"type":"text","part":{"type":"text","text":"REPORT\\nok"}}'
        )

    result = worker.run(
        "a-free",
        "do it",
        cwd=workspace,
        timeout=5,
        executable="opencode",
        runner=routed_elsewhere,
    )

    assert result.ending is worker.Ending.MISROUTED
    assert result.rotate is True, "environment misroute must not consume the job's attempt"
    assert "wrong working directory" in result.why_rotate
    assert any(
        str(main_checkout) in err or "session reported working directory" in err
        for err in result.errors
    )


def test_same_location_with_different_spelling_is_not_misrouted(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    reported = str(workspace).replace("\\", "/").lower()

    def same_place(*_args, **_kwargs):
        return _completed(
            '{"type":"session.init","directory":"' + reported + '"}\n'
            '{"type":"text","part":{"type":"text","text":"REPORT\\nok"}}'
        )

    result = worker.run(
        "a-free",
        "do it",
        cwd=workspace,
        timeout=5,
        executable="opencode",
        runner=same_place,
    )

    assert result.ending is worker.Ending.COMPLETED
    assert "REPORT" in result.text


def test_no_reported_directory_falls_through_normally(tmp_path: Path) -> None:
    # AC1: absence is reported/handled honestly - we cannot detect, so we do not
    # guess. A normal completed stream with no directory must still complete.
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def no_directory(*_args, **_kwargs):
        return _completed('{"type":"text","part":{"type":"text","text":"REPORT\\nok"}}')

    result = worker.run(
        "a-free",
        "do it",
        cwd=workspace,
        timeout=5,
        executable="opencode",
        runner=no_directory,
    )

    assert result.ending is worker.Ending.COMPLETED


def test_standalone_flag_is_passed_to_opencode(tmp_path: Path) -> None:
    seen: list[list[str]] = []

    def capture(*args, **kwargs):
        seen.append(list(args[0]))
        return _completed('{"type":"text","part":{"type":"text","text":"ok"}}')

    result = worker.run(
        "a-free", "do it", cwd=tmp_path, timeout=5, executable="opencode", runner=capture
    )

    assert result.ending is worker.Ending.COMPLETED
    assert seen, "runner was not called"
    assert "--standalone" in seen[0], seen[0]
