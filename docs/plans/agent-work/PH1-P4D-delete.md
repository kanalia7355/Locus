# PH1-P4D — Phase 4 remainder (5): safe delete operations in the admin area

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

Owner-approved Phase 4 remainder, priority 5: **管理メニューの削除操作**, with
MANDATORY 対象確認 (explicit target confirmation)・認可・監査・誤操作対策 per the
owner's priority list. The reconciliation doc lists "保存削除画面不足".

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-P4D-delete -b loop/PH1-P4D-delete origin/loop/local-development` (reuse if it exists). Work ONLY inside it. NOTE: another job (PH1-P4C) is changing the CHAT answer rendering in ITS OWN worktree — keep your changes confined to the ADMIN area (App.tsx admin sections + new components). The integrated P4B added AdminSettings with project/storage/load screens — extend, do not duplicate.

Scope — deletion operations that the backend ALREADY models or where a deletion
is safe and reversible-by-design in the prototype:
1. Survey first: what delete/remove operations exist in `backend/app/service.py`
   (document removal, membership removal, session revocation, etc.) and which
   lack admin UI. Only expose operations whose backend semantics are already
   safe (transactional, audited). Do NOT invent new destructive backend
   capabilities (e.g. no bulk delete, no cascade beyond existing behavior).
2. UI: each destructive action requires (a) an explicit confirmation step
   naming the exact target (type-to-confirm or dialog with the target id/name
   shown), (b) accessible names per the UI baseline, (c) failure keeps prior
   state and shows the error, (d) no accidental double-submit (disable during
   in-flight).
3. Backend: if an operation lacks an admin endpoint, add it with the existing
   conventions (system_admin ceilings, `_limit`, transactional metadata-only
   audit in the SAME transaction, live permission recheck inside the
   transaction mirroring the PH2-B/PH1-J pattern). Deletion must never grant
   new access to anyone.
4. Regressions: authz 403s, confirmation-flow states, audit records, rate
   limits, revoked-access effects (deleting a project/user relation revokes
   access per existing rules), no cascade surprises.

ENVIRONMENT NOTE: `.loop/runtime/qa-venv` may have been cleaned by the loop
engine — if missing, recreate it:
`"C:/Users/hirot/AppData/Local/Programs/Python/Python313/python.exe" -m venv C:/Users/hirot/Locus/.loop/runtime/qa-venv`
then `python -m pip install -e ".[dev]" -r backend/requirements.lock`. NEVER
touch the shared `C:/Users/hirot/Locus/.venv` (broken, Python 3.10.6). For the
frontend e2e server, create a worktree-local `.venv` junction to the qa-venv if
the playwright config expects one.

QA (repeat until ALL green): full pytest (tests -q --ignore=tests/e2e), ruff,
mypy, secret scan; frontend lint/test/build + Playwright (npm ci --offline if
needed).

Process: implement → adversarial self-review (irreversibility, authz, audit
accuracy, UI races) → QA → Conventional Commit (`feat(admin): safe delete operations with confirmation and audit`) → push `loop/PH1-P4D-delete` → wait branch CI → fix/re-push until ALL green (bounded). Append progress + SHA + CI evidence to this file's ## Progress.

Boundaries: never push to `main` or `loop/local-development`; no chat-area
work; no new destructive backend capabilities beyond existing semantics; no
subagents.

## Progress
- 2026-11-09: Read task brief, project governance/product/architecture/bootstrap, loop scope/acceptance/decisions, GitHub workflow, UI baseline and image, multiuser design, and P4B admin implementation. Fetched `origin/loop/local-development`; created isolated worktree `.loop/runtime/worktrees/PH1-P4D-delete` on `loop/PH1-P4D-delete` at `ace8248`. Initial survey: document delete is owner-only (`delete_document`, transactional `document.delete` audit); conversation delete is owner-only and audited; project membership removal has a system-admin endpoint, per-actor limit, live session/system-admin recheck and transactional metadata audit; account disable has the same guards and revokes all sessions (re-enable only permits future login). There is no safe user/document hard-delete API. Plan is to add explicit exact-target confirmation in the existing AdminProjects/AdminUsers UI for the already-safe membership removal and account-disable operations; do not add new deletion authority or cascades.
- 2026-11-09: Implemented exact-target confirmation screens for membership removal and account disable, including target IDs and consequences, cancel paths, in-flight disabling, duplicate-submit guards, and failure-state preservation. Added unit/e2e regressions. Adversarial self-review confirmed the UI only invokes existing APIs and introduces no new delete authority/cascade; failures retain prior rows and confirmation state; a synchronous ref guard prevents duplicate API calls. Existing backend tests cover system-admin 403s, per-actor rate limits, transactional audit rollback/metadata, membership revocation and disable-session revocation; no backend changes were needed.
- 2026-11-09: Synced the worktree fast-forward to integrated HEAD `afb97a4` (`origin/loop/local-development`). Final local QA: `pytest tests -q --ignore=tests/e2e` — 1,145 passed, 18 environment skips; Ruff check and format — passed; mypy backend/app — passed; offline secret scan — 0 findings; frontend lint — passed; Vitest — 60 passed; build — passed; Playwright — 11 passed. An initial Playwright run found a wrong expectation for generated user IDs; corrected the assertion and reran the full suite successfully.
- Delivery handoff: no commit SHA, Push, or branch CI evidence. `.agents/skills/implementation-loop/SKILL.md` explicitly prohibits implementation agents from committing/pushing/merging and assigns delivery to the deterministic Controller; the uncommitted worktree is preserved for that authorized step.
