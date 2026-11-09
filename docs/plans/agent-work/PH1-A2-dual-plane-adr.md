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

## Progress

- 2026-11-08: Read the full task brief and required governance/product/architecture/bootstrap docs. Confirmed `.bootstrap/complete.json` exists and did not start bootstrap. Main checkout has pre-existing modifications/untracked files; left those untouched except for this explicitly requested progress log. Created `C:/Users/hirot/Locus/.loop/runtime/worktrees/PH1-A2-dual-plane-adr` on `loop/PH1-A2-dual-plane-adr` from `origin/loop/local-development` at `aaa06c8`.
- 2026-11-08: Read the accepted threat model, reworked step-2 design, and both PH1-H review briefs. Captured the mandatory fixes for the ADR: receipt per job rechecked at dispatch and execution; B6 explicit dispatch rejection; deny-all classification independent of egress; per-instance runner identity; artifact binding/enforcement; and whole-package import-graph coverage in all directions.
- 2026-11-08: Read all ADRs in `docs/architecture/` and `docs/architecture/decisions/`, the hybrid requirements, phase reconciliation, and the round-2 reviewer result in the main checkout. Round 2 verdict is accept after minor fixes; its additional medium item requires source-deletion propagation tests for artifacts, which will also be carried into this ADR without deciding retention policy. The integrated base advanced to `590f40a` after worktree creation, so rebased the clean task branch onto `origin/loop/local-development` before drafting.
- 2026-11-08: Drafted `docs/architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md`. Adversarial self-review checked B1–B7 and all round-1/round-2 corrections, owner-decision discipline, explicit B6 rejection with a present Runner, artifact source deletion, and no activation/acceptance claim. Static content checks and all four relative source links passed. Docs-only change; application tests were not run. Coordinated with the concurrent PH1-F fix2 agent; no file overlap, and artifact deletion obligations are consistent.
- 2026-11-08: Committed the docs-only change as `124e20c` (`docs(adr): draft the dual-plane decision record`); `git diff --cached --check` was clean and only the new ADR was staged.
- 2026-11-08: Pushed only `loop/PH1-A2-dual-plane-adr` to `origin`. Final SHA: `124e20c2b1add546d622ac15463399e686d80f3b`. Branch CI completed successfully on this exact SHA: [PR title convention](https://github.com/kanalia7355/Locus/actions/runs/42331684402), [Prototype quality](https://github.com/kanalia7355/Locus/actions/runs/42331684414), [Loop engine checks](https://github.com/kanalia7355/Locus/actions/runs/42331684411). No CI repairs/re-push were needed; no push to `main` or `loop/local-development` occurred.
- 2026-11-08: Final check confirmed the worktree is clean, the local branch and `origin/loop/PH1-A2-dual-plane-adr` both resolve to `124e20c2b1add546d622ac15463399e686d80f3b`, and all three successful CI runs are bound to that SHA.
- 2026-11-08: PH1-E2 fix cycle — fetched `origin` and fast-forwarded the task worktree from `124e20c` to `origin/loop/local-development` at `300d848`. Applied exactly the two MEDIUM review fixes to ADR-0012: explicit ADR approval/adoption before every step-2 implementation (including metadata-only slice 2a), and mandatory cancellation-safety semantics with only mechanisms/limits left for owner decision. Kept DRAFT; no owner decisions made. Adversarial self-review checked the sequencing statements against step-2 §§0/6.1, the cancellation invariants/tests against §6.8, and confirmed no Plane M/Plane R weakening or changes outside the ADR. `git diff --check` and ADR content assertions passed; no application tests run (docs-only).
- 2026-11-08: Committed `docs(adr): apply review fixes to the dual-plane decision record` as final ADR SHA `08b05d327e3f9d9714526c32c2d1f2806e6b78d4` and pushed only `loop/PH1-A2-dual-plane-adr` (no force-push; no push to `main` or `loop/local-development`). All branch checks passed on that exact SHA: [PR title convention](https://github.com/kanalia7355/Locus/actions/runs/42333833326), [Prototype quality](https://github.com/kanalia7355/Locus/actions/runs/42333833323), [Loop engine checks](https://github.com/kanalia7355/Locus/actions/runs/42333833337). No CI failures, repairs or follow-up pushes were needed. Worktree and remote branch both resolved to the final SHA after CI.
