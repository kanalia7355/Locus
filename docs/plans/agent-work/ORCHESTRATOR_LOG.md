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
| A | PH1-A authentication recovery | `loop/PH1-recovery` | deepai gpt-6-luna | ph1-a-recovery-003 | running (owner confirmed Luna is quota-free on DeepAI) |
| B | PH1-B admin account enable/disable | `loop/PH1-account-toggle` | deepai gpt-6-luna | ph1-b-toggle-003 | FAILED 2026-11-07: 426 lane_version_unsupported — "This version of DeepAI Code is no longer supported. Please update the app." PAUSED: no relaunch until the desktop app is updated (owner action). Uncommitted draft remains in worktree PH1-account-toggle. A/D still running at report time; if they die with 426 too, pause all slots. |
| C | PH1-C hybrid threat model | loop/local-development (in-parent) | orchestrator glm-5.3-flash | ph1-c-threat-001 | DONE 2026-11-07: docs/security/HYBRID_AGENT_THREAT_MODEL.md committed at 0240f63 (matrix with cited evidence, STRIDE model, phase-mapped gaps with 要決定 markers, 5 consistency findings). The leftover worktree PH1-threat-model only holds the agent's progress notes; retire it at the next cleanup. |
| D | PH1-D admin web user provisioning | `loop/PH1-web-provisioning` | deepai gpt-6-luna | ph1-d-provision-002 | running (worktree reset hard to loop/local-development before starting) |
| E | PH1-E independent review of the hybrid threat model | (read-only, no branch) | deepai gpt-6-luna | ph1-e-review-001 | DONE 2026-11-07: verdict "accept after minor fixes" (1 high + 4 medium); all fixes applied by the document owner in 307a5bb; review history recorded in the doc. Slot free. |
| F | (free) | | | | |

## Queued backlog

1. PH1-E: consolidation — reconciliation doc update from the four task files, cross-job regression run, independent review of the auth-slice aggregate.
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

(orchestrator appends: date, branch, commit, local verification, integration result)
