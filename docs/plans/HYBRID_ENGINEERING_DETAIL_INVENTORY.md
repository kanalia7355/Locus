# Hybrid engineering-detail inventory — DP rows classified `ENGINEERING_DETAIL`

**Status: DESIGN DOCUMENTATION ONLY — inventory + residual-detail record.** This
package maps every row explicitly classified `ENGINEERING_DETAIL` in
[OWNER_QUEUE_CLASSIFICATION_2026-11-09.md](OWNER_QUEUE_CLASSIFICATION_2026-11-09.md)
(the authoritative classification, which is **cited, not duplicated or modified**)
onto the deliverables that already cover it, records the residual engineering detail
that still needs its own design treatment, and records technical options, evidence and
consequences for that residual. It decides nothing, approves nothing, activates
nothing: no dispatch, no isolation profile, no credential, no egress, no real data, no
production. It re-opens no settled owner decision and fills in no owner §4 item.

**Authority chain (descending):**

1. [ADR-0012](../architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md)
   (ACCEPTED) — §4.1 authoritative receipt, B1–B7, approval ≠ activation.
2. [Owner formal decisions Q1–Q7](OWNER_DECISIONS_2026-11-09-EVENING.md)
   (2026-11-09 evening) — settled; not re-opened here. Owner §4 unresolved items stay
   【要決定】 and are never resolved by inference in this package.
3. [OWNER_QUEUE_CLASSIFICATION_2026-11-09.md](OWNER_QUEUE_CLASSIFICATION_2026-11-09.md)
   — authoritative per-row classification.
4. Existing engineering deliverables this inventory builds on (never duplicates):
   [HYBRID_STEP2_RECEIPT_CONTRACT.md](HYBRID_STEP2_RECEIPT_CONTRACT.md) (R-2B-1),
   [HYBRID_ISOLATION_PROFILES.md](HYBRID_ISOLATION_PROFILES.md) (R-ISO-1),
   [HYBRID_ISOLATION_ENGINEERING_DETAIL.md](HYBRID_ISOLATION_ENGINEERING_DETAIL.md)
   (R-ISO-2).
5. [Hybrid threat model](../security/HYBRID_AGENT_THREAT_MODEL.md) and
   [ADR-0011](../architecture/ADR-0011-model-facing-zero-tool-gate-proposal.md) as
   standing constraints.

---

## 0. Purpose and non-goals

**Purpose.** R-ENG-1 was tasked to produce bounded engineering-detail work for the
rows classified `ENGINEERING_DETAIL`, packaged by the **receipt**, **profile** and
**manual-upload** groups, without duplicating the receipt contract, the isolation
profiles or the isolation engineering-detail package. Examination of those packages
shows they already carry the main design positions. This inventory therefore:

1. records the **coverage map** — which deliverable covers which row, at what depth;
2. identifies the **residual engineering detail** that those packages explicitly
   deferred (receipt contract §8.3: "settle via reviewed engineering work, e.g. the
   separate R-2B-2 package") and records options, evidence and consequences for it;
3. records the group findings, including that the manual-upload group contains **no**
   `ENGINEERING_DETAIL` row.

**Non-goals (each excluded on purpose):**

- No duplication or override of the queue classification; every row keeps its
  classification-record category as cited.
- No re-opening of Q1–Q7 and no resolution of any owner §4 item: receipt TTL numbers
  (DP-010/011), new permissions/approval exceptions (DP-021), Runner trust/enrollment/
  key management (DP-035–041, DP-043b), unverified isolation profiles, provider
  credential supply (DP-034b), unapproved external communication (DP-031/032), real
  data, production release, other safety-boundary changes — all stay 【要決定】.
- No code, schema, test, migration, key, endpoint, profile verification or test run.
- No weakening of ADR-0011/0012, B6, no-egress, least privilege, the current ACL,
  metadata-only audit or fail-closed behavior. Design evidence here never activates
  dispatch, isolation, credentials, egress, real data or production.

## 1. Row set and grouping

The classification record classifies exactly 25 rows as `ENGINEERING_DETAIL`
(DP-053b is separately `EXISTING_DECISION`). Grouped by delivery group:

| Group | Rows | Count |
|---|---|---:|
| A — Receipt / approval (DP-001–023 band) | DP-001, DP-002, DP-003, DP-007, DP-008, DP-009, DP-012, DP-013, DP-014, DP-016, DP-017, DP-019, DP-020, DP-023 | 14 |
| B — Profile / Runner enforcement detail (DP-024–053 band) | DP-033, DP-042, DP-044, DP-045, DP-046, DP-047, DP-048, DP-049, DP-051, DP-052, DP-053a | 11 |
| C — Manual upload / storage (DP-054–065 band) | *(none)* | 0 |
| **Total** | | **25** |

## 2. Coverage map

Depth values: **full** = the covering package adopts the design position and records
its boundaries; **full + residual** = position adopted, with concrete mechanics the
covering package explicitly deferred; **n/a** = no row exists in the group.

| Row | Group | Covering deliverable (section) | Depth | Residual recorded here |
|---|---|---|---|---|
| DP-001 | A | Receipt contract §1.3 row, §2.1, §4.2 (exact-instance E2 binding mandatory; carrier placement is detail) | full + residual | §3.2 A-3 (carrier + schema representation) |
| DP-002 | A | Receipt contract §1.3 row, §2.1 (online authoritative verification; no custom Runner signature protocol) | full + residual | §3.2 A-1 |
| DP-003 | A | Receipt contract §1.3 row, §7 (control store + immutable-event convention; production DB → Q7/DP-066) | full + residual | §3.2 A-3 |
| DP-007 | A | Receipt contract §1.3 row, §3.1 (CP-internal protected issuer key; no receipt-only PKI) | full + residual | §3.2 A-2 |
| DP-008 | A | Receipt contract §1.3 row, §4, §6 (online live revocation check at E1/E2, fail-closed on unavailability) | full | — |
| DP-009 | A | Receipt contract §1.3 row, §6 (zero staleness; no default negative cache) | full | — |
| DP-012 | A | Receipt contract §1.3 row, §2.1, §5 (absolute expiry, no grace) | full + residual | §3.2 A-6 (numbers stay 【要決定】) |
| DP-013 | A | Receipt contract §1.3 row, §6 (delegation CP clock reuse; production source → Q7) | full | §3.2 A-6 (production source gated, not chosen) |
| DP-014 | A | Receipt contract §1.3 row, §6 (CP-authoritative online expiry; no invented skew) | full + residual | §3.2 A-6 |
| DP-016 | A | Receipt contract §1.3 row, §3.1 (existing grantor/role model; no dedicated registry) | full + residual | §3.2 A-7 |
| DP-017 | A | Receipt contract §1.3 row, §3.1 (fail-closed invalidation mirroring grant-invalidation triggers) | full + residual | §3.2 A-7 |
| DP-019 | A | Receipt contract §1.3 row, §4.1 (closed versioned reason enum → 409 pattern; values deferred) | full + residual | §3.2 A-4 |
| DP-020 | A | Receipt contract §1.3 row, §7 (`agent.receipt.*` convention; exact names deferred) | full + residual | §3.2 A-5 |
| DP-023 | A | Receipt contract §1.3 row, §7 (metadata-only, no credential bytes; schema is design detail) | full + residual | §3.2 A-3 |
| DP-033 | B | Isolation engineering detail §2.1 (bounded transfer comparison; staged-bundle baseline) | full | — |
| DP-042 | B | Isolation engineering detail §2.2 (same-authority live status; fail closed on uncertainty) | full | — |
| DP-044 | B | Isolation engineering detail §2.2 (opaque one-use reference; closed versioned contract) | full | — (contract-detail only; §4.1) |
| DP-045 | B | Isolation engineering detail §2.2 (vetted transport + closed schema; no second signature family) | full | — (contract-detail only; §4.1) |
| DP-046 | B | Isolation engineering detail §2.2 (CP-authoritative freshness; no second TTL/skew) | full | §4.1 (numeric bounds inherit DP-010/011) |
| DP-047 | B | Isolation engineering detail §2.2 (durable CP job ID consumed atomically online) | full | — |
| DP-048 | B | Isolation engineering detail §2.2 (single CP authority; full binding set; exact enrolled Runner) | full | — |
| DP-049 | B | Isolation engineering detail §2.3 (result digest bound to job/instance; live revalidation before release) | full | — (contract-detail only; §4.1) |
| DP-051 | B | Isolation engineering detail §2.4 (measurement criteria; ADR-0012 cancellation semantics preserved) | full | §4.1 (numbers from future measured plans) |
| DP-052 | B | Isolation engineering detail §3 (test-inventory criteria; never run here, never activating) | full | — |
| DP-053a | B | Isolation engineering detail §4 (evidence-binding contract; design-only) | full | — (design-only; §4.1) |

Group C: no `ENGINEERING_DETAIL` rows exist; see §5.

## 3. Group A — receipt and approval engineering detail

### 3.1 Already covered (cited, not restated)

The receipt contract §1.3 (Tier-2 table) adopts the design position for every Group A
row, each anchored to its classification row, with the Tier-0 invariants (I-1…I-10),
the E1/E2 enforcement-point checklists (§4), the fail-closed matrix (§5) and the
audit requirements (§7) around them. `EXISTING_DECISION` rows DP-015a/DP-018 and
`DEFERRED_WITH_GATE` row DP-022 are adopted there as-is and are **not** touched here.

The receipt contract §8.3 explicitly names what remains contract detail to be settled
by reviewed engineering work: canonical serialization and replay mechanics (DP-002),
issuer-key custody inside the Control Plane (DP-007), reason enum values (DP-019),
audit event names (DP-020), metadata-only schema representation (DP-001/003/023),
expiry shape/clock (DP-012/013/014), invalidation trigger design (DP-016/017).
DP-008 and DP-009 are fully positioned with no deferred mechanics. §3.2 records
options, evidence and consequences for exactly those residual items.

### 3.2 Residual engineering detail — options, evidence, consequences

Every item below records **candidate options only**. None is adopted, implemented or
activated by this inventory. Selecting an option is future reviewed engineering work
(receipt contract §8.3; e.g. the R-2B-2 package) and any dispatch-capable slice needs
the owner-approved receipt contract plus separate slice authorization first. Any
option that would affect a Tier-0/Tier-1 statement returns to the owner.

#### A-1 — Canonical serialization and replay mechanics (DP-002)

| Option | Consequences |
|---|---|
| **O1: canonical-JSON serialization** with a CP-computed integrity value over canonical bytes (fixed key ordering/encoding, duplicate-key and unknown-field rejection); receiver re-canonicalizes and compares before resolving the receipt online. | Envelope can carry self-describing metadata; integrity failures are detectable before the online call; still requires online verification (no offline trust, I-2/I-3 preserved). Adds canonicalization test-vector burden. |
| **O2: no serialized authorization payload at all** — the receipt exists only as Control-Plane state; both E1 and E2 resolve it online by `receipt_id`; the envelope carries only the opaque reference plus non-authorization metadata. | Minimal machinery and replay surface; all binding authority sits in one online resolution (consistent with DP-048's single-authority posture). The envelope's job metadata is then purely advisory and must never be treated as authorization-bearing. |

Both options keep replay prevention where the packages already place it: the **one-use
atomic consumption of the durable Control-Plane job identity** (DP-047 posture,
isolation engineering detail §2.2) — no separate nonce ledger is created by either
option. Neither option permits an offline "assume valid" path; an unreachable
authority rejects (I-3).

**Evidence needed before settling:** threat-model mapping (T-T1 stale policy, T-R1
replay) for the chosen option; canonicalization ambiguity/duplicate-key/unknown-field
rejection test vectors; confirmation that no option weakens the B6
`dispatch_attempt` rejection or adds a cross-plane channel beyond the versioned
`runner_contract/` transport (B1/B4).

#### A-2 — Issuer-key custody inside the Control Plane (DP-007)

| Option | Consequences |
|---|---|
| **O1: symmetric key in CP-controlled configuration** with restrictive host ACL, loaded at CP start, never exported to job/adapter processes. | Simplest prototype-compatible custody; loss of the config file compromises prototype receipts only (fail-closed reissue path). Requires file-protection verification evidence. |
| **O2: OS credential-store / keyring custody** on the CP host (platform keystore, non-exportable to job processes). | Stronger at-rest protection; adds platform dependency and a startup-unavailability failure mode that must fail closed. |
| **O3: no key at all** — Option O2 of A-1 (pure online state). | No custody surface at all; replay/integrity rests entirely on the online channel and atomic consumption. |

Mandatory in every option: no receipt-only PKI, no custom Runner signature protocol,
and no asymmetric key provisioned to runners — any such step imports the Runner
trust/enrollment/key-custody decision (DP-035–041) and stays 【要決定】. Key material
never appears in receipts, envelopes, audit records or logs (I-6; DP-023), never
crosses to Plane-M code (B1), and any production rotation/lifecycle follows the Q7
track, not this design.

**Evidence needed:** proof that the chosen custody survives a job-process compromise
within the assumed threat model; startup/unavailability fail-closed tests; absence-of-
key-material scans (secret scan pattern) over receipt/audit artifacts.

#### A-3 — Metadata-only schema representation and immutable-event state (DP-001, DP-003, DP-023)

The receipt contract §2.1 defines the logical field set as a **superset** of the
slice-2a placeholder table (`job_authorization_receipts`, registry.py line ~161), and
§8.1 records the tension that the placeholder's `revoked INTEGER` column invites
in-place mutation contrary to the immutable-event convention. Residual design:

- **Field additions to carry at representation time:** `approver`/authority basis,
  `schema_version`, the exact-instance binding carrier (DP-001: receipt-field vs
  envelope-field placement — either is acceptable provided the E2 recheck binds
  receipt + envelope + exact `runner_instance_id` and a mismatch rejects).
- **Revocation/state representation options:**
  - **O1: append-only receipt-event rows** (`issued`/`denied`/`revoked`/…), current
    state derived from the event stream, following the
    `delegation_*_no_update/_no_delete` and `workspace_policies_no_update/no_delete`
    trigger precedent (`backend/app/service.py` lines ~169–255).
  - **O2: immutability triggers on the receipt row plus a separate event table** for
    state transitions. Equivalent guarantee, slightly different read pattern;
    no weakening of either trigger direction is permitted.

**Consequences:** any dispatch-capable schema work must replace the placeholder's
mutable column with the event-based representation under the owner-approved contract;
the placeholder must not be read as contract approval (receipt contract §8.1 note 3).
Production DB technology stays on the Q7 track (DP-066); no DDL exists or is proposed
as executable here. Metadata-only content is mandatory (DP-023): no credential bytes
or content anywhere (I-6; presence-only `adapter_credentials` precedent and its
`credential_schema_is_presence_only` invariant stay).

**Evidence needed:** trigger-level immutability tests; an assertion that receipt
resolution code continues not to exist while B6 is active (the existing test suite
asserts the placeholder table stays empty — `tests/test_agents_registry.py` ~293/~339
— and no test may be weakened to change that).

#### A-4 — Closed versioned rejection-reason enum values (DP-019)

Candidate closed set (illustrative, **not adopted**; versioned, fail-closed on unknown
values), mapped to the existing 409 `dispatch_attempt` → `_deny(409, …)` pattern:

`B6_ACTIVE` · `RECEIPT_NOT_FOUND` · `RECEIPT_EXPIRED` · `RECEIPT_REVOKED` ·
`POLICY_STALE` · `BINDING_MISMATCH` · `AUTHORITY_UNAVAILABLE` · `REPLAY_DETECTED` ·
`SCHEMA_UNSUPPORTED`

**Consequences:** the enum is versioned; adding values is a versioned change, never a
relaxation of a fail-closed condition; an unknown/missing reason rejects; every
rejection is audited with the full attribution set (DP-020) and never persisted as a
receipt (ADR-0013 §1). `B6_ACTIVE` remains the unconditional first rejection while the
boundary is unproven (I-4).

**Evidence needed:** regression mapping of each enum value to one §5 fail-closed
matrix row; assertion that no enum value can express a conditional allow.

#### A-5 — Audit event-name set under `agent.receipt.*` (DP-020)

Candidate set (illustrative, **not adopted**), under the existing `agent.*` audit
convention (audit port in `backend/app/agents/registry.py`):

`agent.receipt.issued` · `agent.receipt.denied` · `agent.receipt.revoked` ·
`agent.receipt.e1.pass` · `agent.receipt.e1.reject` · `agent.receipt.e2.pass` ·
`agent.receipt.e2.reject` · `agent.receipt.expired.reject` ·
`agent.receipt.authority_loss`

**Consequences:** every event carries the receipt contract §7 attribution set (actor,
approver/authority basis, workspace, destination, operation, policy version, adapter,
runner instance where applicable, decision); receipt state changes are new immutable
events (DP-003); retention/redaction stays DP-022, gated (no period invented here);
T-T4 audit-store protection remains an unresolved activation blocker.

**Evidence needed:** per-event attribution assertions in the future regression suite
(receipt contract §11.4); confirmation that no event name or payload carries
credential material (DP-023).

#### A-6 — Expiry shape and clock (DP-012, DP-013, DP-014)

The positions are already adopted: absolute expiry, no grace (DP-012); delegation
Control-Plane clock reuse for the prototype (DP-013; production time source → Q7,
DP-066); CP-authoritative online expiry with no invented skew tolerance (DP-014).
Residual consequences recorded here:

- **No numeric value is set anywhere in this inventory.** Receipt TTL default/maximum
  stay DP-010/011 【要決定】 (owner §4「Receipt TTLの具体的な数値」).
- DP-046's envelope freshness inherits the same unresolved numbers: the envelope has
  no second TTL and no skew grace, and its effective freshness bounds are exactly the
  receipt bounds once the owner sets them — **DP-046 cannot and does not set them**
  (task boundary; isolation engineering detail §2.2 freshness row).
- Practical consequence of "no grace, no skew tolerance": expiry decisions read the
  CP-authoritative clock at the enforcement point; the Runner does not decide expiry
  from its own wall clock; measured-tolerance adoption, if ever proposed, is a
  separate reviewed decision (DP-014 posture).
- Long-running jobs interact with absolute expiry: automatic reissue for in-scope jobs
  is the proposal-layer recommendation (unapproved option, cited for orientation in
  classification Entry 1); nothing here assumes it.

#### A-7 — Approver-authority verification and invalidation triggers (DP-016, DP-017)

The positions are adopted: approver authority verified via the existing grantor/role
model (`_delegation_authority`, `backend/app/service.py` lines ~1046–1075;
project owner or `organization_admin` on the target project; administrative
permissions non-delegable; `NON_ADMIN` ceilings bound custom roles) — no dedicated
approver registry; authority loss triggers fail-closed invalidation mirroring the
`delegation_grantor_membership_delete` / `delegation_grantor_role_update` pattern.
Residual design options:

- **O1: invalidation materialized as a receipt-event row** at the moment authority
  loss is observed (event-driven), so the next E1/E2 online resolution sees it.
- **O2: no materialized invalidation record** — the E1/E2 online authority recheck
  itself observes current grantor/role state and rejects; the invalidation is purely
  an audit observation.

**Consequences:** per DP-018/DP-008 the E2 live recheck observes current authority
state in both options, so an enqueued job whose authority was lost fails closed at E2
either way; O1 only accelerates visibility and adds an auditable record. No new
permission is created by either option — an `approve_jobs`-style permission or any
approval exception stays DP-021 【要決定】 (owner §4「新規の権限・承認例外」), and Q2
personal-workspace self-approval is implemented only within the owner's Q2 wording
(approver = actor only in that scope; administered/exception class keeps approver ≠
actor, DP-006).

## 4. Group B — profile / Runner enforcement engineering detail

### 4.1 Already covered; boundary conditions that travel with the rows

All eleven Group B rows are covered **full** by
[HYBRID_ISOLATION_ENGINEERING_DETAIL.md](HYBRID_ISOLATION_ENGINEERING_DETAIL.md)
(§2.1 DP-033; §2.2 DP-042/044–048; §2.3 DP-049; §2.4 DP-051; §3 DP-052; §4 DP-053a),
with the conformance checklists (§5) and the gated-choices register (§6). This
inventory duplicates none of that design and adds none. The task's boundary
conditions are restated here only as travel-with-the-row constraints so they are not
lost when the package is consumed:

- **DP-046:** its freshness design is CP-authoritative online with no second envelope
  TTL and no skew grace; **its numerical bounds inherit the unresolved receipt TTL
  choices (DP-010/011 【要決定】) and cannot be set by any engineering work** — not by
  this inventory, not by the isolation package, not by a future implementation slice.
- **DP-044 / DP-045 / DP-049:** contract-detail design only. They authorize no
  implementation, no transport configuration, no endpoint, no key custody and no
  artifact path; DP-049 adds an artifact signature only if a documented channel
  change justifies it, and then as a separately reviewed design change.
- **DP-053a:** evidence binding is design-only. Binding evidence to the exact
  build/config/tests never activates a profile; activation authority stays a separate
  explicit owner decision (DP-053b, existing rule).
- **DP-051:** no quota, deadline, admission or cancellation number is set anywhere;
  values come only from future measured, separately approved workload plans, and
  ADR-0012 cancellation semantics are preserved unchanged.
- **DP-052:** the test inventory defines future acceptance criteria; **no test was
  run for this docs-only task**; tests never activate a profile, never contact a real
  endpoint and never create a dispatch path.
- **DP-033/DP-042/DP-047/DP-048:** behavior is conditional on a separately approved
  Runner↔Control-Plane channel (DP-031/032 【要決定】) and on the trust/enrollment
  cluster (DP-035–041 【要決定】); neither is authorized by any of these packages.

**Residual engineering detail for Group B: none that is currently workable.** Every
remaining open point in the isolation engineering-detail package is explicitly
gated on an owner decision (its §6 register) or on future measurement (DP-046/051
numbers); inventing those values here would resolve owner §4 items by inference,
which is prohibited. No further design treatment is produced.

## 5. Group C — manual upload / storage engineering detail

**Finding: the classification record contains no `ENGINEERING_DETAIL` row in the
DP-054–065 band.** The manual-upload group consists of `OWNER_POLICY_RESOLVED` rows
(Q5/Q6: DP-054, DP-055, DP-058, DP-059a), `EXISTING_DECISION` rows (DP-057a, DP-062a,
DP-064a, DP-065), and `DEFERRED_WITH_GATE` rows (gates D-1/D-2/D-3: DP-050, DP-056,
DP-057b, DP-059b, DP-060a, DP-060b, DP-061, DP-062b, DP-063, DP-064b) — per the
authoritative classification record, which is cited rather than reproduced. The
deferred rows start only under their recorded gates (connector design phase,
production retention track), none of which is open here.

Consequences for this task: no engineering-detail design is produced or needed for
the manual-upload group. The manual-upload flow itself is implementation work owned
by [R-STORAGE-1](agent-work/R-STORAGE-1-manual-upload.md) under Q5/Q6, not
engineering-detail design; inventing connector or retention design here would
pre-empt gated decisions (D-1/D-3) and is deliberately not done.

## 6. Standing invariants and non-weakening clause

Applies to every option and residual item in this inventory:

- ADR-0011 (Plane-M zero-tool boundary), ADR-0012 (dual-plane separation, B1–B7,
  E1–E9, approval ≠ activation), B6 dispatch rejection, fail-closed on uncertainty,
  no-egress (`local_only` the only operative value), least privilege, the current
  ACL model, and metadata-only audit are unchanged. No option above touches them;
  an option that would would be a safety-boundary change and returns to the owner.
- Design evidence recorded here never activates dispatch, isolation, credentials,
  egress, real data or production. While B6 is active, `dispatch_attempt` rejects
  unconditionally, with or without a receipt, and no issuance/resolution code exists
  or is specified as executable.
- Every owner §4 unresolved item stays 【要決定】; none is defaulted, implicitly
  assumed or resolved by inference anywhere above. The presentation duty for those
  items (options/recommendations/impacts) remains with the existing proposal layer
  (OWNER_DECISION_PROPOSAL / OWNER_REEVAL-A/B/C); this inventory adds no new
  recommendation for them and changes no queue cell.

## 7. Adversarial self-review

- **Duplication risk:** §3.2 could drift into re-deciding receipt-contract positions.
  Each item cites the covering section first and records only the explicitly deferred
  mechanics; candidate enum/event values are labelled illustrative and not adopted.
- **TTL leakage risk:** A-6 restates the DP-046/DP-010/011 dependency in both group
  sections so that no reader can mistake envelope freshness bounds for derivable
  numbers; no duration, tolerance or cache interval is set anywhere.
- **Owner-§4 inference risk:** A-2 and A-7 deliberately stop at the trust/enrollment
  cluster (DP-035–041) and the permission question (DP-021); the nearest engineering
  option consistent with the settled boundary is recorded, and crossing the boundary
  is named as returning to the owner, not chosen.
- **Group C temptation:** the empty manual-upload group could invite "helpful"
  connector/retention design. §5 records the finding and refuses it on gate grounds.
- **Evidence overclaim:** nothing was run, verified against a live authority, or
  activated; the only verification of this package is documentary (source-link and
  consistency checks below).
- **Independent review:** the task prohibits subagent delegation; the adversarial
  self-review above is implementer-side. The receipt contract already requires
  independent review for the DP-044/045/049 contract-detail work before any
  dispatch-capable slice; that requirement is carried forward, not claimed as done.

## 8. Documentary verification performed for this inventory

- All 25 classification rows re-checked against
  OWNER_QUEUE_CLASSIFICATION_2026-11-09.md (14 + 11 + 0 = 25; DP-053b excluded as
  `EXISTING_DECISION`).
- Coverage claims in §2 checked against receipt contract §1.3/§2/§3/§4/§5/§7/§8.3 and
  isolation engineering detail §2–§4/§6.
- Source anchors spot-checked: `backend/app/agents/registry.py` (placeholder receipt
  table, `dispatch_attempt` rejection, audit port), `backend/app/service.py`
  (immutable-event trigger precedent, `_delegation_now`, `_delegation_authority`,
  delegation TTL conditions), `tests/test_agents_registry.py` (empty-table
  assertions). No code or test was modified.

## Review history

- 2026-11-09: authored by slot R-ENG-1 from the classification record, owner
  decisions Q1–Q7, ADR-0012, the receipt contract (R-2B-1), the isolation profiles
  (R-ISO-1), the isolation engineering detail (R-ISO-2) and verified source state in
  `backend/app/agents/registry.py`, `backend/app/service.py` and
  `tests/test_agents_registry.py`. Documentation only; nothing activated; adversarial
  self-review recorded in §7. Independent review not performed in this task (no
  subagents permitted); required reviews remain future gates, not claimed passes.
