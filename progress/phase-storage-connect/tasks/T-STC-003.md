---
id: T-STC-003
phase: phase-storage-connect
status: todo
assignee: unassigned
model: -
weight: medium
updated: 2026-11-22T14:06:00+09:00
attempts: 0
depends_on: T-STC-001
allowed_paths: backend/app/connector_gdrive.py, tests/test_connector_gdrive.py, backend/requirements.lock
test_cmd: python -m pytest tests/test_connector_gdrive.py tests/test_connectors.py -q
---

# Task `T-STC-003`: Google Drive コネクタ（サービスアカウント／読み取り専用）

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR` / owner 決定（2026-11-22、接続対象その2）
- **Background**:
  - Google Drive API は v3 が現行。公式 Python クライアント
    （`google-api-python-client`）があるが、Locus は依存ロックが厳しく
    既存コードが全て httpx のため、**REST API を httpx で直接呼ぶ**方針とする
    SDK 導入が必要と判断した場合は、**自分で入れずに REPORT に理由を記録して停止し、
    オーケストレーターの裁定を仰ぐこと**。`pyproject.toml` は保護パスであり
    **ジョブからは書けない**（`jobloop/gates.py` の `PROTECTED`）。
    `backend/requirements.lock` は allowed_paths にあるが、
    **裁定が出るまでは触らない**（ロックだけ動かすと環境と食い違う）。
  - 認証はサービスアカウント方式：対象フォルダをサービスアカウントの
    メールアドレスに共有する運用。スコープは
    `https://www.googleapis.com/auth/drive.readonly` のみ。
    JWT 署名には既存依存 `cryptography` を使う。
  - 前提: T-STC-001（共通基盤）が done であること。
  - **owner 側の前提手続き**（コード外）: Google Cloud プロジェクトで
    Drive API を有効化し、サービスアカウントと JSON キーを発行、
    対象フォルダをそのアカウントに共有する。キーが用意されるまで
    実環境での疎通確認はできない（テストはモックで完結させる）。
- **Implementation Details**:
  1. 新規 `backend/app/connector_gdrive.py` に `GoogleDriveConnector` を実装。
  2. 資格情報: JSON キーの**ファイルパス**を環境変数
     `LOCUS_GDRIVE_SERVICE_ACCOUNT_FILE` で受ける。キー内容はメモリ上でのみ使い、
     ログ・例外・`status` 相当に一切出さない。未設定なら unavailable。
     アクセストークンは `POST https://oauth2.googleapis.com/token`
     （JWT bearer フロー）で取得し、有効期限内はメモリに保持する。
  3. 列挙: `GET https://www.googleapis.com/drive/v3/files` に
     `q='<folder_id>' in parents and trashed=false`、
     `fields=files(id,name,mimeType,md5Checksum,headRevisionId,size,modifiedTime),nextPageToken`。
     同期リクエストの `source` はフォルダ ID。
     差分は T-STC-001 の revision 照合（`headRevisionId`）で行い、
     Changes API の page token 方式は本タスクでは採用しない（将来の最適化）。
  4. 取得: 通常ファイルは `files/{id}?alt=media`。
     **Google Docs 形式**（`application/vnd.google-apps.document` 等）は
     `files/{id}/export?mimeType=text/plain` でテキスト化できた場合のみ対象とし、
     取り込み名は `.txt` に正規化する。スプレッドシートは `text/csv` export を試みる。
     それ以外の Google ネイティブ形式・バイナリ形式はスキップ（理由コード記録）。
  5. エラー処理: 401 はトークンを1回だけ再取得して再試行、それ以外は
     同期全体を失敗として報告し**自動再送しない**。403（権限喪失）は
     T-STC-001 の revoked 判定に委ねるため、列挙が 403 の場合は
     「ソース到達不可」として同期を中断し、既存 origin を revoked に倒す。
  6. テスト `tests/test_connector_gdrive.py` は `httpx.MockTransport` のみ:
     - JWT 生成とトークン取得（テスト用ダミー鍵で署名形式を検証）
     - ページングを含む列挙、Docs export の分岐、対象外形式のスキップ
     - 401 の単回再取得、403 での中断
     - キー内容が例外・戻り値に含まれないこと
- **Acceptance Criteria**:
  1. モック上で Drive フォルダから文書が取り込め、版管理が revision で効く。
  2. 読み取り専用スコープ以外を要求していない（コード上で確認できる）。
  3. サービスアカウントのキー内容がどこにも露出しない。
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
- **`allowed_paths` から `pyproject.toml` を外した。** これは
  `jobloop/gates.py` の `PROTECTED` に入っており、**票に何と書いてあっても
  ジョブからは書けない**（書けば scope ゲートが即停止する）。
  オーナーの意図（SDK が必要になったときの逃げ道）は残してあるが、
  **経路を「裁定を仰ぐ」に書き換えた**。書けない場所を許可と書いた票は、
  phase-8 で 3 件のジョブを保護パスへ書かせて失わせている。
  `backend/requirements.lock` は保護対象でないのでそのまま残した。
