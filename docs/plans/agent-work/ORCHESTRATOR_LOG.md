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
| A | PH1-A2/PH1-E2 dual-plane ADR — review cycle complete; slot busy on PH1-G? no — slot A currently runs PH1-G; this row tracks ADR work | `loop/PH1-A2-dual-plane-adr` | deepai gpt-6-luna (thinking high) | ph1-e2-adr0012-fix-001 | DONE 2026-11-07 ~05:55Z: both MEDIUM review findings applied to ADR-0012 (approval before ANY step-2 implementation incl. slice 2a; cancellation safety semantics preserved vs owner-decided mechanisms/limits), DRAFT status kept, branch CI all green at 08b05d3, integrated into loop/local-development at 0da044e. ADR-0012 is review-cleared and awaits OWNER approval. Prior PH1-A recovery integrated at 1056021.
| B | PH1-B admin account enable/disable | `loop/PH1-account-toggle` | deepai gpt-6-luna (thinking high) | ph1-b-toggle-004-cont | DONE 2026-11-07 ~03:10Z: QA all green locally (pytest 1098 passed/18 skipped, account-toggle 8, frontend 49 + lint/typecheck/build, Playwright 10). Agent left work uncommitted per implementation-loop skill; orchestrator performed the authorized delivery commit a31d570, pushed the branch, and merged into loop/local-development at b7adb42 (docs conflict resolved keeping both sides). Slot B free.
| C | PH1-C hybrid threat model | loop/local-development (in-parent) | orchestrator glm-5.3-flash | ph1-c-threat-001 | DONE 2026-11-07: docs/security/HYBRID_AGENT_THREAT_MODEL.md committed at 0240f63 (matrix with cited evidence, STRIDE model, phase-mapped gaps with 要決定 markers, 5 consistency findings). The leftover worktree PH1-threat-model only holds the agent's progress notes; retire it at the next cleanup. |
| D | PH1-D admin web user provisioning — DONE, integrated; slot free | `loop/PH1-web-provisioning` | deepai gpt-6-luna (thinking high) | ph1-d-provision-004-cont | DONE 2026-11-07 ~05:00Z: 63ab511 + own CI repairs (cbe12e4 mypy guard, a355efb synthetic fixtures), branch CI all green at 76ba39a, local QA 1094 passed + Vitest 49 + Playwright 10, integrated at 2610b70 (main.py generate-guard conflict resolved to the integrated variant; App.tsx merged so AdminUsers wraps AdminList and keeps currentUserId for the toggle). Slot D free.
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

Cycle 2026-11-07 ~02:45Z: all four slots running, all appending progress (A: adversarial self-review complete, entering QA; B: session revalidation hardening done, backend 8 tests pass, npm offline deps installed; D: fixed a one-time-password hiding race found in self-review, starting full QA cycle 1; F: fix cycle 1 revision in progress after re-reading brief/review). No pushes yet; nothing to integrate; no free slot; CI remains billing-blocked.

Owner rule update (2026-11-07 ~03:15Z): PH1-* branches merge into their derivation source `loop/local-development`, never discussed as main-merges (branch sprawl inflates check load); each integration must wait for ALL CI checks to be green on the exact HEAD before merging, and implementation continues until CI is fully green. GitHub Actions works again (billing unblocked): the earlier failures are real and pre-existing on loop/local-development.

Integration log (out-of-cycle 2026-11-07 ~03:10Z): slot B terminal DONE (Luna). Evidence verified (recorded test counts match local spot-check: account-toggle suite 8 passed; ruff/mypy/secret-scan/pytest run by orchestrator). Delivered commit a31d570 (Conventional Commit) by the orchestrator under the owner's commit instruction, merged --no-ff into loop/local-development at b7adb42 with the task-file conflict resolved keeping both orchestrator notes and agent progress.

CI repair (out-of-cycle 2026-11-07 ~03:15Z, commit ed11f73 on loop/local-development): three pre-existing CI failures fixed without weakening anything — mypy str|None narrowing in the chat generate closure (fail-closed 422 guard, unreachable at runtime since the callback is only passed when a model is configured), and test literals replaced with the owner-approved SYNTHETIC allowlist values (test_chat_queue.py 'Rotated-password-long-01!' -> 'Changed-synthetic-password-01!', test_account_toggle.py 'Another-password-02!' -> 'Changed-synthetic-password-01!', 'Temporary-password-05!' -> 'Synthetic-test-password-01!'). Local evidence: mypy clean, secret scan 0 findings, ruff clean, 41 targeted tests passed. CI on ed11f73 pending at log time. Note: tests/integration/test_loop_c_min_native.py showed 4 failures in one full local run and 5 passed on immediate rerun (load flake) — watch CI windows-latest results.

Integration log (out-of-cycle 2026-11-07 ~03:40Z): slot F rework integrated at fbe7bf4 after its branch hit all-green CI on 890f235 (post-rebase). Slot A integrated at 1056021 after branch CI all green on 93d1633; local regression subset 52 passed (mypy/secret/ruff clean). loop/local-development push c28a280 was fully green (all three workflows incl. windows engine matrix), which also validated the PH1-B integration. Correction recorded: a rebase force-push on loop/PH1-F-hybrid-step2-design tripped check_commit_subjects.py (merge-base assumption) — resolved by a subsequent fast-forward push; force-pushes will not be used again.

Review log (out-of-cycle 2026-11-07 ~04:00Z): PH1-H round 2 verdict = accept after minor fixes — all 8 round-1 findings verified resolved in substance, no new weakening, 【要決定】 discipline intact. Remaining: 1 MEDIUM (runner-output artifact deletion propagation) + 1 LOW (review history update). Fix cycle 2 of 2 (final) assigned to slot F (ph1-f-step2-fix2-001, Luna). Per the reviewer's conditional verdict, the design is treated as accepted once these minor fixes are incorporated; ADR approval itself remains the owner's.

Assignment log (~04:05Z): slot A (freed by PH1-A integration) assigned PH1-A2 — drafting the dual-plane ADR (threat-model follow-up 2), the hard prerequisite before any step-2 implementation under the stricter sequencing. This advances the critical path while D finishes and F applies minor fixes. 3 slots running.

Integration log (cycle 2026-11-07 ~05:05Z): PH1-D integrated at 2610b70 (conflicts in main.py model-guard resolved to the integrated stricter variant; App.tsx users-page merged so ProvisionUser + AdminList coexist and the self-disable guard keeps currentUserId; local full regression 1122 passed/9 skipped + mypy/secret/ruff clean before push). PH1-A2 dual-plane ADR-0012 DRAFT integrated at d14b88d (branch CI all green). loop/local-development push 590f40a CI: all green (engine 4 matrix + quality + title). Remaining running: slot F fix cycle 2 (artifact deletion propagation). Next assignments when F lands: independent review of ADR-0012, then PH1-G consolidation of the three auth-slice jobs.

Review log (out-of-cycle 2026-11-07 ~05:35Z): PH1-E2 review of ADR-0012 DRAFT = accept after minor fixes (accurate C-min attribution, boundaries preserved, draft discipline intact). 2 MEDIUM findings: (1) explicit ADR-approval-before-ANY-step-2-implementation incl. slice 2a; (2) preserve mandatory cancellation safety semantics vs owner-decided mechanisms/limits. Fix cycle assigned to slot A (which authored the ADR): ph1-e2-adr0012-fix-001 on Luna; brief PH1-E2-adr0012-fix.md.

Integration log (~05:35Z): PH1-F fix cycle 2 integrated at 7bf3b11 (branch CI all green at e35e520; docs-only, clean merge). Hybrid step-2 design document is now fully review-cleared.

Integration log (cycle 2026-11-07 ~05:55Z): ADR-0012 fix cycle 1 integrated at 0da044e (branch CI all green at 08b05d3; docs-only, clean merge). ADR-0012 (dual-plane) is now review-cleared: r1 accept-after-minor-fixes → fixes applied → awaiting owner approval. PH1-G consolidation progressing in slot A (full QA green locally: 1113 passed/18 skipped, frontend 52 + Playwright 10, ruff/mypy/secret clean; docs updates being written). Slot D free; slot B free; slot E free.

Assignment log (cycle 2026-11-07 ~06:35Z, post owner status review): two new jobs launched. PH1-J (slot B, ph1-j-provision-race-001, Luna effort high): fix the medium-severity stale-Principal race in web provisioning (revalidate live session inside the creation transaction, mirroring the PH1-B pattern) + race regression + sweep of other newer admin endpoints for the same Principal-before-transaction pattern; brief PH1-J-provision-race.md. PH1-K (slot D, ph1-k-auth-aggregate-review-001, Luna effort high): independent read-only review of the Phase-1 auth-slice aggregate (recovery + toggle + provisioning + consolidation docs) including verification of the race finding and the aggregate's Phase-1 completion prerequisites; brief PH1-K-auth-aggregate-review.md. 2 slots running, 3 free. ADR-0012 still awaits owner approval before any step-2 implementation. loop/local-development push a55d856 CI: pending at log time (PR-triggered runs green so far).

Owner policy update (2026-11-07 ~07:00Z): per-job branches are considered repository pollution — after each job's branch is merged into the derivation source `loop/local-development`, the branch is deleted (local and remote) and its worktree removed. Phase-1 completion will be followed by merging `loop/local-development` into `main` (completion criteria still apply: independent review of the aggregate + all-CI-green at the exact HEAD). The repository is now public; GitHub Actions is usable and has been producing real results since ~02:00Z.

Branch cleanup (out-of-cycle 2026-11-07 ~07:00Z): verified every job branch was an ancestor of loop/local-development (git merge-base --is-ancestor), then deleted local and remote branches loop/PH1-recovery, loop/PH1-account-toggle, loop/PH1-web-provisioning, loop/PH1-F-hybrid-step2-design, loop/PH1-A2-dual-plane-adr, loop/PH1-G-consolidation, loop/PH1-threat-model, loop/TASK-001-fix-requestinit-headers-normalization, and removed their worktrees (PH1-G's final post-CI progress note was copied into the main checkout before removal). Remaining worktrees: main checkout + PH1-J (active, its branch will be deleted after integration). No history was rewritten; only fully merged refs were deleted.

Cycle 2026-11-07 ~07:20Z: slots B (PH1-J race fix: implementation done, targeted 19 passed, full QA in progress, not pushed yet) and D (PH1-K aggregate review, still reading) working. loop/local-development push c2ca69c CI: pending at log time; nothing to integrate; no new assignment (ADR-0012 owner approval still blocks step-2 implementation; Phase 4 remainder awaits owner prioritisation). Pending owner input recorded: whether prototype-scope completion is sufficient for the Phase-1 declaration while MFA and production TLS/session deployment remain unresolved, before the loop/local-development -> main merge.

Review log (out-of-cycle 2026-11-07 ~08:05Z): PH1-K independent aggregate review verdict = **accept after minor fixes**. Race confirmed (medium): stale Principal completes provisioning after disable/revocation; prescribed fix = revalidate live session + admin role inside the same creation/audit transaction + regression test — which is exactly what PH1-J (in progress) implements. Conditions recorded for the Phase-1 completion decision: (1) PH1-J integrated, (2) re-review of the integrated fix, (3) all-CI-green at the exact final HEAD. One LOW note: in-flight admin reads after revocation is a semantics clarification, not a blocker under request-start authorization; a stricter guarantee would need an explicit owner decision. Docs correctly keep MFA/production-TLS unresolved with no completion claim. Evidence spot-checks corroborated all recorded QA/CI references.
