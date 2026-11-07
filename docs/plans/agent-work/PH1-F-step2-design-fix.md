# PH1-F fix cycle 1 — revise the hybrid step-2 design proposal per PH1-H review

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files. Design-only task: no application code changes.

## Task brief

You own `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` (slot F produced it;
it was merged to `loop/local-development` at 77c054d). The independent review
(PH1-H, `docs/plans/agent-work/PH1-H-step2-design-review.md` in the main
checkout) returned **needs major rework** with 8 findings. Revise the document to
resolve them. Work in the existing worktree
`C:/Users/hirot/Locus/.loop/runtime/worktrees/PH1-F-hybrid-step2-design`
(branch `loop/PH1-F-hybrid-step2-design`): first
`git -C C:/Users/hirot/Locus fetch origin && git -C <worktree> reset --hard origin/loop/local-development`
(the integrated HEAD contains both the proposal and the review), then edit.

Findings to resolve (full detail with evidence in PH1-H-step2-design-review.md — read it first):

1. HIGH — classification fail-closed default must be **deny-all (no permitted
   classification) until an administrator explicitly selects a ceiling**;
   classification authorization and egress destination authorization are
   independent gates; add negative acceptance tests for unclassified input denial
   before prompt assembly, attachments, and every output/citation path.
2. HIGH — define an **authoritative job-level approval/authorization receipt**
   (actor, workspace, policy version, adapter/destination, operation) rechecked
   before enqueue AND before runner execution; test denial, revocation, stale
   approval. While B6 is active the Control Plane must REJECT dispatch — do not
   use "no runner exists" as the 2a dispatch test. The separate approval ADR is a
   hard prerequisite to any dispatch-capable code.
3. HIGH — define **runner-output artifact enforcement**: artifact identity bound
   to originating workspace + policy version, ACL/classification inheritance and
   revalidation before persistence/use/export; cross-workspace, revocation and
   downgrade regressions. T-T4 audit-log protection stays an activation blocker.
4. HIGH — define a **runner-instance identity**; bind workspace binding, adapter
   health and credential-presence metadata to it (not adapter_id alone); state
   precisely which OS identity may use the official CLI credential store and how
   a compromised runner is prevented from exporting it; activation blocked until
   the selected OS mechanism is tested for access AND denial.
5. MEDIUM — the dual-plane ADR must **precede ALL step-2 implementation** (the
   accepted threat-model recommendation), not only slice 2b. Adopt the stricter
   sequencing; do not weaken the accepted recommendation.
6. MEDIUM — mark `allowlisted` egress as a **non-operative placeholder
   conditional on owner approval**; prohibit producing an enabling policy/schema
   until decided; state which classifications could ever be eligible; add
   explicit cancellation semantics to the §6.8 admission-limit item (T-D1).
7. MEDIUM — correct the module map: `loop_engine/toolless_boundary.py` is
   launcher/configuration/diagnostic-probe only; the strict C-min
   request/response enforcement is `loop_engine/audit_transport.py` +
   `loop_engine/model_gate.py`, wired by `loop_engine/c_min_runtime.py`.
8. MEDIUM — strengthen slice 2b B1 acceptance: reverse `runner/` → `backend/app/`
   prohibition, transport-only Control-Plane/Runner boundary, `backend/app/agents/`
   must not import Plane-M model-path code; define separable importable primitives
   or an explicit dependency interface; add a whole-package static import-graph
   test covering all B1 directions.

Rules: do not weaken any approved boundary or the accepted threat-model
recommendations; items that remain owner decisions stay in §6 marked 【要決定】
(you may add new ones surfaced by the fixes, e.g. runner trust root, artifact
retention); update §8 self-review notes to reference the PH1-H findings and how
each is resolved. Record the review round (PH1-H needs-major-rework → this fix)
in a short review-history section of the document, like the threat model does.

Process: read PH1-H review + current document → revise → adversarial
self-review against all 8 findings and the threat model → Conventional Commit
(`docs(plans): rework hybrid step-2 design per independent review`) → push
`loop/PH1-F-hybrid-step2-design` to origin → CI billing-blocked ⇒ record blocked,
never passed → append progress + final SHA here.

Boundaries: never push to `main` or `loop/local-development`; no code changes;
do not modify the review file; do not spawn subagents.
