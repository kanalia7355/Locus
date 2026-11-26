---
id: T-STC-004
phase: phase-storage-connect
status: done
assignee: agy
model: agy/gemini-4-carbon-low
weight: medium
updated: 2026-11-26T12:38:40+09:00
attempts: 1
depends_on: T-STC-001
allowed_paths: backend/app/connector_box.py, tests/test_connector_box.py, backend/requirements.lock
test_cmd: python -m pytest tests/test_connector_box.py tests/test_connectors.py -q
reviewer: agy/gemini-4-argon-low
---

# Task `T-STC-004`: Box コネクタ（CCG／読み取り専用）

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR` / owner 決定（2026-11-22、接続対象その3）
- **Background**:
  - Box には公式 Python SDK（現行 `boxsdk>=10`、`box_sdk_gen`）があるが、
    T-STC-003 と同じ理由（依存ロック、既存コードは httpx 統一）で
    **REST API を httpx で直接呼ぶ**方針とする。SDK が必要と判断した場合は
    **自分で入れずに REPORT に理由を記録して停止し、裁定を仰ぐこと**。
    `pyproject.toml` は保護パスで**ジョブからは書けない**
    （`jobloop/gates.py` の `PROTECTED`）。`backend/requirements.lock` は
    allowed_paths にあるが、**裁定が出るまでは触らない**。
  - 認証は CCG（Client Credentials Grant）: サーバが無人でトークンを取得する方式。
    トークンは60分有効で refresh token はないため、期限切れの都度再取得する。
    対象フォルダはサービスアカウントに共有（コラボレーション）する運用。
  - 前提: T-STC-001（共通基盤）が done であること。
  - **owner 側の前提手続き**（コード外）: Box Developer Console で
    Server アプリ（CCG）を作成し、Box 管理者の承認を得ること。
    承認が終わるまで実環境での疎通確認はできない（テストはモックで完結させる）。
- **Implementation Details**:
  1. 新規 `backend/app/connector_box.py` に `BoxConnector` を実装。
  2. 資格情報: 環境変数 `LOCUS_BOX_CLIENT_ID` / `LOCUS_BOX_CLIENT_SECRET` /
     `LOCUS_BOX_ENTERPRISE_ID`。値はログ・例外・状態表示に出さない。
     未設定なら unavailable。
     トークンは `POST https://api.box.com/oauth2/token`
     （`grant_type=client_credentials`、`box_subject_type=enterprise`）で取得し、
     有効期限内はメモリ保持、切れたら再取得する。
  3. 列挙: `GET https://api.box.com/2.0/folders/{folder_id}/items`
     （`fields=id,type,name,sha1,size,modified_at,file_version`、`limit/offset` ページング）。
     同期リクエストの `source` はフォルダ ID（ルートは `0`）。
     再帰は深さ上限（例: 8）と件数上限（例: 1,000）を設ける。
     `external_id` はファイル ID、`revision` は `file_version.id`（なければ `sha1`）、
     `content_hash` は Box が返す `sha1` をそのまま使う。
  4. 取得: `GET https://api.box.com/2.0/files/{file_id}/content`
     （302 リダイレクト先のダウンロードURLへ追従する。この経路に限り
     httpx の `follow_redirects` を有効化し、追従先が Box の
     ダウンロード用ホストであることを確認する）。
  5. エラー処理: 401 はトークンを1回だけ再取得して再試行。
     404／403 は権限喪失として扱い、列挙自体が失敗した場合は
     T-STC-003 と同様に同期を中断し既存 origin を revoked に倒す。
     それ以外の失敗は自動再送しない。
  6. テスト `tests/test_connector_box.py` は `httpx.MockTransport` のみ:
     - トークン取得（CCG）と期限切れ時の再取得
     - ページングと再帰を含む列挙、sha1 による差分判定
     - ダウンロードのリダイレクト追従と、想定外ホストへの追従拒否
     - client secret が例外・戻り値に含まれないこと
- **Acceptance Criteria**:
  1. モック上で Box フォルダから文書が取り込め、版管理が効く。
  2. 読み取り以外の操作（アップロード、削除、共有変更）を一切行わない。
  3. client secret がどこにも露出しない。
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

## ATTEMPT 1 — implementation by agy/gemini-4-carbon-low (2026-11-26T12:37:21+09:00)

Verification checks are running; waiting for completion.
Verification command is completing; waiting for final task notification.
Final verification checks are running; waiting for completion.
REPORT
- Changed files and reasons:
  - [connector_box.py](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-STC-004/backend/app/connector_box.py) (new): Implements read-only `BoxConnector` against the T-STC-001 `list_items` / `fetch_content` sync contract directly over `httpx` (leaving `backend/requirements.lock` untouched). Reads `LOCUS_BOX_CLIENT_ID`, `LOCUS_BOX_CLIENT_SECRET`, and `LOCUS_BOX_ENTERPRISE_ID` into closure-backed storage so credential values and cached bearer tokens do not appear in `vars(connector)`, `repr(connector)`, `self.rejections`, exceptions, or sync results; raises `BoxUnavailable` when unconfigured. Acquires access tokens via `POST https://api.box.com/oauth2/token` (`grant_type=client_credentials`, `box_subject_type=enterprise`, `box_subject_id`), caches them in memory until expiry (with a 60s skew), and re-acquires on expiry. Enumerates `GET https://api.box.com/2.0/folders/{folder_id}/items` with `fields=id,type,name,sha1,size,modified_at,file_version` and `limit`/`offset` pagination, walking nested folders up to `MAX_DEPTH = 8` and `MAX_ITEMS = 1000` (with cycle tracking), setting `external_id` to file ID, `revision` to `file_version.id` (falling back to `sha1`), and `content_hash` to `sha1`. Downloads content via `GET https://api.box.com/2.0/files/{file_id}/content`: the main API client keeps `follow_redirects=False`, and only when `/content` returns a redirect does a dedicated download client follow redirects (without forwarding `Authorization`) after verifying on every hop via `event_hooks` that the target is `https://` on a Box download host (`*.boxcloud.com` / `*.box.com`, excluding `api.box.com` and embedded credentials). Refreshes the token once on `401` without further retries; treats initial root-folder `403`/`404` as source permission loss by recording `source_unreachable` and returning a complete empty listing `([], None)` so `SyncEngine` marks existing origins `revoked`, while raising `BoxError` on mid-enumeration/mid-pagination `403`/`404` so unseen items are not partially revoked.
  - [test_connector_box.py](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-STC-004/tests/test_connector_box.py) (new): Offline test suite using `httpx.MockTransport` covering CCG token acquisition and re-acquisition after expiry, paginated and recursive folder enumeration with depth (`8`) and item (`1,000`) bounds, `file_version.id` and `sha1` revision/diff handling via `Service.sync_connector`, redirect following to Box download hosts without leaking the `Authorization` header, refusal of insecure/unexpected initial and chained redirect hosts, non-following of redirects on listing endpoints, single-retry `401` token refresh without infinite loops, initial `403`/`404` origin revocation vs. mid-pagination `403` abort without partial revocation, unconfigured/invalid-source handling, and non-exposure of `client_secret` across exceptions, connector state, rejections, and sync results.
- Inconsistencies between documentation and code:
  - The task specification states that the sync request's `source` carries the Box folder ID (`"0"` for root), whereas `Service.sync_connector` in [service.py](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-STC-004/backend/app/service.py#L951-L970) currently forwards `source` only as `source_label` to `SyncEngine.sync` rather than passing it to the connector (`service.py`, `main.py`, and `connectors.py` are outside `allowed_paths`, matching `T-STC-002` and `T-STC-003`; `BoxConnector` accepts `source` at construction and wiring request-time `source` / startup registration belongs to `T-STC-005`).
  - `backend/app/connectors.py` and the `backend/app/connectors/` package share the module name `app.connectors`, so importing `app.connectors` resolves to the package rather than `connectors.py`. Following the existing convention in `app/service.py`, `app/connector_local.py`, and `app/connector_gdrive.py`, `connector_box.py` loads `connectors.py` via `importlib.util.spec_from_file_location`.
  - `AGENTS.md` and `docs/agent/PROTOCOL.md` describe worker updates to `progress/<phase>/tasks/<TASK-ID>.md`, whereas the controller brief and `jobloop/gates.py` strictly enforce `allowed_paths` (`backend/app/connector_box.py`, `tests/test_connector_box.py`, `backend/requirements.lock`) and require the report in this reply only; followed the brief and `gates.py`.
- Risks left behind:
  - When a folder tree exceeds `MAX_DEPTH` (`8`) or `MAX_ITEMS` (`1,000`), `list_items` records `depth_limit` / `item_limit` in `self.rejections` and returns the bounded listing as complete (matching `LocalFolderConnector` in [connector_local.py](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-STC-004/backend/app/connector_local.py#L216-L226)); any previously imported items beyond those bounds would be marked `revoked` by `SyncEngine`.
  - Pre-existing `mypy` errors remain in untouched [main.py](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-STC-004/backend/app/main.py) (7 errors when running `python -m mypy backend/app`), while `python -m mypy backend/app/connector_box.py` passes cleanly with 0 errors.
  - Live end-to-end verification against Box's CCG OAuth2 and v2 REST/download endpoints remains pending owner creation and Box administrator approval of the Server (CCG) application, as noted in the task background. Read-path enforcement of `document_origins.revoked` across retrieval endpoints is deferred to `T-STC-005` per the phase plan.

TEST
- `python -m pytest tests/test_connector_box.py -q` (red check before creating `backend/app/connector_box.py`): failed (exit 1), `ModuleNotFoundError: No module named 'app.connector_box'`
- `python -m pytest tests/test_connector_box.py tests/test_connectors.py -q` (initial implementation run): `26 passed in 4.94s`
- `python -m ruff check

### Controller gates

- `scope`: green
- `task-verification`: green
- `python-lint`: green
- `python-format`: green
- `secret-scan`: green

## REVIEW by agy/gemini-4-argon-low (2026-11-26T12:38:39+09:00)

VERDICT
- APPROVED

FINDINGS
- none

UNVERIFIED
- Live Box API integration (Client Credentials Grant approval and folder collaboration in Box Developer Console are external owner prerequisites; tests verify all protocol flows against `httpx.MockTransport` as required by the task definition).
