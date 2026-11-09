# PH2-C2-storage-acl-plan

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Use the isolated
QA venv `.loop/runtime/qa-venv` (recreate if missing: Python313 venv +
`pip install -e ".[dev]" -r backend/requirements.lock`); NEVER touch the shared
`.venv` (broken). Never push to `main` or `loop/local-development`; no subagents.

Full process: read `AGENTS.md` + governance docs first; create your worktree with
`git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/<SLUG> -b loop/<SLUG> origin/loop/local-development`;
implement; self-review adversarially; run the full QA cycle until ALL green
(full pytest tests -q --ignore=tests/e2e, ruff check + format --check, mypy
backend/app, secret scan; plus frontend lint/test/build/playwright when UI
touched); Conventional Commit; push; wait branch CI; fix/re-push until green
(bounded); append progress + SHA + CI evidence here. Branch deleted after
integration.

---

# PH2-C2 — Storage-destination ACL implementation plan (docs only)

Deliverable: `docs/plans/PHASE2_STORAGE_ACL_IMPLEMENTATION_PLAN.md` — the
implementation plan following the recommended interpretation in
`docs/plans/PHASE2_STORAGE_ACL_RESEARCH.md` (source-location authorization and
lifecycle propagation; existing Locus ACLs preserved; external egress
owner-gated). Content: phased implementation slices (data model, enforcement
points, audit, UI if needed), regression-test plan, what requires owner
decisions (【要決定】), what touches which existing modules. Ground claims in
the research doc and the real code (cite paths); no code changes. Commit
`docs(plans): draft the storage-destination ACL implementation plan`; push
branch `loop/PH2-C2-storage-acl-plan`; wait branch CI until green.

## Progress

- [Step 1] Read brief, PHASE2_STORAGE_ACL_RESEARCH.md, AGENTS.md, DEVELOPMENT_POLICY.md,
  GITHUB_WORKFLOW.md, ARCHITECTURE.md, BOOTSTRAP.md (.bootstrap/complete.json exists).
- [Step 2] Created worktree `.loop/runtime/worktrees/PH2-C2-storage-acl-plan`
  (branch `loop/PH2-C2-storage-acl-plan` from `origin/loop/local-development` @ `951c3cf`).
- [Step 3] Grounded the plan in real code: backend/app/service.py (schema ~385, _can_read 1767,
  _document 1791, documents 1837, chunks 1858, related 1874, upload 1944, _ingestion_allowed 2005,
  process_next, _index 2057, seed_synthetic 2067, cancel 2102, delete_document 2121, publish 2127,
  _citations 2178, _generated 2197, conversation 2210, send 2254, _audit 474, _permissions 1155),
  backend/app/scanner.py, backend/app/main.py routes 338-372 + /api/admin/storage 516,
  frontend/src/AdminSettings.tsx AdminStorage 523, frontend/src/App.tsx storage nav,
  tests/ layout, PHASE_SPEC_RECONCILIATION.md, PHASE_STATUS.md.
- [Step 4] Wrote docs/plans/PHASE2_STORAGE_ACL_IMPLEMENTATION_PLAN.md (docs only; slices 0-6,
  regression-test plan, 12 【要決定】 items, module touchpoints; no decisions made, no code).
- [Step 5] Self-review: verified every cited function/line against the worktree; corrected
  recover_jobs/cancel/seed_synthetic/_ingestion_allowed line refs; confirmed AdminStorage is
  read-only with 外部保存「未実装・無効（既定拒否）」 copy; no activation claims present.
- [Step 6] Commit `4919e4c` `docs(plans): draft the storage-destination ACL implementation plan`;
  pushed `loop/PH2-C2-storage-acl-plan`. CI queued: Prototype quality 42533544320,
  PR title convention 42533544331, Loop engine checks 42533544389.
- [Step 7] CI green at commit `4919e4c` on `loop/PH2-C2-storage-acl-plan`:
  - Prototype quality run 42533544320 — success (3m38s)
  - PR title convention run 42533544331 — success (9s)
  - Loop engine checks run 42533544389 — success (8m25s)
- [Result] Deliverable: docs/plans/PHASE2_STORAGE_ACL_IMPLEMENTATION_PLAN.md (385 lines, docs only,
  no code changes, no owner decisions made). Branch ready for integration; not merged anywhere.
