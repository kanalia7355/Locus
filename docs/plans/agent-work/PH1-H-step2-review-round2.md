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

- Round-2 independent read-only review — integrated `loop/local-development` HEAD `aaa06c859057aba6d8d745c84776bd0d0e9734e7` (target design history includes `9f3280a` rework and `353136a` CI-evidence correction). Required governance/product/architecture/bootstrap docs, the prior review, fix-cycle notes, target proposal, hybrid requirements, accepted threat model and phase reconciliation were read. No tests were run (design-only review); no reviewed source/design or other file was modified.

  **Round-1 finding verification:** F1 resolved: §3.1 defaults classification to `none`, separates classification from destination authorization, and §3.1/§5.2c require denial before context/attachment handling and on output/citation paths. F2 resolved: §§0, 2.2, 2.6 and §5 specify a job-bound authoritative receipt rechecked before enqueue and runner execution, denial/revocation/staleness cases, explicit Control-Plane dispatch rejection while B6 is active, and the approval ADR prerequisite. F3 substantially resolved: §§2.1, 3.2/E9 and 5.2c bind artifacts to job/runner/workspace/policy, inherit ACL/classification and revalidate before persistence/use/export; cross-workspace, revocation and downgrade tests are specified; T-T4 remains an activation blocker (§§1.2/B7, 3.3, 6.6). See minor finding below for deletion propagation. F4 resolved: §§1.2/B5, 2.1, 2.4–2.5 bind workspace/health/credential metadata to runner instances and explicitly state eligible OS identity, non-exportable broker constraints, and positive/negative activation tests. F5 resolved in §§0 and 6.1: the dual-plane ADR precedes all step-2 implementation. F6 resolved in §§2.1, 3.1, 3.2/E5, 6.7–6.8: `allowlisted` is non-operative pending owner approval, enabling schema is barred, only 公開 is a possible (not approved) future candidate, and cancellation semantics/tests are specified. F7 resolved in §1.1/1.5: `toolless_boundary.py` is launcher/configuration/diagnostic-only; strict enforcement is attributed to `audit_transport.py` and `model_gate.py`, wired by `c_min_runtime.py`. F8 resolved in §1.2/B1 and §5.2b: all import directions, transport-only communication, Plane-M import prohibition, separable primitives/ports, and whole-package graph checks are specified.

  **Additional review checks:** No new weakening of the accepted zero-tool boundary, approval gates, synthetic-data-only rule, or existing tests was found; the proposal repeatedly keeps implementation/activation behind the stated ADR and verification gates. The owner-decision inventory remains marked 【要決定】, including runner trust root, credential mechanism, audit/artifact retention, egress, cancellation, and approval authority; the possible-public egress statement is explicitly not pre-approval. The review-history entry accurately records round 1's 4 high + 4 medium findings and the fix cycle without claiming approval. It does not yet include this round-2 outcome and should be extended when this review is recorded.

  Evidence spot-check: `docs/security/HYBRID_AGENT_THREAT_MODEL.md` §§2–5 and `docs/plans/PHASE_SPEC_RECONCILIATION.md` retain the relevant T-I2 deletion/ACL propagation, T-T4, synthetic-data, and activation constraints. Checked `loop_engine/toolless_boundary.py`, `audit_transport.py`, `model_gate.py`, `c_min_runtime.py`, `codex_runner.py`, `windows_tcp_peer.py`, `app_credentials.py`, `backend/app/service.py`, `backend/app/local_model.py`, and `backend/app/main.py`; these support the proposal's corrected module attribution and its stated limits (current product code does not itself supply the proposed runner/classification/artifact controls).

  **Findings**

  1. **MEDIUM — artifact source-deletion propagation is not explicit.** Location: `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` §3.2/E9 and §5.2c. E9 requires live policy/ACL/revocation checks and acceptance covers cross-workspace access, ACL revocation, stale policy and downgrade, but neither specifies a deleted-source/tombstone check nor a regression for source deletion and resulting artifact use/export. This leaves one part of the round-1 artifact recommendation and the accepted deletion-propagation requirement implicit. **Recommendation:** define deletion as a deny/revocation condition for derived artifacts (including persistence, reuse and export), and add deleted-source/deleted-artifact regressions; keep artifact retention itself as the separate owner decision in §6.6.
  2. **LOW — round-2 review-history entry pending.** Location: `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` §Review history. The existing entry correctly records round 1 → fix and makes no false approval claim, but naturally stops before this round. **Recommendation:** once this verdict is incorporated, append the round-2 verdict and any follow-up resolution so the history covers round 1 → fix → round 2.

  **Verdict: accept after minor fixes.** The eight round-1 findings are resolved in substance. Record this review and add explicit deletion propagation/test criteria; then complete the review-history entry. The design remains non-approving and non-activating.
