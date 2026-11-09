# OWNER-APPLY-QUEUE — fill the OWNER DECISION cells and classify all 72 items

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Docs-only task:
do NOT modify code, specs, tests, or the OWNER_DECISION_PROPOSAL file. Never push to
`main` or `loop/local-development`; no subagents of your own. NEVER touch the shared
`.venv`; use `.loop/runtime/qa-venv` if needed.

## Task

The owner's formal decisions Q1–Q7 are recorded in `docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md`
(2026-11-09 evening). The owner directed:

1. Fill the OWNER DECISION cells of `docs/plans/OWNER_DECISION_QUEUE_2026-11-09.md` — every
   cell must now reference the owner's decision (Q1–Q7 / EXISTING / split / deferred) instead of
   being blank. Every cell references the decision record file. Never fill a cell with a
   technical number or permission that the owner did not approve (e.g. receipt TTL numbers stay
   【要決定】 in the owner's §4).
2. Create `docs/plans/OWNER_QUEUE_CLASSIFICATION_2026-11-09.md` — a table classifying all 72
   items into the owner's 5 categories:
   - **OWNER_POLICY_RESOLVED** — resolved by the owner's Q1–Q7 decisions.
   - **EXISTING_DECISION** — already resolved by existing ADRs/owner decisions.
   - **ENGINEERING_DETAIL** — technically decidable within the approved scope (orchestrator
     proposes + independent review; NOT owner decision).
   - **OWNER_DECISION_REQUIRED** — a genuinely new permission/safety boundary/operating-policy
     decision still needed. For each, list the options with the owner-directed 8-field format:
     当初設計との対応 / 選択肢 / 推奨案 / メリット・デメリット / 自律性・利便性・安全性への影響 /
     推奨案の採用によって可能になる作業 / 判断を後回しにできるか. Do not re-ask already-approved
     items.
   - **DEFERRED_WITH_GATE** — deferred to a later phase with a start condition and acceptance
     gate.
3. Items containing multiple unresolved parts must be SPLIT into separate rows (e.g. DP-015 may
   carry both a delegation-as-input and a personal-workspace part; DP-043 may carry both a
   revocation and a retention part). Keep the original DP numbering for the primary row and
   label splits (e.g. DP-015a/DP-015b) with a pointer to the original.
4. Explicit mappings the owner directed: DP-005→Q1; DP-006→Q2; DP-024–030→Q3; DP-034→Q4;
   DP-054–055→Q5; DP-058→Q6; DP-066–070/072→Q7. Apply the same decisions as design constraints
   to all related items.
5. Standing instructions: approved-scope work never stops on other pending items; the queue's
   original DP definitions and source links are preserved; do not re-open approved decisions;
   do not weaken any safety boundary (ADR-0011/0012, B6, no-egress, fail-closed); the §4
   unresolved list stays 【要決定】.
6. You may edit ONLY: `docs/plans/OWNER_DECISION_QUEUE_2026-11-09.md` (OWNER DECISION cells
   only) and `docs/plans/OWNER_QUEUE_CLASSIFICATION_2026-11-09.md` (new file). Do not edit the
   proposal, the re-evaluations, or the roadmap — slot I handles those.

## Process

Read AGENTS.md + docs/governance/DEVELOPMENT_POLICY.md, then the owner decision record, then
OWNER_DECISION_QUEUE_2026-11-09.md and OWNER_DECISION_PROPOSAL_2026-11-09.md (the recommendations
for context), then the source reviews (OWNER_REEVAL-A-RECEIPT.md / OWNER_REEVAL-B-ISOLATION.md /
OWNER_REEVAL-C-STORAGE-MISC.md) as needed. Self-review adversarially; run the docs-applicable
verification subset (ruff check + ruff format --check + scripts/secret_scan.py via the qa-venv
if needed). Conventional Commit (`docs(plans): ...`); push origin loop/owner-apply-queue;
repeat the fix cycle until all applicable checks pass. Append progress + SHA + CI evidence to
this file under ## Progress at each step end and at task end, and push.

Conventional Commit subject suggestion: `docs(plans): apply the owner's Q1-Q7 decisions to the queue`
