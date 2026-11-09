# OWNER-REEVAL-B — DP-024…053 (hybrid step-3 isolation & Runner trust, 30 items)

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Docs-only task:
do NOT modify code, specs, tests or the OWNER_DECISION_QUEUE cells. Never push to
`main` or `loop/local-development`; no subagents of your own. NEVER touch the shared
`.venv`; use `.loop/runtime/qa-venv` if needed.

Process: read AGENTS.md + governance docs, then docs/plans/agent-work/OWNER_REEVAL-GROUNDING.md
(the shared grounding pack — follow it exactly), then produce your deliverable.

## Task

Evaluate DP-024…DP-053 (the 30 hybrid step-3 isolation/Runner-trust decisions from
docs/plans/HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md) against the INITIAL LOCUS
DESIGN per the grounding pack's mandatory 7-field format + flags, and write
`docs/plans/OWNER_REEVAL-B-ISOLATION.md`.

Primary owner verifications for this group:
- **Is the Runner isolation practical on BOTH local and server?** (owner priority 2:
  local/server hybrid operation). The proposals are VM-first (Hyper-V guests etc.) —
  check whether VM-per-job on typical LOCAL dev machines is practical for the prototype,
  or whether the initial design supports a phased/graded isolation that is lighter
  locally and stronger server-side. Recommend per initial-design fit, and explicitly
  flag over-engineering (📈過剰設計疑) where the proposal exceeds the original
  functional requirement without grounding.
- Keep ADR-0011/0012 boundaries intact: recommendations must NOT weaken the zero-tool
  gate, dual-plane separation, B6 dispatch gate, or no-egress defaults — but note where
  proposal options add constraints the initial design never contained (⚠根拠不足制約).
- Runner trust-root/enrollment/rotation: recommend minimal configurations consistent
  with the local/server hybrid and the existing keyless/audit ADR lineage
  (ADR-0009/0010 background).
- Extensibility for future features (adding stronger isolation later without redesign).

Self-review adversarially; run the docs-applicable verification subset (ruff check +
format --check + secret scan via scripts/secret_scan.py); Conventional Commit
(`docs(plans): ...`); push origin loop/reeval-b-isolation; repeat the fix cycle until
all applicable checks pass (branch CI green, or recorded blocked while billing-blocked).
Append progress + SHA + CI evidence here at each step end and at task end, and push.
Never bypass hooks; if a model/provider quota error occurs, record it and stop.

Conventional Commit subject suggestion: `docs(plans): re-evaluate DP-024-053 against the initial design`
