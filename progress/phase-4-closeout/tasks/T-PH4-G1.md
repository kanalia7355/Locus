---
id: T-PH4-G1
phase: phase-4-closeout
status: todo
assignee: deepai
model: deepai/gemini-4-hydrogen
weight: heavy
updated: 2026-11-14T17:35:00+09:00
attempts: 0
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

- Implemented by:
- Changed Files:
- Summary:

## TEST

- Commands run:
- Results:

## REVIEW

- Reviewer:
- Findings:
