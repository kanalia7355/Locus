---
id: T-PH4-G1
phase: phase-4-closeout
status: done
assignee: deepai
model: deepai/gemini-4-hydrogen
weight: heavy
updated: 2026-11-14T18:12:00+09:00
qa_verdict: PASS
reviewer: deepai/glm-5.3-flash
attempts: 1
allowed_paths: frontend/e2e/workspace.spec.ts, frontend/e2e/, frontend/src/App.tsx, frontend/src/App.test.tsx, tests/e2e_server.py, frontend/src/
test_cmd: npm --prefix frontend test -- --run && npm --prefix frontend run test:e2e
---

# Task `T-PH4-G1`: Prototype quality E2E timeout 修復（統合ゲート解消）

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: Phase 2/4 統合ゲート（GitHub Actions `Prototype quality` green 化）
- **Evidence** (2026-11-14, run `43574525392`, `loop/local-development` HEAD `f1fa421`):
  - Prototype quality: **FAIL** — verify job の `browser-e2e` 工程
  - 12/13 Playwright テストは成功。失敗は 1 件のみ:
    `[chromium] › e2e/workspace.spec.ts:29:1 › first login, source retrieval, history and logout use actual API`
  - 詳細: `Test timeout of 30000ms exceeded` — `workspace.spec.ts:87`
    `await page.getByRole("button", { name: /調査 ·/ }).click()` が 30 秒間見つからずタイムアウト。
    直前の行 86 `page.getByRole("button", { name: "調査履歴", exact: true }).click()` は通過している。
  - 1 個前のコミット (`2780cde` 時点の run `43573050478`) も同一テストで失敗 → 2 連続で赤。
- **Background**:
  - 直近の機能差分は `T-PH2-001` (frontend/src/App.tsx の文言・Delegations UI) と
    `T-PH2-005` (loop_engine のみ)。App.tsx の文言変更でロケータが壊れた可能性と、
    単なるロード遅延フレークの可能性の両方がある。
- **Implementation Details**:
  1. ローカルで再現する: `npm --prefix frontend run test:e2e`。3 回実行し、
     毎回失敗するか（回帰）たまにしか失敗しないか（フレーク）を判定する。
  2. **回帰の場合**: App.tsx / workspace.spec.ts のどちらが正かを実装意図
     (`progress/phase-2-authz/tasks/T-PH2-001.md` の受入条件) と照合して特定し、
     正しい側のみ最小修正する。テストの期待値を安易に実装側へ合わせない。
  3. **フレークの場合**: テストを弱体化せずに安定化する（例: 特定要素の可視化を
     `expect(...).toBeVisible({ timeout: ... })` で明示的に待つ、`(async () => ...)` の
     応答完了を待ってから次ステップへ進む）。セレクタの緩和 (`*:has-text` 等) や
     タイムアウト値の引き上げだけでの潰しは不可。
  4. 変更は `frontend/e2e/` と（回帰修正時のみ）`frontend/src/App.tsx` 周辺に留める。
     他タスクが App.tsx を改修するため、本タスクでの App.tsx 変更は**ロケータ復旧に必要な最小限**。
  5. 完了条件の検証コマンド: `npm --prefix frontend test -- --run` と
     `npm --prefix frontend run test:e2e`（両方 green）。
- **Acceptance Criteria**:
  1. `workspace.spec.ts:29` のテストがローカルで 3 連続成功する。
  2. 全 13 E2E + 全 Vitest が green。
  3. 変更が許可パス内の最小修正で、既存テストの削除・緩和がない。
  4. 原因区分（回帰/フレーク）と証跡（各回の結果）が REPORT に記録されている。

## REPORT

- Implemented by: deepai/gemini-4-hydrogen
- Changed Files:
  - `frontend/e2e/workspace.spec.ts`
  - `progress/phase-4-closeout/tasks/T-PH4-G1.md`
- Summary:
  - **原因区分**: **回帰（100% 再現）** — フレークではない。
  - **再現結果（修正前）**: `npm --prefix frontend run test:e2e` を 3 回単独実行し、3/3 回とも `workspace.spec.ts:87`（`getByRole("button", { name: /調査 ·/ })`）で 30s タイムアウト失敗（12/13 pass, 1/13 fail）。※並列起動した 1 回は port 8000 競合のため除外し、独立 3 回で確認。
  - **原因特定**: コミット `89e71c4`（`feat(app): show conversation preview in history list`）で `frontend/src/App.tsx` の調査履歴ボタン表記が `調査 · <日時>` から `{conv.preview?.trim() || "調査"} <日時>` に変更された。同コミットで `frontend/src/ProjectContext.test.tsx` は更新されたが、`frontend/e2e/workspace.spec.ts:87` のロケータが旧表記 `/調査 ·/` のまま残存していた。
  - **修復方針と変更内容**: `App.tsx` のプレビュー表示が意図された仕様であるため、`frontend/e2e/workspace.spec.ts:87` のロケータを当該会話で送信した質問プレビューと日時形式に一致する `/^成膜条件を比較 \d{4}\//` へ最小修正した（`App.tsx` 変更なし、既存テストの削除・緩和なし）。

## TEST

- Commands run:
  - 修正前再現 1回目: `npm --prefix frontend run test:e2e` → **FAIL** (12 passed, 1 failed: `workspace.spec.ts:87` 30000ms timeout waiting for `getByRole('button', { name: /調査 ·/ })`)
  - 修正前再現 2回目: `npm --prefix frontend run test:e2e` → **FAIL** (12 passed, 1 failed: `workspace.spec.ts:87` 30000ms timeout)
  - 修正前再現 3回目: `npm --prefix frontend run test:e2e` → **FAIL** (12 passed, 1 failed: `workspace.spec.ts:87` 30000ms timeout)
  - 修正後 1回目: `npm --prefix frontend run test:e2e` → **PASS** (13 passed in 33.9s; `workspace.spec.ts:29` 1.6s)
  - 修正後 2回目: `npm --prefix frontend run test:e2e` → **PASS** (13 passed in 33.8s; `workspace.spec.ts:29` 1.6s)
  - 修正後 3回目: `npm --prefix frontend run test:e2e` → **PASS** (13 passed in 34.6s; `workspace.spec.ts:29` 1.8s)
  - Vitest: `npm --prefix frontend test -- --run` → **PASS** (Test Files: 15 passed, Tests: 79 passed)
  - Lint: `npm --prefix frontend run lint` → **PASS** (`eslint . --max-warnings 0`)
  - Typecheck: `npm --prefix frontend run typecheck` → **PASS** (`tsc -b`)
- Results:
  - 全 13 E2E テストが 3 連続成功（3/3 PASS）、全 79 Vitest・lint・typecheck すべて PASS。

## REVIEW

- Reviewer: deepai/glm-5.3-flash (独立レビュー round 1, 実装モデル gemini-4-hydrogen と異なる)
- Findings: **APPROVED**
  - 検証: (1) `git show 89e71c4 -- frontend/src/App.tsx` で表記変更を確認 — 旧ロケータ `/調査 ·/` は現行 UI に全くマッチせず、回帰主張は正しい。(2) worktree 内で `npm --prefix frontend run test:e2e` → 13 passed (32.2s)。(3) 差分は workspace.spec.ts ロケータ 1 行 + 進捗ファイルのみ、待機アサーションの削除・緩和なし。(4) `grep -rn "調査 ·" frontend/ tests/` → 0 件。(5) REPORT/TEST 記録と実行結果が整合。
  - 新ロケータ `/^成膜条件を比較 \d{4}\//` の固定依存性は問題なし（質問文字列は同テスト内で送信した値・preview 空経路は存在しない・旧ロケータと同等以上の specificity）。
  - 指摘 low 1件（修正不要・参考記録）: テストの質問文を将来 80 文字超にすると preview truncation (`…`) でロケータが破綻し得る。現行 7 文字では影響なし。
