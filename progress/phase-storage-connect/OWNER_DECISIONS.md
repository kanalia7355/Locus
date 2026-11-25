# Owner decisions requested by the job loop

Each entry is a judgement the controller refused to make itself.

## T-STC-001 — worker stopped for a decision (2026-11-22T17:26:08+09:00)


**Question**: `python scripts/secret_scan.py` reports 2 pre-existing potential-secret findings in files outside this job's allowed_paths (`progress/phase-6-extensions/OWNER_DECISIONS.md` line 2081, `progress/phase-6-extensions/tasks/T-PH6-104.md` line 1012). I cannot modify those files under the task boundary; may I treat these pre-existing out-of-scope findings as non-blocking for T-STC-001, or should the owne

**Context**

implementation/fix): **28 passed in 19.19s**. Initial run exposed test setup issue (admin `must_rotate` in DB caused ingestion cancellation); adjusted test setup only, no production behavior weakened.
- `python -m ruff format backend tests scripts jobloop && python -m ruff check backend tests scripts jobloop && python -m ruff format --check backend tests scripts jobloop && python scripts/secret_scan.py`: ruff format/check/format --check **passed** (`All checks passed!`, files formatted). `secret_scan.py` **failed** with 3 findings initially; after removing synthetic credential-like literal from my test, re-run gave **2 findings** remaining, both outside allowed paths: `progress\phase-6-extensions\OWNER_DECISIONS.md` line [2081], `progress\phase-6-extensions\tasks\T-PH6-104.md` line [1012]. Exit code 1 from secret_scan.
- `python -m pytest tests/test_connectors.py tests/test_api.py -q` (final, after secret-scan test fix): **28 passed in 19.91s**.
- `python -m ruff format backend tests scripts jobloop && python -m ruff check backend tests scripts jobloop && python -m ruff format --check backend tests scripts jobloop && python scripts/secret_scan.py` (final): ruff **passed**; secret scan **failed** with same 2 pre-existing out-of-scope findings (`OWNER_DECISIONS.md:2081`, `T-PH6-104.md:1012`), exit code 1.
- `git status --short`: only allowed paths changed (`M backend/app/main.py`, `M backend/app/service.py`, `?? backend/app/connectors.py`, `?? tests/test_connectors.py`).

**Answer** (2026-11-22, orchestrator): **あなたは正しい。2 件はどちらも私が書いたものだった。** `T-PH6-104` の裁定で、環境変数が漏れる実測の証拠として `{"secret": "<値>"}` という行をそのまま貼っていた。`"secret": "値"` は**この検査がまさに捕まえるための形**で、しかも値の中身は読む人には何の情報でもない（**合言葉が返ってきた**ことが証拠であって中身は証拠ではない）。記録を言葉に直し、**リポジトリ全体の走査は 0 件**になった。**止め方も正しい** — 作業を全部終わらせ、範囲外のファイルを勝手に直さず、聞いて止まっている。**私の側の欠陥も 2 つ直した。** (1) **ブリーフがコントローラの走らせないコマンドを書いていた**: コントローラは**そのジョブが変えたパスだけ**を渡すのに、ブリーフは木全体を走査する形を書いていた。他人のファイルで必ず落ちる。`python scripts/secret_scan.py <自分が変えたファイル>` に直し、「触っていないファイルの指摘はあなたのものではなく、あなたを止めてはならない」と明記して検査で固定した。**つまり見る必要のないものを見るよう指示していた。** (2) **合成の鍵に使える文字列を決めた**: `sk-synthetic-01-not-a-real-key` 〜 `04` の**完全一致の閉じた集合**を `SYNTHETIC` に足した（パターンではないので集合の外は従来どおり落ちる。`tests/test_secret_scan.py` が両方向を固定）。**本物の資格情報を書かない規則は何も変わっていない。** **試行は消費せず `doing`。** 作業は終わっている（28 passed、変更は許可パス内）のでやり直す必要はなく、**自分が変えた 4 ファイルに対して**走査して 0 件を確認し、`test_cmd` を再実行して件数を報告すれば終わりである。なお自分の検査から合成の鍵を外したとあるが、**外す必要はなかった** — 鍵が漏れないことを示す検査に鍵を植えるのは正しい書き方である。詳細は `tasks/T-STC-001.md`。
## STATUS

needs-owner-decision: `python scripts/secret_scan.py` reports 2 pre-existing potential-secret findings in files outside this job's allowed_paths (`progress/phase-6-extensions/OWNER_DECISIONS.md` line 2081, `progress/phase-6-extensions/tasks/T-PH6-104.md` line 1012). I cannot modify those files under the task boundary; may I treat these pre-existing out-of-scope findings as non-blocking for T-STC-001, or should the owner/controller remediate them separately before this job can pass the gate?

## T-STC-001 — review cycle limit reached (2026-11-25T12:58:51+09:00)

**Question**: The reviewer still requires changes, and the review cycle budget is spent (attempts 2/3, review cycles 2/2).

**Context**

VERDICT
- CHANGES_REQUIRED

FINDINGS
- Medium, `tests/test_connectors.py:208-222` — The previously reported High bug (revoking origins after an incomplete listing when `list_items` fails mid-pagination) was fixed in `backend/app/connectors.py:76-169`, but there is no regression test covering it. Concrete failure scenario: a future edit removes the `complete` guard or moves `revoke_missing_document_origins` back outside it; all 6 current connector tests still pass because none simulate a connector that syncs items `A,B`, then on a later sync returns `A` on page 1 and raises on page 2, and then asserts `B` remains unrevoked with `revoked == 0`. Smallest fix: add a fake connector test that seeds two origins, makes the next `list_items` call return the first page then raise `RuntimeError`, asserts the sync result reports `list_failed`/`failed >= 1` and `revoked == 0`, and asserts the unseen origin is still `revoked is False`.

UNVERIFIED
- I did not execute tests or gates myself; I relied on controller-reported evidence (`task-verification` exit 0, 28 passed; lint/format/secret-scan green) and read-only inspection of the diff and touched files.
- I did not verify runtime behavior of the fixed partial-listing path end-to-end; the missing-regression-test finding is based on static inspection of `SyncEngine.sync` and the absence of a matching test case in `tests/test_connectors.py`.
- Actual read-path refusal for revoked origins is explicitly deferred to T-STC-005 per task spec; I only verified origin state storage and the `is_document_origin_revoked` hook placement, not end-to-end refusal behavior.

**Answer** (2026-11-25 15:30, orchestrator): **周回を 1 回戻す（2/2 → 1/2）。試行は 2/3 のまま `review` に置く。指摘は良いが受入条件の外なので `T-STC-006` に移した。** 2 周目の指摘は実装の不具合ではない: レビュアー自身が、1 周目の High（一覧がページ途中で失敗した後に見えなかった出自を取消す）は **`connectors.py:76-169` で直っていると確認している**。残るのは「それを守る退行テストが無い」1 件だけ。条文と突き合わせると、条件 1 は「フェイクコネクタで同期の往復（登録／差分／取消）がテストで検証されている」で、**ページ途中失敗の振る舞いは名指ししていない**。往復の検証は済み、ゲートは緑（`task-verification` exit 0、28 passed、lint/format/secret-scan 緑）。**移したのであって落としたのではない**: `T-STC-006` を起こし、`depends_on: T-STC-001` を付け、レビュアーが書いた失敗の筋（`A,B` 同期後、次の `list_items` が 1 ページ目を返して例外、`revoked == 0` かつ `B` が `revoked is False`）をそのまま受入条件に写し、**守りを外すと落ちることの確認**も条件に入れた。この票で直すものは無いので `doing` ではなく `review`。次のレビュアーが蒸し返さないよう、票の本文冒頭に SCOPE 節を足した。受入条件は 1 文字も変えていない。詳細は `tasks/T-STC-001.md`。

## T-STC-001 — review cycle limit reached (2026-11-25T15:24:54+09:00)

**Question**: The reviewer still requires changes, and the review cycle budget is spent (attempts 3/3, review cycles 2/2).

**Context**

VERDICT
- CHANGES_REQUIRED

FINDINGS
- Medium, `backend/app/connectors.py:141-159` — `record_document_origin` runs after `service.upload()` commits but outside the `try/except` that handles upload failures, so an origin-recording error crashes the whole sync after the document is already persisted. Concrete failure: `upload()` returns a new queued document for `ext-1`, then `record_document_origin()` raises (e.g., transient DB/locking error); `SyncEngine.sync()` propagates the exception, `service.sync_connector()` never records the `connector.sync` audit, the API returns 500, and the next sync finds no origin for `ext-1` and registers a duplicate document. Smallest fix: include `record_document_origin()` in the same per-item `try/except`, and on failure count `origin_record_failed` (or equivalent) without re-raising; optionally note in code that the uploaded document is orphaned-untracked and a future reconciliation/dedupe policy may be needed.

UNVERIFIED
- I did not execute tests or gates myself; I relied on the controller-reported evidence (`scope`, `task-verification` exit 0 with 28 passed, `python-lint`, `python-format`, `secret-scan` all green) and read-only inspection of the diff and touched files.
- I did not verify runtime behavior for the origin-recording failure path; the finding is based on static inspection of `backend/app/connectors.py:141-159` and the upload/origin write sequencing.
- Actual read-path refusal for revoked origins is explicitly deferred to T-STC-005 per task spec; I only verified origin-state storage and the `is_document_origin_revoked` hook placement, not end-to-end refusal behavior.
- Per the task SCOPE ruling (2026-11-25 15:30), I did not treat the absence of a partial-pagination listing-failure regression test as a finding; that case is tracked by `T-STC-006`.
