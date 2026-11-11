# Owner queue classification — DP-001…072 against the owner's formal decisions (2026-11-09)

**Status:** reclassification of every row of the [owner decision queue](OWNER_DECISION_QUEUE_2026-11-09.md) after the owner's formal decisions recorded in [OWNER_DECISIONS_2026-11-09-EVENING.md](OWNER_DECISIONS_2026-11-09-EVENING.md). This file classifies and structures the remaining decision requests; it approves no implementation, activation, credential use, egress, real-data use or production exposure. The recommendation layer remains [OWNER_DECISION_PROPOSAL_2026-11-09.md](OWNER_DECISION_PROPOSAL_2026-11-09.md) with full source reviews [A](OWNER_REEVAL-A-RECEIPT.md) / [B](OWNER_REEVAL-B-ISOLATION.md) / [C](OWNER_REEVAL-C-STORAGE-MISC.md).

**Update 2026-11-11 — Entry 1–6 recorded (2026-11-10):** the owner's formal decisions in [OWNER_DECISIONS_2026-11-10-ENTRIES.md](OWNER_DECISIONS_2026-11-10-ENTRIES.md) resolve the affected `OWNER_DECISION_REQUIRED` rows (DP-010/011, DP-021, DP-031/032, DP-034b, DP-035–041, DP-043b, DP-071) to `OWNER_POLICY_RESOLVED` below. Unrelated rows are unchanged. §"Entry 1–6 resolution" near the end of this file records the mapping; the six decision-request blocks in §OWNER_DECISION_REQUIRED are retained as historical proposals and are no longer open. Cross-references elsewhere in this file (e.g., DP-046) that cite those rows as "still 【要決定】" are superseded accordingly. Residual owner §4 items that no Entry decided (unverified isolation profiles, unapproved external communication/egress beyond the Entry 3 *design* approval, real-data use, production release, actual credential supply/activation beyond the Entry 4 *design/verification* approval, dispatch/Runner activation) remain 【要決定】／別途承認.

**Standing rules carried forward from the owner's message:**

- Approved-scope work never stops because another item is still pending.
- Items containing multiple unresolved parts are **split** (a/b suffixes) while preserving the original DP numbering.
- The owner's §4 unresolved list stays **【要決定】**: Receipt TTL numbers, new permissions/approval exceptions, Runner trust/enrollment/key management, unverified isolation profiles, provider credential supply, unapproved external communication, real-data use, production release, other safety-boundary changes. Nothing here treats them as approved. *(Update 2026-11-11: Entries 1–6 of [OWNER_DECISIONS_2026-11-10-ENTRIES.md](OWNER_DECISIONS_2026-11-10-ENTRIES.md) resolved the rows they directly decide — see §"Entry 1–6 resolution"; the remaining §4 items above stay 【要決定】.)*
- Existing mandatory semantics (B6 dispatch-rejection gate, ADR-0011 zero-tool boundary, ADR-0012 dual-plane separation, live rechecks, fail-closed, no-egress, separation of approval from activation) are not weakened and are not reopened.
- Technical implementation details within the initial design, existing ADRs and safety requirements are proposed, compared and verified by the orchestrator with the required independent review — they are not owner decisions. Owner decisions are not fragmented more than necessary, so closely related open items are grouped into one decision request.

## Categories

| Category | Meaning |
|---|---|
| **OWNER_POLICY_RESOLVED** | Resolved by the owner's Q1–Q7 decisions in [OWNER_DECISIONS_2026-11-09-EVENING.md](OWNER_DECISIONS_2026-11-09-EVENING.md). Treated as binding design constraints. |
| **EXISTING_DECISION** | Already resolved by existing ADRs, owner decisions or mandatory source requirements. Not reopened. |
| **ENGINEERING_DETAIL** | Decidable within the approved scope by the orchestrator (proposal + comparison + verification + independent review). Not an owner decision. |
| **OWNER_DECISION_REQUIRED** | A genuinely new permission / safety-boundary / operating-policy decision still needed; presented below in the owner-directed 8-field format. Never re-asks approved items. |
| **DEFERRED_WITH_GATE** | Deferred to a later phase with an explicit start condition and acceptance gate. |

## Summary

| Category | Rows |
|---|---:|
| OWNER_POLICY_RESOLVED | 37 |
| EXISTING_DECISION | 8 |
| ENGINEERING_DETAIL | 25 |
| OWNER_DECISION_REQUIRED | 0 |
| DEFERRED_WITH_GATE | 11 |
| **Total rows (72 original + 9 splits)** | **81** |

## Classification table

"Primary" = the row carrying the original DP number; splits are labelled a/b with a pointer back to the original item.

| ID | Split of | Category | Basis / decision reference |
|---|---|---|---|
| DP-001 | — | ENGINEERING_DETAIL | Receipt schema detail under the Q1 automatic-issuance contract; ADR-0012 exact-instance E2 check stays mandatory. |
| DP-002 | — | ENGINEERING_DETAIL | Signature/serialization/replay mechanics inside the ADR-0013-mandated contract; online authoritative verification (ADR-0012); no custom Runner signature protocol. |
| DP-003 | — | ENGINEERING_DETAIL | Reuse existing control store + immutable-event convention; production DB stays in the Q7 track (DP-066). |
| DP-004 | — | OWNER_POLICY_RESOLVED | **Q1**: policy-driven automatic issuance within the admin-approved scope via a Control-Plane-internal issuer; out-of-scope operations are never auto-approved. |
| DP-005 | — | OWNER_POLICY_RESOLVED | **Q1**: automatic issuance within the pre-approved scope; no per-job human approval in scope; auditability of approval history/actor/workspace/adapter/operation. |
| DP-006 | — | OWNER_POLICY_RESOLVED | **Q1+Q2**: in-scope jobs issued without a human approver (Q1); personal-workspace owner self-approval within permitted bounds (Q2); administered/exception approvals keep approver≠actor under the upper policy Q2 preserves. |
| DP-007 | — | ENGINEERING_DETAIL | CP-internal protected issuer key; no receipt-only PKI; Runner verification stays online/authenticated. |
| DP-008 | — | ENGINEERING_DETAIL | Online live revocation check at E1/E2 with fail-closed on unavailability, within ADR-0013 §3's mandatory live-recheck property. |
| DP-009 | — | ENGINEERING_DETAIL | Zero staleness at enforcement; no default negative cache; any later measured cache is a separate reviewed decision. |
| DP-010 | — | OWNER_POLICY_RESOLVED | **Entry 1** ([OWNER_DECISIONS_2026-11-10-ENTRIES.md](OWNER_DECISIONS_2026-11-10-ENTRIES.md)): default TTL **24 h**, maximum TTL **7 days**; Control-Plane-authoritative absolute epoch-seconds expiry; **no grace period**; reuse of expired receipts prohibited; automatic reissue for in-scope jobs only as a NEW authorization decision after current permission/policy re-verification (never an extension), prohibited on permission loss/policy change/out-of-scope operation; receipt TTL managed separately from delegation TTL. Formerly OWNER_DECISION_REQUIRED (Entry 1, grouped with DP-011). |
| DP-011 | — | OWNER_POLICY_RESOLVED | **Entry 1** (same values as DP-010): default 24 h / maximum 7 days, absolute epoch-seconds, no grace, no expired-receipt reuse, in-scope auto-reissue as a new authorization decision. Formerly OWNER_DECISION_REQUIRED (Entry 1, grouped with DP-010). |
| DP-012 | — | ENGINEERING_DETAIL | Absolute expiry / no grace as the fail-closed default within ADR-0013 §7. |
| DP-013 | — | ENGINEERING_DETAIL | Reuse the delegation CP clock for the prototype; production time source follows Q7 (DP-066). |
| DP-014 | — | ENGINEERING_DETAIL | CP-authoritative online expiry; no invented skew tolerance; any tolerance measured first. |
| DP-015a | DP-015 | EXISTING_DECISION | PH2-A-10 invariant: live membership/role authorization first; a delegation grant is an additional input only, never a prerequisite. |
| DP-015b | DP-015 | OWNER_POLICY_RESOLVED | **Q2**: a personal workspace's legitimate owner approves own executions without a foreign delegation prerequisite. |
| DP-016 | — | ENGINEERING_DETAIL | Approver authority verified via the existing grantor/role model; no dedicated registry. |
| DP-017 | — | ENGINEERING_DETAIL | Fail-closed invalidation on authority loss mirroring the existing grant-invalidation pattern (PH2-A-05/DATA-005). |
| DP-018 | — | EXISTING_DECISION | ADR-0012 §4.1 mandatory live check already answers this: authority loss after enqueue is visible at E2 and queued jobs fail closed. |
| DP-019 | — | ENGINEERING_DETAIL | Small closed versioned reason enum mapped to the existing 409 dispatch-rejection pattern. |
| DP-020 | — | ENGINEERING_DETAIL | Audit naming `agent.receipt.*` under the existing `agent.*` convention. |
| DP-021 | — | OWNER_POLICY_RESOLVED | **Entry 2**: **no new `approve_jobs` permission is added**; approval authority is derived from the existing Owner/Grantor/administrator roles and permission model; personal-workspace owner self-approval within the Q2-approved bounds; organization/shared workspaces keep existing administrator controls and approver authority ceilings. Must not bypass upper policy, explicit deny, membership conditions or delegation limits; approver-subject/execution-subject separation is kept where required. Existing role-ceiling rules remain mandatory. Formerly OWNER_DECISION_REQUIRED (Entry 2). |
| DP-022 | — | DEFERRED_WITH_GATE | No receipt-specific retention period; follows the production retention/audit decisions (DP-068/069, Q7 track). Gate D-1 below. |
| DP-023 | — | ENGINEERING_DETAIL | Metadata-only receipt/audit content with no credential bytes (existing mandatory rule); schema is design detail. |
| DP-024 | — | OWNER_POLICY_RESOLVED | **Q3**: per-environment verified isolation profiles; no universal VM mandate; specific supported targets remain unverified/unapproved per owner §4. |
| DP-025 | — | OWNER_POLICY_RESOLVED | **Q3**: isolation technology chosen per environment as a verified execution profile; OS-level isolation + independent verification mandatory; unverifiable environments do not run. |
| DP-026 | — | OWNER_POLICY_RESOLVED | **Q3**: guest-image/transfer/no-fallback controls designed per profile; no implicit isolation downgrade; unverified profiles stay unapproved (owner §4). |
| DP-027 | — | OWNER_POLICY_RESOLVED | **Q3**: supported Linux hosts = those passing the profile's verification; no exhaustive distro matrix promised. |
| DP-028 | — | OWNER_POLICY_RESOLVED | **Q3**: VM/microVM where the risk profile warrants, not universally; per-environment constraints and guarantees stated explicitly. |
| DP-029 | — | OWNER_POLICY_RESOLVED | **Q3**: additional layers (rootless OCI etc.) only where verified for the profile; container-only is never equated with kernel separation. |
| DP-030 | — | OWNER_POLICY_RESOLVED | **Q3**: if isolation cannot be verified, execution does not run; no unverified host-direct execution or implicit downgrade. |
| DP-031 | — | OWNER_POLICY_RESOLVED | **Entry 3 (design approval):** an authenticated, authorized, encrypted LAN-internal Runner↔Control-Plane channel is approved as the base communication *design*. Endpoints/ports/protocols/direction/boundaries must be explicit and individually designed, verified, independently reviewed and separately Owner-approved; communication to non-approved destinations is denied; no implicit internet/cloud/unapproved-LAN/provider-API allowance; fail-closed on unverifiable paths. This is NOT approval of firewall changes, port opening or Runner communication start. Remote/external-network Runner operation stays in the final requirements for separate design. Formerly OWNER_DECISION_REQUIRED (Entry 3, grouped with DP-032; owner §4「未承認の外部通信」activation still separately gated). |
| DP-032 | — | OWNER_POLICY_RESOLVED | **Entry 3 (design approval):** no endpoint may cross guest/private-network/external-egress boundaries without exact separate approval; the approved LAN-channel design inherits per-endpoint design→verification→independent review→separate Owner approval and default-deny for everything else. Provider egress stays denied regardless. Formerly OWNER_DECISION_REQUIRED (Entry 3). |
| DP-033 | — | ENGINEERING_DETAIL | Minimal verified transfer mechanism within no-unrestricted-host-access and fail-closed constraints; no bespoke broker mandated without threat evidence. |
| DP-034a | DP-034 | OWNER_POLICY_RESOLVED | **Q4**: official CLI / existing login methods preferred; no unofficial auth circumvention; API-key not forced; per-adapter verification of terms/auth/isolated operation. |
| DP-034b | DP-034 | OWNER_POLICY_RESOLVED | **Entry 4 (design/verification approval):** actual provider credential supply to Runners is **not permitted at this stage**. Officially supported auth/execution methods (Codex CLI, Claude Code, etc.) take priority; per-adapter verification of auth method, terms, isolated-environment operation and credential protection; broker-mediated supply is designed and compared, and its adoption requires verification evidence, independent review and separate Owner approval. Credentials never enter job inputs, receipts, audit logs or model context; adapters that cannot demonstrate safe supply are rejected for that environment; unofficial circumvention/subscription-bypass is prohibited. This approves the design and verification of supply methods, not real account login, credential readout/transfer/supply. Formerly OWNER_DECISION_REQUIRED (Entry 4). |
| DP-035 | — | OWNER_POLICY_RESOLVED | **Entry 5 (recommended configuration approved as design policy):** OS-keystore-protected per-instance Runner identity; vetted standard TLS; one-time challenge enrollment by an authenticated administrator; strict binding of Runner instance to enrolled ID; revocable Runner ID. Formerly OWNER_DECISION_REQUIRED (trust anchor/key custody — owner §4 cluster; Entry 5). |
| DP-036 | — | OWNER_POLICY_RESOLVED | **Entry 5:** vetted standard TLS/crypto as the baseline; custom CA, dedicated hardware authentication and multi-administrator quorum are **not required initially** (unless necessity is demonstrated). Numeric cipher/suite selections remain standards+measurement-driven (verification condition). Formerly OWNER_DECISION_REQUIRED (cluster; Entry 5). |
| DP-037 | — | OWNER_POLICY_RESOLVED | **Entry 5:** no custom CA hierarchy / enterprise PKI requirement as a default; enterprise PKI integrates only where a deployment actually has it. Formerly OWNER_DECISION_REQUIRED (cluster; Entry 5). |
| DP-038 | — | OWNER_POLICY_RESOLVED | **Entry 5:** OS keystore is the approved custody mechanism; hardware attestation/non-exportability requirements are not required initially. Verification condition: OS keystore availability and key/credential protection must be demonstrated per platform. Formerly OWNER_DECISION_REQUIRED (cluster; Entry 5). |
| DP-039 | — | OWNER_POLICY_RESOLVED | **Entry 5:** enrollment is a one-time challenge by an authenticated authorized administrator binding the exact Runner instance/key; enrollment/revocation authority maps to the existing RBAC (verification condition). Formerly OWNER_DECISION_REQUIRED (cluster; Entry 5). |
| DP-040 | — | OWNER_POLICY_RESOLVED | **Entry 5:** key lifetime/rotation is measured and verification-driven — standard methods plus measured operational data fix the values; no fixed interval without evidence. Formerly OWNER_DECISION_REQUIRED (cluster; Entry 5). |
| DP-041 | — | OWNER_POLICY_RESOLVED | **Entry 5:** revoke-then-re-enroll on key loss/compromise; privilege escalation during key update/revocation/recovery must be verified absent. Formerly OWNER_DECISION_REQUIRED (cluster; Entry 5). |
| DP-042 | — | ENGINEERING_DETAIL | Live revocation status via the same authority, fail-closed on uncertainty; no invented SLA/cache values. |
| DP-043a | DP-043 | EXISTING_DECISION | Queued/active-work cancellation and hold follow ADR-0012's mandatory cancellation/hold semantics; not reopened. |
| DP-043b | DP-043 | OWNER_POLICY_RESOLVED | **Entry 5:** compromise response is revoke-then-re-enroll with defined procedures for job stop, result hold and re-enrollment; audit of recovery operations. Formerly OWNER_DECISION_REQUIRED (root-compromise recovery / held-output disposition — owner §4 cluster; Entry 5). |
| DP-044 | — | ENGINEERING_DETAIL | Opaque one-use reference over authenticated transport to a closed versioned contract; no second job-envelope signature by default. |
| DP-045 | — | ENGINEERING_DETAIL | No second signature family; vetted TLS + closed schema; any later algorithm choice separately reviewed. |
| DP-046 | — | ENGINEERING_DETAIL | CP-authoritative online freshness; no second envelope TTL or skew grace; numeric bounds only via DP-010/011 (still 【要決定】). |
| DP-047 | — | ENGINEERING_DETAIL | Durable CP job ID consumed atomically online; no separate nonce ledger. |
| DP-048 | — | ENGINEERING_DETAIL | Single CP authority checks all mandatory bindings + exact enrolled Runner; bindings not reopened; endpoint/schema is design detail. |
| DP-049 | — | ENGINEERING_DETAIL | Result digest bound to job/instance, live revalidation before release; artifact signature only if a channel change justifies it. |
| DP-050 | — | DEFERRED_WITH_GATE | Artifact/audit retention follows the existing retention/backup decisions (Q7 production track); Q6's deny-immediately/retain-separately applies meanwhile. Gate D-2 below. |
| DP-051 | — | ENGINEERING_DETAIL | Measured admission/deadline/cancellation bounds; ADR-0012 cancellation semantics unchanged; no arbitrary quotas. |
| DP-052 | — | ENGINEERING_DETAIL | Per-platform test inventory/thresholds with positive+negative controls, synthetic data and independent review; tests never activate anything. |
| DP-053a | DP-053 | ENGINEERING_DETAIL | Evidence bound to the exact build/config/tests, refreshed on material change, independently reviewed. |
| DP-053b | DP-053 | EXISTING_DECISION | Activation authority is the owner via a separate explicit decision — an existing rule (ADR-0012 / owner standing instructions), not reopened. |
| DP-054 | — | OWNER_POLICY_RESOLVED | **Q5**: complete manual upload/retrieval/citation/analysis first; connector-specific source-ACL design is a later phase; no research-support function is removed from the final requirements. |
| DP-055 | — | OWNER_POLICY_RESOLVED | **Q5**: this phase covers manual upload only; local-folder/NAS/online connectors are later-phase and separately approved (connection/auth/transfer 別途承認). |
| DP-056 | — | DEFERRED_WITH_GATE | Connected-source identity/freshness design belongs to the later connector design (Q5); Q6's immediate-denial and re-check-on-reuse apply as standing design constraints. Gate D-3 below. |
| DP-057a | DP-057 | EXISTING_DECISION | Source authorization is an additive fail-closed gate and never replaces Locus ACLs / explicit deny (existing requirement). |
| DP-057b | DP-057 | DEFERRED_WITH_GATE | Exact combination matrix for connected sources specified in the connector design (Q5 later phase). Gate D-3 below. |
| DP-058 | — | OWNER_POLICY_RESOLVED | **Q6**: on access-loss, viewing/search/citation/reuse is denied immediately; re-display/reuse re-checks current permission; no instant physical deletion; retention managed separately per policy. |
| DP-059a | DP-059 | OWNER_POLICY_RESOLVED | **Q6**: Locus-side binding invalidated, derived access denied, access-blocked state maintained per retention policy. |
| DP-059b | DP-059 | DEFERRED_WITH_GATE | Upstream deletion requests require separately approved source-write authority; Locus never modifies upstream without permission (Q6). Gate D-3 below. |
| DP-060a | DP-060 | DEFERRED_WITH_GATE | Original copy/cache/fetch design decided in the connector phase (Q5). Gate D-3 below. |
| DP-060b | DP-060 | DEFERRED_WITH_GATE | Retention/backup periods decided in the production storage track (Q7/DP-069); Q6 retain-but-deny applies meanwhile. Gate D-2 below. |
| DP-061 | — | DEFERRED_WITH_GATE | Multi-source document model decided within the connector design phase (not in the initial design); 1:1 default + extensible schema is a proposal-layer option. Gate D-3 below. |
| DP-062a | DP-062 | EXISTING_DECISION | Admin configures shared roots; personal material private by default (existing design principle). |
| DP-062b | DP-062 | DEFERRED_WITH_GATE | Connector credentials/egress allowlist designed and separately approved in the connector phase (owner §4 gates). Gate D-3 below. |
| DP-063 | — | DEFERRED_WITH_GATE | Sync failure/concurrency/retry/linearization semantics specified in the connector design; Q6 constraint: no release after an observed denial, visibility invalidated first. Gate D-3 below. |
| DP-064a | DP-064 | EXISTING_DECISION | Metadata-only audit; content/credentials/sensitive paths/ACL payloads never logged (existing mandatory rule). |
| DP-064b | DP-064 | DEFERRED_WITH_GATE | Source-metadata retention/access/privacy restrictions follow the audit retention decision (Q7 track). Gate D-2 below. |
| DP-065 | — | EXISTING_DECISION | Source-read permission never consents to external-model egress (existing DATA-012/Product invariant — confirmed here, not reopened). Any future external send still requires its own separate approval. |
| DP-066 | — | OWNER_POLICY_RESOLVED | **Q7**: production DB / vector search / graph technologies compared and verified, then fixed in a later phase; deferral is not removal from the final requirements. |
| DP-067 | — | OWNER_POLICY_RESOLVED | **Q7**: production deployment/TLS/session/LAN verification policy compared, verified and decided in a later phase; no production exposure approved now. |
| DP-068 | — | OWNER_POLICY_RESOLVED | **Q7**: audit protection/retention/erasure decided in a later phase after comparison; audit protection remains a runtime-activation gate. |
| DP-069 | — | OWNER_POLICY_RESOLVED | **Q7**: production retention/backup/secure-deletion policy decided in a later phase; no period inferred; Q6 retain-but-deny applies meanwhile. |
| DP-070 | — | OWNER_POLICY_RESOLVED | **Q7**: production AI provider/capacity decided after evidence and provider-term review; routing requires explicit policy/terms approval. |
| DP-071 | — | OWNER_POLICY_RESOLVED | **Entry 6 (option c):** delegatee-side UI improvement is the approved priority; the current project-scoped delegation/permission model is maintained. UI must let users understand delegation expiry, grantor, scope, revocation state and self-revocation; backend permission verification is mandatory (UI hiding alone is insufficient). Organization-level delegation expansion is **not implemented now** — it stays in the final requirements for a later phase with explicit requirements/dependencies/acceptance criteria, and is not reopened. Formerly OWNER_DECISION_REQUIRED (Entry 6). |
| DP-072 | — | OWNER_POLICY_RESOLVED | **Q7**: production session persistence/lifecycle decided in the later production phase after comparison; nothing inferred for the prototype. |

## Split register

| Original | Parts | Reason for the split |
|---|---|---|
| DP-015 | DP-015a (delegation as additional input — EXISTING_DECISION), DP-015b (personal-workspace self-authorization — Q2) | One item carried a delegation-authorization part and a personal-workspace part resolved by different instruments. |
| DP-034 | DP-034a (authentication-method policy — Q4), DP-034b (credential supply — owner §4 【要決定】) | Q4 resolves the method policy; actual credential supply stays an unresolved §4 item. |
| DP-043 | DP-043a (cancellation/hold semantics — EXISTING_DECISION), DP-043b (root-compromise recovery / held-output disposition — owner §4 cluster) | Mandatory revocation semantics are settled; recovery/key handling is not. |
| DP-053 | DP-053a (evidence binding / verifier — ENGINEERING_DETAIL), DP-053b (activation authority — EXISTING_DECISION) | Evidence design is engineering; activation authority is already fixed as a separate owner decision. |
| DP-057 | DP-057a (additive-gate invariant — EXISTING_DECISION), DP-057b (combination matrix — connector phase) | The invariant is existing; the detailed matrix awaits the connector design. |
| DP-059 | DP-059a (Locus-side handling — Q6), DP-059b (upstream deletion authority — deferred) | Q6 fixes Locus-side behavior; upstream write authority is a separate future approval. |
| DP-060 | DP-060a (copy/cache/fetch — connector phase), DP-060b (retention/backup — production track) | The two parts belong to different deferred tracks with different gates. |
| DP-062 | DP-062a (shared-root config authority — EXISTING_DECISION), DP-062b (credentials/egress — connector phase) | Config authority is settled; credential/egress approval is gated. |
| DP-064 | DP-064a (metadata-only audit — EXISTING_DECISION), DP-064b (retention/access/privacy — audit track) | The exclusion rule is existing; retention restrictions follow the audit retention decision. |

## Entry 1–6 resolution — 2026-11-10 (recorded 2026-11-11)

The owner's formal decisions [OWNER_DECISIONS_2026-11-10-ENTRIES.md](OWNER_DECISIONS_2026-11-10-ENTRIES.md) resolve the previously open `OWNER_DECISION_REQUIRED` rows. Full decision-to-artifact traceability lives in [OWNER_DECISION_REGISTER.md](OWNER_DECISION_REGISTER.md).

| Entry | Choice | DP rows | Decided values (summary) | Implementing artifact(s) |
|---|---|---|---|---|
| Entry 1 | (a) 承認 | DP-010, DP-011 | Receipt TTL default 24 h / maximum 7 days; CP-authoritative absolute epoch-seconds; no grace; no expired-receipt reuse; in-scope auto-reissue as a new authorization decision; receipt TTL separate from delegation TTL | 2b receipt implementation (slot Q, `agent-work/P1-RECEIPT.md`); ADR-0013 §7; HYBRID_STEP2_RECEIPT_CONTRACT §2.1 |
| Entry 2 | (a) 承認 | DP-021 | No new `approve_jobs` permission; approval authority derived from existing Owner/Grantor/admin roles; Q2-bounded personal self-approval; existing ceilings preserved | 2b approval-flow implementation (slot Q, same package) |
| Entry 3 | (a) 承認（設計） | DP-031, DP-032 | Authenticated LAN-internal channel approved as design; per-endpoint design→verification→independent review→separate Owner approval; deny elsewhere; fail-closed; not firewall/port/activation approval | `HYBRID_RUNNER_COMMUNICATION_DESIGN.md` (slot P3) |
| Entry 4 | (a) 承認（設計・検証のみ） | DP-034b | No real credential supply yet; official CLI methods preferred; per-adapter verification; broker-mediated design/compare with evidence+review+separate approval; credentials never enter inputs/receipts/audit/model context | `HYBRID_AGENT_ADAPTER_DESIGN.md` (slot P4) |
| Entry 5 | 推奨構成 承認（設計方針） | DP-035–041, DP-043b | OS-keystore per-instance identity, vetted TLS, admin one-time-challenge enrollment, strict ID binding, revocable ID, measured rotation, revoke-then-re-enroll, full audit; no custom CA/hardware/quorum initially; design-policy approval only — no key issuance/registration/activation | `HYBRID_RUNNER_TRUST_DESIGN.md` (slot P2) |
| Entry 6 | (c) 承認 | DP-071 | Delegatee-side UI only; project-scoped delegation model maintained; backend permission verification required; org-level delegation not implemented now (kept in final requirements for a later phase) | UI research `UI_OPENCODE_RESEARCH.md` (slot V); UI implementation running (slot W) |

Still **【要決定】／別途承認** after Entries 1–6: individual endpoint approvals (Entry 3 scope), real credential supply/activation (Entry 4 scope), actual key issuance/Runner registration/communication start/execution activation (Entry 5 scope), unverified isolation profiles, B6 dispatch release, unapproved external communication/egress, real-data use, production release, production retention/audit (D-1–D-3). The owner's §2 scope (design/spec/QA approved; activation/data/production not approved) governs.

## OWNER_DECISION_REQUIRED — decision requests in the owner-directed 8-field format

> **Update 2026-11-11:** all six decision requests below were **resolved by the owner's Entry 1–6 decisions of 2026-11-10** ([OWNER_DECISIONS_2026-11-10-ENTRIES.md](OWNER_DECISIONS_2026-11-10-ENTRIES.md)); `OWNER_DECISION_REQUIRED` is now empty. The blocks below are retained as historical proposals for traceability — their 「後回し可否」/「stays 【要決定】」closings and "unapproved options" wording are historical and superseded by the resolution table above. The owner's §2/§5 standing boundaries (approval ≠ activation; no dispatch, credential supply, egress, real data or production activation) are unchanged.

These are the only genuinely open owner decisions after applying Q1–Q7 and existing decisions. No technical number, permission or activation is granted anywhere below; source-proposal values are cited as **unapproved options**. Per the owner's standing instruction, related items are grouped into one decision request rather than fragmented.

### Entry 1 — Receipt TTL（既定値・上限値）: DP-010, DP-011

- **当初設計との対応:** ADR-0013 §7 explicitly leaves the job-receipt TTL to be decided. The PH2-A-01 delegation-TTL decision is precedent only; it is not automatically inherited by job receipts.
- **選択肢:** (a) align with the delegation precedent (proposal layer suggests default 24 hours / maximum 7 days — unapproved values, cited for orientation only); (b) shorter job-scoped windows tied to the execution window; (c) any other owner-chosen default/maximum pair.
- **推奨案:** the proposal layer recommends (a) with absolute epoch-seconds expiry and no grace period (DP-012), plus automatic reissue for in-scope jobs so expiry does not stall approved work.
- **メリット:** bounds the exposure of unused approvals; one coherent expiry source shared with the job envelope (no second TTL).
- **デメリット:** long-running jobs need explicit policy or reissue; values require maintenance as usage is measured.
- **自律性・利便性・安全性への影響:** autonomy/usability rise with sensible defaults; safety is maintained because expiry is a hard fail-closed bound and revocation remains live regardless of TTL.
- **採用で可能になる作業:** fixes the numeric parameters of the 2b receipt contract, its tests and the envelope freshness wiring (DP-012/046 references).
- **後回し可否:** the values are needed before the 2b receipt contract is finalized/implemented; design and other approved-scope work continue meanwhile (owner standing instruction). The numbers themselves are NOT approved by this document — they stay 【要決定】 per owner §4.

### Entry 2 — 承認用の新規権限の要否（例: approve_jobs）と上限: DP-021

- **当初設計との対応:** ADR-0013 §8 leaves the permission/ceiling open; IAM-010/011 and ADR-0012 E7 keep the existing role model and role-ceiling rules mandatory.
- **選択肢:** (a) add no new permission — derive approval authority from the existing non-delegable grantor/owner roles; (b) add a dedicated `approve_jobs` permission with an explicit ceiling; (c) other permission shapes.
- **推奨案:** (a) — reuse the existing grantor authority; avoid privilege sprawl and a parallel permission lifecycle.
- **メリット:** one authority model; no new privilege to audit or ceiling-manage.
- **デメリット:** fine-grained delegation of approval authority becomes impossible until a future decision.
- **自律性・利便性・安全性への影響:** autonomy/usability unchanged; safety unchanged or improved (no new privilege surface); Q2's personal-workspace self-approval is bounded by verified owner authority, not by a new permission.
- **採用で可能になる作業:** finalizes the 2b approval-flow authorization reference without a permission-registry change.
- **後回し可否:** the choice must be fixed before 2b approval-flow implementation; it stays 【要決定】 per owner §4「新規の権限・承認例外」until then.

### Entry 3 — Runner通信トポロジと境界越えエンドポイント: DP-031, DP-032

- **当初設計との対応:** HBR-001/002/007 and the Product Spec's local-first, no-egress posture; Step-3 §1.2 names only a local-only endpoint; no Runner topology was ever approved.
- **選択肢:** (a) approve a narrow authenticated LAN-internal Runner↔Control-Plane channel only, with external egress still denied; (b) enumerate exact endpoints/protocols individually; (c) keep the current state (default deny, Runner networking inactive).
- **推奨案:** (a) as the skeleton, with the exact endpoint/protocol proposed, verified and independently reviewed, then individually approved; default deny is preserved for everything else and provider egress stays denied regardless.
- **メリット:** enables hybrid step-3 design/verification while keeping the blast radius minimal.
- **デメリット:** per-endpoint approval overhead; wildcard or subnet-wide rules must be rejected to avoid weakening the boundary.
- **自律性・利便性・安全性への影響:** autonomy/usability rise at activation time; safety maintained by default deny + exact-endpoint approval + ADR-0012 dual-plane separation.
- **採用で可能になる作業:** fixes step-3 communication design, firewall verification plan and the trust-root verification test scope.
- **後回し可否:** needed before any Runner network activation; design and desk verification continue meanwhile. Communication remains unauthorized until then (owner §4「未承認の外部通信」).

### Entry 4 — プロバイダー認証情報の供給（Runnerジョブ内の外部AI認証）: DP-034b

- **当初設計との対応:** HBR-005 (owner-added); the Product Spec defines no Runner credential scheme; DP-034a (Q4) already fixes the method policy (official CLI/existing login preferred, no circumvention, API-key not forced).
- **選択肢:** (a) broker-mediated supply after positive/negative proof and separate approval; (b) no supply — adapters whose credentials cannot be kept from tool processes remain unavailable on that platform (safe local paths still work).
- **推奨案:** under Q4, verify per-adapter whether official authentication works inside the verified isolation profile; broker supply only after the broker evidence exists and is separately approved; until then supply nothing.
- **メリット:** official, supported authentication; subscription reuse where officially permitted (Q4).
- **デメリット:** provider terms must be checked per adapter; some adapter/platform combinations stay unavailable.
- **自律性・利便性・安全性への影響:** usability rises for adapters that pass verification; safety maintained by keeping credentials out of job inputs/audit logs and behind verified isolation.
- **採用で可能になる作業:** per-adapter credential-supply design, broker proof tests and the activation decision for those adapters.
- **後回し可否:** needed before any credential activation; stays 【要決定】 per owner §4「プロバイダー認証情報の供給」until then.

### Entry 5 — Runnerの信頼・登録・鍵管理方式（クラスタ）: DP-035, DP-036, DP-037, DP-038, DP-039, DP-040, DP-041, DP-043b

- **当初設計との対応:** HBR-007 adds revocable, authenticated instance identity as a hybrid requirement; the initial design contains no PKI/keystore/enrollment ceremony; ADR-0012 requires authenticated, revocable instances but no specific trust machinery.
- **選択肢（クラスタ内の各論点）:** trust anchor/custody — shared static secret, TOFU/self-signed pin, installation-specific asymmetric identity under an installation trust anchor, or enterprise PKI (DP-035); crypto profile/hardware/quorum — vetted platform TLS/crypto only, or hardware/quorum requirements with threat evidence (DP-036); enterprise PKI in or out of scope (DP-037); keystore/attestation minimums (DP-038); enrollment/revocation authority and whether a second local confirmation channel is needed (DP-039); lifetime/rotation/overlap values, set on measurement (DP-040); re-enrollment/recovery/compromise rules (DP-041); root-compromise recovery and held-output disposition (DP-043b).
- **推奨案:** minimal standard per-instance identity protected by the OS keystore, vetted platform TLS, enrollment by an authenticated authorized administrator binding a one-use challenge to the exact key/fingerprint, measured rotation with proof-of-possession cutover, revoke-then-re-enroll on loss/compromise, and no custom CA hierarchy, hardware gate, quorum or fixed interval without threat evidence. Enterprise PKI integrated only where the deployment actually has it.
- **メリット:** revocable instances for desktop/server without bespoke infrastructure; consistent with ADR-0012 and the over-engineering reductions in the proposal layer.
- **デメリット:** standalone installations need a local trust lifecycle; high-assurance classes may require later upgrades.
- **自律性・利便性・安全性への影響:** autonomy/usability preserved (no repeated owner confirmation ceremonies); safety maintained via revocable identity and fail-closed status checks; no self-asserted identity.
- **採用で可能になる作業:** finalizes Runner identity/enrollment/rotation design and unblocks step-3 trust implementation after verification.
- **後回し可否:** needed before Runner enrollment/activation; stays 【要決定】 per owner §4「Runnerの具体的な信頼・登録・鍵管理方式」「未検証の隔離プロファイル」until then.

### Entry 6 — 組織モデルと残余の管理UI/受領側UI: DP-071

- **当初設計との対応:** Product role templates; PH2-A already deferred organization-wide delegation — that deferral is resolved and is not reopened. Only the residual recipient-side UI refinement and the question of any org-level management surface remain.
- **選択肢:** (a) no org-level management surface (project-scoped only, refine recipient UI within current scope); (b) define an org model first, then design the management surface; (c) recipient-UI refinement only for now.
- **推奨案:** (c) first; treat (b) as a separate design proposal once the org model requirement is actually needed.
- **メリット:** avoids inventing an org model ahead of need; keeps delegation semantics stable.
- **デメリット:** org administrators may lack a dedicated surface longer.
- **自律性・利便性・安全性への影響:** no research-flow restriction; no scope expansion; safety unchanged because no new authority is created.
- **採用で可能になる作業:** recipient-side delegation UI refinement within the existing project-scoped decision.
- **後回し可否:** yes for (b); the owner decision is only which residual scope, if any, to pursue now.

## DEFERRED_WITH_GATE — start conditions and acceptance gates

| Gate | Items | Start condition | Acceptance gate |
|---|---|---|---|
| D-1 Production retention/audit policy | DP-022, DP-060b, DP-064b | Owner's Q7-track production decisions on retention/backup/audit (DP-068/DP-069) are made. | Retention/access/erasure policy explicitly approved and applied to receipt/audit/artifact/source records; no period invented before that. Q6's deny-immediately/retain-separately applies meanwhile. |
| D-2 Artifact retention wiring | DP-050 | D-1 decisions exist; step-2/step-3 contract design available. | Artifact/audit retention inherited from the approved policy; live revalidation of ACL/classification/source before any persistence, reuse, export or release is verified. |
| D-3 Connector design phase | DP-056, DP-057b, DP-059b, DP-060a, DP-061, DP-062b, DP-063 | Q5 later-phase connector design is authorized (connection/auth/transfer separately approved per Q5). | Connector design ADR approved with live-check/fail-closed semantics (Q6 constraints), no credentials in metadata/audit, egress default-deny unless separately approved; independent review completed. |

## Cross-cutting design constraints applied from Q1–Q7

- **Q1** applies to all receipt/approval items (DP-001–023): automatic issuance within the admin-approved Workspace Policy/operation range/data classification/execution environment; no auto-approval of out-of-scope operations, unapproved external communication, privilege escalation or safety-boundary changes; auditable approval history; receipts issued strictly per current permission/policy.
- **Q2** applies to personal-workspace items (DP-006, DP-015b): owner self-approval within permitted bounds; upper policy cannot be overridden; no automatic acquisition of org-shared data or others' workspaces; self-approval bounds and ceilings must be documented.
- **Q3** applies to all isolation/Runner items (DP-024–030 and related DP-031–053): verified per-environment isolation profiles; OS-level isolation + independent verification mandatory; no execution where isolation is unverifiable; no unverified host-direct execution or implicit downgrade; per-environment constraints and guarantees documented.
- **Q4** applies to provider-adapter items (DP-034a, DP-023/DP-048 credential-exclusion aspects): official CLI/existing login preferred; no unofficial circumvention; per-adapter verification; no credentials in job inputs or audit logs; actual activation separately approved.
- **Q5** applies to storage-ACL scope items (DP-054–065 connector aspects): manual upload first; connectors later phase with separate approval; no research-support function removed from the final requirements.
- **Q6** applies to all revocation/access-loss items (DP-058 and, as standing constraints, DP-056/057/059/063/050/069): immediate denial of viewing/search/citation/reuse on permission loss; current-permission re-check on re-display/reuse; no instant physical deletion; retention separately managed; never modify/delete upstream sources without permission.
- **Q7** applies to production-technology items (DP-066–070, DP-072) and to all prototype-to-production inheritances (DP-003/013/022): compare and verify, then fix in a later phase; deferral is not removal from final requirements; traceability of acceptance criteria maintained; production release and real-data use separately approved.

## Adversarial self-review notes

> **Update 2026-11-11:** the notes below are the dated self-review at the 2026-11-09 classification baseline; the owner's Entry 1–6 decisions (2026-11-10) subsequently resolved the rows listed in §"Entry 1–6 resolution". They are retained as historical evidence and are not silently overwritten.

- All 72 original DP numbers appear exactly once as primaries; 9 split rows carry a/b labels pointing back to their originals (81 rows total, matched by the summary counts).
- No cell or row was resolved by inventing a value: TTL numbers (DP-010/011), new permissions (DP-021), Runner trust/enrollment/key management (DP-035–041, DP-043b), unverified isolation profiles (residual of DP-024–030), provider credential supply (DP-034b), unapproved external communication (DP-031/032), real-data use and production release (Q7 gates) all remain 【要決定】 per owner §4.
- Approved items are not re-asked: DP-015a/DP-065/DP-071 explicitly preserve the PH2-A and DATA-012 invariants; DP-053b preserves the separate-activation rule; no row reopens a resolved decision.
- No safety boundary is weakened: B6, ADR-0011, ADR-0012, fail-closed, no-egress and metadata-only audit appear as binding constraints wherever the affected items reference them.
- The queue document's fixed header/ID-column text (「every row remains 【要決定】」) was intentionally left untouched per the task constraint that only OWNER DECISION cells may be edited; the filled cells themselves carry the authoritative status and links to this classification.
