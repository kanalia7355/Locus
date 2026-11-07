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
pattern.

---

## 1. Module boundaries — the dual-plane rule (zero-tool boundary preserved)

### 1.1 Two planes, two module trees

The hybrid architecture has two fundamentally different execution planes. The design
keeps them in **separate module trees that must never be merged**:

**Plane M — model-facing request path (existing, unchanged).**
The C-min zero-tool gate and everything it protects:

- `loop_engine/toolless_boundary.py` — the model-facing protocol gate.
- `loop_engine/c_min_runtime.py`, `loop_engine/c_min_trial.py` — accepted C-min runtime scope.
- `loop_engine/catalog_snapshot.py` — pinned catalog verification.
- `loop_engine/model_gate.py`, `loop_engine/model_invocations.py` — model-slot invocation bookkeeping.
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
  and runner transport client (`runner/transport.py`).
- New control-plane package `backend/app/agents/` (proposed): Agent Registry
  (`registry.py`), Workspace Policy store (`policy.py`), dispatch job store (`jobs.py`),
  audit bridge (`audit.py`). **Metadata and bookkeeping only — never CLI execution,
  never model-facing request construction.**

### 1.2 Boundary rules (B1–B7)

- **B1 (import isolation).** `backend/app/` model/chat code must not import `runner/`;
  `runner/` must not import `backend/app/`. Control Plane and Runners communicate only
  through the runner transport designed in hybrid 実装順 3 — never in-process calls
  across the plane. `backend/app/agents/` may import only `backend/app/` service-layer
  primitives it extends (audit, roles), never Plane-M model path code.
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
- **B5 (process identity).** The runner process runs under a distinct OS identity from
  the Control Plane and the model gate relay (groundwork precedent:
  `loop_engine/windows_tcp_peer.py` kernel PID/SID binding). User-session and runner
  processes stay separated (T-E4). Exact enrollment ceremony 【要決定】.
- **B6 (fail-closed unproven boundary).** Until hybrid 実装順 3 lands verified OS
  isolation, the runner-side boundary uses the existing `UnprovenBoundary` pattern
  (`loop_engine/codex_runner.py`): every execution attempt raises without running.
  No host fallback is permitted — this is the same rule that keeps the development
  Loop honest today.
- **B7 (audit plane).** Plane R events are audited through the Control Plane audit
  bridge with the who/which-workspace/which-destination/which-model binding required
  by 要件6 (T-R1), reusing the metadata-only `_audit` pattern in `backend/app/service.py`
  plus the model/execution-destination dimension the threat model requires. Product
  audit-log protection (tamper evidence, confidentiality — T-T4) is unresolved
  【要決定】 and is not solved here.

### 1.3 Why this keeps ADR-0011 intact

ADR-0011's accepted scope concerns the **model-facing** protocol gate for the C-min
Loop: zero model-facing tool declarations, pinned Lite contract, rejection before
native dispatch. The hybrid Agent Adapter never touches that wire. Plane R CLIs run as
ordinary authenticated desktop processes executing their own native tools in an
OS-isolated workspace — exactly the "separate, OS-isolated module with its own
approval gates" that the requirements doc (`docs/planning/locus-hybrid-agent-requirements.md`,
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

- `loop_engine/toolless_boundary.py` and its accepted C-min composition — untouched.
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
- `workspaces(id, name, owner_user_id, policy_version_ref, runner_type, classification,
  created, updated)` — the workspace unit of 要件1 (Server/Desktop selection).
- `workspace_policies(id, version, classification_ceiling, runner_types, egress_mode,
  destination_allowlist, filesystem_scope, adapter_allowlist, deadline_seconds,
  concurrency_limit, created_by, created)` — immutable rows; a change creates a new
  version (T-T1/T-T2). Admin-only writable with role-ceiling rules (T-E2).
- `workspace_adapter_bindings(workspace_id, adapter_id, limits, enabled)` — which
  adapters a workspace may use, within what limits.
- `adapter_health(adapter_id, last_heartbeat, policy_version_echo, status)` —
  heartbeat with an echoed policy version (T-T1 freshness).
- `adapter_credentials(adapter_id, state, checked_at)` — **presence metadata only**:
  `state` ∈ {`enrolled`, `absent`, `revoked`}. No token material, no export, ever
  (§2.4). Pattern precedent: the OS-keystore-only rule of
  `loop_engine/app_credentials.py` (`WindowsAppVault` — "Windows Credential Manager
  only; never a plaintext/file fallback") and ADR-0010's narrow encrypted-cache scope.

### 2.2 Lifecycle states

```
registered → (health OK, binding enabled, policy match) → dispatchable
registered → disabled → dispatch-blocked (fail closed)
disabled   → deprecated (audit-kept, non-revivable without new approval)
```

Dispatch eligibility requires ALL of: adapter `registered`, heartbeat fresh with the
policy version the job binds to, workspace binding enabled, and policy adapter
allowlist match. Any miss ⇒ no dispatch (fail closed, T-T1). **The Control Plane never
dispatches to an adapter that failed a recheck** — the same pre-dispatch rejection
philosophy as the Plane-M gate.

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
- **Device-keystore storage.** Official CLI login remains in the CLI's own store on
  the user's device (Codex authentication record in the OS keyring per the ADR-0010
  investigation; Claude Code per its own official login — conformance check is
  実装順 5). Locus never migrates it into its own vault.
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

---

## 3. Workspace Policy model and enforcement points

### 3.1 Policy fields (要件1/2/3)

| Field | Meaning | Default (fail-closed) |
|---|---|---|
| `classification_ceiling` | Highest 要件3 level (公開/個人/研究共有/機密) this policy may touch | 機密 … but egress for anything above 公開 requires explicit allowlist ⇒ effectively deny |
| `runner_types` | Which runner types may execute here (server/desktop) | empty (no runner) |
| `egress_mode` | `local_only` \| `allowlisted` | `local_only` |
| `destination_allowlist` | Explicit outbound destinations when `allowlisted` | empty |
| `filesystem_scope` | Workspace directories the runner may touch | workspace dir only |
| `adapter_allowlist` | Which registered adapters are usable | empty |
| `deadline_seconds`, `concurrency_limit` | T-D1 admission bounds | smallest verified values (development caps, as with the `chat_jobs`/ingestion-queue dev caps) |
| `derived_classification` | Derived data inherits source classification; never downgrade (要件3, T-T3) | inherit-max |

Unclassifiable data ⇒ denied from any non-local path (要件3; T-I1). Documents are
untrusted content, never policy instructions (standing rule in
`docs/security/THREAT_MODEL.md`).

### 3.2 Enforcement points (mapped to the threat model)

| # | Enforcement point | Plane | Threat mitigated |
|---|---|---|---|
| E1 | Dispatch-time policy recheck on the Control Plane: job binds (workspace, policy_version, adapter, actor); version re-read before enqueue | C | T-T1 (stale policy/replay), T-R1 (attribution) |
| E2 | Runner-side admission recheck: revalidate job identity, expiry, policy version and workspace binding before any execution | R | T-T1, T-S1 |
| E3 | Capability ≤ policy at dispatch: an adapter's declared capabilities can only narrow the policy | C | T-E1, T-S3 (capability inflation) |
| E4 | OS/container enforcement of filesystem scope + network scope **inside the runner** (hook `runner/workspace_guard.py`): actual enforcement is hybrid 実装順 3's hard gate; until then B6 blocks all execution | R | T-E3, T-E4, T-D1 |
| E5 | Egress gate: `local_only` ⇒ any external send is technically impossible at the deployment layer AND denied at the application layer (mirrors the startup holds in `backend/app/main.py`); `allowlisted` ⇒ per-send audit record + exact allowlist match, fail closed | R+C | T-I1, T-R2 |
| E6 | Classification gate on inputs before any context assembly: unclassified ⇒ deny; RAG citations keep source ACLs (existing checks in `backend/app/service.py` `send`/`_citations` untouched) | C | T-I1, T-I4 |
| E7 | Admin surface ceilings: workspace/policy administration uses the existing role-ceiling rules (`NON_ADMIN`, `create_role`/`update_role` subset ceilings in `backend/app/service.py`) — a delegated admin cannot invent privileges | C | T-E2 |
| E8 | Session and adapter identity: existing opaque digested/expiring/revocable sessions carry over; the hybrid UI never embeds provider tokens in a Locus session; adapters are verified against pinned binary identity + catalog snapshot (B2 receipt pattern, §2.1) | C | T-S2, T-S3 |

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

No actual runner execution, no OS sandbox, no network filter. Slice 2 ships the
**model** (tables, versioning, checks) and its **enforcement hooks**, with dispatch
permanently fail-closed until 実装順 3 delivers verified isolation. This is the same
"design approved ≠ activated" discipline as ADR-0006/0009/0011.

---

## 4. Integration with the existing Loop Controller, QA, review, Git, CI

- **Loop Controller.** Zero changes to `loop_engine/controller.py`, `scheduler.py`,
  `run_authorization.py`, `approval.py` in this step. The registry/policy work is
  purely additive in `backend/app/agents/`. Future runner jobs are planned to reuse
  the Loop's authorization-then-act pattern (`loop_engine/run_authorization.py`,
  durable intents), but that reuse is a design input to the runner ADR, not something
  this step implements.
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
- **CI.** GitHub Actions is currently blocked by an account billing failure
  (`docs/plans/agent-work/ORCHESTRATOR_LOG.md` outage log). CI evidence for this task
  is recorded as **blocked, never passed**; local QA evidence is mandatory and
  sufficient for branch review only, not for any protected-branch claim.
- **Resource note.** Threat-model finding 4: agent concurrency must not share the
  model slot's queue semantics; the policy table's `concurrency_limit` is the future
  admission hook, inactive this step.

---

## 5. Phased delivery slices, acceptance criteria, regression plan

All slices: synthetic data only; no new Python dependency without a fixed, pinned
version (repo convention: locked requirements); no UI change.

### Slice 2a — Workspace Policy data model + registry tables (metadata only)
- Content: `workspace_policies`, `workspaces`, `agent_adapters`,
  `adapter_capabilities`, `workspace_adapter_bindings`, `adapter_health`,
  `adapter_credentials` tables; admin-path create/list/disable; full audit records.
- Acceptance:
  - Policy rows are immutable; edits create new versions; old bindings reference old
    versions (T-T1/T-T2).
  - Admin-only writes enforced with existing role ceilings; unauthorized writes 403
    and audited (T-E2).
  - Deny-by-default dispatch: zero eligible adapters ⇒ no job ever leaves the
    Control Plane (there is no runner yet — nothing can leave).
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
  - Interface exposes no tool-injecting operation for any model-facing path (B3) —
    verified by an import-boundary test (assert `backend/app/service.py` and
    `local_model.py` cannot import `runner/` or `backend/app/agents/` registry
    internals; B1 lint/test).

### Slice 2c — Classification plumbing into existing paths (minimal, Phase-3-aligned)
- Content: classification level on documents/index entries with inherit-max into
  citations/answers; unclassifiable ⇒ denied from any non-local send target. Hooks
  only — the full Phase-3 classification work remains there.
- Acceptance: private-by-default retrieval regressions unchanged and passing;
  new tests prove derived answers/citations never downgrade classification
  (要件3, T-T3).

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
- CI (GitHub Actions): blocked by billing ⇒ record "blocked", never "passed".

---

## 6. 【要決定】 items — owner decisions (this proposal decides none of them)

1. **Dual-plane ADR adoption** — whether the ADR described in threat-model follow-up 2
   (model gate vs. agent runtime) is drafted and approved before any slice 2b code.
2. **Credential storage details** — beyond the Windows Credential Manager precedent
   (`loop_engine/app_credentials.py`): per-OS keystore strategy for Desktop Runners,
   per-provider login verification method and whether health checks may probe
   authentication at all (§2.4).
3. **Provider subscription-term verification** — the exact receipt form required
   before an adapter can be enabled (要件5; §2.4).
4. **Isolation technology per platform** — OS/container enforcement for 実装順 3
   (T-E3/T-E4). `loop_engine/docker_boundary.py` is dev-loop precedent only, not a
   product decision.
5. **Runner trust root and enrollment ceremony** — enrollment, rotation, revocation
   (T-S1; ADR-0009/0010 precedent is narrow per the threat model), and job
   identity/freshness signing contract (T-T1).
6. **Product audit-log protection** — tamper evidence, access boundaries, retention,
   confidentiality (T-T4), separate from ADR-0010's cache scope.
7. **Cloud egress activation criteria** — when any `allowlisted` egress mode may
   exist, and ratification of the intranet-vs-external-send wording (§3.2).
8. **Plane-R admission limits** — deadlines/concurrency numbers and fairness for
   runner jobs (T-D1; §3.2 note).
9. **Real-data activation** — the standing synthetic-data-only rule continues until
   the owner approves production data handling (threat-model finding 5).
10. **Remote deployment scope** — whether Desktop Runners are ever reachable from
    outside the LAN and under what transport; nothing here enables it.

---

## 7. Findings requiring owner approval (boundary-change inventory)

This proposal introduces **no change to any approved boundary**. For the record:

- The zero-tool boundary, startup holds, approval gates and existing tests are
  preserved (§1.5). No test is deleted or weakened.
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

- Threat-model consistency finding 1 (dual-plane separation) ⇒ §1 is written as the
  design input for that ADR; adoption itself stays a 【要決定】 (§6.1).
- Finding 2 (local-only wording) ⇒ §3.2; flagged, not enacted as policy text.
- Finding 3 (approval-then-activation) ⇒ §0 and every slice is fail-closed until
  実装順 3; no slice claims activation.
- Finding 4 (model slot vs. agent concurrency) ⇒ §3.2, §4; separate admission design.
- Finding 5 (synthetic data only) ⇒ §0, §5.
- Reconciliation doc: this proposal does not declare any Phase complete, touches no
  approved verification contract, and keeps CI-evidence discipline (blocked ≠ passed).
- Requirements doc 整合 clause ("既存の実行承認・安全ゲートを迂回しない") ⇒ §1.5, §7.

End of proposal.
