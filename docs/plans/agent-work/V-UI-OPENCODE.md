# Slot V — UI Improvement & OpenCode Implementation Research

Model: GLM-5.3-Flash (thinking high) | Branch: loop/ui-research-opencode | Owner directive: 2026-11-11

## Objective
Advance the existing Locus UI toward a ChatGPT/Claude-like intuitive conversation experience combined with OpenCode-style advanced agent operability, on the existing React/TypeScript stack. Research OpenCode's implementation and produce the comparison + design + implementation plan; implementation follows in a later slot within approved scope.

## References
- OpenCode: https://github.com/anomalyco/opencode (dev branch: packages/app, packages/ui, packages/session-ui, packages/desktop)
- Locus approved baseline: docs/planning/UI_IMPLEMENTATION_BASELINE.md, docs/planning/ui-and-multiuser-design.md, frontend/src/App.tsx, frontend/src/styles.css
- Network use is limited to reading this one public repo at a fixed commit (record the SHA) — NO other external communication.

## Steps
1. RESEARCH OpenCode: UI structure, component separation, session management, tool-execution display, message streaming/rendering, attachment/reference handling, model switching. Record architecture patterns worth reusing vs patterns tied to SolidJS/OpenCode's own stack that do NOT transfer.
2. COMPARE with the approved Locus baseline: map each OpenCode pattern onto the existing React/TypeScript/Vite structure. The approved UI baseline is PRESERVED — any deviation requires an explicit written reason. NO full SolidJS migration.
3. DESIGN: author docs/plans/UI_OPENCODE_RESEARCH.md covering: comparison table (OpenCode pattern / Locus status / reusable / adapt / skip + reason), target chat-centric UI design (model switching, session history, file attachment, reference materials, unified processing-status display), admin-only visualization of loop progress/review/QA/Phase state, user-vs-admin display permission separation with SERVER-SIDE authorization mandatory, backend/auth/RAG/permission/Loop-Engine compatibility notes, and a phased implementation plan (which improvements are implementable within the approved scope now, which require Owner decisions as 【要決定】).
4. CONSTRAINTS: do not change existing permission boundaries via skills/components; do not enable unauthorized external communication, credential use, or agent execution; never render unfinished backend features as complete; do not carelessly replace working features; distinguish dev mocks from real execution results.
5. If OpenCode code is reused directly, record per-file license, copyright notice, dependencies, and upstream source in the design doc.
6. VERIFY: ruff check + ruff format --check + scripts/secret_scan.py (0 findings) using .loop/runtime/qa-venv (NEVER shared .venv). Docs-only slot — no UI code changes yet.
7. REPORT: findings summary, recommended first implementation slice, open items as 【要決定】 (do not decide for the owner). Append progress to this file under ## Progress.

## Safety
ADR-0011/0012, B6, E1/E2, fail-closed, no-egress beyond the single public repo read. Conventional Commits (docs(plans)); push origin loop/ui-research-opencode; repeat fix cycle until all checks green. Never push main or loop/local-development. Never spawn subagents. Never bypass hooks.

## Progress

### 2026-11-11 (slot V)
- Cloned OpenCode `dev` branch at fixed commit `59ed43f0b8da891f03a7333d540a7b0c428049ea` (shallow clone, read-only) and studied packages/app, packages/ui, packages/session-ui, packages/desktop. Network use limited to this one public repo.
- Findings: 3-layer UI separation (ui/session-ui/app), strict state-machine discipline (pure transition + attempt ids), timeline projection with stable keys, tool-renderer with per-tool display + status-title + counts, Markdown streaming via Web Worker, composer submission machine, process-wide upload machine with stall timeout, per-session model switching with deferred catalog load, session list with cursor pagination, Electron desktop, i18n discipline, SecureContext guards for plain-HTTP LAN origins.
- Not transferable: SolidJS store/memo patterns (adapted to React idioms), design-system token layer (baseline look preserved), Electron desktop, per-session model switching (backend has a single global runtime model — no tool loop, no streaming), fork/revert (backend changes needed).
- Locus baseline comparison: chat UI (exchange layout, citations, attachments, admin nav, permission-gated display) already matches the approved baseline; the only deviations from the baseline are in the proposed additions (conversation-history sidebar, session model switching, streaming) which are marked 【要決定】.
- Found a real latent bug: `frontend/src/App.tsx:613` uses `crypto.randomUUID()` directly, which throws on plain-HTTP non-localhost LAN origins (same class of bug OpenCode documents). Flagged as an in-scope fix (§6.6 of the research doc); no code changed in this slot.
- Authored `docs/plans/UI_OPENCODE_RESEARCH.md`: comparison table (20 rows with reusable/adapt/skip + reasons), target chat-centric UI design (model switching, session history, file attachment, reference materials, unified processing-status display), admin-only loop progress/review/QA/Phase visualization design with server-side authorization mandatory, user-vs-admin display permission separation, backend/auth/RAG/permission/Loop-Engine compatibility notes, and a phased implementation plan (approved-scope items now vs 【要決定】 items for the owner).
- No direct OpenCode code reuse in this slot (design reference only). Per-file license/copyright recording template added (§8) for any future reuse.
- Verification: ruff check + ruff format --check + scripts/secret_scan.py (0 findings) using .loop/runtime/qa-venv (never shared .venv). Docs-only slot — no UI code changes.
- Open items for the owner: conversation-history sidebar (baseline deviation), SSE streaming, per-session model switching, tool loop, admin loop-state endpoint, upload progress API. See §7.2 of the research doc.
