# PH2-E — Web management remainder + combined-roles UI (implementation)

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

Phase-2 job per `docs/plans/PHASE2_JOB_BREAKDOWN.md` (PH2-E) plus the UI
follow-up recorded when PH2-B was integrated. The integrated state:
P4B delivered the admin project/storage/load screens (AdminSettings.tsx);
PH2-B delivered backend concurrent role holdings (兼任) + explicit deny with
role-holding APIs but NO UI; PH2-D (running in another worktree) is adding
delegation BACKEND endpoints — do NOT touch delegation; the web UI for
delegation comes later.

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH2-E-web-mgmt -b loop/PH2-E-web-mgmt origin/loop/local-development` (reuse if it exists). Work ONLY inside it.

Scope:
1. Survey what web-management deltas remain vs the reconciliation Phase-2 row
   ("Web所属/project管理") after P4B — e.g. membership role assignment/holding
   display, org-level views if the backend models them, and any Phase-2 web
   operation still missing. Record the delta list first.
2. UI for combined role holdings + deny state: extend the existing role/members
   admin surfaces (P4B's AdminSettings and/or the existing role editor) to
   display a user's multiple held roles (union result) and deny entries;
   additive only, per `docs/planning/UI_IMPLEMENTATION_BASELINE.md`
   (accessible names, no new decorations, IME handling, failed saves retain
   input). Assigning multiple roles / adding a deny entry must respect the
   backend's ceilings and audit (backend APIs already exist from PH2-B — use
   them; if an endpoint is genuinely missing for a UI flow, add it with the
   existing conventions: transactional audit, live recheck in-transaction).
3. Regressions: frontend tests for the new displays/flows (multiple roles shown
   as union, deny displayed and overriding, ceilings enforced server-side and
   surfaced as errors), plus all existing tests unchanged.
4. Delegation UI is OUT of scope (PH2-D lands first; delegation UI is a later
   job).

ENVIRONMENT NOTE: `.loop/runtime/qa-venv` may have been cleaned — recreate if
missing (Python313: `"C:/Users/hirot/AppData/Local/Programs/Python/Python313/python.exe" -m venv C:/Users/hirot/Locus/.loop/runtime/qa-venv` then `pip install -e ".[dev]" -r backend/requirements.lock`). NEVER touch the shared `.venv`. Worktree `.venv` junction to the qa-venv for the playwright e2e server.

QA (repeat until ALL green): full pytest (tests -q --ignore=tests/e2e), ruff
check + format --check, mypy backend/app, secret scan; frontend npm run lint /
npm test / npm run build / npx playwright test (npm ci --offline if deps
missing).

Process: survey → implement → adversarial self-review (authz, escalation, audit)
→ QA → Conventional Commit (`feat(admin): combined role holdings and deny state management UI`) →
push `loop/PH2-E-web-mgmt` → wait branch CI → fix/re-push until ALL green
(bounded). Append progress + SHA + CI evidence to this file's ## Progress.
Branch deleted after integration.

Boundaries: never push to `main` or `loop/local-development`; no delegation
backend work (PH2-D's scope); no weakening of tests; no subagents.

## Progress
- 2026-11-09: Surveyed the post-P4B baseline. P4B supplies admin project list/create and member assign/remove; its project list already renders `member.roles` (concurrent holdings) and its assignment API is additive. The project role editor supports custom role creation/update, but no UI shows project-member effective permission unions or explicit membership-deny entries. PH2-B already provides scoped per-username role-state, add/remove-role, and set-denials APIs. P4B's existing project roster endpoint is sufficient; extend its read-only response to include effective permissions and denials, while keeping all UI mutations on PH2-B APIs. No standalone organization model/view exists (`projects.org_id` is only a string field), so org-level management would invent scope and is not a remaining web operation. Other web operations found in the Phase-2 row (project/membership and custom roles) are present.
- 2026-11-09: Implemented P4B project roster rendering for effective union permissions and membership-level explicit denials. Added multiple-role assignment/removal and deny add/remove controls using PH2-B APIs; the existing admin project endpoint now reports roles, denies, and computed effective access. System admins can administer roles/denies in projects without personal membership, while added holdings remain bounded to NON_ADMIN permission templates, system_admin is rejected, disabled targets are rejected, and project existence is checked. Existing `manage_members` authorization remains required for non-system admins. User list copy now directs admins to project membership management. Added backend regressions for denied-overrides-union presentation/state and out-of-membership system-admin operations; Vitest covers union + deny display, API paths, failed-save input retention and server-ceiling error display; Playwright exercises assigning multiple roles, effective permissions, deny overriding, and membership removal.
- 2026-11-09: Verification: full backend `pytest tests -q --ignore=tests/e2e` — 1146 passed, 18 skipped (opt-in Docker/native CLI/Windows symlink cases); Ruff check passed; scoped Ruff format check (`backend/app tests scripts`) passed (126 files); mypy `backend/app` passed (9 files); offline secret scan 0 findings. Frontend lint passed; Vitest 64 passed (14 files); production build passed; Playwright Chromium 12 passed. Full-repository Ruff format check still reports only the pre-existing unrelated formatting issue in `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315`; it was left untouched. Playwright used the worktree `.venv` symlink to `.loop/runtime/qa-venv`; shared `.venv` was not touched.
- 2026-11-09: Final diff self-review: role-removal is disabled for a sole held role (use the existing explicit membership-removal confirmation instead); role addition is disabled when the selected role is already held; denials are selected from known permission names, and both add/remove preserve server state on failure. Mutations stay on the existing PH2-B role-holding and denials routes. Updated user-management copy to remove the stale CLI-only membership direction. All tests remain unchanged except additive regressions; no delegation UI/backend work was performed.
- 2026-11-09: Conventional implementation commit `e4819d9a50e938e81c4206b222fa0542eb2b7781` (`feat(admin): combined role holdings and deny state management UI`) pushed to `loop/PH2-E-web-mgmt`. Branch CI on this exact SHA passed: Prototype quality run `42452642087`, Loop engine checks `42452642089` (all four Ubuntu/Windows × Python 3.11/3.13 matrix jobs), PR title convention `42452642110`. No CI repairs were required.
