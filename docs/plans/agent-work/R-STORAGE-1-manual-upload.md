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

## Progress

### 2026-11-09 — slot L implementation

- Reviewed the existing manual-upload path (backend/app/service.py upload →
  queued/scanning → ready/quarantined/cancelled, `send()` lexical retrieval with
  per-document live ACL rechecks, `_citations`/`_generated` provenance gating,
  `related()` linking, frontend App.tsx composer/drag-drop/personal upload,
  IngestionProgress, RelatedDocuments) against AGENTS.md,
  docs/governance/DEVELOPMENT_POLICY.md, docs/requirements/PRODUCT_SPEC.md and
  docs/plans/FINAL_ACCEPTANCE_CRITERIA.md. Owner decisions Q5/Q6 recorded in
  docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md were respected; no connectors,
  no egress, no ACL weakening, production still deferred (Q7).
- Identified two bounded gaps in the DATA-009/DATA-014 evidence class ("expose
  ingestion status and supported outcomes without unsupported claims"):
  1. `/api/admin/storage` did not reveal whether a safety-scanner adapter is
     actually configured, so an administrator could not tell a fail-closed
     default (everything quarantined, no scan possible) from a scan verdict.
  2. The quarantine reason conflated "safety check rejected the upload" with
     "the safety check could not run at all".
- Implemented (commit `56f85e0` — feat(storage): improve the manual-upload
  research flow):
  - backend/app/service.py: `Service` now records `scanner_configured` (only an
    adapter that can actually perform the check counts), reports it in
    `storage_status`, and `process_next()` writes an honest fail-closed reason
    (安全検査を実行できないため隔離中です（既定拒否）) when no scanner is
    configured. Ingestion still fails closed in both cases; quarantined content
    remains excluded from search; status, ACL and retrieval semantics unchanged.
  - frontend/src/AdminSettings.tsx: admin storage panel shows the safety-check
    state (有効 / 未接続（既定拒否）) without claiming production readiness.
  - tests: tests/test_api.py covers configured (ready) and unconfigured
    (quarantined + reason + scanner_configured=False) ingestion paths;
    tests/test_admin_project_storage_load.py exact admin-storage contract
    updated; frontend/src/AdminSettings.test.tsx covers both display states.
- Local QA (isolated .loop/runtime/qa-venv, Python 3.13; shared .venv untouched):
  - `ruff check backend tests scripts` — pass
  - `ruff format --check backend tests scripts` — pass (128 files)
  - `mypy backend/app` — pass
  - `pytest tests -q --ignore=tests/e2e` — 1158 passed, 18 skipped
  - frontend `npm run lint` — pass; `npm test` — 72 passed;
    `npm run typecheck` — pass; `npm run build` — pass
  - Playwright `npm run test:e2e` — 13 passed (webServer python resolved via a
    gitignored worktree-local .venv junction pointing at the isolated
    .loop/runtime/qa-venv; no shared venv was created or modified)
  - `scripts/secret_scan.py` — 0 findings
- Pushed to origin loop/rstorage1-manual-upload (56f85e0). CI evidence:
  PR title convention run 42651187472 — success. Prototype quality run
  42651187449 and Loop engine checks run 42651187438 — in progress at the time
  of this entry; final results recorded below.
