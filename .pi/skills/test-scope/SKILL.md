---
name: test-scope
description: Restrict test execution to files directly related to changed source paths during task cycles; run full suites only at Phase milestones.
---

# Test Scope Skill (`test-scope`)

## 1. 原則（無駄なテスト実行の禁止）

Locus 自律開発ハーネスでは、ワーカー（実装者・レビュアー）が 1 タスクのサイクルごとにフルテストスイートを実行することを **禁止** する。
常に **今回変更したファイルに対応する最小限の関連テストのみ** を実行し、高速なフィードバックとリソース節約を両立させること。

本スキルの対応付け規則は `.pi/extensions/harness/testscope.ts` (`relatedTests()`) の実装と完全に一致している。

---

## 2. 変更パス → 実行すべきテストの対応規則

作業ツリーで変更されたファイル（`git status --porcelain`）に対し、以下の規則で実行コマンドを決定する。

### 2.1 テスト不要（スキップ対象）
以下のパス・拡張子の変更のみである場合、**テストは一切実行しない**：
- `progress/` 配下のすべてのファイル
- `docs/` 配下のすべてのファイル
- `.pi/` 配下のすべてのファイル
- すべての `.md`（Markdown）ファイル

### 2.2 テストファイル自体を変更した場合
- **Python テスト (`tests/**/test_<stem>.py`)**:
  そのテストファイルのみを実行する（最初の失敗で停止する `-x` と簡潔出力 `-q` を付与）：
  ```bash
  python -m pytest tests/<path>/test_<stem>.py -x -q
  ```
- **フロントエンド テスト (`frontend/**/*.{test,spec}.{ts,tsx,js,jsx}`)**:
  そのテストファイルのみを Vitest で実行する：
  ```bash
  npm --prefix frontend test -- frontend/src/<path>/<Name>.test.tsx
  ```

### 2.3 プロダクトソースを変更した場合
- **Python ソース (`backend/**/<stem>.py` 等)**:
  `tests/` 配下（深さ4まで）から同名の `test_<stem>.py` を探し、ヒットしたテストファイルのみを実行する：
  ```bash
  python -m pytest tests/<matched_subpath>/test_<stem>.py -x -q
  ```
  - 例: `backend/app/scanner.py` を変更 → `tests/test_scanner.py`（または関連する `tests/test_api.py` 内の該当テスト関数 `-k <keyword>`）のみを実行する。
  - 注意: ローカル環境で `.venv313`（Python 3.13）が存在する場合は `.venv313/Scripts/python.exe -m pytest ...` を使用する。
- **フロントエンド ソース (`frontend/src/**/<Name>.{ts,tsx,js,jsx}`)**:
  同一ディレクトリ内の `<Name>.test.ts`, `<Name>.test.tsx`, `<Name>.spec.ts`, `<Name>.spec.tsx` を探し、ヒットしたファイルのみを実行する：
  ```bash
  npm --prefix frontend test -- frontend/src/<path>/<Name>.test.tsx
  ```

### 2.4 対応付けできない変更（`unmapped`）の扱い
- 対応する `test_<stem>.py` や `<Name>.test.tsx` が存在しないソース変更、または設定・インフラ定義ファイル等の変更は `unmapped` として扱う。
- 新規機能を実装した場合は、受入条件を検証する対応テストファイルを新規追加（TDD）し、そのファイルのみを実行する。
- 単体テストと1対1に対応しない横断的な変更ファイルは、タスク進捗ファイルの `## TEST` 欄の `Unmapped Changes` に明記し、Phase の節目でまとめて検証する。

---

## 3. フルスイートを実行してよい条件

リポジトリ全体のフルテストスイート（全 pytest スイート、全 Vitest スイート、Playwright E2E、`scripts/verify.py` 等）を実行してよいのは、以下の **Phase の節目のみ** である：

1. **Phase 完了ゲート（`phase/<slug>` → `main` マージ直前）**:
   - 当該 Phase のすべてのタスクが `status: done` となり、`phase/<slug>` ブランチを `main` へマージする前の最終統合検証。
2. **`unmapped` 変更の節目検証**:
   - オーケストレーター（`gpt-6-luna`）または人間が、複数の `unmapped` 変更を検証するために明示的に節目検証を指示した場合。

通常のタスク実装（`doing`）およびコードレビュー（`review`）では、いかなる場合もフルスイートを回してはならない。
