"""Turn a stalled queue into work the loop can do itself.

`selfrepair` undoes the loop's own messes. This module is the step above it:
when the queue stops and the cause is the loop rather than a judgement, it says
so in one place, and files the repair as a job — with the same gates, the same
independent review and the same attempt limit as any other.

The need is measured, not imagined. Between 2026-11-18 and 2026-11-21 the queue
died whole four times. Every single cause was in the loop:

| what stopped it | jobs lost | hours idle |
|---|---|---|
| orphaned worker held the output pipe | 1 | 2 |
| provider outage counted as failed attempts | 5 | 18 |
| an approval written `**APPROVED**` was unreadable | 1 | 18 |
| a conflicted merge left in the checkout | 11 | 7 |

Each time a person read the records, named the signature and wrote the fix. The
reading and the naming are mechanical; only the fix is judgement. This module
does the mechanical part and hands the judgement to a job.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path

HEALTH_PHASE = "phase-9-loop-health"

# Stops the loop is supposed to handle without a person, and the day the handling
# landed. The date is the whole point: a stop that is older than its repair is
# just a job waiting to be restarted, while one that is newer means the repair
# does not work — and those two need opposite responses. Without the date this
# module called ten jobs a regression on the morning their fix was written.
HANDLED = {
    "out-of-scope change": ("2026-11-21", "scratch files are swept by `gates.litter`"),
    "reviewer modified the worktree": (
        "2026-11-19",
        "a reviewer that only wrote a file is rotated to the next model",
    ),
    "integration branch is dirty": (
        "2026-11-21",
        "every phase's records count as the loop's own bookkeeping",
    ),
}

# Stops that are a person's call by design. Counting them is useful; filing a
# repair job for them is not — there is nothing to repair.
JUDGEMENT = {
    "worker stopped for a decision",
    "review cycle limit reached",
    "no independent reviewer available",
    "worker wrote outside its workspace",
    # The abort is automatic; whether the job redoes its work on the moved
    # branch is not. Listing this as "handled" made every correct escalation
    # read as a regression of its own fix on 2026-11-22.
    "the merge conflicted",
    "the merge broke the loop",
    # Three honest attempts that did not meet the acceptance criteria is the
    # escalation working, not a defect. This sat in HANDLED against the
    # 2026-11-20 outage repair, so on 2026-11-22 `T-PH6-125` — whose three
    # attempts were its own, the last of them reviewed and found hollow — was
    # announced as a REGRESSION of that repair. The repair is about *why* an
    # attempt was spent, which this signature does not record; the reasons do.
    "attempt limit reached",
    # The same budget, reached through a review rather than a failed gate. The
    # controller tells them apart now (it used to call both "review cycle limit
    # reached"), so both spellings have to be listed here.
    "attempt limit reached after a review",
}

# Extra guidance for a judgement whose signature hides more than one cause.
NOTE = {
    "attempt limit reached after a review": (
        "the reviewer's findings are the evidence here, not the gates"
    ),
    "attempt limit reached": (
        "read the three reasons before ruling: the same supplier error three times "
        "means the outage repair of 2026-11-20 regressed, not that the job failed"
    ),
}


@dataclass
class Finding:
    """One stop signature, and every job it is holding."""

    category: str
    jobs: list[str] = field(default_factory=list)
    phases: set[str] = field(default_factory=set)
    evidence: str = ""
    latest: str = ""

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.category.lower()).strip("-")

    @property
    def handled(self) -> str:
        return HANDLED.get(self.category, ("", ""))[1]

    @property
    def judgement(self) -> bool:
        return self.category in JUDGEMENT

    @property
    def stale(self) -> bool:
        """Every stop here is older than the repair for it: restart, do not re-fix."""
        since = HANDLED.get(self.category, ("", ""))[0]
        return bool(since) and bool(self.latest) and self.latest[:10] <= since

    @property
    def regression(self) -> bool:
        """Handled, and it happened anyway. The repair is incomplete."""
        return bool(self.handled) and not self.stale

    @property
    def repairable(self) -> bool:
        """Worth filing as a job: the loop's own behaviour, and more than once.

        One job stopped by a new signature may be that job's own fault. Two is a
        pattern, and a pattern in the loop's behaviour is the loop's to fix.
        A stop that predates its own repair is neither — it is waiting to run.
        """
        return not self.judgement and not self.stale and len(self.jobs) >= 2


def identifier(finding: Finding) -> str:
    """A stable id for a signature.

    Derived from the slug and not from `hash()`, which is salted per process:
    the same stop has to get the same ticket id on every run, or a second run
    files a duplicate of the first.
    """
    return f"T-PH9-{zlib.crc32(finding.slug.encode('utf-8')) % 900 + 100}"


HEADING = re.compile(r"(\S+)\s+—\s+(.+?)\s+\((\d{4}-\d{2}-\d{2}T[\d:+]+)\)")


def unanswered(decisions: Path) -> list[tuple[str, str, str, str]]:
    """`(job, category, when, context)` for each request with no `**Answer**` yet."""
    if not decisions.is_file():
        return []
    text = decisions.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    found: list[tuple[str, str, str, str]] = []
    for entry in re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]:
        if "**Question**" not in entry or "**Answer**" in entry:
            continue
        head, _, body = entry.partition("\n")
        named = HEADING.match(head.strip())
        if not named:
            continue
        found.append((named.group(1), named.group(2).strip(), named.group(3), body.strip()))
    return found


def survey(progress: Path, phases: list[str]) -> list[Finding]:
    """Group every open stop across the phases by signature, worst first."""
    grouped: dict[str, Finding] = {}
    for phase in phases:
        for job, category, when, context in unanswered(progress / phase / "OWNER_DECISIONS.md"):
            finding = grouped.setdefault(category, Finding(category=category))
            if job not in finding.jobs:
                finding.jobs.append(job)
            finding.phases.add(phase)
            finding.latest = max(finding.latest, when)
            if not finding.evidence:
                finding.evidence = context[:1200]
    return sorted(grouped.values(), key=lambda finding: (-len(finding.jobs), finding.category))


def report(findings: list[Finding]) -> str:
    """What a person would have had to work out by reading the records."""
    if not findings:
        return "no open stop: nothing is waiting on a decision"
    lines = []
    for finding in findings:
        where = ", ".join(sorted(finding.phases))
        lines.append(f"{len(finding.jobs):>2} job(s)  {finding.category}  [{where}]")
        lines.append(f"           {', '.join(finding.jobs)}  last {finding.latest[:16]}")
        if finding.stale:
            lines.append(
                f"           ALREADY FIXED — {finding.handled}; these only need restarting"
            )
        elif finding.regression:
            lines.append(f"           REGRESSION — {finding.handled}, and it happened anyway")
        elif finding.judgement:
            lines.append("           a person's call by design, not a loop defect")
            if finding.category in NOTE:
                lines.append(f"           {NOTE[finding.category]}")
        elif finding.repairable:
            lines.append("           repairable: no handling exists and it has stopped 2 or more")
        else:
            lines.append("           one job only: watch for a second before calling it a pattern")
    return "\n".join(lines)


def ticket(finding: Finding, *, now: str) -> str:
    """A loop-repair job: the evidence, and criteria that cannot be met by hiding it."""
    return f"""---
id: {identifier(finding)}
phase: {HEALTH_PHASE}
status: todo
assignee: unassigned
model: -
weight: medium
updated: {now}
attempts: 0
allowed_paths: jobloop/, tests/test_jobloop.py, docs/JOBLOOP.md
test_cmd: python -m pytest tests/test_jobloop.py tests/test_selfrepair.py -q
---

# Task `{identifier(finding)}`: ループが自分で止まる原因を直す — `{finding.category}`

## TASK DEFINITION (Filed by the loop itself, {now})

- **なぜこの票があるか**: `{finding.category}` が **{len(finding.jobs)} 件のジョブ**を
  同時に止めている（{", ".join(finding.jobs)}）。
  1 件なら、そのジョブ固有の問題かもしれない。2 件以上は**ループの振る舞いの型**であり、
  型はループ自身が直すべきもの。この票は人ではなくループが起票した。
{
        f"- **これは再発である**: この型は既に対処済みのはずだった — {finding.handled}。"
        "対処が不完全だったということなので、**同じ対処を足すのではなく、"
        "なぜ取りこぼしたのかを先に突き止めること**。"
        if finding.regression
        else ""
    }
- **観測された証跡（最初の 1 件）**:

```
{finding.evidence[:900]}
```

- **やること**:
  1. `progress/*/OWNER_DECISIONS.md` の該当する全エントリと、各ジョブの
     task ファイルを読み、**止まった瞬間に何が起きていたか**を特定する。
  2. ループ側の原因を直す。**ジョブ側の受入条件・許可パス・テストには触らない。**
  3. 直したことを**検査で固定する**（下の受入条件 1・2）。
- **やってはいけないこと**:
  - 受入条件を緩める、テストを消す・skip する、`allowed_paths` を広げる。
  - 「人に聞く」で終わらせる。この票は、人に聞かずに済むようにするためにある。
  - 症状だけを抑える（例: 失敗を無視する、例外を飲む）。
    **止まったこと自体は正しい挙動である場合がある** — その場合は
    「止まるべきだが、その止まり方が人を必要とする」という点を直すこと。

## Acceptance Criteria

1. **この欠陥があると落ちる検査**が `tests/test_jobloop.py` にあり、
   修正を外すと実際に落ちることを確認して報告すること（確認手順も書くこと）。
2. **隣の正しい挙動が止まり続けることを示す検査**を同じ場所に置くこと。
   自己修復が危ないのは、止まるべきものを通してしまうとき。
   例: 作業ファイルを掃除する修正なら、**本物の範囲違反は従来どおり止まる**ことを示す。
3. `python -m pytest tests/test_jobloop.py tests/test_selfrepair.py -q` が PASS。
   `ruff check jobloop tests` / `ruff format --check jobloop tests` / `mypy jobloop` が PASS。
4. 変更は許可パス内に収まる。`docs/JOBLOOP.md` に挙動の変更を 1 行で書くこと。
5. 既存の検査を 1 つも削除・緩和していないこと。

## REPORT

- Implemented by:
- Changed Files:
- Summary:

## TEST

- Commands run:
- Results:

## REVIEW

- Reviewer:
- Findings:
"""


def reopen(progress: Path, findings: list[Finding], *, now: str) -> list[str]:
    """Restart the jobs whose stop has already been repaired.

    This is not the loop overruling a judgement. It says one thing only: *the
    cause of this stop was a defect in the loop, and the defect is fixed since*,
    so the job gets another go. The decision of what counts as a repaired defect
    is in `HANDLED`, which a person writes.

    One attempt is given back — the one the defect consumed — and never more
    than that. The answer written here is what keeps it bounded: a second pass
    finds the entry answered and leaves it alone.
    """
    restarted: list[str] = []
    for finding in findings:
        if not finding.stale:
            continue
        said = (
            f"\n**Answer** ({now[:10]}, jobloop diagnose): この停止は**ループ側の欠陥**が原因で、"
            f"その欠陥は既に直っている — {finding.handled}。"
            f"停止の時刻（{finding.latest[:16]}）は修正より前なので、"
            "判断を覆したのではなく、**原因が無くなったので再開する**という記録である。"
            "欠陥が消費した試行 1 回分だけを戻す（それ以上は戻さない）。"
            "受入条件・許可パスは変更していない。\n"
        )
        for phase in sorted(finding.phases):
            answered = _answer(progress / phase / "OWNER_DECISIONS.md", finding, said)
            for job in answered:
                if _restart(progress / phase / "tasks" / f"{job}.md"):
                    restarted.append(job)
    return restarted


def _answer(decisions: Path, finding: Finding, said: str) -> list[str]:
    """Write `said` under every open entry of this signature; return the jobs named."""
    text = decisions.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    chunks = re.split(r"^(##\s+.*)$", text, flags=re.MULTILINE)
    rebuilt = [chunks[0]]
    touched: list[str] = []
    for head, body in zip(chunks[1::2], chunks[2::2], strict=True):
        named = HEADING.match(head[2:].strip())
        if named and named.group(2).strip() == finding.category and "**Answer**" not in body:
            body = body.rstrip("\n") + "\n" + said
            touched.append(named.group(1))
        rebuilt.append(head + "\n")
        rebuilt.append(body)
    if touched:
        decisions.write_bytes("".join(rebuilt).replace("\n", "\r\n").encode("utf-8"))
    return touched


def _restart(task_file: Path) -> bool:
    """Take one job out of `blocked`, giving back a single attempt."""
    if not task_file.is_file():
        return False
    text = task_file.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    if not re.search(r"^status: blocked$", text, re.MULTILINE):
        return False
    spent = re.search(r"^attempts: (\d+)$", text, re.MULTILINE)
    text = re.sub(r"^status: blocked$", "status: todo", text, count=1, flags=re.MULTILINE)
    if spent and int(spent.group(1)) > 0:
        text = re.sub(
            r"^attempts: \d+$",
            f"attempts: {int(spent.group(1)) - 1}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    task_file.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    return True


def file_tickets(progress: Path, findings: list[Finding], *, now: str) -> list[Path]:
    """Write a repair job for each repairable signature that has no job yet.

    One job per signature, ever: a second ticket for the same category would be
    the loop asking twice, and the first one already carries the evidence.
    """
    directory = progress / HEALTH_PHASE / "tasks"
    directory.mkdir(parents=True, exist_ok=True)
    existing = "\n".join(
        path.read_bytes().decode("utf-8", errors="replace") for path in directory.glob("*.md")
    )
    written: list[Path] = []
    for finding in findings:
        if not finding.repairable or finding.category in existing:
            continue
        body = ticket(finding, now=now)
        name = re.search(r"^id:\s*(\S+)", body, re.MULTILINE)
        path = directory / f"{name.group(1) if name else finding.slug}.md"
        if path.exists():
            continue
        path.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))
        written.append(path)
    return written
