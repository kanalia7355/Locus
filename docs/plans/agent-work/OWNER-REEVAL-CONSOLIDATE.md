# OWNER-REEVAL-CONSOLIDATE — merge the three re-evaluations into ONE proposal

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Docs-only task:
do NOT modify code, specs, tests, the OWNER_DECISION_QUEUE cells, or the three source
re-evaluation files. Never push to `main` or `loop/local-development`; no subagents of
your own. NEVER touch the shared `.venv`; use `.loop/runtime/qa-venv` if needed.

## Task

The three group re-evaluations are already integrated on loop/local-development:

- `docs/plans/OWNER_REEVAL-A-RECEIPT.md` (DP-001–023, 767 lines)
- `docs/plans/OWNER_REEVAL-B-ISOLATION.md` (DP-024–053, 358 lines)
- `docs/plans/OWNER_REEVAL-C-STORAGE-MISC.md` (DP-054–072, 248 lines)

Produce `docs/plans/OWNER_DECISION_PROPOSAL_2026-11-09.md` — the ONE coherent design
decision set for the owner. Requirements:

1. Keep the 7-field per-item format and the flags (🚫初期設計反 / ⚠根拠不足制約 /
   📈過剰設計疑) from the source files; do not re-derive the evaluations — merge them.
2. Add a coherence check as a new section:
   - contradictions between groups (e.g. A's autonomy-friendly receipt design vs
     B's isolation assumptions; B's isolation steps vs C's storage bindings),
   - rootless constraints (⚠) that appear in more than one group,
   - over-engineering flags (📈) that should be dropped or phased,
   - any item where the source recommendation conflicts with the owner's 7 priorities
     (research support first; local/server hybrid; admin × personal-workspace
     balance; in-scope autonomy; no unnecessary owner confirmations; ADR-0011/0012
     intact; no rootless constraints).
3. Add an executive summary: per group (A/B/C) the count of items, the recommended
   direction, the number of 🚫/⚠/📈 flags, and the true owner-decision points that
   remain after the recommendations.
4. Recommendations are NOT execution permission: no activation of dispatch/isolation/
   egress/credentials. Do not fill the queue's OWNER DECISION cells. Do not re-open
   already-approved decisions.
5. Keep per-item entries COMPACT in the proposal (link to the source file for the
   full 7-field text; the proposal may carry the recommendation + flags + owner
   decision needed in ~6 lines per item).

## Process

Read AGENTS.md + docs/governance/DEVELOPMENT_POLICY.md, then the shared grounding
pack docs/plans/agent-work/OWNER_REEVAL-GROUNDING.md, then the three source files in
full, then produce the proposal. Self-review adversarially; run the docs-applicable
verification subset (ruff check + ruff format --check + scripts/secret_scan.py via
the qa-venv if needed). Conventional Commit (`docs(plans): ...`); push origin
loop/reeval-consolidation; repeat the fix cycle until all applicable checks pass
(branch CI green or recorded blocked). Append progress + SHA + CI evidence to this
file under ## Progress at each step end and at task end, and push.

Conventional Commit subject suggestion: `docs(plans): consolidate the 72-item owner decision proposal`
