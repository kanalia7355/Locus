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
