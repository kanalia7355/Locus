---
id: T-STC-002
phase: phase-storage-connect
status: review
assignee: opencode
model: opencode/deepseek-v4.1-flash-free
weight: medium
updated: 2026-11-26T12:12:15+09:00
attempts: 0
depends_on: T-STC-001
allowed_paths: backend/app/connector_local.py, tests/test_connector_local.py
test_cmd: python -m pytest tests/test_connector_local.py tests/test_connectors.py -q
reviewer: agy/gemini-4-argon-low
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

## ATTEMPT 1 — implementation by opencode/deepseek-v4.1-flash-free (2026-11-26T12:12:15+09:00)

REPORT
- `backend/app/connector_local.py` (new): implements `LocalFolderConnector` against the T-STC-001 `list_items` / `fetch_content` contract. The root comes from `LOCUS_LOCAL_SOURCE_ROOT` (or an injected root/env seam for tests); `source` is accepted only as a root-relative sub-path and is refused when absolute, drive-qualified, UNC, containing `..`/`.`/empty segments, alternate-data-stream colons, Windows-reserved device names, or trailing dot/space shapes. Enumeration is metadata-only (no file is opened): it walks breadth-first with `MAX_DEPTH = 8` and `MAX_ITEMS = 1000`, skips symlinks/junctions/reparse points, re-checks each directory's ancestor chain before descending, and records reason codes in `self.rejections` (`root_not_configured`, `path_escape`, `symlink_or_junction`, `depth_limit`, `item_limit`, `not_a_file`, `unreadable`). `external_id` is the root-relative POSIX path, `revision` is `mtime_ns:size`, and `content_hash` is left empty because the sync engine computes SHA-256 when it fetches the bytes. `fetch_content` re-validates the id, re-checks the ancestor chain, rejects links, resolves the real path and confirms it is still under the root before opening it read-only (`"rb"`).
- `tests/test_connector_local.py` (new): covers metadata-only listing (asserts no `open` call during enumeration), normal fetch, `source` sub-folder selection, path escapes (`..`, absolute, drive, UNC, ADS, trailing dot/space, reserved shapes), read-only behaviour (content/size/mtime unchanged), symlinked file/directory, junction, swap-after-listing, unavailable root, environment-supplied root, depth/item limits, and an end-to-end `Service.sync_connector` round trip that verifies the origin’s `content_hash` equals SHA-256 of the file content.

Inconsistencies found:
- The task text says the sync request’s `source` selects the relative sub-path, but `Service.sync_connector` passes `source` only as `source_label` to `SyncEngine`, and `SyncEngine` never forwards it to the connector. Since `backend/app/service.py`, `backend/app/main.py` and `backend/app/connectors.py` are outside `allowed_paths`, `LocalFolderConnector` takes `source` at construction; wiring the request field belongs to T-STC-005.
- `progress/phase-storage-connect/PROGRESS.md` §2.1 says the local revision is `mtime + SHA-256`, while the task text (authoritative) says `revision = mtime + size` and `content_hash = SHA-256` computed by the engine at fetch. I followed the task text.
- `backend/app/connectors.py` and the `backend/app/connectors/` package share the module name `app.connectors`; the package wins on import, so the contract file cannot be imported by name. `app/service.py` and `tests/test_connectors.py` already load it via `importlib.util.spec_from_file_location`; `connector_local.py` follows that same convention.
- `Service.sync_connector_credentials_configured` already contains a `local_folder` key defaulting to `False`, but no local connector is registered and no presence wiring exists yet; that is outside this task’s allowed paths (T-STC-005).

Risks left behind:
- A listing truncated by `MAX_DEPTH` or `MAX_ITEMS` is returned as a complete page (`cursor = None`). `SyncEngine` therefore treats it as complete and may mark origins beyond the cap as revoked. The sync contract has no truncation signal, and `connectors.py` is outside `allowed_paths`.
- A small resolve/verify-to-`open` race remains; the read is read-only and re-verified, but there is no atomic no-follow open (Windows lacks `O_NOFOLLOW`).
- Three symlink tests are skipped on this Windows host because creating symlinks requires a privilege (`WinError 1314`), following the existing `test_storage_connector_smb.py` convention. The junction test executed and passed here; the symlink tests should execute on a POSIX CI runner.
- `content_hash` is intentionally empty at enumeration; a caller that expects it before fetching would need to change the contract.

TEST
- `python -m pytest tests/test_connector_local.py tests/test_connectors.py -q` → **19 passed, 3 skipped** (skips: symlink creation denied by Windows privilege; junction test ran and passed).
- `python -m ruff check backend/app/connector_local.py tests/test_connector_local.py` → first run **failed** with `I001` (import block un-sorted); after `ruff check --fix` → **All checks passed**.
- `python -m ruff format backend/app/connector_local.py tests/test_connector_local.py` → reformatted 1 file; `--check` → **2 files already formatted**.
- `python -m ruff check backend tests scripts jobloop` → **All checks passed**.
- `python -m ruff format --check backend tests scripts jobloop` → **202 files already formatted**.
- `python scripts/secret_scan.py backend/app/connector_local.py tests/test_connector_local.py` → **0 findings**.
- `git status --porcelain` → only `?? backend/app/connector_local.py` and `?? tests/test_connector_local.py`.

STATUS
ready-for-review

### Controller gates

- `scope`: green
- `task-verification`: green
- `python-lint`: green
- `python-format`: green
- `secret-scan`: green

## REVIEW by agy/gemini-4-argon-low (2026-11-26T12:13:33+09:00)

VERDICT
- APPROVED

FINDINGS
- none

UNVERIFIED
- `test_symlinked_file_outside_root_is_not_followed`, `test_fetch_rechecks_after_listing_when_file_is_replaced`, and `test_symlinked_directory_outside_root_is_not_traversed` in `tests/test_connector_local.py` were skipped during local task verification because the unprivileged Windows test account lacks `SeCreateSymbolicLinkPrivilege` (`[WinError 1314]`). Reparse-point traversal protection on Windows was exercised via `test_junction_outside_root_is_not_traversed` (`mklink /J`), and the symlink branches follow the task's documented skip convention (`T-STC-002.md` Implementation Details 5).
