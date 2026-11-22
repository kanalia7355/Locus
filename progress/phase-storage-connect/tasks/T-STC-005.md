---
id: T-STC-005
phase: phase-storage-connect
status: todo
assignee: unassigned
model: -
weight: medium
updated: 2026-11-22T14:06:00+09:00
attempts: 0
depends_on: T-STC-002, T-STC-003, T-STC-004
allowed_paths: frontend/src/ConnectorSettings.tsx, frontend/src/ConnectorSettings.test.tsx, backend/app/service.py, backend/app/main.py, tests/test_connectors.py, tests/test_api.py
test_cmd: python -m pytest tests/test_connectors.py tests/test_api.py -q && npm --prefix frontend test -- --run src/ConnectorSettings.test.tsx && npm --prefix frontend run typecheck
---

# Task `T-STC-005`: 管理画面UI＋権限喪失時のアクセス拒否の統合検証

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR` 必須要件 8（UI）/ owner 決定 Q6（権限喪失時は即アクセス拒否）
- **Background**:
  - T-STC-001〜004 でバックエンドとコネクタが揃っても、管理者が設定・同期でき、
    かつ Q6 の「ソース側の権限を失ったら Locus 側でも即参照不可」が
    実際に効いていなければフェーズの完了条件を満たさない。
  - 前提: T-STC-002〜004 が done であること。
- **Implementation Details**:
  1. バックエンド（`backend/app/service.py` / `main.py`）:
     - `document_origins.revoked = 1` の文書を、読み取り・検索・引用の
       全経路で拒否する。実装箇所は既存の認可集約点（`_can_read()` と
       引用生成の到達可否判定）に寄せ、**経路ごとの個別対応で漏らさない**。
       既に生成済みの回答からの引用も、表示時に到達可否を再判定する
       既存仕様（live authorization）に乗せる。
     - 文書一覧のメタデータに `source`（コネクタ種別と source_label）を追加する。
       資格情報や外部サービスの内部 ID は出さない（external_id は出さない）。
     - 同期の実行は管理者の手動トリガーのみ（定期実行は本フェーズ外）。
  2. フロントエンド（新規 `frontend/src/ConnectorSettings.tsx`）:
     - コネクタ一覧：種別、資格情報の presence（設定済み／未設定）、
       最終同期の集計（登録／更新／スキップ／失敗の**件数のみ**）。
     - 同期操作：プロジェクトと source（ローカル=相対パス、Drive/Box=フォルダID）を
       指定して同期を実行し、結果の件数を表示する。
     - **資格情報を入力する欄は作らない**（環境変数で管理する設計のため）。
       未設定のコネクタは「サーバ側で未設定」と表示して同期不可にする。
     - 取り込んだ文書には出所（例: 「Box / 研究資料」）が表示される。
  3. 統合テスト:
     - `tests/test_connectors.py` に、フェイクコネクタで
       「同期 → 検索・引用できる → ソースから消える → 再同期 →
       読み取り・検索・引用の全てが拒否される」の往復を追加する。
     - 既存テストへの追記は**追記形式の拡張のみ**（既存アサーションの
       緩和・削除はしない）。
     - フロントは `ConnectorSettings.test.tsx` で presence 表示・
       件数のみ表示・資格情報入力欄が存在しないことを検証する。
- **Acceptance Criteria**:
  1. 管理画面から3コネクタの設定状態確認と手動同期ができる。
  2. 権限喪失／削除された文書が全経路で即座に参照できなくなる（Q6）。
  3. 画面・API に資格情報の値と external_id が現れない。
  4. 手動アップロードの既存挙動と既存テストに退行がない。
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

## ORCHESTRATOR — 配管を直した。設計は 1 行も変えていない (2026-11-22 15:10)

この票をループで走らせるために、frontmatter の配管だけ直した。
受入条件・実装方針・境界はオーナーの草案のままである。

- **`test_cmd` の `.venv313/Scripts/python.exe` を素の `python` にした。**
  `.venv313` は `.gitignore:31`（`.venv*/`）で無視されるので**ジョブごとの
  クローンには存在しない**（実測: `workspaces/T-PH6-104/.venv313` は無い）。
  コントローラは**先頭が素の `python` のときだけ**自分のインタプリタに束縛する
  （`jobloop/gates.py` の `INTERPRETER`）。直さなければ検証が毎回失敗し、
  5 票 15 試行が 1 件もマージできずに終わっていた。
  **ジョブ文にインタプリタのパスを書かないこと**自体も封じ込めの要件である
  （2026-11-16 に `T-PH6-103` がこれでメインチェックアウトを編集した）。
- **`model:` を `-` にした**（他フェーズと同じ表記）。
- **`depends_on` を frontmatter に入れた。** 本文とフェーズ表には依存が書いてあったが、
  コントローラが見るのは frontmatter だけである。入れないと土台より先に派遣される。
