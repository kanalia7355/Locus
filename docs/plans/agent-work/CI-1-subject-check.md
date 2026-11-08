# CI-1 — Repair check_commit_subjects.py range handling (merge commits + long-lived branches)

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

CI-infrastructure repair. The `conventional-title` workflow (`.github/workflows/pr-title.yml`
→ `scripts/check_commit_subjects.py`) crashes on legitimate pushes from long-lived
branches, recorded twice in the orchestrator ledger:

- New-branch pushes compute the validated range as `merge-base(origin/main, after)..after`,
  which spans the ENTIRE `loop/local-development` history since the last squash
  merge (hundreds of commits) → `ValueError("Empty or oversized Push range requires assessment")`.
- Ranges containing merge commits are rejected as "non-Conventional Commit"
  because the boilerplate merge subject fails the pattern, even when every real
  commit in the range follows the convention.

These are script robustness defects, NOT a way to bypass validation. The fix must
NOT weaken the control: every non-merge commit in the validated range must still
match `PATTERN`, and the script must keep failing on genuine violations.

Fix design (implement exactly this):
1. Keep the existing validation for the normal case.
2. When the `before..after` range is empty or oversized (>200), fall back to the
   branch-local range: `merge-base(origin/loop/local-development, after)..after`
   (fall back further to `origin/main` if that ref is missing). If THAT range is
   also empty, the push added no new non-merge commits — report success with an
   explanatory note instead of crashing.
3. Skip merge commits (subjects matching `^Merge ` or parents ≥ 2) when
   validating; all non-merge commits in the validated range must match `PATTERN`.
4. Add/extend tests: `tests/integration/test_main_bare_promotion.py` imports
   `verify` — extend that file (or add `tests/test_check_commit_subjects.py`)
   covering: normal short range (existing behavior unchanged), range containing
   a merge commit whose sibling commits are conventional (passes, merge skipped),
   oversized-range fallback to the local-development base, empty range success
   with note, and a genuine violation still failing.
5. Run the required local QA with `C:/Users/hirot/Locus/.loop/runtime/qa-venv/Scripts/python.exe`
   (the shared `.venv` is broken): full pytest (tests -q --ignore=tests/e2e),
   ruff check + format --check, mypy backend/app (unchanged), secret scan.

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/CI-1-subject-check -b loop/CI-1-subject-check origin/loop/local-development` (reuse if it exists). Work ONLY inside it.

Then: Conventional Commit (`fix(ci): validate branch-local commit ranges and skip merge subjects`); push `loop/CI-1-subject-check`; wait branch CI; fix/re-push until ALL green (bounded). Append progress + SHA + CI evidence to this file's ## Progress.

Boundaries: never push to `main` or `loop/local-development`; touch ONLY
`scripts/check_commit_subjects.py` and its tests; do not weaken validation
(genuine non-Conventional subjects must still fail); no subagents.
