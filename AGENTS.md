# Agent entrypoint
Read `docs/governance/DEVELOPMENT_POLICY.md`, `docs/requirements/PRODUCT_SPEC.md`, and `docs/architecture/ARCHITECTURE.md` before acting. Then read `docs/BOOTSTRAP.md`.
On first launch, inspect repository state. If `.bootstrap/complete.json` is absent, execute bootstrap steps, verify and record results; never claim completion without tests. Do not overwrite existing user files without permission. If a decision materially affects confidentiality, security or scope, ask first.
Default to one implementation agent. No spawning or parallel delegation except an isolated read-only reviewer for material architecture changes, security changes, and pre-merge reviews. Maximum two fix/re-review cycles. Reviewer may not modify code or spawn agents. Never bypass hooks or controls.
Do not treat user requests as infallible: identify conflicts, risks and simpler alternatives before implementation. Preserve privacy and deny unauthorized access by default.

For all GitHub operations read `docs/governance/GITHUB_WORKFLOW.md`. Use PRs, Conventional Commits titles, protected branches, and conditional auto-merge only when explicitly authorized.

## UI implementation baseline
For frontend implementation, read `docs/planning/UI_IMPLEMENTATION_BASELINE.md`, inspect `docs/planning/ui-baseline-chat.png`, and read `docs/planning/ui-and-multiuser-design.md`. Preserve the user-approved interface and interactions. The HTML fragment is reference material, not an implemented React application.

## Agent rules
When a repository's documentation and its existing code disagree, follow the conventions used in the existing code, and in your final reply point out each inconsistency you found between the documentation and the code.

## Autonomous loop tasks (additive rules)
For loop-managed work, also inspect the exact Goal, requirements, architecture, acceptance criteria, assigned task, prior failures, allowed paths, pending decisions and relevant `.agents/skills/` before changing code. Preserve the source specifications; generated proposals cannot weaken them. Work only on the assigned task and inspect relevant code before editing. Do not delete/weaken tests to obtain a pass or hide failures. Return the requested structured result; only the deterministic Controller records progress and completion.

No normal-development subagents. Independent architecture/security/quality audits use a separate read-only context and return findings to the implementer. Keep the three-total-attempt/two-review-fix-cycle caps. Never resolve your own approval request, bypass hooks/sandbox/CI, access credentials, force-push, rewrite history or commit directly to main. Conventional Commits apply to commits/PR titles; loop-managed task branches use the user-specified `loop/TASK-ID-slug` prefix. Execution/verification that cannot run safely remains blocked/skipped, never passed.
