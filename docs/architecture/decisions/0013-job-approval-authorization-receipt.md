# ADR 0013 — Plane-R job approval and authorization receipt

Status: **DRAFT.** This record decides nothing and approves nothing. It structures
the owner decision required by [ADR-0012](0012-dual-plane-model-gate-agent-runtime.md)
open item (11) — "the separate job approval/authorization authority and receipt
contract" — and by [step-2 design §2.6](../../plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md).
Every mechanism marked 【要決定】 remains an open owner decision; approval of this
ADR in any form is the owner's alone. **Approving this ADR activates no runtime,
no dispatch path and no code.** Dispatch-capable Plane-R code (slice 2b) remains
forbidden until this ADR is approved per ADR-0012 §4.1 and step-2 design
§3.3/§6.11.

## Context

ADR-0012 (ACCEPTED, owner approval 2026-11-07) established the dual-plane
boundary: Plane M stays the model-facing zero-tool gate; Plane R is a separate
tool-executing Agent Runtime. Its Decision §4.1 makes a **job-level authoritative
approval receipt** a prerequisite for any dispatch: "Every job requires a current,
non-revoked authoritative receipt bound to the job ID, actor, workspace ID, exact
policy version, adapter, execution destination and operation. A role check alone,
UI flag, client/runner claim, adapter status or old boolean is not a receipt."
The Control Plane must recheck immediately before enqueue; the Runner must
independently recheck immediately before execution. Denial, expiry, revocation,
mismatch, policy change or unavailable authority must reject without enqueue or
execution. ADR-0012 explicitly leaves the issuer and trust, issuance, storage,
expiry and revocation contract to "the separate approval/authorization ADR" —
this document.

The step-2 design (`docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md`) pins the
same obligations at enforcement points E1 (Control Plane, before enqueue) and E2
(Runner, before execution), and its §2.6 defines the receipt as "authoritative,
unexpired, non-revoked … bound to **job ID, actor, workspace ID, exact policy
version, adapter, execution destination and operation**", with issuance/signature/
storage/revocation transport marked 【要決定】 for this ADR. Slice 2a acceptance
(step-2 design §6.11) states that even when dispatch-capable code is later
permitted, enqueue and runner execution must independently reject "denied,
revoked, expired, stale-policy or binding-mismatched receipts", with regression
tests covering approval denial, revocation between enqueue and execution, and
stale approval. Threat model
(`docs/security/HYBRID_AGENT_THREAT_MODEL.md`) threats T-T1 (job tampering,
replay, stale policy), T-S1 (runner impersonation), T-R1 (unattributable
invocation) and T-E1 (tool escape) all land on this receipt; the threat model's follow-up 3
names the job identity/freshness/binding/revocation contract as part of the
runner-enrollment ADR follow-up.

On 2026-11-09 the owner resolved the entire open decision register
(`docs/plans/OWNER_DECISION_REGISTER.md`, RESOLVED 2026-11-09), unblocking PH2-D
delegation implementation with concrete TTL and grantor-authority conditions, and
reaffirming the existing sequencing constraints: "never activate the runtime
before safety boundaries are proven". That resolution governs the *delegation*
path (`backend/app/service.py`, specification
`docs/plans/PHASE2_DELEGATION_SPEC.md`, whose §8 open items 1–12 the resolution
approved as recommended with the §A conditions); it does **not** select a
job-receipt authority. PH2-A-11 (grant/audit retention) is recorded in the same
register; its outcome bounds, but does not decide, receipt retention here.

### Current state of the code (verified)

> Source line numbers below are indicative snapshots from the drafting review, not stable anchors; symbols and cited files identify the code, and line positions may drift as the implementation changes. Verify against the current source before relying on a line reference.

- `backend/app/agents/registry.py` implements the metadata-only registry:
  `runner_instances`, `workspace_policies` (immutable, versioned,
  `classification_ceiling` default `none`, `egress_mode` CHECK limited to
  `'local_only'`, `destination_allowlist` CHECK `='[]'`), `workspace_adapter_bindings`,
  `adapter_health`, `adapter_credentials` (presence-only), and adapters
  (`AgentRegistry.__init__`, `_policy`, `_policy_values`). Its `dispatch_attempt`
  (line ~716) is the B6 Control-Plane rejection: it audits
  `agent.dispatch.reject` and returns 409 "Runner boundary is unproven; dispatch
  is disabled" regardless of Runner presence. There is **no receipt table, no
  receipt schema and no receipt-resolution code** anywhere in the package; the
  module docstring states it "never dispatches".
- `backend/app/service.py` implements the PH2-D delegation model
  (RESOLVED 2026-11-09 §A): `delegation_families`, `delegation_grants`,
  `delegation_events` with immutability/retention triggers; `_delegation_authority`
  gates grantor authority (project owner or `organization_admin` role on the
  target project, permissions `<= NON_ADMIN`, `<=` grantor ceiling and effective
  access, no `retrieve` without `read`); `create_delegation` enforces TTL bounds
  900–604800 seconds (15 min–7 days, default 86400 = 24 h) matching the owner
  resolution; `_delegated_permissions` revalidates live (recipient enabled,
  current family version, expiry, revocation events) at every authorization
  point; grantor-membership deletion or role change triggers
  `delegation.invalidate` events fail-closed.
- Role ceilings: `NON_ADMIN = frozenset({"read","retrieve","upload","publish"})`
  (`backend/app/service.py` line ~25); `create_role`/`update_role` reject
  permission sets not `<= NON_ADMIN` (lines ~2696/2738). Custom roles can never
  confer administrative permissions (owner resolution §A, item 9).
- Audit: `backend/app/service.py` `audit` table (line ~418) records actor,
  operation, target, result; the registry injects an audit port and writes
  `agent.*` operations (`backend/app/agents/registry.py` `_audited`/`audit`
  usage). ADR-0012 B7 requires Plane-R events attributed to actor, workspace,
  destination, model and authorization decision through a Control-Plane audit
  path; product audit-log protection (T-T4) remains an unresolved activation
  blocker.

Nothing in this state constitutes a receipt. This ADR designs the contract;
it implements nothing.

## Decision — proposed contract for owner decision; nothing is selected or activated

The following sections propose the receipt contract in the shape ADR-0012
requires, with every unowned choice marked 【要決定】. Sections marked
"mandatory" are fail-closed obligations ADR-0012 already binds — they are not
owner options and cannot be weakened by an owner decision on the marked items.

### 1. Receipt content (mandatory fields)

A receipt is authoritative only if it carries, at minimum, all of the following,
each bound exactly (per ADR-0012 §4.1 and step-2 design §2.6):

| Field | Meaning |
|---|---|
| `receipt_id` | Authoritative, issuer-unique receipt identifier |
| `job_id` | The exact job the receipt authorizes; a receipt authorizes one job |
| `actor` | The requesting user identity (Control-Plane principal, not a client claim) |
| `approver` | The identity that issued the approval decision (see §2) |
| `workspace_id` | Bound workspace |
| `policy_version` | The **exact** `workspace_policies(id, version)` pair current at issuance (T-T1: no stale-policy execution) |
| `adapter_id` | Bound registered adapter |
| `destination` | Exact execution destination (see §7) |
| `operation` | The specific operation authorized (e.g. `run_job`); never a blanket grant |
| `decision` | `approved` (a receipt that exists is an approval; denials are audit events, not receipts) |
| `issued_at`, `expires_at` | Issuance and expiry timestamps |
| `revocation` | Current revocation state as resolved at each check (see §3) |

The step-2 design §2.1 already reserves the logical `job_authorization_receipts`
contract with these fields ("concrete schema only after the approval ADR").
A receipt is additionally bound to the runner instance chosen for dispatch at
enqueue time, because a workspace binding in
`backend/app/agents/registry.py` binds one workspace to one
`(runner_instance_id, adapter_id)` pair; whether the receipt itself must carry
`runner_instance_id` or whether the envelope binding suffices is 【要決定】.

Anti-replay and integrity properties (signature scheme, canonical serialization,
nonce/job-envelope binding) are 【要決定】; whatever is chosen must let both E1
and E2 verify the *same* receipt and envelope.

### 2. Authoritative issuer (mandatory property, mechanism 【要決定】)

The receipt's source must be "the approved authorization authority defined by
the separate approval ADR" (step-2 design §2.6). No client, runner, adapter,
UI flag or role check can produce a receipt. Candidates for the authority:

- **(a) Control-Plane-internal authority module** — a dedicated issuer inside
  the Control Plane, separate from `backend/app/service.py` Plane-M code
  (per B1's import prohibition), signing receipts under a trust root it holds.
- **(b) Explicit human approver per job** — an approver principal (distinct
  from the actor) whose decision the issuer records; the approver may be the
  same class of principal as a delegation grantor under the 2026-11-09
  resolution (project owner or organization-admin role on the target project).
- **(c) Delegation-derived** — the existing PH2-D delegation grant
  (`backend/app/service.py`) feeds the issuer, but is not itself the receipt.

Whether receipts require a per-job human approver, an automated policy-driven
issuer, or approver approval only for a first-scope/exception class is
【要決定】. Whichever is chosen: the issuer is the only writer of receipts; the
approver is recorded on every receipt; and approver identity is never
self-asserted by the actor. Whether the approver must differ from the actor
(no self-approval) is 【要決定】; the fail-closed default proposed here is
approver ≠ actor.

### 3. Revocation (mandatory live-recheck property, mechanism 【要決定】)

Revocation must be resolvable at both enforcement points E1 and E2 at any
moment, fail-closed: an unavailable authority ⇒ reject (step-2 design §2.6,
E1/E2). Mechanism candidates:

- **(a) Online authority check** — both planes query the issuer (or a
  Control-Plane revocation endpoint over the versioned transport contract)
  immediately before enqueue and before execution. Strongest freshness;
  couples runner execution to Control-Plane reachability.
- **(b) Signed revocation lists / short-lived receipts** — receipts carry short
  expiries and revocation propagates via signed lists the runner caches.
  Weaker freshness; the step-2 design's "signature-verified or checked online"
  wording permits it only under an owner-approved trust contract.
- **(c) Hybrid** — online check with bounded negative-cache and an absolute
  receipt TTL that bounds staleness regardless of cache state.

Any mechanism must make revocation take effect before the *next* enforcement
point (a revocation between enqueue and execution must be visible to the
Runner's recheck), must survive runner offline periods fail-closed (an offline
runner cannot prove non-revocation ⇒ it must not execute), and must record
revocation as an immutable, auditable event. The maximum acceptable staleness
bound, and whether the negative-cache/hybrid pattern is permitted at all, are
【要決定】.

### 4. Recheck points (mandatory; not owner-selectable)

Two independent checks of the same authoritative receipt, per E1/E2:

1. **E1 — Control Plane, immediately before enqueue.** Verify receipt
   authenticity against the trust contract, reject replay/expiry, resolve
   revocation, and verify all bindings (job, actor, workspace, policy version,
   adapter, destination, operation — and runner instance, if §1 binds it).
   Denial, revocation, mismatch or unavailable authority ⇒ reject with no
   enqueue. This check runs **after** and in addition to the B6 rejection gate
   (`backend/app/agents/registry.py` `dispatch_attempt`); B6 remains an
   unconditional precondition while the boundary is unproven, and approving
   this ADR does not lift B6.
2. **E2 — Runner, immediately before execution.** Independently verify
   job-envelope authenticity/freshness and recheck the same receipt and
   revocation state, runner-instance identity, policy version and workspace
   binding. Stale/revoked/mismatched receipt ⇒ reject before any execution.

The two checks are independent: the Runner must not trust a Control-Plane
assertion that a receipt was valid at enqueue. The cross-plane transport used
for the E2 check must be the versioned `runner_contract/` transport (ADR-0012
B1/B4), not a new channel. Exact error taxonomy and status codes are 【要決定】,
but every rejection must be audited (see §8).

### 5. Denial / revocation / stale semantics (mandatory behaviors, test names mandatory)

Fail-closed semantics required at both points, with the regression tests
step-2 design §6.11 already specifies:

| Condition | Semantics |
|---|---|
| No receipt / denied approval | Reject before enqueue; audit denial. A denial is never persisted as a receipt |
| Revoked after enqueue | E1 may already have enqueued; E2 must reject before execution (revocation between enqueue and execution is the canonical test) |
| Expired | Reject at whichever check observes expiry; no grace period 【要決定】 (proposed default: none) |
| Stale policy | `workspace_policies` version changed since issuance ⇒ reject; the version is immutable in `backend/app/agents/registry.py`, so any change is a new version |
| Binding mismatch | Any of workspace/adapter/destination/operation/runner-instance differs ⇒ reject |
| Unavailable authority | Reject (never "assume valid") |
| Replay | Same receipt/envelope presented again ⇒ reject |

Required regression tests (future, when dispatch-capable code is permitted;
they exist nowhere today and this ADR creates none): approval denial, revocation
between enqueue and execution, stale approval, stale-policy, binding mismatch,
unavailable authority, and replay — each at E1 and at E2. These tests "cannot
make dispatch active before the ADR gate" (step-2 design §6.11). While B6 is
active the only testable behavior is the existing `dispatch_attempt` rejection;
no receipt test may be written in a way that requires or implies an enabled
dispatch path.

### 6. Actor and approver scopes

- **Actor scope.** The actor must hold, live at issuance and live at both
  recheck points, whatever workspace-level authorization applies
  (membership, role, and — if the owner links the two — a delegation grant
  under the 2026-11-09 conditions: TTL 15 min–7 days, live revalidation at
  every authorization point, no re-delegation, recipient cancellation allowed,
  fail-closed invalidation on grantor authority loss). Whether a delegation
  grant can ever be a *prerequisite* for job authorization, or only one
  additional input, is 【要決定】. The receipt binds the actor's *identity*,
  not a permission set: the actor's effective permissions are rechecked live
  at each point and are never inferred from the receipt.
- **Approver scope.** The approver must hold authority over the target
  workspace/project at issuance. The 2026-11-09 resolution's grantor rule
  (project owner or organization administrator with legitimate authority over
  the target project) is proposed as the approver-authority baseline;
  administrative permissions remain non-delegable (resolution item 9), and
  `NON_ADMIN` ceilings (`backend/app/service.py` lines ~25/2696/2738) bound
  what any custom role can carry. Whether approver authority is checked via
  the existing role model, a dedicated approver registry, or both is
  【要決定】. Approver authority loss between issuance and enqueue must
  invalidate the receipt (same fail-closed pattern as
  `delegation_grantor_membership_delete`/`delegation_grantor_role_update`
  triggers in `backend/app/service.py`); whether it also revokes already-enqueued
  jobs at E2, or only bars new issuance, is 【要決定】.

### 7. Approval-expiry policy

Expiry is a mandatory receipt field (§1). Bounds are owner decisions:

- Default TTL and maximum TTL for job receipts 【要決定】. For orientation
  only: the owner-resolved delegation TTL is 15 min minimum / 24 h default /
  7 days maximum (`create_delegation`, `backend/app/service.py`). A job receipt
  plausibly wants a shorter horizon because it authorizes one execution, but
  no value is proposed here.
- Whether expiry is absolute (wall-clock) or anchored to a job deadline
  (`deadline_seconds` is currently CHECK-constrained to NULL in
  `backend/app/agents/registry.py`), and the timestamp authority (the
  delegation path currently uses epoch seconds from
  `_delegation_now`, pending the production-DB/clock decision per the
  2026-11-09 resolution item 8) are 【要決定】.
- Clock skew tolerance between Control Plane and Runner 【要決定】; the
  fail-closed default is zero tolerance until the owner selects one.

### 8. Audit and role-ceiling integration (mandatory conventions)

- Every receipt lifecycle event — issuance, denial, recheck-pass (enqueue),
  recheck-pass (execution), revocation, expiry-observed rejection — is audited
  through the Control-Plane audit path with actor, approver, workspace,
  destination and the authorization decision (ADR-0012 B7; existing
  `agent.*` audit operations in `backend/app/agents/registry.py` and the
  `audit` table in `backend/app/service.py` are the convention). Audit
  operation naming for the new events is 【要決定】 (proposed shape:
  `agent.receipt.*`).
- Receipt issuance/administration endpoints, if any, use the existing
  role-ceiling rules (E7): writes reject permission sets outside `NON_ADMIN`
  and any delegated-admin attempt to widen ceilings (T-E2). No new permission
  is added to `NON_ADMIN` without owner approval; a new `approve_jobs`-style
  permission would be a boundary change requiring an owner decision 【要決定】.
- Receipt records retain the delegation model's immutability discipline:
  receipt rows are never updated or deleted; revocation and expiry are
  recorded as new immutable events (pattern:
  `delegation_*_no_update`/`_no_delete` triggers in
  `backend/app/service.py`). Retention period and any redaction requirements
  follow the outcome of PH2-A-11 and remain 【要決定】.
- Receipt material must never contain credential bytes (ADR-0012 B2;
  `credential_schema_is_presence_only` in `backend/app/agents/registry.py` is
  the presence-only precedent). T-T4 audit-log protection remains an
  activation blocker independent of this ADR.

### 9. Relationship to Loop authorization and other approvals

Loop Controller authorization code (`loop_engine/run_authorization.py`,
`loop_engine/approval.py`) is a design precedent only; per step-2 design §4 it
"is not assumed to authorize product jobs". This ADR does not reuse,
import or extend Loop approval state. Approval of a dispatch-capable slice
under a future owner decision also does not weaken: the B6 gate, classification
fail-closed defaults (E6), the egress `local_only` CHECK constraint
(`backend/app/agents/registry.py` `_policy`), artifact gates (E9), or any
existing zero-tool regression test (ADR-0012 Verification requirements).

## Consequences

### What this draft would make decidable

If approved with the 【要決定】 items resolved, this ADR supplies the exact
authority, trust, issuance, storage, expiry and revocation contract ADR-0012
§4.1 and step-2 design §2.6 demand, unblocking slice-2b dispatch-capable code
design — but not its implementation, which still requires the owner's
separate slice approval and all activation gates.

### What this draft does not do

It approves no ADR content as final (status DRAFT), selects no issuer, trust
root, signature scheme, TTL, revocation transport or retention period, adds no
permission, schema, table, code or test, lifts no B6 gate, activates no runner,
and touches no Plane-M behavior. Dispatch-capable code remains forbidden. The
only operative code behavior cited is the existing `dispatch_attempt` rejection
and the existing registry/delegation/audit implementations, all unchanged.

### Owner decisions this ADR requests (inventory)

1. Issuer architecture (§2): Control-Plane-internal authority vs. external
   authority; per-job human approver vs. policy-driven issuance; approver ≠
   actor default.
2. Trust contract (§1/§3): signature/verification scheme, canonical
   serialization, replay binding, runner-instance binding on the receipt.
3. Revocation mechanism and staleness bound (§3).
4. Expiry policy (§7): default/max TTL, absolute vs. deadline-anchored,
   timestamp authority, clock-skew tolerance.
5. Actor/delegation linkage and approver-authority mechanics (§6), including
   whether grantor-authority loss revokes enqueued jobs at E2.
6. Error taxonomy/status codes and audit operation names (§4/§8).
7. Any new approver permission and its ceiling treatment (§8).
8. Retention/redaction alignment with PH2-A-11 (§8).

None of these may be resolved by an implementation agent; they belong to the
owner (ADR-0012 pattern; 2026-11-09 register discipline).

## Verification requirements (for the future implementation, not performed here)

When and only when the owner approves this ADR and dispatch-capable code, the
implementation must add, at minimum:

- The regression matrix of §5 (denial, revocation-between-enqueue-and-execution,
  stale approval, stale policy, binding mismatch, unavailable authority, replay)
  at E1 and E2 independently, under `tests/unit/` and, where cross-plane,
  `tests/integration/`, in the naming style of the step-2 design §4 QA plan.
- Static import-graph tests proving the issuer and receipt code respect B1
  (no `backend/app/` ↔ `runner/` imports; no `backend/app/agents/` → Plane-M
  imports; `runner_contract/` neutral).
- A regression that the B6 `dispatch_attempt` rejection still fires with a
  valid-looking receipt present (approving the receipt path must not weaken
  the unproven-boundary gate).
- Audit assertions that every lifecycle event of §8 is recorded with full
  attribution, and that receipt tables are immutable (trigger-style checks
  analogous to the delegation triggers).
- Confirmation that `adapter_credentials` remains presence-only and that no
  receipt content contains credential material.

Until owner approval, the only valid verification is that **no receipt code
exists** and that the existing suites — including the zero-tool regressions
listed in ADR-0012 (`tests/unit/test_loop_tool_surface.py`,
`tests/unit/test_loop_c_min.py`,
`tests/integration/test_loop_c_min_launch.py`,
`tests/integration/test_c_min_public_reference_scan.py`) — pass unchanged.

## Review history

- Drafted 2026-11-09 (slot HYB-A1) from ADR-0012 (ACCEPTED) §4.1 and open item
  (11), step-2 design §2.1/§2.6/§3.2 E1–E2/§6.11/§8, the owner decision
  register RESOLVED 2026-11-09, the hybrid threat model (T-T1/T-S1/T-R1/
  T-E1/T-E2, follow-up 3), and verified source state in
  `backend/app/agents/registry.py` and `backend/app/service.py` (PH2-D
  delegation model, `NON_ADMIN` ceilings, audit conventions). Documentation
  only; no code changed. Self-review against the cited sources found the
  receipt contract fully consistent with ADR-0012 §4.1 and E1/E2; the known
  documentation/code tension noted for the record: the step-2 design's §6.11
  test names are proposals, while actual tests live under `tests/` in layouts
  that differ (`tests/test_*.py` vs the design's `tests/unit/` proposal) —
  this ADR cites both without declaring either authoritative.
- Status remains DRAFT. Next step: independent read-only review, then owner
  decision on the 【要決定】 inventory. This record activates nothing.
