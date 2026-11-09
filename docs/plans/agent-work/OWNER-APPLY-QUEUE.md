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

## Progress

### 2026-11-09 — Slot H: queue cells filled + classification created (step end)

- Read AGENTS.md, docs/governance/DEVELOPMENT_POLICY.md, docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md, this brief, the queue, the proposal and (via the consolidated proposal) the re-evaluations. Bootstrap state verified: `.bootstrap/complete.json` exists; worktree `loop/owner-apply-queue` clean at start.
- `docs/plans/OWNER_DECISION_QUEUE_2026-11-09.md`: all **72 OWNER DECISION cells** filled (verified programmatically: 72 rows, no empty cells, 8 columns per row, each cell links `OWNER_DECISIONS_2026-11-09-EVENING.md` and the classification file). Owner-directed mappings applied: DP-005→Q1, DP-006→Q2, DP-024–030→Q3, DP-034→Q4 (split a/b), DP-054–055→Q5, DP-058→Q6, DP-066–070/072→Q7. No technical number or permission invented; owner §4 items (receipt TTL numbers DP-010/011, new permission DP-021, Runner trust/enrollment/key management DP-035–041 + DP-043b, provider credential supply DP-034b, unapproved external communication DP-031/032, DP-071 org model) remain 【要決定】 as OWNER_DECISION_REQUIRED. Only the OWNER DECISION cells were edited; the queue header/ID columns were intentionally left untouched per the brief's cells-only constraint (residual header wording noted as an inconsistency for slot I/the owner).
- `docs/plans/OWNER_QUEUE_CLASSIFICATION_2026-11-09.md` created: 81 rows (72 primaries + 9 split items → 18 a/b rows; splits: DP-015, DP-034, DP-043, DP-053, DP-057, DP-059, DP-060, DP-062, DP-064) into OWNER_POLICY_RESOLVED 22 / EXISTING_DECISION 8 / ENGINEERING_DETAIL 25 / OWNER_DECISION_REQUIRED 15 / DEFERRED_WITH_GATE 11; OWNER_DECISION_REQUIRED presented in the owner-directed 8-field format (6 grouped decision requests: DP-010/011, DP-021, DP-031/032, DP-034b, DP-035–041+043b, DP-071); DEFERRED_WITH_GATE gates D-1/D-2/D-3 with start conditions; Q1–Q7 recorded as cross-cutting design constraints. Proposal, re-evaluations, roadmap and other agents' files untouched. Coordinated with slot I (no file overlap; shared the ENGINEERING_DETAIL row list).
- Next: local verification (ruff check + ruff format --check + scripts/secret_scan.py, never the shared `.venv`), Conventional Commit, push, CI evidence. Final SHA/evidence to be appended after push.

### 2026-11-09 — Slot H: task end (commit 24b5391, CI green)

- **Commit:** `24b5391` — `docs(plans): apply the owner's Q1-Q7 decisions to the queue` on `loop/owner-apply-queue`, pushed to origin. Files: `docs/plans/OWNER_DECISION_QUEUE_2026-11-09.md` (72 OWNER DECISION cells filled, no other cell or line changed — verified by byte-prefix comparison against HEAD), `docs/plans/OWNER_QUEUE_CLASSIFICATION_2026-11-09.md` (new, 81 rows), this task file.
- **Local verification** (isolated `.loop/runtime/qa-venv`, Python 3.13 + pinned dev tools recreated in this worktree; shared `.venv` untouched):
  - `ruff check .` → **All checks passed** (pinned ruff 0.17.3).
  - `ruff format --check .` → 1 pre-existing finding in `docs/requirements/AUTONOMOUS_LOOP_SPEC.md` (untouched since the initial commit; outside this task's allowed files, which are docs-only and not Python). Not introduced or fixable by this slot without violating its file constraint; recorded as pre-existing, not passed.
  - `python scripts/secret_scan.py` → **0 findings** (exit 0).
- **CI evidence (origin/loop/owner-apply-queue, commit 24b5391):** Loop engine checks **success** (run 42626897591, matrix ubuntu/windows × 3.11/3.13); PR title convention **success** (run 42626897634, Conventional Commit subject accepted); Prototype quality **success** (run 42626897695). Non-blocking deprecation annotations only (Node 20 → 24; ubuntu-latest migration notice).
- **Adversarial self-review:** all 72 primaries present exactly once; counts reconcile (81 = 72 + 9 split items → 18 a/b rows); no invented numbers/permissions; owner §4 items stay 【要決定】; no approved item re-asked; ADR-0011/0012, B6, fail-closed, no-egress and metadata-only audit preserved; queue header/ID columns untouched per the cells-only constraint (residual header wording flagged for slot I/owner).
- **Coordination:** slot I (OWNER-ROADMAP-RESUME) confirmed no file overlap and will cite the pushed classification record; notified with the SHA.
- Task complete: no remaining applicable failures attributable to this slot; no subagents used; no hooks bypassed; no pushes to `main` or `loop/local-development`; no quota errors encountered.
