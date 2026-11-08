# PH4-RV — Independent read-only review of the Phase-4 remainder aggregate

Agent: append your progress under "## Progress" below. You are a REVIEWER: do
not modify any file other than this one (your progress notes), do not spawn
agents, do not push, do not create a persistent worktree. Work in the main
checkout read-only.

## Task brief

Review the Phase-4 remainder aggregate, integrated into `loop/local-development`
at HEAD 63cc5cb or later:

1. **P4A — running-question cooperative cancellation** (integrated `5a7848c`):
   `backend/app/service.py` chat_jobs `cancel_requested` handling, atomic
   queued→executing→cancelled transitions, cancel-racing-completion resolution,
   idempotent repeats, frontend cancel affordance.
2. **P4C — structured comparison tables** (integrated `c381023`):
   `frontend/src/StructuredCitationText.tsx` + chat renderer; deterministic
   client-side table derivation from retrieved source text; ambiguous fallback;
   accessibility; no model calls.
3. **P4D — destructive-operation confirmations** (integrated `a30ec52`):
   AdminSettings/App.tsx confirmation flows for membership removal and account
   disable naming the exact target; no new deletion authority; backend
   conventions preserved.

Review criteria:
1. Correctness & security: authz on every touched path, no new access grants,
   audit accuracy (metadata-only in-transaction), rate limits preserved, no
   injection via the table renderer (source text is untrusted), no answer
   fabrication, cancellation cannot resurrect a completed answer or leak
   another user's job.
2. Spec conformance: the Phase-4 row of `PHASE_SPEC_RECONCILIATION.md`, the UI
   baseline (`docs/planning/UI_IMPLEMENTATION_BASELINE.md`), and the owner's
   priority list (確認・認可・監査・誤操作対策 mandatory for deletes).
3. Evidence: spot-check recorded QA counts (P4C 1145/18+61+12; P4D 1145/18+60+11;
   integrated 1154/9) and CI runs (P4C green at 6b6f940; P4D green at 5d779b3
   after a windows/3.11 flake rerun) against the real files/history.
4. Boundaries: no approved boundary weakened; no test weakened; Conventional
   Commits everywhere; the P4D flake handling (same-SHA rerun) is legitimate.

Verdict: accept / accept after minor fixes / needs major rework. Findings with
severity, location, evidence, fix recommendation. Do not edit anything except
this file.

## Progress

### Independent review — 2026-11-08

**Verdict: accept after minor fixes.** No blocking correctness/security defect found in P4A/P4C/P4D. One non-blocking documentation reconciliation remains; the recorded final-integrated CI evidence should also be made explicit before any later merge/completion declaration.

#### Findings

- **LOW — stale phase tracking; reconcile before declaring Phase 4 complete.** `docs/plans/PHASE_SPEC_RECONCILIATION.md` Phase 4 still says running cancellation is unavailable, structured comparison is absent, and admin project/storage/load/delete screens are missing. `docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md` P4 row likewise still labels P4B in progress and comparison/delete queued. This conflicts with the integrated code and the completion entry in `docs/plans/agent-work/ORCHESTRATOR_LOG.md`. Update those status/delta fields and verification evidence, preserving still-open load/fairness/capacity requirements rather than claiming full product completion.

- **LOW — running-job start time becomes inaccurate after a cancel request.** `backend/app/service.py:1718-1721` updates `chat_jobs.updated` when setting `cancel_requested`; `backend/app/service.py:516-530` reports that same `updated` value as `running_job.started_at`. Thus a running cancellation makes the admin load screen show the cancellation-request time as the job's start time. Preserve a separate start timestamp or stop labeling the mutable `updated` time as `started_at`; add a regression for cancel-request metadata if the load screen is intended to show elapsed run time. This does not affect cancellation arbitration or answer privacy.

- **LOW — integrated CI record is incomplete in the checked-in ledger.** The recorded QA spot-checks match the brief: P4C (`docs/plans/agent-work/PH1-P4C-comparison.md`) says backend `1145 passed/18 skipped`, Vitest `61`, Playwright `12`; P4D (`docs/plans/agent-work/ORCHESTRATOR_LOG.md`) says backend `1145/18`, Vitest `60`, Playwright `11`; integrated regression is `1154 passed/9 skipped`. The records say P4C CI was green at `6b6f940`, and P4D CI green at `5d779b3` after the Windows/3.11 racing-controller failure passed on a same-SHA rerun. Git history confirms `705bad6` → `6b6f940` → `c381023` and `5d779b3` → `a30ec52`, with no repair/change commit between the reported P4D rerun SHA and integration; same-SHA handling is legitimate as recorded. However, the ledger says integrated-HEAD CI (`a30ec52`) was to be checked in the next CI window and I found no later checked-in confirmation/run IDs. Record the exact integrated-HEAD result before a completion/merge gate; do not infer it from the feature-branch runs. Raw hosted run details were not available in this read-only repository inspection, so run outcomes are verified against repository records/history, not independently queried from GitHub.

#### Review evidence and code findings

- **P4A cancellation:** `backend/app/service.py` `cancel_chat_job`, `_cancel_chat_if_requested`, `send`, `process_next_chat`, and `_finish_chat` serialize transitions in the database transaction. A running DELETE records `cancel_requested` without interrupting `LocalModel.generate`; completion checks the flag in the same transaction that inserts the message/answer and marks the job done. Cancellation winning leaves no message/answer and becomes terminal cancelled; completion winning leaves a completed answer and subsequent cancel returns 409. Repeated cancellation is idempotent, queued-to-running arbitration is conditional, request/status endpoints filter by owner, and the same per-user chat-job rate limit applies. `tests/test_chat_queue.py` covers running cancellation, timeout, racing completion, ownership, rate limiting, and no-persistence assertions. Frontend polling in `frontend/src/App.tsx` keeps the job pending until authoritative terminal status, hides the cancel affordance once accepted, and renders cancelled without an answer; `frontend/src/ChatQueue.test.tsx` covers accepted, terminal, and failed cancellation states. Existing queue caps/contracts and the single bounded, no-retry model call in `backend/app/local_model.py` remain intact.

- **P4C structured rendering:** `frontend/src/StructuredCitationText.tsx` uses deterministic Markdown/TSV parsing and React text nodes (no `dangerouslySetInnerHTML`, model call, or table-generation request). Ambiguous row shapes fall back to the original citation text. Table headers and the first-column row headers are semantic; the scroll region has an accessible label, keyboard focus, and arrow-key scrolling. `frontend/src/App.test.tsx` exercises literal script-like input as text, TSV/Markdown and ambiguous fallback; `frontend/e2e/workspace.spec.ts` covers table roles and narrow viewport scrolling. No content is invented beyond source cells. UI styling in `frontend/src/styles.css` is neutral and consistent with the approved baseline.

- **P4D destructive confirmations:** `frontend/src/AdminSettings.tsx` membership removal and `frontend/src/App.tsx` account disable show exact user/project names and IDs, consequences, cancel/confirm controls, and disable while in-flight. Failure preserves the existing row and confirmation; synchronous guards prevent duplicate submission. These only call existing backend endpoints. `backend/app/service.py` `remove_project_member` and `set_user_enabled` retain live authentication/system-admin checks, per-actor limits, transactional metadata-only audit, and existing revocation effects (membership access removal; account session revocation). No new deletion authority or cascade was introduced. Corresponding tests cover 403/rate/audit/revocation contracts and UI confirmation/failure states.

- **Scope/boundaries:** reviewed feature and integration commits use Conventional Commit subjects. No test/spec weakening or approved-boundary expansion was found. The reconciliation table's stale status is called out above, not treated as an implementation regression.

#### Verification performed in this review

- Full backend suite: `.loop/runtime/qa-venv/Scripts/python.exe -m pytest tests -q --ignore=tests/e2e` — **1154 passed, 9 skipped**.
- Ruff check, format check, and mypy: **passed**. Offline secret scan: **0 findings**.
- Frontend Vitest: **62 passed**; ESLint and production build: **passed**.
- Playwright could not be rerun locally: the repository's configured `.venv` E2E server fails to import `_cffi_backend` (Python 3.10.6 shared environment). This is an environment limitation, not a test pass; historical P4C/P4D E2E counts are recorded in their task files/ledger (12 and 11 respectively).
- No implementation files were changed; only this review note was edited.
