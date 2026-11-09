# PH2-D — Time-limited delegation implementation (owner-approved parameters)

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

The owner approved the delegation specification (2026-11-09) with binding
parameters. Implement it exactly per `docs/plans/PHASE2_DELEGATION_SPEC.md`
(§8 resolution banner has the owner conditions) and
`docs/plans/OWNER_DECISION_REGISTER.md` (RESOLVED 2026-11-09 section).

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH2-D-delegation -b loop/PH2-D-delegation origin/loop/local-development` (reuse if it exists). Work ONLY inside it.

NOTE: another job (PH2-E) is adding web-management UI in ITS OWN worktree — keep your changes backend-focused (service.py role/delegation model + main.py endpoints + tests); minimal, well-localized main.py diffs. Also note the integrated PH2-B concurrent-roles/deny model and the integrated slice-2a registry (backend/app/agents/) — integrate with them, don't duplicate.

Approved parameters (binding):
- **Grant model**: immutable, versioned grant rows (family/version); actor,
  project scope (org-wide deferred), permission subset, expiry; transactional
  metadata-only audit (`delegation.grant`/`revoke`/`expire` etc. — follow the
  existing `_audit` naming style).
- **TTL**: default 24h, max 7 days, minimum 15 minutes; expiry enforced by LIVE
  revalidation at EVERY authorization point (no long-lived caches); expired
  grants deny immediately.
- **Grantors**: the project owner, and an org administrator with legitimate
  administrative authority over the target project; grant authority itself is
  NOT delegable; the NON_ADMIN permission ceiling applies (administrative
  permissions are not delegable).
- **Subset rule**: a grant may only narrow; the grantor's own effective ceiling
  is the hard cap; combining with the recipient's concurrent roles must never
  exceed any ceiling; self-privilege-escalation denied and tested.
- **Re-grant**: family/version scheme; no unintended revival or coexistence of
  old versions; scope change or permission expansion requires a NEW
  authorization (never a same-family widening); overlapping grants deduplicated
  within a family.
- **Revocation/cancellation**: grantor revocation and recipient cancellation
  both allowed, idempotent, audited; revocation takes effect at the next
  authorization point and during in-flight operations (deny at recheck, mirror
  the existing live-recheck patterns); grantor authority loss/removal/disable/
  parent-grant expiry → live invalidation, fail-closed.
- **Membership gate**: a grant NEVER substitutes for project membership.
- **Time authority**: epoch seconds (existing `time.time()` convention) until
  the production-DB decision.
- **Retention**: expired/revoked grant versions and audit entries retained
  until the production-deployment phase decision.
- **The disabled 409 placeholder** (`POST /api/admin/delegations` in
  `backend/app/main.py`) is REPLACED by the real, fail-closed implementation.

Endpoint/API design: follow existing admin endpoint conventions (system_admin
ceilings do NOT apply here — grantors are project owners/org admins; use the
project-role ceilings; `_limit` rate limits; live recheck inside the
transaction per the PH2-B/PH1-J pattern; audit in the same transaction).

Regressions (minimum set):
- Grant happy path (grantor=project owner; grantor=org admin), expiry at every
  authorization point (document read/retrieve, chat, attachments), TTL bounds
  validation (too short/too long rejected), subset narrowing enforced,
  self-escalation denied, grantor authority loss invalidates live, revocation +
  idempotency + audit, recipient cancellation, family/version rules (no revival,
  no coexistence, scope change requires new grant), membership-gate independence,
  delegation combined with concurrent roles + deny (deny wins), the old 409
  placeholder replaced, audit contents (no secrets).
- ALL existing tests (roles/concurrent/deny/publication/security/administration)
  pass unchanged.

ENVIRONMENT NOTE: `.loop/runtime/qa-venv` may have been cleaned — recreate if
missing (Python313: `"C:/Users/hirot/AppData/Local/Programs/Python/Python313/python.exe" -m venv C:/Users/hirot/Locus/.loop/runtime/qa-venv` then `pip install -e ".[dev]" -r backend/requirements.lock`). NEVER touch the shared `.venv`.

QA (repeat until ALL green): full pytest (tests -q --ignore=tests/e2e), ruff
check + format --check, mypy backend/app, secret scan. Adversarial
self-review: privilege escalation via grants/combining, expiry bypass, grantor
impersonation, audit leakage, race windows.

Process: implement → self-review → QA → Conventional Commit
(`feat(auth): time-limited delegation grants with live expiry enforcement`) →
push `loop/PH2-D-delegation` → wait branch CI → fix/re-push until ALL green
(bounded). Append progress + SHA + CI evidence to this file's ## Progress.
Branch deleted after integration.

Boundaries: never push to `main` or `loop/local-development`; no frontend (the
UI is PH2-E's scope); do not weaken tests; no subagents.

## Progress

### Run 3 (slot B, GLM relaunch, 2026-11-08)

- Read brief + PHASE2_DELEGATION_SPEC §8 (owner conditions binding).
- Reproduced the orchestrator-identified failure of
  `test_owner_and_project_org_admin_grants_are_authorized` and root-caused it:
  the pre-existing memberships UPSERT in `_replace_role_holding` fires the
  `membership_role_update` trigger, and SQLite's conflict-resolution override
  rule makes the outer statement's ON CONFLICT clause override the
  `INSERT OR IGNORE` clauses inside nested trigger bodies, so
  `delegation_grantor_role_add`'s idempotent `INSERT OR IGNORE INTO
  delegation_events` ran with ABORT and hit UNIQUE(grant_id,event_type).
  Verified with a minimal standalone repro (plain INSERT/UPDATE are fine; only
  the UPSERT path breaks). Minimal fix: explicit UPDATE-or-INSERT in
  `_replace_role_holding` (no upsert); behavior unchanged.
- Removed an accidental duplicated attachment-recheck loop in the post-model
  chat transaction (dead code, no behavior change).
- Adversarial verification against approved parameters: TTL 900..604800 s
  (default 86400) enforced server-side incl. strict pydantic; live revalidation
  at every authorization point via `_permissions` → `_delegated_permissions`
  (expiry, any event, and live grantor-authority recheck; fail-closed on clock
  anomalies); grantor = project owner or project-scoped organization_admin with
  effective manage_roles; NON_ADMIN ceiling (manage_roles 422, tested); subset
  narrowing via role-holding ceiling intersection + effective allow set; deny
  wins; self-grant 403; family/version no-revival/no-coexistence (MAX(version)
  only is live; same-permission renewal dedups or versions within family;
  widened/scope-changed re-grant requires a new family); supersede/expire/
  revoke/cancel events idempotent + audited, retention triggers (immutable,
  no delete); membership gate independent (tested); epoch seconds;
  grantor membership removal/role add-remove/role permission change/deny
  change/account disable/owner change triggers invalidate live; in-flight chat
  re-recheck before model dispatch + post-model commit arbitration; 409
  placeholder replaced by real fail-closed endpoints (GET/POST/DELETE
  /api/admin/delegations). `create_admin_project` owner_id option retained for
  owner registration. Ruff `format .` had incidentally reformatted a fenced
  code block in docs/requirements/AUTONOMOUS_LOOP_SPEC.md — reverted (docs are
  outside the CI format targets).
- QA (all green): pytest tests -q --ignore=tests/e2e → 1156 passed, 18 skipped
  (run twice: after bugfix and after formatting); ruff check backend tests
  scripts → clean; ruff format --check backend tests scripts → clean; mypy
  backend/app → no issues; scripts/secret_scan.py → 0 findings.
- Committed 55d1c39 `feat(auth): time-limited delegation grants with live
  expiry enforcement`; pushed loop/PH2-D-delegation; CI started (run IDs
  42459387027/…050/…052).
- Branch CI: ALL GREEN on loop/PH2-D-delegation @ 55d1c39 —
  - "Prototype quality" (run 42459387052): success, 3m23s
  - "Loop engine checks" (run 42459387027): success, 7m55s (ubuntu/windows × py3.11/3.13)
  - "PR title convention" (run 42459387050): success
- Final SHA: 55d1c39. Work complete; ready for integration (branch deleted after merge).
