# C-min model boundary — independent design review record

Disposition: **PASS for owner consideration of design and offline implementation
scope only**. No unresolved blocking design findings. Not implementation evidence,
ADR adoption, authentication permission, deployment approval or Loop readiness.

## Scope and identity

- Reviewer: isolated read-only agent `/root/c_minimum_design_review`.
- Skill: `.agents/skills/architecture-review/SKILL.md`.
- Inputs: governance, ADR0006/0009/0010/0011, local delivery documentation,
  revised design/proposal, relevant existing runtime source and synthetic evidence.
- Local source/document reads only; no edits, delegation, tests, CLI/model runs,
  credential access, authentication, network calls or service actions.
- Root observation window: 2026-11-02 14:13:52–14:22:59 UTC (547 seconds).
  This includes preparation/waiting; it is not measured reviewer execution time.
  Reviewer token usage and reliable per-agent elapsed counters were unavailable.
- Completed initial review plus one fix/re-review in the current owner-requested
  completion. The earlier quota-interrupted review remains recorded in the design;
  it is not represented as a pass. No additional cycle is planned for these bytes.

## Exact reviewed files

| File | SHA-256 |
| --- | --- |
| docs/plans/MODEL_BOUNDARY_FINAL_DESIGN.md | ae610e2fd410bdca463cbe49687d015ae7f6e3bf3251405928c59fc383ccb001 |
| docs/plans/MODEL_BOUNDARY_APPROVAL_PROPOSAL.md | 5d6320cd86b3c8216db2317b06ae248f73087c6497014fb23d0ad35f9722e8b0 |
| docs/architecture/ADR-0011-model-facing-zero-tool-gate-proposal.md (unchanged PROPOSED) | fdb08eed20671b7a625d88f92d5d386e03bb2ea1808ca89d817304d70040c65b |

## Findings and resolution

1. **Medium / initially blocking — contradictory ADR scope.** Historical ADR0011
   lines56–64/99 called for stripping definitions and standard/Lite coverage;
   C-min requires zero incoming definitions and Lite-only. Approval proposal
   section2 now defines exact, post-owner-approval normative precedence for normal
   roles. Historical audit requirements remain held and unchanged. **Resolved.**
2. **Medium / initially blocking — incomplete durable reservation/recovery.**
   Existing `AuditRelay.used` is memory-only (`audit_transport.py:86,129–133`);
   the normal runner has no durable model-call reservation. Revised design
   lines276–328 specifies trusted stable owners, unique durable reservations,
   commit-before-resume/send, global unsettled hold, crash reconciliation and
   existing caller-result linkage. No task/delivery transition rewrite. **Resolved.**
3. **Medium / initially blocking — unconditional authentication preflight.**
   `codex_runner.py:103–109` runs login status; load can mutate auth storage.
   Revised design lines153–178 removes this preflight, defines nonsecret checks,
   excludes operator adoption of audit storage exceptions, and distinguishes
   ordinary CLI refresh traffic from the inference relay. **Resolved.**

No inherent Critical/High design flaw was identified. This is not a finding that
the implementation is safe: the proposed controls do not exist yet.

## Final independent disposition

The reviewer returned:

> Decision: pass for owner consideration of the design and offline implementation
> scope only. No unresolved blocking design findings. First fix/re-review cycle
> completed; no second cycle needed.

The review positively assessed explicitly consented same-backend credential
transit, zero incoming declarations, closed unknown-rejecting contracts,
response validation before dispatch, owned-child binding, fatal startup errors,
content-free diagnostics, role isolation and preservation of QA/local delivery.

Implementation/runtime readiness remains unestablished. Current source still
streams unvalidated SSE (`audit_transport.py:207–223`), lacks closed request
schemas and durable reservations, checks only peer SID and persists sanitized
transport content. Existing v2 receipts cannot prove C-min. Synthetic positive
evidence still contains CLI errors; ordinary ChatGPT authentication, entitlement,
Lite compatibility and live completion remain unverified.

The owner must approve the exact requested design/offline scope before any ADR
adoption or implementation. Independent security review of the implementation,
separate real-connection permission and separate 30-minute Loop permission remain
required later. Reviewed document changes invalidate this exact-file disposition.
