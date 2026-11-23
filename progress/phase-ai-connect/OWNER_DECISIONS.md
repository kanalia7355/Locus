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
