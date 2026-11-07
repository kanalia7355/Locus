# PH1-E2 — Independent read-only review of the dual-plane ADR-0012 draft

Agent: append your progress under "## Progress" below. You are a REVIEWER: do
not modify any file other than this one (your progress notes), do not spawn
agents, do not push, do not create a persistent worktree. Work in the main
checkout read-only.

## Task brief

Review `docs/architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md`
(DRAFT) at the integrated HEAD of `loop/local-development` (commit d14b88d or
later). It is the dual-plane decision record drafted by PH1-A2 as the hard
prerequisite before any hybrid step-2 implementation, per the accepted threat
model (follow-up 2) and the stricter sequencing adopted in review round 1
(finding 5).

Review criteria:
1. **Accuracy**: spot-check citations (ADR-0011 file and its normative content;
   `loop_engine/audit_transport.py`, `loop_engine/model_gate.py`,
   `loop_engine/c_min_runtime.py`, `loop_engine/toolless_boundary.py`) — the ADR
   must attribute the strict C-min enforcement correctly (round-1 finding 7 of
   the step-2 design review).
2. **Boundary preservation**: the ADR must freeze Plane M with no behavioral
   change, keep Plane R fail-closed (no dispatch-capable code before the
   approval-receipt ADR), and incorporate the round-1/round-2 corrections of the
   step-2 design (deny-all classification default, job-level approval receipt
   prerequisite, runner-instance identity, artifact enforcement + deletion
   propagation, import-graph tests in all directions). Flag ANY weakening.
3. **Decision discipline**: nothing is marked accepted; every 【要決定】 item of
   the step-2 design remains an owner decision; the ADR itself requires
   independent review (this review) and owner approval.
4. **Consistency**: with the accepted threat model, the step-2 design (reworked),
   the hybrid requirements doc, and PHASE_SPEC_RECONCILIATION.
5. **Actionability**: are the consequences and verification sections concrete
   enough for the owner to approve or reject?

Verdict: accept / accept after minor fixes / needs major rework. Findings with
severity, location, evidence, fix recommendation. Do not edit the ADR.

## Progress

- **Independent read-only review — integrated `loop/local-development` HEAD `fa6e7c5`** (includes target integration commit `d14b88d`; target ADR is unchanged in the worktree). Read the required governance/product/architecture/bootstrap documents, ADR-0011, the accepted hybrid threat model, reworked step-2 design, both PH1-H reviews, hybrid requirements, and phase reconciliation. No tests were run (documentation/design review); only this progress section was modified.

  **Criteria summary:** Citation attribution is accurate: ADR-0011's accepted C-min scope is described correctly, and strict request/response enforcement is attributed to `loop_engine/audit_transport.py` and `loop_engine/model_gate.py`, wired by `loop_engine/c_min_runtime.py`; `loop_engine/toolless_boundary.py` is correctly identified as launcher/configuration/diagnostic-probe code. Source spot-checks support these roles. Plane M is frozen and its four named zero-tool regression files exist; no weakening of the accepted gate, approval receipts, synthetic-data-only constraint, or tests was found. Plane R is separate and fail-closed; the draft includes B1 checks in both directions, deny-all classification independent of egress, job-bound receipt checks at enqueue and execution, instance-bound runner identity, artifact ACL/classification/deletion propagation, and T-T4 as an activation blocker. It remains a DRAFT, marks nothing accepted, leaves the step-2 §6 owner decisions unresolved, and requires independent review and owner approval. The proposal is detailed and actionable overall.

  **Findings**

  1. **MEDIUM — explicitly encode the hard sequencing gate.** Location: ADR §Context (lines 24–35), §Consequences, and §Verification requirements. The ADR says the threat model *recommends* this ADR before step 2, while the reworked design makes adoption and approval a hard prerequisite to **all** step-2 implementation, including metadata-only slice 2a (`docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` §§0, 6.1; PH1-H round 2 finding F5). The ADR separately makes the approval/authorization ADR a hard prerequisite to dispatch-capable code, but does not itself clearly state that no step-2 implementation may start before this ADR is adopted; its verification heading is scoped to Plane-R implementation/activation. This is an omission rather than an explicit permission to proceed, but weakens actionability of the sequencing gate. **Recommendation:** state in the proposed decision/forbidden consequences that owner adoption of ADR-0012 must precede every step-2 implementation (including 2a), and that adopting ADR-0012 does not itself approve implementation or activation.
  2. **MEDIUM — preserve the mandatory cancellation semantics, distinct from owner-selected mechanisms.** Location: ADR §Owner decisions deliberately left open, item 8 (lines 215–218). It lists limits, fairness, cancellation actors/signaling, timeout and recovery as open, but omits the safety semantics that the reworked design already requires in §6.8: queued cancellation atomically prevents dispatch; executing cancellation is not terminal and does not release capacity until runner-confirmed termination; dispatch/cancel races are serialized; repeats are idempotent; and timeout/missing acknowledgment fences the runner/job and holds its reservation until safe termination. The current shorthand could be read as leaving those guarantees open for decision, not only their implementation and values. **Recommendation:** retain only limits, actors, signaling, timeout/recovery choices as owner decisions and explicitly preserve the §6.8 invariants and acceptance tests as requirements.

  **Verdict: accept after minor fixes.** The two findings are focused completeness/precision fixes; no substantive Plane-M/Plane-R boundary weakening or decision-discipline violation was found. No reviewed source or design file was modified.
