# Slot W — UI Chat Refactor (Approved-Scope First Slice)

Model: GPT-6-Luna (thinking high) | Branch: loop/ui-chat-refactor | Basis: docs/plans/UI_OPENCODE_RESEARCH.md §7.1 (integrated) + owner UI directive 2026-11-11

## Objective
Implement ONLY the approved-scope items from the integrated UI research §7.1. Preserve the approved UI baseline (docs/planning/UI_IMPLEMENTATION_BASELINE.md, ui-and-multiuser-design.md). Do NOT implement any §7.2 【要決定】 item (no history sidebar, no SSE streaming, no per-session model switching, no tool loop, no admin loop-state endpoint, no upload progress API).

## Scope (§7.1, exactly these five)
1. Latent bug fix: crypto.randomUUID() fallback in frontend/src/App.tsx (~line 613) for plain-HTTP non-localhost LAN origins (research §6.6). No permission-boundary impact.
2. Chat component separation: split the chat area of App.tsx into ChatView / ChatMessage / ChatComposer with projection functions (research §3.2). Preserve the baseline look exactly — pure refactor + projection extraction, no visual redesign.
3. Unified processing-status display: reorganize ChatQueue processing states into one consistent presentation (research §3.6) using EXISTING status values only; never render unfinished backend features as complete.
4. Unified attachment display: unify attachment failure states using existing statusName and reason (research §3.4).
5. Model switching display: do NOT add per-session switching; keep the existing message.model footnote (research §3.7).

## Rules
- Existing React/TypeScript/Vite structure; NO SolidJS migration; no new dependencies without justification.
- Do not carelessly replace working features; distinguish dev mocks from real execution results; server-side authorization untouched; no backend changes in this slot.
- Tests: frontend unit tests (npm test in frontend/), existing suites unbroken, accessibility attributes preserved, regression on existing UI behavior. Update or add component tests for ChatView/ChatMessage/ChatComposer projections.
- QA: frontend npm test + backend regression untouched (no backend changes). Use .loop/runtime/qa-venv for any python-side checks; NEVER shared .venv.
- Conventional Commits (refactor(ui)/fix(ui)/test(ui)); push origin loop/ui-chat-refactor; repeat fix cycle until ALL checks green (frontend + CI workflows). Never push main or loop/local-development. Never spawn subagents. Never bypass hooks.
- Append progress to this file under ## Progress.
