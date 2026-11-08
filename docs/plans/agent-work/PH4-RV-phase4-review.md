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

- (reviewer appends here)
