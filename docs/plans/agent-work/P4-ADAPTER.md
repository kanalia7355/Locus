# P4-ADAPTER — Agent Adapter research: official CLI auth methods and credential supply design

Agent: append your progress under "## Progress" below every time you complete a step.
Work ONLY in your own worktree/branch. Docs-only task: do NOT modify code.
Never push to `main` or `loop/local-development`; no subagents.

## Task

Research and design the Agent Adapter authentication and credential supply approach per the
owner-approved Entry 4 (`docs/plans/OWNER_DECISIONS_2026-11-10-ENTRIES.md`).

**Approved direction (Entry 4 + Q4):**
- Official CLI / existing login methods preferred (Codex CLI, Claude Code, etc.)
- Per-adapter verification of: authentication method, terms of use, isolated environment operation, credential protection
- broker-mediated supply: design and compare; adoption requires evidence + independent review + separate Owner approval
- Credential bytes NEVER enter: job inputs, receipts, audit logs, model context
- Adapters where safe credential supply cannot be demonstrated: REJECT for that environment
- Unofficial auth circumvention / subscription bypass: PROHIBITED
- **SCOPE:** This decision approves the DESIGN and VERIFICATION of credential supply methods — NOT actual account login, credential read/transfer/supply

**Output:** Create `docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md` covering:
- Per-adapter (Codex CLI, Claude Code, etc.) research: official auth method, subscription terms, isolated environment compatibility
- Credential supply design options (broker-mediated vs per-adapter direct vs no-supply)
- Broker comparison: architecture, security properties, evidence requirements
- Per-adapter execution constraints and terms-of-use inventory
- Safe verification test plan (mock/stub credentials only — no real credentials)
- 【要決定】 markers for any genuinely new permission or policy choice
- Adapter availability matrix (which adapters work on which platforms with which auth methods)

**Safety boundaries:** ADR-0011/0012, B6, no-egress, fail-closed, no credential bytes in jobs/logs; design-only (no actual credential access, no provider login, no external communication).

**Process:** Read AGENTS.md + DEVELOPMENT_POLICY.md + owner Entry 4 + Q4 + OWNER_REEVAL-A/B/C for grounding. Conventional Commit (`docs(plans): ...`); push origin loop/p4-adapter-design; repeat until checks pass.
Conventional Commit subject: `docs(plans): author the agent adapter and credential supply design`
