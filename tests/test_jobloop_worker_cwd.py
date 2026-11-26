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


def _write_session_db(db_path: Path, rows: list[tuple[str, str]]) -> None:
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE session_v2 (id TEXT PRIMARY KEY, directory TEXT)")
        conn.executemany("INSERT INTO session_v2 (id, directory) VALUES (?, ?)", rows)
        conn.commit()
    finally:
        conn.close()


def test_session_id_extracts_fact5_error_event_and_returns_none_when_absent() -> None:
    # AC1: Fact 5 single-line error event yields sessionID; missing/invalid yields None.
    fact5 = (
        '{"type":"error","timestamp":1795698255764,'
        '"sessionID":"ses_de82ffa30ffeNr2JmK06tLv8R3",'
        '"error":{"type":"provider.no-route","message":"Model unavailable: nonexistent/probe"}}'
    )
    assert worker.session_id(fact5) == "ses_de82ffa30ffeNr2JmK06tLv8R3"

    nested = '{"type":"session.created","session":{"id":"ses_nested_123"}}'
    assert worker.session_id(nested) == "ses_nested_123"

    assert worker.session_id('{"type":"text","part":{"type":"text","text":"hello"}}') is None
    assert worker.session_id("not json at all\nstill not json") is None
    assert worker.session_id("") is None


def test_session_db_directory_opens_read_only_and_handles_four_failure_cases(
    tmp_path: Path,
) -> None:
    # AC2: read-only connection + 4 failure modes (missing DB, locked DB, missing column,
    # missing row) all return None without raising.
    import sqlite3

    # 1. Missing DB: returns None and does NOT create the file on disk (proves mode=ro).
    missing_db = tmp_path / "does_not_exist.db"
    assert worker.session_db_directory("ses_1", db_path=missing_db) is None
    assert not missing_db.exists(), "a read-only open must never create a missing DB file"

    # Valid DB lookup + explicit proof that _open_readonly_sqlite opens a read-only connection.
    valid_db = tmp_path / "opencode.db"
    _write_session_db(valid_db, [("ses_ok", "C:/repo/workspace")])
    assert worker.session_db_directory("ses_ok", db_path=valid_db) == "C:/repo/workspace"

    ro_conn = worker._open_readonly_sqlite(valid_db)
    try:
        try:
            ro_conn.execute("INSERT INTO session_v2 (id, directory) VALUES ('ses_w', 'C:/x')")
        except sqlite3.OperationalError as exc:
            assert "readonly" in str(exc).lower()
        else:
            raise AssertionError("connection allowed a write; expected read-only SQLite URI")
    finally:
        ro_conn.close()

    # 2. Missing row: returns None without raising.
    assert worker.session_db_directory("ses_no_such_row", db_path=valid_db) is None

    # 3. Missing column (or schema changed): returns None without raising.
    schema_changed_db = tmp_path / "schema_changed.db"
    conn = sqlite3.connect(schema_changed_db)
    try:
        conn.execute("CREATE TABLE session_v2 (id TEXT PRIMARY KEY, title TEXT)")
        conn.execute("INSERT INTO session_v2 (id, title) VALUES ('ses_ok', 'moved schema')")
        conn.commit()
    finally:
        conn.close()
    assert worker.session_db_directory("ses_ok", db_path=schema_changed_db) is None

    # 4. Locked DB: exclusive writer holds lock -> returns None without raising.
    locked_db = tmp_path / "locked.db"
    _write_session_db(locked_db, [("ses_locked", "C:/repo/workspace")])
    locker = sqlite3.connect(locked_db, isolation_level=None)
    try:
        locker.execute("PRAGMA locking_mode=EXCLUSIVE")
        locker.execute("BEGIN EXCLUSIVE")
        locker.execute("INSERT INTO session_v2 (id, directory) VALUES ('ses_hold', 'C:/hold')")
        assert worker.session_db_directory("ses_locked", db_path=locked_db, timeout=0.05) is None
    finally:
        locker.rollback()
        locker.close()


def test_worker_records_both_db_directory_and_passed_cwd_without_stopping_on_mismatch(
    tmp_path: Path,
) -> None:
    # AC3 & AC5: both session_v2.directory and passed cwd are recorded in worker output
    # (both on COMPLETED and on failure, and end-to-end into the controller's task record),
    # and a DB mismatch does NOT stop/misroute the job in this ticket.
    from jobloop import tasks
    from jobloop.controller import Controller, Settings
    from jobloop.roster import Roster

    db_path = tmp_path / "opencode.db"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    other_checkout = tmp_path / "other-checkout"
    other_checkout.mkdir()
    _write_session_db(
        db_path,
        [
            ("ses_done_mismatch", str(other_checkout)),
            ("ses_fail_mismatch", str(other_checkout)),
        ],
    )

    # (a) Completed session with mismatched DB directory still completes (does not stop!)
    # and carries both DB directory and passed cwd in the worker's recorded output.
    def completed_with_sid(*_args, **_kwargs):
        return _completed(
            '{"type":"text","sessionID":"ses_done_mismatch",'
            '"part":{"type":"text","text":"REPORT\\n- implemented\\n\\nSTATUS\\nready-for-review"}}'
        )

    ok = worker.run(
        "opencode/a-free",
        "do it",
        cwd=workspace,
        timeout=5,
        executable="opencode",
        runner=completed_with_sid,
        db_path=db_path,
    )
    assert ok.ending is worker.Ending.COMPLETED, (
        "DB directory mismatch alone must not stop or misroute the session in T-PH9-423"
    )
    assert ok.session_id == "ses_done_mismatch"
    assert ok.db_directory == str(other_checkout)
    assert ok.cwd == str(workspace)
    assert str(other_checkout) in ok.text and str(workspace) in ok.text
    assert not ok.text.rstrip().endswith(str(workspace)), (
        "diagnostic must not break trailing STATUS line conventions"
    )
    assert ok.text.rstrip().endswith("ready-for-review")

    # Verify end-to-end that Controller.run_job writes both directories into the task record,
    # and does NOT false-trigger APPROVAL on a CHANGES_REQUIRED reviewer reply.
    repo = tmp_path / "repo"
    phase_dir = repo / "progress" / "phase-test" / "tasks"
    phase_dir.mkdir(parents=True)
    task_file = phase_dir / "T-JOB-423.md"
    task_file.write_text(
        "---\n"
        "id: T-JOB-423\n"
        "phase: phase-test\n"
        "status: todo\n"
        "assignee: unassigned\n"
        "model: -\n"
        "weight: light\n"
        "updated: 2026-11-26T21:00:00+09:00\n"
        "attempts: 0\n"
        "allowed_paths: allowed.py\n"
        'test_cmd: python -c "print(1)"\n'
        "---\n\n"
        "# Task `T-JOB-423`: probe\n",
        encoding="utf-8",
    )
    import sys

    from jobloop.controller import APPROVAL, git

    git(repo, "init", "-b", "loop/local-development")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    (repo / ".gitignore").write_text(".jobloop/\n", encoding="utf-8")
    for target_dir in ("backend", "tests", "scripts", "jobloop"):
        (repo / target_dir).mkdir(exist_ok=True)
        (repo / target_dir / "__init__.py").write_text("", encoding="utf-8")
    (repo / "allowed.py").write_text("x = 0\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "seed")

    ctrl = Controller(
        Settings(repository=repo, phase="phase-test", python=sys.executable, push=False),
        Roster(
            models=["opencode/a-free", "opencode/b-free"],
            state_file=repo / ".jobloop" / "roster.json",
            now=1000.0,
        ),
        clock=lambda: 0.0,
    )
    calls = {"n": 0}

    def fake_dispatch(model: str, prompt: str, *, cwd: Path, timeout: float) -> worker.Result:
        calls["n"] += 1
        if calls["n"] == 1:
            (cwd / "allowed.py").write_text("x = 1\n", encoding="utf-8")
            return worker.run(
                model,
                prompt,
                cwd=cwd,
                timeout=timeout,
                executable="opencode",
                runner=completed_with_sid,
                db_path=db_path,
            )
        rev_runner = lambda *_a, **_k: _completed(  # noqa: E731
            '{"type":"text","sessionID":"ses_done_mismatch",'
            '"part":{"type":"text","text":"VERDICT\\n- CHANGES_REQUIRED\\n\\nFINDINGS\\n- fix"}}'
        )
        rev = worker.run(
            model,
            prompt,
            cwd=cwd,
            timeout=timeout,
            executable="opencode",
            runner=rev_runner,
            db_path=db_path,
        )
        assert not APPROVAL.search(rev.text)
        return rev

    ctrl.dispatch = fake_dispatch  # type: ignore[assignment]
    task = tasks.load_phase(ctrl.settings.phase_directory).tasks[0]
    outcome = ctrl.run_job(task)
    assert outcome.state == "changes-required"
    recorded_md = task_file.read_text(encoding="utf-8")
    expected_ws = str(ctrl.settings.workspace_root / "T-JOB-423")
    assert str(other_checkout) in recorded_md, "session_v2.directory must be in task record"
    assert expected_ws in recorded_md, "passed cwd must be in task record"

    # (b) Failed session (Fact 5 error event) also records both DB directory and passed cwd.
    def failed_with_sid(*_args, **_kwargs):
        return _completed(
            '{"type":"error","timestamp":1,"sessionID":"ses_fail_mismatch",'
            '"error":{"type":"provider.no-route","message":"Model unavailable"}}',
            returncode=1,
        )

    failed = worker.run(
        "opencode/a-free",
        "do it",
        cwd=workspace,
        timeout=5,
        executable="opencode",
        runner=failed_with_sid,
        db_path=db_path,
    )
    assert failed.ending is worker.Ending.UNAVAILABLE
    assert failed.session_id == "ses_fail_mismatch"
    assert failed.db_directory == str(other_checkout)
    assert failed.cwd == str(workspace)
    joined_errors = "\n".join(failed.errors)
    assert str(other_checkout) in joined_errors and str(workspace) in joined_errors


def test_agy_and_ollama_paths_succeed_when_opencode_db_is_absent(tmp_path: Path) -> None:
    # AC4 & AC5: agy and ollama routes work cleanly on a machine with no opencode.db,
    # and T-PH9-422 symbols remain intact.
    missing_db = tmp_path / "nonexistent" / "opencode.db"
    workspace = tmp_path / "ws"
    workspace.mkdir()

    assert hasattr(worker.Ending, "MISROUTED")
    assert callable(worker.normalize_session_path)
    assert callable(worker.reported_directory)

    # 1. agy route when opencode.db does not exist
    agy_stdout = (
        '{"event":"result","result":'
        '{"status":"SUCCESS","response":"REPORT\\nok","usage":{"total_tokens":10}}}'
    )
    agy_res = worker.run(
        "agy/gemini-4-carbon-low",
        "do it",
        cwd=workspace,
        timeout=5,
        executable="agy",
        runner=lambda *a, **k: subprocess.CompletedProcess(a[0], 0, agy_stdout, ""),
        db_path=missing_db,
    )
    assert agy_res.ending is worker.Ending.COMPLETED
    assert agy_res.text == "REPORT\nok"
    assert not missing_db.exists()

    # 2. ollama route (via opencode CLI) when opencode.db does not exist
    ollama_stdout = (
        '{"type":"text","sessionID":"ses_ollama_1",'
        '"part":{"type":"text","text":"REPORT\\nollama ok"}}'
    )
    ollama_res = worker.run(
        "ollama/gemma3:4b",
        "do it",
        cwd=workspace,
        timeout=5,
        executable="opencode",
        runner=lambda *_a, **_k: _completed(ollama_stdout),
        db_path=missing_db,
    )
    assert ollama_res.ending is worker.Ending.COMPLETED
    assert "REPORT\nollama ok" in ollama_res.text
    assert ollama_res.session_id == "ses_ollama_1"
    assert ollama_res.db_directory is None
    assert ollama_res.cwd == str(workspace)
    assert not missing_db.exists()
