# Owner decision proposal — consolidated DP-001…072 (2026-11-09)

**Status: recommendation layer only.** This merges, without re-evaluating, the three integrated source reviews linked below. Every queue item remains 【要決定】; this document does not fill owner-decision cells or approve implementation. Nothing here activates dispatch (B6), Runner/isolation, external egress, provider credentials, connectors, or production exposure. ADR-0011’s model-facing zero-tool gate and accepted ADR-0012’s dual-plane gates, live checks, fail-closed behavior and separation of approval from activation remain intact. For every safety-boundary item, the recommendation is design guidance only.

**Grounding:** [shared grounding pack](agent-work/OWNER_REEVAL-GROUNDING.md); [initial product spec](../requirements/PRODUCT_SPEC.md); [architecture](../architecture/ARCHITECTURE.md); [owner decision queue](OWNER_DECISION_QUEUE_2026-11-09.md); [owner decision register](OWNER_DECISION_REGISTER.md). The reviewed item text, evidence, option framing and impacts remain in each linked source; this proposal keeps each entry compact. These are not 72 new approvals.

## Executive summary

| Group | Items | Recommended direction | Source flags (🚫 / ⚠ / 📈) | Genuine owner decisions remaining |
|---|---:|---|---:|---|
| A — receipt / DP-001–023 | 23 | Authoritative Control-Plane issuer; one receipt per job; policy-driven issuance within pre-approved scope, human decision for exceptions; online live checks, existing role/authority and audit patterns. Keep adapter/CLI unchanged. | 2 / 13 / 11 | Ratify the receipt contract and its trust/verification and TTL values; choose exception classes and personal-workspace self-approval treatment; settle residual audit/error details. Production clock/DB/retention decisions remain in their existing tracks. |
| B — isolation and Runner trust / DP-024–053 | 30 | Graded, platform-tested local/server profiles; only proven OS-enforced boundaries run; no host fallback. Minimal authenticated, revocable per-instance trust; authoritative online authorization and fail-closed behavior; no universal VM/PKI/hardware stack. | 0 / 20 / 14 | Set supported platforms/threat profiles and exact verified isolation/transfer/network profile; settle provider-auth feasibility, Runner enrollment/trust lifecycle, residual job/artifact contract and measured operation/evidence parameters. Any activation remains a later, separate owner decision. |
| C — storage ACL and housekeeping / DP-054–072 | 19 | Preserve current manual-upload/research flow; keep source ACL an additive live authorization gate; fail closed for stale/unverifiable source state. Defer connectors, source-write, copy/retention and production choices to their proper design/approval tracks. | 0 / 0 / 0 | Define D5/connectors and source identity/freshness/revocation/deletion/storage rules when that connector design is authorized; decide open production operations/provider/session and remaining org-management UI details. Do not reopen resolved project-scoped delegation. |

Flag counts above count items carrying each flag in their source review (an item can carry multiple flags). Group C’s prose notes some unsupported values/constraints without applying a formal ⚠ flag; those caveats remain visible in its item summaries and are not silently recounted. Per-item flags and source wording are retained below. A/B and B/C source row boundaries are complementary: A is DP-001–023, B is DP-024–053, C is DP-054–072.

## Coherence check across groups

### Reconciled tensions and scope boundaries

1. **Receipt signing vs online job-envelope authorization (A DP-002/007 vs B DP-044/045/048).** A proposes an issuer-signed receipt as an audit-integrity artifact; B recommends no second Control-Plane job-envelope signature/key family when the Runner obtains current state online over authenticated transport. Keep these concerns distinct: the authoritative decision and E1/E2 checks are online, independently fail closed, and bind the exact job/policy/actor/workspace/adapter/destination/operation plus enrolled Runner; do not treat a detached signature as authorization or require the Runner to implement signature verification. If a receipt signature is retained for stored-audit integrity, it is CP-internal and not a second envelope trust protocol. The need for that audit signature remains a decision, not runtime permission.
2. **Runner identity in receipt vs exact Runner check (A DP-001 vs B DP-048).** These are compatible: do not duplicate `runner_instance_id` in the receipt; the authoritative envelope/workspace binding and E2’s live exact-instance check enforce the enrolled Runner. Instance identity remains part of the authorization check, not a receipt field.
3. **Receipt TTL vs job-envelope freshness and clock skew (A DP-010–014 vs B DP-046).** A recommends the delegation precedent (24-hour default/7-day maximum); B does not select an independent numeric envelope validity interval and cautions against universal zero-skew assumptions. Treat the receipt expiry as the sole job authorization expiry and use the authoritative Control-Plane clock for online decisions. Runner clock-skew tolerance is not a separate receipt requirement unless a transport check actually compares clocks; if one is needed, measure it. Do not create a second, conflicting envelope TTL or infer clock-skew grace. The receipt values still require explicit owner ratification; PH2-A-01’s grant TTL decision is precedent, not automatic approval for job receipts.
4. **Control-store persistence vs production DB (A DP-003/022 vs C DP-066/068/069).** Reusing the existing prototype Control-Plane store and immutable-event convention is a minimal design recommendation, not a production technology choice. Receipt/audit rows follow the existing deferred production retention decision; no separate receipt store, production DB, retention period or secure-erasure policy is approved here.
5. **Human approval, delegation, and admin/personal scope (A DP-004–006/015–018/021 vs B DP-039/053 and C DP-062/071).** An authoritative receipt is mandatory; human approval for every in-scope job is not. The issuer uses the current grantor/role model and live actor authorization; delegation is not a membership prerequisite. The proposed personal-workspace owner self-approval carve-out remains an actual owner question, not a settled exception. Runner enrollment authority and workspace/source administration are separate controls and must not create new privileges or merge personal and admin scopes. PH2-A resolved authority and project-scoped delegation are not reopened.
6. **Isolation layers vs hybrid practicality (B DP-024–030/033/035–039).** “Local and server” does not mandate identical technology stacks, nor justify universal VM-per-job, rootless OCI plus every defense layer, enterprise PKI, hardware attestation or a bespoke broker. Define deployment risk profiles and prove the minimum OS-enforced controls for each. If no profile passes, that target remains unavailable; no host execution or silent downgrade.
7. **Runner control-plane traffic vs egress/connectors (B DP-031/032 vs C DP-055/062/065).** A future, exact, separately authorized private Runner↔Control-Plane channel is not permission for provider traffic, connectors, or external AI. Default deny remains. Source-read permission never constitutes egress consent; external data use needs its own authorized policy/approval. No network or credential activation follows from this proposal.
8. **Receipt revocation and source/artifact revocation (A DP-008/017/018 vs B DP-042/043/049/050 vs C DP-056–063).** Maintain live checks at every applicable authorization/output boundary; on uncertainty, fail closed. A receipt/Runner revocation does not replace document ACL/classification/provenance checks; source permission loss must prevent later access to derived material. Do not promise synchronous interruption beyond accepted ADR semantics, invent a numeric propagation SLA, or release an uncertain active job’s result.
9. **Agent Adapter compatibility (A cross-cutting verdict and DP-023; B DP-034/048).** Receipt, signing, workspace, trust and policy bookkeeping stay on Locus’s control/runner planes. Keep the existing single adapter operation and official agent/CLI authentication model; do not require agent rewrites or pass Locus credentials to tool processes. Any provider-specific credential mechanism remains separately unapproved.
10. **Storage ACL scope and research utility (C DP-054–065 vs product priorities 1/3).** Source ACL is an additional gate, never a replacement for Locus project membership, explicit deny, publication grants, personal ownership or attachment ACL. The connector design is open; this does not narrow manual upload, citations, retrieval or analysis for unconnected documents. Do not infer broad admin access to personal sources or upstream write/delete authority.
11. **Redundant/overlapping owner questions (C DP-065/071, B DP-043/048/053).** DP-065’s governing invariant—read access does not consent to external egress—is already required by DATA-012 and the Product Spec; do not reopen it as permission to send. Only a future, separately scoped egress proposal is owner-decidable. DP-071 can concern residual recipient-side/org-management UI only; organization-wide delegation remains deferred by the resolved PH2-A decision. B’s mandatory receipt bindings, cancellation/hold, independent review and separate activation cannot be weakened by treating their implementation details as open.

### Repeated rootless constraints (⚠) and handling

- **Invented time/freshness/cache limits recur across A and B:** A DP-009/010/011/014 and B DP-040/042/046/052/053 warn against unsupported staleness, TTL, skew, propagation, or evidence-expiry values. Keep one receipt-expiry decision and authoritative online time; measure any transport/cache tolerance before proposing one. Do not let a second Runner envelope TTL contradict it.
- **Added technology/authority machinery recurs in A and B:** A DP-007/016/021 flags receipt-only PKI, a parallel approver registry, and a new approval permission; B DP-026/029/033/035–039/044–045/049 flags universal brokers, rootless/defense stacks, dedicated CA/signature systems, hardware gates and artifact signatures. Prefer existing authority, authenticated transport and the minimum proven deployment-specific controls. Necessary OS-enforced isolation, authenticated identity, denied-by-default behavior and the ADR-0012 gates are not rootless constraints and must not be dropped.
- **Retention uncertainty appears in all groups, with flags applied differently:** A DP-022 flags inventing a receipt-specific retention period; B DP-050 flags new fixed artifact/audit periods; C DP-060/064/068/069 keeps originals, source audit and production storage/audit periods open without marking individual items ⚠. Consolidate these under the existing production retention/audit decisions; do not assign a period or imply deletion/secure erasure that is not established.
- **Admin/confirmation burden repeats:** A DP-005/006 flags universal per-job human approval and unconditional second-principal approval for a sole personal-workspace owner; B DP-039 flags a mandatory second local enrollment channel. Retain authenticated, issuer-verified admin control and exception approval, but do not add confirmation gates without a demonstrated boundary need.
- **No corresponding rootless flags are assigned in C’s source.** In particular, DP-056’s numeric freshness caveat and DP-061’s absent multi-source concept are not marked as ⚠ by that source; their substantive open points remain as written, not silently relabeled.

### Over-engineering to drop or phase

Drop as universal requirements: receipt-specific store and custom Runner canonicalization/signature protocol; separate approver registry/permission and receipt-only PKI; negative-cache/staleness machinery by default; universal VM-per-job, full rootless-OCI-plus-all-defense stack, exhaustive host matrix, mandatory enterprise PKI/TPM/quorum, universal second enrollment channel, bespoke broker/image supply chain, duplicate nonce service, extra artifact-signing key, and arbitrary fixed quotas/SLAs/retention/evidence windows. Phase only when a tested platform or deployment threat model justifies the added layer, with owner review where the boundary or policy changes. Do **not** drop mandatory ACL filtering, revocation, fail-closed checks, authenticated/revocable instance identity, narrow data transfer, cancellation/hold semantics, metadata-only audit, independent review, or explicit activation gates.

### Check against the owner’s seven priorities

1. **Research support first:** recommendations preserve manual upload, retrieval/citation/analysis and avoid disabling an entire hybrid workflow just because one platform profile is unsupported. Unsupported runner execution fails closed, not the existing research app.
2. **Local/server hybrid:** one policy and authorization contract may have separately verified isolation profiles; no universal VM requirement excludes local devices and no server profile silently weakens enforcement.
3. **Admin × personal workspace:** shared roots/policy stay admin-controlled; personal material remains private by default. Any self-approval carve-out, publication or sharing behavior is still explicitly owner-decidable.
4–5. **In-scope autonomy; no unnecessary confirmation:** automatic receipt issuance within an existing pre-approved scope and no per-job human queue are recommended; exceptions remain human-gated. No recommendation turns a design into permission.
6. **ADR-0011/0012 intact:** zero-tool Plane-M, dual-plane separation, receipt/recheck, fail-closed, B6 and separate activation all remain binding.
7. **No rootless constraints:** recommendations distinguish grounded functional/safety requirements from ungrounded implementation layers and values; no numeric, platform, credential, retention or access expansion is invented. **No source recommendation conflicts with these priorities after the scope distinctions above.** Items with unresolved policy choices are labeled below rather than treated as adopted.

## True remaining owner-decision points

These are choices left genuinely open after merging recommendations, not implementation details or permission to execute. Queue status remains unchanged.

- **A — receipt:** Ratify the one-job receipt/envelope contract (DP-001/002), issuer/key arrangement (DP-004/007), policy and first-scope exceptions (DP-005), personal-workspace self-approval treatment (DP-006), online revocation vs any explicitly accepted staleness (DP-008/009), receipt TTL bounds and absolute/no-grace semantics (DP-010–012), delegation as an additional input only (DP-015), authority/approver role reuse (DP-016), queued-job revocation (DP-018), and the minimum error/audit/permission/metadata conventions where the owner wants to resolve them now (DP-019–021/023). DP-013 inherits the already-open production clock decision; DP-014 does not need a separate number under CP-authoritative online expiry. Receipt retention inherits the production retention decision (DP-022). The A recommendation does not alter ADR-0012’s mandatory receipt gates.
- **B — isolation/trust:** Set deployment-specific local/server threat profiles and tested platform matrix (DP-024–030), exact private topology/transfer boundaries if separately authorized (DP-031–033), provider-specific official-auth/terms feasibility (DP-034), per-installation trust/enrollment/rotation/recovery choices (DP-035–041), operational revocation/cancellation recovery (DP-042/043), and any remaining versioned receipt/result contract details not already settled by A (DP-044–050). Set measured admission/capacity and test/evidence thresholds only where needed (DP-051–053). All runtime activation remains a separate future explicit decision after proof/review; a document recommendation cannot activate it.
- **C — source ACL:** Confirm whether/when D5 includes connector-specific source ACL design (DP-054/055); specify source identity mapping, freshness, revocation, deletion and race behavior (DP-056–063) only in that later design; set metadata visibility/retention under the existing audit policy (DP-064); decide originals/backup under existing storage retention track (DP-060/069). DP-065’s independence invariant is already grounded and not an open permission to egress; only separate egress requests remain subject to their own gates. Production database, deployment/TLS/sessions, audit, provider/capacity and session lifecycle stay in existing deferred tracks (DP-066–070/072). DP-071 is limited to residual recipient/admin UI; PH2-A’s decision deferring organization-wide delegation is resolved and not reopened.
- **Not owner decisions:** adapter rewrites, inventing a second permission registry, choosing arbitrary protocol/TTL/retention/quotas without evidence, implementation schema details that meet a ratified contract, or revisiting PH2-A/AUD-1 resolved decisions. Existing mandatory safety semantics (B6, online rechecks where mandated, ACL filtering, denial on uncertainty, cancellation/hold, independent review and activation separation) are not optional alternatives.

## Consolidated per-item recommendations

Format is compact but retains each source’s seven fields in order: **1** grounding; **2** initial behavior; **3** current options; **4** recommendation; **5** autonomy/usability/safety effect; **6** resulting constraint; **7** true owner decision. Flags reproduce source classifications (a dash means source says none). Follow the source link for full wording and evidence.

### Group A — Job receipt / DP-001–023

Source: [full integrated Group A review](OWNER_REEVAL-A-RECEIPT.md).

#### DP-001 — Runner identity in receipt ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-010/012/013, ADR-0012 B5/§4.1, Step-2 §2.1/2.6. 2. Workspace binds one `(runner_instance_id, adapter_id)` pair; E2 checks exact instance. 3. Put instance ID in receipt or use envelope/binding. 4. Use binding; no duplicate field. 5. Avoid needless reapproval; identity/revocation safety unchanged. 6. One bound Runner/adapter pair per workspace. 7. Ratify binding sufficiency. **Flags:** 🚫—; ⚠ redundant instance requirement; 📈 duplicate state.

#### DP-002 — Receipt integrity, serialization, replay ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-013/010, ADR-0012 §4.1/B1/B4, Step-2 §2.6. 2. E1/E2 check same current receipt/envelope; replay rejected. 3. Signature/canonicalization/nonce are open. 4. Minimal: issuer-signed audit receipt; online E1/E2 authoritative verification; unique job ID + durable one-use state; versioned schema, no custom Runner signature canonicalization. 5. Fresh, independently fail-closed checks; less protocol machinery. 6. Issuer outage blocks execution; offline path is a new decision. 7. Ratify online verification/signature/replay contract. **Flags:** 🚫—; ⚠—; 📈 custom Runner signature/canonicalization.

#### DP-003 — Receipt persistence ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-012/013, IAM-015, PROD-005/DATA-013; ADR-0012 §4.1 and Step-2 §2.1. 2. Control-store, immutable rows/events. 3. Concrete storage open. 4. Reuse current control store/event convention; no new store. 5. One small authoritative surface. 6. Prototype availability follows control store; production DB deferred. 7. No new decision beyond existing production DB/retention. **Flags:** 🚫—; ⚠—; 📈 dedicated store.

#### DP-004 — Issuer architecture ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-013/010, ADR-0012 §4.1/B1. 2. CP-separated issuer alone writes, verifies approver. 3. Internal authority, per-job human, delegation input (mixed categories). 4. CP-internal issuer; approval policy and delegation are inputs. 5. Enables in-scope automation, authority remains. 6. CP availability/audit obligations. 7. Ratify placement; decide policy separately. **Flags:** 🚫—; ⚠ treating policy/input as rival architecture; 📈—.

#### DP-005 — Per-job vs policy approval ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-002/013/014, ADR-0012 §4.1 and Step-2 lifecycle. 2. Receipt is required; pre-approved scope need not mean human per job. 3. Human every job, policy issuance, first-scope exception. 4. Automate within current admin scope; human for first/above-scope or silent policy. 5. Autonomy/usability ↑; audit, scope and B6 unchanged. 6. Policy writes/versioning remain admin-controlled. 7. Ratify classes/always-human exceptions. **Flags:** 🚫—; ⚠ human approval for all jobs; 📈—.

#### DP-006 — Approver distinct from actor ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-013, PH2-A-03, PRODUCT_SPEC personal workspaces, hybrid 要件1. 2. Issuer verifies and records approver authority. 3. Require distinct principal or not. 4. Keep separation in delegated/admin scopes; decide sole workspace-owner self-approval separately. 5. Avoid blocking personal autonomy without eroding administered-scope checks. 6. Carve-out bounded by verified owner authority. 7. Decide personal-workspace case. **Flags:** 🚫—; ⚠ unconditional distinct approver for sole personal owner; 📈—.

#### DP-007 — Issuer trust/key custody ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-007/013/010, ADR-0012 B4/B5, Step-2 §2.6. 2. CP issuer key; Runner identity separate. 3. Internal/external authority and trust scheme. 4. One CP-internal protected key; E2 uses online authenticated check, no Runner receipt root. 5. One custody surface. 6. Rotation/compromise policy needed before activation; runner identity separate. 7. Ratify arrangement; B trust-root item remains. **Flags:** 🚫—; ⚠—; 📈 receipt-only PKI.

#### DP-008 — Live receipt revocation ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-013/011, ADR-0012 §4.1, Step-2 §2.6. 2. Revocation visible next enforcement point; unavailable authority rejects. 3. Online, signed list/short receipt, hybrid cache. 4. Online check at E1/E2; reject if unreachable. 5. Fresh and simplest; offline operation unavailable. 6. CP reachability at E2. 7. Select online, or explicitly accept bounded staleness; note F5. **Flags:** 🚫 signed-list option as worded conflicts with next-point visibility; ⚠—; 📈—.

#### DP-009 — Staleness/cache ([source](OWNER_REEVAL-A-RECEIPT.md))
1. Same HBR/ADR grounding as DP-008; PH2-A-12. 2. Live check at each authorization point. 3. Bound/cache open. 4. Zero staleness at enforcement; no default cache. 5. One lookup, stronger freshness. 6. E2 relies on issuer availability. 7. None unless later permitting a measured cache. **Flags:** 🚫—; ⚠ unsupported staleness tolerance; 📈 default negative cache.

#### DP-010 — Default receipt TTL ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-013/014, ADR-0013 §7; PH2-A-01 precedent. 2. One job, expiring receipt. 3. No value offered. 4. Recommend 24 hours, reusing but not inheriting grant TTL; auto-reissue in-scope jobs. 5. Bounds unused approval without routine stalls. 6. Longer tasks need explicit policy within max. 7. Owner ratifies value. **Flags:** 🚫—; ⚠ unanchored value; 📈—.

#### DP-011 — Maximum receipt TTL ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-013/014, ADR-0013 §7; PH2-A-01 precedent. 2. One-job receipt expires. 3. No value offered. 4. Recommend 7 days; no permanent preapproval. 5. Bounds unused authorization; one-job scope limits exposure. 6. Issuance rejects above max. 7. Owner ratifies maximum. **Flags:** 🚫—; ⚠ unanchored value; 📈—.

#### DP-012 — Expiry model/grace ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-013/014, ADR-0013 §§5/7, Step-2 §2.1; PH2-A-01. 2. Wall clock precedent; no deadline substrate. 3. Absolute/deadline anchored; grace open. 4. Absolute epoch-seconds expiry; no grace. 5. Fail-closed; automatic reissue prevents routine stall. 6. Revisit anchoring only if deadlines enabled. 7. Ratify absolute/no grace. **Flags:** 🚫—; ⚠ deadline anchoring before substrate; 📈 anchoring now/grace.

#### DP-013 — Receipt time authority ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-013; PH2-A-08 resolved prototype time. 2. One CP epoch-seconds convention. 3. Authority open. 4. Reuse delegation CP clock; production clock remains separate open decision. 5. Avoid second clock/skew source. 6. Both inherit prototype limitation until production choice. 7. No new decision. **Flags:** 🚫—; ⚠—; 📈 receipt-specific clock.

#### DP-014 — Receipt clock skew ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-013/011; ADR-0013 §7. 2. Online authority computes expiry; transport skew separate. 3. Tolerance open. 4. A recommends fail-closed zero tolerance; coherence with B DP-046 means no separate Runner/CP skew rule if only CP time determines online expiry; measure any needed transport comparison. 5. No autonomy cost with CP time; fail-closed. 6. Online CP dependency. 7. Decide only if a separate cross-plane clock comparison is necessary. **Flags:** 🚫—; ⚠ nonzero tolerance without evidence; 📈—.

#### DP-015 — Delegation vs actor authorization ([source](OWNER_REEVAL-A-RECEIPT.md))
1. IAM-011/013, PH2-A-10, ADR-0013 §6. 2. Live membership plus role and optional grant; grant never replaces membership. 3. Grant prerequisite or extra input. 4. Additional input only. 5. Keeps ordinary member autonomy and live revocation. 6. Shared actor-authorization function. 7. Ratify. **Flags:** 🚫 prerequisite contradicts resolved invariant; ⚠—; 📈—.

#### DP-016 — Approver authority ([source](OWNER_REEVAL-A-RECEIPT.md))
1. IAM-010/011, PH2-A-03/09, ADR-0013 §6. 2. Existing target project grantor roles verify authority. 3. Role model, dedicated registry, both. 4. Reuse grantor role model; optional future narrowing allowlist only. 5. One authority source; personal/admin scopes preserved. 6. Role changes handled by invalidation. 7. Ratify reuse; allowlist not needed now. **Flags:** 🚫—; ⚠ separate registry as requirement; 📈 dual registry.

#### DP-017 — Approver loses authority before enqueue ([source](OWNER_REEVAL-A-RECEIPT.md))
1. PH2-A-05, DATA-005; ADR-0013 §6. 2. Immutable invalidation; next check fails closed. 3. Exact handling open. 4. Mirror grant invalidation; E1 rejects. 5. Safety preserved, in-scope reissue possible. 6. Share authority-loss event source. 7. No new policy decision. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-018 — Authority loss after enqueue ([source](OWNER_REEVAL-A-RECEIPT.md))
1. PH2-A-05/12; ADR-0012 §4.1, Step-2 §2.6. 2. E2 sees current revocation. 3. Revoke queued job or only bar new issue. 4. Revoke at E2. 5. Uniform semantics; reissue under surviving authority. 6. Queued work may cancel; capacity follows HBR-014. 7. Ratify E2 outcome. **Flags:** 🚫—; ⚠ bar-new-issuance-only weakens live precedent; 📈—.

#### DP-019 — Rejection errors ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-011/013; Step-2 §6.11. 2. Existing 409 dispatch rejection and audit pattern. 3. Taxonomy/codes open. 4. Small closed versioned reason enum mapped to current API; audit all. 5. Supports autonomous retry decisions; no new semantics. 6. Enum is versioned contract. 7. Ratify shape; exact codes are design. **Flags:** 🚫—; ⚠—; 📈 elaborate taxonomy.

#### DP-020 — Receipt audit events ([source](OWNER_REEVAL-A-RECEIPT.md))
1. HBR-006, IAM-015, ADR-0012 B7/ADR-0013 §8. 2. Attributed metadata via `agent.*`. 3. Names open; proposed `agent.receipt.*`. 4. Use issue/deny/recheck/revoke/expiry subevents. 5. Accountable without user friction. 6. Audit names become contract. 7. Ratify naming. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-021 — New approval permission ([source](OWNER_REEVAL-A-RECEIPT.md))
1. IAM-010/011, PH2-A-03/09, ADR-0012 E7. 2. Authority derives from target grantor role; no invented backend privilege. 3. New permission or not/ceiling. 4. No `approve_jobs`; reuse nondelegable grantor authority. 5. Avoid privilege sprawl; role model covers admin and owner. 6. Fine-grained control later needs explicit new decision. 7. Ratify no new permission. **Flags:** 🚫—; ⚠ new permission as requirement; 📈 permission lifecycle for same capability.

#### DP-022 — Receipt/audit retention ([source](OWNER_REEVAL-A-RECEIPT.md))
1. IAM-016, DATA-015; PH2-A-11 resolved, ADR-0013 §8. 2. Immutable records follow delegation. 3. Period open. 4. Retain until existing production retention decision; no separate period. 5. One coherent decision. 6. Records remain meanwhile; no production assumption. 7. No new decision; existing production decision governs. **Flags:** 🚫—; ⚠ invented receipt-specific period; 📈—.

#### DP-023 — Receipt redaction/content ([source](OWNER_REEVAL-A-RECEIPT.md))
1. IAM-015, HBR-005, ADR-0012 B2/§8. 2. Metadata only; no credential bytes. 3. Redaction open; secrets excluded. 4. IDs/references/policy metadata only; schema test. 5. Maintains small, privacy-safe audit surface. 6. Future content fields need explicit decision. 7. Ratify metadata-only. **Flags:** 🚫—; ⚠—; 📈 content-bearing receipt plus redaction pipeline.

### Group B — Isolation and Runner trust / DP-024–053

Source: [full integrated Group B review](OWNER_REEVAL-B-ISOLATION.md).

#### DP-024 — Windows support matrix ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-001/004; Product Spec selects no OS. 2. Local/server use, no universal Windows promise. 3. Editions/features open; VM-first candidate. 4. Support only tested profiles enforcing boundary. 5. Practical hybrid; unsupported target unavailable. 6. Requires supported build; conformance extends later. 7. Choose initial target/risk matrix. **Flags:** 🚫—; ⚠—; 📈 Hyper-V on every desktop edition.

#### DP-025 — Windows isolation ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-004; initial design selects no sandbox technology. 2. Usable authorized local/server work; no VM-per-job requirement. 3. Job Objects, AppContainer, VM/Sandbox, containers. 4. Phased capability-tested native boundary locally; VM when threat/capacity warrants; Job Objects alone insufficient. 5. Usability with proved isolation; no proof, no run. 6. Per-profile proof/scope labels. 7. Choose threat profiles/mechanisms, not activation. **Flags:** 🚫—; ⚠—; 📈 universal VM-per-job.

#### DP-026 — Windows image/transfer/no-VM ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-004/007, Product upload/ACL requirements; no guest-image design. 2. Scoped authorized research inputs. 3. Integrity/transfer/cleanup/broker; no silent downgrade. 4. Narrow bounded job-workspace transfer; reject if no verified boundary. 5. Useful bounded transfer, fail closed. 6. No profiles/unrestricted host mount; output ACL recheck. 7. Choose transfer profile and existing size bounds. **Flags:** 🚫—; ⚠ mandatory bespoke broker/image supply chain; 📈 universal broker.

#### DP-027 — Linux support matrix ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-001/004; Product/Architecture select no distro. 2. Local/on-prem without every-kernel promise. 3. Matrix open; VM-first proposal. 4. Start with hosts passing process/filesystem/network/cleanup tests. 5. Practical/extensible; unverified host unavailable. 6. Unsupported kernel cannot run. 7. Select tested initial targets. **Flags:** 🚫—; ⚠—; 📈 exhaustive distro matrix.

#### DP-028 — Linux VM/microVM ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-004; no separate guest kernel required by initial sources. 2. Isolated local/server work; replaceable mechanism. 3. Hardware VM/microVM options. 4. Stronger server profile where justified; non-VM only if independently proven. 5. Supports common local hardware safely. 6. Adapters cannot assume VM-only capabilities. 7. Decide higher-risk server requirements/platforms. **Flags:** 🚫—; ⚠—; 📈 universal VM/microVM.

#### DP-029 — Linux runtime/rootless OCI ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-004; no rootless/namespaces/seccomp/LSM mandate initially. 2. Enforce workspace/process/network boundary. 3. Namespaces/cgroups, rootless OCI, VM layers. 4. Minimum verified host controls; ban privileged mode, broad mounts/control sockets. 5. Proven least privilege; no assumed container equivalence. 6. Retest relevant kernel/runtime updates. 7. Choose minimum evidence-backed platform profile. **Flags:** 🚫—; ⚠ universal rootless OCI; 📈 unconditional VM+rootless+all layers.

#### DP-030 — Linux virtualization fallback ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-004; ADR-0012 B6. 2. Only verified OS boundary; never host fallback. 3. Unavailable or explicitly approved tested non-VM profile. 4. No host execution; no profile, unavailable. 5. Viable local profiles without silent downgrade. 6. Unsupported local hosts cannot execute. 7. Decide which proven non-VM profiles meet risk bar. **Flags:** 🚫—; ⚠ VM-only and unproven fallback constraints; 📈—.

#### DP-031 — Runner topology/reachability ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-001/007; Product Spec permits private LAN but no Runner topology. 2. Authorized local/on-prem, not public Runner. 3. Desktop/server ownership and endpoint open. 4. Private, narrow authenticated CP channel; no LAN-external reachability. 5. Preserves hybrid and scope. 6. Exact private firewall path required. 7. Choose topology/endpoint binding. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-032 — Cross-boundary endpoint/egress ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-002/007; Product local-only no-egress. 2. Private local-first; no unapproved external send. 3. Exact CP endpoint/protocol open. 4. Default deny; only exact separately authorized private CP endpoint; provider egress stays denied. 5. Hybrid control without cloud permission. 6. No wildcard/private-subnet rule. 7. Choose endpoint only if separately authorized. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-033 — Broker/mount/transfer ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-004/007/013 and Product upload/ACL; no broker specified. 2. Authorized bounded input/output. 3. Narrow broker/bundle or unavailable. 4. Expose only authorized files/results; simplest proven transfer. 5. Research utility without general host access. 6. No arbitrary paths/profiles/sockets; live output rechecks. 7. Select transfer mechanism/scope. **Flags:** 🚫—; ⚠ bespoke broker mandatory; 📈 broker/guest design when simpler proof suffices.

#### DP-034 — Provider credentials/consent ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-005 (owner-added); Product Spec has no Runner credential scheme. 2. Official supported auth; no Locus reuse/implicit send. 3. Broker only after proof/approval, else unavailable. 4. No job credentials by default; assess official CLI user-device auth per adapter; unavailable absent proof. 5. Some adapters unavailable; safe local path remains. 6. Presence flag is not credential authorization. 7. Provider terms/auth and any broker/consent decision. **Flags:** 🚫—; ⚠ mandatory non-exportable broker baseline; 📈—.

#### DP-035 — Trust anchor/key layout ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-007; no initial PKI/MAC layout. 2. Authenticated private services; instance trust is added hybrid requirement. 3. Shared secret, TOFU, per-instance asymmetric, enterprise PKI. 4. Minimal standard per-instance identity, OS-protected; reuse existing PKI optionally; no universal CA hierarchy. 5. Revocable instances for desktop/server. 6. Enroll/revoke separately; not job approval. 7. Choose deployment trust/custody; no provisioning authorized. **Flags:** 🚫—; ⚠ dedicated CA; 📈 offline-root/subordinate hierarchy universally.

#### DP-036 — Crypto/hardware/quorum ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-007; no algorithm/key length/HSM/quorum mandated. 2. Authenticated revocable transport. 3. Details open. 4. Vetted platform TLS/crypto; no custom crypto/hardware/quorum without threat evidence. 5. Standard interoperable profile. 6. Select and review before any implementation/activation. 7. Choose justified crypto profile. **Flags:** 🚫—; ⚠ mandatory hardware/quorum; 📈 imposing universally.

#### DP-037 — Enterprise PKI ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-007; no enterprise PKI assumption. 2. Private operation without hidden dependency. 3. Local installation trust or enterprise PKI. 4. Optional integration; standalone enrollment when absent. 5. Supports individuals and managed orgs. 6. Local trust lifecycle needed where no PKI. 7. Confirm deployment PKI/integration scope. **Flags:** 🚫—; ⚠ enterprise PKI as mandatory; 📈—.

#### DP-038 — Keystore/attestation ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-007/005; no TPM/attestation mandate. 2. Local/server use with separate identity/credentials. 3. OS/hardware store, attestation or unavailable. 4. Protected OS keystore; require hardware evidence only if threat profile needs it. 5. Common devices viable; truthful assurance. 6. Profile unavailable if protection insufficient. 7. Choose minimum keystore and high-assurance class. **Flags:** 🚫—; ⚠ universal TPM/attestation; 📈 universal hardware gate.

#### DP-039 — Enrollment authority/local confirmation ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-007; Product roles, no enrollment ceremony. 2. Admin controls policy, users select allowed workspace. 3. Admin plus second local channel proposed. 4. Authenticated authorized admin approves one-use challenge bound to key; no second channel unless necessary. 5. No repeated owner confirmation; no self-asserted identity. 6. Initial enrollment remains admin action. 7. Choose existing admin role and need for Desktop second check. **Flags:** 🚫—; ⚠ mandatory second channel; 📈—.

#### DP-040 — Key lifetime/rotation ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-007; no initial intervals. 2. Runner disable/revoke; cadence open. 3. Bounded overlap, proof of new-key possession; values open. 4. Per-instance renewal, immediate compromise revocation, minimum measured overlap. 5. Routine renewals need not halt all instances. 6. Audited renewal/recovery. 7. Set deployment cadence/overlap on evidence. **Flags:** 🚫—; ⚠ fixed intervals; 📈—.

#### DP-041 — Re-enrollment/recovery ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-007/006; no initial reinstall rules. 2. Distinct auditable identity. 3. New instance; recovery authority open. 4. Revoke lost/compromised identity; enroll new auditable instance. 5. Admin recovery step prevents impersonation. 6. Reinstall does not revive identity. 7. Select existing admin for exceptional recovery/retention. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-042 — Certificate/revocation status ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-007, ADR-0012 §4.1; no SLA/cache value. 2. No revoked/unauthorized execution. 3. Online state, cache/SLA open. 4. Reuse same authority; live check at admission and execution; reject on uncertainty. 5. Outage blocks but stale auth does not run. 6. No offline grace/cache default. 7. Set operational latency/availability or evidence-based cache bound. **Flags:** 🚫—; ⚠ separate status service/numeric SLA; 📈—.

#### DP-043 — Queued/active work on revocation ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-014 and ADR-0012 mandatory cancellation semantics. 2. Only currently authorized outputs released. 3. Cancel queued; hold/terminate uncertain active work. 4. Apply ADR semantics; uncertain result stays held. 5. May lose results; avoids stale release. 6. Capacity held until termination confirmation. 7. Resolve root-compromise recovery/mechanism, not mandatory semantics. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-044 — Envelope encoding/version ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-007/013, ADR-0012 §§3–4. 2. Current authority authorizes exact operation. 3. CP signature, online opaque ID, or both. 4. Opaque one-use reference over authenticated transport to closed versioned current contract; no job signature by default. 5. One authority, fresh bindings. 6. CP required; no offline path. 7. Decide schema/API detail, not mandatory checks. **Flags:** 🚫—; ⚠ separate signing infrastructure; 📈 signature plus online checks without need.

#### DP-045 — Envelope algorithms/key IDs ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-007/013; no algorithms selected initially. 2. Authenticated current policy and integrity. 3. Signature/digest/key/encoding open. 4. No second signature family by default; vetted TLS + closed schema; if later justified, standard reviewed profile. 5. Fewer keys without weakening checks. 6. Online-only; future signature needs migration. 7. No algorithm choice now; later decision only if needed. **Flags:** 🚫—; ⚠ fixed crypto requirements; 📈 separate signing while online authority suffices.

#### DP-046 — Freshness/time/skew ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-013/014, ADR-0012 §4; no numeric skew. 2. Stale/unauthorized work rejected. 3. Window/authority/skew open. 4. Use CP time/state online; receipt TTL is A DP-010/011; no second TTL/offline grace. 5. Freshness without assumed local clock. 6. Uncertain authority rejects; values apply only per ratified receipt expiry. 7. Ratify receipt expiry; add tolerance only from measurement. **Flags:** 🚫—; ⚠ guessed zero-skew/fixed validity; 📈—.

#### DP-047 — Replay persistence ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-013, ADR-0012 §4.1. 2. Job cannot run twice/on another Runner. 3. Nonce/sequence/retention open. 4. Durable CP job ID as one-use key, atomically consumed online. 5. Safe retries without duplicate service. 6. CP state persists consumption. 7. Minimal lifecycle retention. **Flags:** 🚫—; ⚠—; 📈 separate sequence/nonce ledger.

#### DP-048 — Receipt API/bindings ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-013, ADR-0012 §4.1. 2. Current job authorization checked at enqueue and execution. 3. API/claims open; bindings listed. 4. Single CP authority checks all required bindings and exact enrolled Runner; no second issuer. 5. Outage fails closed; Plane-M unchanged. 6. No execution without exact match/current authority. 7. Decide endpoint/schema only; mandatory bindings not reopened. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-049 — Results/artifact signing ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-013, ADR-0012 §4.4; product needs provenance, not Runner signing key. 2. Integrity/ACL/classification and advisory outputs. 3. Signed manifest proposed. 4. Bind bounded result digest to job/instance; live revalidate; add signature only if leaving authenticated channel. 5. Integrity without treating signature as permission. 6. Digest is not safety/content approval. 7. Decide persistence/channel and whether signature needed. **Flags:** 🚫—; ⚠ separate signing key/ceremony; 📈 while transport binding suffices.

#### DP-050 — Artifact/audit retention ([source](OWNER_REEVAL-B-ISOLATION.md))
1. DATA-005/015, IAM-015/016, ADR-0012 §4.4. 2. Revoked sources/derivatives inaccessible; periods open. 3. Follow Step-2; revalidate before release. 4. Inherit source ACL/deletion/retention; minimum metadata; no invented period. 5. Stale derivative hidden. 6. Results may become inaccessible; no unverified erasure claim. 7. Use existing retention/backup/deletion decisions. **Flags:** 🚫—; ⚠ new fixed periods; 📈—.

#### DP-051 — Admission/deadlines/cancellation ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-014 and ADR-0012 cancellation; UI-006; no Runner quotas. 2. Bounded useful work, confirmed termination. 3. Bounds/guarantees open. 4. Reuse concepts, measure local/server, preserve cancellation semantics. 5. Avoid arbitrary quotas; truthful status. 6. Hold uncertain capacity. 7. Decide measured bounds/mechanism, not mandatory semantics. **Flags:** 🚫—; ⚠ arbitrary limits/second scheduler; 📈—.

#### DP-052 — Tests/thresholds ([source](OWNER_REEVAL-B-ISOLATION.md))
1. HBR-004/007/014, GOV-004, ADR-0012. 2. Evidence before claims, not runtime permission. 3. Matrix/threshold open. 4. Test real boundary, identity, cancellation, failure and positive controls for each claimed host/build using synthetic data; independent review. 5. Credible profiles; tests do not activate. 6. Evidence bound to exact config. 7. Choose targets/pass thresholds; unavailable checks blocked. **Flags:** 🚫—; ⚠ fixed evidence expiry; 📈 exhaustive matrix/arbitrary numeric thresholds.

#### DP-053 — Evidence/independent review/activation ([source](OWNER_REEVAL-B-ISOLATION.md))
1. GOV-004/005, DEVELOPMENT_POLICY, ADR-0012. 2. Evidence, review, activation distinct. 3. Binding/window/verifier/activation authority open. 4. Bind proof to exact build/platform/config/tests; refresh after material change; independent review then separate explicit owner activation. 5. Reuse only unchanged evidence; no automatic activation. 6. Changes invalidate relevant proof. 7. Set numeric window/named approver; do not reopen separation. **Flags:** 🚫—; ⚠ unspecified verifier scheme/expiry; 📈—.

### Group C — Storage ACL / DP-054–065; housekeeping / DP-066–072

Source: [full integrated Group C review](OWNER_REEVAL-C-STORAGE-MISC.md).

#### DP-054 — D5 scope ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-008; research concept §8 and phase reconciliation. 2. Design source-permission mapping after connector choice. 3. A/A2 propagation, B connector, C/D local storage/retention or combination. 4. A/A2 core; C/D retention input; defer B to connector design. 5. Preserve unconnected research flow and personal/admin split. 6. Source ACL mapping remains open. 7. Confirm D5 scope. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-055 — Source modes/connectors ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-008; product refinement; local/NAS early candidates, online drive later. 2. Admin configures shared roots; personal uploads private by default. 3. Manual upload, local folder, NAS, online connector or none. 4. None now; manual upload is current source; local/NAS only future candidates after design approval. 5. Keeps research flow and privacy; no connector/egress. 6. Online personal drive deferred. 7. Confirm no connector for this phase and later source types. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-056 — Live source permissions/identity/freshness ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-004/005, Architecture shared enforcement, UI design. 2. Check permissions at conversation time; exact mapping/freshness open. 3. Live, bounded snapshot, Locus mapping or separate grant. 4. Recommend live source check; no numeric SLA. 5. Protects connected-material use; unconnected docs unchanged. 6. Exact identity mapping/freshness remains open. 7. Choose trust source and measured delay. **Flags:** 🚫—; ⚠—; 📈— (source separately notes that a numeric freshness SLA is ungrounded).

#### DP-057 — ACL combination ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-005, research concept §8, Product document ACL. 2. Source ACL never replaces Locus publication/roles. 3. Combination open; intersection proposed. 4. Additive intersection gate; explicit deny still wins. 5. Unconnected docs unchanged; personal privacy/fail-closed maintained. 6. Both gates apply on all connected paths. 7. Confirm intersection. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-058 — Source revoke/unavailable/move/missed sync ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-005; UI reopening behavior explicitly open. 2. Apply permission at conversation; exact revocation behavior open. 3. Hide/quarantine/delete/retain unavailable. 4. Hide/fail closed on stale or unverifiable state; deletion/retention remains separate. 5. Manual upload unaffected; avoids stale exposure. 6. Reopened conversation behavior remains open. 7. Decide exact source lifecycle behavior. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-059 — Source deletion ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-005, Architecture deletion propagation, concept §8; no upstream write privilege. 2. Read-only ingestion; invalidate Locus binding/derivatives. 3. Binding, Locus copies, upstream request or combination. 4. Remove binding and clean up Locus derivatives; no upstream deletion request by default. 5. Manual upload unaffected; fail closed. 6. Upstream write outside initial scope. 7. Decide only if source-write authority is later sought. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-060 — Original bytes/copy/cache/retention ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-008; concept §8 says copy/cache and period undecided. 2. Preserve originals at source; manage extraction/index/provenance; copy policy open. 3. Copy/cache/link/fetch-on-demand; backup/retention. 4. Defer source storage/retention choice; no service/period inferred. 5. Manual upload unchanged; no egress/credential/connector. 6. Remains owner open point. 7. Decide storage/retention later. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-061 — Multi-source/cardinality ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-008/005; initial design has no multi-source document model. 2. Design connectors later; one-source assumption. 3. Explicit cardinality vs 1:1; revocation/duplicates/moves open. 4. 1:1 default with extensible schema; fail closed on source revoke. 5. Existing manual research unaffected. 6. Multi-source feature not in initial design. 7. Decide if feature is needed. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-062 — Source configuration/authority/credentials ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-008; admin configures shared roots; personal material private; source credentials do not determine publication. 2. Separate admin shared setup and personal ownership. 3. Config/view, credentials, egress open. 4. Admin configures shared scope; keep personal scope private; no credential/egress scheme. 5. Admin/personal distinction preserved; no connectors enabled. 6. Personal online drive/share transfer deferred. 7. Decide these only in future connector design. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-063 — Sync races/linearization ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-005; UI source mapping/reopen behavior open. 2. Apply current permission at conversation; exact race semantics open. 3. Retry/concurrency/linearization open. 4. Extend live checks at read boundaries and existing ingest checks; define races in connector design. 5. Unconnected docs unchanged; fail closed. 6. Exact linearization remains open. 7. Decide detail with source connector. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-064 — Source metadata audit/privacy ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-008/015; metadata-only audit excludes content, creds, sensitive paths/ACL payloads. 2. Audit source events; retention open. 3. Source identity sensitivity/access/retention open. 4. Metadata-only; existing audit retention decision. 5. No content leakage; admin scope preserved. 6. Retention not selected. 7. Decide source metadata retention/access later. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-065 — Source read vs external AI ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-012 and Product cloud/egress rule. 2. Source-read privilege does not authorize external AI. 3. Source states independence but item remains queued. 4. Preserve independence; external egress needs separate authorization. 5. No change to research flow; no egress implied. 6. No source permission can widen destination policy. 7. No decision on this invariant; only a future separate egress proposal is open. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-066 — Production database/vector/graph ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. PROD-005; Architecture initial stack is provisional. 2. Keep stack replaceable pending comparison. 3. Evidence-backed options/verification. 4. Defer selection until evidence-backed production proposal. 5. Research support/local-server unaffected. 6. No production DB selected. 7. Owner selects after evidence. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-067 — Production deployment/TLS/session/LAN ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. PROD-002/003, IAM-017. 2. Production security decisions after prototype. 3. Loopback prototype vs private network; exact validation open. 4. Defer production exposure; preserve authenticated/private deployment requirements. 5. Product functionality unaffected; no exposure. 6. No LAN/TLS/session production approval. 7. Decide deployment and verification in production phase. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-068 — Production audit protection/retention ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-015, IAM-016. 2. Metadata-only; production protection/period open. 3. Confidentiality/access/tamper/retention/erasure. 4. Defer evidence-backed production decision. 5. Keeps audit boundary, no new retention period. 6. Audit activation gate remains. 7. Decide safeguards before production/runtime activation. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-069 — Production data retention/backup/deletion ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. DATA-008/015; copy/retention and production operations open. 2. No production period selected. 3. Retention, backup/restore, secure deletion. 4. Defer pending production design/evidence. 5. Research support preserved; no period invented. 6. Existing storage and audit tracks remain open. 7. Set production policy/periods. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-070 — Production providers/capacity ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. PROD-005/DATA-015; LLM destination open; capacity claims measured. 2. No production model/provider chosen. 3. Provider/model scope and measured capacity. 4. Defer to evidence/terms review. 5. Local-first support unchanged; no egress. 6. No provider/capacity approval implied. 7. Decide after evidence and terms. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-071 — Org model/delegation UI ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. Product role templates; phase reconciliation; PH2-A resolved org-wide delegation deferred. 2. Org-wide grants remain deferred; residual UI may follow org model. 3. Recipient UI and org management surface open. 4. Defer surface decision; preserve project-scoped delegation decision. 5. No research restriction; no scope expansion. 6. Org-wide delegation not reopened. 7. Decide only remaining management/UI scope. **Flags:** 🚫—; ⚠—; 📈—.

#### DP-072 — Production sessions across restart ([source](OWNER_REEVAL-C-STORAGE-MISC.md))
1. IAM-017/PROD-003; production deployment deferred. 2. Prototype completion does not select production session behavior. 3. Persist across restart or other lifecycle. 4. Defer to production session design. 5. No prototype restriction or security weakening. 6. No persistence duration/mechanism inferred. 7. Decide lifecycle/persistence in production phase. **Flags:** 🚫—; ⚠—; 📈—.

## Adversarial self-review

- All 72 IDs appear exactly once, grouped 23/30/19, with fields 1–7 and three flag categories retained and linked to full source reviews. Item-level claims and options are summaries, not fresh technical evaluations.
- Cross-group tensions are explicitly reconciled; signing vs online checking, TTL vs envelope freshness, and prototype vs production storage are not treated as interchangeable mechanisms. Owner-decidable values remain clearly separate from approved precedents.
- Group C’s non-flagged caveats are labeled as such rather than inflated into source flags. DP-065’s mandatory independent egress rule and DP-071’s resolved delegation deferral are not re-opened.
- No recommendation grants authority, changes a queue status, creates a new permission, or authorizes dispatch, isolation, Runner, credentials, connectors, external egress, real-data use or production deployment. ADR-0011/0012 and all named owner priorities remain intact; the over-engineered layers are dropped or conditional on proof/threat need.
- Source of truth for full seven-field rationale remains [A](OWNER_REEVAL-A-RECEIPT.md), [B](OWNER_REEVAL-B-ISOLATION.md), and [C](OWNER_REEVAL-C-STORAGE-MISC.md); this compact synthesis is not a substitute for those evaluations.
