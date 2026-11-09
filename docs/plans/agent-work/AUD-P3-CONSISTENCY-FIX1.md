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
