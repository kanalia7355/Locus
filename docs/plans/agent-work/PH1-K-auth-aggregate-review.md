# PH1-K — Independent read-only review of the Phase-1 auth-slice aggregate

Agent: append your progress under "## Progress" below. You are a REVIEWER: do
not modify any file other than this one (your progress notes), do not spawn
agents, do not push, do not create a persistent worktree. Work in the main
checkout read-only.

## Task brief

Independent review of the Phase-1 auth-slice aggregate, integrated into
`loop/local-development` (review HEAD at a55d856 or later — if the PH1-J race
fix lands during your review, note it but review the aggregate as it stands):

Features:
- PH1-A recovery: admin-issued single-use expiring recovery codes (CLI
  issuance, unauthenticated redemption endpoint, digest-only storage, session
  revocation) — feature commit 60a6d10, CI repair bd9f2cf, branch 93d1633.
- PH1-B account enable/disable: PUT /api/admin/users/{id}/enabled, session
  purge, live-session revalidation in rotate/toggle — feature commit a31d570,
  integrated b7adb42.
- PH1-D web user provisioning: POST /api/admin/users, one-time password,
  admin-ID audit — feature commit 63ab511, CI repairs cbe12e4/a355efb,
  integrated 2610b70.
- PH1-G consolidation: docs update + cross-job regression (1113 passed/18
  skipped, frontend 52, Playwright 10) + the stale-Principal race finding —
  integrated a55d856.

Review criteria:
1. Security: adversarially review the aggregate auth surface (recovery codes,
   toggle, provisioning) for enumeration, timing, replay, audit leakage,
   session semantics, disabled-account invariants, rate limits. Verify the
   documented race finding's severity and the proposed remediation direction.
2. Evidence: spot-check recorded test counts/CI claims against the task files
   and actual code; verify docs claims match reality.
3. Spec conformance: PHASE_SPEC_RECONCILIATION Phase-1 row + PHASE_STATUS
   accuracy (no completion overclaim; MFA/TLS unresolved as stated).
4. Boundaries: no approved boundary weakened; no test weakened; Conventional
   Commits everywhere.
5. Actionability of the race finding: confirm the fix direction or correct it.

Verdict: accept / accept after minor fixes / needs major rework. Findings with
severity, location, evidence, fix recommendation. Do not edit anything except
this file.

## Progress

- Review performed read-only at `loop/local-development` HEAD `a8cb3e714cbcbc9812cd7d06d9055b9fdc12981a`; the requested A/B/D integration commits and `a55d856` are ancestors. I left the pre-existing unrelated working-tree changes untouched. PH1-J was active in its separate worktree; its fix was not yet integrated at this review HEAD.
- Security — **MEDIUM, confirmed: stale-admin provisioning race.** `backend/app/main.py:204-207,434-436` resolves `Actor` to a `Principal` before the POST handler. `backend/app/service.py:240-246` authorizes from the cached `actor.system_admin`, then calls `provision()` in a later DB transaction without checking the session. I reproduced this against a temporary SQLite DB: authenticate admin A, disable A using admin B, confirm A's token now authenticates as 401, then call `provision_web_user(stale_principal, ...)`; it still created the account. This is the documented race and Medium is appropriate: a disabled administrator can complete a delayed privileged account-creation action and receive its one-time credential, but this does not yield general system access by itself. The proposed remediation is correct and actionable: revalidate the live token/session and current admin role inside the same `BEGIN IMMEDIATE` transaction that creates the user and writes the audit row (mirroring `set_user_enabled` at `backend/app/service.py:1408-1423`); add a regression proving a purged/stale admin cannot provision and a live enabled admin can. Avoid authenticating in one transaction and then calling the current nested `provision()` transaction; factor the insert into a transaction-local helper or otherwise preserve one atomic authorization-and-create boundary. Do not return the temporary password on rejection.
- Security — **LOW follow-up, adjacent in-flight read semantics.** `GET /api/admin/users` and `/api/admin/audit` route through `Actor` (`backend/app/main.py:430-440`) and their service methods only test the cached `Principal.system_admin` (`backend/app/service.py:1391-1406`), not the live session. A temporary-DB probe showed stale `Principal`s could still retrieve these lists after disable. This is limited to a request authenticated before revocation (and is not the user-creation mutation finding); clarify whether in-flight admin reads may finish under request-start authorization. If “immediate” disable is intended to cancel those too, revalidate in the read transaction and add coverage. The account-toggle mutation itself revalidates in-transaction; recovery redemption is unauthenticated by design, checks `enabled` inside its transaction, and does not create a session.
- Security spot-checks: recovery issues a 32-byte random code, stores only its SHA-256 digest, uses fixed-size `compare_digest`, rate-limits by hashed username, and atomically consumes it / updates the password / deletes sessions / writes metadata-only audit (`backend/app/service.py:402-458`). Unknown, wrong, expired, used and disabled-account credentials share the generic 401; successful recovery grants no session. Toggle disable+purge+audit is transactional, self-disable is rejected, enable does not recreate sessions, and login rejects disabled accounts. Provisioning uses `secrets.token_urlsafe(24)`, CLI-compatible username/password constraints, Argon2id, `must_rotate`, expiry, admin-ID metadata audit and a per-admin limit; response middleware sets `Cache-Control: no-store` (`backend/app/main.py:197-202`). The UI keeps the password in component state with explicit one-time wording, copy/dismiss controls and does not persist it (`frontend/src/ProvisionUser.tsx`); the account list combines provisioning and toggle UI (`frontend/src/App.tsx:1755-1762,1821-1839`).
- Evidence/spec/boundary spot-check: task files record A 1101 passed/18 skipped, B 1098/18 plus 49 frontend and 10 Playwright, D 1094/18 plus 49 frontend and 10 Playwright; PH1-G records 1113/18, Ruff/format, mypy (7 files), secret scan (0), Vitest 52/13 files and Playwright 10 at base `fa6e7c5`. These match the recorded task progress and the aggregate progress note; the differing skip/test totals are separate worktree/revision runs, not additive totals. Integration CI references (`93d1633`, `c28a280`, `590f40a`) are corroborated by the task/orchestrator records. PH1-G explicitly says exact-HEAD CI was pending; neither reconciliation nor status claims otherwise. I ran the focused suites `tests/test_recovery.py tests/test_account_toggle.py tests/test_api.py -q`: **30 passed**. This was not a rerun of the full aggregate suites or CI.
- `docs/plans/PHASE_SPEC_RECONCILIATION.md:17` and `docs/plans/PHASE_STATUS.md:146-147,175-187` correctly retain the race as unresolved, explicitly keep MFA and production TLS/session deployment unresolved, and do not claim Phase 1 completion. Test changes in the CI repairs replace synthetic password literals only; no assertions, tests or security controls were removed/weakened. The A/B/D/G integration and repair subjects inspected use Conventional Commit types/scopes. No approved boundary weakening found.
- **Verdict: accept after minor fixes**, conditional on resolving the Medium provisioning race with the transaction-bound session check and regression test, then re-reviewing the integrated fix and obtaining exact-HEAD CI evidence before any completion decision. The adjacent in-flight read behavior is a low-priority semantics clarification, not a blocker under request-start authorization; if a stricter revocation guarantee is required, address it explicitly.
