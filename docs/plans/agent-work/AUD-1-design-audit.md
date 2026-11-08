# AUD-1 — 当初設計の網羅調査とギャップ分析・マスターロードマップ (docs only)

Agent: append your progress under "## Progress" below every time you complete a
step. Research/documentation task: NO application code changes.

## Task brief

Owner instruction (2026-11-09): Locus's completion condition is satisfying the
ORIGINAL approved design — not merely finishing the current Phase numbering.
Your job is the first half of the design audit; a second job (AUD-2) will build
the traceability matrix from YOUR requirement-ID scheme, so the ID scheme and
findings must be complete and self-consistent.

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/AUD-1-design-audit -b loop/AUD-1-design-audit origin/loop/local-development` (reuse if it exists). Work ONLY inside it.

Investigate ALL of the following, recording for each document its date, approval
status, scope, and relationship to later changes (do not treat later phase plans
as the only baseline; trace requirement evolution; do NOT invent requirements
that no document contains; contradictions are recorded as findings requiring
owner decisions, never silently resolved):

- Initial requirements / full-implementation instructions: `AGENTS.md`,
  `docs/requirements/PRODUCT_SPEC.md`, `docs/requirements/AUTONOMOUS_LOOP_SPEC.md`,
  `docs/requirements/DEVELOPMENT_LOOP_SPEC.md`, `docs/requirements/LOOP_BOOTSTRAP_SPEC.md`,
  `README.md`, and any earlier requirement documents discoverable in git history
  (use `git log --diff-filter=A -- docs/` and inspect deleted/renamed docs).
- Architecture: `docs/architecture/ARCHITECTURE.md`, all `docs/architecture/ADR-*.md`
  and `docs/architecture/decisions/*` (approval status of each).
- Phase plans/roadmaps: `docs/plans/ROADMAP.md`, `PHASE_SPEC_RECONCILIATION.md`,
  `PHASE_STATUS.md`, `PHASE2_JOB_BREAKDOWN.md`, `LOOP_IMPLEMENTATION.md`,
  `IMPLEMENTATION_LOG.md`, `RISK_REGISTER.md`, and other docs/plans files.
- Security: `docs/security/*`, `docs/governance/*`, threat models, MODEL_BOUNDARY_*,
  ADR-0011/0012.
- Hybrid Agent Runtime: `docs/planning/locus-hybrid-agent-requirements.md`,
  `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md`, `docs/plans/PHASE2_DELEGATION_SPEC.md`.
- UI/UX: `docs/planning/UI_IMPLEMENTATION_BASELINE.md`, `ui-and-multiuser-design.md`,
  `research-app-concept.md`, the baseline image reference.
- Existing code/tests/CI: inventory what the backend/frontend/loop_engine/ actually
  implement at HEAD (do not trust docs alone; verify against code and test files).
- Backlog/hold/review records: `docs/plans/agent-work/*`, `docs/reviews/*`,
  `docs/operations/*`, `docs/dependencies/*`, `.bootstrap/*`.

Deliverables (create in the worktree):

1. `docs/plans/DESIGN_GAP_ANALYSIS.md` — for every requirement area of the
   original design: what the design requires (with source doc + requirement ID),
   what exists in code/tests today (with file paths), and the gap class:
   未着手 / 設計中 / 実装中 / 実装済み・未検証 / 検証済み・未統合 / 統合済み /
   完了条件充足 / Owner判断待ち / 正式に対象外と承認済み. Code existence alone
   never counts as satisfied — implementation + verification + review evidence
   must all exist. Contradictions between documents → findings with owner-decision
   flags. Deferred production items (TLS, MFA, audit retention, runner isolation)
   stay in scope for FINAL completion even if deferred for the prototype.
2. `docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md` — the full roadmap from original
   design to final completion: every phase/step (existing numbering preserved as
   aliases; you may add later phases), purpose, mapped requirement IDs, dependencies,
   parallelizable work, completion conditions, transition conditions, version-bump
   and main-merge rules. Mark which phases are complete with evidence and which
   requirements remain open.
3. `docs/plans/REQUIREMENT_ID_SCHEME.md` — the requirement ID catalog (ID, name,
   one-line requirement, source doc+section, approval status, priority). AUD-2 will
   extend this into the traceability matrix; keep IDs stable and complete.

Rules: preserve all existing approvals; never delete/downgrade a requirement
without recording it as an owner decision; distinguish "prototype-deferred" from
"out of scope"; additions not present in any source document are listed separately
as proposals. Self-review for completeness (every source doc in the list above
must appear in the survey with its status).

Conventional Commit (`docs(plans): audit the original design and publish the gap analysis and master roadmap`).
Push `loop/AUD-1-design-audit`; wait branch CI; fix/re-push until ALL green
(bounded). APPEND progress + SHA + CI evidence to this file's ## Progress.

ENVIRONMENT NOTE: use `C:/Users/hirot/Locus/.loop/runtime/qa-venv/Scripts/python.exe`
for any verification (the shared `.venv` is broken). Boundaries: never push to
`main` or `loop/local-development`; no code changes; no subagents.

## Progress

- 2026-11-09: Read the complete task brief, created/reused the assigned isolated worktree at `loop/AUD-1-design-audit`, and fast-forwarded it to current `origin/loop/local-development` (`27c5a1d`). Read the repository entrypoint, governance policy, product spec, architecture, bootstrap procedure, all four initial requirements/README files, all ADRs and decision records, phase plans, security/threat-model documents, hybrid agent/UI specs (including the baseline image), current state/owner-decision summary, code/tests/CI, bootstrap evidence, and GitHub delivery/security/activation records. No code changed; no agents spawned.
- Survey finding: current owner instruction calls for final completion against original approved design. Current status docs declare only Phase 1 complete in a prototype scope; later phases/production gates remain open. The initial 2026-10-29 source package (`research-ai-bootstrap-v3.zip`) was also inventoried; Git history has no earlier tracked `docs/` sources or removed/renamed docs in reachable history.
- 2026-11-09: Published all three documentation deliverables. The ID scheme contains 92 unique stable IDs across seven families; every ID is explicitly referenced by both the gap analysis and roadmap. The gap analysis names every tracked source file in the required families and assigns date/status/scope/evolution, plus records contradictions and phase status; final requirements (TLS, MFA decision, audit retention, runner isolation, main delivery) remain open. Roadmap preserves P0–P5, MVP-1–6, L1–L6 and H1–H6 as separate aliases, adds P6/P7 final acceptance gates, dependencies, transitions, CI/review/version/main rules and completed-phase evidence.
- Self-review/structural verification: isolated Python 3.13 QA interpreter validated UTF-8, exact 92-ID catalog completeness/uniqueness, all IDs referenced from each deliverable, all nine allowed gap states present, and all 160 tracked `docs/` files plus `.bootstrap` source files surveyed. `git diff --check` passed. Documentation only; no tests removed or weakened and no application code changed.
- Remaining: commit the audited deliverables, push only `loop/AUD-1-design-audit`, observe exact-head branch CI and append final SHA/CI evidence below.
