# PH1-A (slot A, 2nd task) — Dual-plane ADR draft (hybrid prerequisite)

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files. Design-only task: no application code changes.

## Task brief

Goal: draft the **dual-plane ADR** that the accepted threat model lists as
follow-up 2 and the reworked step-2 design now requires as a hard prerequisite
BEFORE any hybrid step-2 implementation (`docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md`
§1 and §6.1 at `loop/local-development` HEAD aaa06c8 or later). This ADR makes
the model-facing zero-tool boundary vs. tool-executing Agent Runtime split an
approved decision.

Setup: create your own worktree: `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-A2-dual-plane-adr -b loop/PH1-A2-dual-plane-adr origin/loop/local-development` (if it already exists, reuse it). Work ONLY inside it.

First read: `docs/security/HYBRID_AGENT_THREAT_MODEL.md` (accepted after minor fixes),
`docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` (reviewed round 2, accept after
minor fixes — read the two PH1-H review files for context), ADR-0011 and the other
ADRs under `docs/architecture/`, `docs/architecture/decisions/`, existing ADR file
naming/format conventions, `docs/planning/locus-hybrid-agent-requirements.md`,
`docs/plans/PHASE_SPEC_RECONCILIATION.md`.

Deliverable: `docs/architecture/decisions/` ADR draft (follow the existing ADR
numbering/format exactly; likely next number) titled around **model-facing gate vs.
tool-executing agent runtime (dual-plane)**. Content requirements:
1. Status/Context: cite ADR-0011's C-min zero-tool boundary, the threat model's
   dual-plane consistency finding, and the hybrid requirements doc.
2. Decision: the two planes are separate module trees that must never be merged;
   Plane M frozen (no behavioral change); Plane R introduced only behind
   fail-closed boundaries (B1–B7 as proposed in the step-2 design, with the
   round-1/round-2 review corrections incorporated: job-level approval receipt
   prerequisite, deny-all classification default, runner-instance identity,
   artifact enforcement, static import-graph tests in all directions).
3. Consequences: what becomes possible, what stays forbidden, what requires
   further owner decisions (reference the step-2 design §6 【要決定】 items; do
   not decide them here).
4. Verification: the regression plan (existing zero-tool tests must pass
   unchanged; import-graph static tests; reject-dispatch-while-B6-active).
5. Review history: note it is a DRAFT requiring independent review before
   approval; do not mark it Accepted.

Self-review against the threat model and the two PH1-H reviews. Then:
Conventional Commit (`docs(adr): draft the dual-plane decision record`), push
`loop/PH1-A2-dual-plane-adr` to origin, wait for the branch CI, fix failures and
re-push until all checks green (bounded), and record progress + final SHA +
CI evidence here. CI failures caused by a pre-existing main-line defect may be
repaired in your branch ONLY if they are test/lint-level; record any such repair.

Boundaries: never push to `main` or `loop/local-development`; no application
code changes; do not modify the approved threat model or the step-2 design; do
not mark the ADR accepted; do not spawn subagents.
