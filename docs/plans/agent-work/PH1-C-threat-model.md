# PH1-C — Hybrid-agent requirements: cross-check and threat model (documentation only)

Agent: write your progress under "## Progress" below every time you complete a step. Do not edit other agents' files.

## Task brief

Goal: deliver step 1 of the newly added specification `docs/planning/locus-hybrid-agent-requirements.md` — "現行コード・ADR・Phase計画の照合と脅威モデル策定" — as a review-ready document. **No code changes.**

Deliverable: `docs/security/HYBRID_AGENT_THREAT_MODEL.md` (create the file in your worktree; the directory exists) containing:
1. **Requirement-to-implementation matrix**: for each of the 8 必須要件, map what already exists in this repository (with file paths as evidence) and rate each as 満足 / 一部 / 未実装. Relevant existing assets to verify, not assume: `loop_engine/` (Loop Controller), `backend/app/service.py` (auth/ACL/audit), `backend/app/main.py` (loopback-only middleware, local-only env guards), `backend/app/scanner.py` + `docs/INGESTION_SCANNER.md`, `docs/LOCAL_MODELS.md`, `docs/LOCAL_COMMIT_PUSH_LOOP.md`, ADRs under `docs/architecture/decisions/` (especially ADR-0011 / C-min zero-tool boundary), `docs/plans/MODEL_BOUNDARY_*`, `docs/plans/RISK_REGISTER.md`.
2. **Threat model** for the target architecture (Control Plane / Server Runner / Desktop Runner / Agent Adapter / UI): enumerate threats per STRIDE category for: workspace policy enforcement, data classification inheritance into derived data (RAG indexes, citations, cached answers), runner authentication, command/file/network isolation enforcement points, audit integrity, and provider credential handling (requirement 5: official CLI login, credentials on user device, no repurposing of provider auth).
3. **Gap list mapped to the existing phase plan**: which gaps belong in Phase 1–5 vs. new phases; explicitly mark which items require owner decisions (do not decide them).
4. **Consistency findings**: contradictions between the new requirements doc and existing governance (e.g. zero-tool boundary vs. Desktop Runner executing official CLIs; local-only mode vs. Runner connections) — listed as findings with recommendations, not silently resolved.

Constraints:
- Ground every claim in the actual repository files you read (cite paths). Do not speculate about code you have not read.
- Respect the standing rule: proposals must not weaken existing specifications or approved boundaries.
- Do not modify any existing document other than creating `docs/security/HYBRID_AGENT_THREAT_MODEL.md`.

Process:
1. Own worktree: `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-threat-model -b loop/PH1-threat-model loop/local-development`; work only inside it.
2. Read the governance docs (`AGENTS.md`, `DEVELOPMENT_POLICY.md`, `ARCHITECTURE.md`, all ADRs) before writing.
3. Self-review: every matrix row cites evidence; every threat has a proposed mitigation or an explicit open decision; the doc is actionable.
4. Conventional Commit (`docs(security): ...`). Push `loop/PH1-threat-model`. Actions billing failure ⇒ record **blocked** (CI not applicable to docs anyway, report the attempt).
5. Record progress and the final SHA below.
