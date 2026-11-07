# PH1-F — hybrid step-2 design proposal (Agent Registry / common adapter / workspace policy)

Branch: `loop/PH1-F-hybrid-step2-design` (worktree
`.loop/runtime/worktrees/PH1-F-hybrid-step2-design`, created from `loop/local-development` @ 102adaf).
TaskId: `ph1-f-step2-design-001`. Design-only task: no application code changes.

## Task brief

Step 2 of hybrid 実装順 (`docs/planning/locus-hybrid-agent-requirements.md`), unlocked
after step 1 (`docs/security/HYBRID_AGENT_THREAT_MODEL.md`) was independently reviewed
and accepted (slot E, verdict "accept after minor fixes", fixes applied in 307a5bb).

Deliverable: `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` — a review-ready
DESIGN PROPOSAL (not an approved ADR) covering:

1. Module boundaries keeping the ADR-0011 / C-min model-facing zero-tool boundary
   intact — the file-editing/tool-executing Agent Runtime lives in a separate,
   separately-audited module tree (`runner/` + `backend/app/agents/`), never merged
   into the existing C-min model-facing path.
2. Registry/adapter data model and lifecycle: registration, capability declaration,
   health, credential handling per 要件5 (official CLI login, credentials on the user
   device, no repurposing).
3. Workspace Policy model and enforcement points (runner selection, data
   classification, network/data-scope limits) mapped to the threat model's
   T-S1…T-E4 mitigations.
4. Integration plan with the existing Loop Controller, QA, independent review, Git
   operations and CI.
5. Phased delivery slices (2a/2b/2c) with acceptance criteria and a regression-test
   plan.
6. Explicit 【要決定】 owner-decision items (credential storage details, container
   isolation technology, remote deployment, runner trust root, audit-log protection,
   cloud-egress criteria, real-data activation, runner admission limits, provider
   subscription verification) — none decided by the proposal.

Constraints honored: no code changes; no boundary weakening; nothing pushed to
`main` or `loop/local-development`; no subagents; CI evidence recorded as blocked
(never passed) per `docs/plans/agent-work/ORCHESTRATOR_LOG.md`.

## Progress

- 2026-11-07: Read governance (`AGENTS.md`, `docs/governance/DEVELOPMENT_POLICY.md`,
  `docs/governance/GITHUB_WORKFLOW.md`, `docs/architecture/ARCHITECTURE.md`, all ADRs
  0004–0011), `docs/security/THREAT_MODEL.md`, `docs/security/HYBRID_AGENT_THREAT_MODEL.md`
  (accepted step-1 review), `docs/planning/locus-hybrid-agent-requirements.md`,
  `docs/plans/PHASE_SPEC_RECONCILIATION.md`, `docs/plans/agent-work/ORCHESTRATOR_LOG.md`,
  `docs/plans/MODEL_BOUNDARY_FINAL_DESIGN.md` (support/authentication conditions), and
  the actual code: `loop_engine/` (toolless_boundary, c_min_runtime, codex_runner,
  docker_boundary, app_credentials, windows_tcp_peer, catalog_snapshot, schemas),
  `backend/app/` (main startup holds, service roles/audit/chat_jobs, local_model),
  `tests/` layout.
- 2026-11-07: Created the worktree; drafted
  `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` with the dual-plane boundary rules
  B1–B7, registry/policy data model and lifecycle, enforcement map E1–E8,
  integration plan, delivery slices 2a–2c with acceptance criteria, and the 要決定
  inventory. Self-reviewed for consistency with the threat model's five consistency
  findings and the reconciliation doc; added the E8 row (T-S2/T-S3 coverage) in
  self-review. Boundary-change inventory recorded explicitly as empty (§7).
- 2026-11-07: Committed and pushed. Local verification for a docs-only slice:
  Markdown reviewed in full; no tests to run (no code changed); existing zero-tool
  regression tests untouched. GitHub Actions push verification: **blocked** by the
  account billing failure (per orchestrator ledger outage log) — recorded as
  blocked, never passed. Final SHA: see the commit line below.
- Final commit: `docs(plans): draft hybrid step-2 agent registry design proposal`
  on `loop/PH1-F-hybrid-step2-design`, pushed to origin. SHA: **(recorded in push
  output; see git log on the branch — task end)**.
