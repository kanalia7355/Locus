# Owner decisions requested by the job loop

Each entry is a judgement the controller refused to make itself.

## T-PH7-201 — out-of-scope change (2026-11-19T23:14:37+09:00)





**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job. — 11 path(s) the worker wrote outside its scope: all_tests.txt, ruff1.txt, ruff2.txt, ruff_check.txt, ruff_format.txt, secret1.txt…. Decide whether the job's scope was drawn too narrowly, or whether the worker should not have written them.

**Context**

outside allowed_paths: ['all_tests.txt', 'ruff1.txt', 'ruff2.txt', 'ruff_check.txt', 'ruff_format.txt', 'secret1.txt', 'secret_scan.txt', 'test_output.txt', 'test_output2.txt', 'test_output3.txt', 'verify1.txt']

**Answer** (2026-11-20, orchestrator): スコープは狭くない。許可パスは広げない。
必要だったパスはすべて許可済みで、実際の成果物（`backend/app/connectors/`、
`tests/test_storage_connectors.py`、`main.py`、`service.py`）は全部その中にある。
11 個のファイルはコマンド出力のリダイレクト先で、1 つも必要なかった。
ただし**同じ失敗の 2 回目**（`T-PH6-108` が 19 個）。私がそのとき 1 票の受入条件にだけ
書いて**常設の指示を直さなかった**ので別フェーズで再発した。`jobloop/prompts.py` の
`BOUNDARY` に「コマンドの出力をファイルに流して読むな」を実例付きで明記した。
試行は戻さない（逸脱は逸脱。残り 2 回）。11 個は削除し、許可パス内の成果物は
残したので続きから進められる。`doing` に戻した。詳細は `tasks/T-PH7-201.md`。


## T-PH7-211 — worker wrote outside its workspace (2026-11-20T00:11:06+09:00)





**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/nemotron-3.5-lightning-free
workspace=C:\Users\hirot\.jobloop-Locus\workspaces\T-PH7-211

**Answer** (2026-11-20, orchestrator): 誤検知。原因は私で、派遣中にメインチェックアウトで
コミットし、`.jobloop/orchestrator-busy` を判定の直前に外してしまった。
ワーカーはメインチェックアウトに何も書いていない。試行は 0 のまま `doing` に戻した。
**止めた本当の原因は別に 2 つあった**: (1) 出力を 15 個のファイルに流していた
（`T-PH6-108` の 19 個、`T-PH7-201` の 11 個に続く 3 回目。常設の指示を直したのは今日なので
このワーカーは古い指示で走っていた）、(2) **時間切れの後もワーカーが生き残って
ワークスペースに書き続け、継承した標準出力を握ってコントローラを塞いでいた**
（90 分予算のサイクルが 114 分に伸び、その間 supervisor は無言だった）。
`jobloop/worker.py` を直してプロセス木ごと落とすようにした。詳細は `tasks/T-PH7-211.md`。


## T-PH7-201 — out-of-scope change (2026-11-20T01:19:16+09:00)





**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job. — 2 path(s) the worker wrote outside its scope: test_output.txt, test_output_raw.txt. Decide whether the job's scope was drawn too narrowly, or whether the worker should not have written them.

**Context**

outside allowed_paths: ['test_output.txt', 'test_output_raw.txt']

**Answer** (2026-11-20, orchestrator): 2 個とも出力のリダイレクト先。前回の裁定どおり
逸脱だが、brief に明記した後もまた起きたので**仕組みで止める**ことにした
（`T-PH6-116` の回答に詳細）。削除し、許可パス内の成果物は残して `review` に戻した。
試行は消費しない。詳細は `tasks/T-PH7-201.md`。
## T-PH7-211 — attempt limit reached (2026-11-20T03:09:59+09:00)





**Question**: Three attempts did not satisfy the acceptance criteria; the job needs a human decision.

**Context**

unavailable: {"type": "provider.invalid-request", "message": "Upstream request failed: Endpoint is unavailable.", "status": 404, "response": {"body": "{\"error\":{\"type\":\"server_error\",\"message\":\"Upstream request failed: Endpoint is unavailable.\"}}"}}

**Answer** (2026-11-20, orchestrator): 試行は 1 度も使われていない。3 回とも
`provider.invalid-request / 404 Upstream request failed: Endpoint is unavailable`、
つまり**無料エンドポイントが落ちていてモデルはジョブを受け取っていない**。
03:08〜03:16 の 8 分で 5 件が未着手から `attempts 3/3` になった
（`T-PH6-104` `T-PH7-211` `T-PH7-221` `T-PH7-223` `T-PH8-304`）。
枠切れを試行に数えないのと同じ理由で供給側の障害も試行ではない。
`Ending.OUTAGE` を追加し、試行を消費せず冷却して回すようにした。
5 件すべて試行 0 に戻し `todo` に戻した。受入条件・許可パスは無変更。
## T-PH7-221 — attempt limit reached (2026-11-20T03:10:22+09:00)





**Question**: Three attempts did not satisfy the acceptance criteria; the job needs a human decision.

**Context**

unavailable: {"type": "provider.invalid-request", "message": "Upstream request failed: Endpoint is unavailable.", "status": 404, "response": {"body": "{\"error\":{\"type\":\"server_error\",\"message\":\"Upstream request failed: Endpoint is unavailable.\"}}"}}

**Answer** (2026-11-20, orchestrator): 試行は 1 度も使われていない。3 回とも
`provider.invalid-request / 404 Upstream request failed: Endpoint is unavailable`、
つまり**無料エンドポイントが落ちていてモデルはジョブを受け取っていない**。
03:08〜03:16 の 8 分で 5 件が未着手から `attempts 3/3` になった
（`T-PH6-104` `T-PH7-211` `T-PH7-221` `T-PH7-223` `T-PH8-304`）。
枠切れを試行に数えないのと同じ理由で供給側の障害も試行ではない。
`Ending.OUTAGE` を追加し、試行を消費せず冷却して回すようにした。
5 件すべて試行 0 に戻し `todo` に戻した。受入条件・許可パスは無変更。
## T-PH7-223 — attempt limit reached (2026-11-20T03:16:24+09:00)





**Question**: Three attempts did not satisfy the acceptance criteria; the job needs a human decision.

**Context**

unavailable: {"type": "provider.invalid-request", "message": "Upstream request failed: Endpoint is unavailable.", "status": 404, "response": {"body": "{\"error\":{\"type\":\"server_error\",\"message\":\"Upstream request failed: Endpoint is unavailable.\"}}"}}

**Answer** (2026-11-20, orchestrator): 試行は 1 度も使われていない。3 回とも
`provider.invalid-request / 404 Upstream request failed: Endpoint is unavailable`、
つまり**無料エンドポイントが落ちていてモデルはジョブを受け取っていない**。
03:08〜03:16 の 8 分で 5 件が未着手から `attempts 3/3` になった
（`T-PH6-104` `T-PH7-211` `T-PH7-221` `T-PH7-223` `T-PH8-304`）。
枠切れを試行に数えないのと同じ理由で供給側の障害も試行ではない。
`Ending.OUTAGE` を追加し、試行を消費せず冷却して回すようにした。
5 件すべて試行 0 に戻し `todo` に戻した。受入条件・許可パスは無変更。

## T-PH7-201 — integration branch is dirty (2026-11-21T00:20:41+09:00)



**Question**: The main checkout has uncommitted changes, so the reviewed commit was not merged. Decide how to integrate it.

**Context**

commit=e6f9287d5e9e078f748cc14af8f336beffc9a893
 M docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html
M  frontend/e2e/a11y.spec.ts
UU frontend/src/App.test.tsx
UU frontend/src/App.tsx
M  frontend/src/styles.css
 M progress/phase-6-extensions/OWNER_DECISIONS.md
 M progress/phase-6-extensions/tasks/T-PH6-116.md
 M progress/phase-6-extensions/tasks/T-PH6-126.md
 M progress/phase-7-production/tasks/T-PH7-201.md
 M progress/phase-8-runner/tasks/T-PH8-301.md
 M progress/phase-8-runner/tasks/T-PH8-302.md
 M progress/phase-8-runner/tasks/T-PH8-303.md

**Answer** (2026-11-21, jobloop diagnose): この停止は**ループ側の欠陥**が原因で、その欠陥は既に直っている — every phase's records count as the loop's own bookkeeping。停止の時刻（2026-11-21T04:00）は修正より前なので、判断を覆したのではなく、**原因が無くなったので再開する**という記録である。欠陥が消費した試行 1 回分だけを戻す（それ以上は戻さない）。受入条件・許可パスは変更していない。
## T-PH7-211 — out-of-scope change (2026-11-21T02:32:28+09:00)



**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job. — 12 path(s) the worker wrote outside its scope: test_conn.py, test_conn2.py, test_conn3.py, test_cursor.py, test_cursor2.py, test_cursor3.py…. Decide whether the job's scope was drawn too narrowly, or whether the worker should not have written them.

**Context**

outside allowed_paths: ['test_conn.py', 'test_conn2.py', 'test_conn3.py', 'test_cursor.py', 'test_cursor2.py', 'test_cursor3.py', 'test_cursor4.py', 'test_cursor5.py', 'test_cursor6.py', 'test_patch.py', 'test_patch2.py', 'test_prop_check.py']

**Answer** (2026-11-21, jobloop diagnose): この停止は**ループ側の欠陥**が原因で、その欠陥は既に直っている — scratch files are swept by `gates.litter`。停止の時刻（2026-11-21T03:32）は修正より前なので、判断を覆したのではなく、**原因が無くなったので再開する**という記録である。欠陥が消費した試行 1 回分だけを戻す（それ以上は戻さない）。受入条件・許可パスは変更していない。
## T-PH7-221 — out-of-scope change (2026-11-21T03:24:22+09:00)



**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job. — 1 path(s) the worker wrote outside its scope: debug_test.py. Decide whether the job's scope was drawn too narrowly, or whether the worker should not have written them.

**Context**

outside allowed_paths: ['debug_test.py']

**Answer** (2026-11-21, jobloop diagnose): この停止は**ループ側の欠陥**が原因で、その欠陥は既に直っている — scratch files are swept by `gates.litter`。停止の時刻（2026-11-21T03:32）は修正より前なので、判断を覆したのではなく、**原因が無くなったので再開する**という記録である。欠陥が消費した試行 1 回分だけを戻す（それ以上は戻さない）。受入条件・許可パスは変更していない。
## T-PH7-223 — integration branch is dirty (2026-11-21T04:00:20+09:00)



**Question**: The main checkout has uncommitted changes, so the reviewed commit was not merged. Decide how to integrate it.

**Context**

commit=950c56ce07541eb16c15e4bbf6aa52212e226b37
 M docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html
M  frontend/e2e/a11y.spec.ts
UU frontend/src/App.test.tsx
UU frontend/src/App.tsx
M  frontend/src/styles.css
 M progress/phase-6-extensions/OWNER_DECISIONS.md
 M progress/phase-6-extensions/tasks/T-PH6-104.md
 M progress/phase-6-extensions/tasks/T-PH6-116.md
 M progress/phase-6-extensions/tasks/T-PH6-126.md
 M progress/phase-7-production/OWNER_DECISIONS.md
 M progress/phase-7-production/tasks/T-PH7-201.md
 M progress/phase-7-production/tasks/T-PH7-211.md
 M progress/phase-7-production/tasks/T-PH7-221.md
 M progress/phase-7-production/tasks/T-PH7-223.md
 M progress/phase-8-runner/OWNER_DECISIONS.md
 M progress/phase-8-runner/tasks/T-PH8-301.md
 M progress/phase-8-runner/tasks/T-PH8-302.md
 M progress/phase-8-runner/tasks/T-PH8-303.md
 M progress/phase-8-runner/tasks/T-PH8-304.md

**Answer** (2026-11-21, jobloop diagnose): この停止は**ループ側の欠陥**が原因で、その欠陥は既に直っている — every phase's records count as the loop's own bookkeeping。停止の時刻（2026-11-21T04:00）は修正より前なので、判断を覆したのではなく、**原因が無くなったので再開する**という記録である。欠陥が消費した試行 1 回分だけを戻す（それ以上は戻さない）。受入条件・許可パスは変更していない。
