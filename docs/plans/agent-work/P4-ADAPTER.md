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

## Progress

### 2026-11-10 (P4-ADAPTER, this worktree)

- Read AGENTS.md, `docs/governance/DEVELOPMENT_POLICY.md`, owner Entry 4
  (`docs/plans/OWNER_DECISIONS_2026-11-10-ENTRIES.md`) and Q4
  (`docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md`), plus ADR-0011/0012,
  step-2 registry design §2.4–2.5, step-3 isolation proposals, DP-034
  classification, and the threat model for grounding.
- Authored `docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md` (14 sections) covering:
  - Fixed safety boundaries (no credential bytes, no repurposing, no
    unofficial circumvention, no egress approval, fail-closed, design-only).
  - Credential supply options: Option 0 no-supply (default), Option 1
    per-adapter direct (preferred per Q4), Option 2 broker-mediated (design
    and comparison only), plus rejected options.
  - Per-adapter research: Codex CLI, Claude Code, Gemini CLI, local LLM
    runtimes; each with official auth methods, subscription terms, isolated
    environment compatibility, and verification requirements. All vendor
    claims are knowledge-recorded and unverified in this no-egress
    environment; each is marked with an explicit verification requirement.
  - Broker comparison: BR-1 CLI-store broker, BR-2 short-lived file
    injection, BR-3 OS-keystore broker, BR-4 local proxy (rejected by Q4);
    architecture, security properties, evidence requirements per sub-arch.
  - Per-adapter execution constraints / terms-of-use inventory (§8 tables).
  - Safe verification test plan (§9): mock/stub credentials only
    (`MOCK-0000` synthetic tokens, stub CLI binaries); 5 positive and 12
    negative tests; evidence binding to pinned CLI/OS/isolation/runner
    versions; no real credential read, no provider login, no egress.
  - Adapter availability matrix (§10) — design-level, all provider adapters
    "Pending verification + egress"; no adapter enabled by this document.
  - 7 【要決定】 items (AD-1…AD-7) for genuinely new permission/policy
    choices only (verification form, CLI-sandbox boundary sufficiency,
    broker adoption, API-key policy, enablement list, credential rotation,
    provider egress approval).
  - Activation gates (§12) explicitly listing what is NOT approved.
- Adversarial self-review: confirmed all six required output sections are
  present; no credential bytes anywhere in the document (only synthetic
  mock tokens); 【要決定】 markers limited to genuinely new choices; broker
  adoption is gated on evidence + independent review + separate Owner
  approval; unofficial circumvention prohibited; reject rule preserved for
  adapters where safe supply cannot be demonstrated; design-vs-activation
  scope separation stated in §1.1, §12 and §14.
- QA: `ruff check` passed (All checks passed); `ruff format --check` —
  only pre-existing `docs/requirements/AUTONOMOUS_LOOP_SPEC.md` flagged,
  untouched by this work; `scripts/secret_scan.py` — 0 findings. Used
  `.loop/runtime/qa-venv` (Python 3.13.2, Ruff 0.17.3); shared `.venv`
  untouched.
- Commit: `docs(plans): author the agent adapter and credential supply design`
  pushed to `origin loop/p4-adapter-design`. No push to main or
  loop/local-development; no subagents; no hooks bypassed.
