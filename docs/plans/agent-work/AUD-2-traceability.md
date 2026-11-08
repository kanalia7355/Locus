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

## Progress

- Read this brief, mandatory governance/product/architecture/bootstrap documents,
  GitHub workflow, AUD-1 ID scheme/gap analysis/roadmap, delegation spec and its
  owner status register, ADR-0012, bootstrap approval record, Phase-1 status,
  local-delivery migration, hybrid registry design, and review records. Fetched
  origin and created the authorized isolated worktree at
  `.loop/runtime/worktrees/AUD-2-traceability` from `origin/loop/local-development`
  on branch `loop/AUD-2-traceability`; base is `167035d`.
- Drafted all three requested deliverables in the worktree. Matrix includes the
  92 stable IDs, source/approval, phase/job, code/test/review/gap/closure columns,
  and explicit V/S/U verification methods; checked more than 25 code/test paths.
  Acceptance criteria retain prototype-deferred production conditions and
  separately identify the requested restart-persistent-session item as a proposal:
  no approved source located specifies restart persistence. Decision register records
  evidenced decisions and all 10 AUD-1 + 12 PH2-A open items with pointers.
- During cross-check found a time-baseline mismatch: AUD-1 gap state is pinned
  to `27c5a1d`, while this authorized branch starts at `167035d` and already
  contains PH2-B integration `73beb25`. Kept IAM-012's requested frozen gap
  state unchanged and documented the stale snapshot discrepancy explicitly;
  did not update the AUD-1 finding or change code.
- Structural self-review passed with the isolated QA Python: all 92 unique catalog IDs
  have exactly one matrix row and a V/S/U method; all 92 gap-state values match
  the AUD-1 crosswalk exactly; all 40 acceptance rows have valid requirement IDs,
  evidence class and status; final conditions include TLS, final MFA, the requested
  persistent-session decision/proposal, protected/retained audit, Runner isolation
  and production storage. The open register has exactly 10 AUD-1 and 12 PH2-A rows
  with evidence pointers. `git diff --check` passed. No tests/code were changed or run.
- Fast-forwarded the documentation worktree to origin after six later commits,
  including PH2-C research/integration; no conflict and no other agent's work was
  changed. Current pre-delivery base is `82c8daf`. The deliverables and progress
  remain the only changes.
- Commit `450c45b8898eaa73eeceac8f4f7657b0c2c84855` was pushed to the authorized
  task branch. Exact-SHA CI: Prototype quality and Loop engine checks succeeded;
  PR title convention failed because the initial push's default comparison range
  from `origin/main` contained 216 commits and existing validator refuses ranges
  over 200 (“Empty or oversized Push range requires assessment”). This was a
  range/validator interaction, not a commit-subject error. Kept the checker and
  branch history unchanged. The ordinary progress-note commit
  `a2db859dcc29642ad41f8dc6e603ea10dde7303b` used a one-commit push range; all
  required branch workflows passed on that exact SHA: Prototype quality
  `42435494167` SUCCESS; Loop engine checks `42435494201` SUCCESS (Ubuntu/Windows
  Python 3.11/3.13); PR title convention `42435494198` SUCCESS. The failed
  initial range check remains recorded for transparency; latest exact-head status
  is all green.
