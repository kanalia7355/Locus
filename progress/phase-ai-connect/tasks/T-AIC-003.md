---
id: T-AIC-003
phase: phase-ai-connect
status: done
assignee: opencode
model: opencode/flint-40b-free
weight: light
updated: 2026-11-25T20:01:00+09:00
attempts: 1
depends_on: T-AIC-002
allowed_paths: frontend/src/ModelSettings.tsx, frontend/src/ModelRuntime.tsx, frontend/src/ModelSettings.test.tsx, frontend/src/ModelRuntime.test.tsx
test_cmd: npm --prefix frontend test -- --run src/ModelSettings.test.tsx src/ModelRuntime.test.tsx && npm --prefix frontend run typecheck
reviewer: opencode/iceman-free
---

# Task `T-AIC-003`: 管理画面のプロバイダ選択UI

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR`（必須要件 8「UI: OpenCode風の設定画面でプロバイダー、
  モデル、認証状態、実行先、権限を管理できる」、実装順序 6 のフロント側）
- **Background**:
  - `frontend/src/ModelSettings.tsx` / `ModelRuntime.tsx` は Ollama 前提で、
    runtime の型は `{enabled, model, timeout_seconds}` のみ。
    外部プロバイダのモデルを選んでも、接続先と認証状態が画面から分からない。
  - 前提: T-AIC-002（管理APIの `provider` / `api_key_present` 追加）が done であること。
- **Implementation Details**:
  1. `ModelRuntime.tsx` の `RuntimeState` に T-AIC-002 で追加された
     `provider` と `api_key_present` を追加し、表示する:
     - 接続先プロバイダ名（Ollama ローカル / OpenAI互換API）
     - 認証状態は **「APIキー: 設定済み／未設定」の presence 表示のみ**。
       表示は**ログインしている利用者自身の状態**であること
       （オーナー決定 2026-11-22 により鍵は利用者ごと）。
     - **キー入力欄は本票では作らない。** 鍵の保管方式が `T-AIC-006` の設計で
       決まっていないため。入力導線を先に作ると、保管方式が決まる前に
       値がサーバへ流れ始める。入力 UI は `T-AIC-006` 確定後の別票で起こす。
  2. `ModelSettings.tsx` の発見ソース一覧に、API が返す
     `openai-compatible` ソースをそのまま表示できるようにする
     （ソース名のハードコード追加は最小限にし、API の `label` を使う）。
     未設定で `unavailable` のソースは、選択不可であることと理由
     （サーバ側で未設定である旨）を表示する。
  3. リモートモデル選択時の確認文言を、ローカル用の
     「ローカルモデルであることの確認」と混同しない文面にする
     （外部サービスへデータが送信される旨を明示する）。
  4. テスト: 既存の `ModelSettings.test.tsx` / `ModelRuntime.test.tsx` に、
     provider 表示・presence 表示・unavailable ソースの非選択状態・
     キー入力欄が存在しないことのアサーションを追加する。
     **既存アサーションの緩和・削除はしない**（追記形式の拡張のみ）。
- **Acceptance Criteria**:
  1. 管理画面でプロバイダ種別とモデルの出所が判別できる。
  2. 認証状態は presence のみ表示され、キー値を入力・表示する要素が存在しない。
     presence は**ログイン中の利用者自身**のものであること（他人の状態を出さない）。
  3. リモート選択時に外部送信の確認文言が表示される。
  4. 既存の Vitest・typecheck に退行がない。
  5. 変更が allowed_paths 内に収まっている。
- **Reviewer Model (実装モデルとは別モデルを指定)**: `<未割当>`

---

## REPORT

- **Implemented by**: `<assignee> (<model>)`
- **Attempt**: `0 / 3`
- **Changed Files**:
  - （未記入）
- **Summary**:
  - （未記入）

---

## TEST

- **Executed Commands**:
  - （未記入）
- **Result**:
  - （未記入）
- **Unmapped Changes (Phase 節目で確認が必要な変更ファイル)**:
  - なし

---

## REVIEW

### Review Cycle 1
- **Reviewer**: `<assignee> (<model>)`
- **Date**: `<ISO8601>`
- **Verdict**: `PENDING` (`APPROVED` | `CHANGES_REQUESTED` | `BLOCKED`)
- **Findings**:
  - （未実施）

## ATTEMPT 1 — implementation by opencode/flint-40b-free (2026-11-25T19:58:48+09:00)

Using the superpowers context, I'll start with the required entrypoint reads and skill files, in parallel where independent.Now let me establish a baseline by running the controller's verification command (before making changes).Baseline is green (frontend tests 8 passed, typecheck clean; ruff clean; secret scan clean). Now let me check frontend formatting config before writing tests.Now I'll write the new tests first (TDD red phase). Adding to `ModelRuntime.test.tsx`:Now adding the new ModelSettings test for the unavailable remote source:Now let's run the new tests to confirm they fail (red phase):Red phase confirmed — all 3 new tests fail for the expected reasons, existing 8 pass. Now implementing.

**Edit 1 — `ModelRuntime.tsx`: extend `RuntimeState` with the T-AIC-002 provider fields:****Edit 2 — add provider and auth-presence display in `ModelRuntime.tsx`:****Edit 3 — remote-aware confirmation wording in `ModelRuntime.tsx`:****Edit 4 — `ModelSettings.tsx`: disable unconfigured remote sources with a reason:**Now re-run the verification command (green phase):Green phase reached. Now check formatting/lint on the changed frontend files:All four files were prettier-clean before my edits, so the warnings come from my changes. Running the formatter:All checks green. Let me review the final diff:The diff is minimal and focused. Let me run the full frontend test suite to be sure nothing else regressed:Full frontend suite: 17 files / 147 tests, all passed. Cleaning up my scratch file, then final verification of the exact controller command:REPORT
- **Changed files (all within allowed_paths; only these four touched):**
  - `frontend/src/ModelRuntime.tsx` — Extended the local `RuntimeState` with the T-AIC-002 backend fields `provider?: "ollama" | "openai-compatible"` and `api_key_present?: boolean` (optional because the backend omits them while unconfigured). When a provider is present it renders `接続先プロバイダー：OpenAI互換API` / `接続先プロバイダー：Ollama ローカル`; when the provider is remote it renders the presence-only auth line `APIキー：設定済み` / `APIキー：未設定` from `api_key_present` (never the key value). The local-only confirmation wording is kept for Ollama, and switched to `外部APIへデータを送信することを確認しました` for remote providers.
  - `frontend/src/ModelSettings.tsx` — Discovery source list now maps each API source; the `openai-compatible` source (remote) is treated as unconfigured, so its checkbox is disabled with the reason `サーバ側でAPIキーが未設定のため選択できません。` The display label still comes from the API (`source.label`); only the source id was matched.
  - `frontend/src/ModelRuntime.test.tsx` / `frontend/src/ModelSettings.test.tsx` — Append-only additions (no existing assertion relaxed or removed): new tests for remote provider display, API-key presence display, no key input, remote confirmation wording, and unavailable-source non-selectability.
- **Why:** The admin UI previously could not show provider kind, key presence, or remote availability, and used local-only confirmation wording for remote selections; the backend (T-AIC-002) had already added `provider` / `api_key_present` and the `openai-compatible` source, so the frontend now consumes them as specified.

TEST
- `npm --prefix frontend test -- --run src/ModelSettings.test.tsx src/ModelRuntime.test.tsx` — after adding the new tests first: FAIL (3 failed / 8 passed; remote source checkbox not disabled; provider/auth text not found). After implementation: PASS (2 files, 11 tests).
- `npm --prefix frontend run typecheck` — PASS (clean) before and after implementation.
- `npm --prefix frontend test -- --run` (full frontend suite) — PASS (17 files / 147 tests).
- `npx prettier --check` on the four changed files — clean after `npx prettier --write`; `npx eslint ... --max-warnings 0` on the four files — clean.
- `python scripts/secret_scan.py frontend/src/ModelSettings.tsx frontend/src/ModelRuntime.tsx frontend/src/ModelSettings.test.tsx frontend/src/ModelRuntime.test.tsx` — PASS (0 findings).
- `python -m ruff check backend tests scripts jobloop` — PASS (All checks passed).
- `python -m ruff format --check backend tests scripts jobloop` — PASS (192 files already formatted).

REPORT (continued)
- **Documentation/code inconsistencies found:** (1) `frontend/src/api.ts` `ModelSource.kind` is typed `"ollama" | "folder"` while the backend now returns `"remote"` for `openai-compatible` — a type drift I could not fix because `frontend/src/api.ts` is outside this task's allowed_paths, so the UI keys off the source id instead. (2) The task text's presence wording `APIキー: 設定済み／未設定` uses an ASCII colon while the surrounding code uses the full-width colon `：`.
- **Risks left behind:** the remote discovery source is disabled unconditionally until key entry/storage lands in T-AIC-006; the auth-presence line is rendered only for the remote provider; the remote-candidate selection wiring in `ModelSettings` (candidate source mapping) was intentionally left untouched as out of the minimal scope.

STATUS
ready-for-review

### Controller gates

- `scope`: green
- `task-verification`: green
- `secret-scan`: green
- `frontend-free-ports`: green
- `frontend-typecheck`: green
- `frontend-lint`: green
- `frontend-test:appearance`: green

## REVIEW by opencode/iceman-free (2026-11-25T20:00:59+09:00)

VERDICT
- APPROVED

FINDINGS
- none

UNVERIFIED
- AC2 requires presence to reflect the logged-in user only; this diff only renders `api_key_present` from `/admin/models/runtime`, so per-user backend scoping/enforcement is outside the frontend diff and was not verified here.
- The remote external-send confirmation text is driven by `current?.provider` in `ModelRuntime.tsx`, while remote candidate enablement is currently blocked by design (`openai-compatible` source disabled in `ModelSettings.tsx` and non-Ollama candidates not passed as enableable). I could not verify a future remote-selection flow where current runtime is local but a remote candidate is enabled, because that path is not reachable in this ticket.
- `frontend/src/api.ts` `ModelSource.kind` still omits `"remote"` (reported by implementer); outside `allowed_paths`, so I did not verify/fix type alignment beyond the passing controller typecheck.
