# R-ISO-1 — Per-environment isolation profiles and proof plans

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Docs-only task:
do NOT modify code, specs, tests, or the OWNER_DECISION_QUEUE. Never push to
`main` or `loop/local-development`; no subagents of your own. NEVER touch the shared
`.venv`; use `.loop/runtime/qa-venv` if needed.

## Task

Author the per-environment isolation profile design and proof plan per the resumable-jobs
plan (`docs/plans/RESUMABLE_JOBS_2026-11-09.md` §R-ISO-1). The owner's formal decisions
Q1–Q7 are recorded in `docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md`.

**Scope:** Design a profile matrix for Windows/Linux and local/server environments:
- State target/threat assumptions, controls, constraints, and profile-specific independent
  verification evidence for each profile.
- Compare VM and non-VM approaches WITHOUT prescribing a universal VM (owner Q3).
- Provide negative/positive test plans for OS-enforced filesystem, process and network
  boundaries, cleanup, failure behavior and profile claims.
- Profile design and evaluation documentation may start; do NOT activate an unverified
  profile or perform a host execution.
- Explicitly mark any unresolved owner choice (specific isolation technology, trust root,
  enrollment/key management, risk acceptance for unverified profiles) as 【要決定】.

**Owner decision relied on:** Q3 requires environment-appropriate, independently verified
OS-level isolation; no universal VM; an unverified environment remains unavailable. Q4 is
an input to describe adapter constraints only, not credential use.

**Safety boundary that must not change:** no unverified host-direct execution, silent
downgrade, or weakening of ADR-0011/0012/B6; no egress, credentials, dispatch, or real
data; default-deny and fail-closed remain. A design profile is not proof that a platform
passes.

**Output:** Create `docs/plans/HYBRID_ISOLATION_PROFILES.md` (the design package).
This is documentation/design only, not product code.

**Completion gate:** per-profile design states enforceable boundary and limits honestly,
with a source-grounded test/evidence plan and independent review. Each profile remains
**inactive** until exact-platform/build/config evidence passes, required security review
is accepted, and its separate activation decision and all ADR-0012 gates are satisfied.

## Process

Read AGENTS.md + docs/governance/DEVELOPMENT_POLICY.md, then the owner decisions
(docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md), then ADR-0012, ADR-0013, the
isolation/trust proposals (docs/plans/HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md),
and the receipt contract (docs/plans/HYBRID_STEP2_RECEIPT_CONTRACT.md). Self-review
adversarially; run the docs-applicable verification subset (ruff check + ruff format
--check + scripts/secret_scan.py via the qa-venv if needed). Conventional Commit
(`docs(plans): ...`); push origin loop/riso1-isolation-profiles; repeat the fix cycle
until all applicable checks pass. Append progress + SHA + CI evidence to this file under
## Progress at each step end and at task end, and push.

Conventional Commit subject suggestion: `docs(plans): author the per-environment isolation profile design`

## Progress

- 2026-11-09 — Step 1 (source and scope review) complete. Read the repository entrypoint and development policy, Q1–Q7, the exact R-ISO-1 brief, resumable-jobs plan, product/architecture requirements, loop acceptance and skill, OWNER_QUEUE_CLASSIFICATION, ADR-0011/0012/0013, step-2 registry design and receipt contract, step-3 isolation/trust proposals, and hybrid threat model. Confirmed this worktree is `loop/riso1-isolation-profiles`, initially clean at `9ed75bbbc87e90b49058a7c49b8aac2c1ac46b8e`, with bootstrap complete. No runtime/profile execution, egress, credentials, dispatch or real data used. Design guardrail: compare approaches without selecting one; distinguish desktop/server assumptions; profile proof must bind to exact builds/configuration and remain inactive pending gates. The step-3 proposal's VM-first candidate is a comparison, not authority to impose a universal VM. Source consistency note for the design: ADR-0013 is still marked DRAFT; isolation profiles do not resolve or depend on its open contract. CI evidence not yet available.
- 2026-11-09 — Step 2 (design authoring and adversarial self-review) complete. Added `docs/plans/HYBRID_ISOLATION_PROFILES.md` with four distinct inactive profiles (Windows/Linux × local/server), target/threat assumptions, option comparisons that do not select a universal VM, filesystem/process/network boundaries, positive and negative verification cases, failure/cleanup semantics, exact evidence-binding requirements, residual-risk and activation gates, and explicit 【要決定】 owner choices. Self-review checked against ADR-0011/0012, step-2 E2/E4/E5, Q3/Q4, trust/receipt proposal boundaries, ADR-0006 incomplete Windows probe, and narrow Docker-QA precedent. No host execution/evaluation or independent review was performed; independent security review remains required before activation. No code, tests, specs, or owner-queue changes. Initial QA evidence: `ruff check .` passed. Whole-repo `ruff format --check .` reports the pre-existing unformatted `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315`; its committed baseline also fails the same check. Both changed Markdown paths pass `ruff format --check` and `ruff check`. `git diff --check` passed. `python scripts/secret_scan.py` did not run successfully because this checkout lacks `detect_secrets` and `.loop/runtime/qa-venv`; no shared `.venv` was touched. The requested disposable `.loop/runtime/qa-venv` does not exist; system Python 3.10 provides Ruff but neither Python 3.10 nor 3.13 has `detect_secrets`. I did not provision via network or inspect/use the shared `.venv`, because this scope forbids egress. Secret scan remains blocked by missing dependency; report as not passed. No CI run/evidence exists before branch push. Next: finish local path/link/content checks, commit the two scoped docs, push only this task branch, then record actual remote/CI result without claiming unavailable checks passed.
- 2026-11-09 — Step 3 (final local QA) complete. `ruff check .` passed; changed-document `ruff format --check` passed; whole-repository format check has the documented pre-existing failure at `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315` (also fails on the committed baseline). `git diff --check` passed and all relative Markdown links in the new design resolve. Design SHA-256: `c795827333e5c5955cb93aad89e85191829dcfb4c0bf2f59eba3b5fc852791c8`. Secret scan remains blocked/not passed because `detect_secrets` is unavailable and the task QA venv does not exist; no shared environment or network used. CI not yet available. Proceed to Conventional Commit and task-branch push.
- 2026-11-09 — Step 4 (delivery preparation) complete. Created Conventional Commit `398fd16a2ba4b967e315f1e0c940c711082f632e` (`docs(plans): author per-environment isolation profiles`) containing only the requested design and this task log. Confirmed staged diff has only those two allowed documentation paths, no whitespace errors, four distinct profile IDs, unresolved-choice markers, and working relative links. This commit's design file SHA-256 remains `c795827333e5c5955cb93aad89e85191829dcfb4c0bf2f59eba3b5fc852791c8`. Local `ruff check .` and changed-file `ruff format --check` pass. Whole-repo `ruff format --check` has an unrelated baseline failure. Secret scan remains unrun/not passed (missing `detect_secrets`; no task QA venv; cannot use network under the no-egress scope). Push and CI status are pending; will record actual results next.
- 2026-11-09 — Step 5 (push and CI verification) complete for the design commit. Pushed `398fd16d7959488978ebed9cea4370f77225ab09` to `origin/loop/riso1-isolation-profiles`; `git ls-remote` confirmed the remote ref matches. GitHub Actions for this exact SHA completed successfully: Prototype quality run `42643065840`, Loop engine checks run `42643065843` (all four Windows/Linux × Python 3.11/3.13 matrix jobs passed), and pushed Conventional Commit check run `42643065836` succeeded. Prototype quality's `Verify application and dependencies` step passed, which includes the repository secret-scan invocation; thus CI secret scan passed even though local invocation was blocked by unavailable `detect_secrets`/QA venv. No platform-isolation verification was run; CI is code/repository QA, not profile proof. The task prohibits subagents, so no independent review was requested or claimed; independent security review remains mandatory before any profile activation. The standalone PR-title job marks PR-title validation skipped (this is a branch push, not a PR); pushed-commit convention validation passed.
- 2026-11-09 — Task-end status: authored and delivered `docs/plans/HYBRID_ISOLATION_PROFILES.md`, design SHA-256 `c795827333e5c5955cb93aad89e85191829dcfb4c0bf2f59eba3b5fc852791c8`; source commit `398fd16d7959488978ebed9cea4370f77225ab09` on the requested branch. Actions: [Prototype quality](https://github.com/kanalia7355/Locus/actions/runs/42643065840) PASS; [Loop engine checks](https://github.com/kanalia7355/Locus/actions/runs/42643065843) PASS on all four matrix jobs; [pushed Conventional Commit validation](https://github.com/kanalia7355/Locus/actions/runs/42643065836) PASS. CI verification includes the repository secret scan; local `scripts/secret_scan.py` was blocked by missing `detect_secrets` and absent `.loop/runtime/qa-venv`, and is recorded not passed locally. Local Ruff result: `ruff check .` PASS; changed-file `ruff format --check` PASS; whole-tree format check FAILS only on the pre-existing `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315` (baseline independently checked); `git diff --check` and design links PASS. No independent review or profile/platform test was performed; the task does not permit spawning subagents, and all profiles remain inactive pending independent review, exact-platform proof and separate authorization. No egress, credentials, dispatch, real data, host execution, or shared `.venv` access. Pushing this final task-log entry is still pending; no PR or activation was initiated.
