---
id: T-STC-001
phase: phase-storage-connect
status: todo
assignee: unassigned
model: unassigned
weight: medium
updated: 2026-11-22T14:06:00+09:00
attempts: 0
allowed_paths: backend/app/connectors.py, backend/app/service.py, backend/app/main.py, tests/test_connectors.py
test_cmd: .venv313/Scripts/python.exe -m pytest tests/test_connectors.py tests/test_api.py -q
---

# Task `T-STC-001`: コネクタ共通基盤（IF／出所テーブル／同期エンジン／管理API）

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR` / owner 決定 Q5 の部分的解禁（2026-11-22、対象は
  ローカルフォルダ／Google Drive／Box の3種のみ）、Q6（権限喪失時は即アクセス拒否）
- **Background**:
  - 取り込みは手動アップロードのみで、外部ストレージからの取り込み口がない。
  - `documents` テーブルに出所を表す列がないため、コネクタ由来の文書の
    追跡・差分同期・権限喪失時の拒否ができない。
  - 本タスクは3コネクタ共通の土台だけを作る。個別コネクタは T-STC-002〜004。
- **Implementation Details**:
  1. 先に `backend/app/service.py` の `upload()`、`documents` テーブル定義、
     `_can_read()` と監査 `_audit()` を読む。
  2. 新規 `backend/app/connectors.py`:
     - `SourceItem`（`external_id, name, revision, content_hash, size, modified_at`）と
       コネクタ protocol（`list_items(cursor)`, `fetch_content(external_id) -> bytes`）を定義。
     - `SyncEngine.sync(actor, project, connector, source_label)`:
       列挙 → 形式フィルタ（`.txt/.md/.csv`、UTF-8 デコード可能、256 KiB 以内。
       `Service.upload()` の検証条件と同一に保つ）→
       `document_origins` と照合し、未登録／revision 変化のみ取得 →
       `Service.upload(actor, project, name, content, kind="personal")` で登録 →
       origin を記録。失敗・スキップは件数と理由コードのみ集計して返す（内容は残さない）。
       **自動再送はしない**（失敗は次回同期で再判定）。
     - 同期時に列挙結果から消えていた origin は `revoked` として印を付け、
       対応文書の読み取り可否に使う（実際の拒否の組み込みは T-STC-005 と共同。
       本タスクでは origin 側の状態管理と、その状態を読むための
       service 側フックの置き場まで）。
  3. `backend/app/service.py` のスキーマ追加（既存パターンに従い
     `CREATE TABLE IF NOT EXISTS` ＋ 必要な列追加は既存の migration 方式で）:
     - `document_origins (document_id TEXT PRIMARY KEY, connector_id TEXT NOT NULL,
       external_id TEXT NOT NULL, external_revision TEXT NOT NULL DEFAULT '',
       content_hash TEXT NOT NULL DEFAULT '', source_label TEXT NOT NULL DEFAULT '',
       synced_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
       UNIQUE(connector_id, external_id))`
     - `documents` 本体の列は変更しない。
  4. 管理API（`backend/app/main.py`、system_admin のみ、既存の models 管理APIと同型）:
     - `GET /api/admin/connectors` — 接続可能なコネクタ種別と、
       資格情報の **presence**（設定済みか否か）の一覧。値は返さない。
     - `POST /api/admin/connectors/{connector_id}/sync` —
       body は `{project_id, source}`（source の意味はコネクタごとに定義。
       本タスクではテスト用フェイクコネクタで往復させる）。
       監査 `connector.sync` を記録し、集計（登録／更新／スキップ／失敗の件数）を返す。
  5. テスト `tests/test_connectors.py`: フェイクコネクタ（メモリ内）で
     - 初回同期で文書が登録され origin が付く
     - 再同期で重複登録されない、revision 変化で新文書になる
     - 形式外・上限超過がスキップされ内容が残らない
     - 列挙から消えた項目が `revoked` になる
     - 非管理者が管理APIを使えない
     を検証する。**実ネットワーク・実ファイルシステムへは出ない。**
- **Acceptance Criteria**:
  1. フェイクコネクタで同期の往復（登録／差分／取消）がテストで検証されている。
  2. コネクタ経由の文書もスキャン・ACL・上限を手動アップロードと同様に受ける。
  3. 資格情報に相当する値が API 応答・監査に含まれない。
  4. 既存の `tests/test_api.py` 等に退行がない。
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
