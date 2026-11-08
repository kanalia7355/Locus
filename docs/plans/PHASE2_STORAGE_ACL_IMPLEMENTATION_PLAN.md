# PHASE2_STORAGE_ACL_IMPLEMENTATION_PLAN — 元保存先ACL対応 実装計画 (proposal only)

Status: **implementation plan proposal; documentation only.** This plan extends the
recommended interpretation in `docs/plans/PHASE2_STORAGE_ACL_RESEARCH.md` (PH2-C
research, integrated `0e06107`): **source-location authorization (A) plus lifecycle
propagation (A2)** as the core of D5 (元保存先ACL対応), with all existing Locus ACLs
preserved as independent gates and any external egress remaining explicitly
owner-gated. Nothing in this plan approves a connector, credential, network path or
schema change; every undecided point is listed as 【要決定】 in §7 and implementation
of any slice is gated on the owner answers recorded there. No code is changed by
this document and no behavior is activated.

Primary assignment: `docs/plans/agent-work/PH2-C2-storage-acl-plan.md` (PH2-C2,
docs-only). Parent research: `docs/plans/PHASE2_STORAGE_ACL_RESEARCH.md`.
D5 context: `docs/plans/PHASE2_JOB_BREAKDOWN.md` ("PH2-C — 元保存先ACL対応
research + design", D5 row).

---

## 1. Current-state baseline (verified against integrated HEAD `951c3cf`)

All claims below were read from the actual code at the worktree HEAD this plan was
drafted at (`loop/local-development` @ `951c3cf`). Line numbers are indicative and
may shift; function/schema names are the stable citations.

### 1.1 Storage and ingestion today

- `backend/app/service.py` `Store` schema (CREATE TABLE block at ~385–427):
  `documents(id, owner_id, project_id, kind, name, content, status, reason,
  conversation_id, grants, created)` stores the **full extracted text** in SQLite;
  `chunks(id, document_id …, page, ordinal, text)` stores derived text with
  `ON DELETE CASCADE`. There is **no** source identity, source path/object ID,
  source revision, source ACL snapshot, connector credential or source lifecycle
  column anywhere in the schema. This matches research §2 finding 2.
- `Service.upload` (~1944): bounded per-user upload (UTF-8 txt/md/csv, 256 KiB,
  filename validation, per-user/global queue and total caps 429s), inserts a
  `queued` document and audits `document.upload`. New uploads are only
  `personal` or `attachment` (`kind not in {"personal","attachment"}` → 422);
  `shared` status is reachable only via `Service.publish`. No source concept.
- `Service._ingestion_allowed` + `Service.process_next` (~2009–2055): the
  **two-check pattern** — permission recheck before content is exposed to the
  scanner adapter, and recheck again after the out-of-transaction scan before
  indexing; stale work after revoke/delete/cancel is never published. Scanner
  failure or disapproval → `quarantined` (fail-closed). This pattern is the
  template any source-ACL recheck must slot into (research §4 enforcement point 2).
- `backend/app/scanner.py` (63 lines) + `docs/INGESTION_SCANNER.md`: default
  fail-closed unavailable scanner; optional loopback ClamAV adapter, explicitly
  configured. The scanner is a content-safety check, **not** a source-identity or
  source-ACL check.
- `Service._index` (~2057): re-derives chunks from `documents.content`, sets
  `status='ready'`. `Store.recover_jobs` (~457) resets `scanning→queued` at worker
  startup — a lifecycle state machine already exists for Locus-internal states only.
- `Service.cancel` (~2102) / `Service.delete_document` (~2121): local-only
  cancel/delete of the Locus row (and cascaded chunks). Neither can detect or
  propagate an upstream source change/deletion (research §5 finding 3).
- `Service.seed_synthetic` (~2067): local CLI/test-only synthetic seed, not a
  connector; it does not create source bindings and must not be used as evidence
  of source support.

### 1.2 Document authorization today (the surface a source gate must join)

- `Service._can_read` (~1767) is the central document-level gate: project
  permission via `Service.require`/`Service._permissions` (~1155; PH2-B union of
  held roles, explicit deny wins, deny-by-default), owner-only access for
  `personal`/`attachment` (attachment additionally conversation-bound), and for
  `shared` documents a matching **current** role grant (`documents.grants`) for
  `read`/`retrieve`.
- `Service._document` (~1791) applies `_can_read` before returning any document;
  `Service.documents` (~1836) filters the list through `_can_read` (plus the
  owner-with-`upload` visibility of own shared rows).
- Every derived/consumption path re-runs `_can_read` live: `chunks` (~1858),
  `related` (~1874, double `retrieve`+`read` check per candidate),
  `_citations` (~2178, per citation at read time), `_generated` (~2197, hides the
  answer when any citation is no longer readable — `answer_hidden`), 
  `conversation` (~2210, attachments re-filtered live), `send` (~2254, retrieval
  candidates filtered by `_can_read` per document and attachment admission via
  `_document`). This is the property the research calls "the natural shared
  enforcement surface": a source gate added here is inherited by all data paths.
- `Service.publish` (~2127): publication restricted to same-project roles and
  `read`/`retrieve` operations; attachments cannot be published.
- `Service._audit` (~474): transaction-bound, metadata-only audit rows
  `(id, at, actor_id, operation, target_id, outcome)`; no document body, no
  credentials. Existing operations include `document.upload`, `document.delete`,
  `document.publish`, `ingestion.cancel`, `retrieval.complete` (see audit
  operation set in `service.py`).
- API surface: `backend/app/main.py` routes ~338–372 (`/api/documents`,
  `/api/documents/{document}` (+`/chunks`, `/related`, `/cancel`,
  `/publication`, DELETE)) and `/api/admin/storage` (~516).
- Admin UI: `frontend/src/AdminSettings.tsx` `AdminStorage` (~523) is a
  **read-only** status view (backend, mode, external storage explicitly
  "無効（既定拒否）", formats, limits, ingestion status counts) reached from the
  system-admin `storage` nav entry (`frontend/src/App.tsx` ~43, ~893, ~1264).
  It states plainly that connection settings do not exist. It is not a connector
  and grants nothing (research §2/§5 finding 1).

---

## 2. Design principles for the implementation plan

1. **Additive second gate, never a replacement** (research §3 recommendation, §4.3):
   a source gate joins `Service._can_read` as an additional fail-closed condition.
   A source grant can never bypass project membership, explicit deny
   (`_permissions`), publication grants, personal ownership or attachment
   conversation binding. Interpretation E (source ACL as sole ACL) is rejected.
2. **Fail closed on the unknown.** When source state is stale, unverifiable, or
   the source adapter is unavailable, source-derived content is hidden, not
   served. A failed sync is never proof of authorization (research §3 A2 row).
3. **No egress by default.** Local-only mode stays no-egress
   (`docs/architecture/ARCHITECTURE.md` deployment row). Any network source
   (NAS, Drive) is a separate, explicitly owner-approved connector workstream
   (research §3 B, §4.6). Source read permission never implies consent to send
   content to an external model (research §6 item 12).
4. **Reuse existing conventions only** (per task brief): additive SQLite
   migrations via the `Store._ensure_column` / `CREATE TABLE IF NOT EXISTS`
   pattern (~420–445), the `process_next` two-check pattern, `_audit`
   metadata-only rows, HTTP `fail()` JSON errors, and the live-recheck property
   already proven by `test_concurrent_roles.py` / `test_delegations.py`.
5. **Phased behind owner answers.** Each slice below names the 【要決定】 items
   that must be answered before it can start. No slice is scheduled without them.

---

## 3. Phased implementation slices

Ordering follows research §7: data model → shared enforcement → lifecycle →
audit → UI, with the connector/egress boundary as an owner-gated prerequisite
throughout. Slices are vertical and independently testable; none starts before
its listed 【要決定】 inputs exist.

### Slice 0 — Prerequisites (owner decision gate, no code)

- Owner answers the 【要決定】 items in §7 that gate Slices 1–3 (at minimum:
  D5 scope confirmation, first source types, permission model/freshness,
  combination rule, revoked/unavailable behavior, deletion semantics).
- Record a source-specific security/data-flow design and threat review per
  research §7 ("Before any connector implementation"). Keep all outbound access
  disabled at the deployment layer as well as the application layer
  (`docs/architecture/ARCHITECTURE.md`).
- Deliverable: owner-decision register entries (no code). The read-only
  `AdminStorage` view stays as-is; it must not imply connectivity.

### Slice 1 — Data model (backend only, additive)

Goal: represent source identity and source-authorization state without touching
existing columns' semantics, so current behavior is bit-identical when no source
binding exists.

- New tables (names provisional; logical sketch from research §4):
  - `storage_sources`: opaque ID, connector kind, admin scope, enabled state,
    non-secret configuration reference. No credentials in this table or any
    document metadata/audit row.
  - `source_objects`: source ID, stable opaque object ID, optional canonical
    locator, source revision/etag, last-observed state/time, ACL observation
    status/revision. Display names and mutable paths are never stable identity.
  - `document_source_bindings`: document ID ↔ source-object ID, imported
    revision, sync state. Cardinality (one document from multiple sources) is a
    【要決定】 item (§7 #8) — model it explicitly rather than assuming 1:1.
- Source-ACL representation: prefer a connector-specific live authorization
  adapter; if a snapshot is used it must be normalized, versioned and carry an
  explicit freshness/expiry (research §4 data-model sketch). Raw credentials are
  never stored; an import credential is never treated as an end-user grant.
- Existing `documents`/`chunks` rows gain derived-artifact linkage to the
  document/source revision so revocation can invalidate the whole dependency set
  (research §4 last bullet). Unbound documents (all current uploads) keep
  exactly today's behavior — this is the regression invariant of this slice.
- Migration style: additive `CREATE TABLE IF NOT EXISTS` + `Store._ensure_column`
  in the existing schema block; no column repurposing; legacy databases keep
  loading (pattern proven by `cancel_requested`/`denied_permissions` migrations).
- Touchpoints: `backend/app/service.py` (schema block, uid handling), new store
  helpers; `tests/test_api.py`-style schema tests.
- 【要決定】 gate: §7 #1, #2, #7, #8.

### Slice 2 — Enforcement points (shared authorization surface)

Goal: a source gate that every read path inherits, matching research §4
enforcement points 2–3.

- Add a source condition inside the shared surface (`_can_read` / `_document`
  equivalent in `service.py`), NOT as a UI- or route-only check:
  - `documents` list, `document` metadata, `chunks`, `related` (both the source
    and per-candidate checks), `_citations`, `_generated`/`conversation`
    (`answer_hidden` semantics must extend to source-denied citations),
    `send` retrieval candidates and attachment admission, and any future
    export/cache path. Anything that reaches content or derived text goes
    through the gate.
- Ingestion admission: extend `_ingestion_allowed` and `process_next`'s
  two-check pattern with source-permission and source-revision recheck before
  scanner exposure and again before `_index`. Revoked/deleted/moved/changed/
  unverifiable → do not index; land in a fail-closed state (quarantine-like)
  whose exact lifecycle contract is a 【要決定】 item (§7 #5).
- Combination semantics: source gate AND existing gates (intersection), per the
  research recommendation; owner confirms (§7 #4). Explicit deny still wins.
  Delegation must not infer source grants from delegated project rights
  (research §7 Phase 2 row).
- Linearization: define the authorization linearization point for source ACL
  changes concurrent with scan/retrieval/generation; never release content after
  a denial is observed (§7 #10).
- Touchpoints: `backend/app/service.py` (`_can_read`, `_document`,
  `documents`, `chunks`, `related`, `_citations`, `_generated`, `conversation`,
  `send`, `_ingestion_allowed`, `process_next`), `backend/app/main.py` only if
  new endpoints are approved; no frontend behavior change yet.
- 【要決定】 gate: §7 #3, #4, #5, #10.

### Slice 3 — Lifecycle propagation (A2)

Goal: source move/rename/delete/permission-revocation changes Locus visibility
and derived state, without stale resurrection.

- Invalidate visibility **first** (fail closed), then reconcile/delete/re-index
  content and derived artifacts (research §4 enforcement point 4). Chunk,
  retrieval, citation, generated-answer and cache invalidation flow from the
  document/source revision link created in Slice 1.
- Track source revision so a stale worker cannot restore superseded indexed data
  after a newer revoke/delete/change event (the same discipline as
  `process_next`'s out-of-transaction recheck).
- Event/polling model, stable identity across moves, freshness SLA, missed-event
  recovery and retry semantics are per-connector designs (§7 #3, #5, #10) —
  the slice defines the state machine and hooks, not the connector.
- Source deletion semantics (binding-only vs. Locus copies/derivatives vs.
  upstream request; who may initiate upstream deletion) are owner decisions
  (§7 #6). Read-only ingestion never assumes source-write permission.
- Original bytes (copy/link/fetch-on-demand) and retention/backup policy for
  originals, extracted text, chunks, embeddings, caches, answers and audit rows
  are owner decisions (§7 #7); access to stored originals is gated independently
  (research §4 enforcement point 5).
- Touchpoints: `backend/app/service.py` (worker loop, `delete_document`,
  `cancel`, new sync/refresh service methods), `Store.recover_jobs` extension for
  source-bound states; scanner flow untouched.
- 【要決定】 gate: §7 #3, #5, #6, #7, #8, #10.

### Slice 4 — Audit

Goal: preserve the transaction-bound, metadata-only convention while making
source authorization transitions auditable.

- New operation IDs in the `document.*`/`ingestion.*`/`source.*` family,
  e.g. source configuration change, scan/sync start, permission refresh/change,
  source move/delete, index publication/invalidation, and denied/unknown-source
  decisions (research §4 audit proposal). Same `(actor_id, operation, target_id,
  outcome)` shape via `Service._audit`; opaque IDs only.
- Never log: document content, source credentials, raw provider responses,
  sensitive filenames/paths, source ACL payloads (§7 #11 decides whether source
  identity itself is sensitive and audit retention/access rules).
- Atomicity: an audit failure for a state-changing authorization transition must
  not leave a success-looking state; exact semantics across connector calls and
  DB transactions need connector-specific design (research §4 audit proposal).
- Touchpoints: `backend/app/service.py` (`_audit` call sites), audit regression
  tests (`tests/test_audit_regressions.py`, `tests/test_administration_audit.py`).

### Slice 5 — Admin/UI (only after backend semantics are approved)

Goal: operator visibility without implying connectivity or currentness.

- Extend the read-only `AdminStorage` panel (`frontend/src/AdminSettings.tsx`
  ~523) with source configuration/status/coverage/refresh/error/audit views
  **only for what the server can actually verify**; UI may not show a source as
  connected or access as current when it cannot (research §7 Phase 4 row).
  The existing "外部保存先: 未実装・無効（既定拒否）" statement stays accurate
  until a connector is owner-approved.
- User-facing document surfaces (`frontend/src/App.tsx` upload flow,
  `IngestionProgress.tsx`, `ProvenanceDiagram.tsx`, `RelatedDocuments.tsx`):
  only provenance/status presentation changes; no new authorization behavior in
  the UI. Any source-availability state shown must come from the backend gate.
- 【要決定】 gate: §7 #9 (who may configure/view sources, credential handling)
  and #2 (whether any connector UI exists at all in this phase).

### Slice 6 — Egress boundary (permanent condition, not a feature)

- Local-only mode remains no-egress at deployment and application layers.
- A connector that contacts a NAS/Drive/network source, and any transmission of
  source-derived content to an external model, are each separately owner-gated
  (research §3 B, §4.6, §5 finding 5, §7 external-egress row). No connector
  implementation, PH2 task, or UI state implies egress approval.
- Verification-style guard: the existing egress/boundary test family (e.g.
  `tests/integration/test_live_docker_boundary.py` conventions) is the template
  for asserting no outbound calls in local-only mode.

---

## 4. Regression-test plan

Goal: prove "no behavior change when no source exists" and "fail-closed on every
path when source state changes", per the research recommendation to test the full
source→ACL change/deletion→every derived read path (research §7 Phase 3 row).

1. **Existing-suite invariants (must stay green, unchanged semantics):**
   - `tests/test_api.py`, `tests/test_security.py` — upload/list/read/publish/
     delete and deny-by-default behavior for unbound documents.
   - `tests/test_concurrent_roles.py`, `tests/test_role_updates.py`,
     `tests/test_custom_role_publication.py` — 兼任 union + explicit deny +
     live grant recheck remain the only ACL path for unbound documents.
   - `tests/test_delegations.py` — delegation expiry/subset/self-escalation
     untouched; no source grant inference from delegated rights.
   - `tests/test_scanner.py`, `tests/test_chat_queue.py`,
     `tests/test_recovery.py`, `tests/test_related_documents.py`,
     `tests/test_audit_regressions.py`, `tests/test_administration_audit.py`,
     `tests/test_admin_project_storage_load.py` — existing queue/scanner/
     recovery/audit/load regressions unchanged.
2. **New unit/integration tests (per slice):**
   - Slice 1: schema migration round-trip (fresh DB + legacy DB via
     `_ensure_column` path); unbound documents byte-identical metadata/list.
   - Slice 2: source gate matrix — for each read path (list, document, chunks,
     related, citations, generated-answer hiding, conversation attachments,
     send retrieval/attachment admission): Locus-granted × source-denied → deny;
     source-granted × Locus-denied → deny; both granted → allow; unknown/stale
     source state → deny. Two-check ingestion: revocation between the checks
     cancels without scanner exposure (mirrors `process_next` tests).
   - Slice 3: source delete/revoke/move/change → visibility invalidates first,
     derived artifacts reconcile, stale worker cannot resurrect superseded data,
     `recover_jobs` semantics for source-bound states.
   - Slice 4: audit rows for each new operation, metadata-only (no content,
     credential, path or ACL payload), audit-failure atomicity for
     state-changing transitions.
   - Slice 5: Vitest for any `AdminStorage` extension (server-verified states
     only) and Playwright only if a user-visible surface changes.
   - Slice 6: no-egress assertion in local-only mode (no outbound calls from
     ingestion/retrieval code paths).
3. **Full QA cycle per slice (per `docs/plans/agent-work/PH2-C2-storage-acl-plan.md`):
   `pytest tests -q --ignore=tests/e2e`, `ruff check` + `ruff format --check`,
   `mypy backend/app`, secret scan; frontend lint/test/build/Playwright when UI
   is touched — plus branch CI green at the exact HEAD.

---

## 5. Module touchpoints (existing code)

| Module | Role in this plan |
|---|---|
| `backend/app/service.py` (Store schema ~385; `_ensure_column` ~437; `_audit` ~474; `_permissions` ~1155; `require` ~1705; `_can_read` ~1767; `_document` ~1791; `documents` ~1836; `chunks` ~1858; `related` ~1874; `upload` ~1944; `_ingestion_allowed`/`process_next` ~2005–2055; `_index` ~2057; `seed_synthetic` ~2067; `cancel` ~2102; `delete_document` ~2121; `publish` ~2127; `_citations` ~2178; `_generated` ~2197; `conversation` ~2210; `send` ~2254; `recover_jobs` ~455) | Schema additions (S1), shared source gate (S2), lifecycle propagation (S3), audit operations (S4) |
| `backend/app/scanner.py`, `docs/INGESTION_SCANNER.md` | Unchanged semantics; two-check pattern template; not a source-ACL mechanism |
| `backend/app/main.py` (~338–372 document routes; ~516 `/api/admin/storage`) | New endpoints only if a slice requires them; existing routes inherit the gate via service calls |
| `frontend/src/AdminSettings.tsx` (`AdminStorage` ~523) | Slice 5 extension target (read-only today, accurate "無効（既定拒否）" copy) |
| `frontend/src/App.tsx` (`storage` nav ~43/893/1264), `IngestionProgress.tsx`, `ProvenanceDiagram.tsx`, `RelatedDocuments.tsx`, `Publication.tsx` | Slice 5 presentation-only provenance/status changes |
| `tests/*` as listed in §4 | Regression harness; no weakening of existing tests permitted |
| Docs: `docs/requirements/PRODUCT_SPEC.md`, `docs/architecture/ARCHITECTURE.md`, `docs/planning/research-app-concept.md` §8, `docs/planning/ui-and-multiuser-design.md`, `docs/plans/PHASE_SPEC_RECONCILIATION.md` (Phase 3 row) | Requirement sources; Phase-3 placement of connector→ingestion→index lifecycle; spec updates only after owner decisions |

Not touched by this plan: `backend/app/local_model.py`, `backend/app/agents/`,
`backend/app/cli.py` (except audit side effects if provisioning changes — none
planned), delegation spec `docs/plans/PHASE2_DELEGATION_SPEC.md` (only the
no-source-grant-inference invariant is asserted by tests).

---

## 6. Explicit non-goals of this document

- No connector, source scan, NAS/Drive access, credential handling or network
  client is designed in implementable detail here; that is the separate
  connector/security configuration phase (research §3 B, §7).
- No decision is made on any item in §7; this plan does not self-approve.
- No claim that any source ACL, propagation, or egress behavior exists today;
  §1 records only what the code at HEAD `951c3cf` actually does.
- No changes to `main`, `loop/local-development`, protected branches, CI
  configuration, or existing tests.

## 7. 【要決定】 items (owner decisions required; intentionally unresolved)

Carried from research §6 with slice gating; none is decided here.

| # | Decision | Gates |
|---|---|---|
| 1 | Confirm D5 means source-ACL propagation (A/A2), not only connector setup (B) or local-storage ACL/retention (C/D) | S1, S2 |
| 2 | First source types/access modes in scope (manual upload / server-local folder / NAS / named online service); whether any connector exists in this phase at all | S0, S1, S5 |
| 3 | Live vs. bounded/versioned snapshot source-permission checks; identity mapping; acceptable freshness / max revocation delay; source of truth | S1, S2, S3 |
| 4 | Combination rule with project membership, explicit deny, publication grants, personal ownership, conversation attachments (research proposes intersection/additional gate) | S2 |
| 5 | Behavior on source ACL revoked/unavailable/disconnected/moved/sync-missed: hide, quarantine, delete, retain-but-unavailable? Effect on open conversations/citations/answers | S2, S3 |
| 6 | Source-deletion semantics: binding-only vs. Locus copies/derivatives vs. upstream deletion request; who may initiate upstream deletion | S3 |
| 7 | Original bytes: copy / cache / link / fetch-on-demand; retention & backup for originals, extracted text, chunks, embeddings, caches, answers, audit rows | S1, S3 |
| 8 | Multi-source documents: cardinality and access rule when any source is revoked; duplicate handling and stable identity across moves | S1, S3 |
| 9 | Source configuration authority: who configures roots/scopes, who sees paths/credentials/status; credential protection/rotation; egress allowlist | S0, S5 |
| 10 | Sync failure/concurrency/retry/race semantics; authorization linearization point during scan/retrieval/generation | S2, S3 |
| 11 | Source metadata in audit; retention/access/privacy restrictions for connector administrators | S4 |
| 12 | Source permission vs. external AI policy: confirmed independent; source read permission never consents to external model egress | S0, S6 |

---

## Self-review / evidence limits

- Grounded in `docs/plans/PHASE2_STORAGE_ACL_RESEARCH.md` and first-hand reads of
  `backend/app/service.py`, `backend/app/scanner.py`, `backend/app/main.py`,
  `frontend/src/AdminSettings.tsx`, `frontend/src/App.tsx`, `tests/` layout,
  `docs/plans/PHASE_SPEC_RECONCILIATION.md`, `docs/plans/PHASE_STATUS.md` and the
  governance docs, all at this worktree's HEAD (`951c3cf` lineage).
- No code was changed; no behavior is activated or claimed. Every slice is
  explicitly gated on owner answers to §7. The word "recommended" anywhere above
  means a proposal for owner review, following the research note's convention.
