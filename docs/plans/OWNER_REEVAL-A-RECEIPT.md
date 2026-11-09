# Owner re-evaluation A — DP-001…DP-023 (ADR-0013 job receipt) vs the initial Locus design

Status: **recommendation layer only.** This file evaluates the 23 job-receipt decision
items against the INITIAL Locus design per
`docs/plans/agent-work/OWNER_REEVAL-GROUNDING.md` (owner directive 2026-11-09). It
records no owner decision, resolves no 【要決定】 item, and does not edit ADR-0013 or
the queue cells.

**Global guardrail (applies to every ⚠ SAFETY BOUNDARY item below):** design
recommendations ≠ execution permission. Nothing here activates dispatch, lifts B6,
enables egress, activates a Runner or isolation, approves credentials, or exposes
production. ADR-0012's approval-before-dispatch boundary (§4.1, E1/E2) stays INTACT
in every recommendation below; autonomy-friendliness is achieved inside the boundary,
never by weakening it. Activation remains separately owner-gated.

**Grounding sources used:** `REQUIREMENT_ID_SCHEME.md` / `REQUIREMENTS_TRACEABILITY_MATRIX.md`
IDs (HBR-*, IAM-*, DATA-*, PROD-*, LOOP-*, GOV-*); `PRODUCT_SPEC.md`; `ARCHITECTURE.md`;
ADR-0011/0012/0013; `HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md`; `PHASE2_DELEGATION_SPEC.md`
+ the RESOLVED 2026-11-09 register (PH2-A-01…12); `locus-hybrid-agent-requirements.md`;
master roadmap rows H2/H3; audit finding F5 (AUD-P3-CONSISTENCY) noted, not re-decided.

## Cross-cutting verdicts (owner's special verifications, group A)

1. **Does the job-approval mechanism obstruct autonomous in-scope execution?**
   The initial design requires an *authoritative receipt* per job (ADR-0012 §4.1) — it
   does NOT require a human per job. With policy-driven issuance inside an
   owner/administrator pre-approved scope (see DP-005) and automated re-issuance, the
   receipt mechanism adds no human stall to in-scope work: issuance, recheck and expiry
   handling are automatic, and a human appears only for the exception/first-scope class
   (owner priorities 4/5 satisfied; priority 6 intact). Per-job human approval for ALL
   jobs would be an initial-design-ungrounded obstruction (flagged at DP-005).
2. **Admin approval vs personal-workspace separation (DP-015–018).** The initial design
   already separates the two planes of authority: org/admin policy (HBR-002,
   NON_ADMIN ceilings, non-delegable admin permissions) vs personal workspace
   ownership (PRODUCT_SPEC personal documents / per-user privacy; hybrid 要件1
   Desktop Runner personal workspaces; PH2-A-03 grantor = project owner OR org
   admin). The receipt layer should reuse exactly that boundary: approver authority
   = existing grantor-class authority over the target project/workspace (DP-016),
   delegation is an additional live-checked input never a prerequisite (DP-015),
   and in a personal workspace the workspace owner's issuer-verified authority is the
   approver class — no separate admin approval surface is grounded by the initial
   design (DP-006/018 carry the nuance).
3. **Can the Agent Adapter consume existing AI agents as-is?** Yes — and this must stay
   true. The receipt contract lives entirely in Control Plane (issuer, E1) and Runner
   host (E2) code; the adapter interface remains the single `run_job(job,
   workspace_policy)` operation (ADR-0012 B3; step-2 §1.1/§2.1); provider CLIs (Codex
   CLI, Claude Code, local LLM) keep their own official auth and native tools
   (hybrid 要件5, HBR-005). No DP-001…023 recommendation may place receipt handling,
   signing or verification inside the adapter or the CLI agents; requiring agent
   rewrites would contradict the owner requirement (目的/要件5) and is flagged where
   an option could drift that way. Receipt/envelope metadata is Locus-plane
   bookkeeping the agents never see.
4. **Extensibility.** The receipt must carry an explicit `schema_version` field from
   day one, exchanged via the versioned `runner_contract/` transport (ADR-0012 B4:
   unknown fields/unsupported versions fail closed). This is initial-design grounded
   (B4), costs nothing now, and is folded into the DP-002/DP-003 minimal
   configuration rather than proposed as a new mechanism.

---

## DP-001 — `runner_instance_id` in the receipt vs enqueue-time envelope binding

1. **初期設計要件IDと原典:** HBR-010 (ADR-0012 B5 runner-instance identity, instance-scoped
   bindings), HBR-012 (step-2 §2.1 `workspaces.runner_instance_id`,
   `workspace_adapter_bindings`), HBR-013 (ADR-0012 §4.1; step-2 §2.6). Source:
   ADR-0012 B5/§4.1; step-2 design §2.1/§2.6.
2. **当初想定されていた動作:** A workspace is bound to exactly one
   `(runner_instance_id, adapter_id)` pair; E2 rechecks the runner's own instance
   identity, policy version and workspace binding immediately before execution. The
   instance executing a job is derivable from the workspace binding — the initial
   design never duplicates it into an approval artifact.
3. **現在提示されている選択肢:** (i) put `runner_instance_id` in the receipt; (ii) rely
   on the enqueue-time envelope/binding. (Option set is complete for this question.)
4. **初期設計に最も整合する推奨案:** (ii) — envelope + workspace binding suffice; the
   receipt need not carry `runner_instance_id`. E2's mandatory independent recheck of
   its own instance identity against the workspace binding (step-2 §2.6/E2) already
   fails closed on any instance mismatch; duplicating the instance into the receipt
   adds a redundant constraint the initial design does not contain.
5. **自律性・利便性・安全性への影響:** (ii) avoids re-approval friction if an instance is
   re-enrolled/replaced under the same binding (autonomy/usability ↑); safety is
   unchanged — B5 identity, revocation and the E2 recheck are untouched, and B6/activation
   remain unapproved as before (⚠ SAFETY BOUNDARY item; recommendation is design only).
6. **推奨案を採用した場合の制約:** The workspace→instance binding becomes part of the
   effective authorization chain; any future multi-instance workspace class (not in the
   initial design) would require revisiting this and the step-2 binding model.
7. **Ownerが新たに決定する必要がある事項:** None beyond the ADR-0013 inventory; owner only
   ratifies "envelope binding sufficient" in the queue cell.

🚫初期設計反 — none. ⚠根拠不足制約 — option (i) as a *requirement* (derivable already).
📈過剰設計疑 — option (i) duplicates derivable state.

## DP-002 — Receipt signature / canonical serialization / nonce / envelope binding

1. **初期設計要件IDと原典:** HBR-013 (ADR-0012 §4.1), HBR-010 (B4 closed versioned
   contracts; B1 transport-only). Source: ADR-0012 §4.1/B1/B4; step-2 §2.6 ("receipt /
   job envelope must be signature-verified **or checked online** with the authoritative
   issuer"), E1/E2.
2. **当初想定されていた動作:** Both E1 and E2 verify the *same* receipt and envelope;
   E2 does not trust an enqueue-time assertion; replay must reject. The step-2 wording
   explicitly permits online checking as the verification mode — a full runner-side
   signature/canonicalization stack was never mandated.
3. **現在提示されている選択肢:** Scheme, canonicalization and nonce binding are open
   (no specific option supplied). (Option set incomplete by design — see 4.)
4. **初期設計に最も整合する推奨案:** 初期設計では未規定 → 最小構成推奨: issuer signs the
   receipt (audit-integrity artifact), but *runtime verification at both E1 and E2 is
   online* against the issuer over the versioned `runner_contract/` transport (B4);
   replay is prevented by job-ID uniqueness plus persisted single-consumption state;
   the envelope carries `schema_version` (B4) and the DP-001 binding set. No custom
   canonical-serialization contract is built while verification is online.
5. **自律性・利便性・安全性への影響:** Online verification keeps freshness maximal and the
   design small (autonomy: fewer moving parts to fail; safety: same mandatory
   fail-closed rechecks; E2 independence preserved because the Runner queries the
   authority itself, never trusting the Control Plane's enqueue claim). B6/activation
   remain unapproved (⚠ SAFETY BOUNDARY item; design only).
6. **推奨案を採用した場合の制約:** E2 execution becomes dependent on issuer
   reachability (fail-closed by mandate — offline Runner ⇒ no execution). If an owner
   later wants offline-capable verification, that is a new trust contract decision
   (DP-007/008), not an extension of this one.
7. **Ownerが新たに決定する必要がある事項:** Ratify "online verification, issuer-signed
   receipts, job-ID-based replay binding" as the 2b receipt-contract basis; a concrete
   signature algorithm is only needed for the audit artifact and may follow the
   existing trust-key decisions (group B, DP-035/036).

🚫初期設計反 — none. ⚠根拠不足制約 — none. 📈過剰設計疑 — a bespoke runner-side
signature/canonicalization verification stack would exceed what §2.6's online-check
wording needs.

## DP-003 — Receipt persistence / storage contract

1. **初期設計要件IDと原典:** HBR-012/HBR-013; IAM-015 (metadata-only audit); PROD-005 /
   DATA-013 (production DB remains open). Source: ADR-0012 §4.1; step-2 §2.1
   (`job_authorization_receipts` logical contract, "concrete schema only after the
   approval ADR"); ADR-0013 §2 (immutable rows; revocation as immutable events).
2. **当初想定されていた動作:** Receipts live in the existing Control-Plane control store
   (the same SQLite store pattern as the registry and delegation tables; production-DB
   migration is a separate already-open decision, not re-decided here); receipt rows
   immutable; revocation/expiry recorded as new immutable events (the
   `delegation_*_no_update/_no_delete` trigger pattern in `backend/app/service.py`).
3. **現在提示されている選択肢:** Storage mechanism open; ADR-0013 supplies the immutability
   convention.
4. **初期設計に最も整合する推奨案:** 初期設計では未規定 → 最小構成推奨: reuse the existing
   control-store + immutable-rows/immutable-events pattern (same conventions as PH2-D
   delegation); receipt table carries the §1 fields plus `schema_version`; no external
   or new store.
5. **自律性・利便性・安全性への影響:** One store, one discipline — no new operational
   surface (autonomy/usability neutral-positive); fail-closed authoritative state
   preserved; B6/activation unapproved (⚠ SAFETY BOUNDARY — authoritative state; design
   only).
6. **推奨案を採用した場合の制約:** Receipt availability equals control-store
   availability; a production-DB migration (DATA-013, DP-066) later moves receipts with
   everything else.
7. **Ownerが新たに決定する必要がある事項:** Only retention (DP-022) and the already-open
   production-DB choice; storage mechanics need no new owner decision.

🚫初期設計反 — none. ⚠根拠不足制約 — none. 📈過剰設計疑 — a dedicated receipt store /
separate persistence service would exceed the initial design.

## DP-004 — Authoritative issuer architecture

1. **初期設計要件IDと原典:** HBR-013 (ADR-0012 §4.1 + open item (11)); HBR-010 (B1
   module separation). Source: ADR-0012 §4.1 item 1, B1; step-2 §2.6 ("approved
   authorization authority"); ADR-0013 §2.
2. **当初想定されていた動作:** A dedicated authority separate from Plane-M code (B1
   forbids `backend/app/agents/` → `backend/app/service.py` imports); the issuer alone
   writes receipts; approver identity is recorded by the issuer, never self-asserted
   by the actor.
3. **現在提示されている選択肢:** (a) Control-Plane-internal authority module; (b) explicit
   human approver per job; (c) delegation-derived input to an issuer. (Note: the option
   set mixes *architecture*, *approval policy* and *input* — (a) is the architecture
   question, (b) is DP-005's policy question, (c) is an input under DP-015; they are
   not mutually exclusive. Flagged as an incomplete/overlapping framing.)
4. **初期設計に最も整合する推奨案:** (a) — a Control-Plane-internal issuer module inside
   `backend/app/agents/`, separate from Plane-M (B1), as the single receipt writer.
   (b) and (c) become inputs to it, decided at DP-005/DP-015.
5. **自律性・利便性・安全性への影響:** An in-plane issuer is the only B1-consistent
   placement; it enables automated issuance (DP-005) without weakening the approval
   authority. B6/activation unapproved (⚠ SAFETY BOUNDARY — approval authority; design
   only).
6. **推奨案を採用した場合の制約:** The issuer inherits Control-Plane availability and
   audit obligations (B7); no external approval service may be introduced without a
   new owner decision.
7. **Ownerが新たに決定する必要がある事項:** Ratify (a) as the architecture; separate the
   policy question (DP-005) from it when deciding.

🚫初期設計反 — none. ⚠根據不足制約 — treating (b)/(c) as rival *architectures* is
ungrounded; they are policy/input choices. 📈過剰設計疑 — none.

## DP-005 — Per-job vs policy-driven vs first-scope approval classes

1. **初期設計要件IDと原典:** HBR-002 (org policy constrains execution; user settings only
   narrow), HBR-013 (ADR-0012 §4.1 authoritative receipt), HBR-014 (policy fields).
   Source: ADR-0012 §4.1; step-2 §2.2 lifecycle ("enqueue only after all gates and
   receipt recheck pass"), §3.1 policy fields; owner directive priorities 4/5 ("agents
   act autonomously WITHIN the pre-approved scope"; "unnecessary owner confirmations
   must not stop autonomous development").
2. **当初想定されていた動作:** The initial design's approval emphasis is *pre-approved
   scope*: administrators bind workspaces to policy versions (classification ceiling,
   runner types, egress `local_only`, adapter allowlist, filesystem scope) and the
   lifecycle state machine admits a job when all gates and a current receipt pass.
   Nothing in ADR-0012/step-2 requires a human decision per job — the mandatory item
   is the receipt, not the human.
3. **現在提示されている選択肢:** (a) per-job human approval; (b) automated policy-driven
   issuance; (c) approver approval only for a first-scope/exception class.
4. **初期設計に最も整合する推奨案:** (b) as the general class + (c) as the exception
   class, composed: policy-driven issuance whenever the job is fully inside a current
   pre-approved scope (workspace policy + adapter allowlist + delegation/membership
   authorization, live-checked); human approver decision only when the scope does not
   already cover the job (first activation of an adapter/destination/operation class,
   any above-scope request), failing closed to human approval when policy is silent.
   Per-job human approval for ALL jobs is recommended AGAINST: it adds a
   human-confirmation constraint the initial design does not contain (priority 7) and
   directly obstructs priorities 4/5, while ADR-0012's receipt requirement is fully
   satisfied either way. The approval-before-dispatch boundary stays INTACT: a valid
   receipt still exists before every enqueue, E1/E2 rechecks unchanged, B6 untouched.
5. **自律性・利便性・安全性への影響:** Autonomy ↑↑ (in-scope jobs never stall on a human;
   expiry/re-issue is automatic); usability ↑ (one admin policy surface, no approval
   queue for routine work); safety unchanged — scope is still admin-controlled
   (HBR-002), every issuance is audited (B7), and anything outside scope fails closed
   to a human. B6/activation unapproved (⚠ SAFETY BOUNDARY — approval authority; design
   only).
6. **推奨案を採用した場合の制約:** Policy authorship becomes the security-relevant act:
   policy tables must stay admin-only writable with role-ceiling rules (E7) and every
   policy change must create a new immutable version (already in step-2 §2.1), making
   stale-policy rejection effective.
7. **Ownerが新たに決定する必要がある事項:** Select the class scheme (this recommendation);
   define what counts as the exception/first-scope class (candidate definition in 4)
   and whether any class is always human-approved.

🚫初期設計反 — none (the queue framing "approval required" is ADR-0012-mandated and kept).
⚠根拠不足制約 — per-job human approval as the *general* class (ungrounded, autonomy-
obstructing). 📈過剰設計疑 — none.

## DP-006 — Approver ≠ actor (no self-approval)

1. **初期設計要件IDと原典:** HBR-013; PH2-A-03 (grantor = project owner OR organization
   administrator; authority is issuer-verified, not asserted). Source: ADR-0013 §2
   (proposed fail-closed default approver ≠ actor); ADR-0012 §4.1 ("approver identity
   is recorded, never self-asserted by actor"); PRODUCT_SPEC personal workspace model;
   hybrid 要件1 (Desktop Runner personal workspaces).
2. **当初想定されていた動作:** Approver authority is verified by the issuer against the
   existing authority model; a receipt records the approving principal.
3. **現在提示されている選択肢:** Approver ≠ actor required, or not; fail-closed default
   proposed as approver ≠ actor.
4. **初期設計に最も整合する推奨案:** Keep the fail-closed default **approver ≠ actor for
   delegated/administered contexts** (actor acting under a delegation grant or below
   workspace-owner authority). Owner decision needed for the personal-workspace class:
   where the actor *is* the workspace owner with sole grantor-class authority
   (hybrid 要件1 personal workspace on a Desktop Runner), requiring a distinct second
   principal has no grounding in the initial design and would make every personal-
   workspace job stall on another person — contrary to owner priority 3 (admin control
   vs personal-workspace flexibility). An issuer-verified workspace-owner self-approval
   is not a "self-assertion" under ADR-0012 §4.1: the issuer checks and records the
   authority; the actor cannot claim it.
5. **自律性・利便性・安全性への影響:** With the carve-out, personal-workspace autonomy is
   preserved and administered scopes keep separation-of-duties; without it, personal
   workspaces are unusable autonomously (autonomy ↓, no safety gain — the same
   authority already controls the policy). B6/activation unapproved (⚠ SAFETY BOUNDARY
   — approval separation; design only).
6. **推奨案を採用した場合の制約:** The carve-out is bounded by the DP-016 authority check;
   loss of owner authority falls under DP-017/018 fail-closed handling.
7. **Ownerが新たに決定する必要がある事項:** Decide the personal-workspace
   (actor = sole workspace owner) carve-out; keep approver ≠ actor everywhere else.

🚫初期設計反 — none. ⚠根拠不足制約 — an unconditional approver ≠ actor rule for personal
workspaces (no initial-design grounding; conflicts with priority 3). 📈過剰設計疑 — none.

## DP-007 — Issuer trust root and verification / key custody at E1 and E2

1. **初期設計要件IDと原典:** HBR-007 (authenticated runner transport), HBR-013, HBR-010
   (B4/B5). Source: ADR-0013 §2/§3 (issuer alone writes receipts; approver identity
   recorded); step-2 §2.6; ADR-0012 B4 (versioned transport), B5 (runner identity is a
   separate, owner-decided trust root — group B DP-035/036, not re-decided here).
2. **当初想定されていた動作:** Cross-plane trust rides the versioned `runner_contract/`
   transport with authenticated runner identity; the issuer's signing key lives with
   the issuer inside the Control Plane (B1 placement, DP-004).
3. **現在提示されている選択肢:** Authority inside CP or external; trust/signing
   arrangement open.
4. **初期設計に最も整合する推奨案:** 初期設計では未規定 → 最小構成推奨: single CP-internal
   issuer key (created with the issuer module, protected at rest like other
   Control-Plane secrets); E1 verifies issuer-signed receipts directly; E2 verifies
   via the authenticated online check over the versioned transport (DP-002), so the
   Runner needs no copy of the receipt trust root — its transport identity is the
   already-separate B5 trust-root decision owned by group B. No external authority.
5. **自律性・利便性・安全性への影響:** One key, one custody surface — minimal operational
   burden; safety equivalent to the mandatory properties (authenticity, non-repudiable
   audit artifact, E2 independence). B6/activation unapproved (⚠ SAFETY BOUNDARY —
   trust root and signing authority; design only).
6. **推奨案を採用した場合の制約:** Key rotation/compromise procedures must be defined
   before activation; runner-side offline verification is intentionally not supported
   (DP-002 constraint).
7. **Ownerが新たに決定する必要がある事項:** Ratify the single-issuer-key arrangement;
   runner identity trust (DP-035/036) remains a separate group-B decision.

🚫初期設計反 — none. ⚠根拠不足制約 — none. 📈過剰設計疑 — a full PKI solely for receipts
would exceed the initial design (runner PKI is group B's separate question).

## DP-008 — Live-revocation mechanism at E1 and E2

1. **初期設計要件IDと原典:** HBR-013; HBR-011 (fail-closed). Source: ADR-0012 §4.1
   (revocation ⇒ reject before enqueue/execution); step-2 §2.6/E1/E2 (revocation
   resolvable at both points, unavailable authority ⇒ reject); ADR-0013 §3 mandatory
   property: revocation must be visible at the *next enforcement point*.
2. **当初想定されていた動作:** Revocation is an immutable audited event; both enforcement
   points resolve current revocation state immediately before their action; a
   revocation between enqueue and execution is visible to E2 (the canonical regression
   test, step-2 §6.11).
3. **現在提示されている選択肢:** (a) online authority check; (b) signed revocation lists /
   short-lived receipts; (c) hybrid online check with bounded negative cache + absolute TTL.
4. **初期設計に最も整合する推奨案:** (a) online authority check at both E1 and E2 over the
   versioned transport; unavailable authority ⇒ reject (mandatory). Candidate (b) is
   NOT recommended — see F5 (AUD-P3-CONSISTENCY, MEDIUM, deferred to owner): a cached
   signed revocation list cannot make a post-refresh revocation "visible to the next
   enforcement point", so (b) as worded contradicts ADR-0013's own mandatory property
   and the step-2/HYB-A2 online-check envelope requirement. (c) only if the owner
   explicitly accepts a nonzero staleness bound (DP-009) — the default recommendation
   has no cache to bound.
5. **自律性・利便性・安全性への影響:** Online checking is the strongest-freshness option and
   also the *simplest* (no list distribution, no cache-invalidation protocol);
   fail-closed unavailability means an offline Runner cannot execute (mandatory, not an
   autonomy choice). B6/activation unapproved (⚠ SAFETY BOUNDARY — revocation; design
   only).
6. **推奨案を採用した場合の制約:** Execution couples to Control-Plane reachability at E2
   (already implied by the mandatory property and E2 independence); an offline execution
   mode would be a new owner decision (and a weaker one).
7. **Ownerが新たに決定する必要がある事項:** Select (a) (or explicitly accept (c)'s bounded
   staleness); note F5 for the record when rejecting (b).

🚫初期設計反 — candidate (b) as worded (contradicts the mandatory next-enforcement-point
property and the step-2 online-check requirement). ⚠根拠不足制約 — none.
📈過剰設計疑 — none (that is why (a) is recommended over (c)).

## DP-009 — Revocation-staleness bound; negative-cache permission

1. **初期設計要件IDと原典:** Same as DP-008; PH2-A-12 (resolved analogue: revocation
   denies at the next authorization point; no stronger synchronous interruption is
   promised). Source: ADR-0013 §3; step-2 §2.6.
2. **当初想定されていた動作:** The staleness question exists only if a cache exists; the
   initial design's precedent (delegation) resolves revocation live at each
   authorization point with zero staleness.
3. **現在提示されている選択肢:** Staleness bound open; negative-cache/hybrid permission open.
4. **初期設計に最も整合する推奨案:** 初期設計では未規定 → 最小構成推奨: with DP-008 (a), the
   staleness bound is **zero at the enforcement point** (checked immediately before
   enqueue and execution); no negative cache in the default configuration. A bounded
   cache is permitted only if the owner later accepts a nonzero bound — that would be a
   deliberate weakening decision, not a default.
5. **自律性・利便性・安全性への影響:** Zero-staleness costs one lookup per enforcement point
   (negligible; issuance is already a CP round-trip); a cache would buy performance the
   initial design never asked for at the price of the mandatory property. B6/activation
   unapproved (⚠ SAFETY BOUNDARY — revocation freshness; design only).
6. **推奨案を採用した場合の制約:** Throughput at E2 is bounded by issuer availability;
   mitigations (read replicas etc.) are later performance work, not safety decisions.
7. **Ownerが新たに決定する必要がある事項:** None under the recommendation; only if a cache
   is later wanted does the owner set the bound.

🚫初期設計反 — none. ⚠根拠不足制約 — an unbounded/unevidenced staleness tolerance would be
ungrounded. 📈過剰設計疑 — negative caching in the default configuration.

## DP-010 — Default job-receipt TTL

1. **初期設計要件IDと原典:** HBR-013; HBR-014 (deadlines owner-decided). Source:
   ADR-0013 §7 (no value supplied; delegation TTL cited for orientation only);
   PH2-A-01 (RESOLVED: delegation TTL 15 min min / 24 h default / 7 days max).
2. **当初想定されていた動作:** A receipt authorizes ONE job (ADR-0013 §1); expiry is a
   mandatory field; the delegation TTL is the only owner-resolved time-bound precedent.
3. **現在提示されている選択肢:** No value supplied by the source.
4. **初期設計に最も整合する推奨案:** 初期設計では未規定 → 最小構成推奨: default TTL = **24 h**,
   reusing the owner-resolved delegation default (PH2-A-01) so Locus has one coherent
   time-bound surface instead of two invented numbers. With DP-005 policy-driven
   issuance, expiry costs no autonomy: an expired in-scope job is automatically
   re-issued and re-enqueued, with the expiry itself audited.
5. **自律性・利便性・安全性への影響:** 24 h comfortably covers enqueue→execution plus retries
   without multi-day authorization drift (safety ↑ vs no-TTL; autonomy neutral because
   re-issuance is automatic). B6/activation unapproved (⚠ SAFETY BOUNDARY — approval
   lifetime; design only).
6. **推奨案を採用した場合の制約:** Jobs legitimately needing longer horizons (long offline
   Desktop sessions) need an explicit longer policy value within DP-011's max.
7. **Ownerが新たに決定する必要がある事項:** Ratify the default value (reuse rationale vs a
   different number).

🚫初期設計反 — none. ⚠根拠不足制約 — any number not anchored to the resolved delegation
bounds would be ungrounded. 📈過剰設計疑 — none.

## DP-011 — Maximum job-receipt TTL

1. **初期設計要件IDと原典 / 2. / 3.:** Same grounding as DP-010 (ADR-0013 §7; PH2-A-01).
   No value supplied by the source.
4. **初期設計に最も整合する推奨案:** 初期設計では未規定 → 最小構成推奨: maximum TTL = **7
   days**, reusing the owner-resolved delegation maximum (PH2-A-01) for coherence. Note
   the shorter-the-better property: because a receipt authorizes exactly one job and
   E2 rechecks revocation live (DP-008), a long max TTL does not materially weaken
   revocation — it only bounds how stale an *unused* approval may linger.
5. **自律性・利便性・安全性への影響:** A bounded max prevents permanent pre-approvals from
   accreting (safety); per-job binding keeps the blast radius of any single receipt to
   one job regardless of TTL. B6/activation unapproved (⚠ SAFETY BOUNDARY — approval
   lifetime; design only).
6. **推奨案を採用した場合の制約:** Same as DP-010; policy values above the max are rejected
   at issuance.
7. **Ownerが新たに決定する必要がある事項:** Ratify the maximum (reuse rationale vs a
   different number).

🚫初期設計反 — none. ⚠根拠不足制約 — unanchored values. 📈過剰設計疑 — none.

## DP-012 — Absolute vs deadline-anchored expiry; grace period

1. **初期設計要件IDと原典:** HBR-013; HBR-014 (admission/deadline bounds owner-decided;
   mechanisms open). Source: ADR-0013 §5/§7 (proposed default: no grace);
   step-2 §2.1 (`deadline_seconds` currently CHECK-constrained to NULL in
   `backend/app/agents/registry.py`); PH2-A-01 (delegation expiry is wall-clock).
2. **当初想定されていた動作:** Expiry is a receipt field; the delegation precedent is plain
   wall-clock expiry; no job-deadline substrate exists yet.
3. **現在提示されている選択肢:** Absolute wall-clock vs job-deadline-anchored; grace open
   (source proposes none).
4. **初期設計に最も整合する推奨案:** Absolute wall-clock expiry (epoch seconds, PH2-A-08
   convention) and **no grace period**. Deadline anchoring is NOT recommended now: the
   deadline field it would anchor to is disabled (`deadline_seconds` NULL), so
   anchoring would build a mechanism on a nonexistent substrate — pure speculative
   complexity until HBR-014's owner decisions enable deadlines.
5. **自律性・利便性・安全性への影響:** No grace = simplest fail-closed semantics and matches
   the delegation precedent; with policy-driven re-issuance (DP-005) expiry does not
   strand autonomous work. B6/activation unapproved (⚠ SAFETY BOUNDARY — approval
   freshness; design only).
6. **推奨案を採用した場合の制約:** If job deadlines are later enabled (HBR-014), expiry
   anchoring can be revisited as an additive option.
7. **Ownerが新たに決定する必要がある事項:** Ratify absolute + no grace; revisit only if
   deadlines are enabled.

🚫初期設計反 — none. ⚠根拠不足制約 — deadline-anchored expiry before any deadline
substrate exists. 📈過剰設計疑 — deadline anchoring now; grace periods.

## DP-013 — Timestamp authority for issuance/expiry

1. **初期設計要件IDと原典:** HBR-013; PH2-A-08 (RESOLVED: epoch-seconds time authority via
   `_delegation_now` until the production-DB/clock decision; production clock policy
   remains open and is NOT re-decided here). Source: ADR-0013 §7 (delegation clock
   cited as context only).
2. **当初想定されていた動作:** One Control-Plane clock convention already exists and was
   owner-resolved for delegation.
3. **現在提示されている選択肢:** Timestamp authority open.
4. **初期設計に最も整合する推奨案:** Reuse the resolved delegation convention (Control-Plane
   epoch seconds) for receipt issuance/expiry. No new timestamp infrastructure; the
   production clock decision (already open in the register) applies to both when made.
5. **自律性・利便性・安全性への影響:** Consistency avoids a second clock authority and the
   skew/verification bugs it invites. B6/activation unapproved (⚠ SAFETY BOUNDARY —
   expiry verification; design only).
6. **推奨案を採用した場合の制約:** Receipts inherit the same prototype-time-authority
   limitation as delegation; both move together at the production-DB decision.
7. **Ownerが新たに決定する必要がある事項:** None new — the production clock question is
   already open in the register and governs both mechanisms.

🚫初期設計反 — none. ⚠根拠不足制約 — none. 📈過剰設計疑 — a separate receipt-dedicated time
authority.

## DP-014 — Clock-skew tolerance between Control Plane and Runner

1. **初期設計要件IDと原典:** HBR-013; HBR-011 (fail-closed discipline). Source: ADR-0013 §7
   (proposed fail-closed default: zero tolerance until selected).
2. **当初想定されていた動作:** With online verification (DP-002/008), expiry math is
   performed against the authority's own clock; cross-plane skew matters only for
   transport-level freshness windows, which the runner trust decisions (group B,
   DP-046) own.
3. **現在提示されている選択肢:** Tolerance open.
4. **初期設計に最も整合する推奨案:** Keep the fail-closed zero-tolerance default for
   receipt expiry. Any nonzero tolerance is an ungrounded weakening until a measured
   need exists; receipt skew questions largely dissolve under the online-check
   recommendation.
5. **自律性・利便性・安全性への影響:** Zero tolerance is fail-closed (priority 6); no
   autonomy cost because the authority, not the Runner, computes expiry. B6/activation
   unapproved (⚠ SAFETY BOUNDARY — freshness verification; design only).
6. **推奨案を採用した場合の制約:** None beyond DP-002's online dependence.
7. **Ownerが新たに決定する必要がある事項:** Ratify zero tolerance; any future tolerance
   needs its own evidence-backed decision.

🚫初期設計反 — none. ⚠根拠不足制約 — any nonzero tolerance today. 📈過剰設計疑 — none.

## DP-015 — Delegation grant: prerequisite vs additional input

1. **初期設計要件IDと原典:** IAM-011 (delegated administration bounded, audited,
   non-escalating), IAM-013 (membership independent from grants — owner-approved
   invariant), PH2-A-10 (RESOLVED: membership remains an independent gate). Source:
   ADR-0013 §6 ("actor authorization is live-checked; delegation cannot be inferred
   from the receipt"; "the grant itself is not the receipt"); ADR-0012 §4.1 (live
   recheck of actor authorization).
2. **当初想定されていた動作:** Actor authorization is computed live from membership +
   role + (optionally) delegation at every authorization point; delegation never
   substitutes for membership or confers standing by itself.
3. **現在提示されている選択肢:** Prerequisite or additional input.
4. **初期設計に最も整合する推奨案:** **Additional input only.** Making a delegation grant a
   prerequisite would contradict the approved invariant that membership/ownership
   authorization is independent of grants (IAM-013/PH2-A-10): workspace members acting
   on their own membership would be unable to obtain receipts without a grant. A
   grant is one live-checked input to the actor-authorization computation that the
   issuer (and E1/E2) performs; the receipt binds the actor's identity, never a
   permission set.
5. **自律性・利便性・安全性への影響:** Additional-input keeps both the delegation feature and
   ordinary member autonomy intact; live rechecking keeps revocation effective
   (priority 6). B6/activation unapproved (⚠ SAFETY BOUNDARY — actor authorization;
   design only).
6. **推奨案を採用した場合の制約:** Receipt issuance must invoke the same live
   actor-authorization function used elsewhere (single source of truth), so delegation
   lifecycle changes are automatically reflected.
7. **Ownerが新たに決定する必要がある事項:** Ratify "additional input only".

🚫初期設計反 — the "prerequisite" option (contradicts IAM-013 / PH2-A-10).
⚠根拠不足制約 — none. 📈過剰設計疑 — none.

## DP-016 — Approver authority verification mechanism

1. **初期設計要件IDと原典:** IAM-010/IAM-011 (role model + ceilings), PH2-A-03 (RESOLVED
   grantor rule), PH2-A-09 (admin permissions non-delegable). Source: ADR-0013 §6
   (grantor rule proposed as baseline); ADR-0012 §4.1 (issuer-verified authority).
2. **当初想定されていた動作:** Authority over a project/workspace is already computed by
   the existing role/membership model; the grantor rule (project owner or org admin on
   the target project) was owner-resolved for delegation and is the natural approver
   baseline.
3. **現在提示されている選択肢:** Existing role model; dedicated approver registry; or both.
4. **初期設計に最も整合する推奨案:** **Existing role model with the grantor rule** — reuse
   the resolved grantor-authority computation; no dedicated approver registry. A
   separate registry is a new authority construct the initial design does not contain
   (it would create a second source of truth that can diverge from the role model).
   An *optional* approver allowlist per workspace could later narrow (never widen)
   authority if the owner wants tighter control — additive, fail-closed, owner-gated.
5. **自律性・利便性・安全性への影響:** Reuse keeps one authority computation (safety ↑,
   maintenance ↓); personal-workspace owners and org admins are both handled by the
   resolved rule (priority 3). B6/activation unapproved (⚠ SAFETY BOUNDARY — approval
   authority; design only).
6. **推奨案を採用した場合の制約:** Approver authority moves when roles/memberships move —
   which is exactly what DP-017/018 fail-closed handling covers.
7. **Ownerが新たに決定する必要がある事項:** Ratify role-model reuse; decide later whether
   any narrowing allowlist is wanted (not needed for 2b design).

🚫初期設計反 — none. ⚠根拠不足制約 — a dedicated approver registry as a requirement.
📈過剰設計疑 — the registry (dual-source-of-truth complexity).

## DP-017 — Issued receipt when approver authority is lost before enqueue

1. **初期設計要件IDと原典:** PH2-A-05 (RESOLVED: live fail-closed invalidation on grantor
   authority loss); DATA-005 (invalidation propagates before later access — the same
   discipline family). Source: ADR-0013 §6 (fail-closed invalidation is a stated
   requirement; exact handling open); delegation triggers in
   `backend/app/service.py` (`delegation_grantor_membership_delete` /
   `delegation_grantor_role_update`).
2. **当初想定されていた動作:** Authority loss emits an immutable invalidation event; the
   next authorization point fails closed. The receipt must behave like the grant.
3. **現在提示されている選択肢:** Exact handling open; fail-closed invalidation proposed.
4. **初期設計に最も整合する推奨案:** Mirror the delegation pattern exactly: approver
   authority loss (role change, membership removal, account disable) emits an
   immutable receipt-invalidation event; E1 then rejects enqueue. No discretionary
   handling.
5. **自律性・利便性・安全性への影響:** Fail-closed (priority 6); autonomy cost is minimal
   because policy-driven issuance (DP-005) re-approves in-scope work under the new
   authority holder automatically. B6/activation unapproved (⚠ SAFETY BOUNDARY —
   approval authority revocation; design only).
6. **推奨案を採用した場合の制約:** The authority-loss event source must be shared with the
   delegation triggers so one role/membership change invalidates both grant and
   receipts consistently.
7. **Ownerが新たに決定する必要がある事項:** None — the fail-closed pattern is effectively
   mandated; only implementation detail remains.

🚫初期設計反 — none. ⚠根拠不足制約 — none. 📈過剰設計疑 — none.

## DP-018 — Does approver-authority loss revoke already-enqueued jobs at E2?

1. **初期設計要件IDと原典:** Same as DP-017, plus E2's mandatory independent recheck of
   receipt/revocation state (step-2 §2.6/E2; ADR-0012 §4.1) and PH2-A-12 (resolved
   next-authorization-point semantics). Source: ADR-0013 §6 (open).
2. **当初想定されていた動作:** E2 live-rechecks the same receipt's revocation state before
   execution; the delegation analogue invalidates the grant at the next authorization
   point, including for in-flight usage.
3. **現在提示されている選択肢:** Revoke queued jobs at E2; or bar new issuance only.
4. **初期設計に最も整合する推奨案:** **Revoke queued jobs at E2** — i.e., approver-authority
   loss emits the same invalidation/revocation event as DP-017, which E2's mandatory
   live recheck then observes. "Bar new issuance only" would require E2 NOT to see the
   invalidation, diverging from the delegation precedent (PH2-A-05/12) and from the
   uniform fail-closed rule that every authority invalidation is visible at the next
   enforcement point. Admin/personal separation stays coherent: org-admin and
   workspace-owner authority losses behave identically.
5. **自律性・利便性・安全性への影響:** Uniform revocation semantics = predictable and safe;
   autonomy cost is bounded because re-issuance under the surviving/new authority is
   automatic (DP-005). B6/activation unapproved (⚠ SAFETY BOUNDARY — queued-job
   authorization; design only).
6. **推奨案を採用した場合の制約:** Enqueued-but-not-started work may be canceled by an
   authority change; HBR-014 cancellation semantics then govern capacity release.
7. **Ownerが新たに決定する必要がある事項:** Ratify E2 revocation (vs the narrower option).

🚫初期設計反 — none. ⚠根拠不足制約 — "bar new issuance only" (weaker than the delegation
fail-closed precedent it mirrors). 📈過剰設計疑 — none.

## DP-019 — Error taxonomy and status codes for receipt rejection

1. **初期設計要件IDと原典:** HBR-011 (existing explicit 409 dispatch rejection), HBR-013.
   Source: ADR-0013 §4 (taxonomy/codes open; rejection and audit mandatory); step-2
   §6.11 (regression-test naming).
2. **当初想定されていた動作:** The Control Plane already rejects dispatch with an explicit
   409 + audited `agent.dispatch.reject`; receipt rejections extend this convention.
3. **現在提示されている選択肢:** Exact taxonomy/codes open.
4. **初期設計に最も整合する推奨案:** 初期設計では未規定 → 最小構成推奨: a small closed
   rejection-reason enum in the versioned `runner_contract/` DTOs (B4; unknown values
   fail closed), mapped onto existing API conventions (boundary/gate conflicts → 409
   like B6; authorization denial → 403; revoked/expired → 410/404-class); every
   rejection audited (B7). No new HTTP semantics.
5. **自律性・利便性・安全性への影響:** Machine-readable reasons let policy-driven issuance
   (DP-005) distinguish "re-request after re-approval" from "hard denial" — directly
   supports autonomy; safety unchanged. Non-boundary row.
6. **推奨案を採用した場合の制約:** Enum values are part of the versioned contract; adding
   values is a contract-version change (B4), not an in-place edit.
7. **Ownerが新たに決定する必要がある事項:** None beyond ratifying the enum-in-contract
   approach; exact codes are design detail for 2b.

🚫初期設計反 — none. ⚠根拠不足制約 — none. 📈過剰設計疑 — an elaborate error hierarchy.

## DP-020 — Audit operation names for receipt lifecycle events

1. **初期設計要件IDと原典:** HBR-006 (agent invocation audit), IAM-015 (metadata-only
   audit). Source: ADR-0012 B7; ADR-0013 §8 (proposed shape `agent.receipt.*`);
   existing `agent.*` operations in `backend/app/agents/registry.py`.
2. **当初想定されていた動作:** Plane-R events are attributed (actor, workspace,
   destination, model, authorization decision) through the Control-Plane audit path
   using the existing `agent.*` naming convention.
3. **現在提示されている選択肢:** Naming open; shape proposed.
4. **初期設計に最も整合する推奨案:** Adopt `agent.receipt.*` (e.g.
   `agent.receipt.issue`, `.deny`, `.recheck_enqueue`, `.recheck_execute`, `.revoke`,
   `.expiry_reject`) — it matches the existing convention exactly and needs no new
   audit machinery.
5. **自律性・利便性・安全性への影響:** Full lifecycle attribution (priority 6/B7); no
   friction. Non-boundary row.
6. **推奨案を採用した場合の制約:** Event names join the audit contract; renames later are
   additive aliases, not history rewrites.
7. **Ownerが新たに決定する必要がある事項:** Ratify the naming shape.

🚫初期設計反 — none. ⚠根拠不足制約 — none. 📈過剰設計疑 — none.

## DP-021 — New approval permission (e.g. `approve_jobs`) and ceiling

1. **初期設計要件IDと原典:** IAM-010/IAM-011 (role templates, ceilings, no invented
   backend privileges), PH2-A-03/09 (grantor rule; admin permissions non-delegable).
   Source: ADR-0013 §8 (no new permission without owner approval; existing role-ceiling
   rules remain mandatory); ADR-0012 §4/E7.
2. **当初想定されていた動作:** PRODUCT_SPEC: administrators configure roles only within
   their own delegable permissions and cannot invent new backend privileges; approval
   authority in the initial design derives from project/workspace authority (grantor
   rule), not from a dedicated permission bit.
3. **現在提示されている選択肢:** Add a new permission or not; ceiling treatment open.
4. **初期設計に最も整合する推奨案:** **No new permission.** Approval authority = existing
   grantor-class authority (DP-016); it is administrative in nature and therefore
   non-delegable (PH2-A-09) and outside the `NON_ADMIN` ceiling by construction. A new
   `approve_jobs` permission would be a new backend privilege beyond the initial
   design (flagged) — it adds an entire permission-lifecycle surface (grant, ceiling,
   audit, UI) for no capability the initial design requires.
5. **自律性・利便性・安全性への影響:** Reuse avoids permission sprawl and the escalation
   surface it creates (priority 6); personal-workspace owners and org admins already
   satisfy the grantor rule (priority 3). B6/activation unapproved (⚠ SAFETY BOUNDARY —
   permission/authority change; design only).
6. **推奨案を採用した場合の制約:** If finer-grained approval control is ever wanted, it
   arrives as an additive owner decision (new permission + ceiling treatment), not by
   reinterpreting this one.
7. **Ownerが新たに決定する必要がある事項:** Ratify "no new permission"; only if the owner
   explicitly wants finer granularity does the permission question return.

🚫初期設計反 — none. ⚠根拠不足制約 — a new permission as a *requirement* (initial design
derives approval authority from the grantor rule). 📈過剰設計疑 — the new-permission
surface for equivalent capability.

## DP-022 — Receipt / audit retention period (PH2-A-11 alignment)

1. **初期設計要件IDと原典:** IAM-016 (audit protection/retention — owner decision open),
   DATA-015 (retention owner-decided, none assumed). Source: ADR-0013 §8 (follow
   PH2-A-11 outcome); PH2-A-11 (RESOLVED: grant versions + audit entries retained
   until the production-deployment phase decision; no production period implied).
2. **当初想定されていた動作:** Immutable records retained under the same discipline as the
   delegation model until the already-open production retention decision.
3. **現在提示されている選択肢:** Period open.
4. **初期設計に最も整合する推奨案:** Mirror PH2-A-11 exactly: receipts, invalidation/audit
   events retained (immutable) until the production-deployment retention decision; no
   period selected here, no separate retention scheme for receipts.
5. **自律性・利便性・安全性への影響:** One retention decision covers delegation + receipts
   (no fragmentation); safety preserved via immutability; the production retention
   gate (IAM-016/DATA-015/DP-068/069) remains open and is not re-decided. B6/
   activation unapproved (⚠ SAFETY BOUNDARY — sensitive audit retention; design only).
6. **推奨案を採用した場合の制約:** Receipt rows grow until the production decision; storage
   impact is bounded by per-job issuance volume and is the same class of growth as
   delegation events.
7. **Ownerが新たに決定する必要がある事項:** None new — the production retention decision is
   already open in the register; receipts ride it.

🚫初期設計反 — none. ⚠根拠不足制約 — inventing a receipt-specific period now.
📈過剰設計疑 — none.

## DP-023 — Receipt redaction requirements

1. **初期設計要件IDと原典:** IAM-015 (metadata-only audit — no secrets/content/payloads),
   HBR-005 (credentials stay on user device; never repurposed). Source: ADR-0012 B2 +
   §8 (receipt material must never contain credential bytes;
   `adapter_credentials` presence-only precedent); ADR-0013 §8.
2. **当初想定されていた動作:** Registry/audit state is metadata-only; credential material
   never enters Locus-controlled records.
3. **現在提示されている選択肢:** Redaction requirements open; no credential bytes in receipt
   material (mandatory).
4. **初期設計に最も整合する推奨案:** 初期設計では未規定 → 最小構成推奨: receipts carry
   metadata only — IDs, principal references (non-secret), workspace/policy/adapter/
   destination/operation identifiers, timestamps, version, decision — never
   credentials, document/chat content, policy secrets or ACL payloads. Then redaction
   reduces to the existing metadata-only audit rule (IAM-015): nothing sensitive
   present ⇒ nothing to redact. A static/schema-level test (presence-only analogue)
   enforces this.
5. **自律性・利便性・安全性への影響:** Metadata-only receipts are also the autonomy-friendly
   shape (no content entanglement to redact per future feature); safety = B2/IAM-015
   unchanged. B6/activation unapproved (⚠ SAFETY BOUNDARY — credentials and audit
   data; design only).
6. **推奨案を採用した場合の制約:** Future fields must remain metadata-class; any field that
   would embed content requires a new owner decision and redaction design.
7. **Ownerが新たに決定する必要がある事項:** Ratify metadata-only receipt content; no
   separate redaction policy needed under it.

🚫初期設計反 — none. ⚠根拠不足制約 — none. 📈過剰設計疑 — a content-bearing receipt design
that then needs a redaction pipeline.

---

## Summary of flags

| Item | 🚫初期設計反 | ⚠根拠不足制約 | 📈過剰設計疑 |
|---|---|---|---|
| DP-001 | — | option (i) as requirement | option (i) |
| DP-002 | — | — | bespoke runner-side sig/canon stack |
| DP-003 | — | — | dedicated receipt store |
| DP-004 | — | (b)/(c) as rival architectures | — |
| DP-005 | — | per-job-human for ALL jobs | — |
| DP-006 | — | unconditional approver≠actor for personal workspaces | — |
| DP-007 | — | — | receipt-only PKI |
| DP-008 | candidate (b) as worded (F5) | — | — |
| DP-009 | — | unevidenced staleness tolerance | default negative cache |
| DP-010 | — | unanchored values | — |
| DP-011 | — | unanchored values | — |
| DP-012 | — | deadline anchoring pre-substrate | anchoring now; grace |
| DP-013 | — | — | separate time authority |
| DP-014 | — | nonzero tolerance today | — |
| DP-015 | prerequisite framing | — | — |
| DP-016 | — | approver registry as requirement | approver registry |
| DP-017 | — | — | — |
| DP-018 | — | bar-new-issuance-only | — |
| DP-019 | — | — | elaborate error hierarchy |
| DP-020 | — | — | — |
| DP-021 | — | new permission as requirement | new-permission surface |
| DP-022 | — | receipt-specific period now | — |
| DP-023 | — | — | content-bearing receipts |

## Self-review record (adversarial)

- Checked every recommendation against the guardrails: none activates dispatch, lifts
  B6, enables egress/isolation/credentials/production exposure; ADR-0012 §4.1 E1/E2
  rechecks and all step-2 §6.11 test obligations are preserved verbatim in DP-002/005/
  008/018.
- Checked no approved decision is re-opened: PH2-A-01…12 are reused as grounding only;
  the production-DB/clock/retention questions (DP-066/068/069, PH2-A-08/11) are
  explicitly inherited, not re-decided.
- Checked F5 handling: noted at DP-008 as owner-deferred input; ADR-0013 not edited;
  candidate (b) flagged via the mandatory-property conflict, not "re-labeled" here.
- Checked the Agent Adapter constraint: no recommendation places receipt logic inside
  adapters/CLIs (cross-cutting verdict 3); the adapter interface stays B3's
  `run_job(job, workspace_policy)`.
- Checked completeness: all 23 items present, each with all 7 fields + flag line; per-item
  line counts kept within the grounding pack's ≤12-line target (summary table used
  where options needed tabulation).
- Known limitation: the personal-workspace self-approval carve-out (DP-006) is a
  *policy-shaping* recommendation on a safety-boundary row; it is explicitly left as an
  owner decision rather than recommended as settled, per the grounding pack's rule
  that this file produces a recommendation layer only.
