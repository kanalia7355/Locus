# PH1-J — Fix the stale-Principal race in web provisioning

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

Context: PH1-G consolidation found one cross-slice semantic issue (recorded in
`docs/plans/agent-work/PH1-G-consolidation.md` at the integrated HEAD of
`loop/local-development`, a55d856 or later):

> The API obtains an admin `Principal` in `backend/app/main.py`'s `Actor`
> dependency before `POST /api/admin/users` calls `Service.provision_web_user`.
> That service checks the cached `system_admin` flag but does not revalidate the
> session in its creation transaction. Reproduction: capture admin A's
> principal, disable A via admin B (A's token then 401), call
> `provision_web_user` with the captured principal — the user is nevertheless
> created. Impact: a delayed in-flight admin provisioning request can mutate
> state after disable/session revocation.

Goal: revalidate the live session inside the provisioning mutation transaction
(follow the pattern PH1-B used for `set_user_enabled`/`rotate`: bind
authorization to the live session inside the serialized transaction) and add a
race regression test (disabled/purged admin principal cannot create a user;
enabled admin can). Check whether the same Principal-before-transaction pattern
affects other newer admin endpoints added by the integrated slices
(`set_user_enabled` already revalidates; verify recovery redemption needs none)
and align them, recording any judgement.

Setup: create your own worktree: `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-J-provision-race -b loop/PH1-J-provision-race origin/loop/local-development` (reuse if it exists). Work ONLY inside it. Read `AGENTS.md`, governance docs, `backend/app/service.py` (provision_web_user, set_user_enabled, _authenticate), `backend/app/main.py`, and `tests/test_account_toggle.py` (revalidation test pattern) first.

QA (repeat until ALL green): pytest tests -q --ignore=tests/e2e (full suite), ruff check + format --check, mypy backend/app, secret scan; frontend lint/test/build only if you touch frontend (you should not). Adversarial self-review the fix (auth path: check enumeration, timing, audit accuracy).

Conventional Commit (`fix(admin): revalidate the live session inside web provisioning`). Push `loop/PH1-J-provision-race`. Wait for branch CI; fix failures and re-push until ALL checks green (bounded; record if blocked). Append progress + SHA + CI evidence here.

Boundaries: never push to `main` or `loop/local-development`; scope is the race fix + regression only (no other features); do not weaken tests; do not spawn subagents.

## Progress

- Setup: fetched `origin/loop/local-development` and created `C:/Users/hirot/Locus/.loop/runtime/worktrees/PH1-J-provision-race` on `loop/PH1-J-provision-race` at `a8cb3e7`. The assigned task file is tracked in this worktree. Its starting tree is clean; pre-existing uncommitted files in the main checkout and other worktrees remain untouched. `.bootstrap/complete.json` exists; no bootstrap actions were needed.
- Requirements/code review: read AGENTS.md, development/product/architecture/bootstrap/GitHub governance, loop Goal/requirements/architecture/acceptance and relevant implementation/security/quality skills; inspected `provision_web_user`, `_authenticate`, `set_user_enabled`, `rotate`, the admin API routes, `tests/test_account_toggle.py`, the existing provisioning API tests, and PH1-A/B/D task evidence. The reproduced issue is that provisioning currently relies on the Actor dependency's cached Principal and opens a separate transaction to create the account.
- Related endpoint judgement: account disable already takes the raw cookie and runs `_authenticate` inside the `BEGIN IMMEDIATE` mutation transaction; password recovery redemption has no Principal (by design) and validates the recovery code, expiry, used state, and account enabled state within its transaction. Neither needs this race fix. Admin user/audit listing are read-only; model runtime configuration already authenticates inside its transaction; model discovery reauthenticates after local catalog I/O and only records discovery metadata. No other PH1-A/B/D account/credential mutation has the same stale-Principal authorization gap, so I will keep the implementation limited to provisioning and its regression tests.
- Implementation: `provision_web_user` now reauthenticates the request cookie with `_authenticate` inside `self.db()` (`BEGIN IMMEDIATE`), requires the live principal ID to equal the dependency principal, checks the current admin flag, then inserts the new account and writes the existing metadata-only audit record in that same transaction. The API passes its cookie into the service. Added a regression that disables an admin A using admin B, re-enables A (which does not restore A's purged token), proves stale provisioning returns 401 without user/audit creation, and verifies a live admin can still provision successfully. Targeted checks pass: `tests/test_account_toggle.py tests/test_api.py` (**19 passed**); Ruff check/format, mypy (7 files), secret scan (0 findings), and `git diff --check` pass.

## Orchestrator delivery postscript (2026-11-07 ~10:00 JST)

- The stalled agent run was cancelled after two steers; the orchestrator completed the authorized delivery.
- Test hardening during delivery: the new regression initially reused the disallowed `Temporary-password-05!` literal (replaced with the allowlisted `Synthetic-test-password-01!`), logged admin B in via POST, added the first-login rotation + re-login (rotation purges the session), and used POST for /api/auth/password; ruff format applied.
- Final local QA: full pytest 1114 passed / 18 skipped; ruff check + format clean; mypy 7 files clean; secret scan 0 findings.
