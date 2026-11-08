# PH2-2AF — Slice 2a review fixes (audit ordering + pre-auth validation)

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

The independent review of the integrated slice 2a (PH2-2AR,
`docs/plans/agent-work/PH2-2AR-slice2a-review.md` at `loop/local-development`
HEAD 278d25d or later — read it first) returned **accept after minor fixes** with
one MEDIUM finding in `backend/app/agents/registry.py`:

- Unauthenticated / non-admin requests are AUDITED before the rate limiter runs,
  allowing repeated requests to grow the audit table.
- Malformed admin writes can fail request validation (422) BEFORE authentication
  and auditing — e.g. an anonymous adapter-registration POST with `{}` returns
  422 without an audit event.

Fix (owner decisions not required — this strengthens existing behavior):
1. Order each registry admin/dispatch path as: rate limit → authentication →
   authorization → validation → mutation + audit, so unauthenticated floods are
   rate-limited first and every rejected write is still audited exactly once
   after authentication (metadata-only, in-transaction, as today).
2. Where request-body validation currently short-circuits before auth, restructure
   so authentication/authorization happen before validation failures are returned
   (keep the same 422 semantics for authenticated admins; unauthenticated callers
   get the standard 401).
3. Do NOT weaken the existing dispatch-rejection gate, policy immutability,
   capability 422+audit behavior, or any test; extend the regressions to cover:
   (a) repeated unauthenticated attempts hit the rate limit and do NOT each write
   an audit row, (b) malformed-body requests from anonymous callers are audited
   (once) and rejected 401, (c) authenticated admin with malformed body gets 422
   + audit.
4. Check the same ordering issue across the OTHER registry paths in the same
   module (workspace/policy/binding/health endpoints) and align them; record any
   judgement.

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH2-2AF-registry-fix -b loop/PH2-2AF-registry-fix origin/loop/local-development` (reuse if it exists). Work ONLY inside it.

QA (repeat until ALL green): full pytest (tests -q --ignore=tests/e2e), ruff
check + format --check, mypy backend/app, secret scan — using
`C:/Users/hirot/Locus/.loop/runtime/qa-venv/Scripts/python.exe` (the shared
`.venv` is Python 3.10.6 without project deps — do NOT use or modify it).

Then: Conventional Commit (`fix(agents): order rate limiting and authentication before audit in the registry`); push `loop/PH2-2AF-registry-fix`; wait branch CI; fix/re-push until ALL green (bounded). Append progress + SHA + CI evidence to this file's ## Progress.

Boundaries: never push to `main` or `loop/local-development`; scope is the
ordering fix + regressions only; no subagents.
