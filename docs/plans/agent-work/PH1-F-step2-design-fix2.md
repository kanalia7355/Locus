# PH1-F fix cycle 2 — minor fixes from the round-2 review

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files. Design-only task: no application code changes.

## Task brief

Round 2 of the independent review (`docs/plans/agent-work/PH1-H-step2-review-round2.md`
in the main checkout) returned **accept after minor fixes**: all 8 round-1
findings resolved in substance, no new weakening. Two follow-ups:

1. MEDIUM — Specify and test **deletion propagation for runner-output
   artifacts**, including denial of reuse/export after source deletion.
   Update `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md`: extend the artifact
   enforcement section (around §3.2 E-artifact / slice 2c acceptance) with
   deletion-propagation semantics (artifact lifecycle bound to source data and
   workspace policy version; deletion/revocation of sources or workspace must
   invalidate derived artifacts before any reuse/export/read; regression tests
   listed in the slice 2c plan). Keep 【要決定】 discipline: retention/deletion
   policy numbers stay owner decisions if they are not already covered.
2. LOW — Add the round-2 outcome to the document's review history section
   (round 1 needs-major-rework → fix cycle 1 → round 2 accept after minor
   fixes → fix cycle 2 (this change) → considered accepted per the reviewer's
   conditional verdict; final approval of the ADR remains the owner's).

Setup: work in the existing worktree
`C:/Users/hirot/Locus/.loop/runtime/worktrees/PH1-F-hybrid-step2-design`
(branch `loop/PH1-F-hybrid-step2-design`). First
`git -C C:/Users/hirot/Locus fetch origin && git -C <worktree> merge --ff-only origin/loop/local-development`
to pick up the round-2 review file; if ff-only fails, STOP and record it (do not
force-push).

Then: make the two edits, adversarial self-review, Conventional Commit
(`docs(plans): add artifact deletion propagation per round-2 review`), push,
wait for branch CI, fix and re-push until ALL checks green (bounded; record if
blocked). Append progress + final SHA + CI evidence to this file's ## Progress.

Boundaries: never push to `main` or `loop/local-development`; no code changes;
do not modify the review files; no force-push; do not spawn subagents.

## Progress

- Setup complete: fetched `origin` and fast-forwarded this worktree from `890f235` to `590f40a` (`origin/loop/local-development`); branch is `loop/PH1-F-hybrid-step2-design`, worktree was clean before edits. Read the task brief, round-2 review, required governance/product/architecture/bootstrap documents, and GitHub workflow. No review files or application code will be changed.
- Design edits and adversarial self-review complete: artifacts are bound to source identities and exact workspace policy version; source/workspace deletion or revocation and policy-version changes invalidate artifacts before persistence, reuse, export or read. Slice-2c regressions cover deletion/revocation before persistence and after production, deny read/reuse/export before payload access, and leave physical-deletion/retention timing as owner decisions. Review history records the conditional round-2 verdict and owner ADR approval. `git diff --check` passes; no application tests were run for this docs-only change.
- Conventional Commit `a362b91d4687fa61bb150607f56cec3b066b7eb6` (`docs(plans): add artifact deletion propagation per round-2 review`) was pushed to `loop/PH1-F-hybrid-step2-design`. All Actions checks on that task commit passed: Loop engine checks run [42331808217](https://github.com/kanalia7355/Locus/actions/runs/42331808217), Prototype quality run [42331808234](https://github.com/kanalia7355/Locus/actions/runs/42331808234), and PR title convention run [42331808283](https://github.com/kanalia7355/Locus/actions/runs/42331808283). No CI failures or fixes/re-pushes were needed. This is the final design-content SHA; the progress-record update is a separate documentation-only commit.
