# R-STORAGE-2 — Fix the MEDIUM finding from the 5-package aggregate review

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit any other file outside this brief, the code paths below, and their tests.
You own a dedicated worktree on branch loop/rstorage2-scanner-status-fix. Never push
main or loop/local-development. Never spawn subagents. On a model/provider quota
error, record it and stop.

## Finding (from DESIGN-REVIEW-aggregate, slot O, MEDIUM)

R-STORAGE-1's fail-closed ingestion is preserved, but a configured-yet-unreachable or
erroring scanner is reported as a failed verdict ("安全検査を通過していない") instead of an
unavailable check, indistinguishable from an actual rejection. The admin UI also says
safety inspection is "有効" even when the scanner cannot run. Recommendation (minimal):

- Preserve quarantine for EVERY non-clean result (fail-closed unchanged — do not weaken).
- Represent clean / rejected / unavailable-or-error as separate, truthful statuses (or a
  typed scanner result).
- Report adapter configuration separately from operational/scan outcome.
- Add tests covering: configured scanner timeout/exception → still quarantined with
  truthful status/reason; explicit rejection → still quarantined with rejected status.

## Scope

- backend/app/service.py (process_next/_ingestion_allowed status handling)
- backend/app/scanner.py (typed result; no connectivity checks that change fail-closed)
- frontend/src/AdminSettings.tsx (status display distinguishes 有効/検査不能/拒否)
- backend tests (test_api.py etc.) + frontend tests (AdminSettings.test.tsx)
- docs/plans/agent-work/R-STORAGE-2-scanner-status-fix.md (progress only)

## Acceptance

- All 1158+ pytest tests pass locally; frontend lint + vitest + typecheck + build pass.
- No ACL weakening, no connector/egress addition, no activation claims.
- Conventional Commit subject suggestion: `feat(storage): report scanner failure as an unavailable check, not a failed verdict`
- Push your branch, record CI evidence in ## Progress, then mark 完了.

## Progress

Agent: append your progress under ## Progress at each step end and at task end, and push.

### 2026-11-10 — status check (orchestrator cycle)

Implementation in progress in this worktree (branch loop/rstorage2-scanner-status-fix),
not yet committed; no blocker, no quota error. Done so far, uncommitted:

- `backend/app/scanner.py`: typed fail-closed result (`ScanResult` with
  `clean` / `rejected` / `unavailable`); timeout/connection errors, busy adapter,
  truncated or malformed daemon replies now report `unavailable` instead of being
  conflated with a rejection verdict; explicit non-clean daemon verdicts report
  `rejected`; no connectivity checks added, quarantine semantics unchanged.
- `backend/app/service.py`: `Scanner` protocol and `UnavailableScanner` use the typed
  result; `process_next` keys the quarantine reason off the outcome (rejected vs
  unavailable) instead of adapter configuration; adapter configuration
  (`scanner_configured`) is now reported separately from the operational outcome
  (`scanner_last_outcome`, None until the first scan) in `storage_status`.
- `frontend/src/AdminSettings.tsx`: 安全検査 display now distinguishes 有効 /
  検査不能 / 拒否 via `scannerStatusText(status)`; `StorageStatus` carries
  `scanner_last_outcome`.
- Tests updated/added: `tests/test_scanner.py` (typed outcomes),
  `tests/test_api.py` (configured scanner timeout/exception → quarantined with
  unavailable reason + status; explicit rejection → quarantined with rejected
  reason + status; `scanner_last_outcome` clean on success),
  `tests/test_admin_project_storage_load.py` (exact storage-status payload),
  scanner fakes in `tests/test_security.py` / `tests/test_delegations.py`,
  `frontend/src/AdminSettings.test.tsx` (検査不能 and 拒否 display states).
- Not yet run: local QA (ruff/mypy/pytest, frontend lint/vitest/typecheck/build).
  Next: run QA, fix fallout, commit + push, then branch CI evidence.
