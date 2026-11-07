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
