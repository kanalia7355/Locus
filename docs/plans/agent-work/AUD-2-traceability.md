# AUD-2 — Traceability matrix, final acceptance criteria, owner decision register (docs only)

Agent: append your progress under "## Progress" below every time you complete a
step. Research/documentation task: NO application code changes.

## Task brief

Second half of the owner's 2026-11-09 design-audit instruction. AUD-1 is
delivered and integrated: `docs/plans/REQUIREMENT_ID_SCHEME.md` (92 IDs),
`DESIGN_GAP_ANALYSIS.md` (gap states + 10 owner-decision/contradiction findings),
`MASTER_IMPLEMENTATION_ROADMAP.md`. Build on those documents — extend, do not
replace them.

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/AUD-2-traceability -b loop/AUD-2-traceability origin/loop/local-development` (reuse if it exists). Work ONLY inside it. Use `C:/Users/hirot/Locus/.loop/runtime/qa-venv/Scripts/python.exe` for any verification (the shared `.venv` is broken).

Deliverables:

1. `docs/plans/REQUIREMENTS_TRACEABILITY_MATRIX.md` — for ALL 92 requirement IDs
   from `REQUIREMENT_ID_SCHEME.md`, one row per requirement with: ID, name,
   source doc+section, approval status, mapped phase/step, implementation job,
   implementing code/config (file paths, verified — spot-check at least 25 IDs
   against the real code/tests and mark each row's verification method), test/
   verification evidence (test file + counts where applicable), independent
   review result (which review covered it, verdict), current gap state (from
   DESIGN_GAP_ANALYSIS, unchanged), completion conditions, and remaining work.
   Rows whose evidence cannot be verified must say so explicitly — never fill
   gaps by assumption.
2. `docs/plans/FINAL_ACCEPTANCE_CRITERIA.md` — Locus's final completion
   conditions derived ONLY from approved source documents (original design +
   later owner-approved extensions): grouped by area (research support,
   authN/authZ/delegation, data/classification, hybrid agent platform, runner
   isolation/activation gates, audit, UI, operations/deployment, quality gates);
   for each criterion: requirement IDs, the verifying evidence class (tests,
   review, deployment validation…), and whether it is prototype-satisfied,
   deferred-with-owner-approval, or open. Production items (TLS, MFA final
   decision, persistent sessions, audit-log protection/retention, runner
   isolation, production storage) MUST appear as final conditions even though
   deferred for the prototype. Do NOT add criteria absent from source documents;
   list any additions as separate proposals.
3. `docs/plans/OWNER_DECISION_REGISTER.md` — the consolidated register of owner
   decisions with date, scope, and evidence pointer: bootstrap-era approvals,
   model-boundary/Ollama approvals, phase-1 completion scoping (MFA/TLS/LAN
   deferral), the 2026-11-07 decision package (ADR-0012 approval, step-2 ten
   answers, phase-4 remainder approval, autonomous rules), the 2026-11-09
   restructuring instruction, plus the OPEN register: AUD-1's 10 findings and
   the delegation spec's 12 items with their current status (open → awaiting
   owner). Every entry needs an evidence pointer (commit/doc path); unknown
   provenance is recorded as such, never invented.

Self-review: structural completeness (all 92 IDs present, every register entry
has an evidence pointer), consistency with the gap analysis states, no invented
requirements. Conventional Commit (`docs(plans): publish the traceability matrix, final acceptance criteria, and owner decision register`).
Push `loop/AUD-2-traceability`; wait branch CI; fix/re-push until ALL green
(bounded). APPEND progress + SHA + CI evidence to this file's ## Progress.

Boundaries: never push to `main` or `loop/local-development`; no code changes;
no subagents.
