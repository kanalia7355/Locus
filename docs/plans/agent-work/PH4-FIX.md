# PH4-FIX — Phase 4 remainder review fixes (cycle 1)

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

The independent review of the Phase-4 remainder aggregate (PH4-RV,
`docs/plans/agent-work/PH4-RV-phase4-review.md` at `loop/local-development`
HEAD 183ccc3 or later — read it first) returned **accept after minor fixes**
with three findings. Apply them:

1. **Stale Phase-4 status documents**: update the Phase-4 row of
   `docs/plans/PHASE_SPEC_RECONCILIATION.md` and the relevant sections of
   `docs/plans/PHASE_STATUS.md` (and `docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md`
   if it marks these open) to record that ALL FIVE owner-approved Phase-4
   remainder priorities are implemented and integrated with evidence:
   (1) running-question cancellation `5a7848c`, (2) project/storage settings +
   (3) load display `b8bae86`, (4) comparison tables `c381023`, (5)
   destructive-operation confirmations `a30ec52`; independent review PH4-RV
   accept-after-minor-fixes (this fix cycle closes its conditions). No Phase-4
   completion claim beyond the implemented remainder — production items stay
   deferred as recorded.
2. **Cancellation timestamp display bug (P4A)**: in the pending-job UI, the
   timestamp displayed as the running job's start time is UPDATED when
   cancellation is accepted, so the user sees a misleading start time after
   pressing cancel. Fix so the displayed start time stays the ORIGINAL queue/
   dispatch time after `cancelRequested` flips (investigate
   `frontend/src/App.tsx` pendingJob state updates — the cancel path spreads
   `updated` into the display field; keep the server-facing fields intact and
   only freeze the displayed start timestamp). Add a regression test
   (frontend unit) asserting the displayed start time is unchanged after a
   cancel is accepted.
3. **Record CI evidence in checked-in docs**: append to the same docs a dated
   note that the integrated HEAD `183ccc3` (and the P4D integration head
   `a30ec52`) passed Prototype quality, Loop engine checks (4-matrix; the P4D
   windows/3.11 failure was a flake that PASSED on the same-SHA rerun), and the
   title convention.

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH4-FIX -b loop/PH4-FIX origin/loop/local-development` (reuse if it exists). Work ONLY inside it.

ENVIRONMENT NOTE: `.loop/runtime/qa-venv` may have been cleaned — recreate it if
missing (Python313: `"C:/Users/hirot/AppData/Local/Programs/Python/Python313/python.exe" -m venv C:/Users/hirot/Locus/.loop/runtime/qa-venv` then `pip install -e ".[dev]" -r backend/requirements.lock`). NEVER touch the shared `.venv`. Worktree `.venv` junction to the qa-venv for Playwright if the config expects one (a prior reviewer could not run Playwright due to a `_cffi_backend` import failure in the venv — recreate the venv fully and report whether Playwright runs).

QA (repeat until ALL green): full pytest (tests -q --ignore=tests/e2e), ruff
check + format --check, mypy backend/app, secret scan; frontend lint/test/build
+ npx playwright test (npm ci --offline if deps missing).

Then: Conventional Commit (`fix(chat): preserve the displayed start time after cancellation and record phase-4 evidence`); push `loop/PH4-FIX`; wait branch CI; fix/re-push until ALL green (bounded). Append progress + SHA + CI evidence to this file's ## Progress.

Boundaries: never push to `main` or `loop/local-development`; scope is the
three findings only; no subagents.
