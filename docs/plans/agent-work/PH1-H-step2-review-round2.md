# PH1-H round 2 — Re-review of the reworked hybrid step-2 design proposal

Agent: append your progress under "## Progress" below. You are a REVIEWER: do
not modify any file other than this one (your progress notes), do not spawn
agents, do not push, do not create a persistent worktree. Work in the main
checkout read-only.

## Task brief

This is round 2 of the independent review of
`docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md`, now at the integrated HEAD
of `loop/local-development` (commit fbe7bf4 or later, including the fix-cycle
rework at 9f3280a). Round 1 (PH1-H-step2-design-review.md) returned
**needs major rework** with 8 findings. The fix cycle (PH1-F-step2-design-fix.md)
claims all 8 were resolved.

Review:
1. Verify each of the 8 round-1 findings is actually resolved in the reworked
   document (read both review files and the document):
   - F1 classification deny-all default + independent egress gate + negative tests
   - F2 job-level approval receipt rechecked at enqueue AND runner execution;
     reject-dispatch-while-B6-active tests; approval ADR as hard prerequisite
   - F3 runner-output artifact identity/ACL/classification enforcement + regressions;
     T-T4 stays an activation blocker
   - F4 runner-instance identity binding (workspace/health/credential-presence)
     + explicit OS credential access/denial statement
   - F5 dual-plane ADR before ALL step-2 implementation
   - F6 allowlisted egress non-operative placeholder + cancellation semantics (T-D1)
   - F7 corrected module attribution (audit_transport.py/model_gate.py/c_min_runtime.py)
   - F8 strengthened B1 import-graph acceptance in all directions
2. Check no NEW weakening was introduced by the rework (approved boundaries,
   accepted threat-model recommendations, existing tests).
3. Check 【要決定】 discipline still holds (new owner decisions surfaced by the
   fixes are listed, not decided).
4. Verify the review-history section accurately records round 1 → fix → round 2.

Verdict options: accept / accept after minor fixes / needs major rework.
Findings with severity (critical/high/medium/low), location, evidence, fix
recommendation. Do not edit the reviewed document.

## Progress

- (reviewer appends here)
