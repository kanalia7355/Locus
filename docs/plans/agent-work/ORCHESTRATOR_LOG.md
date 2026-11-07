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
| A | PH1-A authentication recovery | `loop/PH1-recovery` | (relaunch after quota refresh; owner prefers DeepAI, Luna) | ph1-a-recovery-002 | FAILED theos_exhausted (account-wide daily quota, refresh 2026-11-07T22:01Z). Worktree clean. Relaunch queued. |
| B | PH1-B admin account enable/disable | `loop/PH1-account-toggle` | deepai gpt-6-luna | ph1-b-toggle-003 | running — AT RISK: theos quota is account-wide; if it fails, relaunch after refresh with Luna. |
| C | PH1-C hybrid threat model | loop/local-development (in-parent) | orchestrator glm-5.3-flash | ph1-c-threat-001 | DONE 2026-11-07: docs/security/HYBRID_AGENT_THREAT_MODEL.md committed at 0240f63 (matrix with cited evidence, STRIDE model, phase-mapped gaps with 要決定 markers, 5 consistency findings). The leftover worktree PH1-threat-model only holds the agent's progress notes; retire it at the next cleanup. |
| D | PH1-D admin web user provisioning | `loop/PH1-web-provisioning` | (relaunch after quota refresh) | ph1-d-provision-001 | FAILED theos_exhausted. Worktree clean. Relaunch queued. |
| E | (free) | | | | |

## Queued backlog

1. PH1-E: consolidation — reconciliation doc update from the four task files, cross-job regression run, independent review of the auth-slice aggregate.
2. Phase 4 remainder (admin screens, comparison table, running-question cancellation) — pending owner prioritisation.
3. Hybrid-requirements step 2 (Agent Registry / common adapter / workspace policy) — only after the threat model (PH1-C) is reviewed.

## Outage log

- 2026-11-07: all DeepAI subagent runs die with `theos_exhausted` (account-wide
  daily quota). Refresh at 2026-11-07T22:01:03Z. Policy: no relaunch attempts
  before refresh; after refresh, relaunch failed slots (A, D, and B/C as needed)
  using DeepAI models (owner preference: Luna for relaunches). Orchestrator
  continues docs-only work in-parent meanwhile.
- GitHub Actions remains separately blocked by account billing; CI evidence is
  recorded as blocked, never passed.

## Integration log

(orchestrator appends: date, branch, commit, local verification, integration result)
