# Codex Handoff — Locus development continuation (2026-11-12)

## Purpose
Enable Codex to resume overall audit/development stewardship after OpenCode-first implementation work, with clear visibility into environment, completed work, verification, unmerged commits, blockers, and next executable tasks.

**Final goal remains full Locus application completion.** Phase completion is not the final goal; no main integration/version bump is claimed here.

## Environment (verified)
- Host: Windows, repo `C:\Users\hirot\Locus`, branch `loop/local-development`
- Python interpreters: 3.13 (default) and 3.10 via `py -0p`
- Project: `locus-loop-engine 0.4.0`, `requires-python >=3.11` (`pyproject.toml`)
- Verification venv (independent, **`.venv` preserved**): `.venv313` (Python 3.13.2)
  - Setup: `python -m pip install --upgrade pip`; `pip install -r backend/requirements.lock`; `pip install -e ".[dev]"`
- CI reference: `.github/workflows/quality.yml` (Python 3.13, backend lint/type/unit+integration/build; frontend Node 22 lint/type/test/build)
- Frontend: `frontend/package.json` (`locus-research-ui 0.4.0`)

## Python 3.13 regression evidence
- **Baseline (before this round's core feature edits):** `.\.venv313\Scripts\python.exe -m pytest -q tests\unit tests\integration` → **990 passed, 7 skipped in 478.54s (0:07:58)**.
  - Skips: `tests/unit/test_loop_policy_migration.py:237` (Windows synthetic symlink permission), `tests/integration/test_live_docker_boundary.py` 6 tests (real Docker containment opt-in).
  - Classification: environment none / existing issues none / regressions none in `.venv313`.
  - Evidence: `.loop/runtime/evidence/py313-env-and-document-search-2026-11-11.json`, `.loop/runtime/evidence/py313-regression.out`.
- **Post-feature full regression (after commits below):** `pytest -q tests/unit tests/integration` in `.venv313` executed again; capture: `.loop/runtime/evidence/py313-regression-post-features.out` / `.err`. **Check this file for the final summary** (started during this session; may still be running when handoff was written).
- **Prior `.venv` (Python 3.10.6):** collection 30 errors due to env mismatch (`tomllib`/`datetime.UTC` unavailable, binary deps) — classified as environment incompatibility, not product regression.

## Completed in this continuation (OpenCode-first, local commits on loop/local-development)

### Adapter/foundation commits (previous continuation, retained)
- `8ba2a1825416a1ba0d6b6113972e69ddee77c005` `feat(loop-engine): add OpenCode CLI runner adapter with synthetic tests`
- `5d48e17deb69080eed25f37ba61db8abadccfd99` `feat(loop-engine): integrate OpenCode runner config and execution evidence`
- `2e0392721bf458e85bed3209fb73de13f82421fd` `feat(loop-engine): add bounded OpenCode free-model fallback routing`
- `ed7a74fd9dc5f3536a2cec9842cb6f3ec579e5c3` `feat(loop-engine): wire OpenCode fallback model configuration`
- Targeted verification recorded earlier: **15 passed** for OpenCode runner/config/fallback/integration tests; limited single-shot synthetic live CLI check completed under approved constraints (evidence: `.loop/runtime/evidence/opencode-adapter-foundation-2026-11-11.json`).

### Locus core user-facing features (this continuation)
1. **Document library search by name** — `d55f3c06c6bc3549e9e898c88ae3bd5942fe30a1` `feat(app): add project document library search by name`
   - Changed: `backend/app/main.py`, `backend/app/service.py`, `frontend/src/App.tsx`, `tests/test_api.py`
   - Behavior: `GET /api/documents` accepts optional `q` (case-insensitive name substring) while preserving existing visibility/authorization; shared/personal/ingestion views include search input and client-side filtering.
   - TDD: failing `test_document_list_search_filters_by_name` added before implementation.
   - Tests added: `test_document_list_search_filters_by_name`, `test_document_list_search_respects_visibility`.
   - Verification: `pytest -q tests/test_api.py` **17 passed** (post-implementation); frontend `tsc -b` **pass**.
   - Independent read-only review: initial coverage gap addressed (visibility test added); non-blocking note: UI filters client-side, backend `q` implemented/tested.

2. **Conversation history preview** — `89e71c473a49a2d036dd527ba0d67ac8820d7878` `feat(app): show conversation preview in history list`
   - Changed: `backend/app/service.py`, `frontend/src/App.tsx`, `frontend/src/ProjectContext.test.tsx`, `frontend/src/api.ts`, `tests/test_api.py`
   - Behavior: conversation list includes owner/project-scoped `preview` (first message snippet, normalized/truncated); history UI shows preview with date (fallback "調査" for empty); frontend typing/defaults made compatible for list/detail responses.
   - TDD: failing `test_conversation_list_includes_preview` added before implementation.
   - Verification: `pytest -q tests/test_api.py` **18 passed**; frontend `npm run lint` **pass**, `tsc -b` **pass**, `npm test` (vitest) **15 files / 74 tests passed**, `npm run build` **pass**.
   - Independent read-only review: **pass** (no blocking issues).

Evidence: `.loop/runtime/evidence/py313-env-and-document-search-2026-11-11.json`, `.loop/runtime/evidence/locus-core-continuation-2026-11-12.json`, `.loop/runtime/evidence/opencode-adapter-foundation-2026-11-11.json`.

## Git / integration state
- Branch: `loop/local-development`, ahead of `main` by local commits (see `git log --oneline main..HEAD`); includes adapter and core feature commits above plus prior branch history.
- **Not merged to `main`**; no version bump performed.
- Untracked (left untouched): `.agents/skills/opencode-free-worker/`, `docs/plans/FREE_FIRST_GOAL_LOOP_DIRECTIVE_2026-11-11.md`

## Pending approvals / blocked / safety-held items
- **Controller-via-live-OpenCode bounded E2E:** blocked/recorded — cannot technically guarantee external send scope limited to synthetic prompt/code when task/workspace context is involved under limited approval.
- **Runner activation / external communications / credentials / `--auto` / paid usage:** not authorized beyond previously recorded limited single-shot synthetic CLI check.
- **Phase acceptance for final audit/main integration/version update:** not claimed satisfied; follow existing ADRs/gates/review limits.

## Suggested next executable P0/user-facing tasks (verify against current specs/impl before coding)
1. Conversation history search/filter (by preview/text/date) in history view/API if absent.
2. Citation/source UX improvements in chat (clearer source/page/position navigation) consistent with existing citation data.
3. Document management UX/API gaps (status clarity, owner actions, metadata visibility) aligned with permissions.
4. Permission/role management UI clarity improvements where behavior exists but operator UX is unclear.
5. Per feature: TDD → implementation → feature/regression tests (`.venv313` pytest, frontend lint/typecheck/test/build as applicable) → independent read-only review → fixes → commit → evidence/handoff update.

## Handoff checklist for Codex
- [ ] Read `.loop/runtime/evidence/py313-regression-post-features.out` for final post-feature regression summary and classify any failures.
- [ ] Review commits `d55f3c0`, `89e71c4` (and adapter commits if relevant) for integration readiness vs phase gates.
- [ ] Confirm no unapproved external comms/credentials/activation occurred.
- [ ] Continue implementation; update this handoff and evidence after each completed task.
