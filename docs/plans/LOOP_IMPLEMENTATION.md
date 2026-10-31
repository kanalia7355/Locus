# Autonomous loop implementation ledger

Latest environment and execution evidence is in
[ADR0006](../architecture/ADR-0006-source-only-runtime.md) and the
[runtime ledger](../reviews/2026-10-31-unattended-runtime.md). Earlier phase
entries below are historical snapshots, including their initial no-remote and
unavailable-executor statements. PR-only operation is the current authorization;
no merge or full acceptance conclusion supersedes the outstanding guarantees.

Source: user-supplied "Codex Autonomous Loop Engineering — Implementation Specification", received2026-10-31. Scope is a new independent controller alongside the existing app. No research-app replacement, live remote mutation, live worker or background daemon is implied by implementation.

| Phase | Acceptance evidence | Status |
|---|---|---|
| 1 Foundation | Strict config/schema/state transitions, cycle rejection, SQLite transactions, project lock, redacted events, CLI init/status/doctor | Implemented;8 scoped tests and independent review passed |
| 2 Planning | Goal-bound validated plan import, immutable source acceptance, atomic DAG/metadata/decisions, seven validated scoped skills | Local import implemented/reviewed; live model planning blocked by missing isolation |
| 3 Execution | Documented CLI adapter, bounded process trees/output, attempts<=3, deterministic verification | Local/mock tests and review passed; live executor boundary unimplemented/unproven, therefore incomplete |
| 4 Review/approval | Fresh read-only review adapter, structured findings, hash-bound human CLI decisions, independent task continuation | Controller/approval logic tested/reviewed; actual CLI review transport remains blocked |
| 5 GitHub | Actual isolated fixture worktrees, guarded commit/PR reconciliation, current head/base CI/review evidence, safe merge predicate | Local/mock implementation reviewed; remote writes not exercised; atomic base-binding unavailable, so real automatic merge is disabled/incomplete |
| 6 Recovery/E2E | Conservative uncertainty queue, no blind replay, pause/resume/stop/report, mocked CLI E2E, Windows Job owner-death test, CI files | Local evidence implemented; final verification/review recorded below; live restart/capability and remote integration acceptance remain incomplete |

Design decisions and external integration blockers: ADR0003. Runtime state belongs in `.loop/runtime/` and is excluded from Git. Phase results, audit findings and commands will be appended as executed, never inferred from AI summaries.

## Verification and environment

- Engine local suites currently39 tests, including actual temporary Git worktree/index/commit checks and Windows child-lifetime tests. Python3.11 syntax/types and current Windows types are checked separately; actual local interpreter is3.13.2. Linux/Python3.11 remote runtime CI is prepared, not claimed executed.
- Codex0.144.5 and gh2.95.0 are installed and authenticated according to metadata-only status probes. Root repository still has no committed baseline/default integration branch or remote. No live worker, remote push, PR or merge was executed.
- Correctly formed synthetic `codex sandbox` diagnostic returned exit2. This is not isolation proof. `UnprovenBoundary` intentionally refuses every live worker/verifier/planner context, including after a human decision. No unrestricted fallback exists.
- `gh` expected-head matching cannot atomically match the PR base reference; the real adapter always returns atomic_base_binding=false. The merge predicate can be tested with complete synthetic evidence, but that is not a real successful merge.
- Reports use ownership receipts. They preserve preexisting/user-edited content detected before replacement; concurrent manual edits can still race. Windows lifetime proof covers successful Job assignment, not the suspended creation-to-assignment crash window. POSIX lifetime tests are explicitly unavailable/skipped.
- The implementation is not marked complete against section18 of the supplied specification. Missing live isolation and remote atomic enforcement are engineering blockers, not approvals that can be granted away.

## Final local result

All8 engine verification commands exited0 (including optional advisory checks). The full application verifier also passed all12 commands:61 Python tests,4 UI unit tests and5 Chromium E2E tests. Seven skills validated successfully. Editable package/console entrypoint0.1.0 was installed and smoke-tested. Setup PowerShell syntax was parsed successfully; its full installation workflow was not rerun. All independent scoped audits passed after at most the permitted two fix cycles; see the audit record for exact limits.

Three unresolved gates are persisted in the local SQLite approval queue: isolated executor design/proof, exact GitHub repository/base/publication scope, and atomic merge-base enforcement. These are also reflected in `.loop/decisions.md`. State is stopped; no background controller, live model worker, PR/push or merge was launched. There is no `.loop/complete.json` or claim that all live acceptance criteria passed.

Current local implementation branch: `feat/autonomous-loop-engine`, still without a baseline commit or remote. Older research-bootstrap branch references describe the earlier inspection, not the new feature branch. No user work was committed automatically.
