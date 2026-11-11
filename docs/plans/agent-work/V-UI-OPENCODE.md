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
