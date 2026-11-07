# PH1-K2 — Re-review of the integrated provisioning race fix (PH1-J)

Agent: append your progress under "## Progress" below. You are a REVIEWER: do
not modify any file other than this one (your progress notes), do not spawn
agents, do not push, do not create a persistent worktree. Work in the main
checkout read-only.

## Task brief

The PH1-K aggregate review (verdict: accept after minor fixes) conditioned
acceptance on: (1) the provisioning race fix, (2) a re-review of the integrated
fix, (3) all-CI-green at the exact final HEAD. Condition (1) is now integrated:
commit `0365a6a` on `loop/local-development` — `fix(admin): revalidate the live
session inside web provisioning` (branch CI green at a196e5e; full local pytest
1114 passed/18 skipped).

Review the integrated fix commit `0365a6a` (diff vs its parent):
1. Does `provision_web_user` now bind authorization to the live session INSIDE
   the serialized creation transaction (re-authenticate cookie, principal-id
   match, current system_admin check, rate limit, user insert + audit in the
   same transaction)? Any residual window?
2. Is the race regression test valid and does it assert no user/audit creation
   on the stale path and success on the live path?
3. Does the fix weaken anything (authz, audit accuracy, existing tests)?
4. Delivery note: the agent stalled and the orchestrator completed delivery,
   hardening the test (allowlisted password literals, first-login rotation +
   re-login). Verify the test changes are sound and secret-scan-safe.

Verdict: accept / accept after minor fixes / needs major rework — this closes
the PH1-K condition if accepted. Findings with severity/location/evidence/fix.
Do not edit anything except this file.

## Progress

- Reviewed read-only at `loop/local-development` HEAD `ac64555`; the target `0365a6ace4cefb8e5c9b1ed4f53163fff9f90457` is integrated (first-parent `8d6e2d5`; second parent `a196e5e`). No implementation files were changed. The worktree was clean before this note.
- **Authorization/transaction — PASS.** `backend/app/main.py:435-437` passes the request cookie to `Service.provision_web_user`. `backend/app/service.py:253-269` opens `self.db()` (which issues `BEGIN IMMEDIATE` at lines 165-169), then calls `_authenticate` within that transaction, matches the live principal ID to the dependency principal, checks the current `system_admin` flag, applies the per-admin limit, and creates the temporary credential/user. `_provision` at lines 220-250 inserts the user and audit event on that same DB connection/transaction; the temporary password is returned only after context-manager commit. The same serialization boundary used by account-disable/revocation (`set_user_enabled`, lines 1408 onward) orders concurrent operations: if revocation wins, the session lookup fails; if provisioning wins, its authorized operation completes before revocation. No check-then-create window remains. Audit actor is the live ID, existing metadata-only audit semantics are preserved, and there is no password in audit data.
- **Regression — PASS.** `tests/test_account_toggle.py:185-245` logs in admin A and B, rotates B's first-login password and re-logs in (because rotation invalidates sessions), disables and re-enables A, confirms A's old token remains invalid, then calls the service with A's captured stale principal/token. It asserts 401, zero user rows for the target username, and unchanged `account.provision` audit count. The live-admin HTTP path asserts 201 and the returned username/rotation requirement. Existing API tests at `tests/test_api.py:245-275` continue to cover successful provisioning and audit actor/target accuracy.
- **No weakening found.** The diff refactors shared creation logic into `_provision` so CLI provisioning retains its transaction and web provisioning can reuse the helper within its authorization transaction. Username/password validation, unique-name conflict handling, Argon2 hashing, one-day expiry, forced rotation, admin-ID audit, and rollback behavior remain intact. No tests or auth controls were removed or relaxed in the target diff.
- **Delivery hardening / secret scan — PASS.** The regression's literals `Synthetic-test-password-01!` and `Changed-synthetic-password-01!` are exact entries in the narrow `SYNTHETIC` allowlist (`scripts/secret_scan.py:14-16`), consistent with existing test fixtures; the scanner allowlist was not broadened in the reviewed fix. The real first-login flow (login -> `/api/auth/password` rotation -> re-login) is correct and ensures B has a live, non-rotation session for the race operation. Local verification from this checkout: `.venv/Scripts/python.exe scripts/secret_scan.py` reported **0 findings**; `python -m pytest tests/test_account_toggle.py tests/test_api.py -q` reported **20 passed**; Ruff check/format and mypy passed for the changed files / backend app. `git diff --check 0365a6a^ 0365a6a` was clean. The task and orchestrator records report the full suite (1114 passed/18 skipped) and branch CI green at `a196e5e`; I did not independently query hosted CI for the later current HEAD `ac64555`, so its exact-HEAD CI remains a separate completion gate as the aggregate review specified.
- **Verdict: accept.** No unresolved findings in the reviewed fix; this re-review closes PH1-K's integrated-race-fix condition. Preserve the separate requirement to confirm all required CI checks green on the eventual exact final HEAD before declaring Phase 1 complete.
