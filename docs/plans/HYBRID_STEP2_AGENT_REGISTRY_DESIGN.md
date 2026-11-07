# Hybrid step 2 — Agent Registry, common Agent Adapter, Workspace Policy — DESIGN PROPOSAL

Status: **DRAFT DESIGN PROPOSAL (not an approved ADR; approves nothing, activates nothing).**
Date: 2026-11-07. Slot F of the Phase-1/hybrid pipeline (`docs/plans/agent-work/ORCHESTRATOR_LOG.md`),
task `ph1-f-step2-design-001`, branch `loop/PH1-F-hybrid-step2-design`.
Inputs: `docs/planning/locus-hybrid-agent-requirements.md` (owner-added hybrid spec, 実装順 2),
`docs/security/HYBRID_AGENT_THREAT_MODEL.md` (step 1, independently reviewed and accepted),
the ADRs under `docs/architecture/` (especially ADR-0011 and its accepted C-min scope),
`docs/plans/MODEL_BOUNDARY_FINAL_DESIGN.md`, `docs/plans/PHASE_SPEC_RECONCILIATION.md`,
and the current code at `loop/local-development` (102adaf).

This document is the design that hybrid 実装順 2 ("Agent Registry／共通 Adapter と
Workspace Policy の実装") would follow **if and only if** the owner adopts it and the
follow-up ADRs it feeds are approved. Every item marked 【要決定】 is an owner decision
that this proposal deliberately does not make. No sentence here may be read as
weakening an approved boundary; §1.5 lists the boundaries preserved verbatim.

---

## 0. Scope and non-goals

In scope (design only; **no application code changes in this slice**):

1. Module boundaries that keep the ADR-0011 / C-min model-facing zero-tool boundary intact.
2. Registry and adapter data model and lifecycle (registration, capabilities, health,
   credentials per 要件5).
3. Workspace Policy model and its enforcement points, mapped to the threat model's
   mitigations (T-S1…T-E4).
4. Integration plan with the existing Loop Controller, QA, independent review, Git
   operations and CI.
5. Phased delivery slices with acceptance criteria and a regression-test plan.
6. Explicit 【要決定】 inventory (§6) and findings requiring owner approval (§7).

Out of scope (later hybrid steps; this proposal only reserves hooks):

- Desktop/Server Runner authentication, isolation, transport and audit — 実装順 3
  (threat-model follow-ups 2/3: dual-plane ADR and runner-enrollment ADR).
- Codex CLI end-to-end validation in a personal workspace — 実装順 4.
- Claude Code / local-LLM adapter conformance — 実装順 5.
- Provider/model settings UI — 実装順 6 (Phase 4 UI track).
- Any live inference, credential read, external network send or real research data.
  Synthetic-data-only remains binding (threat-model consistency finding 5).

Approval-then-activation discipline (threat-model finding 3) applies: document
approval never activates anything; each future step needs its own audited package,
verification gates and separately recorded evidence, following the ADR-0006/0009/0011
pattern. The accepted threat-model recommendation is a hard sequencing gate: the
dual-plane ADR must be adopted and approved **before any implementation of hybrid
step 2 begins**, including metadata-only slice 2a. Separately, an approval/authorization
ADR is a hard prerequisite to any dispatch-capable code (enqueue, dispatch, or runner
execution); until it is approved, the Control Plane must reject dispatch. These are
prerequisites, not approvals granted by this proposal.

---

## 1. Module boundaries — the dual-plane rule (zero-tool boundary preserved)

### 1.1 Two planes, two module trees

The hybrid architecture has two fundamentally different execution planes. The design
keeps them in **separate module trees that must never be merged**:

**Plane M — model-facing request path (existing, unchanged).**
The C-min zero-tool gate and everything it protects:

- `loop_engine/toolless_boundary.py` — launcher/configuration and diagnostic-probe only; its probe is not C-min enforcement.
- Strict C-min request/response enforcement is in `loop_engine/audit_transport.py` and `loop_engine/model_gate.py`, wired by `loop_engine/c_min_runtime.py`; `loop_engine/c_min_trial.py` is accepted C-min trial scope.
- `loop_engine/catalog_snapshot.py` — pinned catalog verification; `loop_engine/model_invocations.py` — model-slot invocation bookkeeping.
- Product chat path: `backend/app/service.py` (`send`, `_citations`, `_generated`, `chat_jobs`
  queue) and `backend/app/local_model.py` (single-request Ollama adapter, no tools).
- Governing approvals: ADR-0011 accepted C-min scope, `docs/plans/MODEL_BOUNDARY_FINAL_DESIGN.md`,
  `docs/plans/MODEL_BOUNDARY_APPROVAL_PROPOSAL.md`.

In Plane M every model-facing request carries **zero tool declarations**, verified in
both standard and Responses-Lite locations, with rejection before native dispatch.
This plane is frozen by this proposal.

**Plane R — runner-side tool execution (new, separately audited).**
Official CLIs (Codex CLI, Claude Code) and local LLM runtimes that legitimately
execute files/commands inside an OS-enforced workspace:

- New top-level package `runner/` (proposed): the runner host process — adapter host,
  per-adapter modules (`runner/adapters/codex_cli.py`, `runner/adapters/claude_code.py`,
  `runner/adapters/local_llm.py`), workspace guard (`runner/workspace_guard.py`),
  and runner transport client (`runner/transport.py`). A separate, dependency-neutral
  `runner_contract/` package (proposed) contains only versioned transport DTOs/schemas;
  it imports neither application nor Plane-M code.
- New control-plane package `backend/app/agents/` (proposed): Agent Registry
  (`registry.py`), Workspace Policy store (`policy.py`), dispatch job store (`jobs.py`),
  audit bridge (`audit.py`). **Metadata and bookkeeping only — never CLI execution,
  never model-facing request construction.**

### 1.2 Boundary rules (B1–B7)

- **B1 (whole-package isolation and transport-only boundary).** No module anywhere
  under `backend/app/` may import `runner/`, and no module anywhere under `runner/`
  may import `backend/app/`. Control Plane and Runner communicate only by the
  authenticated, versioned transport protocol using `runner_contract/`; no in-process
  calls, shared objects, direct function calls or alternate data channel across planes.
  `backend/app/agents/` must not import Plane-M model-path code, including
  `backend/app/service.py`, `backend/app/local_model.py`, or C-min/model-gate modules
  under `loop_engine/`. Shared authorization/audit functionality must be exposed as
  separable, independently importable primitives or narrow injected ports/interfaces;
  the current `service.py` is not such a primitive because it combines model/chat,
  retrieval, audit and role logic. A whole-package static import-graph test must scan
  all production modules in both packages, check both prohibited directions and the
  Plane-M prohibition, permit only an explicit allowlist of dependency-neutral
  primitives/contracts, and reject unaccounted dynamic-import escape hatches.
- **B2 (registry neutrality).** The Agent Registry stores descriptors, capability
  declarations, policy bindings, health and credential *presence* metadata. It contains
  no code path that constructs a model-facing request and no code path that executes
  a tool. A registry compromise cannot produce an inference with tools (defends T-E1
  from the registry side).
- **B3 (adapter operation separation).** The common Agent Adapter interface defines
  exactly one execution operation — `run_job(job, workspace_policy)` — runner-side CLI
  execution with tools under OS enforcement. It defines **no** operation that injects
  tool declarations into any Plane-M request. Provider CLIs execute their own native
  tools inside Plane R; that must never be conflated with the Plane-M gate, which keeps
  rejecting all tool declarations.
- **B4 (shared contract discipline).** Any schema shared across planes (job envelopes,
  policy versions, health payloads) is a versioned, pinned contract validated with the
  existing pattern (`loop_engine/schemas.py` schema registry, catalog snapshots as in
  `loop_engine/catalog_snapshot.py`). Unknown fields fail closed. A contract upgrade
  fails closed until reviewed — same rule as the ADR-0011 parser-upgrade rule.
- **B5 (process and runner-instance identity).** Every Runner installation/process
  has an immutable, revocable `runner_instance_id`, cryptographically bound to its
  enrolled OS principal, pinned binary identity and transport identity. It is distinct
  from the Control Plane and model-gate relay identities; workspace binding, adapter
  health and credential-presence metadata are scoped to `(runner_instance_id,
  adapter_id)` and never to `adapter_id` alone. The identity must distinguish separate
  devices/process instances and support revocation (T-S1/T-T1/T-E4). The exact trust
  root/enrollment ceremony remains 【要決定】; `windows_tcp_peer.py` is only same-SID/PID
  groundwork, not proof of user-vs-runner separation.
- **B6 (fail-closed unproven boundary).** Until hybrid 実装順 3 lands verified OS
  isolation, the runner-side boundary uses the existing `UnprovenBoundary` pattern
  (`loop_engine/codex_runner.py`): every execution attempt raises without running.
  No host fallback is permitted — this is the same rule that keeps the development
  Loop honest today.
- **B7 (audit plane).** Plane R events are audited through the Control Plane audit
  bridge with the who/which-workspace/which-destination/which-model binding required
  by 要件6 (T-R1), reusing the metadata-only `_audit` pattern in `backend/app/service.py`
  plus the model/execution-destination dimension the threat model requires. Product
  audit-log protection (tamper evidence, confidentiality, access boundary and retention
  — T-T4) is unresolved 【要決定】 and is a hard activation blocker; this proposal does
  not claim the existing metadata log protects itself.

### 1.3 Why this keeps ADR-0011 intact

ADR-0011's accepted scope concerns the **model-facing** protocol gate for the C-min
Loop: zero model-facing tool declarations, pinned Lite contract, rejection before
native dispatch. The hybrid Agent Adapter never touches that wire. Plane R CLIs run
under a dedicated, per-instance OS identity and credential-broker boundary, executing
their own native tools only in a verified OS-isolated workspace — exactly the
"separate, OS-isolated module with its own approval gates" that the requirements doc
(`docs/planning/locus-hybrid-agent-requirements.md`,
整合 section) and the threat model (T-E1) demand. There is one corner to keep clear:
a model-inference call that is *part of a Plane-R job* (e.g. an adapter that asks a
local LLM a question) is **not** routed through Plane-M code. If such a call ever needs
the Plane-M gate, that is a new integration decision for the dual-plane ADR — see §7.

### 1.4 ADR-0011 rule that carries over into Plane R design (not a boundary change)

The owner-approved principle "reject nonempty declarations rather than stripping them"
(ADR-0011 normative scope) becomes the registry's capability rule: an adapter whose
capability declaration contains unknown or out-of-scope capability fields is
**rejected at registration**, never silently stripped (§2.3). This is policy-plane
reuse of the same fail-closed philosophy, not an edit to any accepted document.

### 1.5 Boundaries preserved verbatim by this proposal

- C-min's strict request/response gate in `loop_engine/audit_transport.py` and
  `loop_engine/model_gate.py`, wired by `loop_engine/c_min_runtime.py`, plus the
  launcher/configuration/diagnostic-only role of `loop_engine/toolless_boundary.py` —
  untouched.
- `backend/app/main.py` startup holds: `APP_ENV=development`, `ALLOW_CLOUD_EGRESS=false`,
  `LOCAL_ONLY_MODE=true` — untouched; no hybrid change relaxes them in this step.
- `docs/plans/MODEL_BOUNDARY_FINAL_DESIGN.md` support/authentication conditions —
  untouched; Plane R design cites them, never amends them.
- All zero-tool regression tests (`tests/unit/test_loop_tool_surface.py`,
  `tests/unit/test_loop_c_min.py`, `tests/integration/test_loop_c_min_launch.py`,
  `tests/integration/test_c_min_public_reference_scan.py`) — untouched; they must keep
  passing unchanged after every slice (§5.4).
- ADR-0006's binding note that the Windows sandbox diagnostic proved incomplete —
  untouched; the development-loop Docker boundary (`loop_engine/docker_boundary.py`,
  opt-in `tests/integration/test_live_docker_boundary.py`) is **not** evidence for
  Desktop Runner isolation (threat model T-E4), and this proposal does not claim it is.

---

## 2. Registry / adapter data model and lifecycle

### 2.1 Storage

New tables added by the `backend/app/agents/` package using the existing migration
pattern (the `CREATE TABLE IF NOT EXISTS` block style of `backend/app/service.py`;
the same SQLite control store — production DB migration 【要決定】 remains a Phase-3
open item in `docs/plans/PHASE_SPEC_RECONCILIATION.md` and is not reopened here):

- `agent_adapters(id, name, adapter_type, binary_identity, version_pin, catalog_ref,
  capability_declaration, status, registered_by, created, updated)`
  - `binary_identity` — pinned binary hash in the receipt style of
    `.loop/runtime/codex-client.json` consumed by `loop_engine/codex_runner.py`
    (`codex_binary`): hash + relative path, mismatch ⇒ SafetyError.
  - `catalog_ref` — catalog snapshot reference validated like
    `loop_engine/catalog_snapshot.py`.
  - `status` ∈ {`registered`, `disabled`, `deprecated`} — only the Control Plane
    admin path can mutate it; every change audited (T-T2).
- `adapter_capabilities(id, adapter_id, key, value, schema_version)` — normalized
  capability declaration (executes_tools, max_classification_honored,
  requires_device_keystore, network_destinations …). Unknown keys rejected at
  registration (§1.4).
- `runner_instances(id, enrolled_os_principal_ref, binary_identity, transport_identity,
  status, enrolled_at, revoked_at)` — one record per enrolled runner instance; never
  collapse distinct devices/process identities under an adapter or runner-type ID.
  The OS principal reference is non-secret metadata. Enrollment/trust root remain
  【要決定】.
- `workspaces(id, name, owner_user_id, runner_instance_id, policy_version_ref,
  runner_type, created, updated)` — workspace binding is to an instance, not just a
  runner type; workspace classification is policy-governed.
- `workspace_policies(id, version, classification_ceiling, runner_types, egress_mode,
  destination_allowlist, filesystem_scope, adapter_allowlist, deadline_seconds,
  concurrency_limit, created_by, created)` — immutable rows; a change creates a new
  version (T-T1/T-T2). Admin-only writable with role-ceiling rules (T-E2). The default
  ceiling is `none` (no permitted classification); `allowlisted` must not be emitted
  as an operative value or implemented in schema until its owner decision (§3.1/§6.7).
- `workspace_adapter_bindings(workspace_id, runner_instance_id, adapter_id, limits,
  enabled)` — binds a workspace to one enrolled instance and adapter.
- `adapter_health(runner_instance_id, adapter_id, last_heartbeat,
  policy_version_echo, status)` — instance-scoped heartbeat and policy echo (T-T1).
- `adapter_credentials(runner_instance_id, adapter_id, state, checked_at)` —
  **presence metadata only**: `state` ∈ {`enrolled`, `absent`, `revoked`}. No token
  material, no export, ever (§2.4); instance-scoped, not adapter-scoped.
- `job_authorization_receipts` (logical contract; concrete schema only after the
  approval ADR): authoritative receipt ID, job ID, actor, workspace, policy version,
  adapter, destination, operation, decision, issue/expiry times and revocation state.
  It is issued by the approved authorization authority, never client- or runner-asserted;
  it and the associated job envelope must be signature-verified or checked online with
  the authoritative issuer, under the trust contract selected by the ADR.
- `runner_artifacts` (logical contract; persistence schema only after artifact/security
  design): immutable artifact ID/digest/integrity proof, originating job, runner
  instance, workspace, exact policy version, source-data identities/versions, source ACL
  references and classification. Lifecycle is bound to the source data and exact
  workspace policy version. Deletion/revocation of any source or workspace, or a
  policy-version change, invalidates the artifact before reuse, export or read.
  Binding and enforcement are specified in §3.2/E9; physical deletion and retention
  timing/numbers remain 【要決定】 (§6.6).

### 2.2 Lifecycle states

```
registered → (health OK, binding/policy/receipt checks pass) → otherwise eligible
otherwise eligible → dispatch-rejected while B6 or either ADR gate is active
otherwise eligible → enqueue only after all gates and receipt recheck pass
registered → disabled → dispatch-blocked (fail closed)
disabled   → deprecated (audit-kept, non-revivable without new approval)
```

Normal dispatch eligibility would require ALL of: adapter `registered`; runner
instance enrolled, active and not revoked; fresh instance-scoped heartbeat with the
job's policy version; workspace-to-instance binding enabled; adapter allowlist match;
a valid signed/authenticated job envelope with replay/expiry checks; valid
classification and destination decisions; and a valid authoritative job approval
receipt. Any missing, denied, stale, mismatched or revoked input ⇒ Control Plane
rejects the job before enqueue and records a denial. The same receipt and bindings are
rechecked immediately before runner execution. A runner cannot substitute its own
receipt or trust a prior enqueue check. While B6 is active, **the Control Plane rejects
all dispatch/enqueue attempts by an explicit B6 gate**, regardless of whether any
Runner is installed; “no runner exists” is not an acceptable dispatch test. No dispatch-
capable code may be written until the separate approval ADR is approved (§0/§6.11).

### 2.3 Registration and capability declaration (admin operation)

1. Admin submits adapter metadata + pinned binary identity + catalog snapshot.
2. Registry validates the capability declaration against a **closed schema**:
   unknown fields, unknown capability keys or capability values that would widen
   any policy ceiling are rejected outright (not stripped — §1.4).
3. Registration writes an audit record (`adapter.register`) with the actor
   (`_audit` pattern, `backend/app/service.py`).
4. Registration does **not** contact the CLI, read any credential, or execute anything.

### 2.4 Credential handling (要件5)

Requirements text: official CLI login methods, credentials on the user's device by
default, no repurposing into Locus authentication; provider-specific subscription
terms verified per provider.

Design rules derived from existing accepted positions:

- **No Locus-side copy.** The registry records only `adapter_credentials.state`.
  It never reads, exports, transmits, logs or validates the value of a provider
  credential. This mirrors `loop_engine/app_credentials.py`'s OS-vault-only stance and
  the credential non-extraction clause of the accepted C-min design
  (`docs/plans/MODEL_BOUNDARY_FINAL_DESIGN.md`: the gate "never reads credential
  stores, exports tokens, calls login/refresh APIs" — cited, not amended).
- **No repurposing.** Provider credentials are never Locus session material, never
  API-key substitutes, never shared into the audit-relay path (ADR-0010 scope is the
  audit worker's cache alone — threat-model finding on ADR-0009/0010 narrowness
  respected).
- **Explicit OS identity boundary.** Only the dedicated, enrolled OS principal for a
  specific `runner_instance_id` may request an official CLI authentication operation
  from that instance's OS credential mechanism. The Control Plane identity, other
  runner instances, and the user's interactive-session identity may not read/use that
  store. The runner receives no raw credential bytes: a selected OS mechanism must
  provide a non-exportable, operation-scoped broker/CLI integration that denies
  credential read/export to the tool-executing process while allowing only the
  official CLI authentication operation. A compromised Runner must therefore have no
  API, file, memory-dump, or alternate path to export credential material; if the
  official CLI requires exposing exportable secret bytes to the compromised execution
  identity, that platform/adapter is not activatable. This is a required design
  property, not an established capability of Windows Credential Manager or the current
  code.
- **Device-keystore storage.** Official CLI login remains in the CLI's own supported
  store on the user's device (Codex per its supported OS keyring; Claude Code per its
  own official login — conformance check is 実装順 5), accessed only through the
  identity/broker boundary above. Locus never migrates it into its own vault.
- **Health without secrets.** Adapter health may verify "can this CLI authenticate"
  only through a runner-side, Locus-defined benign command whose result is a boolean
  and whose execution never surfaces credential material to the Control Plane, to
  logs, or to any model input. Exact verification method, and whether to verify at
  all 【要決定】.
- **Subscription terms.** Whether a provider's subscription permits this usage
  pattern must be verified per provider before any provider is enabled — 実装順 4/5
  gate; registry cannot enable an adapter without a recorded verification receipt
  【要決定】 on the acceptance form of that receipt.

### 2.5 Health

- Runners heartbeat; the Control Plane records freshness and the echoed policy
  version. A stale heartbeat, a version mismatch or a failed echo ⇒ adapter is
  non-dispatchable until fresh again (T-T1: no stale-policy execution).
- Health checks carry no job payload and no model content.
- Credential-presence and health records are keyed by runner instance + adapter and
  cannot be replayed across instances or workspace bindings.
- Runner activation stays blocked until the selected OS mechanism passes both positive
  tests (the intended runner identity can perform the supported authentication
  operation) and negative tests (Control Plane, interactive user, another instance,
  and a compromised tool-executing runner cannot read/export the credential). If no
  mechanism satisfies both access and denial, do not activate that adapter/platform.

### 2.6 Authoritative job-level approval receipt

Each job requires an authoritative, unexpired, non-revoked approval/authorization
receipt bound to **job ID, actor, workspace ID, exact policy version, adapter, execution
destination and operation**. The receipt records issuer/decision and issuance/expiry;
its source is the approved authorization authority defined by the separate approval
ADR, and the receipt/job envelope must be signature-verified or checked directly with
that authority under its approved trust contract. A UI flag, role check alone, client claim, adapter status, or an old job-level
boolean is not a receipt. The Control Plane resolves and rechecks the authoritative
receipt immediately before enqueue; the Runner independently rechecks the same
receipt/revocation state and every binding before execution. Denial, revocation,
expiration, policy-version change, workspace/adapter/destination/operation mismatch,
or unavailable authority ⇒ reject, with no enqueue/execution. Exact issuance,
signature/storage and revocation transport are 【要決定】 for that ADR. The ADR must
be approved before dispatch-capable code is implemented.

---

## 3. Workspace Policy model and enforcement points

### 3.1 Policy fields (要件1/2/3)

| Field | Meaning | Default (fail-closed) |
|---|---|---|
| `classification_ceiling` | Highest 要件3 level (公開/個人/研究共有/機密) this policy may touch | `none`: no classification permitted until an administrator explicitly selects a ceiling; missing/unclassified data is always denied |
| `runner_types` | Which runner types may execute here (server/desktop) | empty (no runner) |
| `egress_mode` | External-destination gate, independent of classification authorization | `local_only`; `allowlisted` is a non-operative placeholder conditional on owner approval, not an enabled enum/value |
| `destination_allowlist` | Exact outbound destinations, if a future egress decision approves a mode | none; do not create/populate an enabling policy/schema before §6.7 is decided |
| `filesystem_scope` | Workspace directories the runner may touch | workspace dir only |
| `adapter_allowlist` | Which registered adapters are usable | empty |
| `deadline_seconds`, `concurrency_limit`, cancellation | T-D1 admission bounds and cancellation lifecycle | no admissions while B6 is active; values and cancellation mechanism require owner decision (§6.8) |
| `derived_classification` | Derived data inherits the maximum source classification; never downgrade (要件3, T-T3) | inherit-max; missing provenance ⇒ deny |

Classification authorization and destination authorization are independent gates:
first every input/output must be classified and within the explicit ceiling; separately,
external egress must be permitted for that exact destination. Passing one gate never
implies passing the other. No data classification is eligible for external egress
until an owner-approved decision and its gates exist. This proposal considers only
`公開` data a possible future candidate; `個人`, `研究共有` and `機密` are never
eligible under this proposal. The owner may decide that even `公開` is not eligible.
No schema, policy value or code that enables `allowlisted` may be produced before that
decision.

Unclassifiable data ⇒ denied from every path before prompt/context assembly, including
attachment loading; it cannot be processed locally as a fallback. Any answer,
citation, log-bearing artifact, stored derivative, reuse or export path lacking known
provenance/classification is also denied (T-I1/T-I2/T-T3). Documents remain untrusted
content, never policy instructions (standing rule in `docs/security/THREAT_MODEL.md`).

### 3.2 Enforcement points (mapped to the threat model)

| # | Enforcement point | Plane | Threat mitigated |
|---|---|---|---|
| E1 | Control Plane verifies the signed/authenticated job envelope against the enrolled trust contract, rejects replay/expiry, and rechecks the authoritative receipt and exact bindings (job, actor, workspace, policy version, adapter, destination, operation) immediately before enqueue; denial, revocation, mismatch or unavailable authority rejects | C | T-T1, T-R1, approval gate |
| E2 | Runner independently verifies job-envelope authenticity/freshness and rechecks the same authoritative receipt/revocation state, runner-instance identity, policy version and workspace binding immediately before execution; stale/revoked/mismatched receipt rejects | R | T-T1, T-S1, approval gate |
| E3 | Capability ≤ policy at dispatch: an adapter's declared capabilities can only narrow the policy | C | T-E1, T-S3 (capability inflation) |
| E4 | OS/container enforcement of filesystem scope + network scope **inside the runner** (hook `runner/workspace_guard.py`): actual enforcement is hybrid 実装順 3's hard gate; until then B6 blocks all execution | R | T-E3, T-E4, T-D1 |
| E5 | Independent destination/egress gate: `local_only` ⇒ external send is technically blocked at deployment and denied in application; `allowlisted` remains non-operative until owner approval; any future permitted send needs exact destination match and per-send audit | R+C | T-I1, T-R2 |
| E6 | Classification gate before prompt/context assembly and attachment loading; unclassified or above-ceiling input denies. Recheck answer, every citation, generated output and all output paths; preserve inherited classification and source ACLs; no path may omit the check | C | T-I1, T-I4, T-T3 |
| E7 | Admin surface ceilings: workspace/policy administration uses the existing role-ceiling rules (`NON_ADMIN`, `create_role`/`update_role` subset ceilings in `backend/app/service.py`) — a delegated admin cannot invent privileges | C | T-E2 |
| E8 | Session and adapter identity: existing opaque digested/expiring/revocable sessions carry over; the hybrid UI never embeds provider tokens in a Locus session; adapters are verified against pinned binary identity + catalog snapshot (B2 receipt pattern, §2.1) | C | T-S2, T-S3 |
| E9 | Runner-output artifact gate: verify artifact integrity/signature and identity/digest bound to originating job, runner instance, workspace, exact policy version and source-data identities/versions; inherit source ACLs and maximum classification. Before persistence, reuse, export or read, revalidate live source existence/tombstone, ACL/revocation and workspace active/revoked/deleted state plus the exact policy version. Deletion/revocation of any source or workspace, or a policy-version mismatch, invalidates the derived artifact and denies the operation; also deny cross-workspace access and downgrade. Physical deletion and retention timing/numbers remain 【要決定】 (§6.6) | C+R | T-I2, T-T1, T-T3, 要件7 |

Two wording clarifications this proposal adopts (from threat-model findings 2 and 4),
flagged for owner ratification in §7:

- Runner↔Control-Plane traffic is **intranet** traffic, distinct from **external
  sends**; `LOCAL_ONLY_MODE` does not forbid it, and policies must say so explicitly
  to prevent future ambiguity.
- The `chat_jobs` single-model-slot serialization in `backend/app/service.py` protects
  local model capacity only. Plane-R job admission (deadlines, per-workspace/
  per-user concurrency) is a separate mechanism designed in this step's policy model
  and gated before any runner activation 【要決定】 on its limits.

### 3.3 What this step does NOT enforce

No actual runner execution, no OS sandbox, no network filter. No slice may implement
or enable dispatch before the dual-plane ADR (all step-2 implementation) and the
separate approval ADR (all dispatch-capable code) are approved. While B6 is active, an
explicit Control-Plane gate rejects every dispatch/enqueue attempt; test that rejection,
not the absence of a Runner. No execution, artifact persistence/use/export or egress
is activated by this proposal. Even after ADR approval, runner/artifact activation
remains blocked until verified OS isolation, credential access-and-denial tests,
classification/artifact enforcement, and T-T4 audit-log protection are in place. This
is the same "design approved ≠ activated" discipline as ADR-0006/0009/0011.

---

## 4. Integration with the existing Loop Controller, QA, review, Git, CI

- **Loop Controller.** Zero changes to `loop_engine/controller.py`, `scheduler.py`,
  `run_authorization.py`, `approval.py` in this design task. Future product-job approval
  must be authoritative and bound as in §2.6; Loop authorization code is a design
  precedent only and is not assumed to authorize product jobs. The dual-plane ADR must
  precede every step-2 implementation, and the separate approval ADR must precede any
  code capable of enqueue/dispatch/execution. Until then B6 is an explicit Control-Plane
  rejection gate.
- **QA.** New tests under `tests/unit/test_agents_registry.py`,
  `tests/unit/test_workspace_policy.py` (proposed names), run with the existing
  pytest suite; frontend untouched. All existing suites must keep passing unchanged.
- **Independent review.** Registry + policy is a significant architecture/data-model
  and security change ⇒ mandatory fresh-context read-only review before any merge,
  per `docs/governance/DEVELOPMENT_POLICY.md` and `docs/governance/GITHUB_WORKFLOW.md`
  (max two fix/re-review cycles).
- **Git operations.** No changes to `loop_engine/git_manager.py` / GitHub flows. This
  design slice commits only to `loop/PH1-F-hybrid-step2-design`; never to `main` or
  `loop/local-development`.
- **CI.** The earlier integrated HEAD had an account billing failure recorded in
  `docs/plans/agent-work/ORCHESTRATOR_LOG.md`. On fix-cycle commit
  `e8425bebf383dcf91ea376bcfbbcbe4d7c2d4627`, Actions did run and were not billing-
  blocked: the PR-title convention check succeeded, but Prototype quality failed on
  mypy at `backend/app/main.py:291` (`str | None` passed to a `str` parameter), and
  Loop engine checks failed the secret scan at `tests/test_chat_queue.py:218` (one
  finding; remaining matrix jobs were canceled). Thus full CI for that SHA is **failed,
  never passed**; these findings are outside this docs-only task and were not changed.
  Individual check success is not full verification or a protected-branch claim.
- **Resource note.** Threat-model finding 4: agent concurrency must not share the
  model slot's queue semantics; the policy table's `concurrency_limit` is the future
  admission hook, inactive this step.

---

## 5. Phased delivery slices, acceptance criteria, regression plan

All slices: synthetic data only; no new Python dependency without a fixed, pinned
version (repo convention: locked requirements); no UI change.

### Slice 2a — Workspace Policy data model + registry tables (metadata only)
- Content: `workspace_policies`, `workspaces`, `runner_instances`, `agent_adapters`,
  `adapter_capabilities`, `workspace_adapter_bindings`, instance-scoped `adapter_health`
  and `adapter_credentials` metadata; the logical job-receipt/artifact contracts from
  §2.1; admin-path create/list/disable; full audit records. Any concrete dispatch or
  receipt-resolution behavior remains gated on the approval ADR.
- Acceptance:
  - Policy rows are immutable; edits create new versions; old bindings reference old
    versions (T-T1/T-T2).
  - Admin-only writes enforced with existing role ceilings; unauthorized writes 403
    and audited (T-E2).
  - While B6 is active, an explicit Control-Plane dispatch/admission attempt is
    rejected before enqueue and audited even if a Runner is installed; this is not
    tested by relying on absence of a Runner.
  - If/when the separate approval ADR permits dispatch-capable code, enqueue rejects
    denied, revoked, expired, stale-policy or binding-mismatched receipts; runner-side
    execution independently rejects those same cases. Tests cover approval denial,
    revocation between enqueue and execution, and stale approval. These future tests
    cannot make dispatch active before the ADR gate.
  - Registration rejects unknown capability fields (§1.4) with a 422-style error and
    audit record.
  - `adapter_credentials` provably stores no secret material (grep-able schema check +
    code review).

### Slice 2b — Common Agent Adapter interface + health lifecycle (offline only)
- Content: the adapter interface contract (B3), an offline stub adapter for tests,
  heartbeat/policy-echo handling, health ⇒ dispatchability state machine, fail-closed
  `UnprovenBoundary`-style execution guard.
- Acceptance:
  - A stub "runs" only in tests; any attempt to execute outside tests fails closed
    (B6), verified by a regression test.
  - Stale heartbeat / version mismatch ⇒ adapter becomes non-dispatchable (T-T1).
  - Interface exposes no tool-injecting operation for any model-facing path (B3).
  - A whole-package static import-graph test scans all production modules and
    dependencies and verifies every B1 direction: `backend/app/**` never imports
    `runner/**`; `runner/**` never imports `backend/app/**`; Control Plane/Runner
    communication has only the transport protocol/shared dependency-neutral contract,
    never in-process calls; and `backend/app/agents/**` never imports Plane-M model
    path modules (`service.py`, `local_model.py`, or the C-min/model-gate path).
  - The test checks explicit allowed imports for separately importable authorization/
    audit primitives or injected ports, rejects imports of mixed-purpose `service.py`,
    and fails on unaccounted dynamic imports. This is a whole-package graph check, not
    a pair of file assertions.

### Slice 2c — Classification plumbing into existing paths (minimal, Phase-3-aligned)
- Content: classification on inputs, attachments and index entries; inherit-max into
  citations, answers and runner-output artifacts; ACL/classification enforcement at
  persistence, reuse, retrieval and export. Artifact lifecycle is bound to source-data
  identities/versions and the exact workspace policy version. Hooks only — the full
  Phase-3 classification work remains there. No classification ceiling means deny-all; unclassifiable input
  is denied before prompt/context assembly, with no local fallback.
- Acceptance: private-by-default retrieval regressions unchanged and passing. Negative
  tests deny unclassified input before prompt assembly, attachment loading and every
  answer/citation/output path. Tests prove derived answers/citations/artifacts never
  downgrade classification; artifact identity is bound to originating job, runner
  instance, workspace, exact policy version and source data; source ACLs are inherited
  and checked again before persistence/use/export/read. Regressions cover cross-workspace access; source
  deletion before persistence and after production (deny artifact read, reuse and
  export); source-ACL revocation after production; workspace deletion/revocation after
  production; and workspace-policy-version change after production.
  Additional regressions cover stale-policy and attempted-downgrade denial. Missing
  provenance or changed/revoked authorization denies the operation (T-I1/T-I2/T-T3);
  invalidation is checked before artifact payload access. Physical-purge and retention
  timing/numbers remain owner decisions (§6.6).

### 5.4 Regression-test plan (every slice)
- Full backend suite (`pytest` — existing `tests/` incl. `test_api.py`,
  `test_security.py`, `test_chat_queue.py`, `test_administration_audit.py`,
  `test_role_updates.py`, `test_custom_role_publication.py`, unit loop tests
  `test_loop_tool_surface.py` / `test_loop_c_min.py`) — all PASS unchanged.
- Frontend: `vitest` unit suite PASS (untouched code ⇒ unchanged counts).
- lint / typecheck / build PASS.
- secret scan: 0 findings.
- Zero-tool loop tests must pass **without modification**; any failure is a blocker,
  never a test edit.
- Hybrid regressions must include explicit B6 Control-Plane dispatch rejection with a
  present Runner, denied/revoked/stale approval at enqueue and runner execution,
  classification denial before prompt/attachment handling and all output/citation
  paths, and artifact cross-workspace/revocation/downgrade checks before
  persistence/reuse/export. Runner-instance OS credential tests must prove intended
  access and denied/export attempts for all disallowed identities. The whole-package B1
  import-graph test must cover every direction (§5.2b).
- CI (GitHub Actions): blocked by billing ⇒ record "blocked", never "passed".

---

## 6. 【要決定】 items — owner decisions (this proposal decides none of them)

1. **Dual-plane ADR content and approval.** The owner decides the ADR's exact
   architecture/contract, but not the accepted sequencing: it must be adopted and
   approved before **any** step-2 implementation, including metadata-only slice 2a.
   This is a hard gate, not an option to defer until slice 2b.
2. **Credential storage and runner identity details** — beyond the Windows Credential
   Manager precedent (`loop_engine/app_credentials.py`): select and test the OS
   principal/broker for each platform, including positive intended-runner access and
   negative Control Plane/user/other-instance/compromised-runner denial/export tests;
   choose per-provider login verification and whether health checks may probe at all
   (§1.2/B5, §2.4-2.5). Activation is blocked unless both access and denial pass.
3. **Provider subscription-term verification** — the exact receipt form required
   before an adapter can be enabled (要件5; §2.4).
4. **Isolation technology per platform** — OS/container enforcement for 実装順 3
   (T-E3/T-E4). `loop_engine/docker_boundary.py` is dev-loop precedent only, not a
   product decision.
5. **Runner trust root and enrollment ceremony** — enrollment, rotation, revocation
   (T-S1; ADR-0009/0010 precedent is narrow per the threat model), and job
   identity/freshness signing contract (T-T1); bind each identity to one runner instance.
6. **Product audit-log protection and artifact retention** — tamper evidence, access
   boundaries, retention, confidentiality (T-T4), plus retention/secure deletion for
   runner artifacts. T-T4 protection is a hard activation blocker, separate from
   ADR-0010's cache scope.
7. **Cloud egress activation criteria** — whether any `allowlisted` mode may ever be
   enabled and ratification of the intranet-vs-external-send wording (§3.1/§3.2).
   No operative `allowlisted` schema or policy may be produced before this decision;
   only `公開` could be considered by this proposal, and it is not pre-approved.
8. **Plane-R admission limits and cancellation** — deadlines/concurrency numbers,
   fairness and authorized cancel actors (T-D1). Required semantics: cancellation of a
   queued job is atomic and prevents dispatch; an executing job records a cancel request
   but is not reported terminal/capacity-released until the Runner confirms termination;
   races with dispatch are serialized; repeated cancellation is idempotent; a timeout or
   missing acknowledgement fences that runner/job and holds its admission reservation
   until safe termination is established. Future acceptance tests must cover cancel-before-
   dispatch, cancellation racing dispatch, idempotent repeats, runner acknowledgement,
   termination timeout and capacity not being released early. Select the signaling/
   termination mechanism, timeout and recovery process before activation.
9. **Real-data activation** — the standing synthetic-data-only rule continues until
   the owner approves production data handling (threat-model finding 5).
10. **Remote deployment scope** — whether Desktop Runners are ever reachable from
    outside the LAN and under what transport; nothing here enables it.
11. **Job approval/authorization ADR** — select the authoritative issuer and exact
    approval/revocation mechanism, receipt signature/storage and availability contract,
    actor/approver scopes, and policy on approval expiry. The receipt bindings and both
    recheck points in §2.6 are required; this ADR is a hard prerequisite to any
    dispatch-capable code, not an optional future refinement.

---

## 7. Findings requiring owner approval (boundary-change inventory)

This proposal introduces **no change to any approved boundary**. For the record:

- The zero-tool boundary, startup holds, approval gates and existing tests are
  preserved (§1.5). No test is deleted or weakened. The dual-plane ADR precedes all
  step-2 implementation; the approval ADR precedes dispatch-capable code; this draft
  adopts neither ADR. `allowlisted` egress remains non-operative and must not appear in
  an enabling schema/policy before owner approval (§3.1/§6.7).
- Two **wording** clarifications adopted from the threat model (§3.2 — intranet
  runner traffic vs. external send; model-slot vs. runner admission) are noted as
  requiring owner ratification because they touch policy text, not because they
  change code.
- If, during future implementation, anyone needs (a) a Plane-R adapter to route a
  model call through the Plane-M gate, or (b) any relaxation of B1–B7, that is a
  **new finding for the dual-plane ADR and the owner** — not a consequence of this
  document.

---

## 8. Self-review consistency notes (against the threat model and reconciliation doc)

- PH1-H finding 1 (classification fail-closed) ⇒ §3.1 defaults to `none`/deny-all,
  keeps classification and destination authorization independent, and §3.2/E6 plus
  slice 2c require denial before prompt/attachment handling and on all outputs/citations.
- PH1-H finding 2 (job-level approval) ⇒ §0, §2.2, §2.6, §3.2/E1-E2 and slice 2a
  require an authoritative receipt bound to actor/workspace/policy/adapter/destination/
  operation, checked before enqueue and runner execution; denial/revocation/stale tests
  are specified. B6 acceptance explicitly tests Control-Plane rejection. The separate
  approval ADR is a hard prerequisite to any dispatch-capable code.
- PH1-H finding 3 (runner artifacts) ⇒ §2.1, §3.2/E9, §3.3 and slice 2c define
  instance/job/workspace/exact-policy/source-bound artifact identity with inherited
  ACL/classification; revalidation before persistence/use/export/read. Source/workspace deletion or revocation invalidates artifacts; regressions deny
  stale artifacts before payload access. Physical deletion and
  retention timing/numbers remain owner decisions (§6.6); T-T4 stays an activation
  blocker.
- PH1-H finding 4 (runner identity/credentials) ⇒ §1.2/B5, §2.1, §2.4-2.5 bind
  workspace/health/credential presence to `runner_instance_id`; name the sole eligible
  OS principal and non-exportable broker requirement, with activation blocked pending
  positive access and negative denial/export tests.
- PH1-H finding 5 (dual-plane ADR timing) ⇒ §0 and §6.1 require the dual-plane ADR
  before **all** step-2 implementation, including 2a; this adopts the threat model's
  stricter sequencing rather than deferring only 2b.
- PH1-H finding 6 (`allowlisted` and cancellation) ⇒ §2.1, §3.1, §3.2/E5 and §6.7
  make egress a non-operative placeholder pending owner approval, bar enabling schema,
  and identify 公開 as the only possible future candidate (not pre-approved). §6.8
  adds explicit cancellation states, races, termination and capacity-release semantics.
- PH1-H finding 7 (C-min module map) ⇒ §1.1 and §1.5 identify
  `toolless_boundary.py` as launcher/configuration/diagnostic probe only and name
  `audit_transport.py` + `model_gate.py`, wired by `c_min_runtime.py`, as strict
  request/response enforcement.
- PH1-H finding 8 (B1 import boundary) ⇒ §1.2/B1 and slice 2b require the reverse
  Runner→Control-Plane prohibition, transport-only cross-plane communication, no
  Plane-M imports from `backend/app/agents/`, separable primitives/ports, and a
  whole-package static import-graph test covering all directions.
- Threat-model findings 2–5 remain preserved: intranet runner traffic is distinct
  from external egress (§3.2); approval-then-activation and synthetic-data-only apply
  to every slice (§0, §3.3, §5); Plane-R admission/cancellation is separate from the
  model slot (§3.2, §6.8). T-T4 remains an activation blocker (§1.2/B7, §3.3, §6.6).
- Reconciliation doc: this proposal does not declare any Phase complete, touches no
  approved verification contract, and keeps CI-evidence discipline (blocked ≠ passed).
- Requirements doc 整合 clause ("既存の実行承認・安全ゲートを迂回しない") ⇒ §0,
  §1.5, §2.6, §3.3 and §7.

## Review history

- 2026-11-07: PH1-H independent read-only review returned **needs major rework**
  (4 high + 4 medium findings). PH1-F fix cycle 1 revises the draft against all eight
  findings; see §8 for the finding-to-resolution map. Round 2 returned **accept after
  minor fixes**; fix cycle 2 addresses both minor findings. Per the reviewer's
  conditional verdict, the design is considered accepted after these fixes; final
  approval of the ADR remains the owner's. This history records the review
  outcome only; it does not approve an ADR, implementation, or activation.

End of proposal.
