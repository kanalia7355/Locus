"""The loop reading its own stops.

The danger here is the mirror of `selfrepair`'s: not that the diagnosis misses a
defect, but that it restarts a job whose stop was a real judgement, or files a
repair job for something no repair can fix. Both would read, afterwards, as
though the loop had worked.
"""

from pathlib import Path

from jobloop import diagnose

ENTRY = """## {job} — {category} ({when})

**Question**: something stopped.

**Context**

{context}
"""


def decisions(directory: Path, *entries: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "OWNER_DECISIONS.md"
    body = "# Owner decisions requested by the job loop\n\n" + "\n".join(entries)
    path.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))
    return path


def job_file(directory: Path, job: str, *, status: str = "blocked", attempts: int = 2) -> Path:
    tasks = directory / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    path = tasks / f"{job}.md"
    path.write_bytes(
        (
            f"---\nid: {job}\nphase: phase-x\nstatus: {status}\nattempts: {attempts}\n"
            "allowed_paths: backend/app/service.py\ntest_cmd: python -m pytest -q\n---\n\n# body\n"
        )
        .replace("\n", "\r\n")
        .encode("utf-8")
    )
    return path


def test_an_answered_stop_is_not_counted_again(tmp_path: Path) -> None:
    answered = (
        ENTRY.format(
            job="T-A-1",
            category="out-of-scope change",
            when="2026-11-30T10:00:00+09:00",
            context="x",
        )
        + "\n**Answer** (2026-11-30, orchestrator): ruled.\n"
    )
    decisions(tmp_path / "phase-x", answered)
    assert diagnose.survey(tmp_path, ["phase-x"]) == []


def test_a_signature_older_than_its_repair_is_restarted_not_re_fixed(tmp_path: Path) -> None:
    # Ten jobs were sitting on stops whose cause had been fixed hours earlier.
    # Calling those a regression would have filed a job to fix what was already
    # fixed; leaving them blocked kept the queue dead. Neither is right.
    phase = tmp_path / "phase-x"
    decisions(
        phase,
        ENTRY.format(
            job="T-A-1",
            category="integration branch is dirty",
            when="2026-11-21T04:00:00+09:00",
            context="commit=abc",
        ),
        ENTRY.format(
            job="T-A-2",
            category="integration branch is dirty",
            when="2026-11-21T01:00:00+09:00",
            context="commit=def",
        ),
    )
    job_file(phase, "T-A-1", attempts=2)
    job_file(phase, "T-A-2", attempts=0)

    findings = diagnose.survey(tmp_path, ["phase-x"])
    assert [finding.category for finding in findings] == ["integration branch is dirty"]
    assert findings[0].stale and not findings[0].regression and not findings[0].repairable

    restarted = diagnose.reopen(tmp_path, findings, now="2026-11-21T12:00:00+09:00")
    assert sorted(restarted) == ["T-A-1", "T-A-2"]
    first = (phase / "tasks" / "T-A-1.md").read_bytes().decode("utf-8")
    assert "status: todo" in first and "attempts: 1" in first, "one attempt back, not all of them"
    second = (phase / "tasks" / "T-A-2.md").read_bytes().decode("utf-8")
    assert "attempts: 0" in second, "nothing to give back, and never below zero"
    # The record says why, and that keeps it bounded: a second pass finds the
    # entry answered and does nothing.
    text = (phase / "OWNER_DECISIONS.md").read_bytes().decode("utf-8")
    assert "原因が無くなったので再開する" in text
    assert diagnose.reopen(tmp_path, diagnose.survey(tmp_path, ["phase-x"]), now="x") == []


def test_a_stop_newer_than_its_repair_is_a_regression_and_gets_a_job(tmp_path: Path) -> None:
    phase = tmp_path / "phase-x"
    decisions(
        phase,
        *[
            ENTRY.format(
                job=f"T-A-{index}",
                category="integration branch is dirty",
                when=f"2026-12-0{index}T04:00:00+09:00",
                context="commit=abc",
            )
            for index in (1, 2)
        ],
    )
    findings = diagnose.survey(tmp_path, ["phase-x"])
    assert findings[0].regression and findings[0].repairable
    assert not findings[0].stale

    written = diagnose.file_tickets(tmp_path, findings, now="2026-12-03T00:00:00+09:00")
    assert len(written) == 1
    body = written[0].read_bytes().decode("utf-8")
    assert "これは再発である" in body, "a recurrence has to be told apart from a first sighting"
    assert "status: todo" in body and "allowed_paths: jobloop/" in body
    # The criteria a self-repair must not be able to dodge.
    assert "修正を外すと実際に落ちる" in body
    assert "本物の範囲違反は従来どおり止まる" in body
    # Filed once, ever: a second pass must not ask the same question twice.
    assert diagnose.file_tickets(tmp_path, findings, now="2026-12-04T00:00:00+09:00") == []


def test_a_judgement_is_never_restarted_or_turned_into_a_repair_job(tmp_path: Path) -> None:
    # The dangerous direction. A reviewer that still requires changes, a worker
    # that asked a real question — no repair exists for those, and restarting
    # them would bury the question under another attempt.
    phase = tmp_path / "phase-x"
    decisions(
        phase,
        *[
            ENTRY.format(
                job=f"T-A-{index}",
                category=category,
                when="2026-12-05T04:00:00+09:00",
                context="see the review",
            )
            for index, category in enumerate(
                ("review cycle limit reached", "worker stopped for a decision"), start=1
            )
        ],
    )
    job_file(phase, "T-A-1")
    job_file(phase, "T-A-2")
    findings = diagnose.survey(tmp_path, ["phase-x"])
    assert all(finding.judgement for finding in findings)
    assert not any(finding.repairable for finding in findings)
    assert diagnose.reopen(tmp_path, findings, now="2026-12-05T12:00:00+09:00") == []
    assert diagnose.file_tickets(tmp_path, findings, now="2026-12-05T12:00:00+09:00") == []
    assert "status: blocked" in (phase / "tasks" / "T-A-1.md").read_bytes().decode("utf-8")


def test_one_job_alone_is_not_yet_a_pattern(tmp_path: Path) -> None:
    phase = tmp_path / "phase-x"
    decisions(
        phase,
        ENTRY.format(
            job="T-A-1",
            category="something nobody has seen before",
            when="2026-12-06T04:00:00+09:00",
            context="a brand new failure",
        ),
    )
    findings = diagnose.survey(tmp_path, ["phase-x"])
    assert not findings[0].repairable, "one job may simply be that job's own problem"
    assert diagnose.file_tickets(tmp_path, findings, now="2026-12-06T12:00:00+09:00") == []
    assert "something nobody has seen before" in diagnose.report(findings)


def test_the_same_signature_across_phases_is_one_finding(tmp_path: Path) -> None:
    for phase in ("phase-a", "phase-b"):
        decisions(
            tmp_path / phase,
            ENTRY.format(
                job=f"T-{phase}-1",
                category="a shared failure",
                when="2026-12-07T04:00:00+09:00",
                context="same cause",
            ),
        )
    findings = diagnose.survey(tmp_path, ["phase-a", "phase-b"])
    assert len(findings) == 1
    assert findings[0].phases == {"phase-a", "phase-b"}
    assert findings[0].repairable, "two phases hitting it is exactly what makes it the loop's"


def test_a_ticket_id_is_the_same_on_every_run() -> None:
    # A salted `hash()` gave the same stop a new id each process, so a rerun
    # filed a duplicate of the job it had already filed.
    one = diagnose.Finding(category="a stable name", jobs=["T-A-1", "T-A-2"])
    again = diagnose.Finding(category="a stable name", jobs=["T-A-1", "T-A-2"])
    assert diagnose.identifier(one) == diagnose.identifier(again)
    assert diagnose.identifier(one) != diagnose.identifier(
        diagnose.Finding(category="a different name")
    )
