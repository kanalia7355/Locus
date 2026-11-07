# PH1-P4B — Phase 4 remainder (2+3): admin project/storage settings and load display

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

Owner-approved Phase 4 remainder, priorities 2+3 of 5 (combined into ONE job to
avoid three-way conflicts in the shared admin page): **管理メニューのproject・保存先
設定** and **管理メニューの負荷表示**, per `docs/plans/PHASE_SPEC_RECONCILIATION.md`
Phase-4 row ("管理メニューのproject/保存先/負荷/保存削除画面不足").

Scope:
1. Project settings screen (admin): list existing projects, create a project,
   assign/remove members where the backend already supports it; every mutation
   follows existing role ceilings (system_admin), rate limits, and metadata-only
   audit conventions. If a needed backend endpoint does not exist, add it
   backend-side with the same conventions (atomic, audited, transactional).
2. 保存先 (storage destination) settings: the prototype's storage is local
   bounded ingestion; provide a read-only status/config view plus explicitly
   guarded configuration where a backend setting already exists. Do NOT invent
   new storage backends or credentials; anything that would enable external
   storage stays a marked placeholder (default deny, owner gate noted in UI
   text).
3. Load display: show current model-slot/chat-queue state (queue length, running
   job, per-user limits) from existing backend state; read-only endpoint if
   needed, admin-visible, no new enforcement.
4. UI baseline rules apply: sidebar/chat/admin layout per
   `docs/planning/UI_IMPLEMENTATION_BASELINE.md`, accessible names, IME handling,
   no new decorations; failed saves retain input; destructive actions are NOT in
   this job (priority 5 delete operations belong to a later job).

Constraints: read `frontend/src/App.tsx` admin sections, `backend/app/main.py`
admin endpoints, `backend/app/service.py` (users/projects/roles), and the
multiuser design doc first. Another job is changing the CHAT area of App.tsx
(running-question cancellation) — keep your UI changes confined to the admin
settings sections and new components to minimise conflicts.

QA (repeat until ALL green): full pytest, ruff, mypy, secret scan; frontend
lint/test/build + Playwright (npm ci --offline for worktree deps). Add backend
and frontend regressions for each new screen/endpoint (authz 403s, validation,
audit, state display).

Process: own worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-P4B-admin-screens -b loop/PH1-P4B-admin-screens origin/loop/local-development`; work ONLY inside it. Implement → adversarial self-review (authz, injection, audit accuracy) → QA → Conventional Commit (`feat(admin): project/storage settings and load display screens`) → push → wait branch CI → fix/re-push until ALL green (bounded). Append progress + SHA + CI evidence here.

Boundaries: never push to `main` or `loop/local-development`; no chat-area or
delete-operation work; no new external storage or egress; do not spawn subagents.
