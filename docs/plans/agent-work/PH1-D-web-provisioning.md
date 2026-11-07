# PH1-D — Administrator web user provisioning (create user with one-time password)

Agent: write your progress under "## Progress" below every time you complete a step. Do not edit other agents' files.

## Task brief

Goal: close the Phase 1/2 gap "Web利用者追加" (creation half): a system administrator can create a new user account from the web UI; the UI shows the generated one-time temporary password **once**.

Approved design constraints:
- Endpoint: `POST /api/admin/users` with body `{ "username": string }`, `system_admin` only. Reuse the existing provisioning rules verbatim: username pattern `^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,63}$`, temporary password 14–128 chars generated with `secrets`, `must_rotate=1`, `temp_expires = now + 86400`, Argon2id hash, audit record `account.provision` (the existing CLI path uses actor "local-cli" — for the web path use the administrator's user id).
- Response returns the temporary password **exactly once** in the JSON body; it must never be persisted, logged, or included in audit records. Rate-limit the endpoint (reuse `_limit`, e.g. 10/min for admin actions).
- Duplicate username → 409 with the existing message. Validation errors → 422 with the existing messages.
- The temporary password strength requirement mirrors the CLI: no policy beyond length, but generation must be cryptographic (`secrets.token_urlsafe` or equivalent of the CLI's pattern).
- Frontend: extend the existing 利用者 (users) admin page: an "追加" action opening a small inline form (username field + submit); after success, show the one-time password in a dismissible block with explicit "一度だけ表示されます" wording; copying is allowed; refresh discards it. Follow `UI_IMPLEMENTATION_BASELINE.md` (no new decorations; icon buttons need readable names). Failed submissions retain input and show errors.
- Follow existing conventions exactly; read `backend/app/cli.py` `provision` usage, `service.provision`, `main.py` admin endpoints, and frontend users-page code first. Coordinate expectations with the fact that another agent is adding enable/disable rows to the same page (keep your UI changes additive and isolated to a creation section to minimise merge conflicts).

Regression tests:
- Backend: system_admin-only (403 otherwise), happy path returns 201 + one-time password + `must_rotate` true, duplicate 409, invalid username 422, rate limit, audit written with the admin's id and no password material, the created user can log in and is forced to rotate.
- Frontend: `ProvisionUser.test.tsx` (or extend existing users test): creation flow, one-time display, dismissal, error retention.

Process (mandatory):
1. Own worktree: `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-web-provisioning -b loop/PH1-web-provisioning loop/local-development`; work only inside it.
2. Read `AGENTS.md`, `DEVELOPMENT_POLICY.md`, `GITHUB_WORKFLOW.md`, `UI_IMPLEMENTATION_BASELINE.md` first.
3. Implement → adversarial self-review (secret exposure in logs/responses/errors, authorization, audit leakage, injection via username) → local QA: `.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/e2e`, frontend `npm test`, `npx playwright test` in frontend/. Iterate until green.
4. Conventional Commit. Push `loop/PH1-web-provisioning`. Actions billing failure ⇒ record **blocked**, stop retrying. Real failures ⇒ fix, re-push until green.
5. Record design notes, evidence, SHA, push state below.

Boundaries: no `main`/`loop/local-development` pushes; no enable/disable work (PH1-B owns it); do not weaken tests; no password material in logs or audit.
