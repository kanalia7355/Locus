# ADR 0005 — Evidence-driven project Development Loop

Status: implemented and locally tested; live execution remains blocked.

The outer loop runs inside the existing Controller's single OS lock, serial
scheduler, explicit runtime window, task/attempt/review caps and process
boundary. There is no second implementation agent or standalone unbounded
service. Initial assessment and each observed merge trigger evaluation.

Main is fetched without force into `refs/remotes/origin/main`; the user's
checked-out main is not reset or overwritten. Dependency worktrees use that
latest integration ref. A detached evaluation worktree must stay at the
observed SHA and have no tracked/untracked modifications. Verify the expected
merge is an ancestor. Recheck remote main after assessment/QA and before the
completion gate; changing main invalidates terminal state and forces a new
bounded assessment before selecting more work.

`goal_evaluator` invokes a fresh read-only structured assessment with stable
criterion IDs derived from original acceptance bullets. `gap_analyzer` rejects
missing/altered criteria, stale SHA/spec hash and ungrounded findings. Every gap
must cite an exact inspected tracked-file anchor, relevant criterion, concrete
reproduction, benefit, allowed paths and acceptance. The model may propose
changes; it cannot replace Goal/design/acceptance or approve decisions.

`improvement_planner` atomically appends tasks and evidence in SQLite, validates
the complete dependency DAG and keeps a unique stable finding identity across
rewording. Only untouched, unapproved work may have scheduling fields updated.
No existing attempted scope, counter or exhausted task is reset. Scope changes
or risk escalation on attempted/approved tasks create human Decisions. A
persistent risk floor never decreases and still governs Controller preapproval
and merge eligibility after a decision is resolved. Security, scope and
architecture findings require preapproval.

Planning deduplication is separate from assessment freshness: failed same-head
QA can recover. Latest receipts and append-only observation history preserve
each assessment. `progress_evaluator` measures criterion/gap improvements and
mandatory-QA recovery, not commit count. Repeated/no-progress assessments halt
after the configured bound. `completion_gate` requires current-head/spec-bound
required checks, independent review, every criterion met, no gaps, no unfinished
tasks and no unresolved decisions. Fully proven completion takes precedence
over historical stagnation.

`loop start 2h` starts an explicit bounded run. `loop resume 2h` grants a new
window to the same run, retaining its task/cycle counters; plain resume keeps
its deadline. Task attempts, approvals and observations survive both. Windows
do not exceed the configured six-hour maximum. Idle/sleeping PCs do not execute
work; a later explicit window does not imply work happened while powered off.

Production factory continues to use `UnprovenBoundary`: no setting can fabricate
unverified tool/credential/MCP/network isolation. Native gh merge remains
blocked without the existing protected, trusted-review and atomic-base gates.
The E2E uses actual temporary Git/worktrees/commits/main updates and Python QA,
but synthetic Codex, GitHub PR/Checks/protection and merge authority. Those
fixtures are not configurable production executors or remote review publishers.
