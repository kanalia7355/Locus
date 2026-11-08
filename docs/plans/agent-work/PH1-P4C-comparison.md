# PH1-P4C — Phase 4 remainder (4): structured comparison table

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

Owner-approved Phase 4 remainder, priority 4: **比較表の構造化表示**, per
`docs/plans/PHASE_SPEC_RECONCILIATION.md` Phase-4 row ("比較表の構造化表示なし")
and `docs/planning/ui-and-multiuser-design.md`. The UI baseline notes that the
baseline image's table/PDF names/values are SAMPLES — matching their literal
wording is NOT an acceptance condition, but a practical structured comparison
display is expected.

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-P4C-comparison -b loop/PH1-P4C-comparison origin/loop/local-development` (reuse if it exists). Work ONLY inside it. NOTE: another job (PH1-P4D) is adding delete operations to the admin area in ITS OWN worktree — keep your changes confined to the CHAT/answer rendering area of App.tsx and new components.

Scope (read the actual answer/citation rendering first):
1. When an answer contains tabular content (the current chat rendering shows
   plain text from lexical retrieval sources), render a structured, accessible
   table (proper <table> with headers, keyboard navigable, screen-reader labels
   per UI_IMPLEMENTATION_BASELINE.md; no new decorations).
2. The table must be derived deterministically from the source text (e.g.
   markdown/TSV-like structures in the retrieved excerpt); ambiguous content
   falls back to the existing plain rendering. No AI/table generation, no model
   calls — pure client-side formatting of retrieved source text.
3. IME handling, narrow-width/mobile behavior, long-content scrolling per the
   baseline; a text/table toggle only if it aids accessibility.
4. Backend: no changes expected; if any are needed they must follow existing
   conventions.

ENVIRONMENT NOTE: `.loop/runtime/qa-venv` may have been cleaned by the loop
engine — if missing, recreate it:
`"C:/Users/hirot/AppData/Local/Programs/Python/Python313/python.exe" -m venv C:/Users/hirot/Locus/.loop/runtime/qa-venv`
then `python -m pip install -e ".[dev]" -r backend/requirements.lock` (offline
flags allowed). NEVER touch the shared `C:/Users/hirot/Locus/.venv` (broken,
Python 3.10.6). For the frontend e2e server, create a worktree-local `.venv`
junction to the qa-venv if the playwright config expects one.

QA (repeat until ALL green): full pytest (tests -q --ignore=tests/e2e), ruff,
mypy, secret scan; frontend npm run lint / npm test / npm run build / npx
playwright test (npm ci --offline if deps missing). Add unit + browser
regressions (table renders from a fixture excerpt, fallback for ambiguous
text, accessibility roles).

Process: implement → adversarial self-review (injection via table markup,
accessibility, no content fabrication) → QA → Conventional Commit
(`feat(chat): structured comparison tables for retrieved source content`) →
push `loop/PH1-P4C-comparison` → wait branch CI → fix/re-push until ALL green
(bounded). Append progress + SHA + CI evidence to this file's ## Progress.

Boundaries: never push to `main` or `loop/local-development`; no admin-area or
delete-operation work; no model calls; no subagents.
