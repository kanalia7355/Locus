# PH2-A — Delegation specification (design-only)

Agent: append your progress under "## Progress" below every time you complete a
step. Design-only task: NO application code changes.

## Task brief

Phase-2 job per `docs/plans/PHASE2_JOB_BREAKDOWN.md` (PH2-A). The reconciliation
doc marks 期限付き委任 as disabled (409) and 期限・取消仕様 as 未確定. Your job is
to draft the authoritative delegation specification that the implementation job
(PH2-D) will follow.

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH2-A-delegation-spec -b loop/PH2-A-delegation-spec origin/loop/local-development` (reuse if it exists). Work ONLY inside it.

First read: `AGENTS.md`, governance docs, `docs/plans/PHASE2_JOB_BREAKDOWN.md`,
`docs/plans/PHASE_SPEC_RECONCILIATION.md` Phase-2 row, `docs/requirements/PRODUCT_SPEC.md`
(delegation requirements), `docs/architecture/ARCHITECTURE.md`, and the actual
code: `backend/app/service.py` (roles, publication grants, membership, the
disabled delegation path returning 409), `backend/app/main.py`, existing tests
(`tests/test_custom_role_publication.py`, `tests/test_role_updates.py`,
`tests/test_administration_audit.py`, `tests/test_security.py`).

Deliverable: `docs/plans/PHASE2_DELEGATION_SPEC.md` containing:
1. Grant model: who grants what to whom (actor, project/organization scope,
   permission subset, expiry), data model following existing conventions
   (immutable versioned rows where the step-2 design uses them; transactional
   metadata-only audit), and how grants interact with existing roles/publication
   grants (no bypass of the subset ceiling).
2. Expiry semantics: TTL bounds, renewal, what happens at expiry (live recheck at
   every authorization point — no long-lived caches; expired grants deny
   immediately), clock-skew/timestamp conventions matching existing code.
3. Revocation/cancellation semantics: immediate effect on live sessions/data
   paths (mirror the Phase-1 disable/revoke pattern), revocation during in-flight
   operations, audit.
4. Self-privilege-escalation denial: a grantor cannot grant beyond their own
   effective ceiling; explicit denial rules and tests.
5. Subset/scope narrowing rules: delegate receives a subset only; union with
   existing roles stays within ceilings; organization vs project scoping rules.
6. Interaction with 兼任/明示deny (PH2-B's concurrent role holdings + explicit
   deny) — reference, don't duplicate.
7. Regression-test plan covering the reconciliation verification column:
   異なる利用者/組織/権限変更中の全データ経路、委任subset/scope/expiry、自己昇格拒否.
8. 【要決定】 inventory: default max expiry, re-delegation allowed?, who may grant
   (project owner? org admin? system_admin only?), anything else you cannot
   decide. Mark them; do not decide.

Rules: follow existing conventions; weaken nothing; spec must not require
disabling existing security behavior. Self-review against the reconciliation doc
and the product spec. Conventional Commit (`docs(plans): draft the phase-2 delegation specification`).
Push `loop/PH2-A-delegation-spec`; wait branch CI; fix/re-push until ALL green
(bounded; record if blocked). Append progress + SHA + CI evidence to this file's
## Progress section.

Boundaries: never push to `main` or `loop/local-development`; no code changes;
do not mark anything approved; no subagents.

## Progress

- Read task brief, Phase-2 breakdown, reconciliation Phase-2 row, product spec,
  architecture, governance, bootstrap, and required implementation/tests in the
  PH2-A worktree. Confirmed the delegation endpoint remains disabled with 409;
  current source has no active delegation storage/authorization logic.
- Drafted `docs/plans/PHASE2_DELEGATION_SPEC.md` with the eight required areas,
  fail-closed semantics, code-grounded distinctions, and undecided owner items.
- Adversarial self-review: confirmed the draft preserves the existing 409
  disabled delegation endpoint and existing membership/publication/ownership/
  role ceilings; it does not authorize enablement, mark approval, change code,
  or relax tests. Documented the distinction that the source has a 409
  placeholder but no active delegation implementation and that existing role
  and publication data are mutable (the versioned grant model is proposed).
  `git diff --check` passed; a UTF-8/checklist assertion confirmed all eight
  required sections and the explicit 409/exact-expiry semantics. A first
  checklist assertion used a mismatched heading label and failed; the corrected
  section check passed. Fast-forwarded the task worktree to current
  `origin/loop/local-development` before delivery; no conflict.
