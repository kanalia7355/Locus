# R-2B-1 — Receipt contract and hybrid step-2 (2b) design package

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Docs-only task:
do NOT modify code, specs, tests, or the OWNER_DECISION_QUEUE. Never push to
`main` or `loop/local-development`; no subagents of your own. NEVER touch the shared
`.venv`; use `.loop/runtime/qa-venv` if needed.

## Task

Author the receipt contract and hybrid step-2 (2b) design package per the resumable-jobs
plan (`docs/plans/RESUMABLE_JOBS_2026-11-09.md` §R-2B-1). The owner's formal decisions
Q1–Q7 are recorded in `docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md`.

**Scope:** Draft/reconcile the logical receipt and job-envelope contract against
ADR-0012 §4.1, ADR-0013, and step-2 §§2.1/2.6/3.2/6.11:
- Trace the exact job, actor, workspace, policy-version, adapter, destination and
  operation bindings.
- Define the control-plane and runner enforcement-point responsibilities (E1, E2).
- Describe automated issuance only inside current policy and authority (owner Q1).
- Document online/current authorization and audit requirements.
- Separate mandatory ADR-0012 semantics from contract details.
- Explicitly mark any unresolved owner choice (e.g. receipt TTL values, new permissions,
  Runner trust/enrollment/key custody, provider credential supply) as 【要決定】.

**This is design documentation only.** Do NOT write receipt code, dispatch-capable tests,
key provisioning, Runner activation, or any schema enabling execution.

**Safety boundaries that must not change:** ADR-0011 Plane-M zero-tool behavior;
ADR-0012 dual-plane separation and mandatory authoritative receipt; E1 recheck before
enqueue and independent E2 recheck before execution; B6 explicit dispatch rejection;
default-deny/no-egress; fail-closed on denial, stale policy, mismatch, revocation or
unavailable authority; no credential bytes or content in receipts/audit.

**Output:** Create `docs/plans/HYBRID_STEP2_RECEIPT_CONTRACT.md` (the design package).
This is documentation/design only, not product code.

**Owner decisions relied on:** Q1 (automatic approval only inside a current,
administrator-approved policy/scope); Q2 (personal Workspace owner authority stays
within upper policy limits); Q4 (official-CLI/no-credential-mixing constraint).

**Completion gate:** source-linked, internally consistent design reviewed against
ADR-0012/0013 and step-2, with every owner-controlled open point visibly marked
【要決定】 and no activation claim. Any 2b dispatch-capable implementation remains
blocked until the owner-approved receipt contract and separate slice authorization
exist; dispatch stays disabled until the ADR-0012 activation gate and all its
verification/authorization gates pass.

## Process

Read AGENTS.md + docs/governance/DEVELOPMENT_POLICY.md, then the owner decisions
(docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md), then ADR-0012, ADR-0013, and
the relevant step-2 sections. Self-review adversarially; run the docs-applicable
verification subset (ruff check + ruff format --check + scripts/secret_scan.py via
the qa-venv if needed). Conventional Commit (`docs(plans): ...`); push origin
loop/r2b1-receipt-design; repeat the fix cycle until all applicable checks pass.
Append progress + SHA + CI evidence to this file under ## Progress at each step end
and at task end, and push.

Conventional Commit subject suggestion: `docs(plans): author the receipt contract and 2b design package`
