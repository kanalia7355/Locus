# ADR 0012 — Dual-plane boundary: model-facing gate and tool-executing Agent Runtime

Status: **ACCEPTED (owner approval, 2026-11-07).** The owner approved the dual-plane
boundary decision: Plane M's existing safety boundary is maintained; Plane R is
implemented as a separate Agent Runtime; rules B1–B7, fail-closed behavior and
static import-graph checks are mandatory; ADR approval and runtime activation are
explicitly separate. This record still approves no activation: every activation
step requires its own audited package, verification gates and separately recorded
evidence (ADR-0006/0009/0011 pattern). Slices 2a implementation is authorized;
dispatch-capable code still requires the separate approval ADR.

## Context

[ADR 0011](../ADR-0011-model-facing-zero-tool-gate-proposal.md) accepts the
C-min model-facing zero-tool boundary for normal-development design and offline
implementation only. Its normative rule is to reject nonempty model-facing tool
declarations (rather than strip them), enforce the pinned standard/Responses-Lite
contract, and reject tool-bearing responses before native dispatch. The strict
request/response enforcement is in `loop_engine/audit_transport.py` and
`loop_engine/model_gate.py`, wired by `loop_engine/c_min_runtime.py`;
`loop_engine/toolless_boundary.py` is a launcher/configuration and diagnostic
probe layer, not that enforcement gate. This acceptance is neither proof of live
runtime readiness nor approval of a product runner or its isolation.

The accepted-after-minor-fixes [hybrid threat model](../../security/HYBRID_AGENT_THREAT_MODEL.md)
identifies a consistency condition: ADR-0011 applies to model-facing requests,
while tool-executing Agent Runtimes must be separate, OS-isolated modules with
their own approval gates (consistency finding 1; threat T-E1). It lists this
dual-plane ADR as follow-up 2 and recommends it before any implementation of
hybrid step 2. The model-facing and runner-side planes are consistent only if a
runner's native CLI tools never become tool declarations on the model-facing
path.

The owner-added [hybrid agent requirements](../../planning/locus-hybrid-agent-requirements.md)
require preserving ADR-0011, separating and auditing file/tool-executing Agent
Runtimes, and not bypassing existing execution approvals or safety gates. The
reworked [step-2 design](../../plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md)
§§0–3 requires two module trees, boundaries B1–B7, a separate approval/authorization
ADR before dispatch-capable code, and fail-closed behavior until isolation and
other activation gates are verified. Owner approval and adoption of ADR-0012
are required before **any** step-2 implementation begins, including metadata-only
slice 2a; this is a hard sequencing prerequisite, not merely a recommendation.
Approval of ADR-0012 does not itself authorize step-2 implementation or activation.
The step-2 design's round-2 review returned **accept after minor fixes**; the
additional artifact source-deletion propagation requirement is included below.
This draft does not approve that design or decide any of its owner-marked
【要決定】 items.

The product remains synthetic-data-only. Design approval is not implementation,
operational readiness, live inference, or permission to process real research
data.

## Decision (proposed; pending owner approval)

Adopt the following dual-plane rule for hybrid-agent architecture. It preserves
the accepted C-min behavior and establishes a separate, fail-closed design
boundary for any future tool-executing Agent Runtime.

### 1. Plane M — existing model-facing path; frozen

Plane M is the model-facing request/response path protected by ADR-0011. Every
model-facing request must continue to carry zero tool declarations in all
supported protocol locations, including Responses Lite; tool-bearing or unknown
requests and tool-bearing responses must continue to be rejected before native
dispatch. No change to this behavior, its approved protocol contract, or its
existing regression tests is proposed here.

Plane M includes the applicable C-min gate path (`audit_transport.py`,
`model_gate.py`, `c_min_runtime.py`) and existing model-facing product paths.
The precise implementation map remains subject to the cited source files and
ADR-0011; this ADR does not move enforcement into `toolless_boundary.py` or
weaken the accepted gate.

### 2. Plane R — separate tool-executing Agent Runtime

Plane R is a future, separately audited runtime for official provider CLIs or
other explicitly approved adapters that execute their native tools inside an
OS-enforced workspace. It is not a mode of Plane M, and it is not an extension
that injects tools into Plane M. The proposed module trees are:

- `runner/`: runner host and adapter implementations, workspace enforcement,
  and transport client.
- `backend/app/agents/`: Control-Plane registry, workspace-policy and job
  metadata, and audit bridge. It performs no CLI/tool execution and constructs
  no model-facing request.
- `runner_contract/`: dependency-neutral, versioned transport DTOs/schemas;
  it imports neither the Control Plane nor the Runner.

**The two planes must remain separate module trees and must never be merged.**
Cross-plane communication is only through the authenticated, versioned transport
contract; there are no in-process calls, shared objects, or alternate channels.

### 3. Required boundaries (B1–B7)

These are proposed design constraints, not evidence that the corresponding
controls exist or are activated.

- **B1 — whole-package import isolation and transport-only communication.** No
  production module under `backend/app/` may import `runner/`, and no production
  module under `runner/` may import `backend/app/`. `backend/app/agents/` may not
  import Plane-M model-path code, including `backend/app/service.py`,
  `backend/app/local_model.py`, or C-min/model-gate modules under `loop_engine/`.
  Shared authorization/audit behavior must be exposed only through separately
  importable dependency-neutral primitives or narrow injected ports, never by
  importing mixed-purpose `service.py`. `runner_contract/` must itself import
  neither plane. A whole-package static import-graph test must check both
  prohibited directions, the Plane-M prohibition, the neutral-contract
  allowlist, transport-only communication, and unaccounted dynamic-import
  escape hatches.
- **B2 — registry neutrality.** Registry state is metadata (adapter descriptors,
  capability declarations, policy bindings, health and credential-presence
  state) only; it never stores, reads, exports, transmits or logs credential
  material or repurposes provider credentials as Locus authentication. Registry
  code neither constructs model-facing requests nor executes
  tools; registry compromise cannot create a tool-enabled Plane-M inference.
- **B3 — adapter separation.** The common adapter exposes only runner-side job
  execution (the proposed `run_job(job, workspace_policy)` operation). It has no
  operation for adding tool declarations to Plane-M. A provider CLI's native
  tools remain exclusively within Plane R.
- **B4 — closed shared contracts.** Cross-plane job, policy and health schemas
  are versioned and pinned. Unknown fields, unsupported versions, and contract
  upgrades not yet reviewed fail closed.
- **B5 — runner-instance identity.** Each Runner installation/process has an
  immutable, revocable `runner_instance_id` bound to its enrolled OS principal,
  pinned binary identity and transport identity. It is distinct from Control
  Plane and model-gate identities. Workspace binding, health and
  credential-presence metadata are scoped to `(runner_instance_id, adapter_id)`,
  never to `adapter_id` alone. Provider credentials remain in the CLI's
  supported device store; the tool-executing process receives no raw credential
  bytes and may use only a verified operation-scoped non-exportable broker/CLI
  mechanism. If that property cannot be verified for a platform/adapter, it is
  not activatable. The exact trust root and enrollment ceremony remain owner
  decisions.
- **B6 — fail-closed unproven boundary.** While verified OS isolation is absent,
  Plane R execution fails through an `UnprovenBoundary`-style guard; no host
  fallback is permitted. The Control Plane must explicitly reject every
  dispatch/enqueue attempt while B6 is active, including when a Runner is
  present. Absence of an installed Runner is not the rejection test. No runner
  execution is activated merely by approving this ADR.
- **B7 — audit plane.** Plane-R events must be attributed to the actor, workspace,
  destination, model and authorization decision and sent through a Control-Plane
  audit path. This does not claim that the existing metadata audit store is
  tamper-evident, confidential, access-controlled or retained safely. Protection
  of the product audit log remains unresolved and an activation blocker.

### 4. Approval, policy and artifact enforcement

The following fail-closed obligations apply to any later Plane-R design and
implementation. They preserve the reviewed step-2 corrections without selecting
an owner-controlled mechanism or policy value.

1. **A job-level authoritative approval receipt is a prerequisite.** Every job
   requires a current, non-revoked authoritative receipt bound to the job ID,
   actor, workspace ID, exact policy version, adapter, execution destination and
   operation. A role check alone, UI flag, client/runner claim, adapter status or
   old boolean is not a receipt. The Control Plane must verify the receipt and
   bindings immediately before enqueue; the Runner must independently recheck
   that same authority, receipt/revocation state and bindings immediately before
   execution. Denial, expiry, revocation, mismatch, policy change or unavailable
   authority means reject without enqueue or execution. The separate
   approval/authorization ADR must choose the issuer and trust, issuance, storage,
   expiry and revocation contract; it is a hard prerequisite to any
   dispatch-capable code.
2. **Classification defaults to deny-all and is independent of egress.** The
   proposed workspace classification ceiling defaults to `none`; unclassified
   or unclassifiable data is denied before prompt/context assembly and attachment
   loading, with no local fallback. Inputs, outputs, citations, logs and derived
   artifacts must retain known provenance, source ACLs and inherited maximum
   classification; missing provenance or a value above the explicit ceiling is
   denied. Classification authorization never implies destination authorization.
3. **Egress remains separately fail-closed.** `local_only` is the default. An
   `allowlisted` mode is non-operative pending the owner decision in step-2
   design §6.7; no enabling schema, policy value, or code may be introduced
   before that decision. Runner-to-Control-Plane intranet traffic is distinct
   from external sends; this distinction does not authorize external egress.
4. **Runner outputs are policy-checked artifacts.** An artifact must have
   verified integrity and identity/digest bound to its originating job, runner
   instance, workspace and policy version. It inherits source ACLs and maximum
   classification. Live policy, ACL, authorization and revocation must be
   revalidated before persistence, read/retrieval, reuse or export. Cross-workspace
   access, stale bindings, missing provenance, or classification downgrade is
   denied. Deletion or revocation of a source or workspace must invalidate
   derived artifacts before persistence/use/read/export; tests must cover source
   deletion and subsequent attempted reuse/export. Artifact retention and secure
   deletion policy remain owner decisions.
5. **Isolation, identity and audit remain activation gates.** OS/container
   filesystem and network enforcement must be verified inside the Runner before
   execution is enabled. Credential handling must prove both intended runner
   access and denial of credential read/export by the Control Plane, interactive
   user, other runner instances and compromised tool-executing process. Product
   audit-log protection (T-T4), classification/artifact checks and all required
   approvals must also be in place before activation. Existing development-loop
   Docker or Windows peer groundwork is not proof of product Runner isolation or
   user-vs-runner identity separation.

## Consequences

### What this makes possible

If separately approved and implemented, a Control Plane can manage runner and
workspace metadata while a separate Plane-R process runs an authorized CLI job
inside a verified workspace. It creates a clear place for runner-instance
identity, per-job approvals, policy gates, artifact checks and audit attribution
without adding tools to the model-facing protocol.

### What remains forbidden or inactive

This draft does not authorize changing Plane M, merging the module trees,
constructing tool-bearing model requests, dispatching jobs, executing a CLI,
using host fallback, or treating registry metadata as execution permission. It
does not approve external egress, credential extraction/transfer, live model
calls, real research data, or product Runner activation. Owner approval and
adoption of ADR-0012 must precede every step-2 implementation,
including metadata-only slice 2a. This sequencing approval is necessary but does
not itself authorize implementation or activation. The separate
approval/authorization ADR and all verification/activation gates remain
mandatory. Existing zero-tool tests must not be edited or weakened.

### Owner decisions deliberately left open

No 【要決定】 item in step-2 design §6 is resolved here. The design's mandatory
cancellation-safety semantics are requirements, not owner decisions: queued
cancellation atomically prevents dispatch; cancellation of executing work is not
terminal and does not release capacity until the Runner confirms termination;
dispatch/cancel races are serialized; repeated cancellation is idempotent; and a
timeout or missing acknowledgement fences the Runner/job and holds its
reservation until safe termination. The owner decides mechanisms and limits,
not whether these safety guarantees apply. In particular, the owner must still
decide or approve: (1) this ADR's content and adoption; (2) the per-platform OS
credential mechanism, runner principal, broker, health-check method and
access/denial evidence; (3) provider subscription-term verification; (4)
isolation technology per platform; (5) runner trust root, enrollment,
rotation/revocation and job freshness/signing contract; (6) product audit-log
protection and artifact retention/deletion policy; (7) whether any external
egress mode may ever be enabled and related wording; (8) admission limits,
fairness, cancellation actors and signaling mechanisms, timeout/recovery
mechanisms and limits; (9) real-data activation; (10) remote Desktop Runner
deployment scope; and (11) the separate job approval/authorization authority
and receipt contract. Refer to
[step-2 design §6](../../plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md) for the
full decision descriptions. No concrete issuer, trust root, provider, platform,
classification ceiling beyond the deny-all default, egress allowance, limit,
retention period or deployment scope is selected in this draft.

## Verification requirements

Before any Plane-R implementation or activation, the following regression and
verification plan is required. The checks below are acceptance criteria for
future work, not claims that they have run or passed here.

- Existing zero-tool regressions pass unchanged: `tests/unit/test_loop_tool_surface.py`,
  `tests/unit/test_loop_c_min.py`, `tests/integration/test_loop_c_min_launch.py`,
  and `tests/integration/test_c_min_public_reference_scan.py`.
- Whole-package static import-graph tests cover both Control-Plane/Runner
  directions, the `backend/app/agents/` → Plane-M prohibition, the neutral
  contract/primitive allowlist, transport-only communication and unaccounted
  dynamic-import paths.
- A dispatch/admission regression asserts explicit Control-Plane rejection
  while B6 is active **with a Runner present**; it must not pass merely because
  no Runner is installed. After the separate approval ADR permits dispatch-capable
  code, receipt tests cover denied, expired, revoked, stale-policy, mismatched
  binding and unavailable-authority cases at both enqueue and Runner execution.
- Classification tests deny unclassified inputs before context assembly and
  attachment loading and test all output, citation and artifact paths for
  inherited classification/ACL, missing provenance and downgrade. Artifact
  regressions cover integrity and job/instance/workspace/policy binding,
  cross-workspace access, policy/ACL revocation, source deletion, and attempted
  persistence, read, reuse or export after invalidation.
- Cancellation tests prove queued cancellation atomically prevents dispatch;
  executing cancellation remains non-terminal and retains capacity until
  Runner-confirmed termination; dispatch/cancel races are serialized; repeats
  are idempotent; and timeout or missing acknowledgement fences the Runner/job
  while retaining its reservation until safe termination. These semantics remain
  mandatory regardless of the owner-selected mechanisms, actors or limits.
- Runner-identity and isolation tests prove intended credential-operation access
  and denied read/export for each disallowed identity, verified filesystem/network
  enforcement, no host fallback, and dispatch rejection until the activation gates
  pass. Audit tests verify attribution and ensure that unresolved T-T4 controls
  remain an activation blocker.

## Review history

- Drafted 2026-11-08 from ADR-0011, the accepted-after-minor-fixes hybrid threat
  model, the reworked step-2 design and its PH1-H review history. PH1-H round 1
  returned **needs major rework** (4 high and 4 medium findings); the step-2
  design was revised before round 2.
- PH1-H round 2 returned **accept after minor fixes**: the eight round-1 findings
  were resolved in substance, with one medium follow-up requiring explicit
  artifact source-deletion propagation/tests and a low follow-up to record the
  round-2 history. This draft includes the source-deletion obligation and records
  no retention-policy decision.
- PH1-E2 review returned **accept after minor fixes** with two MEDIUM findings.
  This ADR-0012 fix cycle makes owner approval a prerequisite to all step-2
  implementation, including slice 2a, and distinguishes mandatory cancellation
  safety semantics from owner-selected mechanisms and limits; no owner items are
  decided.
- This ADR itself is a **DRAFT requiring independent review before owner
  approval**. It is not Accepted and approves no implementation or activation.
