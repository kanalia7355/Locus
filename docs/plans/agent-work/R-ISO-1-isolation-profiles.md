# R-ISO-1 — Per-environment isolation profiles and proof plans

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Docs-only task:
do NOT modify code, specs, tests, or the OWNER_DECISION_QUEUE. Never push to
`main` or `loop/local-development`; no subagents of your own. NEVER touch the shared
`.venv`; use `.loop/runtime/qa-venv` if needed.

## Task

Author the per-environment isolation profile design and proof plan per the resumable-jobs
plan (`docs/plans/RESUMABLE_JOBS_2026-11-09.md` §R-ISO-1). The owner's formal decisions
Q1–Q7 are recorded in `docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md`.

**Scope:** Design a profile matrix for Windows/Linux and local/server environments:
- State target/threat assumptions, controls, constraints, and profile-specific independent
  verification evidence for each profile.
- Compare VM and non-VM approaches WITHOUT prescribing a universal VM (owner Q3).
- Provide negative/positive test plans for OS-enforced filesystem, process and network
  boundaries, cleanup, failure behavior and profile claims.
- Profile design and evaluation documentation may start; do NOT activate an unverified
  profile or perform a host execution.
- Explicitly mark any unresolved owner choice (specific isolation technology, trust root,
  enrollment/key management, risk acceptance for unverified profiles) as 【要決定】.

**Owner decision relied on:** Q3 requires environment-appropriate, independently verified
OS-level isolation; no universal VM; an unverified environment remains unavailable. Q4 is
an input to describe adapter constraints only, not credential use.

**Safety boundary that must not change:** no unverified host-direct execution, silent
downgrade, or weakening of ADR-0011/0012/B6; no egress, credentials, dispatch, or real
data; default-deny and fail-closed remain. A design profile is not proof that a platform
passes.

**Output:** Create `docs/plans/HYBRID_ISOLATION_PROFILES.md` (the design package).
This is documentation/design only, not product code.

**Completion gate:** per-profile design states enforceable boundary and limits honestly,
with a source-grounded test/evidence plan and independent review. Each profile remains
**inactive** until exact-platform/build/config evidence passes, required security review
is accepted, and its separate activation decision and all ADR-0012 gates are satisfied.

## Process

Read AGENTS.md + docs/governance/DEVELOPMENT_POLICY.md, then the owner decisions
(docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md), then ADR-0012, ADR-0013, the
isolation/trust proposals (docs/plans/HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md),
and the receipt contract (docs/plans/HYBRID_STEP2_RECEIPT_CONTRACT.md). Self-review
adversarially; run the docs-applicable verification subset (ruff check + ruff format
--check + scripts/secret_scan.py via the qa-venv if needed). Conventional Commit
(`docs(plans): ...`); push origin loop/riso1-isolation-profiles; repeat the fix cycle
until all applicable checks pass. Append progress + SHA + CI evidence to this file under
## Progress at each step end and at task end, and push.

Conventional Commit subject suggestion: `docs(plans): author the per-environment isolation profile design`
