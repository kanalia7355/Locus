# PH1-G — Consolidation of the Phase-1 auth-slice jobs

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

Goal: consolidate the three completed Phase-1 auth-slice jobs (PH1-A recovery,
PH1-B account toggle, PH1-D web provisioning), which are now all integrated into
`loop/local-development` (HEAD 1af18e7 or later), and prepare the Phase-1
reconciliation update for independent review.

Setup: create your own worktree: `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-G-consolidation -b loop/PH1-G-consolidation origin/loop/local-development` (reuse if it exists). Work ONLY inside it.

Deliverables (docs + tests only; feature work belongs to the integrated branches):
1. Update `docs/plans/PHASE_SPEC_RECONCILIATION.md` Phase-1 row: move
   回復 (recovery), Web利用者追加 (creation), 停止操作 (disable) from 未解決差分
   to 照合・既存実装 with evidence (branch, commit, test counts). Keep 本番TLS/
   session配備 and MFA as unresolved. Do NOT declare Phase 1 complete — the
   completion criteria (independent review of the aggregate + all-CI-green at
   the exact HEAD) are recorded, not met.
2. Update `docs/plans/PHASE_STATUS.md` with a dated section describing the three
   integrated features and their evidence (same restraint: no completion claim).
3. Cross-job regression: run the full local QA in your worktree (`.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/e2e`, ruff check/format, mypy backend/app, secret scan; frontend `npm run lint`, `npm test`, `npm run build`; `npx playwright test`) and record exact counts. Fix ONLY test-level conflicts between the integrated slices (e.g. duplicate fixture/route collisions) — any semantic conflict gets recorded as a finding instead of being silently resolved.
4. Write a short aggregate review request at the top of
   `docs/plans/agent-work/PH1-G-consolidation.md` (scope, commits, evidence) so
   the orchestrator can commission the independent review of the auth-slice aggregate.

Process: read AGENTS.md, governance docs, the three task files
(PH1-A-recovery.md, PH1-B-account-toggle.md, PH1-D-web-provisioning.md), and the
reconciliation doc first. Then implement, self-review, run QA, Conventional
Commit (`docs(plans): consolidate phase-1 auth-slice evidence`), push
`loop/PH1-G-consolidation`, wait for branch CI, fix and re-push until ALL checks
green (bounded; record if blocked). Record progress + SHA + CI evidence here.

Boundaries: never push to `main` or `loop/local-development`; no feature code
changes; do not weaken tests; do not declare Phase 1 complete; do not spawn
subagents.
