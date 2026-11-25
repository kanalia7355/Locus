---
id: T-STC-007
phase: phase-storage-connect
status: todo
assignee: unassigned
model: -
weight: light
depends_on: T-STC-001
allowed_paths: backend/app/connectors.py, tests/test_connectors.py
test_cmd: python -m pytest tests/test_connectors.py -q
updated: 2026-11-25T16:30:00+09:00
attempts: 0
---

# Task `T-STC-007`: 出自の記録が失敗しても、同期全体を落とさない

## SCOPE — レビュアーへ（先に読むこと）

- **この票は `T-STC-001` の受入条件を蒸し返す票ではない。** あの票の条件 1〜5 は
  同期の往復・走査/ACL/上限・資格情報の非露出・既存テストの退行・許可パスであり、
  **出自記録の失敗経路の堅牢さは名指ししていない**。だからこの票に分けた。
- **判断はこの票の受入条件に対して行うこと。** 条件の外で気づいたことは
  `## REVIEW` に所見として書き、`CHANGES_REQUIRED` の理由にしないこと。

## TASK DEFINITION (Assigned by Orchestrator)

- **なぜこの票があるか**: 2026-11-25 15:24 の `T-STC-001` のレビューが Medium として
  挙げた指摘がそのまま根拠である。`backend/app/connectors.py:141-159` の
  `record_document_origin` は `service.upload()` が commit した**後**に、しかも
  アップロード失敗を扱う `try/except` の**外**で走る。

- **具体的な失敗の筋**（レビュアーが書いたもの）: `upload()` が `ext-1` の文書を
  queued で返した直後に `record_document_origin()` が例外を上げると
  （一時的な DB ロックなど）、**文書は既に永続化されているのに同期全体が落ちる**。
  文書は残り、出自は記録されない、という食い違った状態になる。

- **Implementation Details**:
  1. 出自の記録を、アップロード失敗を扱うのと同じ扱いの中に入れること。
     1 件の失敗で同期全体を落とさず、その 1 件を失敗として数えて続けること。
  2. **文書が残って出自が無い状態をどう扱うかを決めて、記録に書くこと。**
     次の同期で拾い直せるのか、それとも記録できなかった文書を取り消すのか。
     どちらでもよいが、**選んだ理由を書くこと**。
  3. 既存の 6 件のコネクタテストを壊さないこと。

## ACCEPTANCE CRITERIA

1. `record_document_origin` が例外を上げたとき、**同期全体が落ちない**ことを示す
   テストがある（フェイクコネクタで出自記録だけを失敗させる）。
2. そのとき同期結果が、その 1 件を**失敗として報告する**ことを示すテストがある。
3. 文書が残って出自が無い状態の扱いが、Implementation Details 2 の決定どおりに
   動くことを示すテストがある。
4. 既存の `tests/test_connectors.py` に退行がない。
5. `python -m pytest tests/test_connectors.py -q` が緑。
6. 変更が `allowed_paths` 内に収まっている。
