# Hybrid step 2 (2b) — job authorization receipt and job-envelope contract — DESIGN PACKAGE

Status: **DESIGN DOCUMENTATION ONLY.** This package drafts and reconciles the logical
job authorization receipt and job-envelope contract required before any 2b
dispatch-capable work. It decides nothing, approves nothing, activates nothing, and
contains no code, no executable schema, no dispatch path, no key provisioning and no
Runner activation. Dispatch remains disabled; the B6 gate
(`backend/app/agents/registry.py` `dispatch_attempt`, line ~716) continues to reject
every dispatch/enqueue attempt regardless of Runner presence.

**Authority chain (in descending order):**

1. [ADR-0012](../architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md)
   (ACCEPTED, owner approval 2026-11-07) — §4.1 mandatory authoritative receipt;
   B1–B7; approval ≠ activation.
2. [Owner formal decisions Q1–Q7](OWNER_DECISIONS_2026-11-09-EVENING.md)
   (2026-11-09 evening) — policy-level resolutions; owner §4 lists the items that
   remain 【要決定】.
3. [Step-2 design](HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md)
   §2.1/§2.2/§2.6/§3.1/§3.2/§3.3/§6/§6.11 — the enforcement-point and slice
   acceptance structure this package reconciles against.
4. [ADR-0013](../architecture/decisions/0013-job-approval-authorization-receipt.md)
   (**DRAFT** — structures the owner decision required by ADR-0012 §4.1 open item
   (11); it decides nothing by itself). Where ADR-0013's open-item framing has been
   superseded by the later owner decisions and the classification record, the later
   record governs and this package says so explicitly (§1.3, §9).
   Citation convention note: "step-2 §6.11" in ADR-0013 and in this package denotes
   the slice-2a receipt-rejection acceptance block and step-2 §6 item 11 (the
   approval-ADR prerequisite); the step-2 document itself has no numbered §6.11
   subsection.
5. [OWNER_QUEUE_CLASSIFICATION_2026-11-09.md](OWNER_QUEUE_CLASSIFICATION_2026-11-09.md)
   — authoritative DP-row classification (ENGINEERING_DETAIL /
   OWNER_DECISION_REQUIRED / OWNER_POLICY_RESOLVED / EXISTING_DECISION /
   DEFERRED_WITH_GATE) used throughout to label every contract choice.
6. [Hybrid threat model](../security/HYBRID_AGENT_THREAT_MODEL.md) — threats
   T-T1, T-S1, T-R1, T-E1, T-E2 land on this contract.

**Completion gate (from [R-2B-1](agent-work/R-2B-1-receipt-design.md)):**
source-linked, internally consistent design reviewed against ADR-0012/0013 and the
step-2 design, with every owner-controlled open point visibly marked 【要決定】 and
no activation claim. Any 2b dispatch-capable implementation remains blocked until
the owner-approved receipt contract and separate slice authorization exist; dispatch
stays disabled until the ADR-0012 activation gate and all its
verification/authorization gates pass.

---

## 0. Scope and non-goals

**In scope:** the logical contract only — receipt fields and bindings, job-envelope
fields and bindings, issuance inside current policy/authority (owner Q1), the two
enforcement points E1/E2, online/current authorization and revocation visibility,
audit requirements, and the explicit separation of mandatory ADR-0012 semantics from
contract details.

**Out of scope (each is separately gated work, none started here):**

- Receipt/envelope implementation, issuance code, verification code, or any schema
  change enabling execution. Slice 2a's metadata-only tables exist already; this
  package adds none and modifies none (§8.1).
- Dispatch-capable tests of any kind, including tests that would require an enabled
  dispatch path (step-2 design §6.11; ADR-0013 §5).
- Runner trust root, enrollment ceremony, key custody, per-platform credential
  mechanisms (step-2 design §6 items 4/5; owner §4) — design policy decided by
  Entry 5 / Entry 4 (2026-11-10); implementation/verification and activation remain gated.
- Isolation profiles and their verification (separate packages
  [R-ISO-1/2](RESUMABLE_JOBS_2026-11-09.md)); profiles are inputs to E2
  preconditions only.
- Provider authentication/credential supply and any external communication
  activation (owner Q4 constraint only; owner §4).
- Egress: `allowlisted` remains a non-operative placeholder; no enabling schema,
  policy value or code may exist before the owner decision (step-2 design §3.1/§6.7;
  ADR-0012 §4.3). This contract assumes and requires `local_only`.

## 1. Decision-tier taxonomy — how to read every statement below

Every normative statement in this package belongs to exactly one tier. Weakening a
Tier-0 statement is a safety-boundary change and is out of scope for any later
decision, engineering detail, or implementation slice.

### 1.1 Tier 0 — mandatory ADR-0012 semantics (invariant; not owner-selectable)

From ADR-0012 §4.1 and the step-2 design §2.6/§3.2 (E1/E2)/§3.3/§6.11:

| # | Invariant |
|---|---|
| I-1 | Every job requires a **current, non-revoked, authoritative** approval receipt bound to job ID, actor, workspace ID, exact policy version, adapter, execution destination and operation. A role check alone, UI flag, client/runner claim, adapter status or old boolean is never a receipt. |
| I-2 | The Control Plane verifies the receipt and all bindings **immediately before enqueue** (E1); the Runner **independently** rechecks the same authority, receipt/revocation state and bindings **immediately before execution** (E2). The Runner never trusts a Control-Plane assertion that the receipt was valid at enqueue. |
| I-3 | Denial, expiry, revocation, binding mismatch, policy change, or **unavailable authority** ⇒ reject without enqueue (E1) or without execution (E2). Fail-closed in every case; "assume valid" is never permitted. |
| I-4 | While B6 is active the Control Plane explicitly rejects every dispatch/enqueue attempt, with a Runner present or not; "no Runner exists" is not an acceptable rejection test. B6 precedes and outlives any receipt logic; approving a receipt contract never lifts B6. |
| I-5 | Classification defaults to deny-all (`classification_ceiling` default `none`, `backend/app/agents/registry.py` line ~85) and is independent of destination/egress authorization; `egress_mode` is CHECK-constrained to `local_only` (line ~90); `destination_allowlist` is CHECK-constrained to `'[]'` (line ~92). |
| I-6 | No credential bytes or credential content in receipts, envelopes, audit records or registry metadata (B2; `adapter_credentials` is presence-only, enforced by `credential_schema_is_presence_only`, line ~53/186). |
| I-7 | Plane-M zero-tool behavior (ADR-0011) is untouched; receipt/envelope work never adds tools to the model-facing path and never imports Plane-M code from `backend/app/agents/` (B1). |
| I-8 | Runner-output artifacts remain policy-checked (ADR-0012 §4.4; E9) — the receipt authorizes execution only; it never substitutes for artifact, classification or egress gates. |
| I-9 | Plane-R events are attributed to actor, workspace, destination, model and authorization decision through the Control-Plane audit path (B7). Product audit-log protection (T-T4) remains an unresolved activation blocker. |
| I-10 | Approval of any receipt contract is not activation: every activation step needs its own audited package, verification gates and separately recorded evidence (ADR-0012 status; step-2 design §3.3). |

### 1.2 Tier 1 — owner-resolved policy (Q1/Q2/Q4 and step-2 §6; fixed inputs here)

- **Q1 — automatic issuance inside current policy and authority.** Job approvals are
  issued automatically per the administrator-approved Workspace Policy, operation
  range, data classification and execution environment; no per-job human approval
  for in-scope jobs. Out-of-scope operations, unapproved external communication,
  privilege escalation and safety-boundary changes are **never** auto-approved.
  Approval history, executing actor, target workspace, adapter and operation must be
  auditable; receipts are issued strictly on current permission and policy.
  (Classification rows DP-004/DP-005: OWNER_POLICY_RESOLVED.)
- **Q2 — personal Workspace owner authority.** The legitimate owner of a personal
  workspace approves own executions within the permitted range; upper
  organizational policy and prohibitions cannot be overridden; no automatic
  acquisition of shared or third-party data access; no unjustified foreign-admin
  per-job approval for the personal scope. Self-approval scope and ceilings must be
  explicit. (DP-015b: OWNER_POLICY_RESOLVED; combined form DP-006.)
- **Q4 — official-CLI / no-credential-mixing constraint.** Official CLI login
  methods are preferred; subscription use only as officially permitted; API-key is
  not the only allowed mechanism; per-adapter verification of terms, authentication
  and isolated operation; credentials never enter job inputs or audit logs. The
  actual provider credential supply is decided by **Entry 4 (2026-11-10): design
  and verification approved, real supply not permitted at this stage** (DP-034b).
- **Step-2 design §6 resolutions (2026-11-07)** that bound this contract: dual-plane
  ADR approved (item 1); registry stores credential presence only (item 2); provider
  contract verification recording schema approved, per-provider activation gate
  remains (item 3); `allowlisted` egress placeholder approved as non-operative,
  default stays deny (item 7); real data not approved (item 9); LAN-external runner
  reachability not approved (item 10).

### 1.3 Tier 2 — ENGINEERING_DETAIL contract design (classification-authoritative)

The classification record is authoritative for which receipt items are engineering
detail. The following rows are designed in this package as engineering detail and
**do not require a separate owner decision**, provided no boundary is affected; any
change that would affect a Tier-0 or Tier-1 statement returns to the owner:

| Row | Design position adopted here |
|---|---|
| DP-001 | Receipt schema detail sits under the Q1 automatic-issuance contract. ADR-0012's **exact-instance E2 check stays mandatory**; whether `runner_instance_id` rides on the receipt or on the envelope, the E2 recheck must bind receipt + envelope + the exact runner instance, and a mismatch rejects. |
| DP-002 | Signature/serialization/replay mechanics live inside the ADR-0013-mandated contract with **online authoritative verification**; no bespoke Runner signature protocol is introduced. |
| DP-003 | Receipt state reuses the existing Control-Plane control store and the immutable-event convention (the `workspace_policies_no_update/no_delete` trigger pattern and the `delegation_*_no_update/_no_delete` pattern in `backend/app/service.py` lines ~169–261); production DB migration stays in the Q7 track (DP-066). |
| DP-007 | A Control-Plane-internal **protected issuer key**; no receipt-only PKI; Runner verification stays online/authenticated. |
| DP-008 | **Online live revocation check at E1 and E2**, fail-closed on unavailability — within ADR-0013 §3's mandatory live-recheck property. |
| DP-009 | **Zero staleness at enforcement**: no negative cache in the default design; any later measured cache is a separate reviewed decision. |
| DP-012 | **Absolute expiry, no grace period**, as the fail-closed default within ADR-0013 §7. |
| DP-013 | Reuse the delegation Control-Plane clock (`_delegation_now`, `backend/app/service.py` line ~1073) for the prototype; the production time source follows Q7 (DP-066). |
| DP-014 | **CP-authoritative online expiry**; no invented clock-skew tolerance; any tolerance is measured first and reviewed before adoption. |
| DP-016 | Approver authority is verified through the **existing grantor/role model** (project owner or `organization_admin` on the target project, `_delegation_authority`, `backend/app/service.py` line ~1042/1058–1063); no dedicated approver registry. |
| DP-017 | Fail-closed invalidation on approver-authority loss, mirroring the existing `delegation_grantor_membership_delete` / `delegation_grantor_role_update` trigger pattern. |
| DP-019 | A small, **closed, versioned reason enum** for rejections, mapped to the existing 409 dispatch-rejection pattern (`dispatch_attempt` → `_deny(409, …)`). |
| DP-020 | Audit event naming `agent.receipt.*` under the existing `agent.*` convention (`audit` port in `backend/app/agents/registry.py`). |
| DP-023 | Receipts/audit carry **metadata only — no credential bytes or content** (existing mandatory rule; schema is design detail). |

`EXISTING_DECISION` rows adopted as-is: DP-015a (live membership/role authorization
first; a delegation grant is an additional live-checked input, never a prerequisite);
DP-018 (authority loss after enqueue is visible at the E2 recheck — ADR-0012 §4.1
already mandates this; enqueued jobs fail closed at E2).

`DEFERRED_WITH_GATE`: DP-022 (receipt retention/redaction follows the production
retention/audit decisions DP-068/069, Q7 track; gate D-1 in the classification
record). No receipt-specific retention period is invented here.

### 1.4 Tier 3 — 【要決定】: owner choices this package must not fill in

See §9 for the full inventory and its 2026-11-11 resolution update: items decided
by owner Entries 1–6 (TTL values, approval permissions, trust design policy,
credential-supply design scope, LAN-channel design) carry their decided values at
each point of use below; items 6–9 remain 【要決定】: unverified isolation profiles;
receipt retention (DP-022,
gated); real-data use and production exposure (Q7); any other safety-boundary
change.

## 2. Contract object model — logical only

This section defines the two logical objects and their bindings. It defines no
DDL and changes no table; §8.1 records honestly how the existing slice-2a
placeholder schema relates to this contract.

### 2.1 The authorization receipt (logical fields)

The receipt is the authoritative approval artifact of ADR-0012 §4.1. A receipt
exists only as an **approval of one job**; denials are audit events, never receipts
(ADR-0013 §1). Logical fields, each source-bound:

| Field | Binding semantics | Verified at | Sources |
|---|---|---|---|
| `receipt_id` | Issuer-unique identifier; the handle both E1 and E2 resolve | E1, E2 | ADR-0013 §1 |
| `job_id` | The exact single job authorized; one receipt authorizes exactly one job; never a blanket grant | E1, E2 | ADR-0012 §4.1 |
| `actor` | The requesting **Control-Plane principal** at issuance; never a client-asserted claim; permissions are always rechecked live and never inferred from the receipt | E1, E2 | step-2 §2.6; ADR-0013 §6 |
| `approver` | The authority that justifies issuance under Q1/Q2: for automated in-scope issuance, the issuer records the policy authority (administrator-approved Workspace Policy) as the approval basis; for administered/exception approvals, the human approver principal; approver ≠ actor for that class | E1 | DP-006/DP-016; Q1/Q2 |
| `workspace_id` | Bound workspace; must be `active` and bound to the adapter/runner pair at every check | E1, E2 | step-2 §2.1 `workspaces` |
| `policy_id` + `policy_version` | The **exact** `workspace_policies(id, version)` pair current at issuance; rows are immutable (trigger-enforced, `backend/app/agents/registry.py` lines ~99–117), so any policy change is a new version ⇒ stale receipt ⇒ reject | E1, E2 | ADR-0012 §4.1; T-T1 |
| `adapter_id` | Bound registered adapter; must be `registered` (not `disabled`/`deprecated`) and inside the policy `adapter_allowlist` at every check | E1, E2 | step-2 §2.1 |
| `destination` | The exact execution destination; under the current policy universe this is the local workspace destination only — `local_only` is the only operative egress value, so no external destination can ever appear in a valid receipt today | E1, E2 | step-2 §3.1; ADR-0012 §4.3 |
| `operation` | The specific operation authorized (the B3 adapter surface `run_job(job, workspace_policy)`); a receipt for one operation never authorizes another | E1, E2 | ADR-0012 B3 |
| `runner instance binding` | ADR-0012's exact-instance E2 check is mandatory: the checked pair (receipt, envelope) must be bound to the exact enrolled `runner_instance_id` the workspace is bound to (`workspace_adapter_bindings`, `workspaces.runner_instance_id`); carrier placement (receipt field vs envelope field) is engineering detail (DP-001) | E2 (and consistency at E1) | DP-001; B5 |
| `decision` | `approved` (a persisted receipt is an approval; `pending`/`denied` states are not receipts) | — | ADR-0013 §1 |
| `issued_at`, `expires_at` | Issuance/expiry instants under the CP-authoritative clock (DP-013/014); absolute expiry, no grace (DP-012); numeric values decided by **Entry 1 (2026-11-10): default 24 h / maximum 7 days** (DP-010/011) | E1, E2 | ADR-0013 §7; [OWNER_DECISIONS_2026-11-10-ENTRIES.md](OWNER_DECISIONS_2026-11-10-ENTRIES.md) |
| `revocation state` | Resolved **live at each check** via online authority check (DP-008); revocation recorded as an immutable event, never an in-place mutation (DP-003) | E1, E2 | ADR-0013 §3 |
| `schema_version` | Explicit version field from day one, exchanged only via the versioned `runner_contract/` transport; unknown fields/unsupported versions fail closed (B4) | E1, E2 | threat-model cross-cutting verdict 3; B4 |

Integrity/anti-replay properties (canonical serialization, nonce/envelope binding,
verification scheme) are engineering detail inside DP-002/DP-007's mandate: online
authoritative verification against the Control-Plane-internal protected issuer key;
no custom Runner signature protocol. Any trust-root-dependent mechanism beyond this
(e.g. asymmetric keys provisioned to runners) would import the Runner
trust/enrollment/key-custody decision — **the design policy is now decided by
Entry 5 (2026-11-10): OS-keystore per-instance identity, vetted TLS, admin
one-time-challenge enrollment** ([HYBRID_RUNNER_TRUST_DESIGN.md](HYBRID_RUNNER_TRUST_DESIGN.md));
its verification conditions and activation gates still apply, and the online-verification
mandate above stays the operative default until that verification passes.

### 2.2 The job envelope (logical fields)

The envelope is the transport object that carries the job to the Runner across the
versioned `runner_contract/` transport (B1/B4: the only cross-plane channel — no
in-process calls, no shared objects, no alternate channels).

| Property | Requirement | Sources |
|---|---|---|
| Closed, versioned schema | Unknown fields, unsupported versions, unreviewed upgrades fail closed at both planes | B4; step-2 §1.2 |
| Receipt reference | Carries the `receipt_id` (and the exact binding set of §2.1) it was enqueued under; E2 rechecks the same receipt, not a Control-Plane assertion | ADR-0013 §4; I-2 |
| Job identity + freshness | `job_id` binding, freshness/expiry checks at both E1 and E2; replay of the same envelope rejects | step-2 §2.2; §3.2 E1 |
| Integrity | The envelope must be verifiable by the Runner as authentic and unmodified under the trust contract selected for the issuer (DP-002/DP-007); the specific mechanism is contract detail, and any runner-side key material raises the Runner key-custody gate — design policy decided by Entry 5 (2026-11-10; [HYBRID_RUNNER_TRUST_DESIGN.md](HYBRID_RUNNER_TRUST_DESIGN.md)), verification/activation still gated | DP-002/007; §9 |
| No credential/content leakage | Envelope contains job/policy metadata only — never credential bytes, never provider-credential content, never model-facing request content (I-6; Q4; B2) | I-6 |
| No tool declarations | The envelope never carries tool declarations toward any model-facing path; native CLI tools remain inside Plane R (ADR-0011 preserved; B3) | I-7 |
| Policy echo | Carries the `policy_id`/`policy_version` the job was admitted under, matching the workspace binding and the runner's health `policy_version_echo` (T-T1 stale-policy defense) | step-2 §2.5 |

Envelope fields that depend on the owner-decided trust contract (nonce carrier,
signature blocks, key references) are contract detail inside DP-002 **only under the
CP-internal-key / online-verification mandate**; they are not license to build a
runner-held-key protocol, which stays 【要決定】 (§9, item 3) — with the Entry 5
design-policy approval noted there (verification conditions and activation gates
still apply; no runner-held-key protocol is enabled by this package).

### 2.3 Binding trace — where each binding is established and rechecked

| Binding | Established at | E1 recheck (before enqueue) | E2 recheck (before execution) | Threat |
|---|---|---|---|---|
| job | job creation; receipt issued for exactly this `job_id` | receipt↔envelope↔admission record identity; replay rejected | same receipt/envelope re-verified; replay rejected | T-T1, T-R1 |
| actor | issuance: authenticated Control-Plane principal | live: identity valid, membership/role authorization current (DP-015a); delegation grant, if any, live-revalidated as an additional input only | live re-verification of the same actor authorization (exact-instance + identity binding) | T-R1 |
| approver / authority | issuance: policy authority (Q1) or human approver (Q2/administered) recorded by the issuer; approver authority checked via the existing grantor/role model (DP-016) | approver-authority loss since issuance ⇒ fail-closed invalidation (DP-017); whether already-enqueued jobs are revoked at E2 on later authority loss is answered by DP-018/DP-008: the E2 live recheck sees current state ⇒ reject | DP-018: authority loss after enqueue is visible at E2; enqueued jobs fail closed | T-T1 |
| workspace | receipt issued against the bound, `active` workspace | workspace active; binding enabled | workspace active; binding unchanged; cross-workspace substitution impossible | T-T1 |
| policy version | exact `(policy_id, version)` pair at issuance | version unchanged (immutable rows ⇒ any change = new version ⇒ stale ⇒ reject) | same version re-checked; also matched against runner health `policy_version_echo` | T-T1 |
| adapter | registered adapter inside the policy allowlist | adapter `registered`, allowlist match, capabilities ≤ policy (E3) | adapter state unchanged; instance-scoped health fresh | T-S3 |
| destination | exact destination at issuance | `local_only` ⇒ only local workspace destination representable; no external destination can pass | same destination re-checked; E5 independent egress gate still applies | T-I1, T-R2 |
| operation | exact operation (B3 `run_job` surface) | operation matches receipt and policy scope | same operation re-checked | T-E1 |
| runner instance | workspace bound to one `(runner_instance_id, adapter_id)` pair | binding consistency | **exact-instance check**: receipt+envelope bound to this exact instance; any other instance ⇒ reject | T-S1 |

## 3. Automated issuance only inside current policy and authority (owner Q1)

### 3.1 Issuance model (Tier 1 + Tier 2)

- **Issuer.** A Control-Plane-internal issuer module is the only writer of receipts
  (DP-004/DP-007). It is separate from Plane-M code per B1 (`backend/app/agents/`
  never imports `service.py`, `local_model.py` or C-min/model-gate modules); it
  holds a protected issuer key; there is no receipt-only PKI and no custom Runner
  signature protocol (DP-007/DP-002).
- **Automatic issuance scope.** Per Q1, issuance for a job is automatic **iff** the
  job is inside the administrator-approved Workspace Policy and every live
  precondition below holds at issuance time. There is no per-job human approval for
  in-scope jobs. The issuer must be **unable** to auto-approve: operations outside
  the policy's operation scope, unapproved external communication, privilege
  escalation, or any safety-boundary change — such requests are denied and audited,
  never receipted.
- **Issuance preconditions (all live, all fail-closed; each derives from the
  registry state of slice 2a and step-2 §2.2):**
  1. Actor authenticated as a Control-Plane principal; live membership/role
     authorization for the workspace (DP-015a); delegation grant only as an
     additional live-checked input (never a prerequisite) under the 2026-11-09
     resolution conditions (TTL 900–604800 s, live revalidation, no
     re-delegation, fail-closed invalidation on grantor-authority loss;
     `backend/app/service.py` lines ~1331–1342).
  2. Target workspace exists, `status='active'`, and its `(policy_id, policy_version)`
     pair is the current one.
  3. The exact policy is administrator-approved and current; `classification_ceiling`
     admits the job's data (default `none` ⇒ deny-all); classification authorization
     and destination authorization stay independent gates (I-5).
  4. `egress_mode='local_only'` (the only schema-permissible value); destination is
     the local workspace destination; `destination_allowlist` remains `'[]'` and no
     external destination is representable in a valid receipt.
  5. Adapter `registered`, inside the policy `adapter_allowlist`, capabilities ≤
     policy (E3), provider contract verification recorded
     (`provider_contract_verifications`) — recording alone never activates a
     provider.
  6. Workspace-to-`(runner_instance_id, adapter_id)` binding `enabled=1` (note: the
     slice-2a schema defaults bindings to disabled and this package does not change
     enabling semantics — enabling is an admin operation gated by existing role
     ceilings, E7).
  7. Runner instance enrolled, `status='registered'` (not disabled/revoked), with a
     fresh instance-scoped heartbeat echoing the job's policy version
     (`adapter_health.policy_version_echo`, T-T1).
  8. B6 is still active ⇒ **nothing is enqueued and nothing executes regardless of
     any receipt**. Issuance and enqueue are separate acts; E1 (§4) rechecks
     everything again before enqueue. While B6 is active the only operative
     dispatch-related behavior is the explicit `dispatch_attempt` rejection; no
     issuance code exists yet, and none may be written until the contract is
     owner-approved — so nothing in this precondition asserts any current runtime
     behavior.
- **Personal workspaces (Q2).** In a personal workspace whose policy ceiling the
  administrator has approved, the workspace owner's issuer-verified authority is the
  approval basis for own executions; no separate foreign-admin approval is required
  (owner Q2: "個人領域の操作に対し、根拠のない別管理者の都度承認を要求しない").
  The owner cannot override upper policy, cannot acquire shared/third-party data
  access through issuance, and the effective ceilings remain the
  administrator-approved policy values. Self-approval is recorded explicitly as
  approver = actor **only in this Q2 personal scope**; the administered/exception
  class keeps approver ≠ actor (DP-006). The precise scope wording of Q2
  self-approval is owner text (Q2 bullet 5) and is implemented only within it.
- **Approver authority mechanics.** Verified via the existing grantor/role model
  (DP-016): project owner or `organization_admin` role with legitimate authority
  over the target project/workspace; administrative permissions remain
  non-delegable; `NON_ADMIN` ceilings (`backend/app/service.py` line ~25) bound what
  any custom role can carry. Approver-authority loss after issuance triggers
  fail-closed invalidation in the DP-017 pattern; per DP-018/DP-008 the E2 live
  recheck observes current authority state, so an enqueued job whose authority was
  lost fails closed at E2.
- **No credentials anywhere.** The issuer consumes only presence metadata
  (`adapter_credentials.state` ∈ enrolled/absent/revoked). Provider credential
  supply is governed by **Entry 4 (2026-11-10): design/verification approved,
  actual supply not permitted at this stage** (DP-034b) and is not assumed by any
  part of this contract; no receipt, envelope, audit record or log may contain
  credential bytes or credential content (I-6, Q4).

### 3.2 What automated issuance is not

- It is not a bypass of B6, E1, E2, E3–E9, or the ADR-0012 activation gates.
- It is not permission to widen any policy value: the issuer reads policy; it never
  writes it. Policy writes stay admin-only under existing role ceilings (E7).
- It is not approval of new permissions: any `approve_jobs`-style permission or
  approval exception would have been a boundary change — **decided by Entry 2
  (2026-11-10): no new permission; approval authority derives from the existing
  Owner/Grantor/administrator roles** (DP-021; §9, item 2).
- It is not a delegation primitive: the receipt binds identity, not permission sets;
  effective permissions are rechecked live at every point (ADR-0013 §6).

## 4. Enforcement points — E1 and E2 responsibilities

### 4.1 E1 — Control Plane, immediately before enqueue

Ordered, fail-closed checklist. Every failure ⇒ reject **without enqueue**, audit
the denial (DP-019 reason enum; DP-020 naming), and stop:

1. **B6 gate first (I-4).** The existing `dispatch_attempt` rejection fires
   unconditionally while the boundary is unproven — with or without a Runner, with
   or without a receipt. No receipt logic may precede, mask or weaken it; a valid
   receipt does not lift B6 (ADR-0013 §4.1; step-2 §2.2).
2. **Envelope authenticity/freshness.** Verify the job envelope under the trust
   contract (DP-002/DP-007): schema version supported (B4), integrity intact,
   `job_id`/freshness checks pass, replay rejected (step-2 §3.2 E1; T-T1, T-R1).
3. **Receipt resolution — online.** Resolve the receipt against the authoritative
   issuer online (DP-007/DP-008): exists, `decision='approved'`, not expired
   (absolute, no grace, DP-012/014), revocation state current (DP-008), zero
   staleness (DP-009). **Unavailable authority ⇒ reject** — never "assume valid"
   (I-3).
4. **Binding verification.** Every binding of §2.3 re-checked live: job, actor
   (with live authorization, DP-015a), workspace active, exact policy version
   unchanged, adapter registered/allowlisted/capability-narrowed (E3), destination
   (`local_only` universe), operation, runner-instance binding consistency (DP-001).
5. **Classification/other gates remain independent.** E1 does not replace E6
   (classification before context assembly), E5 (egress), E9 (artifacts) — the
   receipt authorizes execution, nothing else (I-5, I-8).
6. **Audit.** Record the outcome with actor, approver/authority, workspace,
   destination, operation and decision (B7; DP-020). Pass and denial alike are
   audited; denial is never persisted as a receipt.

### 4.2 E2 — Runner, immediately before execution

Independent recheck by the Runner host. The Runner must not trust the enqueue-time
result (I-2). Ordered checklist; every failure ⇒ reject before any execution,
report/audit through the Control-Plane audit path:

1. **Runner-instance identity.** Verify its own immutable, revocable
   `runner_instance_id` binding (enrolled OS principal, pinned binary identity,
   transport identity per B5). The trust design policy is decided by **Entry 5
   (2026-11-10): OS-keystore per-instance identity, vetted TLS, admin
   one-time-challenge enrollment** ([HYBRID_RUNNER_TRUST_DESIGN.md](HYBRID_RUNNER_TRUST_DESIGN.md));
   the verification conditions (keystore/protection/RBAC/no-escalation/compromise
   procedures/independent review) must pass and activation stays separately gated,
   so until verified, no execution pathway exists at all (B6 holds).
2. **Envelope authenticity/freshness.** Independently verify the envelope: version
   support (B4), integrity, freshness, replay rejection (T-T1, T-S1).
3. **Receipt recheck — online.** Independently resolve the **same** receipt online
   (DP-007/DP-008): approved, non-expired (DP-012), revocation state current
   (DP-008), zero staleness (DP-009). A runner that is offline or otherwise unable
   to reach the authority **cannot prove non-revocation ⇒ it must not execute**
   (ADR-0013 §3; I-3).
4. **Binding recheck.** All §2.3 bindings re-verified by the Runner itself: actor,
   workspace (its own bound workspace only), exact policy version (also against its
   health echo), adapter, destination, operation, and the **exact-instance** check —
   the job must be bound to this runner instance; mismatch ⇒ reject (DP-001, T-S1).
5. **Execution-env preconditions.** Verified OS isolation for the target profile
   must be in place before any execution is enabled (ADR-0012 §4.5; Q3); the
   receipt passing is never sufficient for execution.
6. **Audit.** The execution-time authorization decision is attributed (actor,
   workspace, destination, operation, decision) through the Control-Plane audit
   path (B7; DP-020).

### 4.3 Cross-point semantics

- **Revocation between E1 and E2** must be visible at E2: E2's online check resolves
  current state, not enqueue-time state (DP-008/DP-018; canonical future test,
  step-2 §6.11).
- **Policy change between issuance and either check** ⇒ stale receipt ⇒ reject
  (immutable versioned rows make "stale" decidable; T-T1).
- **Authority loss after enqueue** ⇒ E2 live recheck fails closed (DP-017/DP-018).
- **Denial vs revocation:** a denial is an audit event at issuance time; revocation
  is an immutable event on an existing receipt; both reject at the next enforcement
  point (ADR-0013 §1/§3).
- **No grace periods, no fallbacks:** expiry, mismatch, unavailability and replay
  each reject outright (DP-009/DP-012/DP-014; I-3).

### 4.4 Relationship to the other enforcement points

E1/E2 are necessary, not sufficient. E3 (capability ≤ policy), E4 (in-runner OS
enforcement of filesystem/network scope), E5 (independent egress gate),
E6 (classification before prompt/context assembly and on all outputs/citations),
E7 (admin ceilings), E8 (session/adapter identity) and E9 (artifact gate) each
remain separate gates with their own threats and tests (step-2 §3.2). A valid
receipt never implies classification permission, destination permission, artifact
permission, or isolation proof.

## 5. Fail-closed semantics matrix (mandatory behaviors)

Mandatory at both E1 and E2, per ADR-0012 §4.1, step-2 §2.6/§6.11 and ADR-0013 §5.
These are Tier-0 semantics; only owner-decided mechanisms/limits sit on top of them.

| Condition | E1 (before enqueue) | E2 (before execution) |
|---|---|---|
| No receipt / approval denied | Reject before enqueue; audit denial; no receipt row is created for a denial | Not reachable (nothing enqueued); if observed anyway ⇒ reject |
| Revoked after enqueue | Reject on any recheck observing revocation | **Must** reject before execution (canonical test) |
| Expired | Reject; absolute expiry, no grace (DP-012); numeric TTL decided by **Entry 1 (2026-11-10): default 24 h / max 7 days** | Reject on the same rule |
| Stale policy (version changed) | Reject (new policy version ⇒ old receipt stale) | Reject; also reject on health-echo mismatch |
| Binding mismatch (workspace/adapter/destination/operation/runner instance) | Reject | Reject; exact-instance mismatch included (DP-001) |
| Unavailable authority | Reject — never assume valid | Reject — an unreachable authority is not proof of validity |
| Replay (same receipt/envelope again) | Reject | Reject |
| Approver/authority lost after issuance | Fail-closed invalidation (DP-017) | Live recheck observes loss ⇒ reject (DP-018) |
| B6 active (always, today) | Unconditional reject before all of the above (I-4) | No execution pathway exists |

The future regression matrix (denial, revocation between enqueue and execution,
stale approval, stale policy, binding mismatch, unavailable authority, replay —
each at E1 and E2 independently) is specified by step-2 §6.11 and ADR-0013 §5; it
is **not written here** and cannot exist in a way that requires or implies an
enabled dispatch path while B6 is active (§8.3).

## 6. Online / current authorization requirements

- **Currency at every point.** Authorization state is evaluated *now* at issuance,
  at E1 and at E2. Nothing authorizes from a cached, enqueue-time, or UI-era state
  (DP-009 zero staleness; DP-008 online check).
- **Availability is part of validity.** The authority being unreachable is a
  rejection condition, not a degraded-allow condition (I-3; DP-008). Consequence:
  runner execution requires Control-Plane reachability for the authorization check;
  the Runner↔Control-Plane transport itself is intranet traffic, distinct from
  external sends (step-2 §3.2 clarification), and any reachability/firewall path was
  unapproved external-communication territory — **now decided by Entry 3
  (2026-11-10) at the design level: an authenticated LAN-internal channel is
  approved as a design; each exact endpoint still requires design → verification →
  independent review → separate Owner approval, and no network path is activated by
  this package** (DP-031/032; §9, item 5).
- **Freshness inputs.** Heartbeat freshness and `policy_version_echo` must match the
  job's policy version at E1; the Runner re-derives its own view at E2 (step-2
  §2.5; T-T1).
- **Clock.** Prototype reuses the delegation Control-Plane clock (DP-013);
  production time source is a Q7-track decision; expiry is CP-authoritative online
  (DP-014) with no invented skew tolerance (any tolerance is measured, then
  reviewed — a measured-tolerance adoption would itself be a reviewed decision).
- **Revocation propagation.** Revocation is recorded as an immutable, audited event
  and takes effect before the next enforcement point; offline runners cannot
  out-stale it because they cannot execute while unable to verify (DP-003/DP-008).
- **Q6 alignment (analogue for execution inputs).** Where a job's inputs derive from
  research data, current-permission semantics apply: loss of source access denies
  the derived use at the enforcement point that observes it, independent of
  retention decisions (owner Q6; E9 for artifacts). The receipt contract adds no
  exception to this.

## 7. Audit requirements

- **Event set.** All receipt lifecycle events are audited under the `agent.receipt.*`
  convention (DP-020): issuance, denial, revocation, E1 recheck-pass, E1 rejection,
  E2 recheck-pass, E2 rejection, expiry-observed rejection, authority-loss
  invalidation. Exact event names beyond the convention are engineering detail
  (DP-020) and are not fixed here.
- **Attribution.** Every event carries actor, approver/authority basis, workspace,
  destination, operation, policy version, adapter, runner instance (where
  applicable) and the decision — the B7 attribution set (I-9).
- **Immutability.** Receipt state changes are new immutable events, never updates or
  deletes (DP-003; `delegation_*_no_update/_no_delete` and
  `workspace_policies_no_update/no_delete` trigger precedent). Retention/redaction
  is DP-022, gated on the Q7-track production decisions — no period invented here.
- **No secrets.** No credential bytes or credential-derived content in receipts,
  envelopes, audit records or logs (I-6, DP-023, Q4). Presence-only
  `adapter_credentials` remains the schema-level precedent, and its
  `credential_schema_is_presence_only` invariant check stays.
- **Audit-log protection.** T-T4 (audit-store tamper-evidence/confidentiality/
  access control) remains an unresolved activation blocker independent of this
  contract (I-9; step-2 §6.6).

## 8. Mandatory semantics vs contract details — explicit separation

### 8.1 Current code state (verified, for reconciliation honesty)

- `backend/app/agents/registry.py` (slice 2a, commits `e711c0c`, `1ee1315`)
  implements metadata-only registry tables including a **placeholder**
  `job_authorization_receipts` table (line ~161): fields `id, job_id, actor_id,
  workspace_id, policy_id, policy_version, adapter_id, destination, operation,
  decision CHECK IN ('pending','approved','denied'), issued_at, expires_at, revoked
  INTEGER DEFAULT 0`. **No issuance, resolution or verification code exists**; the
  test suite asserts the table stays empty
  (`tests/test_agents_registry.py` lines ~293, ~339).
- **Documentation/code tensions recorded (per AGENTS.md agent rules):**
  1. ADR-0013 §"Current state" states "no receipt table … anywhere in the package";
     slice 2a subsequently added the metadata-only placeholder table. ADR-0013's
     statement was accurate at its drafting time and is stale as of slice 2a.
  2. Step-2 §2.1 says the receipt schema is "concrete … only after the approval
     ADR", yet slice 2a created a placeholder table. The placeholder must not be
     read as approval of any contract; it holds no behavior and the contract
     field set (approver, authority basis, `schema_version`, immutable-event
     revocation, exact-instance binding carrier) is a superset the placeholder does
     not implement.
  3. The placeholder's `revoked` INTEGER column invites in-place mutation, which
     contradicts the mandatory immutable-event convention (ADR-0013 §8; DP-003).
     Any dispatch-capable schema work must replace this with the event-based
     representation under the owner-approved contract; this package neither
     changes the table nor treats it as a contract approval.
  4. Step-2 §6.11 test names are proposals while actual tests live under `tests/`
     with differing layouts (tension already recorded by ADR-0013 §Review history);
     both are cited without declaring either authoritative.
- `dispatch_attempt` (line ~716) audits `agent.dispatch.reject` and returns 409
  "Runner boundary is unproven; dispatch is disabled" regardless of Runner presence
  — the operative B6 gate this contract must never weaken.

### 8.2 What no decision may change (Tier 0 restated as a change-control rule)

The invariants I-1…I-10 of §1.1 are fixed points of the architecture. A future
owner decision may select mechanisms, values and limits **on top of** them (issuer
internals already fixed as engineering detail, TTL numbers, permissions, trust
root, credential supply, retention); it may not remove a binding, relax a
fail-closed condition, merge the planes, weaken B6/B1–B7, or convert any
"reject" in §5 into a conditional allow.

### 8.3 What is contract detail (and who may settle it)

- Engineering detail (settle via reviewed engineering work, e.g. the separate
  R-2B-2 package, classification-authoritative): canonical serialization and
  replay mechanics under online verification (DP-002), issuer-key custody inside
  the Control Plane (DP-007), reason enum values (DP-019), audit event names
  (DP-020), metadata-only schema representation (DP-001/DP-003/DP-023), expiry
  shape/clock (DP-012/013/014), invalidation trigger design (DP-016/DP-017).
- Owner decision (§9; resolved 2026-11-10 by Entries 1–6 at the design level for
  TTLs, permissions, trust, credential-supply scope and LAN-channel design; the
  remaining §9 items 6–9 stay 【要決定】): retention, real data/production, other
  safety-boundary changes.
- Never decidable by either: Tier-0 invariants (§8.2).

## 9. 【要決定】 inventory — unresolved owner choices

> **Resolution update 2026-11-11:** owner Entries 1–6 ([OWNER_DECISIONS_2026-11-10-ENTRIES.md](OWNER_DECISIONS_2026-11-10-ENTRIES.md), 2026-11-10) resolved items 1–5 of this inventory at the design level:
> - **Item 1 (TTL):** decided by Entry 1 — default 24 h / maximum 7 days; CP-authoritative absolute epoch-seconds; no grace; no expired-receipt reuse; in-scope auto-reissue as a new authorization decision.
> - **Item 2 (new permissions):** decided by Entry 2 — no new `approve_jobs` permission; authority derived from existing Owner/Grantor/admin roles; Q2-bounded personal self-approval.
> - **Item 3 (trust/enrollment/key custody):** design policy decided by Entry 5 (OS-keystore per-instance identity, vetted TLS, admin one-time-challenge enrollment, [HYBRID_RUNNER_TRUST_DESIGN.md](HYBRID_RUNNER_TRUST_DESIGN.md)); verification conditions and activation gates still apply.
> - **Item 4 (credential supply):** decided by Entry 4 — design/verification approved; actual supply not permitted at this stage; broker adoption needs evidence + independent review + separate Owner approval.
> - **Item 5 (external communication):** decided by Entry 3 at the design level — authenticated LAN-internal channel; each exact endpoint requires design → verification → independent review → separate Owner approval; no network path is activated by this package.
>
> Items 6–9 (unverified isolation profiles, receipt/audit retention D-1, real-data/production, other safety-boundary changes) remain **【要決定】**／別途承認. The table and the inline 【要決定】 markers elsewhere in this package are retained as the historical snapshot; where an inline marker corresponds to an item above, the Entry resolution supersedes it.

Each item cites its owner §4 wording and the classification row. None is resolved,
defaulted or implicitly assumed anywhere in this package.

| # | Item | Owner §4 wording | Classification |
|---|---|---|---|
| 1 | Receipt TTL values (default and maximum; whether a separate first-scope/exception class needs distinct values) | 「Receipt TTLの具体的な数値」 | DP-010/011 — OWNER_DECISION_REQUIRED |
| 2 | New permissions / approval exceptions (e.g. an `approve_jobs`-style permission, any approver-scope exception beyond Q2 self-approval) | 「新規の権限・承認例外」 | DP-021 — OWNER_DECISION_REQUIRED |
| 3 | Runner trust root, enrollment ceremony, key custody (incl. any runner-held verification key, rotation/revocation, job-freshness/signing contract) — also gates envelope mechanism choices beyond online verification | step-2 §6 item 5; owner §4 | OWNER_DECISION_REQUIRED (step-2 §6 item 5: decided before 実装順 3) |
| 4 | Provider credential supply (actual authentication material flow, per-adapter) — Q4 fixes the *constraint*, not the supply | 「プロバイダー認証情報の供給」 | DP-034b — OWNER_DECISION_REQUIRED |
| 5 | Unapproved external communication, including the Runner↔Control-Plane reachability/firewall path any online E2 check depends on | 「未承認の外部通信」 | DP-031/032 — OWNER_DECISION_REQUIRED |
| 6 | Each concrete isolation profile remains unverified/unapproved until its exact-platform evidence and separate activation decision | 「未検証の隔離プロファイル」 | OWNER_DECISION_REQUIRED per profile (Q3 policy direction resolved) |
| 7 | Receipt/audit retention and redaction | (Q7 track) | DP-022 — DEFERRED_WITH_GATE (gate D-1) |
| 8 | Real-data use; production exposure; production DB/time-source/audit-protection track | 「実データの使用」「本番公開」; step-2 §6 items 6/8 | OWNER_DECISION_REQUIRED / Q7 track |
| 9 | Any other safety-boundary change (incl. anything that would alter §8.2) | 「その他の安全境界変更」 | OWNER_DECISION_REQUIRED |

Presentation duty (owner standing instruction): unresolved items are to be presented
with options/recommendations/impacts — that recommendation layer exists in
[OWNER_DECISION_PROPOSAL_2026-11-09.md](OWNER_DECISION_PROPOSAL_2026-11-09.md) and
[OWNER_REEVAL-A-RECEIPT.md](OWNER_REEVAL-A-RECEIPT.md); this package adds no new
recommendation and changes no queue cell.

## 10. What this package does not do

- It approves no receipt contract as final; ADR-0013 remains DRAFT and the owner
  has approved no contract. Q1/Q2 resolve the issuance *policy direction*; they do
  not approve the contract artifact, any schema, or any code.
- It writes no code and no test; it creates no schema and changes no table; it
  provisions no key; it activates no Runner, no dispatch path, no egress, no
  credential use, no real data, no production exposure.
- It lifts no gate: B6, E1–E9, the ADR-0012 activation gates, T-T4, and the
  zero-tool regressions (`tests/unit/test_loop_tool_surface.py`,
  `tests/unit/test_loop_c_min.py`,
  `tests/integration/test_loop_c_min_launch.py`,
  `tests/integration/test_c_min_public_reference_scan.py`) all remain exactly as
  they are.
- It leaves every §9 item that no owner Entry decided 【要決定】 and adds no approval
  surface; items 1–5 carry the Entry 1–6 design-level resolutions recorded in §9
  (with their activation gates intact), and items 6–9 remain unresolved.

## 11. Verification requirements for the future implementation (not performed here)

When and only when the owner approves the receipt contract and separately
authorizes a dispatch-capable slice, the implementation must satisfy, at minimum
(restating step-2 §6.11 and ADR-0013 §Verification without re-deciding them):

1. The §5 regression matrix at E1 and E2 independently (denial, revocation between
   enqueue and execution, stale approval, stale policy, binding mismatch, unavailable
   authority, replay), in the existing test layout.
2. A regression proving the B6 `dispatch_attempt` rejection still fires with a
   valid-looking receipt present (the receipt path must not weaken the
   unproven-boundary gate).
3. Whole-package static import-graph tests for every B1 direction, including that
   issuer/receipt code never imports Plane-M modules and that cross-plane
   communication is transport-only through `runner_contract/` (B4 versioned).
4. Audit assertions for every §7 event with full attribution; immutability checks
   for receipt/event state; confirmation that `adapter_credentials` remains
   presence-only and no receipt/envelope/audit content contains credential
   material.
5. Zero-tool regressions pass unchanged; no test is deleted or weakened.

Until then, the only valid verification of this package is documentary: source-link
check against ADR-0012/0013 and the step-2 design, and that the repository still
contains no receipt-resolution code and no dispatch path.

## 12. Self-review notes (adversarial)

- **Q1 misread risk:** Q1 could be over-read as "owner approved automatic job
  execution". It approved automatic *approval issuance inside an
  administrator-approved policy/scope*; it did not approve dispatch, execution,
  egress, credentials, real data or production. The package repeatedly re-states
  this (§0, §3.2, §10) and keeps B6 unconditional.
- **Tier leakage risk:** engineering-detail rows (DP-002/007/008/009/012/013/014)
  could be misread as owner-approved values. §1.3 anchors each to its classification
  row and states the boundary-return rule; numeric TTLs are kept 【要決定】 with the
  delegation TTL cited as orientation only (as ADR-0013 §7 did).
- **Tension honesty:** the slice-2a placeholder table vs ADR-0013's "no receipt
  table" statement and vs the immutable-event convention is recorded in §8.1 with
  four numbered tension notes, rather than silently harmonized.
- **Circularity risk:** §4.2 makes E2's online check a hard precondition, which
  couples execution to Control-Plane reachability; the network path itself is
  unapproved (DP-031/032 【要決定】). This is surfaced in §6 rather than hidden:
  the contract is correct fail-closed, and the reachability approval is a separate
  owner decision.
- **Scope discipline:** no dispatch-capable test, schema or code is specified; the
  §11 list is a restatement of already-specified future requirements, not new
  executable design.

## Review history

- 2026-11-09: authored by slot R-2B-1 from ADR-0012 (ACCEPTED) §4.1, ADR-0013
  (DRAFT), the step-2 design §2.1/§2.2/§2.6/§3.1/§3.2/§3.3/§6/§6.11, owner
  decisions Q1–Q7 (2026-11-09 evening), the classification record
  (OWNER_QUEUE_CLASSIFICATION_2026-11-09.md) and verified source state in
  `backend/app/agents/registry.py` and `backend/app/service.py`. Documentation
  only; no code changed. Adversarial self-review recorded in §12.
- Status: DESIGN PACKAGE awaiting independent read-only review; owner approval of
  the receipt contract remains a hard prerequisite to any dispatch-capable work.
  This package activates nothing.
