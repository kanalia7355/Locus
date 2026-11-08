# PH2-UI-delegation

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

# PH2-UI — Delegation management UI (implementation)

Deliverable: the delegation grant/revoke/expiration UI over the integrated
PH2-D backend APIs (GET/POST/DELETE /api/admin/delegations — read
`backend/app/main.py` and `backend/app/service.py` delegation section first).
Additive screens/components in the ADMIN area following
`docs/planning/UI_IMPLEMENTATION_BASELINE.md` (accessible names, no
decorations, IME handling, failed saves retain input): list grants visible to
the actor, grant creation form (recipient, permissions subset within the
grantor's ceiling — server-enforced, TTL selection within 15m-7d), revoke with
confirmation naming the exact target, expired/revoked states shown. Recipient
cancellation for grants received. Regressions: frontend unit + browser tests
(grant flow, TTL validation errors, revoke confirmation, recipient cancel,
403/422 surfacing) and backend additions only if a UI flow is genuinely missing
(existing conventions). Full pytest + frontend QA per the standard cycle.
Commit `feat(admin): delegation management UI`; push branch
`loop/PH2-UI-delegation`; wait branch CI until green.
