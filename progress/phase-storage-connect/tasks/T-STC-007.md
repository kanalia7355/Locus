---
id: T-STC-007
phase: phase-storage-connect
status: done
assignee: opencode
model: opencode/deepseek-v4.1-flash-free
weight: light
depends_on: T-STC-001
allowed_paths: backend/app/connectors.py, tests/test_connectors.py
test_cmd: python -m pytest tests/test_connectors.py -q
updated: 2026-11-26T11:59:49+09:00
attempts: 1
reviewer: agy/gemini-4-argon-low
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

## ATTEMPT 1 — implementation by opencode/deepseek-v4.1-flash-free (2026-11-26T11:58:51+09:00)

Now I'll add the failing tests first (TDD), then implement.

Tests fail for the right reason (origin exception escapes and aborts sync). Now the fix:

REPORT
- `backend/app/connectors.py`: `record_document_origin` now runs inside its own `try/except` inside the per-item loop, mirroring the `upload`/`fetch` failure handling. On failure the item is counted as `failed` with reason `origin_failed`, the sync continues with the remaining items, and the already-committed document is removed via `Service.delete_document` (best effort, guarded by `contextlib.suppress`, consistent with `backend/app/sandbox.py`). Decision for Implementation Details 2: **roll the document back rather than leave it**, because an origin-less document can never be updated or revoked by a later sync and a retry would otherwise import a duplicate; deleting it means the next sync re-imports the item cleanly, keeping “document exists” and “origin exists” in step. This is recorded in the code comment and in the tests below.
- `tests/test_connectors.py`: added `OriginFailingService`, a delegating wrapper around the real `Service` that raises only from `record_document_origin` for one external id (a fake connector/service, no production seam added), plus two tests: (1) an origin failure for one of two items does not abort sync — `registered == 1`, `failed == 1`, reason `origin_failed == 1`, and the healthy item still gets its origin; (2) the failed item leaves no orphan document, and a later successful sync registers it with the expected content. Existing tests were not modified.
- Inconsistency found: the ticket text says “the existing 6 connector tests”, but `tests/test_connectors.py` contained 7 passing tests at the base commit; the acceptance intent (no regression) is met and all 7 still pass. No documentation/code inconsistency was found in the governance or connector documentation.

Risks left behind:
- Rollback is best effort. If `delete_document` also fails (for example the same transient DB lock), the document remains without an origin and is only recoverable by operator action; the sync still does not abort, but the inconsistent row survives that rare double failure.
- The uploaded document is `queued`, so a worker could pick it up concurrently with the rollback delete; deletion removes the row but a concurrently started ingestion is outside this module’s control. This window already exists for any delete-after-upload and is unchanged by the normal (origin-succeeds) path.

TEST
- `python -m pytest tests/test_connectors.py -q` before the change: `7 passed in 3.39s`.
- Same command after adding the new tests but before the fix: `2 failed, 7 passed in 3.88s` (both new tests failed with the origin exception escaping `sync`).
- After the fix: `9 passed in 4.06s`; final rerun `9 passed in 3.60s`.
- `python -m ruff check backend tests scripts jobloop`: first run failed with `S110 try-except-pass` in `connectors.py:164`; after switching to `suppress`, `All checks passed!`.
- `python -m ruff format --check backend tests scripts jobloop`: first run reported `tests/test_connectors.py` would be reformatted; after `python -m ruff format backend/app/connectors.py tests/test_connectors.py`, `200 files already formatted`.
- `python scripts/secret_scan.py backend/app/connectors.py tests/test_connectors.py`: `Offline secret scan: 0 findings` (exit 0).
- `git status --short`: only `backend/app/connectors.py` and `tests/test_connectors.py` modified.

STATUS
ready-for-review

### Controller gates

- `scope`: green
- `task-verification`: green
- `python-lint`: green
- `python-format`: green
- `secret-scan`: green

## REVIEW by agy/gemini-4-argon-low (2026-11-26T11:59:48+09:00)

VERDICT
- `APPROVED`

FINDINGS
- none

UNVERIFIED
- Required hosted CI and merge-gate checks were not verified in this local read-only review context.
