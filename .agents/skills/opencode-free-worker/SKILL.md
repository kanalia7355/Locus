---
name: opencode-free-worker
description: Execute a bounded Locus development task using verified eligible OpenCode free models with test-first evidence and safe fallback.
---

# OpenCode free worker for Locus

Use only inside the authorized development environment. This skill **does not grant** credentials, network egress, provider access, Runner activation, or workspace access. Read `AGENTS.md`, `docs/plans/FREE_FIRST_GOAL_LOOP_DIRECTIVE_2026-11-11.md`, the exact task, the applicable ADRs, acceptance and current Owner decisions first.

## Runbook

1. Identify current `opencode` executable/version, the installed documented CLI interface, and exact free model IDs. Never guess a model ID or pass undocumented flags. Confirm that the provider and workspace are permitted to receive the selected task material; use synthetic content while external routing is not approved.
2. Check installed Skills and Superpowers integration without clobbering existing `.agents/skills`. If Superpowers is not installed, follow its version-specific upstream instructions only after checking plugin permissions, license and supply-chain provenance. No speculative install or remote script execution.
3. Pick the highest-capability compatible free worker using bounded capability checks and previous QA, not the brand name. Persist model ID, provider, routing reason, catalog snapshot time, quota observations and decision.
4. Create or select one task-specific branch/worktree under established Controller policy. Record failing regression or concrete acceptance first. Give the worker the smallest allowed path scope and no secrets.
5. Have a **single** implementation worker modify code. Run deterministic static/functional/security checks. Review in an independent read-only context when required. Use at most three implementation/repair attempts and two review remediation cycles. Preserve all failures and evidence.
6. Distinguish an explicit provider quota exhaustion from auth errors, timeouts, 429 transient backoff, model/tool incompatibility, or skipped checks. Before GPT fallback verify every enabled eligible free worker is exhausted/unavailable under a bounded check and that an already-authorized no-extra-cost GPT route exists. Do not retry indefinitely or incur new paid charges.
7. Commit only verified code through approved local development delivery. Never direct-push main. Report exact SHA, CI, acceptance and remaining gaps to the durable Controller state, then select the next unblocked task. A single blocked task must not stop the final goal.

## Skill-level acceptance

- Model discovery/provenance and free eligibility independently verified.
- Skill actually discoverable and invoked in the configured CLI (not only present on disk).
- One non-sensitive bounded implementation task completes with test-first evidence, independent audit where applicable, exact-head checks and traceable commit.
- Quota-exhaustion, partial availability, transient failure, malformed output, cancellation and unauthorized egress each have explicit fail-closed tests.
- No parity claim with GPT-6.1 Sol without a measured benchmark on equivalent accepted tasks.

Reference: https://opencode.ai/docs/skills and https://github.com/obra/superpowers .
