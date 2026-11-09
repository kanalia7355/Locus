# AUD-P3-CONSISTENCY-FIX1 — apply the consistency-audit staleness findings

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Docs-only task:
do NOT modify code, tests or the ADR semantics (F5 is DEFERRED — see scope). Never push
to `main` or `loop/local-development`; no subagents of your own. NEVER touch the shared
`.venv` (broken); use `.loop/runtime/qa-venv` if needed.

Full process: read `AGENTS.md` + governance docs first; implement; self-review
adversarially; run the docs-applicable verification subset (ruff check + format --check
+ secret scan via scripts/secret_scan.py); Conventional Commit (`docs(plans): ...`);
push your dedicated branch; wait branch CI; fix/re-push until green or recorded
blocked; append progress + SHA + CI evidence here. Branch deleted after integration.

---

## Task (source: docs/plans/agent-work/AUD-P3-CONSISTENCY.md, integrated at e4b9aa2)

Apply the audit's MINIMAL recommended fixes for the staleness/accuracy findings —
accuracy restoration only, no semantics weakening, no decisions made:

1. **F1 (HIGH)** — `docs/plans/PHASE_STATUS.md`: the duplicate contradictory Phase-2
   completion declarations. Mark the FIRST declaration (lines ~50–96) and the
   line-9/line-12 table cells as a dated superseded snapshot pointing to the current
   declaration; consolidate the delegation-UI status in one place recording the
   integration SHAs (`c1c5f4c`/`a445b3f`/`84dc1eb`); reconcile the 18-vs-9 skipped
   counts (or state the two environments). Never delete history — label it superseded.
2. **F2 (MEDIUM)** — `docs/plans/PHASE2_DELEGATION_SPEC.md`: fix the stale
   header/grounding/observations per the audit's evidence (read F2's full text in
   AUD-P3-CONSISTENCY.md).
3. **F3 (MEDIUM)** — `docs/plans/OWNER_DECISION_REGISTER.md`: reconcile the
   open-decision tables with the actual resolved state (mark resolved items resolved;
   do NOT invent new resolutions and do NOT un-resolve anything).
4. **F4 (MEDIUM)** — `docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md`: refresh the
   post-integration rows (Phase-2 completion, delegation UI done, v0.3.0) per the
   audit's evidence, preserving the H2 gating language (2b/2c still require
   owner-approved ADR-0013; dispatch remains disabled).
5. **F6, F7, F8 (LOW)** — fix the citation/pointer/count errors exactly as recommended
   (HYB-A2 header authorization pointer; ADR-0013 §Context "§2 open items 1–12" →
   "§8 open items 1–12"; ADR-0013 verified-section line-number disclaimer + the
   PHASE_STATUS test-count correction or counting-method note).

OUT OF SCOPE: **F5 (ADR-0013 §3 revocation candidate (b) semantics)** — deferred to the
owner/doc-owner because ADR-0013 is a DRAFT with 23 pending 【要決定】 items; do not
re-label or re-frame its candidates. (F5 will be surfaced via the owner decision queue.)

Guardrails: these are status/accuracy documents — a fix must never make a pending item
look decided, never claim unrun verification, never weaken an approval gate. If a
recommended fix would require interpreting an undecided item, record it as a note for
the owner instead of changing the text.

Conventional Commit subject suggestion: `docs(plans): apply the consistency-audit staleness fixes`

## Progress

### 2026-11-09 — scope and source inspection complete

- Confirmed clean dedicated branch `loop/aud-p3-consistency-fix1` at `ce0168e`; bootstrap record exists. Read the assigned brief, audit findings, required governance/product/architecture/bootstrap documents, GitHub workflow, and relevant loop/quality skills. No uncommitted work was present at inspection.
- Confirmed F1–F8 against the named source docs and commit history. The integrated delegation UI commits are `c1c5f4c` → `a445b3f` → `84dc1eb`; the 2026-11-09 Phase-2 main integration is `c307939` (with reconciliation/closeout records `1284f4f`/`6e970ee`). ADR-0013 remains DRAFT; all pending items and the B6 dispatch rejection remain untouched.
- Proceeding with docs-only accuracy edits to the assigned status, roadmap, decision-register, ADR/proposal, and phase-specification files plus this task ledger. No code/test change or approval-gate change is in scope.

### 2026-11-09 — minimal accuracy edits applied

- F1: labeled the first Phase-2 declaration and old table states as superseded snapshots; consolidated current delegation-UI status with `c1c5f4c`/`a445b3f`/`84dc1eb`; distinguished PH2-CA's 18-skip environment from PH2-RV's 9-skip/9-failure local environment and stated the hosted-CI review condition separately. Clarified test function count baseline (10, later 11).
- F2: added a dated status banner and explicit historical labels above old grounding/source observations in PHASE2_DELEGATION_SPEC; retained historical text without suggesting the 409 endpoint remains current.
- F3: labeled AUD-1 and PH2-A open tables historical and updated statuses only to resolutions already recorded in §A/§B; production database/clock, deployment, implementation, and runtime choices remain open or gated as the register says.
- F4: refreshed the roadmap baseline note and Phase-2 row/closeout for main integration, delegation UI, and v0.3.0; kept H2's 2b/2c gates, requirement for owner-approved ADR-0013 and separate authorization, and B6 dispatch-disabled language explicit.
- F6–F8: pointed HYB-A2 to its task brief and exact relevant decision-register items; corrected ADR-0013's §8 pointer and added an indicative-line-number disclaimer.
- F5 deliberately untouched: ADR-0013 §3 candidate wording and its 23 pending 【要決定】 markers were not modified.
- Adversarial review surfaced an integration-boundary nuance: `a445b3f` and `84dc1eb` are in `loop/local-development` but not ancestors of `main`/`c307939`. Updated PHASE_STATUS and roadmap wording to distinguish the UI's local-development integration from the Phase-2 core main integration; no claim that UI is already in main.

### 2026-11-09 — QA environment preparation

- The isolated `.loop/runtime/qa-venv` was absent. System Python is 3.10.6 and global Ruff is 0.16.1, while the project pins Python 3.13/Ruff 0.17.3. Recreated the isolated venv with Python 3.13 and installed the project dev/locked dependencies; the shared `.venv` remains untouched.

### 2026-11-09 — docs-applicable verification complete

- `ruff check backend tests scripts loop_engine` — PASS (pinned Ruff 0.17.3).
- `ruff format --check backend tests scripts loop_engine` — PASS (222 files already formatted).
- `scripts/secret_scan.py` — PASS (0 findings).
- `git diff --check` — PASS; checked edited Markdown is valid UTF-8 with final newlines. Adversarial guard check confirms ADR-0013 §3 is byte-for-byte unchanged and its pending 【要決定】 marker count remains 23.
- Checks above are completed local verification. Branch CI has not yet been run; no CI result is claimed.

### 2026-11-09 — adversarial self-review complete

- Reviewed the complete documentation diff against F1–F8 and the original findings. Confirmed each historical table/declaration is visibly time-bounded, resolved decisions point to the existing RESOLVED section, unknown/residual items remain open, and old 18-skip versus 9-skip/9-failure reports are explicitly scoped by environment.
- Confirmed the delegation UI is documented as integrated on `loop/local-development`, not falsely included in main `c307939`; `MASTER_IMPLEMENTATION_ROADMAP.md` preserves the open storage ACL work, final-product MFA and deployment requirements. H2 2b/2c explicitly require owner-approved ADR-0013 and separate slice authorization; B6 dispatch stays disabled.
- Confirmed the ADR-0013 revocation candidate section is unchanged and retains all 23 pending markers. No code/tests changed. `git diff --check` is clean.

### 2026-11-09 — commit and push (CI pending)

- Docs-only Conventional Commit `285d6fa96197a74b10878eb3572f1f7ef838a609` (`docs(plans): apply the consistency-audit staleness fixes`) created and pushed to `origin/loop/aud-p3-consistency-fix1`.
- Push succeeded. Exact-SHA branch CI evidence is not yet available; will record the workflow outcomes when queried. No CI pass is claimed at this step.
