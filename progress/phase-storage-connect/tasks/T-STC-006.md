---
id: T-STC-006
phase: phase-storage-connect
status: review
assignee: opencode
model: agy/gemini-4-hydrogen-low
weight: light
depends_on: T-STC-001
allowed_paths: tests/test_connectors.py
test_cmd: python -m pytest tests/test_connectors.py -q
updated: 2026-11-25T20:31:09+09:00
attempts: 0
reviewer: agy/gemini-4-argon-low
---

# Task `T-STC-006`: 一覧が途中で失敗したときに取消を走らせない守りに、退行テストを付ける

## SCOPE — レビュアーへ（先に読むこと）

- **この票はテストだけを足す。** `backend/app/connectors.py` の不具合は
  `T-STC-001` で**既に直っている**（`connectors.py:76-169` の `complete` ガード）。
  この票は**実装を直す票ではない**。直っている守りに退行テストを付ける票である。
- **`T-STC-001` の受入条件を蒸し返さないこと。** あの票の条件 1 は
  「フェイクコネクタで同期の往復（登録／差分／取消）がテストで検証されている」であり、
  **ページ途中失敗という端の場合は名指ししていない**。だからこの票に分けた。
  往復そのものの検証は `T-STC-001` 側で済んでいる。

## TASK DEFINITION (Assigned by Orchestrator)

- **なぜこの票があるか**: `T-STC-001` の 1 周目のレビューが High として挙げた不具合
  （一覧がページ途中で失敗した後に、見えなかった出自を取消してしまう）は、
  2 周目のレビューが確認したとおり**直っている**。しかし**それを守るテストが無い**。
  2026-11-25 12:58 のレビューの指摘（Medium, `tests/test_connectors.py:208-222`）が
  そのまま根拠である。

- **具体的な失敗の筋**（レビュアーが書いたもの）: 将来の編集が `complete` ガードを外すか、
  `revoke_missing_document_origins` をガードの外へ戻したとき、**現在の 6 件の
  コネクタテストは全部通る**。どれも「`A,B` を同期した後、次の同期で 1 ページ目に `A` を
  返して 2 ページ目で例外を投げる」という形を作っていないためである。

- **Implementation Details**:
  1. フェイクコネクタのテストを 1 本足す。筋は次のとおり。
     - 出自を 2 件（`A`、`B`）仕込んで同期を 1 回成功させる
     - 次の `list_items` 呼び出しで 1 ページ目を返したあと `RuntimeError` を投げさせる
     - 同期結果が `list_failed` を報告し、`failed >= 1` であること
     - **`revoked == 0`** であること
     - 見えなかった出自 `B` が **`revoked is False`** のまま残っていること
  2. 既存の 6 件のコネクタテストを壊さないこと。

## ACCEPTANCE CRITERIA

1. 上記の筋のテストが `tests/test_connectors.py` にあり、通ること。
2. そのテストが**守りを外すと落ちる**ことを確かめ、どう確かめたかを `## TEST` に書くこと
   （`complete` ガードを一時的に外して赤くなることを見る、など。
   **確かめた後は必ず元に戻すこと** — `backend/app/connectors.py` は許可パスの外である）。
3. 既存の `tests/test_connectors.py` に退行がない。
4. `python -m pytest tests/test_connectors.py -q` が緑。
5. 変更が `allowed_paths` 内に収まっている（`tests/test_connectors.py` のみ）。

## CONTAINMENT UNVERIFIED (2026-11-25T20:31:04+09:00)

The operator was editing the main checkout during this cycle, so the containment comparison was suspended. The worker's isolation was not verified for this attempt.

## ATTEMPT 1 — implementation by agy/gemini-4-hydrogen-low (2026-11-25T20:31:09+09:00)

REPORT
- `tests/test_connectors.py`: Added `test_sync_does_not_revoke_when_listing_fails_mid_pagination` to verify that when `list_items` succeeds on page 1 (returning `ext-a` and cursor `"page-2"`) and raises `RuntimeError` on page 2, `SyncEngine.sync` reports `failed >= 1` with `list_failed` in `reasons`, `revoked == 0`, and the unseen origin `ext-b` remains `revoked is False`.
- No inconsistency found between documentation and code.
- No remaining risk.

TEST
- `python -m pytest tests/test_connectors.py -q` (baseline before edits): `6 passed in 3.45s`
- `python -m pytest tests/test_connectors.py -q` (with `if complete else 0` guard temporarily removed in `backend/app/connectors.py` to verify the regression test catches the bug): `1 failed, 6 passed in 4.03s` — `test_sync_does_not_revoke_when_listing_fails_mid_pagination` failed at `assert second["revoked"] == 0` (`assert 1 == 0`). `backend/app/connectors.py` was immediately restored afterwards.
- `python -m ruff format tests/test_connectors.py`: `1 file reformatted`
- `python -m pytest tests/test_connectors.py -q` (after final edit): `7 passed in 3.40s`
- `python -m ruff check backend tests scripts jobloop`: `All checks passed!`
- `python -m ruff format --check backend tests scripts jobloop`: `194 files already formatted`
- `python scripts/secret_scan.py tests/test_connectors.py`: `Offline secret scan: 0 findings`
- `git status --short`: ` M tests/test_connectors.py`

STATUS
ready-for-review

### Controller gates

- `scope`: green
- `task-verification`: green
- `python-lint`: green
- `python-format`: green
- `secret-scan`: green

## REVIEW by agy/gemini-4-argon-low (2026-11-25T20:31:56+09:00)

VERDICT
- APPROVED

FINDINGS
- none

UNVERIFIED
- Hosted GitHub Actions CI execution (local deterministic verification ran and passed, including `python -m pytest tests/test_connectors.py -q` with 7 passed, lint, format, and secret scan).
