# OWNER-ROADMAP-RESUME — update the roadmap, list the resumable jobs, and inventory the deferred gates

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Docs-only task:
do NOT modify code, specs, tests, the OWNER_DECISION_QUEUE, the proposal, or the
re-evaluation files. Never push to `main` or `loop/local-development`; no subagents of
your own. NEVER touch the shared `.venv`; use `.loop/runtime/qa-venv` if needed.

## Task

The owner's formal decisions Q1–Q7 are recorded in `docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md`
(2026-11-09 evening). The owner directed (§5–7): approved-scope work never stops on other
pending items; the roadmap must be updated; the resumable jobs must be listed; and the
deferred items must carry gates. Deliverables:

1. Update `docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md` — reflect the owner's Q1–Q7 decisions:
   the hybrid step-2 receipt design (2b) and step-3 isolation profiles are now DESIGN-READY
   under the owner's decisions (Q1/Q3), storage-ACL is manual-upload-first with connectors
   deferred (Q5), production tech is deferred with gates (Q7). Preserve the existing gating
   language: 2b/2c still require the owner-approved receipt contract and dispatch remains
   disabled until the ADR-0012 activation gate; the owner's §4 unresolved list stays
   【要決定】. Do not delete the prior history; append a dated update section.
2. Create `docs/plans/RESUMABLE_JOBS_2026-11-09.md` — the list of work that can start now
   within the approved scope, with a slot-assignment shape (implementation → self-review →
   QA → delivery → integration), grouped into: design docs ready for the receipt/2b contract
   (excluding owner-decision points), isolation-profile design docs (per-environment, excluding
   the unverified-profile activation), storage manual-upload first, and the engineering
   details that are ENGINEERING_DETAIL-classified. Each job: scope, the owner decision it
   relies on, the safety boundary that must not change, and the completion gate.
3. Create `docs/plans/DEFERRED_WITH_GATES_2026-11-09.md` — the deferred items with explicit
   start conditions and acceptance gates (connectors per Q5, production tech per Q7, the
   owner's §4 unresolved list, and any other deferred row).
4. You may edit ONLY: `docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md` (append a dated update
   section), `docs/plans/RESUMABLE_JOBS_2026-11-09.md` (new), and
   `docs/plans/DEFERRED_WITH_GATES_2026-11-09.md` (new). Do not edit the queue cells, the
   proposal, or the re-evaluations — slot H handles those.
5. Standing instructions: approved-scope work never stops; do not re-open approved decisions;
   do not weaken any safety boundary (ADR-0011/0012, B6, no-egress, fail-closed); the owner's
   §4 unresolved list stays 【要決定】; dispatch/isolation/egress/credentials/production stay
   inactive until their own gates.

## Process

Read AGENTS.md + docs/governance/DEVELOPMENT_POLICY.md, then the owner decision record, then
MASTER_IMPLEMENTATION_ROADMAP.md and OWNER_DECISION_PROPOSAL_2026-11-09.md (the recommendations
for context), then the source reviews (OWNER_REEVAL-A-RECEIPT.md / OWNER_REEVAL-B-ISOLATION.md /
OWNER_REEVAL-C-STORAGE-MISC.md) as needed. Self-review adversarially; run the docs-applicable
verification subset (ruff check + ruff format --check + scripts/secret_scan.py via the qa-venv
if needed). Conventional Commit (`docs(plans): ...`); push origin loop/owner-roadmap-resume;
repeat the fix cycle until all applicable checks pass. Append progress + SHA + CI evidence to
this file under ## Progress at each step end and at task end, and push.

Conventional Commit subject suggestion: `docs(plans): update the roadmap and list the resumable jobs`

## Progress

- 2026-11-09 — Step 1 complete: read the required governance, owner decisions, roadmap, proposal, source re-evaluations, and current loop acceptance. Confirmed the worktree is clean on `loop/owner-roadmap-resume` at baseline SHA `0d631797f869c1bc5b23189ae39581a4b816a1b3`; bootstrap record exists. No task checks or CI have run yet; no pass is claimed. The work will keep unresolved §4 choices marked 【要決定】 and distinguish design readiness from implementation/activation.
- 2026-11-09 — Step 2/3/4 complete: appended the dated Q1–Q7 roadmap update, created the resumable jobs and deferred-gates inventories. Design-ready status is limited to documents; dispatch, Runner profiles, egress, credentials, real data, and production remain inactive.
- 2026-11-09 — Adversarial review and local QA: confirmed the roadmap is append-only; verified 2b/2c's receipt-contract and ADR-0012 activation gates, Q3 isolation non-activation, Q5/Q6 manual-upload/access-denial scope, Q7 production deferrals, and unresolved §4 【要決定】 status. Isolated QA venv commands: `python -m ruff check` PASS; `scripts/secret_scan.py` PASS (0 findings); full-repository `ruff format --check` reports only the existing untouched `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315` formatting discrepancy (outside allowed paths); changed-file format check PASS (4 files); `git diff --check` PASS. No files outside the allowed set were edited.
- 2026-11-09 — Initial delivery commit `099a29616b74ba5c4ec8c2f144ee88c7b72fa6c1` pushed to `origin/loop/owner-roadmap-resume`. Initial exact-SHA CI passed: Prototype quality `42627355052`; Loop engine checks `42627355098` (all four matrix jobs); PR title convention `42627355157`.
- 2026-11-09 — Follow-up commit `3b7cb4ed4af1447ec4947ef72a910a3e5a4b81cd` aligns storage deferred rows with slot H's D-1/D-2/D-3 gate mapping and records final evidence. Pushed to `origin/loop/owner-roadmap-resume`; exact-SHA CI passed: Prototype quality `42628692459`; Loop engine checks `42628692535` (all four matrix jobs); PR title convention `42628692427`. Final local QA on this content: isolated-venv Ruff check PASS; changed-file Ruff format check PASS (4 files); secret scan PASS (0 findings); diff check PASS. Full-repository Ruff format check remains non-green only for pre-existing, untouched `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315`; no out-of-scope file was changed.
- 2026-11-09 — Task-end verification: final deliverable commit `3b7cb4ed4af1447ec4947ef72a910a3e5a4b81cd` is on `origin/loop/owner-roadmap-resume`; local Ruff check, changed-file format check, secret scan (0 findings), and diff check passed. Full-repository format check has the one pre-existing out-of-scope issue at `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315`. Final task-content CI passed at SHA `3b7cb4ed4af1447ec4947ef72a910a3e5a4b81cd`: Prototype quality `42628692459`, Loop engine checks `42628692535` (all four matrix jobs), PR title `42628692427`. The progress-only delivery ledger commit `d1d731e87b08324e2f4a80466dc050b835ed5791` was also pushed; its CI passed: Prototype quality `42629754069`, Loop engine checks `42629754076` (all four matrix jobs), PR title `42629754052`. Recording this task-end evidence and pushing the final ledger update on the same assigned branch; no main/local-development operation or out-of-scope file change.
