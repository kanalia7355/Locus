# Final acceptance criteria

Authority: this is the final-design acceptance checklist derived from the approved product/security/governance sources and later owner-approved scoped extensions. Stable IDs and per-ID evidence are in [`REQUIREMENTS_TRACEABILITY_MATRIX.md`](REQUIREMENTS_TRACEABILITY_MATRIX.md); the original sources and gap boundaries are in [`REQUIREMENT_ID_SCHEME.md`](REQUIREMENT_ID_SCHEME.md), [`DESIGN_GAP_ANALYSIS.md`](DESIGN_GAP_ANALYSIS.md), and [`MASTER_IMPLEMENTATION_ROADMAP.md`](MASTER_IMPLEMENTATION_ROADMAP.md). Prototype satisfaction never silently closes a final or production condition. No proposed technology, sample UI content, capacity value, retention period, or other unapproved design choice becomes a criterion here.

**Status key:** `prototype-satisfied` = evidence satisfies only the expressly bounded approved prototype scope; `deferred-with-owner-approval` = the owner expressly approved deferral/exception while retaining a later condition; `open` = required final evidence and/or owner decision is outstanding. These status labels do not waive any criterion.

## Research support

| Final completion condition | Requirement IDs | Evidence class | Status |
|---|---|---|---|
| Deliver authorized research-data management and AI-assisted analysis with traceable source material; ingestion updates retrieval, not model weights; generated hypotheses remain suggestions, not verified findings. | PROD-001, PROD-006, DATA-002, DATA-011, UI-007 | End-to-end functional tests; source/citation review; UI review | open |
| Keep credits and billing UI absent. | PROD-008 | UI source review; regression/scope review | prototype-satisfied |
| Treat full autonomy, fine-tuning, unrestricted cloud, automatic privileged delegation, multi-organization federation, billing and production HA only as first-prototype exclusions, not presumed final exclusions. | PROD-009 | Source scope review; owner decision for any final exclusion | open |
| Provide lexical/provenance behavior that demonstrably links results to actual authorized indexed document/page/chunk content; do not claim lexical relationships are semantic GraphRAG or citations prove correctness. | DATA-003, DATA-004, UI-004 | Retrieval tests; ACL negative tests; source-link review | open |
| Complete structured comparisons, plots and approved research analysis from the original product scope; sample image/demo values are not acceptance requirements. | UI-007 | Functional tests; usability and security review of execution/input boundaries | open |
| Keep the assistant private by default; external AI/cloud routes only after explicit allowed-data and administrator/owner egress authorization and provider checks. | PROD-002, HBR-002, DATA-012, HBR-015 | Policy tests; deployment egress validation; provider evidence | open |

## AuthN, AuthZ and delegation

| Final completion condition | Requirement IDs | Evidence class | Status |
|---|---|---|---|
| Maintain unique managed identities, Argon2id password storage, one-time expiring temporary credentials, forced first-login rotation, secure recovery and session revocation; verify every live authorization path, including recovery and administrative mutations. | IAM-001, IAM-002, IAM-003, IAM-004, IAM-006, IAM-007 | Auth/API tests; database/storage inspection; independent security review | open |
| Establish the final MFA policy explicitly. The owner decision excludes MFA only from the LAN-limited prototype; it does not settle the production requirement. If required by that decision, implement and test it before production acceptance. | IAM-005 | Owner decision; auth tests; production deployment review | deferred-with-owner-approval |
| Separate organizations, projects and users with deny-by-default server authorization; enforce current ACL on every applicable data path, including histories, attachments, retrieval, graph/vector traversal, exports, caches, jobs and generated content. | IAM-006, IAM-007, IAM-008, IAM-009, DATA-004, UI-005 | Cross-user/tenant negative tests; API/data-path security review; integration tests | open |
| Provide built-in role templates and constrained customization/effective-access preview; concurrent-role composition must not create privilege escalation and explicit deny must override allow in its approved scope. | IAM-010, IAM-012, IAM-014 | Role/service tests; UI tests; independent authorization review | open |
| Keep delegation unavailable until the spec is owner-approved; then prove strict permission subset, scope, expiry, revocation, current membership/resource checks, no self/indirect escalation, transactional metadata audit, and interaction with explicit deny. | IAM-011, IAM-013 | Owner-approved spec; API/service adversarial tests; audit transaction tests; review | open |
| Preserve private history/attachments and audit security-sensitive actions without credentials or sensitive payloads; mutations and audit events must have the atomicity required by their approved source. | IAM-009, IAM-015, DATA-010 | Cross-user tests; audit redaction/rollback tests; code review | prototype-satisfied |

## Data and classification

| Final completion condition | Requirement IDs | Evidence class | Status |
|---|---|---|---|
| Bound upload types/sizes and safely parse/scan in isolated storage; fail closed when scanner is unavailable or uncertain; expose ingestion status and supported outcomes without unsupported ETA/capacity claims. | DATA-001, DATA-002, DATA-006, DATA-007, DATA-009, DATA-014 | Parser/scanner tests; operational scanner validation; ingestion E2E and failure/restart tests | open |
| Enforce provenance and live source ACL at every read/search/retrieval and propagate deletion, permission changes and source loss to chunks, citations, answers, caches, jobs and artifacts before later use/export. | DATA-003, DATA-004, DATA-005, IAM-008 | Adversarial ACL/revocation/deletion tests for every implemented path; independent security review | open |
| Preserve separation between personal, shared and conversation-attached material with no implicit publication; originals and source destinations retain their own ACL semantics. | DATA-008, DATA-010 | Source connector tests; ACL review; ingestion/deletion E2E | open |
| Enforce classification fail-closed for unknown/unclassified data; derived answers, citations, logs and artifacts inherit source ACLs and maximum classification. Classification does not itself authorize destination/egress. | DATA-012, HBR-003 | Classification propagation and negative tests across all paths; architecture/security review | open |
| Select production persistence/search and source storage only through owner decisions; implement production storage, backup/restore, retention and secure deletion for research data and generated outputs. No storage technology or retention period is inferred here. | DATA-008, DATA-013, DATA-015, PROD-005 | Owner decision; migration/backup restore drills; data deletion and retention verification | deferred-with-owner-approval |

## Hybrid agent platform

| Final completion condition | Requirement IDs | Evidence class | Status |
|---|---|---|---|
| Preserve Plane-M's accepted zero-tool request/response gate; keep tool-executing Plane R in separate module trees and communicate only over the reviewed, authenticated, versioned contract. | HBR-009, HBR-010 | Unchanged zero-tool regressions; whole-package import-graph/static analysis; contract tests; independent architecture review | open |
| Enforce organization policy ceilings over provider, execution location, network and data; user choices may narrow but never widen the policy. | HBR-001, HBR-002, HBR-003, HBR-008 | Policy/API/UI tests; end-to-end authorization review | open |
| Bind each Runner and adapter to immutable, revocable identity and provider-supported device credentials; never store or repurpose provider secret material in Locus; verify supported provider terms before activation. | HBR-005, HBR-015 | OS credential access/denial tests; provider documentation/terms evidence; independent security review | open |
| Record actor, workspace, destination/model and authorization for every invocation without sensitive payloads, using a protected audit plane. | HBR-006, IAM-015, IAM-016 | Audit-content tests; tamper/access/retention validation; security review | open |
| Require per-job authoritative approval bound to job, actor, workspace, exact policy version, adapter, destination and operation; revalidate before enqueue and execution. Outputs must be integrity/provenance bound and rechecked against live ACL/classification/policy/source deletion before persistence, use, read or export. | HBR-013, DATA-005, DATA-012 | Approval-receipt tests; artifact provenance/ACL tests; source deletion/revocation tests; independent review | open |

## Runner isolation and activation gates

| Final completion condition | Requirement IDs | Evidence class | Status |
|---|---|---|---|
| Enforce filesystem, process and network scope technically through a selected OS/container boundary; no prompt-only isolation or host fallback. Verify positive and negative identity/credential behavior on each activated platform. | HBR-004, HBR-005, HBR-007, HBR-010 | OS-level isolation/credential adversarial tests; platform deployment validation; independent security review | open |
| Authenticate Runner enrollment, transport, jobs, artifacts and logs; verify trust root, freshness, revocation, exact policy binding and source provenance before sensitive operations. | HBR-007, HBR-010, HBR-013 | Protocol/identity tests; negative stale/replay/revocation cases; deployment validation | open |
| Until all distinct approval and verified isolation/identity/classification/audit gates pass, explicitly reject every dispatch/enqueue attempt, including with a Runner present. A registered Runner, UI flag, or ADR approval is not activation authority. | HBR-011, HBR-012, HBR-013 | B6 rejection tests with a Runner present; gate/receipt review | open |
| Bound execution admission, deadlines and cancellation. Cancellation cannot release capacity until process termination is confirmed; timeout/missing acknowledgement must fail closed as required by approved hybrid design. | HBR-014 | Race/deadline/cancellation tests; process-containment review | open |

## Audit

| Final completion condition | Requirement IDs | Evidence class | Status |
|---|---|---|---|
| Keep events metadata-only and transactionally consistent with security-sensitive mutations where required; ensure failed operations do not create success events. | IAM-015, HBR-006 | Audit redaction/rollback tests; code review | prototype-satisfied |
| Before production/runtime activation, protect the audit log itself: appropriate confidentiality, access control, tamper/rollback evidence, retention and secure erasure. No retention period is assumed. | IAM-016, DATA-015 | Owner decision; operational retention/restore/tamper tests; independent security review | open |

## UI

| Final completion condition | Requirement IDs | Evidence class | Status |
|---|---|---|---|
| Preserve the user-selected chat baseline and accessible responsive behavior; attachments share picker/drop flow, preserve drafts, expose processing/failure and removal; show scope, source and generated-state disclosures. | UI-001, UI-002, UI-003, UI-004 | Visual baseline review; keyboard/mobile/accessibility tests; frontend component/E2E tests | prototype-satisfied |
| Ensure private per-user history and current source permissions when answers/citations are reopened; admin operations remain understandable and server-authorized. | UI-005, UI-008, IAM-007, IAM-008, IAM-009 | Multi-user E2E; permission/revocation tests; admin authorization and audit tests | open |
| Provide bounded multi-user queue/admission display, structured comparison/plots, and approved admin project/storage/load/delete flows with deletion safeguards. Do not state unmeasured capacity. | UI-006, UI-007, UI-008 | Functional and concurrency tests; usability/security review; operational measurement where capacity is claimed | open |

## Operations and deployment

| Final completion condition | Requirement IDs | Evidence class | Status |
|---|---|---|---|
| Production private-network deployment authenticates every client; apply TLS where applicable, private interface/firewall/allowlist and VPN for remote access; prove local-only outbound restrictions at deployment layer. | PROD-002, PROD-003, IAM-017 | Deployment/config inspection; network-egress and TLS tests; operational sign-off | deferred-with-owner-approval |
| Resolve and validate the production session lifecycle, including whether sessions persist across service restarts, plus approved secure cookie/TLS, expiry/revocation and recovery behavior. The Phase-1 prototype exception is not a production decision; persistence across restarts is explicitly a proposal pending source/owner confirmation, not an inferred approved implementation requirement. | IAM-004, IAM-017 | Owner decision; session-store/restart and deployment validation; auth security tests | open |
| Keep all systems synthetic-only until separate real-data approval and completed data-handling gates. Keep local-only and allowlisted egress behavior fail-closed until explicit activation approval and boundary verification. | PROD-007, HBR-002, HBR-003, HBR-011 | Owner approval record; deployment egress tests; classification/activation gate review | deferred-with-owner-approval |
| Validate actual production storage, scanner, parser, backup/restore, retention/deletion and supported-provider terms in the selected deployment rather than relying on mocks. | DATA-006, DATA-007, DATA-008, DATA-013, DATA-014, DATA-015, HBR-015 | Deployment/operations validation; restore and recovery drill; scanner/provider evidence | open |

## Quality gates and final release

| Final completion condition | Requirement IDs | Evidence class | Status |
|---|---|---|---|
| Preserve original approved requirements and their provenance; every requirement is traced to implementation, applicable tests, review, integration and explicit acceptance evidence. Proposals cannot weaken sources; skipped/unavailable checks remain skipped/blocked. | PROD-004, LOOP-003, LOOP-007, LOOP-010, GOV-001, GOV-004, GOV-005 | Complete traceability audit; immutable source/decision review; current-head QA and CI | open |
| For the autonomous Controller, satisfy the original live lifecycle: bounded execution, independent read-only review, hash-bound human approval, exact-head CI, safe recovery/delivery, conditional integration and post-merge Goal reassessment. Mocked stages are explicitly distinguished from live acceptance. | LOOP-001, LOOP-002, LOOP-003, LOOP-004, LOOP-005, LOOP-006, LOOP-007, LOOP-008, LOOP-009, LOOP-010, LOOP-011, LOOP-012, LOOP-013, LOOP-014, LOOP-015, LOOP-016, LOOP-017, LOOP-018, LOOP-020, LOOP-021, LOOP-022, GOV-002, GOV-003 | End-to-end live acceptance; independent security/quality review; exact-head hosted CI and delivery evidence | open |
| Resolve the conflict between local development-branch push policy, original PR/conditional-merge requirements and the 2026-11-09 phase/main rule through an authorized safe delivery policy; no direct main push or bypass. | LOOP-012, LOOP-013, LOOP-014, LOOP-019, LOOP-022, GOV-003 | Owner decision; protected workflow and exact-head CI; integration/version evidence | open |
| Maintain pinned dependency provenance and required quality/security checks; complete production distribution/license review before release. | GOV-006, LOOP-007, LOOP-011 | Dependency/SBOM/license and vulnerability reports; CI and independent review | open |
| Complete all applicable IDs, resolve blocking owner decisions and major findings, obtain final independent aggregate review, current required QA/CI and authorized release/version evidence. | All applicable IDs; PROD-004, LOOP-014, LOOP-018, GOV-004 | Final owner/independent acceptance; matrix audit; exact-head CI; integration/release record | open |

## Additions outside the approved sources

**Proposal, not an approved requirement:** the AUD-2 task brief expressly calls out “persistent sessions” as a production item, but the source survey did not locate an approved requirement that sessions persist across process/service restarts or specify a persistence mechanism. Owner confirmation is needed on whether restart persistence is intended. Until adopted, the final source-grounded condition is to decide and validate the production session lifecycle (IAM-004/IAM-017); no persistence technology, duration, or restart-survival behavior is assumed. This proposal does not weaken the explicit task requirement to track the decision as a final gate.

No other additional acceptance criterion is proposed. Any future requirement not traceable to the approved product/governance sources or a separately recorded owner-approved extension must be presented as a proposal and must not be treated as acceptance until adopted.
