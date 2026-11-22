---
id: T-AIC-003
phase: phase-ai-connect
status: todo
assignee: unassigned
model: unassigned
weight: light
updated: 2026-11-22T13:56:00+09:00
attempts: 0
depends_on: T-AIC-002
allowed_paths: frontend/src/ModelSettings.tsx, frontend/src/ModelRuntime.tsx, frontend/src/ModelSettings.test.tsx, frontend/src/ModelRuntime.test.tsx
test_cmd: npm --prefix frontend test -- --run src/ModelSettings.test.tsx src/ModelRuntime.test.tsx && npm --prefix frontend run typecheck
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
       **キー入力欄は作らない**（キーはサーバ環境変数で管理する設計のため。
       画面から値を送る導線を作ることは本フェーズの境界 §3-2 違反）。
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
