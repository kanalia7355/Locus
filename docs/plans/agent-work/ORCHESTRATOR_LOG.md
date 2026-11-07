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
| A | PH1-A authentication recovery | `loop/PH1-recovery` | deepai gpt-6.1-sol | ph1-a-recovery-002 | running (first codex run failed on a Codex CLI config error, not the task) |
| B | PH1-B admin account enable/disable | `loop/PH1-account-toggle` | deepai gpt-6-luna | ph1-b-toggle-003 | running (relaunch; first run died on provider daily quota `theos_exhausted`, gpt-6.1-sol; uncommitted draft preserved in worktree) |
| C | PH1-C hybrid threat model | `loop/PH1-threat-model` | deepai kimi-k3 | (assigned) | running |
| D | PH1-D admin web user provisioning | `loop/PH1-web-provisioning` | deepai glm-5.3 | (assigned) | running |
| E | (free) | | | | |

## Queued backlog

1. PH1-E: consolidation — reconciliation doc update from the four task files, cross-job regression run, independent review of the auth-slice aggregate.
2. Phase 4 remainder (admin screens, comparison table, running-question cancellation) — pending owner prioritisation.
3. Hybrid-requirements step 2 (Agent Registry / common adapter / workspace policy) — only after the threat model (PH1-C) is reviewed.

## Integration log

(orchestrator appends: date, branch, commit, local verification, integration result)
