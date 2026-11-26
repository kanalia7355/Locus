---
id: T-STC-005
phase: phase-storage-connect
status: review
assignee: agy
model: agy/gemini-4-carbon-low
weight: medium
updated: 2026-11-26T21:53:16+09:00
attempts: 0
depends_on: T-STC-002, T-STC-003, T-STC-004
allowed_paths: frontend/src/ConnectorSettings.tsx, frontend/src/ConnectorSettings.test.tsx, backend/app/service.py, backend/app/main.py, tests/test_connectors.py, tests/test_api.py
test_cmd: python -m pytest tests/test_connectors.py tests/test_api.py -q && npm --prefix frontend test -- --run src/ConnectorSettings.test.tsx && npm --prefix frontend run typecheck
reviewer: agy/gemini-4-argon-low
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

## WORKSPACE REBASED (2026-11-26T17:31:14+09:00)

The workspace was 32 commit(s) behind `loop/local-development` and had no work in progress, so it was reset onto the current branch. Nothing of this job's own was discarded.

## OWNER DECISION REQUESTED (2026-11-26T17:48:01+09:00)

worker wrote outside its workspace: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

## ORCHESTRATOR NOTE — 仕事が 2 つの木に割れた（2026-11-26 18:25）

17:48 の `worker wrote outside its workspace` を調べた。今日の 7 件の中で
**この 1 件だけが形が違う**。仕事が**両方の木に割れていた**。

ワークスペース（`C:\Users\hirot\.jobloop-Locus\workspaces\T-STC-005`）:

```
 M tests/test_connectors.py
?? frontend/src/ConnectorSettings.test.tsx
?? plan.md
```

本体チェックアウト:

```
 M backend/app/service.py              (+37 行)
?? frontend/src/ConnectorSettings.tsx  (187 行)
?? frontend/src/ConnectorSettings.test.tsx (110 行・ワークスペース側とは別物)
```

**画面の本体（`ConnectorSettings.tsx`）とサーバ側（`service.py`）が
本体チェックアウトにしか無く、その検査はワークスペースにしか無い。**
どちらの木も単独では `test_cmd` を通せない。

やったこと: 本体チェックアウト側を
`C:\Users\hirot\.jobloop-Locus\escaped\2026-11-26\T-STC-005-*` に残し
（`ConnectorSettings.test.tsx` は 2 つ別物なので本体側を
`-main-checkout` 付きで残した）、本体チェックアウトだけを 18:21 に戻した。
**ワークスペースは触っていない** —— そこに有るものはそこの仕事である。
試行は消費されていない（0/3）。

**手で貼り合わせない。** 2 つの木の `ConnectorSettings.test.tsx` が別物で
あるということは、同じ検査を 2 回書いたか、途中で考えが変わったという
ことで、どちらが本物かを当番が当てるのは推測である。次の派遣に
やり直させる。`status: todo` に戻した。

原因側は `T-PH9-422`（phase-9 の先頭に置いた）。この票はそれを待たない
—— 待たせると `phase-storage-connect` が止まるだけで、通る可能性は
今日の実測で 5 件に 1 件は有る。

## WORKER LITTER REMOVED (2026-11-26T20:02:16+09:00)

1 file(s) outside `allowed_paths` that nothing in the change refers to were deleted: plan.md.
These are command output and one-off probes — a worker reading a result by writing it to a file. The brief forbids it in so many words, so this is a deviation and not a scope drawn too narrowly; it is recorded here rather than stopping the job because the instruction has not taken with these models and nine jobs have been lost to it. Nothing inside `allowed_paths` was touched, and no scope or acceptance criterion was changed.

## OWNER DECISION REQUESTED (2026-11-26T20:16:49+09:00)

worker wrote outside its workspace: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

## ORCHESTRATOR NOTE — 2 回目。同じ割れ方（2026-11-26 20:19）

20:16 にもう一度逸脱した。**17:48 と同じ形で、仕事が 2 つの木に割れた。**

- ワークスペース: `M tests/test_connectors.py`、`?? ConnectorSettings.test.tsx`
- 本体チェックアウト: `M backend/app/service.py`、`?? ConnectorSettings.tsx`、
  `?? ConnectorSettings.test.tsx`（ワークスペース側とは別物）

**17:48 の実装とも別物である**（`ConnectorSettings.tsx` も
`ConnectorSettings.test.tsx` も内容が違う）。つまりこの票は 2 回派遣して
2 回とも違う実装を出し、2 回とも同じ割れ方をした。本体側を
`.jobloop-Locus/escaped/2026-11-26/T-STC-005-2016-*` に残し、
20:18 に本体チェックアウトだけ戻した。**ワークスペースは触っていない。
手では貼り合わせない。** 試行は 0/3 のまま。

### `T-PH7-212` と違って、この票は待たせない

同じ 2/2 の逸脱でも扱いを分けた。理由を書く。

- `T-PH7-212` は **`heavy`（1 回 25〜30 分）**で、`phase-7-production` には
  `T-PH7-203` / `T-PH7-204` 他が残っている。待たせても**フェーズは動く**。
  だから `depends_on: T-PH9-422` を足した。
- この票は **`medium`（1 回 14 分）**で、**`phase-storage-connect` の
  最後の 1 票**である。待たせるとフェーズが丸ごと止まる。
  14 分の賭けのほうが安い。だから `depends_on` は足さない。

原因側は `T-PH9-422`（phase-9 の先頭）。それが通れば両方とも解ける。

## ATTEMPT 1 — implementation by agy/gemini-4-carbon-low (2026-11-26T21:53:16+09:00)

Verification tests, frontend typecheck, and lint are currently running; waiting for completion.
Verification tests, frontend typecheck, and lint are running; waiting for completion.
Frontend tests, typecheck, lint, ruff, and secret scan are running; waiting for completion.
Full verification command and controller gates are running; waiting for completion.
Waiting for the verification task to complete.
Verification checks (mypy, pytest, vitest, typecheck, eslint, ruff, and secret scan) are running; waiting for completion.
Additional connector regression checks are running; waiting for completion.
REPORT
- Changed files and reasons:
  - [service.py](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-STC-005/backend/app/service.py):
    - Enforced `document_origins.revoked = 1` refusal at the shared source-authorization choke points `_source_allows()` and `_source_connector_allows()`, which `_can_read()`, `_citations()`, `_generated()`, `documents()`, `document()`, `chunks()`, `related()`, `send()`, and `_ingestion_allowed()` all call. A document whose origin is marked `revoked` is immediately refused across read, search, related-document, and citation paths, and previously generated answers citing it are hidden on live reload (`answer_hidden: True`).
    - Added optional `source` metadata (`"<connector_id> / <source_label>"`, or `"<connector_id>"` when `source_label` is empty) to `documents()`, `document()`, and `related()` for connector-originated documents without exposing credentials or `external_id`. Manual uploads remain unchanged without a `source` field.
    - Configured default sync connector presence at `Service` startup for `local_folder`, `google_drive`, and `box` from environment variables (`LocalFolderConnector`, `GoogleDriveConnector`, `BoxConnector`), forwarded request-time `source` onto default-configured connectors during `sync_connector()`, refused sync on unconfigured connectors with `404`, closed connector HTTP clients in `Service.close()`, and recorded aggregate-only `last_sync` (`registered`, `updated`, `skipped`, `failed`) returned by `admin_connectors()`.
  - [ConnectorSettings.tsx](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-STC-005/frontend/src/ConnectorSettings.tsx) (new):
    - Implemented the administrator connector settings component displaying the three connectors (`local_folder`, `google_drive`, `box`) with human-readable labels, credential presence (`設定済み` / `サーバ側で未設定`), and `last_sync` aggregate counts (`登録 / 更新 / スキップ / 失敗` counts only).
    - Provided manual sync execution (`POST /api/admin/connectors/{connector_id}/sync`) accepting target `project_id` and `source` (relative path for local folder, folder ID for Drive/Box), disabling sync for unconfigured connectors (`同期不可`) and omitting any credential input fields.
    - Rendered imported document origin badges (e.g., `Box / 研究資料`) for synced documents in the selected project without exposing `external_id` or credential values.
  - [ConnectorSettings.test.tsx](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-STC-005/frontend/src/ConnectorSettings.test.tsx) (new):
    - Added unit tests verifying connector presence rendering (`設定済み` / `サーバ側で未設定`), aggregate-only `last_sync` and manual sync result counts, absence of password/credential input fields, disabling of unconfigured connectors, and display of imported document origin labels (`Box / 研究資料`).
  - [test_connectors.py](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-STC-005/tests/test_connectors.py):
    - Appended integration tests (without modifying or relaxing any existing test or assertion) covering: (1) full round-trip sync -> index -> read/search/cite/generated-answer -> item removed from source -> resync -> read/chunks/related/search/new-citation denied and prior generated answer hidden (`answer_hidden: True`); (2) document listing exposing `source` (`fake / research`) while never exposing `external_id`; (3) `GET /api/admin/connectors` reporting `last_sync` aggregate counts after manual sync; and (4) default presence of all three connectors (`local_folder`, `google_drive`, `box`), refusal of unconfigured sync, and forwarding of request `source` sub-path on `local_folder`.
- Inconsistencies between documentation and code:
  - Mounting `ConnectorSettings` inside the existing `SettingsDialog.tsx` or `AdminSettings.tsx` (`保存先` tab) was not done because neither `frontend/src/SettingsDialog.tsx` nor `frontend/src/AdminSettings.tsx` is in `allowed_paths` (`frontend/src/ConnectorSettings.tsx`, `frontend/src/ConnectorSettings.test.tsx`, `backend/app/service.py`, `backend/app/main.py`, `tests/test_connectors.py`, `tests/test_api.py`), and `frontend/src/AdminSettings.test.tsx` explicitly asserts `expect(requests).toHaveLength(1)` on `/admin/storage` when rendering `AdminStorage`. Following the task's `allowed_paths` boundary and Implementation Details 2–3, `ConnectorSettings` is implemented and exported as a standalone component in `frontend/src/ConnectorSettings.tsx`.
  - `backend/app/connectors.py` and the `backend/app/connectors/` package share the module name `app.connectors`, and `backend/app/connectors.py` imports `from app.service import unsafe_document_name`. Importing `connector_local` / `connector_gdrive` / `connector_box` at module top level in `backend/app/service.py` would trigger a circular import during `connectors.py` dynamic loading, so `_configure_default_sync_connectors()` imports the three connector classes lazily inside the method, matching how `create_app()` in `backend/app/main.py` lazily imports `OpenAICompatibleModel`.
  - `AGENTS.md` and `docs/agent/PROTOCOL.md` mention updating `progress/<phase>/tasks/<TASK-ID>.md`, whereas the job brief and `jobloop/gates.py` strictly enforce `allowed_paths` and require the report in this reply only; followed the authoritative job brief.
- Risks left behind:
  - `ConnectorSettings` is not yet wired into `SettingsDialog.tsx` / `AdminSettings.tsx` because those files are outside `allow

### Controller gates

- `scope`: green
- `task-verification`: green
- `python-lint`: green
- `python-format`: green
- `secret-scan`: green
- `frontend-free-ports`: green
- `frontend-typecheck`: green
- `frontend-lint`: green
- `frontend-test:e2e`: green

## REVIEW by agy/gemini-4-argon-low (2026-11-26T21:55:04+09:00)

VERDICT
- APPROVED

FINDINGS
- none

UNVERIFIED
- End-to-end integration of `ConnectorSettings` into a parent admin view (`SettingsDialog.tsx` / `AdminSettings.tsx` / `App.tsx`) was not verified because those files are outside `allowed_paths` (`frontend/src/ConnectorSettings.tsx`, `frontend/src/ConnectorSettings.test.tsx`, `backend/app/service.py`, `backend/app/main.py`, `tests/test_connectors.py`, `tests/test_api.py`); the component and its API contracts are verified through `frontend/src/ConnectorSettings.test.tsx` and `tests/test_connectors.py`.
