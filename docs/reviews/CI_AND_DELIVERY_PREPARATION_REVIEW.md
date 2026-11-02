# CI repairs and delivery/trial preparation review — 2026-11-03

Independent reviewer: /root/ci_main_design_readonly_review, fresh read-only context.
Skills: architecture-review, quality-review. No writes, tests, credentials,
services, network, delegation or approvals. Elapsed/usage not instrumented.
One initial scoped CI/design review; no fix/re-review cycle used. The old C-min
core review remains closed and its reviewed implementation was not changed.

## CI repair

Disposition: PASS for the scoped code review, no findings. Actual final QA and
hosted Windows3.11 results remain the implementer's responsibility.

AuditCodexModel now subtracts elapsed time from the original finite <=300s budget
instead of adding/subtracting a fractional absolute origin. Preparation consumes
the same budget; cancellation/post-call expiry checks stay. Regression tests cover
fractional origins, consumed preparation, pre-launch expiry and invalid budgets.

The two generated-script tests still parse actual generated PowerShell, select
exactly one Add-Type AST node, compile that exact native helper and require success.
The unchanged30s deadline and process-tree containment remain. Explicit PSHOME
Utility import/qualified Add-Type remove ambient command autodiscovery; stage
markers distinguish host/module/compile entry/completion. ErrorAction Stop now
prevents a nonterminating compilation error from masquerading as a success marker.
Local success or this change alone does not prove the hosted timeout root cause.

## Main integration design

Disposition: needs_decision; suitable for explicit OFFLINE implementation approval,
not permission to update main. No blocking design findings. Informational points:

- updateRefs with paired beforeOid source/main guards is a conditional design.
  Bare transactions cannot prove hosted no-op support or protected-branch access.
  Unsupported operations/protection must HOLD, with no fallback or bypass.
- Current LocalDelivery completes immediately after development Push and existing
  StateStore connections do not verify FULL durability. The extension must add
  explicit receipt/durability gates. PolicyMigration._idle must also exclude an
  unsettled promotion; current executor/task checks alone are insufficient.
- Preserve whole-range independent review, trusted exact-SHA/latest-attempt CI,
  atomic guards, source identity, uncertain-send holds and unchanged normal mode.

Current protection demands a PR even for administrators. No protection change is
proposed for execution now. Main PR-free activation therefore remains blocked.
The frozen config also requires conventional-title, currently absent on push:
an additive commit validator is proposed, not removal of the required condition.

## C-min one-shot preparation

Disposition: needs_decision, no findings as an OFFLINE implementation proposal.
It is not a live-ready executable plan. Before live permission the reviewer
requires an implemented/reviewed purpose-specific adapter path and command,
complete semantic-input/hash binding, cumulative single-slot owner/ack, no-replay
recovery tests, expressly authorized nonsecret historical reconciliation, profile
evidence and explicit ordinary-refresh disposition. The trial-scoped proof must
remain unusable as normal-development readiness.

The current normal preflight circularity, per-workspace binding mismatch, expired
run/task3-of3 history, invalid v2 proof and inaccessible current audit-history
records are disclosed. Historical documents do not establish current protected
state or authorize an additional call. Root's read-only SQLite inspection is
reported separately; reviewer did not independently access protected/local state.

## Scope of authorization

Owner approval requests reference separate exact design hashes. Neither reviewer
resolves them. No main writes, protection edits, real auth/inference, service
operations or Loop launches occurred. Pending source specifications and config
are preserved. CI logs are untrusted evidence, never instructions.
