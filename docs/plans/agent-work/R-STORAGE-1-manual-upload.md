# R-STORAGE-1 — Complete the approved manual-upload research flow

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. This task may
involve CODE changes (not just docs). Never push to `main` or `loop/local-development`;
no subagents of your own. Use the isolated `.loop/runtime/qa-venv` (recreate if missing:
Python 3.13 venv + `pip install -e ".[dev]" -r backend/requirements.lock`); NEVER touch
the shared `.venv`.

## Task

Resume and complete the already-approved manual-upload path and its research-support
acceptance per the resumable-jobs plan (`docs/plans/RESUMABLE_JOBS_2026-11-09.md`
§R-STORAGE-1). The owner's formal decisions Q1–Q7 are recorded in
`docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md`.

**Scope:**
- Review the current manual-upload path (upload, safe ingestion, search/retrieval,
  citation/provenance, analysis) against existing requirements and acceptance criteria.
- Identify gaps and improvement opportunities in the manual path.
- Implement bounded improvements grounded in existing requirements — this MAY include
  code changes (backend/frontend) that enhance the manual upload → search → cite →
  analyse flow.
- Do NOT remove or weaken research requirements because connectors are deferred.
- Do NOT implement connectors (local folder, NAS, online storage) — those are deferred
  to a later phase with gates (owner Q5).

**Owner decision relied on:** Q5 prioritizes manual uploads and defers local-folder/NAS/
online-storage connectors to a later phase; Q6 denies access immediately when source
permission is lost and separates retention/deletion from access denial.

**Safety boundary that must not change:**
- No connector, source credential, network access, external transfer or egress.
- Preserve document/project ACLs, private-by-default personal documents.
- Fail-closed scanner/parser behavior and live authorization.
- Revocation blocks read/search/citation/reuse, including existing derived answers.
- Do not infer immediate physical deletion or upstream write/delete permission.
- Production stays deferred (owner Q7).

**Completion gate:** each manual-upload change meets the existing product/source
acceptance, preserves unconnected-document behavior and access-denial semantics,
passes applicable backend/frontend/security QA and independent review where required,
and has exact-head required CI. No production readiness or connector support is claimed.

## Process

Read AGENTS.md + docs/governance/DEVELOPMENT_POLICY.md, then the owner decisions
(docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md), then the existing research-upload
code (backend/app/ and frontend/src/) and its tests. Identify gaps and implement
bounded improvements. Run the FULL QA cycle: ruff check + ruff format --check,
mypy backend/app, `.venv/Scripts/python.exe` or qa-venv `pytest tests -q
--ignore=tests/e2e`, frontend `npm test` when UI changed, Playwright when UI changed.
Conventional Commit (`feat(...)` or `fix(...)` or `docs(plans): ...` as appropriate);
push origin loop/rstorage1-manual-upload; repeat the fix cycle until ALL configured
checks pass. Append progress + SHA + CI evidence to this file under ## Progress at
each step end and at task end, and push.

Conventional Commit subject suggestion: `feat(storage): improve the manual-upload research flow`
