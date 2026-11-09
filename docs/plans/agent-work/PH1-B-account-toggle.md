# PH1-B — Administrator account enable/disable (web)

Agent: write your progress under "## Progress" below every time you complete a step. Do not edit other agents' files.

## Task brief

Goal: close the Phase 1/2 gap "Web利用者追加・停止操作" (stop operation half): administrators can enable/disable a user account from the web UI, with immediate effect.

Approved design constraints:
- Endpoint: `PUT /api/admin/users/{user_id}/enabled` with body `{ "enabled": bool }`. Requires `system_admin` (same as the existing `GET /api/admin/users`).
- Disabling an account must **immediately revoke access**: the existing `_authenticate` already rejects disabled users; deleting all of the user's sessions on disable closes live sessions (mirror the password-rotation session purge). Enabling restores future logins only (no sessions are recreated).
- Audit: metadata-only records `account.disable` / `account.enable` with target user id, written in the same transaction. Admin cannot disable themselves (422) — prevents lockout; disabling another system_admin is allowed but audited.
- Provisioned CLI accounts and recovery flows must respect the disabled state (coordinate the invariant "disabled account cannot log in, rotate, or redeem recovery codes" — if recovery endpoints do not exist yet on your branch, add a defensive check in `login`/`rotate` paths only where they already exist).
- Rate-limit the toggle endpoint (reuse `_limit` with a sensible key, e.g. 30/min).
- Frontend: extend the existing 利用者 (users) admin page in `frontend/src/App.tsx`: list rows gain a visible state label and an enable/disable button (icon-button with readable name, per `UI_IMPLEMENTATION_BASELINE.md`; no new decorations). Disabled state must be obvious; failed toggles keep the row state and show the error. Keyboard and screen-reader labels required.
- Follow existing conventions exactly (read `backend/app/service.py` `users()`, `main.py` admin endpoints, `frontend/src/App.test.tsx` patterns first).

Regression tests:
- Backend: toggle requires system_admin (403 otherwise), unknown user 404, disable revokes live session (401 immediately after), disabled user cannot re-login (login fails with the generic credential message), enable allows login, self-disable 422, audit records written transactionally, rate limit.
- Frontend: extend the users page test file if one exists, otherwise add `AccountToggle.test.tsx` with mocked fetch: toggle call payload, optimistic/refreshed state, error retention.

Process (mandatory):
1. Own worktree: `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-account-toggle -b loop/PH1-account-toggle loop/local-development`; work only inside it.
2. Read `AGENTS.md`, `docs/governance/DEVELOPMENT_POLICY.md`, `docs/governance/GITHUB_WORKFLOW.md`, `docs/planning/UI_IMPLEMENTATION_BASELINE.md` first. Match existing code style; ruff + format + `npm run lint` + `npm run typecheck` must pass.
3. Implement → adversarial self-review (authorization, IDOR on user ids, audit accuracy, UI state races) → local QA: `.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/e2e`, frontend `npm test`, and `npx playwright test` in frontend/ (browser tests exist for the admin pages). Iterate until green.
4. Conventional Commit. Push `loop/PH1-account-toggle`. Check Actions: billing-failure ⇒ record **blocked**, stop retrying. Real failures ⇒ fix and re-push until green.
5. Record design notes, evidence, commit SHA, push state below.

Boundaries: no `main`/`loop/local-development` pushes; no changes to other agents' scope; do not implement user *creation* (that is PH1-D); do not weaken tests.


## Orchestrator notes (2026-11-06)

- First run (task ph1-b-toggle-001) died on provider quota exhaustion
  (`theos_exhausted`, deepai gpt-6.1-sol daily limit) mid-implementation.
- The worktree `.loop/runtime/worktrees/PH1-account-toggle` (branch
  `loop/PH1-account-toggle`) contains UNCOMMITTED partial work from that run:
  modified `backend/app/main.py`, `backend/app/service.py`,
  `frontend/src/App.tsx`, this file, plus new `frontend/src/AccountToggle.test.tsx`
  and `tests/test_account_toggle.py`. Treat it as an UNTRUSTED DRAFT: review the
  existing diff adversarially, keep only what is correct, complete the rest per
  the brief, and run the full local QA before committing.
- The relaunched agent is authorised to commission exactly ONE independent
  read-only security review round of its final diff (via delegate_task,
  role=review) before the final push. Incorporate findings; the two-cycle
  fix/re-review cap still applies.
## Progress

- Relaunch: read the main-checkout brief and Orchestrator notes, then verified the assigned worktree is on `loop/PH1-account-toggle`; inspected every tracked draft hunk and read both new regression test files. The draft review confirmed the toggle uses the existing serialized SQLite transaction/audit/session conventions, while backend/frontend tests need verification before retaining it.
- Read the required governance, product, architecture, bootstrap, GitHub and corrected UI-baseline docs; inspected the baseline image and multiuser UI notes. Confirmed bootstrap evidence exists and read loop Goal/requirements/architecture/acceptance plus relevant implementation/security skills. No recovery endpoint exists; existing login already checks `enabled`, while rotate now defensively checks it.
- First QA launch found dependencies are not installed in this worktree (no local `.venv` or `frontend/node_modules`); no install/network action was taken. The main checkout has an existing Python venv and npm dependency tree, so I will reuse those locally for isolated worktree checks without touching other branches.
- Relaunch verification: confirmed assigned worktree and branch at `2db93a0` with only the listed draft files modified/untracked; reread the full task brief, governance/product/architecture/bootstrap docs and UI reference/design. Bootstrap evidence is present; no product-scope conflict or new decision was identified.
- Read the authoritative Goal, requirements, architecture, acceptance, decisions, progress and required implementation/security/quality/loop skills. The assigned stop-operation scope does not expand product scope; the pending broader approvals remain untouched. The worktree copy omits loop progress/decision ledgers; I did not access or alter Controller state.
- Adversarially inspected the inherited backend/frontend diffs and new regression tests against authentication, transaction, audit, session and UI conventions. The paths appear scoped and implement the brief; QA and remaining edge checks will decide retention. Recovery/redeem handlers were not present in inspected service routes; login checks enabled and rotate has a defensive disabled-account check.
- Security self-review found a request-boundary race in the draft: account-toggle and password-rotation service calls authenticated a `Principal` before entering their mutation transaction, so a request paused across disable+reenable could rely on a purged session. I will revalidate the session inside both transactions and add regression coverage; this strengthens the approved “enable restores future logins only” invariant.
- Frontend dependency bootstrap attempt: the first `npm ci --offline` ran from the repository root rather than `frontend/` and stopped because there is no root lockfile; it made no changes. The worktree contains its frontend lockfile, so I will rerun from the assigned worktree's `frontend/` directory.
- Implemented transaction-bound session revalidation for account toggles and password rotation, so a stale request cannot mutate state after disable/reenable purges its session. Updated route wiring and added regression assertions for stale rotate/toggle attempts; session purge, audit and rate-limit behavior remain unchanged.
- Offline frontend dependencies installed successfully with `npm ci --offline` from the assigned worktree's `frontend/` directory (252 packages, 0 advisories); targeted account-toggle backend suite passes (8 tests).
- Full QA cycle 1: pytest passed (1,098 passed, 18 skipped); frontend unit tests passed (49); ESLint passed. Ruff check/format and frontend build exposed formatting/lint and new test type errors; corrected the test formatting and replaced unsupported `exact` options with anchored accessible-name regexes.
- Recheck after fixes: Ruff check and format passed; frontend lint, all 49 unit tests, typecheck and TypeScript/Vite build passed; targeted account-toggle backend suite passed again (8 tests). Playwright Chromium E2E passed (10 tests) using a temporary worktree `.venv` helper for the config's expected path; the temporary artifact was removed afterward. Full pytest was 1,098 passed / 18 environment skips.
- Final adversarial self-review: authorization is checked against a live session and system-admin role inside the toggle transaction; the user id is a parameterized DB lookup; self-disable is rejected; disable+session purge+metadata-only audit are atomic; enable does not recreate sessions; login and rotation reject disabled accounts (including stale sessions after re-enable). UI state stays unchanged on error, blocks duplicate updates, disables self-toggle, escapes target ids and guards late unmount responses. No recovery/redeem endpoint exists in this base branch; no recovery code is introduced.
- Delivery status: the assigned implementation-loop skill forbids implementation agents from committing or pushing. Therefore commit SHA: none; push: not attempted; GitHub Actions: not checked (no branch push). Changes remain uncommitted in this worktree at base `2db93a0` for the Controller/authorized delivery step.
