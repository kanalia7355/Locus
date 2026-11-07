# PH1-2A — Hybrid step-2 slice 2a: Workspace Policy data model + registry tables (metadata only)

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

Context: ADR-0012 is now ACCEPTED by the owner (2026-11-07) and slice 2a is
authorized. Your authoritative specification is `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md`
§6 (owner answers) and §"Slice 2a" (content + acceptance), at `loop/local-development`
HEAD 7453daf or later. Read also `docs/architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md`
(ACCEPTED), `docs/security/HYBRID_AGENT_THREAT_MODEL.md`, `AGENTS.md`, governance docs.

Scope (backend only, no frontend, no runner/ module tree yet):
- New metadata tables per the Slice 2a content list: `workspace_policies` (immutable,
  versioned), `workspaces`, `runner_instances`, `agent_adapters`,
  `adapter_capabilities`, `workspace_adapter_bindings`, instance-scoped
  `adapter_health` and `adapter_credentials` (presence-only; PROVABLY no secret
  material — add a schema/static check that fails if credential-value-like columns
  exist), and the logical job-receipt/artifact contracts as schema/metadata only.
- Admin-path create/list/disable endpoints with existing role ceilings
  (system_admin), audit records on every mutation, policy immutability (edits
  create new versions; old bindings keep old versions).
- Explicit Control-Plane dispatch/admission gate: while B6 is active every
  dispatch/enqueue attempt is REJECTED before enqueue and audited (do not test by
  absence of a Runner).
- Capability registration rejects unknown capability fields with 422 + audit.
- NO dispatch, NO runner execution, NO adapter activation, NO egress: `allowlisted`
  stays a non-operative placeholder (default deny), never produced in an enabling
  schema/policy value.
- The approval ADR (design §6 item 11) is NOT yet drafted; do not implement
  receipt-resolution behavior.

Constraints: follow existing service/main conventions exactly (serialized SQLite
transactions, metadata-only `_audit`, `_limit`, role ceilings). Keep changes inside
`backend/app/` (a new `backend/app/agents/` module tree may be created; it must NOT
import Plane-M model-path modules: `service.py` model/chat paths, `local_model.py`,
C-min gate modules — if you need auth/audit primitives, import only narrowly-scoped
primitives or duplicate minimal local helpers and record the judgement).

QA (repeat until ALL green): full pytest (tests -q --ignore=tests/e2e), ruff check
+ format --check, mypy backend/app, secret scan. Add regression tests for every
acceptance bullet.

Process: own worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-2A-registry -b loop/PH1-2A-registry origin/loop/local-development`; work ONLY inside it. Implement → adversarial self-review → QA → Conventional Commit (`feat(agents): workspace policy and agent registry metadata (slice 2a)`) → push → wait branch CI → fix/re-push until ALL checks green (bounded). Append progress + SHA + CI evidence here. After integration the orchestrator deletes your branch per policy.

Boundaries: never push to `main` or `loop/local-development`; no frontend; no
activation of anything; do not spawn subagents.
