# PH2-2AR — Independent read-only review of the integrated slice 2a (agent registry)

Agent: append your progress under "## Progress" below. You are a REVIEWER: do
not modify any file other than this one (your progress notes), do not spawn
agents, do not push, do not create a persistent worktree. Work in the main
checkout read-only.

## Task brief

Review the integrated slice 2a at `loop/local-development` HEAD 282e864 or
later: commit `e711c0c` `feat(agents): workspace policy and agent registry
metadata (slice 2a)` (backend/app/agents/__init__.py + registry.py 671 lines,
backend/app/main.py +114, tests/test_agents_registry.py 353 lines), produced by
PH1-2A, integrated after branch CI all green (475c153) and full local regression
(1136 passed/9 skipped).

Review against:
1. `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` — the "Slice 2a" content
   list and EVERY acceptance bullet (immutable versioned policies; admin-only
   writes with role ceilings + audit; explicit dispatch/admission rejection
   while B6 is active tested by the rejection itself; unknown-capability 422 +
   audit; `adapter_credentials` provably stores no secret material).
2. `docs/architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md`
   (ACCEPTED): B1–B7 boundaries, fail-closed behavior, Plane-M/Plane-R module
   separation — especially that `backend/app/agents/` does not import Plane-M
   model-path modules (`service.py` model/chat paths, `local_model.py`,
   C-min gate modules).
3. The owner's §6 answers (2026-11-07): presence-only credentials, `allowlisted`
   non-operative placeholder (default deny), NO receipt-resolution behavior (the
   job-approval ADR is not drafted), no dispatch/execution/activation of anything.
4. Security adversarial pass: authorization on every admin path, injection,
   audit accuracy (metadata-only, in-transaction), rate limits, IDOR on
   workspace/adapter/policy ids, policy immutability bypass, secret-material
   leakage.
5. Spot-check at least 10 code paths against the actual repository files.

Verdict: accept / accept after minor fixes / needs major rework. Findings with
severity (critical/high/medium/low), location, evidence, fix recommendation.
Do not edit anything except this file.

## Progress

- 2026-11-09 — Independent read-only review completed against integrated commit
  `282e864` (feature commit `e711c0c` is an ancestor); checkout HEAD was
  `263014b`. Reviewed the slice-2a design/acceptance and its owner decisions,
  accepted ADR-0012, implementation, endpoint wiring, existing auth/audit/rate
  limit helpers, and all 10 new registry tests. Ran the focused suite:
  `pytest tests/test_agents_registry.py -q` — **10 passed**. No files other than
  this review brief were changed.

  **Findings**

  1. **MEDIUM — unauthenticated and non-admin admin-path requests bypass the
     registry rate limit and can grow the persistent audit table.**
     `backend/app/agents/registry.py:235-249` authenticates and checks
     `system_admin` before calling `limit`; on failed authentication or role
     checks it writes an audit event and exits. `AgentRegistry._db` commits
     `_AuditedDenial` at lines 188-201. Therefore repeated anonymous requests
     (including safe-method list routes) and repeated authenticated non-admin
     requests can each create a durable audit row without hitting the
     `agent-admin:<actor>` limit. In addition, malformed writes can fail FastAPI
     body validation before the handler calls `_admin`; e.g. an anonymous
     `POST /api/admin/agent-adapters` with `{}` receives 422 and is not audited,
     rather than the acceptance-specified 401/403 audited denial. These are not
     authorization bypasses, but permit audit-store growth/availability pressure
     and leave some rejected admin writes without an audit record.
     **Recommendation:** apply an appropriate pre-authentication/peer or global
     limiter to rejected attempts (and a bounded audit strategy that preserves
     useful evidence), authenticate before body validation where feasible, and
     add regressions for anonymous/non-admin floods and malformed unauthenticated
     writes. Do not rate-limit only after successful admin authentication.

  **Acceptance and adversarial checks:** Workspace policy edits insert a new
  `(policy_id, version)` and CAS-update the workspace in one transaction;
  SQLite update/delete/duplicate-insert triggers protect prior versions, and
  bindings retain exact policy versions (`registry.py:82-109, 347-395, 464-519`;
  tested in `tests/test_agents_registry.py:test_workspace_policies_are_immutable_versioned_and_bindings_keep_version`).
  Every admin handler reviewed delegates to registry methods that call `_admin`;
  session authentication and admin-role checks occur inside the serialized DB
  transaction, all SQL values are parameterized, rate limits are applied to
  authenticated admins, and mutation plus audit share a transaction. Audit
  rollback is covered by `test_audit_failure_rolls_back_registry_mutation`.
  Unknown capabilities fail with 422 and a metadata-only denial event; the
  explicit dispatch route audits and returns 409 with a registered Runner
  present, before receipt/artifact writes. `allowlisted` is rejected by the
  policy validator and absent from enabling schema values. Credentials are
  limited to `(runner_instance_id, adapter_id, state, checked_at)` and the
  startup schema guard uses `table_xinfo`; its regression detects an added
  secret-named column. No credential processing, receipt resolution, runner
  execution, adapter enablement, or egress path was found.

  Spot-checked more than 10 paths against repository source: workspace create,
  list, policy-version update/list, workspace disable; adapter register, list,
  disable; runner create, list, disable; binding create, list, disable; dispatch
  rejection; and the registry initialization/audit/rate-limit helpers. All use
  placeholders for SQL values; dynamic SQL column selection in
  `_disable_bindings` is restricted to a fixed internal allowlist. No IDOR or
  SQL injection path was found in this admin surface. `backend/app/agents/`
  imports only stdlib and FastAPI and receives auth/audit/limit via narrow
  injected callbacks; the AST regression checks it for Plane-M imports and
  common dynamic-import escape hatches. This satisfies the slice's current
  Plane-M import prohibition; it is not the whole-package cross-plane graph
  check required for later runtime slices. ADR-0012 B5's cryptographic runner
  enrollment and other activation gates are not implemented here, consistently
  with the no-activation scope; the `registered` metadata state must not be
  treated as proof of enrollment by future dispatch-capable code.

  **Verdict: accept after minor fixes** — no critical/high finding and the
  specified metadata-only acceptance bullets are substantially met. Address
  the MEDIUM unauthenticated-denial audit/rate-limit gap before treating this
  security surface as hardened; retain all B5/activation checks as hard gates
  for later slices.
