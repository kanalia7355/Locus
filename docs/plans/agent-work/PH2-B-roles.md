# PH2-B — Concurrent role holdings (兼任) + explicit deny permissions (implementation)

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

Phase-2 job per `docs/plans/PHASE2_JOB_BREAKDOWN.md` (PH2-B), from the
reconciliation Phase-2 row: 兼任/明示deny semantics are 未確定または未実装.

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH2-B-roles -b loop/PH2-B-roles origin/loop/local-development` (reuse if it exists). Work ONLY inside it.

First read: `AGENTS.md`, governance docs, `backend/app/service.py` (roles,
memberships, permission checks, `_can_read`, role ceilings), `backend/app/main.py`,
`tests/test_role_updates.py`, `tests/test_custom_role_publication.py`,
`tests/test_security.py`, and `docs/planning/ui-and-multiuser-design.md`.
IMPORTANT: another job (P4B) is adding admin project/member endpoints on the
shared files — check its current scope in `docs/plans/agent-work/PH1-P4B-admin-screens.md`
and keep your changes in the role/membership model + role APIs, minimizing
overlap.

Behavior to implement (backend first; UI only if trivially additive):
1. Verify current role cardinality per membership (investigate first; record the
   finding). Implement 兼任: a user may hold multiple roles in the same project;
   effective permissions are the UNION of held roles; the non-administrative
   ceiling and subset rules still apply to every held role; no elevation path.
2. Implement 明示deny: role/membership-level explicit deny entries that override
   allow within the same scope; deny-by-default remains the global default; deny
   cannot be overridden by another role; document precedence rules in code
   comments; audit role changes transactionally as today.
3. Regressions (minimum): union semantics (two roles combine), deny overrides
   allow in the same scope, deny does not leak across scopes, no self-escalation
   via combining roles, custom-role updates still within ceiling, built-ins
   immutable, all existing role/publication/security tests pass unchanged.
4. Web UI: only if the existing role editor can show combined roles/deny state
   additively; otherwise record UI work as a follow-up (do not expand scope).

QA (repeat until ALL green): full pytest (tests -q --ignore=tests/e2e), ruff
check + format --check, mypy backend/app, secret scan; frontend tests only if
you touch frontend. Adversarial self-review focused on privilege escalation.

Process: Implement → self-review → QA → Conventional Commit
(`feat(auth): concurrent role holdings and explicit deny permissions`) → push
`loop/PH2-B-roles` → wait branch CI → fix/re-push until ALL green (bounded).
Append progress + SHA + CI evidence to this file's ## Progress section.

Boundaries: never push to `main` or `loop/local-development`; do not weaken
tests; do not change delegation (PH2-D's scope); no subagents.

## Progress
- 2026-11-07: Inspected role/membership storage and confirmed one role per project membership: `memberships` has a single `role` column and `PRIMARY KEY(user_id, project_id)`. Existing authz, publication, role-update, security tests and P4B scope reviewed. Implementing project-scoped normalized concurrent role holdings plus scoped deny sets, while preserving legacy membership shape for adjacent admin endpoints.
- 2026-11-08: Fast-forward synced `origin/loop/local-development` to `04ac645` with `git merge` (no force-push). Integrated PH1-P4A migration hunks conservatively; role migration remains additive, preserving the `cancel_requested` column migration and adding only role/deny schema. P4B project/member admin endpoints are separate; role holdings remain project-scoped. Implemented union authorization, per-held-role intersection ceilings for custom grants, explicit same-project deny precedence (including membership-level denies), transactional audits, migration from legacy single-role memberships, and role-holding/denial APIs. Added adversarial regressions for union, deny-overrides, scope isolation, custom-role subset/escalation, built-in immutability, audit rollback, API authorization, and legacy migration. No frontend changes: role editor cannot safely represent concurrent holdings/deny state; UI remains follow-up.
- 2026-11-08: Focused role/publication/security tests: 32 passed. Full QA: `pytest tests -q --ignore=tests/e2e` — 1124 passed, 18 skipped (environment-gated Docker/native/symlink cases); Ruff check passed; Ruff format check passed (117 files); mypy `backend/app` passed (7 source files); offline secret scan passed (0 findings).
