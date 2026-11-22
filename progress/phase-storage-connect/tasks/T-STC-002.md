---
id: T-STC-002
phase: phase-storage-connect
status: todo
assignee: unassigned
model: -
weight: medium
updated: 2026-11-22T14:06:00+09:00
attempts: 0
depends_on: T-STC-001
allowed_paths: backend/app/connector_local.py, tests/test_connector_local.py
test_cmd: python -m pytest tests/test_connector_local.py tests/test_connectors.py -q
---

# Task `T-STC-002`: ローカルフォルダ（エクスプローラー）コネクタ

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR` / owner 決定（2026-11-22、接続対象その1）
- **Background**:
  - 「エクスプローラー」= Locus が稼働するマシン上のローカルフォルダ。
    研究室の共有フォルダや個人PCの作業フォルダを、エクスプローラーで
    そのまま管理しながら Locus に取り込む用途。
  - ローカルパスの安全検査は `backend/app/model_catalog.py` に既存部品がある
    （`reparse()`、`local_volume()`、`checked_directories()`）。再実装しない。
  - 前提: T-STC-001（共通基盤）が done であること。
- **Implementation Details**:
  1. 新規 `backend/app/connector_local.py` に `LocalFolderConnector` を実装する。
     T-STC-001 の protocol（`list_items` / `fetch_content`）に従う。
  2. 対象ルートの決定:
     - ルートパスは環境変数 `LOCUS_LOCAL_SOURCE_ROOT` で管理者が指定した
       **単一の親フォルダ配下のみ**。同期リクエストの `source` はその配下の
       相対パスだけを受け付け、絶対パス・`..` を含むパスは拒否する。
     - 環境変数が未設定ならコネクタは unavailable（presence 表示は false）。
  3. 列挙:
     - 再帰列挙は深さ上限（例: 8）と件数上限（例: 1,000）を設ける。
     - **シンボリックリンク／ジャンクション／リパースポイントを辿らない**
       （`model_catalog.reparse()` 等の既存検査を再利用し、ルート外への
       逸脱を検出したらその枝を打ち切って理由コードを記録）。
     - `external_id` はルート相対パス、`revision` は `mtime + size`、
       `content_hash` は SHA-256。本文の読み取りは列挙時には行わない
       （hash は同期エンジンが取得時に計算する。列挙はメタデータのみ）。
  4. 取得: `fetch_content` は解決後の実パスがルート配下であることを
     再検証してから読み取る（列挙と取得の間の差し替え対策）。
     読み取り専用で開き、書き込みは一切しない。
  5. テスト `tests/test_connector_local.py` は `tmp_path` 配下のみを使う:
     - 通常の列挙／取得、相対パス逸脱（`..`、絶対パス）の拒否
     - リンクを辿らないこと（プラットフォームで作成可能な場合のみ。
       Windows の symlink 権限による skip は既存テストの慣例に従う）
     - ルート未設定時の unavailable
     - 形式外ファイルが列挙には出るが同期ではスキップされることは
       T-STC-001 のテストに委ね、ここでは列挙の正確さに絞る
- **Acceptance Criteria**:
  1. 指定ルート配下の文書が共通基盤経由で取り込める。
  2. ルート外のファイルには、パスの細工・リンク経由のいずれでも到達できない。
  3. ソースフォルダ側のファイルが変更・削除されていない（読み取り専用）。
  4. 変更が allowed_paths 内に収まっている。
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
