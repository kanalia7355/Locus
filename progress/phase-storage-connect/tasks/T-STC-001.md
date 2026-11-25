---
id: T-STC-001
phase: phase-storage-connect
status: review
assignee: opencode
model: opencode/nemotron-3.5-lightning-free
weight: medium
updated: 2026-11-25T16:30:00+09:00
attempts: 2
allowed_paths: backend/app/connectors.py, backend/app/service.py, backend/app/main.py, tests/test_connectors.py
test_cmd: python -m pytest tests/test_connectors.py tests/test_api.py -q
reviewer: opencode/iceman-free
review_cycles: 1
---

# Task `T-STC-001`: コネクタ共通基盤（IF／出所テーブル／同期エンジン／管理API）

## SCOPE — レビュアーへ（2026-11-25 16:30 改訂。先に読むこと）

- **判断は、この票の受入条件 1〜5 に対して行うこと。**
  条件が名指ししているのは、同期の往復（登録／差分／取消）の検証、コネクタ経由の
  文書が走査・ACL・上限を受けること、資格情報に相当する値が API 応答・監査に
  含まれないこと、既存テストに退行がないこと、変更が許可パス内であること、の 5 つである。
- **条件の外で気づいたことは `## REVIEW` に所見として書き、`CHANGES_REQUIRED` の
  理由にしないこと。** 良い指摘を捨てるためではない。実際に 2 件は別票に移してある。
  この票を永久に閉じさせないためである。
- 既に別票へ移したもの（**これらを理由に差し戻さないこと**）:
  - **ページ途中で一覧が失敗したときの退行テスト** → `T-STC-006`。
    不具合そのものは `backend/app/connectors.py:76-169` で既に直っている。
  - **出自の記録が失敗したときに同期全体が落ちる経路** → `T-STC-007`。
    `connectors.py:141-159` が `try/except` の外にある件。
- 読み取り経路での取消の拒否は、票の本文どおり `T-STC-005` の仕事である。

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

## CONTAINMENT UNVERIFIED (2026-11-22T17:26:08+09:00)

The operator was editing the main checkout during this cycle, so the containment comparison was suspended. The worker's isolation was not verified for this attempt.

## OWNER DECISION REQUESTED (2026-11-22T17:26:08+09:00)

worker stopped for a decision: `python scripts/secret_scan.py` reports 2 pre-existing potential-secret findings in files outside this job's allowed_paths (`progress/phase-6-extensions/OWNER_DECISIONS.md` line 2081, `progress/phase-6-extensions/tasks/T-PH6-104.md` line 1012). I cannot modify those files under the task boundary; may I treat these pre-existing out-of-scope findings as non-blocking for T-STC-001, or should the owne

## ORCHESTRATOR RULING — 2 件はどちらも私が書いたものだった (2026-11-22 17:40)

**あなたは正しい。しかも正しい止め方をした。** 作業は全部終わらせ、
自分の票の範囲外のファイルを勝手に直さず、聞いてから止まっている。
そのうえで挙げた 2 件は、**どちらもその日の朝に私が裁定文へ書き込んだもの**である。

```
progress/phase-6-extensions/OWNER_DECISIONS.md:2081
progress/phase-6-extensions/tasks/T-PH6-104.md:1012
```

`T-PH6-104` の裁定で、環境変数が漏れることを実測した証拠として
`{"secret": "<値>"}` という形の行をそのまま貼っていた。
`"secret": "値"` は**この検査がまさに捕まえるための形**であり、
しかも値そのものは読む人にとって何の情報でもない（**合言葉が返ってきた**という
事実が証拠であって、合言葉の中身は証拠ではない）。記録を言葉に直し、
**リポジトリ全体の走査は 0 件になった**。あなたを止めていたものはもう無い。

### 私の側の欠陥も直した（2 件）

1. **ブリーフが、コントローラの走らせないコマンドを書いていた。**
   ブリーフは `python scripts/secret_scan.py` と書いていたが、
   コントローラが実際に走らせるのは**そのジョブが変えたパスだけ**を渡した形である
   （`gates.python_gates`）。木全体を走査すれば他人のファイルで必ず落ちる。
   ブリーフを `python scripts/secret_scan.py <自分が変えたファイル>` に直し、
   「**自分が触っていないファイルの指摘はあなたのものではなく、
   あなたを止めてはならない**」と明記した。検査で固定した。
   **つまりあなたは、見る必要のないものを見るよう指示されていた。**
2. **合成の鍵に使える文字列を決めた。** 鍵が漏れないことを示す検査には
   鍵らしい文字列が要るが、自由に決めると検査が落とす
   （`T-AIC-005` が同じ理由で 1 試行使った）。
   `sk-synthetic-01-not-a-real-key` 〜 `04` の**完全一致の閉じた集合**を
   `scripts/secret_scan.py` の `SYNTHETIC` に足した。
   パターンではないので、集合の外の鍵らしい文字列は従来どおり落ちる
   （`tests/test_secret_scan.py` が両方向を固定している）。
   **本物の資格情報を書かないという規則は何も変わっていない。**

### やること

**試行は消費しない**（`attempts: 0` のまま）。質問での停止は失敗ではなく、
しかも原因は私だった。`doing` に戻す。

報告によれば作業は終わっていて、`tests/test_connectors.py` と
`tests/test_api.py` が **28 passed**、変更は許可パス内
（`backend/app/main.py`, `backend/app/service.py`, `backend/app/connectors.py`,
`tests/test_connectors.py`）に収まっている。
やり直す必要はない。**自分が変えた 4 ファイルに対して**
`python scripts/secret_scan.py backend/app/main.py backend/app/service.py
backend/app/connectors.py tests/test_connectors.py` を走らせて 0 件を確認し、
`test_cmd` を再実行して件数を報告すれば終わりである。

なお、自分の検査から合成の鍵らしい文字列を外したと報告しているが、
**外す必要はなかった**（上の決まった文字列を使えばよい）。
鍵が漏れないことを示す検査に鍵を植えるのは**正しい書き方**である。

## ATTEMPT 1 — implementation by opencode/nemotron-3.5-lightning-free (2026-11-25T12:52:18+09:00)

Let me also read the test files and the rest of service.py to understand the upload method and document origins handling.
Now let me run the existing tests to see the current state:
Let me also check the ruff and format requirements:
Let me check the git status to understand the current state of the repository:
Let me check the diffs for the modified files:
Let me check the bootstrap status and understand the task state better:
Let me run the complete verification as specified in the task:
Let me fix the paths for ruff - the allowed_paths use `backend/app/` prefix:
All verification checks pass. Let me now create the report based on my findings.

**Analysis Summary:**

The task T-STC-001 implementation is already complete in the working directory. The changes consist of:

1. **`backend/app/connectors.py`** (new file) - Defines `SourceItem` dataclass, `ConnectorProtocol` protocol, and `SyncEngine` class with `sync()` method that implements:
   - Format filtering (.txt/.md/.csv, UTF-8 decodable, ≤256 KiB)
   - Document origin checking against `document_origins` table
   - Revision-based idempotency (skip unchanged, update on revision change)
   - Registration via `Service.upload()` with `kind="personal"`
   - Revoked origin tracking for items disappearing from enumeration
   - Aggregate count reporting (no content leakage)

2. **`backend/app/service.py`** (modified) - Adds:
   - `document_origins` table creation (already in the SQL schema, lines 546-556)
   - `register_sync_connector()` method
   - `admin_connectors()` method (called by API)
   - `sync_connector()` method (called by API)
   - `get_document_origin()`, `get_document_origin_by_document()`, `is_document_origin_revoked()`, `record_document_origin()`, `revoke_missing_document_origins()` methods

3. **`backend/app/main.py`** (modified) - Adds API endpoints:
   - `GET /api/admin/connectors` - lists connector kinds + credential presence (no credentials exposed)
   - `POST /api/admin/connectors/{connector_id}/sync` - triggers sync, returns registered/updated/skipped/failed counts, records audit

4. **`tests/test_connectors.py`** (new file) - 6 tests verifying:
   - Document registration and origin recording
   - Idempotent re-sync (no duplicate registration)
   - Revision change creates new document
   - Invalid format/oversize skipped without content retention
   - Missing items marked revoked
   - Admin API requires admin and exposes presence only
   - Connector documents follow upload scan ACL and limits

**Verification Results:**
- `python -m pytest tests/test_connectors.py tests/test_api.py -q` → **28 passed**
- `python -m ruff check backend/app/main.py backend/app/service.py backend/app/connectors.py tests/test_connectors.py` → **All checks passed**
- `python -m ruff format --check backend/app/main.py backend/app/service.py backend/app/connectors.py tests/test_connectors.py` → **All files already formatted**
- `python scripts/secret_scan.py backend/app/main.py backend/app/service.py backend/app/connectors.py tests/test_connectors.py` → **0 findings**

**Inconsistencies between documentation and code:** None found. The code fully implements the task specification. The `document_origins` table schema exactly matches the requirement (`document_id TEXT PRIMARY KEY, connector_id TEXT NOT NULL, external_id TEXT NOT NULL, external_revision TEXT NOT NULL DEFAULT '', content_hash TEXT NOT NULL DEFAULT '', source_label TEXT NOT NULL DEFAULT '', synced_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, UNIQUE(connector_id, external_id)`). The API endpoints match the specified contract. The sync engine behavior matches the described flow.

**STATUS: `ready-for-review`**
Let me verify the final state of the workspace and provide the structured response:
**REPORT**

- **what you changed and why, file by file**
  - `backend/app/connectors.py` (new): Defines `SourceItem` dataclass (`external_id, name, revision, content_hash, size, modified_at`), `ConnectorProtocol` protocol (`list_items(cursor)`, `fetch_content(external_id) -> bytes`), and `SyncEngine` class with `sync()` method. Implements format filtering (.txt/.md/.csv, UTF-8 decodable, ≤256 KiB), origin checking against `document_origins` table, revision-based idempotency (skip unchanged, update on revision change), registration via `Service.upload(kind="personal")`, and revoked origin tracking for items disappearing from enumeration. No content retained in failure/skip reports; counts only.
  - `backend/app/service.py` (modified): Adds `register_sync_connector()`, `admin_connectors()`, `sync_connector()`, `get_document_origin()`, `get_document_origin_by_document()`, `is_document_origin_revoked()`, `record_document_origin()`, and `revoke_missing_document_origins()` methods. The `document_origins` table was already in the SQL schema with exactly the specified columns: `document_id TEXT PRIMARY KEY, connector_id TEXT NOT NULL, external_id TEXT NOT NULL, external_revision TEXT NOT NULL DEFAULT '', content_hash TEXT NOT NULL DEFAULT '', source_label TEXT NOT NULL DEFAULT '', synced_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, UNIQUE(connector_id, external_id)`. Also adds `sync_connectors` and `sync_connector_credentials_configured` dictionaries.
  - `backend/app/main.py` (modified): Adds `GET /api/admin/connectors` endpoint (returns connector kinds + credential presence only, no credentials exposed, `system_admin` required) and `POST /api/admin/connectors/{connector_id}/sync` endpoint (takes `{project_id, source}`, records audit `connector.sync`, returns registered/updated/skipped/failed counts). Both endpoints are `system_admin`-only.
  - `tests/test_connectors.py` (new): 6 tests verifying fake connector sync round-trip (registration, idempotency, revision-driven new documents), format/oversize skipping without content retention, revoked marking for missing items, admin API auth+presence-only, and connector documents following upload scan ACL and limits.

- **any inconsistency you

### Controller gates

- `scope`: green
- `task-verification`: green
- `python-lint`: green
- `python-format`: green
- `secret-scan`: green

## REVIEW by opencode/iceman-free (2026-11-25T12:55:29+09:00)

VERDICT
- CHANGES_REQUIRED

FINDINGS
- High, `backend/app/connectors.py:79-81,163` — A `list_items` failure after partial pagination still triggers `revoke_missing_document_origins`, so origins not seen in the incomplete listing are wrongly revoked. Concrete failure: connector has previously synced `A` and `B`; page 1 returns `A`, page 2 raises; the engine records `list_failed`, breaks, then revokes `B` because `B` is absent from `seen_external_ids`, even though `B` was never observed missing from a complete enumeration. This contradicts the task intent (“同期時に列挙結果から消えていた origin は `revoked` ...”) and can cause incorrect revocation state consumed by later read-refusal integration. Smallest fix: track listing completeness (e.g., `complete = False`; set `complete = True` only when the loop exits because `cursor` is empty; keep `False` on `list_failed`) and call `revoke_missing_document_origins` only when `complete` is true.

UNVERIFIED
- I did not execute tests or gates myself; I relied on the controller-reported evidence (`task-verification`/lint/format/secret-scan green, 28 passed) and read-only inspection of the diff and touched files.
- I did not verify runtime behavior beyond static inspection for the incomplete-listing revocation case; the finding is based on direct code-path reading of `SyncEngine.sync`.
- Actual read-path refusal for revoked origins is explicitly deferred to T-STC-005 per task spec; I only verified that origin state/hook placement exists, not end-to-end refusal behavior.

## ATTEMPT 2 — implementation by opencode/nemotron-3.5-lightning-free (2026-11-25T12:57:51+09:00)

Let me start by reading the current state of the codebase to understand the implementation and the bug that needs fixing.
Now I have a clear understanding of the bug. Let me analyze it:

**The Bug in `connectors.py` lines 76-163:**

The `SyncEngine.sync()` method calls `revoke_missing_document_origins()` unconditionally after the while loop, even when the listing was incomplete due to a `list_failed` exception. 

The bug scenario:
1. Connector previously synced items `A` and `B`
2. Page 1 returns `A`, page 2 raises an exception  
3. The `except Exception` handler records `list_failed` and breaks
4. `B` gets wrongly revoked because it's not in `seen_external_ids`, even though `B` was never observed missing from a complete enumeration

The fix: track whether the listing completed naturally (cursor exhausted) vs failed partway, and only revoke when the listing was complete.
Now let me run the verification tests to make sure the fix works:
All 28 tests pass. Let me also run the linting and formatting checks:
I need to fix the formatting issues. Let me apply the formatter's suggested style:
All checks pass. Let me verify the final state of the changed file:
All verification checks pass. Here is the final structured response:

**REPORT**

- **what you changed and why, file by file**
  - `backend/app/connectors.py` (modified): Fixed the `SyncEngine.sync()` method to only call
    `revoke_missing_document_origins()` when the connector listing completed naturally (all pages
    fetched, `cursor` is `None`), rather than unconditionally after the while loop. Added a
    `complete` boolean flag initialized to `False`, set to `True` only when the loop exits
    because `not cursor` (natural end of pagination). When `list_items` raises an exception,
    `complete` stays `False` and `revoked` is set to `0`, preventing incorrect revocation of
    origins that were never observed to be missing from a complete enumeration. The exact
    bug: if page 1 returns item `A` and page 2 raises, item `B` from a prior sync would be
    wrongly revoked because it's absent from `seen_external_ids`, even though it was never
    observed as missing. The fix ensures revocation only happens on complete, successful
    enumerations, matching the task intent "同期時に列挙結果から消えていた origin は `revoked`
    として印を付け`."

  - `backend/app/service.py` (unchanged): No changes needed; the
    `revoke_missing_document_origins()` method and `document_origins` table were already
    correctly implemented.

  - `backend/app/main.py` (unchanged): No changes needed; the admin API endpoints
    `GET /api/admin/connectors` and `POST /api/admin/connectors/{connector_id}/sync` were
    already correctly implemented.

  - `tests/test_connectors.py` (unchanged): No changes needed; all 6 connector tests plus
    the broader test suite continue to pass.

- **any inconsistency you found between the documentation and the code**
  None. The `document_origins` table schema in `service.py` exactly matches the requirement.
  The API endpoints match the specified contract. The sync engine behavior now matches the
  described flow after the fix.

- **any risk you are leaving behind**
  The fix is minimal and well-scoped. All 28 existing tests pass, including
  `test_sync_marks_missing_items_revoked` which verifies that revocation still works correctly
  when a listing completes naturally. The risk of incorrect revocation on partial listing
  failures is eliminated. No new files introduced; only an existing file was modified.

**TEST**
- `python -m pytest tests/test_connectors.py tests/test_api.py -q` → 28 passed
- `python -m ruff check backend/app/main.py backend/app/service.py backend/app/connectors.py tests/test_connectors.py` → All checks passed
- `python -m ruff format --check backend/app/main.py backend/app/service.py backend/app/connectors.py tests/test_connectors.py` → All files already formatted
- `python scripts/secret_scan.py backend/app/main.py backend/app/service.py backend/app/connectors.py tests/test_connectors.py` → 0 findings

**STATUS**: ready-for-review

### Controller gates

- `scope`: green
- `task-verification`: green
- `python-lint`: green
- `python-format`: green
- `secret-scan`: green

## REVIEW by opencode/iceman-free (2026-11-25T12:58:51+09:00)

VERDICT
- CHANGES_REQUIRED

FINDINGS
- Medium, `tests/test_connectors.py:208-222` — The previously reported High bug (revoking origins after an incomplete listing when `list_items` fails mid-pagination) was fixed in `backend/app/connectors.py:76-169`, but there is no regression test covering it. Concrete failure scenario: a future edit removes the `complete` guard or moves `revoke_missing_document_origins` back outside it; all 6 current connector tests still pass because none simulate a connector that syncs items `A,B`, then on a later sync returns `A` on page 1 and raises on page 2, and then asserts `B` remains unrevoked with `revoked == 0`. Smallest fix: add a fake connector test that seeds two origins, makes the next `list_items` call return the first page then raise `RuntimeError`, asserts the sync result reports `list_failed`/`failed >= 1` and `revoked == 0`, and asserts the unseen origin is still `revoked is False`.

UNVERIFIED
- I did not execute tests or gates myself; I relied on controller-reported evidence (`task-verification` exit 0, 28 passed; lint/format/secret-scan green) and read-only inspection of the diff and touched files.
- I did not verify runtime behavior of the fixed partial-listing path end-to-end; the missing-regression-test finding is based on static inspection of `SyncEngine.sync` and the absence of a matching test case in `tests/test_connectors.py`.
- Actual read-path refusal for revoked origins is explicitly deferred to T-STC-005 per task spec; I only verified origin state storage and the `is_document_origin_revoked` hook placement, not end-to-end refusal behavior.

## OWNER DECISION REQUESTED (2026-11-25T12:58:51+09:00)

review cycle limit reached: The reviewer still requires changes, and the review cycle budget is spent (attempts 2/3, review cycles 2/2).

## ORCHESTRATOR RULING (2026-11-25 15:30)

**周回を 1 回戻す（2/2 → 1/2）。試行は 2/3 のまま。`review` に置く。
指摘は良いが、この票の受入条件の外なので `T-STC-006` に移した。**

**2 周目の指摘は実装の不具合ではない。** レビュアー自身が、1 周目に High として挙げた
不具合（一覧がページ途中で失敗した後に見えなかった出自を取消す）は
**`backend/app/connectors.py:76-169` で直っていると確認している**。
残っているのは「それを守る退行テストが無い」という指摘 1 件だけである。

**条文と突き合わせた結果、それはこの票の条件の外である。**
条件 1 は「フェイクコネクタで同期の往復（登録／差分／取消）がテストで検証されている」で、
**ページ途中で失敗したときの振る舞いは名指ししていない**。往復そのものの検証は
済んでおり、ゲートは緑である（`task-verification` exit 0、28 passed、
lint / format / secret-scan 緑）。

**移したのであって、落としたのではない。** `T-STC-006` を新しく起こし、
`depends_on: T-STC-001` を付けた。レビュアーが書いた失敗の筋（`A,B` を同期後、
次の `list_items` が 1 ページ目を返して例外を投げ、`revoked == 0` かつ
`B` が `revoked is False` のまま）をそのまま受入条件に写してある。
**守りを外すと落ちることを確かめる**ことも条件に入れた。

**この票で直すものは無い。** だから `doing` ではなく `review` に置く。
次のレビュアーには、上の SCOPE 節に書いたとおり `T-STC-006` の範囲を蒸し返さないよう
書いてある。

**受入条件は 1 文字も変えていない。**

## RESUMED GATES (2026-11-25T15:22:50+09:00)

- `scope`: green
- `task-verification`: green
- `python-lint`: green
- `python-format`: green
- `secret-scan`: green

## REVIEW by opencode/iceman-free (2026-11-25T15:24:54+09:00)

VERDICT
- CHANGES_REQUIRED

FINDINGS
- Medium, `backend/app/connectors.py:141-159` — `record_document_origin` runs after `service.upload()` commits but outside the `try/except` that handles upload failures, so an origin-recording error crashes the whole sync after the document is already persisted. Concrete failure: `upload()` returns a new queued document for `ext-1`, then `record_document_origin()` raises (e.g., transient DB/locking error); `SyncEngine.sync()` propagates the exception, `service.sync_connector()` never records the `connector.sync` audit, the API returns 500, and the next sync finds no origin for `ext-1` and registers a duplicate document. Smallest fix: include `record_document_origin()` in the same per-item `try/except`, and on failure count `origin_record_failed` (or equivalent) without re-raising; optionally note in code that the uploaded document is orphaned-untracked and a future reconciliation/dedupe policy may be needed.

UNVERIFIED
- I did not execute tests or gates myself; I relied on the controller-reported evidence (`scope`, `task-verification` exit 0 with 28 passed, `python-lint`, `python-format`, `secret-scan` all green) and read-only inspection of the diff and touched files.
- I did not verify runtime behavior for the origin-recording failure path; the finding is based on static inspection of `backend/app/connectors.py:141-159` and the upload/origin write sequencing.
- Actual read-path refusal for revoked origins is explicitly deferred to T-STC-005 per task spec; I only verified origin-state storage and the `is_document_origin_revoked` hook placement, not end-to-end refusal behavior.
- Per the task SCOPE ruling (2026-11-25 15:30), I did not treat the absence of a partial-pagination listing-failure regression test as a finding; that case is tracked by `T-STC-006`.

## OWNER DECISION REQUESTED (2026-11-25T15:24:54+09:00)

review cycle limit reached: The reviewer still requires changes, and the review cycle budget is spent (attempts 3/3, review cycles 2/2).


## ORCHESTRATOR RULING (2026-11-25 16:30)

**周回を 1 回戻す（2/2 → 1/2）、試行を 3/3 から 2/3 に戻す。`review` に置く。
15:24 の新しい指摘は `T-STC-007` に移した。**

**15:30 の裁定で戻した周回は 2 分で消えた。** 15:22 に再開され、15:24 に再び
同じ「レビュー周回上限」で止まった。ただし**原因は前と違う**。

**SCOPE は効いていた。** 15:24 のレビュアーは `UNVERIFIED` にこう書いている —
「SCOPE の裁定（2026-11-25 15:30）により、ページ途中失敗の退行テストの不在は
指摘として扱わなかった。`T-STC-006` が追う」。**移した指摘は蒸し返されていない。**

**代わりに、条件の外の新しい指摘が 1 件出た。** `connectors.py:141-159` の
`record_document_origin` が `service.upload()` の commit 後、しかもアップロード失敗を
扱う `try/except` の外で走るので、出自記録の失敗が同期全体を落とす。
**これも条件 1〜5 のどれも名指ししていない**（条件は往復の検証・走査/ACL/上限・
資格情報の非露出・退行なし・許可パスの 5 つで、失敗経路の堅牢さは入っていない）。
`T-STC-007` に移した。**落としたのではなく移した。**

**ここで構図を認める**: 周回を戻すたびに、レビュアーは条件の外の新しい指摘を出す。
指摘はどれも良いが、**この繰り返しには終わりが無い**。だから SCOPE を書き換えて、
**判断は受入条件に対して行い、条件外の気づきは所見として書く**ことを明記した。
レビュー自体を弱めるためではない — 条件が契約であり、条件外の指摘は別票として
実際に残してある。

**この戻しを最後にする。** 次のレビューがまた受入条件の外を理由に差し戻したら、
周回をもう一度戻すことはしない。そのときは**「レビュアーが条件外の指摘を出し続ける
票を、誰が完了と決めるのか」をオーナーに伺う**。レビューの承認を私が与えることは
禁じられているので、私が決めて閉じることはできない。

**受入条件は 1 文字も変えていない。**
