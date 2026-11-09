# R-ISO-2 — Isolation engineering details classified ENGINEERING_DETAIL

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Docs-only task:
do NOT modify code, specs, tests, or the OWNER_DECISION_QUEUE. Never push to
`main` or `loop/local-development`; no subagents of your own. NEVER touch the shared
`.venv`; use `.loop/runtime/qa-venv` if needed.

## Task

Produce comparison, test-inventory, evidence-binding, and profile-conformance details
ONLY for isolation items explicitly classified as `ENGINEERING_DETAIL` in
`docs/plans/OWNER_QUEUE_CLASSIFICATION_2026-11-09.md`. The owner's formal decisions
Q1–Q7 are recorded in `docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md`.

**Scope:**
- Work only the isolation details classified `ENGINEERING_DETAIL` that do NOT depend on
  an unresolved owner choice.
- Do NOT decide unresolved trust/enrollment/key custody, support authorization, provider
  credential supply, endpoint/egress, or risk acceptance for an unverified profile.
- Do NOT decide numerical bounds for any item classified OWNER_DECISION_REQUIRED.
- Produce comparison tables, test-inventory criteria, evidence-binding contracts, and
  profile-conformance checklists for the engineering-detail items only.
- Explicitly mark any emerging policy/scope choice as 【要決定】 and split it out.

**Owner decision relied on:** Q3's approved per-environment verified-profile direction;
Q4's official CLI preference (describes adapter constraints only, does NOT authorize
provider authentication or credentials).

**Safety boundary that must not change:** independent proof for the exact environment;
unverified profiles unavailable; no host fallback; no dispatch before the receipt and
ADR-0012 gates; no egress or credentials.

**Output:** Create `docs/plans/HYBRID_ISOLATION_ENGINEERING_DETAIL.md` (the design
package). This is documentation/design only, not product code.

**Completion gate:** reviewed comparison/test criteria are reproducible, evidence-bound
to the claimed environment, and do not claim profile activation. Any unresolved
authority, trust or policy item remains explicitly gated.

## Process

Read AGENTS.md + docs/governance/DEVELOPMENT_POLICY.md, then the owner decisions
(docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md), then the classification record
(docs/plans/OWNER_QUEUE_CLASSIFICATION_2026-11-09.md) to identify exactly which
isolation rows are ENGINEERING_DETAIL, then the isolation profile design
(docs/plans/HYBRID_ISOLATION_PROFILES.md) and the trust proposals
(docs/plans/HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md). Self-review adversarially;
run the docs-applicable verification subset (ruff check + ruff format --check +
scripts/secret_scan.py via the qa-venv if needed). Conventional Commit
(`docs(plans): ...`); push origin loop/riso2-isolation-engineering; repeat the fix
cycle until all applicable checks pass. Append progress + SHA + CI evidence to this
file under ## Progress at each step end and at task end, and push.

Conventional Commit subject suggestion: `docs(plans): author isolation engineering detail design`
