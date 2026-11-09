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

## Progress

### 2026-11-09 — implementation + self-review + QA + delivery complete; CI queued

- **Implementation:** authored `docs/plans/HYBRID_STEP2_RECEIPT_CONTRACT.md`
  (633 lines) reconciling the logical receipt/job-envelope contract against
  ADR-0012 §4.1, ADR-0013 (DRAFT), step-2 §§2.1/2.2/2.6/3.1/3.2/3.3/6/6.11, owner
  Q1–Q7 and the DP classification record. Contents: decision-tier taxonomy
  (Tier-0 ADR-0012 invariants I-1…I-10 / owner-resolved Q1-Q2-Q4 / engineering
  detail per classification / 【要決定】); receipt and job-envelope logical field
  tables with full binding trace (job, actor, approver/authority, workspace,
  policy version, adapter, destination, operation, runner instance) mapped to E1
  and E2; automated issuance strictly inside current policy/authority (owner Q1,
  Q2 personal scope, DP-004…023); online/current authorization and revocation
  visibility (DP-007/008/009, fail-closed on unavailable authority); fail-closed
  semantics matrix; audit requirements (`agent.receipt.*`, immutable events,
  no credential bytes); mandatory-vs-contract-detail separation; 【要決定】
  inventory (9 items: receipt TTL values DP-010/011, new permissions DP-021,
  Runner trust/enrollment/key custody, provider credential supply DP-034b,
  external communication DP-031/032, unverified isolation profiles, retention
  DP-022, real data/production Q7, any boundary change). No code, no schema, no
  dispatch-capable test, no key provisioning, no Runner activation.
- **Adversarial self-review:** recorded in the document §12 (Q1 over-read risk,
  tier-leakage risk, tension honesty, E2-reachability circularity, scope
  discipline). Verified source citations against `backend/app/agents/registry.py`
  (`dispatch_attempt` ~716, `workspace_policies` triggers ~99–117, presence-only
  credentials ~53/186, placeholder `job_authorization_receipts` ~161) and
  `backend/app/service.py` (`NON_ADMIN` ~25, `_delegation_now` ~1073,
  `_delegation_authority` ~1042, delegation TTL 900–604800 s ~1341). Four
  documentation/code tensions recorded (incl. slice-2a placeholder table vs
  ADR-0013's "no receipt table" statement and the mutable `revoked` column vs the
  immutable-event convention).
- **QA (local, applicable docs subset):** `ruff check .` → All checks passed;
  `ruff format --check docs/plans/HYBRID_STEP2_RECEIPT_CONTRACT.md` → already
  formatted (full-tree check shows 1 PRE-EXISTING failure in
  `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315`, a file this task must not
  touch); `scripts/secret_scan.py` via a task-local `.loop/runtime/qa-venv`
  (Python 3.13, detect-secrets installed; the shared `.venv` was never used) →
  "Offline secret scan: 0 findings", exit 0.
- **Delivery:** commit `1e51bae9a42c3a40957ae3f7ab38dd73fcaeb81e`, subject
  `docs(plans): author the receipt contract and 2b design package`, pushed to
  `origin loop/r2b1-receipt-design` (new branch; main and loop/local-development
  untouched).
- **CI evidence:** run 42637449714 ("Loop engine checks") queued for the SHA at
  2026-11-09T14:43:23Z; result to be appended below when observed. Queued ≠
  passed.
- **Status:** completion gate satisfied on the design side (source-linked,
  internally consistent, every owner open point marked 【要決定】, no activation
  claim). 2b dispatch-capable implementation remains blocked until the
  owner-approved receipt contract and separate slice authorization exist.

### 2026-11-09 — TASK END: CI green for the delivered SHA

- **CI evidence for `1e51bae9a42c3a40957ae3f7ab38dd73fcaeb81e`** (all observed
  `completed success` on GitHub Actions, run at 2026-11-09T14:43Z):
  - PR title convention — run 42637449704 — success (10 s)
  - Prototype quality — run 42637450021 — success (3 m 7 s)
  - Loop engine checks — run 42637449714 — success (7 m 2 s)
  - Full CI for the SHA **passed**; no billing block this time (contrast with the
    older billing-blocked history recorded in step-2 design §4). No fix cycle was
    needed: local checks and CI were green on the first delivery.
- **Note on the local format check:** the full-tree `ruff format --check` shows one
  pre-existing would-reformat in `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315`
  (outside this task's files and not modified); CI's checks for this SHA passed,
  and the delivered file itself is ruff-clean.
- **Task outcome:** deliverable `docs/plans/HYBRID_STEP2_RECEIPT_CONTRACT.md`
  complete at `1e51bae9a42c3a40957ae3f7ab38dd73fcaeb81e` on
  `loop/r2b1-receipt-design`, pushed. Remaining pipeline steps (independent
  read-only review, integration) belong to later slots; dispatch stays disabled
  and every §9 【要決定】 item remains with the owner.
