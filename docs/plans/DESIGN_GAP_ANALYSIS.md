# Original-design gap analysis

Audit baseline: `loop/local-development` HEAD **`27c5a1d`** (2026-11-09), worktree `loop/AUD-1-design-audit`. Requirement IDs are from [`REQUIREMENT_ID_SCHEME.md`](REQUIREMENT_ID_SCHEME.md). This audit covers both the research assistant and the independently specified autonomous development controller; completion is the original approved design, not a phase-number counter. It is a read-only documentation audit; no application code was modified.

## Status vocabulary and evidence rule

Use only these states: `未着手` (no implementation), `設計中` (proposal/design underway or unapproved), `実装中` (implementation in progress), `実装済み・未検証` (code exists without sufficient verification), `検証済み・未統合` (QA/review evidence exists but is not in the integration branch), `統合済み` (integrated, but a stated completion/review/acceptance gate is still unmet), `完了条件充足` (the explicitly bounded requirement and all required evidence are met), `Owner判断待ち` (a source conflict or required owner decision blocks safe selection), `正式に対象外と承認済み` (only when owner-approved as out of scope). `Prototype-deferred` is not the same as out of scope. A path or test name proves neither behavior nor completion; evidence below is limited to the cited scoped QA, independent review, integration SHA and CI records.

## Executive finding

Only the bootstrap and Phase-1 authentication slices are explicitly declared complete in the **owner-approved local synthetic-data prototype scope**. That does not complete the original product or autonomous-loop acceptance. The integrated product remains loopback/development-only, with SQLite and lexical retrieval; several core and final-production requirements remain open. The loop has an extensive offline/mocked implementation but its own implementation ledger says live executor, real review transport, remote merge/base-binding and unattended acceptance are incomplete. Hybrid step 2a is metadata-only and dispatch remains rejected. The phase label systems are aliases, not interchangeable completion criteria.

## Requirement-area gaps

| Area / IDs | Original requirement and authoritative source | What is verified at audited HEAD (paths + evidence) | Gap / state |
|---|---|---|---|
| Product purpose and deployment — PROD-001–009 | Confidential research knowledge assistant; authorized LAN/private clients; private-network deployment controls; replaceable candidates; first-prototype exclusions scoped only to prototype. `PRODUCT_SPEC.md` Purpose/Core/Out-of-scope; `ARCHITECTURE.md` Deployment; original README/ZIP. | FastAPI/React app and synthetic fixture. Production is rejected at startup; loopback restriction and egress startup holds in `backend/app/main.py`; prototype scope and test evidence in `decisions/0002-development-prototype.md`, `.bootstrap/complete.json`, `docs/DEVELOPMENT.md`. `backend/` and `frontend/`. | Prototype implementation exists and Bootstrap acceptance is evidenced; actual LAN/private deployment, TLS, firewall/egress proof and production stack are not. Prototype subset `完了条件充足`; full deployment `未着手`/`Owner判断待ち`. |
| Authentication/session — IAM-001–005, IAM-017 | Unique accounts, one-time password, forced rotation, Argon2id, recovery/revocation and production session security. `PRODUCT_SPEC.md` Core/Acceptance; ADR-0002; reconciliation Phase 1. | `backend/app/service.py`, `backend/app/main.py`, `backend/app/cli.py`; `tests/test_security.py`, `tests/test_api.py`, auth-specific tests. Phase 1 evidence and independent aggregate/re-review + exact-HEAD CI/version 0.2.0 recorded in `PHASE_STATUS.md`, `PHASE_SPEC_RECONCILIATION.md`, `STATUS_AND_DECISIONS_2026-11-09.md`; main `75d4e0a`. | Phase-1 auth prototype slice `完了条件充足`. MFA is explicitly excluded only for LAN prototype; final MFA posture unresolved. Production TLS/cookie/session deployment remains deferred. `Owner判断待ち` for final MFA policy; production controls `未着手`. |
| Org/project identity and authorization — IAM-006–014 | Organization/project/user separation, default-deny, every data path live ACL, private history, named built-in roles, bounded role edits/delegation, effective-access preview. `PRODUCT_SPEC.md` Core/Acceptance; architecture and multiuser design. | `backend/app/service.py` and `backend/app/main.py`; `tests/test_api.py`, `test_security.py`, `test_custom_role_publication.py`, `test_role_updates.py`, `test_administration_audit.py`. Project-level identity and current role model are real; PH2-B branch `355706f` has 1124 pass/18 skip, but is not integrated at this base. | Existing prototype ACL paths are implemented/tested; every unimplemented vector/graph/export/agent path cannot be declared covered. Concurrent roles/deny are `検証済み・未統合`; web admin settings P4B `実装中`; role/permission UI and full end-to-end delegation `未着手`/`Owner判断待ち`. |
| Delegation and audit — IAM-011, IAM-013, IAM-015–016 | Delegation by subset/scope/expiry; no escalation; transaction-bound metadata audit; final audit protection/retention. `PRODUCT_SPEC.md`; `PHASE2_DELEGATION_SPEC.md`; threat model T-T4. | Product audit table `_audit` in `backend/app/service.py`; tests `tests/test_administration_audit.py`, `tests/test_audit_regressions.py`. `/api/admin/delegations` intentionally returns 409 in `backend/app/main.py`. PH2-A spec lists 12 unresolved decisions. | Delegation implementation `Owner判断待ち` (disabled, spec unapproved). Metadata audit is not tamper-evident/confidential or retention-complete; final audit-log protection is activation blocker `未着手`/`Owner判断待ち`. |
| Ingestion, search, provenance — DATA-001–015 | Safe bounded ingestion, scan/parse/index async, citation to actual source/page/chunk, ACL/revocation and deletion propagation, local RAG; eventual original source ACL/storage, safe parsers, retention/backup. `PRODUCT_SPEC.md`; `ARCHITECTURE.md`; `THREAT_MODEL.md`; `research-app-concept.md` §§3,8; reconciliation Phase 3. | `backend/app/service.py`, `backend/app/scanner.py`, `backend/app/local_model.py`; tests `tests/test_scanner.py`, `tests/test_api.py`, `tests/test_security.py`, `tests/test_related_documents.py`, `tests/test_local_model.py`; UI `frontend/src/RelatedDocuments.tsx`, `IngestionProgress.tsx`. Only text/Markdown/CSV ≤256 KiB; scanner unavailable defaults quarantine; optional ClamAV adapter has mock evidence in `INGESTION_SCANNER.md`; optional Ollama answer path has mock and specifically bounded synthetic trials in `LOCAL_MODELS.md`/Phase status. | Local lexical/provenance prototype paths verified, not production formats/capacity. Storage connectors, recursive inventory, original-source ACL, PDF/OCR/parser isolation, production DB/vector/graph, durable distributed resumption, retention, backup/restore, secure deletion remain `未着手`/`Owner判断待ち`. Real ClamAV operations not verified. |
| Chat/UI/multi-user — UI-001–008 | Owner-selected baseline, accessible/responsive sidebar/chat, file/drop attachment, source/generated disclosure, private history, multi-user queue/cancel, structured comparison/plots, admin and safe delete flows. `UI_IMPLEMENTATION_BASELINE.md`, image, `ui-and-multiuser-design.md`, `PRODUCT_SPEC.md`, reconciliation Phase 4. | `frontend/src/App.tsx`, `styles.css`, component and unit tests, `frontend/e2e/workspace.spec.ts`; `backend/app/service.py` chat jobs, cancellation and ACL; `tests/test_chat_queue.py`, `frontend/src/ChatQueue.test.tsx`. P4A completed in local integration at `5a7848c`, CI and 1117 pytest evidence in status docs. | Baseline prototype is substantially implemented; current P4A slice integrated. P4B project/storage/load UI/backend is active on another worktree. Comparison table and audited delete operations remain open. Representative user/accessibility and multi-user capacity testing remain `未着手`; no capacity claim. |
| Hybrid requirements — HBR-001–015 | Server/Desktop Runner per workspace, org policy, classification, OS isolation, official per-user CLI auth/terms, audit, authenticated transport, settings UI; preserve Plane-M boundary. `locus-hybrid-agent-requirements.md`; `HYBRID_AGENT_THREAT_MODEL.md`; accepted ADR-0012. | `backend/app/agents/registry.py`, admin routes in `backend/app/main.py`, `tests/test_agents_registry.py`, `tests/test_quality_parallel.py`; `loop_engine/model_gate.py`, `audit_transport.py`, `c_min_runtime.py`; zero-tool suite in `tests/unit/test_loop_tool_surface.py`, `test_loop_c_min.py`, integration tests. Registry stores metadata/presence only and includes explicit B6 rejection. | Hybrid threat/design/ADR are not activation. Slice 2a integrated at `282e864`; independent review accepted with a MEDIUM fix pending, so not complete. Runner, real dispatch, classification in product data flows, OS isolation, trust root, authenticated runner transport, provider terms, artifact enforcement, audit protections, and provider UI are `未着手` or `Owner判断待ち`. Real data and external runner reach are explicitly not approved. |
| Controller foundation/planning — LOOP-001–004, 017 | Additive persistent language-independent Controller; planning from Goal with stable requirements, validated tasks and DAG. `AUTONOMOUS_LOOP_SPEC.md` §§0–6,15,18; `LOOP_BOOTSTRAP_SPEC.md`; ADR-0003. | `loop_engine/{cli,controller,scheduler,state_store,planning,schemas,models,reporting}.py`; `.loop/schemas/*`; `tests/unit/test_loop_foundation.py`, `test_loop_planning.py`, integration and `scripts/verify_loop.py`. | Local functionality and mock verification documented; whole original live acceptance remains. Foundation is `統合済み`, not product final complete. Goal planning adapter is blocked by the model boundary. |
| Controller execution/review/approval/QA — LOOP-005–011, 015–016, 020–021 | Three attempts/two review-fix cycles, independent fresh read-only review, required static/functional/security/alignment checks, bounded sandbox/authorization, hash-bound decisions, durable recovery and non-replay. Same spec §§7–13,16,18; ADR-0003/0004/0005/0006/0011. | `loop_engine/codex_runner.py`, `process.py`, `verification.py`, `reviewer.py`, `approval.py`, `recovery.py`, `security.py`, `model_gate.py`, `audit_transport.py`, `trial_input_binding.py`; tests under `tests/unit/test_loop_*`, `tests/integration/test_loop_*`. `LOOP_IMPLEMENTATION.md`, `LOOP_ENGINE.md`, C-min review records distinguish synthetic/local tests from real use. | Broad offline implementation is locally tested/reviewed. Live normal model executor requires a valid current boundary receipt and is held; real independent review transport and full live lifecycle are not proven. `統合済み` for mock/local subset; original live acceptance `未着手`/`Owner判断待ち`. |
| Controller Git/CI/merge and ongoing completion — LOOP-010–014, 018–022, GOV-003–004 | Original specification describes task PRs, current-head checks, conditional safe merge and post-merge reassessment; later mode changes are scoped and must not erase original acceptance. | `loop_engine/git_manager.py`, `github_manager.py`, `main_integration.py`, `local_delivery.py`, `.github/workflows/{loop-ci,quality,pr-title}.yml`, integration tests and CI evidence. Exact C-min/Main/local-delivery records in `docs/reviews/*`, `LOCAL_DELIVERY_*`, `MAIN_*`, `SAFE_AUTO_MERGE_SETUP.md`. | Local commit/push migration to `loop/local-development` was explicitly approved and applied; it does not establish main integration. `atomic_base_binding=false`, trusted independent review publisher/activation and main policy are unresolved. 2026-11-09 instruction calls for phase-completion main merge/version bump while PR-free Main activation remains explicitly unapproved; resolve delivery policy before claiming original LOOP-013/022 complete. `Owner判断待ち`. |
| Governance and supply chain — GOV-001–006 | Preserve user files/approvals, single implementer except allowed reviewer, protected delivery, explicit decisions, evidence, dependency/license diligence. `AGENTS.md`, governance docs, `BOOTSTRAP.md`, dependencies inventory. | Policy/workflow, `.github/workflows/*`, `pyproject.toml`, requirements lockfiles, dependency reports and reviews. | Process and local controls implemented, but reviewer host isolation is explicitly procedural/not technically enforced and production distribution legal review remains open. Partial `統合済み`; final reviewer isolation `未着手`/`Owner判断待ち`. |

## Requirement ID → gap-state crosswalk

This crosswalk makes the per-ID state explicit; rows refer to the evidence and gap explanations above. State labels are exactly the approved vocabulary. A state is not a declaration of final completion if its row describes only a prototype or offline scope.

| Requirement IDs | Current gap state at audited HEAD | Scope note |
|---|---|---|
| PROD-001, PROD-004, PROD-005, PROD-006, PROD-007, PROD-008 | `統合済み` | Prototype implementation/evidence only; overall final product remains open. |
| PROD-002, PROD-003, PROD-009 | `Owner判断待ち` | Deployment/privacy scope and first-prototype exclusions versus final completion require explicit decision/verification; production currently not implemented. |
| IAM-001, IAM-002, IAM-003 | `完了条件充足` | Phase-1 owner-approved prototype slice only, with review/CI evidence cited above. |
| IAM-004, IAM-006, IAM-007, IAM-008, IAM-009, IAM-010, IAM-014, IAM-015 | `統合済み` | Implemented prototype paths; complete-system path coverage and production enforcement not satisfied. |
| IAM-005, IAM-011, IAM-013, IAM-016, IAM-017 | `Owner判断待ち` | MFA/final delegation decisions, grant/membership semantics, audit retention/protection and production TLS/session scope remain open. |
| IAM-012 | `検証済み・未統合` | PH2-B branch tests/QA/CI evidence exists, but code is not integrated at audited HEAD. |
| DATA-001, DATA-002, DATA-003, DATA-005, DATA-009, DATA-010, DATA-011 | `統合済み` | Bounded prototype behavior exists; not production ingestion, retention, or all-path proof. |
| DATA-004, DATA-006, DATA-007, DATA-008, DATA-012, DATA-013, DATA-014, DATA-015 | `未着手` | Remaining final search/scan/parser/source/classification/database/discovery/retention work; some design choices separately require owner decision. |
| UI-001, UI-002, UI-003, UI-004, UI-005 | `統合済み` | Approved baseline and implemented screens/tests; remaining usability/accessibility evidence remains. |
| UI-006, UI-007, UI-008 | `実装中` | Multi-user/capacity/analysis requirements remain; P4B is active; comparison/deletion are queued. |
| HBR-001, HBR-002, HBR-003, HBR-004, HBR-005, HBR-006, HBR-007, HBR-008, HBR-009, HBR-010, HBR-013, HBR-014, HBR-015 | `未着手` | Product hybrid execution, org policy, isolation, credentials, audit, transport, settings, admission/cancellation and full contracts/receipts are not active. |
| HBR-011, HBR-012 | `実装中` | 2a metadata and B6 reject gate integrated; review fix and exact-head CI still pending; scope authorizes no execution. |
| LOOP-001, LOOP-002, LOOP-004, LOOP-005, LOOP-007, LOOP-009, LOOP-010, LOOP-011, LOOP-015, LOOP-016, LOOP-017 | `統合済み` | Local/mock controller behaviors implemented, with original live acceptance still open. |
| LOOP-003, LOOP-006, LOOP-008, LOOP-012, LOOP-013, LOOP-014, LOOP-018, LOOP-020, LOOP-021, LOOP-022 | `Owner判断待ち` | Original criteria require live isolation/review/delivery/main integration; some are engineering gaps, and main-policy conflict needs owner resolution. |
| LOOP-019 | `完了条件充足` | Exact scoped local branch policy migration applied; does not complete the original PR/merge/final system acceptance. |
| GOV-001, GOV-003, GOV-004, GOV-005 | `統合済み` | Controls/policy and evidence conventions are present; final secure operation still requires proof. |
| GOV-002, GOV-006 | `Owner判断待ち` | Reviewer host restrictions are not technically enforced; production distribution/license clearance remains open. |

No ID is assigned `正式に対象外と承認済み` by this audit. `PROD-009` names exclusions only for the first prototype, not the final product. `未着手` means no final-scope implementation verified, even where exploratory or metadata-only code exists.

## Explicit owner-decision / contradiction findings

These are not reconciled by this audit; none changes an existing approval:

1. **Phase schemes**: original product roadmap 0–5 (`ROADMAP.md`), PRODUCT_SPEC MVP slices 1–6, and autonomous controller Phases 1–6 (`AUTONOMOUS_LOOP_SPEC.md`) use overlapping numbers for different work. `PHASE_STATUS.md` already notes that its Phase numbering is not the MVP slice numbering. Owner's 2026-11-09 instruction makes original-design completion authoritative. Keep namespaced aliases; do not infer one family is complete from another. (`Owner判断待ち` for final canonical crosswalk.)
2. **Delivery policy**: original autonomous specification requires PR creation and conditional safe merge; later owner-approved migration selects local `local_commit_push` to `loop/local-development`; main integration proposals say PR-free Main mode is not approved and current atomic base binding is false. The 2026-11-09 phase rule calls for main merge after phase completion. Do not treat dev-branch push as main integration, or activate unapproved Main mode. Owner decision required on safe, authorized main-delivery mechanism and relationship to phase policy.
3. **Phase 1 exclusions**: owner accepts MFA omission only for LAN prototype, with production TLS/session/LAN deployment validation explicitly deferred. These do not become final out-of-scope requirements; final MFA decision still needs explicit resolution.
4. **ADR-0012 internal status contradiction**: front matter says ACCEPTED by owner on 2026-11-07, while its §Decision says “proposed; pending owner approval.” Later top-level authority section and owner record support acceptance of the dual-plane boundary (implementation only slice 2a; activation still separate). Preserve the accepted status but flag and correct the stale contradictory section in a docs-only owner-reviewed update; never widen the approval.
5. **Code vs architecture proposal**: `ARCHITECTURE.md` suggests PostgreSQL/pgvector and optional graph engine, but ADR-0002 and current code expressly use replaceable SQLite + lexical retrieval in development. That is an approved prototype divergence, not completion of production database/search requirements.
6. **Code vs deployment design**: Product/architecture require eventual LAN/private deployment and egress restrictions; `backend/app/main.py` explicitly supports development loopback only, HTTP cookie `secure=False`, and production startup refusal. This is consistent with the prototype hold, not production proof.
7. **Delegation documentation**: Phase plans describe the disabled delegation API as an existing path, but actual `backend/app/main.py` has only a 409 placeholder; no grant storage or active grant checks exist. Keep disabled. PH2-A is still draft and its 12 decisions are unanswered.
8. **Hybrid sequencing**: early ROADMAP says hybrid steps feed existing phases; threat model / ADR-0012 impose ADR approval before any step-2 code and separate approval ADR + activation gates before dispatch. Later accepted constraints prevail without removing any product requirement.
9. **Development Loop and main claims**: ADR-0005 defines completion against every Goal criterion, current mandatory QA and no open blockers; local-delivery/Main docs retain additional proof/owner gates. None permits declaring completion merely because a bounded phase or mock E2E succeeded.
10. **Current status snapshots are time-bound**: `STATUS_AND_DECISIONS_2026-11-09.md` reports PH2-B CI pending at that recorded time, whereas `loop/PH2-B-roles` later reports green exact-head CI and local QA but is not integrated into this audited base. P4B and PH2-2AF are independently active. Do not overwrite contemporaneous status records with stale/assumed state.

## Original-requirement provenance and evolution

The first tracked commit (`c48065e`, 2026-10-31) introduced the synthetic-data product app, prototype ADR, UI specification, initial threat model and the full `AUTONOMOUS_LOOP_SPEC.md`. The included `research-ai-bootstrap-v3.zip` is the 2026-10-29 reference package and contains earlier Product Spec, Architecture, Threat Model, Roadmap, AGENTS and UI documents; its original Product Spec is labeled proposed and its stack remains provisional. Git history shows no earlier tracked `docs/` documents before the initial repository commit and no deleted/renamed `docs/` files in the reachable history examined (`git log --diff-filter=A -- docs/` and `git log --all --diff-filter=DR -- docs/`). The original hybrid requirements were added 2026-11-07; they add a separate required runtime, not a replacement of the product/security acceptance. Later approved changes are scoped: synthetic-only development prototype; local model extension; auth Phase-1 prototype completion with MFA/TLS/LAN deployment deferred; ADR-0011 normal-development C-min offline boundary; ADR-0012 dual-plane split and slice-2a authorization; local-commit/push policy migration; no real-data or runtime activation. None of these authorizes dropping unresolved original final requirements.

## Source survey register

Dates below are document dates when explicitly stated; otherwise the Git first-add date (recorded date) is used. “Status/scope” records the actual authority in the document, not a conclusion that the source requirements are satisfied. The compact directory registers name every tracked file at the audited HEAD; files grouped in a family share the family status/scope shown in the heading. Later changes are described at the family/section level above so a proposal/review is not mistaken for a requirement or an approval.

### Initial specifications, entry points and archived earlier source

| Source | Date | Approval/status | Scope and relationship |
|---|---|---|---|
| `AGENTS.md` | 2026-10-31 (initial tracked) | Repository standing instructions; current text includes later loop governance | Source-entry/governance, UI rules and safety; read with `DEVELOPMENT_POLICY.md`; later loop-task constraints are additive. |
| `docs/requirements/PRODUCT_SPEC.md` | 2026-10-31; refinement 2026-10-29 noted | Proposed product baseline, later prototype owner approvals scope implementation | Research assistant requirements and first-prototype exclusions; later planning docs refine but do not silently erase final capabilities. |
| `docs/requirements/AUTONOMOUS_LOOP_SPEC.md` | 2026-10-31 | User-supplied full implementation specification | Controller acceptance; later local-delivery/ADR decisions change only the approved delivery/runtime scope. |
| `docs/requirements/DEVELOPMENT_LOOP_SPEC.md` | 2026-10-31 | User requirements | Outer merge-assessment/completion loop; later delivery mode does not waive criteria or QA. |
| `docs/requirements/LOOP_BOOTSTRAP_SPEC.md` | 2026-10-31 | Bootstrap task scope, not product completion authorization | `$loop` setup and CI integration; bootstrap completion is not full live Controller acceptance. |
| `README.md` | 2026-10-31; refers to 2026-10-29 source | Reference/bootstrap description, explicitly distinguishes sample/prototype | Points to UI/product docs and development scope; later sections add Loop and approved extensions. |
| `research-ai-bootstrap-v3.zip` (root, not a tracked docs file) | 2026-10-29 | Reference package; ZIP instructions explicitly not executed | Contains earlier AGENTS, Product Spec, Architecture, Threat Model, Roadmap, decision 0001 and UI sources; Product Spec is proposed; later repository docs retain/refine it. |
| `docs/plans/bootstrap-goal-history/goal.md` | 2026-10-31 | Preserved original Controller Goal | Additive autonomous controller alongside app; linked to full spec. |
| `docs/plans/bootstrap-goal-history/requirements.md` | 2026-10-31 | Preserved authoritative requirements pointer | Full AUTONOMOUS_LOOP_SPEC absolute conditions; no mocks-as-live substitution. |
| `docs/plans/bootstrap-goal-history/architecture.md` | 2026-10-31 | Preserved architecture pointer | ADR-0003 and explicit live blockers. |
| `docs/plans/bootstrap-goal-history/acceptance.md` | 2026-10-31 | Preserved original acceptance | Original §18 remains unrelaxed; live integration acceptance remains open. |
| `docs/BOOTSTRAP.md` | 2026-10-31 | Bootstrap procedure | Inventory, approval, setup, verification and report; `.bootstrap/complete.json` is scoped to prototype. |

### Architecture/ADR and security documents (each file listed; approval is scope-limited)

| Source | Date (recorded) | Status / scope at HEAD; relation |
|---|---|---|
| `docs/architecture/ARCHITECTURE.md` | 2026-10-31 | Baseline “subject to ADRs”; original product architecture. Prototype ADR explains current SQLite/loopback divergence; production proposals remain open. |
| `docs/architecture/decisions/0001-open-decisions.md` | 2026-10-31 | Proposed/open decisions; not an approval. Security-critical items remain owner-decision inputs. |
| `docs/architecture/decisions/0002-development-prototype.md` | 2026-10-31; amended through 2026-11-06 | Accepted local synthetic-data development scope and later explicitly approved offline Ollama extension. It excludes production/data/egress claims; later ADRs refine, not broaden activation. |
| `docs/architecture/decisions/0003-autonomous-loop-engine.md` | 2026-10-31 | Implementation design based on user spec; detailed runtime constraints and incomplete-live acceptance. |
| `docs/architecture/ADR-0004-loop-bootstrap-qa.md` | 2026-10-31 | Implemented adapters, executor/merge activation blocked; supplements (does not replace) ADR-0003. |
| `docs/architecture/ADR-0005-development-loop.md` | 2026-10-31 | Implemented/local-tested development-loop design; live execution remains blocked. |
| `docs/architecture/ADR-0006-source-only-runtime.md` | 2026-10-31, revised 2026-11-03 | Owner-approved narrow offline C-min refinement; corrects earlier proof assumptions; no live activation. |
| `docs/architecture/ADR-0007-safe-merge-broker-proposal.md` | 2026-10-31; approved 2026-10-31 | Approved for implementation only; activation requires trusted review/base/locking proofs. |
| `docs/architecture/ADR-0008-merge-policy-read-permission-proposal.md` | 2026-10-31; approved 2026-10-31 | Narrow Merge App Administration-read scope approved for implementation/request, not activation. |
| `docs/architecture/ADR-0009-keyless-audit-worker-proposal.md` | 2026-11-01; corrected 2026-11-02 | Accepted audit worker design/implementation; ADR-0010 narrows authentication storage; 0011 corrects zero-tool boundary. No product-runtime activation. |
| `docs/architecture/ADR-0010-encrypted-audit-auth-proposal.md` | 2026-11-01 | Accepted narrow audit-only encrypted cache implementation; not product credentials or deployment activation. |
| `docs/architecture/ADR-0011-model-facing-zero-tool-gate-proposal.md` | 2026-11-02; accepted 2026-11-03 | Accepted only for C-min normal-development offline implementation; not live inference/auth. Normative scope is supplement/final design. |
| `docs/architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md` | 2026-11-07 | Owner-accepted dual-plane constraints; only metadata slice 2a authorized. Front matter vs §Decision wording conflict is finding #4. |
| `docs/security/THREAT_MODEL.md` | 2026-10-31 | Initial, non-certification product threat model; later hybrid model extends it. |
| `docs/security/HYBRID_AGENT_THREAT_MODEL.md` | 2026-11-07 | Analysis/proposal, independently accepted after minor fixes; threat/gap mapping, not implementation or activation authority. |

### Planning, phase, boundary, and owner-decision records

Every tracked regular file under `docs/plans/` at HEAD is named below. Status: plan, design, proposal, approval record, evidence, or task ledger as indicated by filename/title; no plan by itself is code or owner approval. Date defaults to first Git addition unless the document says otherwise. Later owner decisions are in the dated status record and append-only task/review evidence.

| Source | Recorded date | Status/scope and later relationship |
|---|---|---|
| `docs/plans/APPROVAL_RELATIVE_ACTIVATION.md` | 2026-11-05 | Owner-relative activation design/approved offline change context; does not itself grant a live execution. |
| `docs/plans/BOUNDED_RUN_NOTIFY_OFFLINE_RESULT.md` | 2026-11-05 | Offline implementation result; tests/review reported, live authorization explicitly absent. |
| `docs/plans/C_MIN_ACL_AUTH_REMEDIATION_PROPOSAL.md` | 2026-11-04 | Investigation/proposal for ACL/auth boundary; no real mutation authority. |
| `docs/plans/C_MIN_ACL_REPAIR_OWNER_APPROVAL.md` | 2026-11-04 | Approval boundary document, itself states not permission to apply real changes. |
| `docs/plans/C_MIN_CONNECTION_PREPARATION_DIAGNOSTIC.md` | 2026-11-04 | Read-only preparation/diagnostic; not authentication or inference permission. |
| `docs/plans/C_MIN_DERIVED_INSTRUCTION_ID_ADDENDUM.md` | 2026-11-03 | Design only, not approved/implemented at record time; later implementation evidence remains separately scoped. |
| `docs/plans/C_MIN_LIVE_ACTIVATION_PROPOSAL.md` | 2026-11-03 | Explicit NOT approved; not a live authorization. |
| `docs/plans/C_MIN_METADATA_LEASE_MASK_ADDENDUM.md` | 2026-11-04 | Proposal only; no credential/profile ACL change. |
| `docs/plans/C_MIN_NATIVE_METADATA_ADDENDUM.md` | 2026-11-03 | Approval required before extension; complements narrow accepted boundary. |
| `docs/plans/C_MIN_NOTIFY_SUPPRESSION_APPROVAL.md` | 2026-11-05 | Limited offline approval proposal; not general runtime authorization. |
| `docs/plans/C_MIN_RUNTIME_INPUT_BINDING_APPROVAL.json` | 2026-11-03 | Exact protocol/approval manifest; status is scoped in companion design/review. |
| `docs/plans/C_MIN_RUNTIME_INPUT_BINDING_DESIGN.md` | 2026-11-03 | Design requiring approval; later implementation record does not activate live execution. |
| `docs/plans/C_MIN_SINGLE_CONNECTION_APPROVAL.md` | 2026-11-03 | Preparation-only document; no live operation at issuance. |
| `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` | 2026-11-07 | Draft, review-cleared design, not approved as an ADR; owner decision authorizes slice 2a only through ADR-0012. |
| `docs/plans/IMPLEMENTATION_LOG.md` | 2026-10-31 | Historical bootstrap implementation evidence; records explicit code/docs exceptions and residual risk. |
| `docs/plans/LOCAL_DELIVERY_ACTIVATION.md` | 2026-11-02 | Contains superseded proposal plus exact approved migration; current mode is local dev branch Push only. |
| `docs/plans/LOCAL_DELIVERY_MIGRATION_RESULT.md` | 2026-11-02 | Evidence exact policy migration applied; does not certify live loop or main merge. |
| `docs/plans/LOOP_30M_ACTIVATION_REMAINDER.md` | 2026-11-05 | Proposal/offline scope; no grant; outstanding real-runtime gates. |
| `docs/plans/LOOP_IMPLEMENTATION.md` | 2026-10-31 | Phase ledger. Phases 1–6 local/mock implementation evidence, live executor/review/merge incomplete. |
| `docs/plans/MAIN_FF_INTEGRATION_DESIGN.md` | 2026-11-03 | Proposed offline Main extension, not activated; requires separate owner decision and live proof. |
| `docs/plans/MAIN_PRODUCTION_ACTIVATION_PROPOSAL.md` | 2026-11-03 | Explicit Decision M NOT approved; no PR-free main mutation. |
| `docs/plans/MINIMAL_LOOP_POLICY_PROPOSAL.md` | 2026-11-06 | Proposal only, unadopted/unactivated; must not override frozen acceptance. |
| `docs/plans/MODEL_BOUNDARY_APPROVAL_MANIFEST.json` | 2026-11-03 | Proposed manifest says owner decision still required and readiness not established. |
| `docs/plans/MODEL_BOUNDARY_APPROVAL_PROPOSAL.md` | 2026-11-03 | Owner approval proposal; acceptance recorded in `reviews/C_MIN_OWNER_APPROVAL.md`, narrow scope. |
| `docs/plans/MODEL_BOUNDARY_FINAL_DESIGN.md` | 2026-11-02; revised through 2026-11-07 | Investigation/proposal, not itself approval; accepted C-min supplement and live gates distinguish. |
| `docs/plans/NORMAL_AUTH_STORAGE_DECISION.md` | 2026-11-03 | Decision required before implementation; no real auth/model/service operation permitted. |
| `docs/plans/PHASE2_DELEGATION_SPEC.md` | 2026-11-07 | Draft NOT approved; all twelve owner decisions pending; API remains disabled. |
| `docs/plans/PHASE2_JOB_BREAKDOWN.md` | 2026-11-07 | Orchestrator task decomposition from Product/architecture/reconciliation; individual jobs have their own authority/evidence. |
| `docs/plans/PHASE_SPEC_RECONCILIATION.md` | 2026-11-06, updated 2026-11-07 | Product-to-phase discrepancy/acceptance plan; explicitly says not to exclude final requirements; phase status table is a dated snapshot. |
| `docs/plans/PHASE_STATUS.md` | 2026-10-31; substantial updates through 2026-11-07 | Local synthetic prototype ledger; explicit Phase-1 prototype completion only; production requirements remain. |
| `docs/plans/RISK_REGISTER.md` | 2026-10-31 | Open development and production risk list; risk closure needs evidence/decision. |
| `docs/plans/ROADMAP.md` | 2026-10-31; hybrid addition 2026-11-06 | Initial product phases and hybrid requirements added as feed; not a final production roadmap. |
| `docs/plans/STATUS_AND_DECISIONS_2026-11-09.md` | 2026-11-09 | Current owner decision requests/status/prototype designs; not all items are approved, PH2-B line is time-bound. |
| `docs/plans/request-headers-plan.json` | 2026-10-31 | Initial request-header planning evidence; does not expand security boundary by itself. |
| `docs/plans/local-delivery-snapshot.json` | 2026-11-02 | Exact migration snapshot/proposal inputs; use together with migration result and approval. |
| `docs/plans/bootstrap-goal-history/goal.md` | 2026-10-31 | Original loop Goal snapshot, immutable history. |
| `docs/plans/bootstrap-goal-history/requirements.md` | 2026-10-31 | Original loop requirements snapshot, full acceptance retained. |
| `docs/plans/bootstrap-goal-history/architecture.md` | 2026-10-31 | Original loop architecture snapshot; live gates explicit. |
| `docs/plans/bootstrap-goal-history/acceptance.md` | 2026-10-31 | Original loop acceptance snapshot; not relaxed. |
| `docs/plans/agent-work/ORCHESTRATOR_LOG.md` | 2026-11-07–09 | Append-only orchestration status, owner decisions, integration/CI evidence and assignments; records parallel pipeline exceptions. |
| `docs/plans/agent-work/PH1-2A-registry.md` | 2026-11-07–08 | Slice 2a implementation assignment/evidence; superseded status by integration/review/fix task files. |
| `docs/plans/agent-work/PH1-A-recovery.md` | 2026-11-07 | Recovery implementation brief/evidence; contributes to Phase-1 completion. |
| `docs/plans/agent-work/PH1-A2-dual-plane-adr.md` | 2026-11-07 | Draft ADR task; resulting ADR-0012 owner accepted separately. |
| `docs/plans/agent-work/PH1-B-account-toggle.md` | 2026-11-07 | Account enable/disable task/evidence; integrated Phase-1. |
| `docs/plans/agent-work/PH1-C-threat-model.md` | 2026-11-07 | Hybrid threat model task brief; threat model is analysis not approval. |
| `docs/plans/agent-work/PH1-D-web-provisioning.md` | 2026-11-07 | Web provisioning task/evidence; integrated Phase-1. |
| `docs/plans/agent-work/PH1-E-threat-review.md` | 2026-11-07 | Independent security review assignment/results reference. |
| `docs/plans/agent-work/PH1-E2-adr0012-fix.md` | 2026-11-07 | ADR review fix brief; resulting approval remains owner-controlled. |
| `docs/plans/agent-work/PH1-E2-adr0012-review.md` | 2026-11-07 | Independent ADR review; review is not owner approval. |
| `docs/plans/agent-work/PH1-F-hybrid-step2-design.md` | 2026-11-07 | Hybrid design proposal assignment, not implementation approval. |
| `docs/plans/agent-work/PH1-F-step2-design-fix.md` | 2026-11-07 | First review fix-cycle brief; proposal only. |
| `docs/plans/agent-work/PH1-F-step2-design-fix2.md` | 2026-11-07 | Second review fix-cycle brief and disposition; approval still separate. |
| `docs/plans/agent-work/PH1-G-consolidation.md` | 2026-11-07 | Phase-1 aggregate reconciliation/review brief and evidence. |
| `docs/plans/agent-work/PH1-H-step2-design-review.md` | 2026-11-07 | Independent hybrid design review, first round major rework; later round 2 recorded separately. |
| `docs/plans/agent-work/PH1-H-step2-review-round2.md` | 2026-11-07 | Independent design re-review accept after minor fixes; not owner adoption. |
| `docs/plans/agent-work/PH1-J-provision-race.md` | 2026-11-07 | Phase-1 stale-Principal race fix assignment/evidence. |
| `docs/plans/agent-work/PH1-K-auth-aggregate-review.md` | 2026-11-07 | Independent aggregate review, conditional until race fix re-review. |
| `docs/plans/agent-work/PH1-K2-race-fix-review.md` | 2026-11-07 | Independent re-review that closed PH1-K condition. |
| `docs/plans/agent-work/PH1-P4A-cancel.md` | 2026-11-07–08 | Owner-approved Phase-4 cancellation task, integrated at `5a7848c`; not all Phase 4 complete. |
| `docs/plans/agent-work/PH1-P4B-admin-screens.md` | 2026-11-07 | Owner-approved project/storage/load delivery task, active at audit HEAD. |
| `docs/plans/agent-work/PH2-A-delegation-spec.md` | 2026-11-07 | Draft design-only delegation task; twelve owner decisions remain. |
| `docs/plans/agent-work/PH2-B-roles.md` | 2026-11-07–08 | Concurrent roles/deny implementation; branch CI/local QA green per branch ledger, not integrated in audited base. |
| `docs/plans/agent-work/PH2-2AR-slice2a-review.md` | 2026-11-08 | Independent review accept-after-minor-fixes; one MEDIUM audit/rate-limit finding led to PH2-2AF. |
| `docs/plans/agent-work/PH2-2AF-registry-fix.md` | 2026-11-08 | Active registry security fix; no code in this audit branch. |
| `docs/plans/agent-work/AUD-1-design-audit.md` | 2026-11-08 | Current audit assignment; task brief is not an independent requirement source. |

### UI and hybrid design sources

| Source | Date | Status/scope; relation |
|---|---|---|
| `docs/planning/research-app-concept.md` | 2026-10-29 | Product concept/refinement; explicitly differentiates concept from adopted design and sample values. |
| `docs/planning/ui-and-multiuser-design.md` | 2026-10-29 | Design guidance with explicit proposals/open decisions; current baseline doc wins on UI conflicts. |
| `docs/planning/UI_IMPLEMENTATION_BASELINE.md` | 2026-10-29 | User-selected implementation baseline; sample names/values are not acceptance requirements. |
| `docs/planning/ui-baseline-chat.png` | 2026-10-29 | Visual reference image; layout/interaction baseline, sample content not product requirement. |
| `docs/planning/demo-source.fragment.html` | 2026-10-29 | Preview fragment, not application implementation; README explicitly says no backend/model/ACL. |
| `docs/planning/locus-hybrid-agent-requirements.md` | 2026-11-07 | Owner-added hybrid design requirements; does not authorize runtime activation. |

### Other root-level product/operations documentation

| Source | Date (recorded) | Status/scope and relationship |
|---|---|---|
| `docs/APP_PROVISIONING.md` | 2026-11-01; updated 2026-11-07 | Existing App provisioning/auth scope; no token extraction or merge activation. |
| `docs/BROKER_SETUP.md` | 2026-11-01; updated 2026-11-07 | ADR-0007 implementation/activation ledger; explicitly says not activated. |
| `docs/DEVELOPMENT.md` | 2026-10-31 | Synthetic prototype runbook; its historical statements are scoped to bootstrap and later phases supersede them. |
| `docs/INGESTION_SCANNER.md` | 2026-11-06; recorded 2026-11-07 | Owner-approved offline optional ClamAV adapter design/implementation; daemon use remains unverified. |
| `docs/LOCAL_COMMIT_PUSH_LOOP.md` | 2026-11-02; recorded 2026-11-07 | Exact development-branch push policy; explicitly not main-push or runtime readiness authorization. |
| `docs/LOCAL_MODELS.md` | 2026-11-06; recorded 2026-11-07 | Owner-approved local-model offline extension and bounded synthetic trial evidence; not general production inference. |
| `docs/LOOP_BOOTSTRAP_STATUS.md` | 2026-10-31 | Bootstrap/loop integration status; newer ADR and runtime ledger supersede historical status. |
| `docs/LOOP_ENGINE.md` | 2026-11-02; updated 2026-11-02 | Usage/limits; exact live execution and merge gates remain explicitly open. |
| `docs/UNATTENDED_READINESS.md` | 2026-11-02; updated 2026-11-07 | Detailed requirements/readiness matrix, not an activation approval. |
| `docs/WINDOWS_AUDIT_SERVICE_SETUP.md` | 2026-11-02; updated 2026-11-07 | Audit-only service setup; current hold says not to restart after Lite finding. |
| `docs/WINDOWS_SERVICE_SETUP.md` | 2026-11-01; updated 2026-11-07 | Prepare-mode Windows service deployment procedure/evidence, not final runtime approval. |
| `docs/WINDOWS_SERVICE_RECOVERY.md` | 2026-11-01; updated 2026-11-07 | Specific partial-preparation recovery procedure; never general retry authority. |
| `docs/WINDOWS_SERVICE_COMPLETION.md` | 2026-11-01; updated 2026-11-07 | Specific service registration completion evidence; prepare-mode only. |

### Governance, operations, dependencies, bootstrap records

| Source | Date | Status/scope; relation |
|---|---|---|
| `docs/governance/DEVELOPMENT_POLICY.md` | 2026-10-31 | Standing single-implementer, review, delivery and resource rules. |
| `docs/governance/GITHUB_CONNECTION.md` | 2026-10-31 | Repository connection and authorization evidence; old “no remote” observations are superseded by dated later state. |
| `docs/governance/GITHUB_WORKFLOW.md` | 2026-10-31; updated 2026-11-02 | PR/protected delivery and later local branch exception; phase/main conflict remains as finding. |
| `docs/governance/UNATTENDED_AUTHORIZATION.md` | 2026-10-31; updates 2026-11-01/02 | Conditional operations authorization; does not waive execution proof or unresolved security gates. |
| `docs/operations/LOCAL_LOOP_STARTUP_REPAIR.md` | 2026-11-02 | Readiness correction; startup stays held when boundary is unproven. |
| `docs/operations/SAFE_AUTO_MERGE_SETUP.md` | 2026-10-31; updated 2026-11-07 | Setup/protection evidence and explicit missing trusted-review/base gates; not merge activation. |
| `docs/operations/WINDOWS_CI_STARTUP_FINDINGS.md` | 2026-11-02 | Investigation/evidence for Windows CI failures; not requirements relaxation. |
| `docs/dependencies/README.md` | 2026-10-31 | Dependency/license methodology and limits. |
| `docs/dependencies/loop-engine-licenses.json` | 2026-10-31 | Dependency metadata inventory, not production license clearance. |
| `docs/dependencies/python-licenses.json` | 2026-10-31 | Python package license inventory. |
| `docs/dependencies/npm-licenses.json` | 2026-10-31 | npm package license inventory. |
| `.bootstrap/complete.json` | 2026-10-31 | Passed local synthetic prototype/bootstrap verification only; limitations explicitly enumerated. |
| `.bootstrap/python-licenses.json` | 2026-10-31 | Initial bootstrap dependency inventory. |
| `.bootstrap/README.md` | 2026-10-31 | Bootstrap evidence directory context. |

### Review records (each file at HEAD)

Review documents are read-only assessment/evidence, not requirements or approvals unless they reproduce a separate owner decision. The recorded date is the named review date/initial Git addition; later fixes are identified in the record or subsequent task files. This register ensures the review corpus is included rather than treating a later phase summary as the sole evidence.

| Source | Date | Status/scope and relationship |
|---|---|---|
| `docs/reviews/REVIEW_TEMPLATE.md` | 2026-10-31 | Review report format only. |
| `docs/reviews/2026-10-31-loop-audits.md` | 2026-10-31 | Initial loop design/implementation audits; findings and enforcement limits. |
| `docs/reviews/2026-10-31-loop-audits.json` | 2026-10-31 | Structured companion audit evidence. |
| `docs/reviews/2026-10-31-prototype-audit.md` | 2026-10-31 | Product prototype design/implementation review and fix/re-review; scoped synthetic app. |
| `docs/reviews/2026-10-31-bootstrap-qa.md` | 2026-10-31 | Bootstrap/CI audit; defects and verification scope. |
| `docs/reviews/2026-10-31-development-loop.md` | 2026-10-31 | Development Loop independent review; local implementation evidence, not live completion. |
| `docs/reviews/2026-10-31-unattended-runtime.md` | 2026-10-31 | Runtime evidence ledger; explicit live blocks. |
| `docs/reviews/2026-10-31-minimatch-mitigation.md` | 2026-10-31 | Dependency mitigation review; narrow build dependency. |
| `docs/reviews/2026-10-31-ci-registration.md` | 2026-10-31 | CI registration/current-head defect follow-up. |
| `docs/reviews/2026-10-31-app-broker-foundation.md` | 2026-10-31 | ADR-0007 foundation review; preparation/activation gates separated. |
| `docs/reviews/2026-10-31-existing-app-provisioning.md` | 2026-11-01 | Existing App provisioning/policy observation; no blanket activation. |
| `docs/reviews/2026-11-01-app-delivery-readiness.md` | 2026-11-01 | App delivery and migration source review; contingent on exact state. |
| `docs/reviews/2026-11-01-audit-installation-recovery.md` | 2026-11-01 | Audit service install/recovery review; scoped service state only. |
| `docs/reviews/2026-11-01-audit-model-trial-held.md` | 2026-11-01 | Real audit model trial is held/unsuccessful evidence, not a successful review. |
| `docs/reviews/2026-11-01-audit-preparation-services-live.md` | 2026-11-01 | Preparation service live validation, not production runtime activation. |
| `docs/reviews/2026-11-01-audit-service-preparation.md` | 2026-11-01 | Audit-service preparation implementation review. |
| `docs/reviews/2026-11-01-audit-worker-core.md` | 2026-11-01 | ADR-0009 worker core evidence; design/activation distinction. |
| `docs/reviews/2026-11-01-encrypted-audit-auth-design.md` | 2026-11-01 | ADR-0010 storage design review, narrow audit account scope. |
| `docs/reviews/2026-11-01-held-audit-reconciliation.md` | 2026-11-01 | Held auth state reconciliation evidence; no blind retry. |
| `docs/reviews/2026-11-01-merge-401-diagnostics.md` | 2026-11-01 | Merge API authentication diagnostic; does not establish mutation authority. |
| `docs/reviews/2026-11-01-partial-service-recovery.md` | 2026-11-01 | Partial Windows-service recovery audit. |
| `docs/reviews/2026-11-01-permission-diagnostics.md` | 2026-11-01 | Permission diagnostics; read evidence not write permission. |
| `docs/reviews/2026-11-01-preparation-services-live.md` | 2026-11-01 | Preparation service actual deployment evidence; not product Runner readiness. |
| `docs/reviews/2026-11-01-windows-service-preparation.md` | 2026-11-01 | Windows service preparation review, not runtime activation. |
| `docs/reviews/2026-11-02-local-commit-push.md` | 2026-11-02 | Local commit/push mode review; no implied main push. |
| `docs/reviews/2026-11-02-responses-lite-boundary.md` | 2026-11-02 | Responses-Lite tool boundary investigation; defect prompted stricter C-min gates. |
| `docs/reviews/2026-11-05-approval-relative-activation.md` | 2026-11-05 | Offline security review and validation; no live authorization. |
| `docs/reviews/C_MIN_ACL_REHEARSAL_RESULT.md` | 2026-11-04 | Synthetic ACL rehearsal/Windows CI evidence; no real ACL mutation. |
| `docs/reviews/C_MIN_DERIVED_INSTRUCTION_ID_IMPLEMENTATION.md` | 2026-11-04 | Offline implementation evidence only. |
| `docs/reviews/C_MIN_IMPLEMENTATION_SECURITY_REVIEW.md` | 2026-11-03 | Security review of offline C-min implementation; live remains separate. |
| `docs/reviews/C_MIN_OFFLINE_IMPLEMENTATION_RESULT.md` | 2026-11-03 | Offline implementation/verification complete; live execution held. |
| `docs/reviews/C_MIN_OWNER_APPROVAL.md` | 2026-11-03 | Owner's bounded C-min approval record; defines implementation scope. |
| `docs/reviews/C_MIN_RUNTIME_ACL_LEASE_IMPLEMENTATION.md` | 2026-11-04 | Offline ACL/lease implementation evidence; no live use authorization. |
| `docs/reviews/C_MIN_RUNTIME_INPUT_BINDING_DESIGN_REVIEW.md` | 2026-11-03 | Independent design review; not runtime readiness. |
| `docs/reviews/C_MIN_RUNTIME_INPUT_BINDING_IMPLEMENTATION.md` | 2026-11-03 | Offline input binding implementation, native extension held. |
| `docs/reviews/C_MIN_TRIAL_HISTORY_RECONCILIATION.md` | 2026-11-04 | Historical trial disposition/reconciliation; attempts preserved. |
| `docs/reviews/CI_AND_DELIVERY_PREPARATION_REVIEW.md` | 2026-11-03 | CI/delivery preparation review; does not prove remote main. |
| `docs/reviews/EXISTING_AUTH_FILE_OFFLINE_IMPLEMENTATION.md` | 2026-11-03 | Narrow offline existing-auth implementation evidence. |
| `docs/reviews/LOOP_30M_LAUNCH_READINESS.md` | 2026-11-05 | Real launch rejected at boundary; readiness not achieved. |
| `docs/reviews/MAIN_TRIAL_OFFLINE_IMPLEMENTATION.md` | 2026-11-03 | Offline Main delivery implementation; no live activation. |
| `docs/reviews/MODEL_BOUNDARY_DESIGN_REVIEW.md` | 2026-11-03 | Independent C-min design review for owner consideration/offline scope. |
| `docs/reviews/OFFLINE_GITHUB_PROTOCOL_BACKEND.md` | 2026-11-03 | Offline GitHub protocol adapter validation; hosted API semantics remain open. |

No files were found under `docs/operations/`, `docs/security/`, `docs/governance/`, `docs/dependencies/`, `.bootstrap/`, `docs/reviews/` or `docs/plans/agent-work/` outside the paths explicitly listed in this register. All source families named in the task brief are represented above. Detailed test/CI file inventory and phase transitions are in the roadmap; AUD-2's traceability matrix should reference these stable IDs.
