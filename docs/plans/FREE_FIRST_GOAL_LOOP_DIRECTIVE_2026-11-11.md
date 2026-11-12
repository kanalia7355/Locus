# Locus final-goal development: free-first OpenCode + Codex orchestration

Status: operator execution intent recorded 2026-11-11. This document adds development-workflow requirements; it does **not** activate external credentials, network egress, runners, model-facing tools, or unapproved main integration.

## Goal and source hierarchy

Deliver the complete Locus application against the original design, not just a prototype or one phase. At the start of every work cycle read `docs/planning/` (especially `research-app-concept.md`, `ui-and-multiuser-design.md`, `UI_IMPLEMENTATION_BASELINE.md`, and `locus-hybrid-agent-requirements.md`), then consult `docs/requirements/`, `docs/architecture/`, `docs/plans/` and the current implementation. Use `MASTER_IMPLEMENTATION_ROADMAP.md`, `REQUIREMENTS_TRACEABILITY_MATRIX.md`, `FINAL_ACCEPTANCE_CRITERIA.md`, `PHASE_STATUS.md`, current Owner decisions and QA/CI evidence. Later decisions supersede only the precise earlier point they explicitly change. Keep product P0–P5, MVP-1–6, Loop L1–L6, hybrid H1–H6 namespaces distinct.

For the current product, finish permissioned research-document management, ingestion, retrieval/citations and analysis, multiuser workspace UI, administration, hybrid agent execution, and the approved automation loop; preserve the original final backlog even where prototype shortcuts or deferred gates exist. UI reference is the approved chat baseline; OpenCode can be evaluated for interaction patterns but does not override Locus security/UX decisions or justify copying code without a license check.

## Execution roles

- Codex/Controller hosts and supervises the durable goal loop. GPT-6.1 Terra is the requested orchestration role **if that model and a compliant execution integration are actually available**; do not claim this chat or another model is Terra.
- OpenCode CLI free models are the preferred implementation and first-line code-review resources. Do not assume any particular free catalog entry, fixed free quota, permitted data policy, or model entitlement. Discover models with `opencode models` / current model catalog and record provider, exact ID, eligibility, context/tool capabilities, health and limits. Use the strongest verified compatible available free model for each bounded task.
- GPT implementation fallback is permitted only when **all enabled, eligible OpenCode free implementation models** have actually been exhausted or are unavailable under a documented, bounded check; distinguish exhausted/quota-reset, transient errors, auth failure and model incompatibility. Recheck eligibility before switching; never simulate quota exhaustion. No new paid API usage or subscription purchase is authorized. If no already-authorized GPT route is available, queue the implementation task rather than incur charges.
- Skills can improve engineering process, but cannot guarantee free-model parity with GPT-6.1 Sol. Measure results with the same acceptance tests and independent review; do not make an unverified quality claim.
- Keep one implementation agent at a time. Independent review runs in an isolated read-only context; do not enable Superpowers' subagent execution patterns where they conflict with the repository's single-implementer policy.

## Skill and CLI bootstrap (first executable engineering task, not a terminal research report)

1. Inspect current `.agents/skills/`, AGENTS.md, OpenCode/Codex CLI versions, tool support, installed plugins, and live free model catalog. Keep existing skill files intact. Source: https://docs.opencode.ai/docs/skills/ and https://opencode.ai/docs/models .
2. Review upstream https://github.com/obra/superpowers and its OpenCode-specific installation guide https://github.com/obra/superpowers/blob/main/.opencode/INSTALL.md ; inspect current license/version, avoid unpinned supply-chain changes, and use the version-specific `plugin` (V1) or `plugins` (V2 >=2.0.4) configuration. Install only to the development CLI environment and after the allowed plugin/network/credential gates. Do not embed a speculative config that disables existing integrations. Verify actual skill discovery and a sample skill invocation.
3. Prefer existing repository `.agents/skills/` for goal planning, architecture review, task planning, implementation-loop, quality review, security audit, and decision triage. Add project-specific skill wrappers for repository reading, test-driven implementation, bounded debugging, review remediation, context compression, and evidence recording only when they provide measurable added value. Skills are on-demand and their invocation must be proven, not merely documented.
4. Prototype the exact OpenCode CLI adapter with structured subprocess invocation, exit/timeout handling, tool permissions, session persistence, output parsing, cancellation, usage/rate-limit accounting, audited model selection and safe fallback; reuse the existing Controller. Begin with synthetic tasks in an authorized isolated environment. A passing mocked test is not live CLI proof.
5. Verify a free-model worker on a real but non-sensitive bounded implementation task: failing regression first, code fix, static checks, functional tests, security checks when applicable, independent review, repair, and exact-head CI. Record model and skill versions, run logs without secrets, resource usage and acceptance evidence. Only then expand to other tasks.

## Unattended final-goal loop

`load durable goal -> inspect source, code and phase -> reconcile requirement gaps -> select highest-priority unblocked task -> implement -> test -> independent audit as required -> repair -> persist evidence -> integrate through currently authorized guarded path -> update version on fully audited phase completion -> next phase -> repeat`.

This is a **final-product Goal**. Intermediate phases are milestones, not terminal goals. Never return a research-only conclusion while authorized implementation, testing or repair is feasible. Do not confuse a task successfully dispatched with verified code changes.

Owner questions go into a durable decision queue containing the specific choice, rationale, options, recommended option, impact and blocked task IDs. Continue every independent authorized task; surface queued questions when the owner next chats or explicitly asks for them. Do not ask on every task. If a required decision blocks one workstream, do not treat it as global permission to stop other eligible work.

Bounded safety constraints remain: maximum three implementation attempts per task and two review remediation cycles; no infinite spin, quota-hammering, API abuse, unauthorized external communication, or guesses about side effects. Exhausted tasks become blocked with evidence and the scheduler proceeds to other eligible work. If no task is authorized/feasible, persist an explicit BLOCKED state and precise recovery steps: this is not successful final completion. The runtime must genuinely remain available for unattended work; a chat instruction alone does not create a background service.

At every phase boundary, prove acceptance + final phase audit + independent review + all required exact-HEAD CI + protected-main integration authorization and technical gate. Only after confirmed main integration bump the corresponding version according to repository conventions; preserve main safety requirements and proceed automatically to the next eligible phase. Do not push directly to protected main, forge review evidence, weaken tests, reset counters or infer authorization from this workflow document.

## Required implementation deliverables

- Versioned CLI adapter implementation and tests; actual verified free model selection and quota/fallback routing.
- Audited Skills installation/lock inventory and runtime discovery evidence.
- Durable goal scheduler and decision queue, including across-session resume, bounded retry and non-global blocking.
- Working application increments traced to the full original requirements and exact verified QA/CI SHA.
- Final end-to-end acceptance report that explicitly distinguishes prototype, synthetic, real-data, runner, egress, LAN and production evidence.

## Security boundary

This is an engineering **design/workflow directive**, not a grant of operational activation. Preserve ADR-0011 Plane-M zero-tool behavior and ADR-0012 Plane-R separation, dispatch refusal at B6, workspace authorization/receipt gates, OS isolation, official provider authentication, network/data classification controls, audited protected-branch merge and every Owner decision recorded in the repository. Owner approval of a skill/adapter design is not permission to run an untrusted plugin, transmit source to an external provider, supply credentials, access real research material, or start an unapproved Runner. In the meantime execute permitted offline/source-only engineering and synthetic tests rather than stopping at analysis.
