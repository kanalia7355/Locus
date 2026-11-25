---
id: T-STC-006
phase: phase-storage-connect
status: todo
assignee: unassigned
model: -
weight: light
depends_on: T-STC-001
allowed_paths: tests/test_connectors.py
test_cmd: python -m pytest tests/test_connectors.py -q
updated: 2026-11-25T15:30:00+09:00
attempts: 0
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
