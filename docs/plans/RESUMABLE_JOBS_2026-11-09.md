# Resumable jobs within the approved scope — 2026-11-09

**Authority:** owner's formal decisions [Q1–Q7](OWNER_DECISIONS_2026-11-09-EVENING.md), together with accepted ADR-0012 and the source requirements. This is a work inventory, not an implementation approval or activation record. “Can start now” means the bounded work below may proceed without waiting on unrelated open decisions; it does not waive a job-specific gate. Owner §4 unresolved items remain 【要決定】. No dispatch, Runner/isolation, external egress, provider credentials, real data or production exposure is activated here.

## Slot-assignment shape

Every package follows the same handoff sequence; actual slot/thread assignment is made by the controller and is not implied by this plan:

**implementation (author the scoped deliverable) → self-review (adversarial, source-linked) → QA (applicable checks and evidence) → delivery (Conventional Commit and authorized branch push) → integration (only after required independent review and exact-head CI).**

For design-document packages, “implementation” means authoring the design, not product code. A package is not complete on a proposed document alone: its completion gate below applies, and a later separately authorized implementation package must retain all source acceptance conditions.

## A. Receipt / hybrid step-2 (2b) design documents — DESIGN-READY

Q1 makes policy-driven automatic receipt issuance within an already approved Workspace Policy/scope an accepted direction; Q2 allows the verified personal Workspace owner to act within that same policy ceiling. The receipt contract and 2b design-document work can therefore resume now without resolving every receipt detail. These owner decisions do **not** approve or activate dispatch.

### R-2B-1 — Receipt contract and 2b design package

- **Scope:** Draft/reconcile the logical receipt and job-envelope contract against ADR-0012 §4.1, ADR-0013, and step-2 §§2.1/2.6/3.2/6.11. Trace the exact job, actor, workspace, policy-version, adapter, destination and operation bindings; define the control-plane and runner enforcement-point responsibilities; describe automated issuance only inside current policy and authority; document online/current authorization and audit requirements. Separate mandatory ADR-0012 semantics from contract details. Explicitly mark any unresolved owner choice rather than filling it in. This is documentation/design only: no receipt code, dispatch path, dispatch-capable tests, key provisioning, Runner, or schema enabling execution.
- **Owner decision relied on:** Q1 (automatic approval only inside a current, administrator-approved policy/scope); Q2 (personal Workspace owner authority stays within upper policy limits); Q4 only as the official-CLI/no-credential-mixing constraint where adapter context is documented.
- **Safety boundary that must not change:** ADR-0011 Plane-M zero-tool behavior; ADR-0012 dual-plane separation and mandatory authoritative receipt; E1 recheck before enqueue and independent E2 recheck before execution; B6 explicit dispatch rejection; default-deny/no-egress; fail-closed on denial, stale policy, mismatch, revocation or unavailable authority; no credential bytes or content in receipts/audit. The owner §4 receipt TTL values, new permissions/exceptions and other unresolved matters remain 【要決定】.
- **Completion gate:** source-linked, internally consistent design reviewed against ADR-0012/0013 and step-2, with every owner-controlled open point visibly marked 【要決定】 and no activation claim. **Any 2b dispatch-capable implementation remains blocked until the owner-approved receipt contract and separate slice authorization exist; dispatch stays disabled until the ADR-0012 activation gate and all its verification/authorization gates pass.**
- **Slot shape:** implementation → self-review → QA → delivery → integration.

### R-2B-2 — Contract details classed ENGINEERING_DETAIL

- **Scope:** Work only the receipt/2b details that `OWNER_QUEUE_CLASSIFICATION_2026-11-09.md` explicitly classifies as `ENGINEERING_DETAIL` and that do not depend on an unresolved owner choice. Candidate bounded design details include versioned DTO/error handling, audit event naming, immutable-state representation and metadata-only schema validation. Classification in that file is authoritative; this job must exclude any mixed/split row classified `OWNER_DECISION_REQUIRED` or `DEFERRED_WITH_GATE`. Do not turn a recommendation into an approved numeric TTL, trust root, new permission, offline path, or executable dispatch design.
- **Owner decision relied on:** Q1, with Q2's personal-workspace authority ceiling where relevant; Q4 preserves official adapter authentication without credential transfer.
- **Safety boundary that must not change:** All R-2B-1 boundaries; especially immutable/auditable attribution, policy/authority rechecks, B6, zero-tool Plane M, and the owner's unresolved §4 items.
- **Completion gate:** each item has a traceable engineering rationale, negative/fail-closed cases and review evidence; the classification row permits engineering treatment; any change affecting a boundary is returned for owner decision. Receipt approval and activation gates are still independently required before implementation/dispatch.
- **Slot shape:** implementation → self-review → QA → delivery → integration.

## B. Isolation-profile design documents — DESIGN-READY, activation excluded

### R-ISO-1 — Per-environment isolation profiles and proof plans

- **Scope:** Design a profile matrix for Windows/Linux and local/server environments, stating target/threat assumptions, controls, constraints, and profile-specific independent verification evidence. Compare VM and non-VM approaches without prescribing a universal VM. Provide negative/positive test plans for OS-enforced filesystem, process and network boundaries, cleanup, failure behavior and profile claims. Profile design and evaluation documentation may start; do not activate an unverified profile or perform a host execution.
- **Owner decision relied on:** Q3 requires environment-appropriate, independently verified OS-level isolation; no universal VM; an unverified environment remains unavailable. Q4 is an input to describe adapter constraints only, not credential use.
- **Safety boundary that must not change:** no unverified host-direct execution, silent downgrade, or weakening of ADR-0011/0012/B6; no egress, credentials, dispatch, or real data; default-deny and fail-closed remain. A design profile is not proof that a platform passes.
- **Completion gate:** per-profile design states enforceable boundary and limits honestly, with a source-grounded test/evidence plan and independent review. Each profile remains **inactive** until exact-platform/build/config evidence passes, required security review is accepted, and its separate activation decision and all ADR-0012 gates are satisfied.
- **Slot shape:** implementation → self-review → QA → delivery → integration.

### R-ISO-2 — Isolation engineering details classified ENGINEERING_DETAIL

- **Scope:** Produce comparison, test-inventory, evidence-binding, and profile-conformance details only for items explicitly labelled `ENGINEERING_DETAIL` in the classification record. Do not decide unresolved trust/enrollment/key custody, support authorization, provider credential supply, endpoint/egress, or risk acceptance for an unverified profile. The classifier's split rows and labels control scope.
- **Owner decision relied on:** Q3's approved per-environment verified-profile direction; Q4's official CLI preference does not authorize provider authentication or credentials.
- **Safety boundary that must not change:** independent proof for the exact environment; unverified profiles unavailable; no host fallback; no dispatch before the receipt and ADR-0012 gates; no egress or credentials.
- **Completion gate:** reviewed comparison/test criteria are reproducible, evidence-bound to the claimed environment, and do not claim profile activation. Any unresolved authority, trust or policy item remains explicitly gated.
- **Slot shape:** implementation → self-review → QA → delivery → integration.

## C. Storage: manual-upload-first work

### R-STORAGE-1 — Complete approved manual-upload research flow

- **Scope:** Resume only the already approved manual-upload path and its research-support acceptance: upload, safe ingestion, search/retrieval, citation/provenance, and analysis improvements grounded in existing requirements. Identify gaps from the current manual path and propose bounded work packages; implementation may cover those existing requirements without waiting for connector design. Do not remove or weaken research requirements because connectors are deferred.
- **Owner decision relied on:** Q5 prioritizes manual uploads and defers local-folder/NAS/online-storage connectors to a later phase; Q6 denies access immediately when source permission is lost and separates retention/deletion from access denial.
- **Safety boundary that must not change:** no connector, source credential, network access, external transfer or egress; preserve document/project ACLs, private-by-default personal documents, fail-closed scanner/parser behavior and live authorization. Revocation blocks read/search/citation/reuse, including existing derived answers; do not infer immediate physical deletion or upstream write/delete permission. Production stays deferred.
- **Completion gate:** each manual-upload change meets the existing product/source acceptance, preserves unconnected-document behavior and access-denial semantics, passes applicable backend/frontend/security QA and independent review where required, and has exact-head required CI. No production readiness or connector support is claimed.
- **Slot shape:** implementation → self-review → QA → delivery → integration.

## D. Additional ENGINEERING_DETAIL-classified work

### R-ENG-1 — Bounded engineering-detail work across DP-001…072

- **Scope:** The classification record [OWNER_QUEUE_CLASSIFICATION_2026-11-09.md](OWNER_QUEUE_CLASSIFICATION_2026-11-09.md) is the source of truth for which DP rows (including split rows) are `ENGINEERING_DETAIL`; its Group C inventory has none, so storage work in this plan is limited to Q5/Q6-approved manual-upload-first scope rather than inventing a connector engineering job. The classified rows relevant to design work are **DP-001, DP-002, DP-003, DP-007, DP-008, DP-009, DP-012, DP-013, DP-014, DP-016, DP-017, DP-019, DP-020, DP-023, DP-033, DP-042, DP-044, DP-045, DP-046, DP-047, DP-048, DP-049, DP-051, DP-052, and DP-053a**; DP-053b is separately `EXISTING_DECISION`. Start only rows whose dependencies and safety boundary permit work now; package by the receipt, profile, or manual-upload groups above. DP-046 numerical bounds inherit unresolved receipt TTL choices and cannot set them. DP-044/045/049 are contract-detail design only and require independent review; DP-053a evidence binding is design-only and does not activate a profile. Record technical options, evidence and consequences rather than introducing a new approval surface. Do not duplicate or override queue classifications.
- **Owner decision relied on:** Q1–Q7 only within their expressly approved scope; the owner's direction to continue approved-scope work and let the orchestrator propose/compare/verify engineering details subject to independent review.
- **Safety boundary that must not change:** no re-opening settled Q1–Q7; no resolving owner §4 questions by inference; no weakening ADR-0011/0012, B6, no-egress, least privilege, current ACL, metadata-only audit or fail-closed behavior. Design evidence never activates dispatch, isolation, credentials, egress, real data or production.
- **Completion gate:** the row is explicitly classified `ENGINEERING_DETAIL`; its source and approved boundary are cited; required tests/review pass; any emerging policy/scope choice is split out and returned as 【要決定】. Delivery/integration requires exact-head gates and authorized branch workflow.
- **Slot shape:** implementation → self-review → QA → delivery → integration.

## Explicit non-authorization and traceability

The companion [deferred-gates inventory](DEFERRED_WITH_GATES_2026-11-09.md) records work that cannot start until its stated trigger. This document changes no queue cell and does not classify or approve any row itself. Keep the proposal and source re-evaluations as recommendation history; retain the owner decision record and stable requirement IDs as authority. In particular, **2b/2c require the owner-approved receipt contract; dispatch remains disabled until the ADR-0012 activation gate; unresolved owner §4 items remain 【要決定】.
**