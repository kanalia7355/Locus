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
