# Orchestrator ledger — Phase 1 parallel jobs

Rules established by the owner (2026-11-06):
- Up to 5 concurrent subagents, one job each; implementation, self-review and QA in one flow.
- Coordination only through the markdown files in this directory; each agent appends progress to its own task file (in its worktree copy) whenever it finishes a step and at task end.
- Each agent commits and pushes its dedicated `loop/PH1-<slug>` branch. No pushes to `main` or `loop/local-development` by agents.
- Orchestrator checks every 10 minutes: read task files, verify finished work (local QA evidence + branch state), integrate approved branches into `loop/local-development`, and assign the next queued task.
- Merge to `main` still requires: phase completion criteria, independent review, and ALL required CI checks green at the exact HEAD. GitHub Actions is currently blocked by an account billing failure; while that persists, CI evidence is recorded as blocked, never passed.

## Active assignments

| Slot | Task | Branch | Model/provider | TaskId | Status |
|---|---|---|---|---|---|
| A | PH1-A authentication recovery | `loop/PH1-recovery` | deepai gpt-6-luna (thinking high) | ph1-a-recovery-004-cont | running 2026-11-07 ~01:45Z: relaunched from NEW orchestrator thread (previous thread's taskIds unreachable); continues the uncommitted worktree draft per its brief |
| B | PH1-B admin account enable/disable | `loop/PH1-account-toggle` | deepai gpt-6-luna (thinking high) | ph1-b-toggle-004-cont | running 2026-11-07 ~01:45Z: relaunch succeeded after the desktop app update (426 resolved); continues the untrusted draft with adversarial review |
| C | PH1-C hybrid threat model | loop/local-development (in-parent) | orchestrator glm-5.3-flash | ph1-c-threat-001 | DONE 2026-11-07: docs/security/HYBRID_AGENT_THREAT_MODEL.md committed at 0240f63 (matrix with cited evidence, STRIDE model, phase-mapped gaps with 要決定 markers, 5 consistency findings). The leftover worktree PH1-threat-model only holds the agent's progress notes; retire it at the next cleanup. |
| D | PH1-D admin web user provisioning | `loop/PH1-web-provisioning` | deepai gpt-6-luna (thinking high) | ph1-d-provision-004-cont | running 2026-11-07 ~01:45Z: relaunched on the new thread; continues the uncommitted worktree draft (backend done, frontend QA pending) |
| E | PH1-E independent review of the hybrid threat model | (read-only, no branch) | deepai gpt-6-luna | ph1-e-review-001 | DONE 2026-11-07: verdict "accept after minor fixes" (1 high + 4 medium); all fixes applied by the document owner in 307a5bb; review history recorded in the doc. Slot free. |
| F | PH1-F hybrid step-2 design proposal → now PH1-H review of it | `loop/PH1-F-hybrid-step2-design` (merged; slot F now review-only) | deepai glm-5.3-flash (thinking high) / next: Luna | ph1-f-step2-design-001 | DONE 2026-11-07: design proposal pushed at e99565c+57bf7f5, merged into loop/local-development at 77c054d (docs-only, clean merge). Slot F: PH1-H independent design review DONE 2026-11-07 ~02:30Z — verdict needs major rework (4 HIGH: permissive classification default, missing job-level approval contract, artifact ACL gap, runner identity/credential binding; 4 MEDIUM: ADR sequencing, allowlisted placeholder, toolless_boundary attribution, B1 import-graph coverage); full report in PH1-H-step2-design-review.md. Fix cycle 1 (max 2) assigned back to slot F: ph1-f-step2-fix-001 on Luna effort high, brief PH1-F-step2-design-fix.md; re-review round 2 follows on completion.

## Queued backlog

1. PH1-G: consolidation — reconciliation doc update from the four task files, cross-job regression run, independent review of the auth-slice aggregate. Blocked until slots A/B/D finish.
2. Phase 4 remainder (admin screens, comparison table, running-question cancellation) — pending owner prioritisation.
3. Hybrid-requirements step 2 (Agent Registry / common adapter / workspace policy) — only after the threat model (PH1-C) is reviewed.

## Outage log

- 2026-11-07: slot B relaunch died with 426 lane_version_unsupported — the
  DeepAI Code desktop app version is no longer supported by the provider lane.
  OWNER ACTION REQUIRED: update the DeepAI Code desktop app. Until then, do not
  relaunch any slot that fails with this error (relaunches fail identically).
  App update is an environment blocker for the whole subagent pipeline.
- 2026-11-07: non-Luna DeepAI subagent models died with `theos_exhausted`
  (account-wide daily quota). Owner confirmed deepai/gpt-6-luna is quota-free;
  all slots run on Luna now. If a Luna slot ever dies with quota errors, stop
  retrying and record it; otherwise relaunch freely on Luna.
- GitHub Actions remains separately blocked by account billing; CI evidence is
  recorded as blocked, never passed.

## Integration log

Out-of-cycle 2026-11-07: slot E review completed (accept after minor fixes);
fixes applied and pushed (307a5bb). Slot E freed.

Cycle 2026-11-07 ~01:04Z: A progressing (notes only, no code yet), B implementing
(uncommitted backend+frontend diff), D aligned worktree to 50319a0 and reading
specs. Nothing to integrate. Assigned PH1-E (independent threat-model review)
to slot E on Luna. Ledger updated.

Cycle 2026-11-07 ~01:45Z (NEW orchestrator thread): prior thread's delegated tasks became unreachable, so slots A, B, D were relaunched as continuations on their existing worktrees/branches (426 lane error resolved by the desktop app update; relaunches succeeded). Threat-model review (PH1-E) accepted, so hybrid-requirements step 2 was unlocked and assigned to slot F as a design-only proposal on glm-5.3-flash effort high. 4 slots running; 1 free. Committed the previously untracked `docs/planning/locus-hybrid-agent-requirements.md` (referenced by ROADMAP/PHASE_SPEC_RECONCILIATION since 2db93a0 but never committed) together with this ledger update.

(orchestrator appends: date, branch, commit, local verification, integration result)

Cycle 2026-11-07 ~01:55Z: all four slots (A/B/D/F) running on this thread; each appended relaunch-progress notes to its task file. No branch pushed to origin yet, nothing to integrate. No new assignment this cycle: backlog 1 (PH1-G consolidation) is blocked until A/B/D finish, backlog 2 awaits owner prioritisation; slot E stays free (5-slot cap observed with 4 running). CI remains billing-blocked.

Integration log (out-of-cycle 2026-11-07 ~02:05Z): slot F terminal DONE (glm-5.3-flash effort high). Verified deliverable docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md (463 lines: dual-plane boundary B1-B7 preserving ADR-0011, registry/adapter data model with pinned binary identity, fail-closed workspace policy E1-E8 mapped to threat model T-S1..T-E4, integration plan, slices 2a-2c, 10 【要決定】 owner items, empty boundary-change inventory). Merged origin/loop/PH1-F-hybrid-step2-design --no-ff into loop/local-development (clean, docs-only) at 77c054d and pushed. No code regression required (no code paths changed). Slot F freed and reassigned to PH1-H (read-only independent review of the step-2 design proposal) per the material-architecture-review rule; 10 【要決定】 items surfaced to the owner, NOT decided.

Review log (out-of-cycle 2026-11-07 ~02:35Z): PH1-H review of the hybrid step-2 design proposal returned needs major rework; evidence spot-check of 14 paths was otherwise supportive (C-min enforcement evidence confirmed in audit_transport.py/model_gate.py/c_min_runtime.py). Fix cycle 1 of 2 dispatched to slot F (Luna effort high). Design rework is docs-only; no integration until re-review passes.
