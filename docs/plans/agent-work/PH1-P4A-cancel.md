# PH1-P4A — Phase 4 remainder (1): running-question cancellation and state consistency

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

Owner-approved Phase 4 remainder, priority 1 of 5: **実行中質問の取消と状態整合性**
(cancellation of a RUNNING question and state consistency), per
`docs/plans/PHASE_SPEC_RECONCILIATION.md` Phase-4 row ("実行中質問の中断は不可
（実行中表示のみ）") and the waiting-queue design in the same row.

Current behavior (verify in code first): `backend/app/service.py` chat_jobs —
queued jobs can be cancelled; an EXECUTING job cannot (the model slot is held by
`LocalModel.generate`'s non-reacquirable lock and the request is a single bounded
HTTP call to Ollama; see `backend/app/local_model.py`). `docs/PHASE_STATUS` and
tests/test_chat_queue.py define the existing contracts you must not weaken:
sync 200 / queued 202, waiting-only cancellation, owner-scoped job visibility,
300s wait cap, 16/2 limits.

Required behavior:
1. A cancel request on an EXECUTING job must be accepted and recorded, and the
   job must reach a terminal cancelled state as soon as the in-flight model call
   finishes (or its process-local deadline expires); the slot must not be
   re-dispatched with the cancelled job's work. Design the cooperative-cancellation
   flag so the executing request itself is not killed mid-flight (single bounded
   HTTP remains intact — no tool calls, no retries); the cancelled outcome must
   never be persisted as an answer and must not be returned as the conversation's
   answer.
2. State consistency: queued→executing→cancelled transitions are atomic; cancel
   racing completion resolves to exactly one terminal state (completed keeps the
   answer; cancelled discards it); repeated cancel is idempotent; owner-only
   authorization and rate limits apply; metadata-only audit as usual.
3. Frontend: the running state gains a cancel affordance (readable name, per
   UI baseline), shows the accepted-cancel state, and after completion shows
   cancelled instead of an answer. Failed cancels keep prior state and show the
   error.

Constraints: read `backend/app/service.py` chat_jobs + `backend/app/local_model.py`
+ `tests/test_chat_queue.py` + frontend chat queue components first; follow
existing conventions exactly; do NOT weaken the existing queue tests; the single
model slot semantics stay unchanged; no new limits beyond what the design verifies.

QA (repeat until ALL green): full pytest (tests -q --ignore=tests/e2e), ruff
check + format --check, mypy backend/app, secret scan; frontend `npm run lint`,
`npm test`, `npm run build`, `npx playwright test` (in frontend/; use npm ci
--offline for worktree deps). Add regressions for every behavior above.

Process: own worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-P4A-cancel -b loop/PH1-P4A-cancel origin/loop/local-development`; work ONLY inside it. Implement → adversarial self-review → QA → Conventional Commit (`feat(chat): cooperative cancellation of running questions`) → push → wait branch CI → fix/re-push until ALL green (bounded). Append progress + SHA + CI evidence here. Branch is deleted after integration.

Boundaries: never push to `main` or `loop/local-development`; no admin-page work
(another job owns the admin screens); no LocalModel behavior changes beyond the
cooperative-cancellation flag; do not spawn subagents.

## Progress

- Relaunch verification: inspected the existing chat job implementation, LocalModel's single bounded HTTP request and non-reacquirable lock, queue tests, frontend polling/cancel affordance, API response schema, the Phase-4 reconciliation row, and approved UI baseline. Confirmed queued 202 / synchronous 200 contracts and 300s / 16 / 2 caps are unchanged. Fast-forward merged `origin/loop/local-development` (including subsequent docs-only commits) with no conflict and no force-push.
- Adversarial draft review: confirmed serialized SQLite transitions arbitrate cancellation vs completion; cancelled running output is checked before publication and answer/message/job completion commit together; timeout/failure path also honors the cancel flag; repeat cancellation is idempotent; owner filtering and per-user rate limit remain. Found a UI race: cancellation can succeed after the server starts a job but before the next poll updates the UI, so treating the stale local `queued` state as terminal hid the still-running job. Fixed frontend to retain the pending state and poll for the authoritative terminal cancellation, and removed duplicate state updates. Added regressions for running-call timeout, cancellation authorization/rate limits, and frontend pending-state behavior. Full QA and delivery remain pending.

## Orchestrator delivery postscript (2026-11-08)

- The delivery relaunch run died with the provider-wide 429 rate limit; the orchestrator completed the authorized delivery with an isolated QA venv (`.loop/runtime/qa-venv`, Python 3.13) because the shared `.venv` had been switched to Python 3.10.6 without the project dependencies (environment change recorded in the ledger).
- Delivery-time fixes: two ruff issues in service.py (long line split; unused variable removed — behavior preserved); three ChatQueue test harness fixes (queued-cancel mock now transitions to `cancelled` after DELETE; duplicate-text assertion uses `getAllByText` because the toast notice and the inline running-status line legitimately share the accepted-cancellation wording; `findByText` timeouts raised to 6s to cover the 2-second status poll). No component logic changed.
- Final local QA: full pytest 1117 passed / 18 skipped; ruff check + format clean; mypy backend/app clean; secret scan 0 findings; frontend lint clean; Vitest 55 passed (13 files); build success; Playwright Chromium 10 passed (worktree `.venv` junction points at the isolated QA venv for the e2e server).
