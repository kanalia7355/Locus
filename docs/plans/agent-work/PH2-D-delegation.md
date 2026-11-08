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
