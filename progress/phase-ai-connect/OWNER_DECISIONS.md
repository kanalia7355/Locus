# Owner decisions requested by the job loop

Each entry is a judgement the controller refused to make itself.

## T-AIC-005 — integration branch is dirty (2026-11-23T21:16:14+09:00)

**Question**: The main checkout has uncommitted changes, so the reviewed commit was not merged. Decide how to integrate it.

**Context**

commit=a14b69c5b0c9733eee67b091180b03b510166ec2
 M docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html
 M progress/phase-7-production/OWNER_DECISIONS.md
 M progress/phase-7-production/tasks/T-PH7-202.md
 M progress/phase-7-production/tasks/T-PH7-211.md
 M progress/phase-ai-connect/tasks/T-AIC-005.md
?? tests/test_storage_seam.py
**Answer** (2026-11-23 21:25): 退行ではない。`foreign` は 1 件
（`?? tests/test_storage_seam.py` = `T-PH7-211` のワーカーが本体に書いた製品ファイル）で、
記録の扱い（`progress/` と平易化ページをループ自身のものとする対処）は正しく働いている。
停止記録が未コミットの全行を印字するので退行のように見えるだけである。
この票の `a14b69c` は許可パス 2 件とちょうど一致しレビュー済み。
逸脱ファイルを退避して外したので `foreign` は 0 件。
**試行は消費せず `review` に戻す**（成果はコミット済みなので `doing` ではない）。
読み分けを機械化する分は `T-PH9-403`。

## T-AIC-005 — integration branch is dirty (2026-11-23T23:16:11+09:00)

**Question**: The main checkout has uncommitted changes, so the reviewed commit was not merged. Decide how to integrate it.

**Context**

commit=a14b69c5b0c9733eee67b091180b03b510166ec2
 M backend/app/main.py
 M docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html
 M progress/phase-6-extensions/OWNER_DECISIONS.md
 M progress/phase-6-extensions/tasks/T-PH6-104.md
 M progress/phase-7-production/OWNER_DECISIONS.md
 M progress/phase-7-production/tasks/T-PH7-211.md
 M progress/phase-7-production/tasks/T-PH7-223.md
 M progress/phase-9-loop-health/OWNER_DECISIONS.md
 M progress/phase-9-loop-health/tasks/T-PH9-402.md
 M progress/phase-9-loop-health/tasks/T-PH9-403.md
 M progress/phase-ai-connect/tasks/T-AIC-005.md
 M scripts/shift_check.py
 M tests/test_api.py
 M tests/test_shift_check.py
?? backend/app/deployment.py
?? tests/test_production_startup.py

**Answer** (2026-11-23 23:30, orchestrator): 21:16 と同じ形で、この票は今日 2 回とも無実である。`foreign` は他票（`T-PH9-402`・`T-PH7-223`）が本体に書いた製品コード。`a14b69c` は許可パス 2 件とちょうど一致しレビュー済み。本体は綺麗にした。**試行は消費せず `review`。** 原因と対処は `T-PH9-406`。詳細は `tasks/T-AIC-005.md`。

## T-AIC-002 — out-of-scope change (2026-11-25T12:43:02+09:00)

**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job. — 1 path(s) the worker wrote outside its scope: tests/test_local_model.py. Decide whether the job's scope was drawn too narrowly, or whether the worker should not have written them.

**Context**

outside allowed_paths: ['tests/test_local_model.py']

## T-AIC-006 — attempt limit reached (2026-11-25T12:47:36+09:00)

**Question**: Three attempts did not satisfy the acceptance criteria; the job needs a human decision.

**Context**

the worker changed nothing
