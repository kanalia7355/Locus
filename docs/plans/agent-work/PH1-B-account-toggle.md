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
2. Read `AGENTS.md`, `docs/governance/DEVELOPMENT_POLICY.md`, `docs/governance/GITHUB_WORKFLOW.md`, `docs/plans/UI_IMPLEMENTATION_BASELINE.md` first. Match existing code style; ruff + format + `npm run lint` + `npm run typecheck` must pass.
3. Implement → adversarial self-review (authorization, IDOR on user ids, audit accuracy, UI state races) → local QA: `.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/e2e`, frontend `npm test`, and `npx playwright test` in frontend/ (browser tests exist for the admin pages). Iterate until green.
4. Conventional Commit. Push `loop/PH1-account-toggle`. Check Actions: billing-failure ⇒ record **blocked**, stop retrying. Real failures ⇒ fix and re-push until green.
5. Record design notes, evidence, commit SHA, push state below.

Boundaries: no `main`/`loop/local-development` pushes; no changes to other agents' scope; do not implement user *creation* (that is PH1-D); do not weaken tests.
