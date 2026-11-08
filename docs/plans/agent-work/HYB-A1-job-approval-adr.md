# HYB-A1-job-approval-adr

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

# HYB-A1 — Job-approval/authorization ADR draft (docs only)

Deliverable: `docs/architecture/decisions/` ADR DRAFT (next number, follow the
existing format; likely 0013) for the Phase-2/Plane-R **job approval and
authorization receipt** mechanism — the hard prerequisite for any
dispatch-capable Plane-R code (slice 2b) per
`docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` sections 2.6/E1-E2 and its
owner-resolved item 11 (`docs/plans/OWNER_DECISION_REGISTER.md` RESOLVED
2026-11-09; also `docs/plans/PHASE2_DELEGATION_SPEC.md`).

Requirements for the draft: receipt content (actor, approver, workspace,
policy version, adapter/destination, operation, expiry), authoritative issuer
and revocation mechanism, recheck points at enqueue AND runner execution,
denial/revocation/stale-approval semantics and their regression tests,
actor/approver scopes, approval-expiry policy, and integration with the
existing role/permission ceilings (NON_ADMIN) and audit conventions. Mark
everything undecidable as 【要決定】; do NOT approve activation; status DRAFT.
Ground every claim in the real repository (cite files). Self-review against
ADR-0012 (ACCEPTED), the threat model, and the step-2 design's E1/E2. Commit
`docs(adr): draft the job approval and authorization receipt ADR`; push your
branch `loop/HYB-A1-job-approval-adr`; wait branch CI until green.
