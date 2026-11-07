## Aggregate independent review request (orchestrator action)

Please commission a fresh-context, read-only review of the integrated Phase-1 auth
aggregate and the PH1-G reconciliation/status evidence. Review recovery, web user
creation and account disable/session revocation across these integration commits:
`1056021` (recovery), `b7adb42` + `ed11f73` (account toggle/CI repair), and
`2610b70` (web provisioning). Verify authorization, one-time credential secrecy,
recovery replay/expiry behavior, session invalidation, audit metadata and the
users-page integration. Specifically independently assess the reproduced race:
a stale system-admin Principal obtained before account disable can still complete
`POST /api/admin/users` afterward. Check that MFA and production TLS/session
deployment stay unresolved and that no Phase-1 completion claim is made.

Evidence for commissioning: source branches `loop/PH1-recovery` (`bd9f2cf`,
branch CI green at `93d1633`), `loop/PH1-account-toggle` (`a31d570`, local
pytest 1098 passed/18 skipped, frontend 49, Playwright 10; integrated CI green
at `c28a280`), and `loop/PH1-web-provisioning` (`a355efb`, branch CI green at
`76ba39a`; pytest 1094 passed/18 skipped, frontend 49, Playwright 10). The
consolidation worktree's cross-job QA passed at base `fa6e7c5`: pytest 1113
passed/18 skipped, Ruff/format, mypy (7 source files), secret scan (0), frontend
lint/build, Vitest 52, and Playwright 10. PH1-G exact-HEAD CI is pending push;
record its final result below. This is a request, not an independent review or
Phase-1 completion decision.

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

## Progress

- Setup: created the assigned worktree `C:/Users/hirot/Locus/.loop/runtime/worktrees/PH1-G-consolidation` on `loop/PH1-G-consolidation`, based on `origin/loop/local-development` at `fa6e7c5`. The base includes the PH1-A, PH1-B and PH1-D integration commits. `.bootstrap/complete.json` exists, so no bootstrap action was needed. The main checkout has pre-existing unrelated modifications; I have not changed them and will work only in this worktree.
- Requirements review: read the complete PH1-G brief, AGENTS.md, governance/product/architecture/bootstrap docs, GitHub workflow, all three auth-slice task files, Phase reconciliation/status docs, loop Goal/requirements/architecture/acceptance/decisions and the loop skill. Independent review is explicitly prohibited for this task; none will be spawned.
- Cross-job Python regression (worktree): `C:/Users/hirot/Locus/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/e2e` passed: **1113 passed, 18 skipped** in 493.30s. Skips were the documented real-Docker/native CLI opt-ins and Windows symlink capability checks. No test-level collision occurred and no test edits were needed; subsequent cross-slice self-review reproduced the unresolved in-flight admin-authorization race recorded below.
- Static/security QA passed from the worktree: Ruff check (all checks passed), Ruff format check (117 files already formatted), `mypy backend/app` (7 source files, no issues), and `scripts/secret_scan.py` (0 findings). The worktree lacked frontend dependencies; `npm ci --offline` installed the locked 252-package set (0 vulnerabilities), without network access.
- Frontend QA passed from the worktree: `npm run lint`; `npm test` (**52 tests across 13 files passed**); and `npm run build` (TypeScript + Vite production build succeeded). `npx playwright test` passed (**10 Chromium tests**). The first browser launch lacked Playwright's expected worktree `.venv` path; after provisioning a temporary local Python-path helper (removed after test), the configured API/frontend servers and all browser cases passed.
- Documentation implementation: updated the Phase-1 reconciliation row with the three integrated features, source/integration branches and commits, per-slice QA evidence, and the aggregate regression counts. MFA and production TLS/session deployment stay explicitly unresolved; no completion claim was added. Updated the Phase-1 status summary and added the dated evidence section. Added the aggregate independent-review commissioning request at the top of this task brief; the request is not itself a review.
- Cross-slice semantic finding (unresolved; no feature fix is authorized in PH1-G): the API obtains an admin `Principal` in `backend/app/main.py`'s `Actor` dependency before `POST /api/admin/users` calls `Service.provision_web_user`. That service checks the cached `system_admin` flag but does not revalidate the session in its creation transaction. Reproduction in a temporary SQLite DB: capture admin A's principal, disable A via admin B (A's token then returns 401), and call `provision_web_user` with the captured principal; the user is nevertheless created. Impact: a delayed in-flight admin provisioning request can mutate state after disable/session revocation. Recommend revalidating the live session inside the provisioning transaction and adding a race regression test; no feature/test changes made under this docs-and-test-only assignment. The independent reviewer should verify severity and remediation.
- Adversarial self-review: confirmed the A/B/D integration commits are ancestors of the task base; inspected recovery, disable/session purge, provisioning service and the composed users page; cross-checked branch SHA/test/CI evidence against the completed task files and orchestrator integration log. Verified the docs preserve MFA/TLS/session deployment as unresolved and do not claim Phase 1 completion. `git diff --check` passed, post-edit secret scan remains at 0 findings, and changes are limited to the reconciliation, status and PH1-G task files. The stale-Principal race above is the sole cross-slice finding; it remains intentionally unfixed under this task's feature-code boundary.
- Commit: created the required Conventional Commit `docs(plans): consolidate phase-1 auth-slice evidence` at `ba9d5f00c68236ac4ef6b1585ea176f62e0bdaf0`. Branch CI is pending the authorized push; no main or `loop/local-development` push was made.
