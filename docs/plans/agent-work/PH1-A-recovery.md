# PH1-A — Authentication recovery (single-use, admin-issued)

Agent: write your progress under "## Progress" below every time you complete a step (setup, design note, implementation, self-review, QA cycle, commit, push, CI attempt). Do not edit other agents' files.

## Task brief

Goal: close the Phase 1 gap "回復 (recovery) flow" recorded in `docs/plans/PHASE_SPEC_RECONCILIATION.md` (row Phase 1: "回復/MFA...未完成").

Approved design constraints (follow these; do not invent a self-service flow):
- Recovery is **admin-issued, single-use, expiring**: the local administrator (system_admin, via CLI) issues a recovery code for a specific username, exactly like existing temporary-password provisioning. No email, no self-service, no security questions (prototype is LAN-only, `APP_ENV=development` enforced).
- The code is a high-entropy token shown **once** in CLI output and stored only as a digest (mirror the session-token digest pattern; do not store the plaintext).
- Redemption: an authenticated-less endpoint (rate-limited per username) accepts `username`, `recovery_code`, and a new password meeting the existing 14–128 char rules and different-from-current rule. On success: password hash updated, `must_rotate=0`, code marked used (single-use), the code expires at redemption, **all sessions for the user are revoked**, and a metadata-only audit record is written (no plaintext, no code digest in audit? record operation + target user only). Expiry: codes expire 24h after issuance (reuse the `temp_expires` pattern); expired or used codes fail with a generic message that does not reveal whether the username or code was wrong.
- Rotation semantics must reuse existing helpers (`rotate` rules, `PASSWORDS`, `_limit`, `digest`, `_audit`). Read `backend/app/service.py` and `backend/app/cli.py` first and follow existing code conventions exactly.
- CLI: add a subcommand (e.g. `issue-recovery <username>`) to `backend/app/cli.py` following the existing argument style; print the code once with a warning that it is shown only once.
- Regression tests (extend `tests/test_security.py` or add `tests/test_recovery.py`): happy path, wrong code, reused code, expired code, unknown username (same generic failure), weak/same new password rejection, session revocation after recovery (old token 401), rate limiting, audit record presence, account-disabled interaction (recovery must not resurrect a disabled account), code shown only once (CLI output).
- No frontend changes are in scope. MFA is explicitly out of scope.

Process (mandatory):
1. Work ONLY in your own worktree: `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-recovery -b loop/PH1-recovery loop/local-development` then work inside that directory (absolute paths).
2. Read `AGENTS.md`, `docs/governance/DEVELOPMENT_POLICY.md`, `docs/governance/GITHUB_WORKFLOW.md`, `docs/LOCAL_COMMIT_PUSH_LOOP.md`, and `docs/plans/PHASE_SPEC_RECONCILIATION.md` before coding. Follow existing code style; ruff + ruff format must pass.
3. Implement → self-review your own diff adversarially (auth paths are security-sensitive: check enumeration, timing, brute force, replay, audit leakage) → run the local suites: `C:/Users/hirot/Locus/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/e2e` plus `ruff check backend tests`. Iterate until green.
4. Conventional Commit subject. Push `loop/PH1-recovery` to origin. Check the Actions runs for your branch: if they fail with the account billing/spending-limit error, record it as **blocked (CI evidence unavailable, not passed)** and stop retrying — do not loop indefinitely; report the blockage in your progress notes. If any real CI failure occurs, fix and re-push (repeat until green or blocked).
5. Record: design decisions + deviations (if any) + QA evidence (command, counts) + final commit SHA + push state in this file.

Boundaries: do not touch `main`, `loop/local-development`, other agents' branches or files outside your worktree; do not modify the reconciliation doc; do not change `LocalModel`/model settings; do not weaken existing tests.
