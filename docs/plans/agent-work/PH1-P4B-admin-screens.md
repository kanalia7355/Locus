# PH1-P4B — Phase 4 remainder (2+3): admin project/storage settings and load display

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

Owner-approved Phase 4 remainder, priorities 2+3 of 5 (combined into ONE job to
avoid three-way conflicts in the shared admin page): **管理メニューのproject・保存先
設定** and **管理メニューの負荷表示**, per `docs/plans/PHASE_SPEC_RECONCILIATION.md`
Phase-4 row ("管理メニューのproject/保存先/負荷/保存削除画面不足").

Scope:
1. Project settings screen (admin): list existing projects, create a project,
   assign/remove members where the backend already supports it; every mutation
   follows existing role ceilings (system_admin), rate limits, and metadata-only
   audit conventions. If a needed backend endpoint does not exist, add it
   backend-side with the same conventions (atomic, audited, transactional).
2. 保存先 (storage destination) settings: the prototype's storage is local
   bounded ingestion; provide a read-only status/config view plus explicitly
   guarded configuration where a backend setting already exists. Do NOT invent
   new storage backends or credentials; anything that would enable external
   storage stays a marked placeholder (default deny, owner gate noted in UI
   text).
3. Load display: show current model-slot/chat-queue state (queue length, running
   job, per-user limits) from existing backend state; read-only endpoint if
   needed, admin-visible, no new enforcement.
4. UI baseline rules apply: sidebar/chat/admin layout per
   `docs/planning/UI_IMPLEMENTATION_BASELINE.md`, accessible names, IME handling,
   no new decorations; failed saves retain input; destructive actions are NOT in
   this job (priority 5 delete operations belong to a later job).

Constraints: read `frontend/src/App.tsx` admin sections, `backend/app/main.py`
admin endpoints, `backend/app/service.py` (users/projects/roles), and the
multiuser design doc first. Another job is changing the CHAT area of App.tsx
(running-question cancellation) — keep your UI changes confined to the admin
settings sections and new components to minimise conflicts.

QA (repeat until ALL green): full pytest, ruff, mypy, secret scan; frontend
lint/test/build + Playwright (npm ci --offline for worktree deps). Add backend
and frontend regressions for each new screen/endpoint (authz 403s, validation,
audit, state display).

Process: own worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-P4B-admin-screens -b loop/PH1-P4B-admin-screens origin/loop/local-development`; work ONLY inside it. Implement → adversarial self-review (authz, injection, audit accuracy) → QA → Conventional Commit (`feat(admin): project/storage settings and load display screens`) → push → wait branch CI → fix/re-push until ALL green (bounded). Append progress + SHA + CI evidence here.

Boundaries: never push to `main` or `loop/local-development`; no chat-area or
delete-operation work; no new external storage or egress; do not spawn subagents.

## Progress
- 2026-11-07: Read task brief, governance/product/architecture/bootstrap, UI baseline + image, multiuser design, reconciliation spec, GitHub workflow, existing admin App.tsx and backend service/routes. Confirmed bootstrap marker exists. Fetched origin and created isolated worktree `.loop/runtime/worktrees/PH1-P4B-admin-screens` on `loop/PH1-P4B-admin-screens` from `origin/loop/local-development`; audited the timed-out draft and fast-forward merged shared documentation commits without conflict.
- 2026-11-07: Implemented system-admin-only project list/create/member assign/remove APIs with validated IDs/names, request throttles, live-session checks for writes, transactional metadata-only audit, and atomic rollback; added read-only local storage status and model-slot/chat-queue status APIs. Added admin project, storage, and load screens; hooked navigation to admin sections without editing chat behavior; retained project form data on failed saves; external storage remains disabled with owner/security approval gate text. Added backend, component, and Playwright regressions.
- 2026-11-07: Prior-run QA notes (unverified on this relaunch): pytest 1119 passed/18 skipped; Ruff, mypy, secret scan, frontend lint/Vitest/build, Playwright passed. The relaunch repeated QA rather than relying on these notes.
- 2026-11-09: Relaunch sync fast-forwarded the worktree from `abdd95d` through `27c5a1d` to current `origin/loop/local-development` `167035d`, preserving the uncommitted draft. The slice-2a `AgentRegistry` and its `/api/admin/workspaces`, adapter, runner, and dispatch routes remain unchanged; P4B uses distinct `/api/admin/projects`, `/api/admin/storage`, and `/api/admin/load` paths. Merge inspection found a new concurrency: the integrated membership model permits multiple roles per user/project. Updated the P4B admin member assignment to add a role holding without erasing existing roles, render all held roles, and audit only a real change; added a regression proving the existing role is preserved. This is required to avoid weakening the newly integrated multi-role authorization design.
- 2026-11-09: Current worktree QA: full `C:/Users/hirot/Locus/.loop/runtime/qa-venv/Scripts/python.exe -m pytest tests -q --ignore=tests/e2e` passed (1140 passed, 18 skipped; skips are opt-in Docker, unavailable pinned native CLI, and Windows symlink capability). Ruff check passed; Ruff format check passed for `backend/app` and `tests`; mypy `backend/app` passed (9 source files); offline secret scan 0 findings. `frontend` npm lint passed, Vitest 59 passed/14 files, build passed, Playwright 11 passed including admin screens. Playwright used a worktree-local `.venv` junction to the shared QA venv required by `frontend/playwright.config.ts`; shared `.venv` was not modified. Initial post-merge test exposed a bad member assignment under new multi-role schema; fixed by retaining held roles, and reran admin+role regressions (13 passed) and all frontend/E2E checks successfully. Repo-wide Ruff format check also reports a pre-existing formatting issue in `docs/requirements/AUTONOMOUS_LOOP_SPEC.md`; it is untouched/out of scope.
- 2026-11-09: Commit `09fb971bbb0e60100829dc087b3641e15e77359d` (`feat(admin): project/storage settings and load display screens`) pushed to `loop/PH1-P4B-admin-screens`. Initial branch-head CI: Prototype quality run `42434489491` passed; Loop engine checks run `42434489525` passed on all four matrix jobs. Conventional Commit push check `42434489497` failed before title inspection because this was a first branch Push with zero `before` OID; the workflow fell back to `origin/main`, yielding its documented oversized-range assessment error (not a bad feature commit). Synced the latest `origin/loop/local-development` documentation/PH2-C commits via a clean merge `6797e528` (`chore: sync the latest integration base`), retaining the feature commit and avoiding history rewrites. On evidence commit `db6cd9e539467bc9488fd856bf0c0974d97f42d2`, the pushed branch CI rerun was all green: PR title convention `42435158166`, Prototype quality `42435158176`, Loop engine checks `42435158113` (four jobs). A subsequent ledger-only commit `a37859cca7b1ec9eaba27014edeb49387c3113b5` records the final evidence; its CI rerun is also all green: title convention `42435900859`, Prototype quality `42435900727`, Loop engine checks `42435900790` (four jobs). No production code changed after the verified feature commit.
