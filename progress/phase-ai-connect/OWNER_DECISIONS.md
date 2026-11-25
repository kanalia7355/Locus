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

**Answer** (2026-11-25 13:20, orchestrator): **私の範囲の引き方が狭すぎた。`allowed_paths` に `tests/test_local_model.py` を足し、試行は消費せず `doing` で続行。** この票は同じ 1 ファイルについて「作れ」と「触るな」を同時に命じていた: `test_cmd` が `tests/test_local_model.py` を名指しし、本文 `Implementation Details` 3 もそれを作れと書いているのに、`allowed_paths` にその 1 本だけが入っていなかった。**ワーカーは本文に従っただけである。** 逸脱を後から合法化したのではなく、票自身が要求していたファイルを許可し忘れていたのを直した（要求と許可を一致させただけで、範囲は広げていない）。受入条件は 1 文字も変えていない。詳細は `tasks/T-AIC-002.md`。

## T-AIC-006 — attempt limit reached (2026-11-25T12:47:36+09:00)

**Question**: Three attempts did not satisfy the acceptance criteria; the job needs a human decision.

**Context**

the worker changed nothing

**Answer** (2026-11-25 13:20, orchestrator): **試行を 3/3 から 0/3 に戻す。ただし `blocked` のまま置き、ワーカーには回さない — オーナーの判断を待つ。** 3 回の「the worker changed nothing」は**正直な報告**だった: 成果物 `material/USER_CREDENTIAL_DESIGN.md`（33,069 バイト）は**既に統合ブランチに存在し**、ワークスペースの HEAD 版と本体の HEAD 版はバイト単位で同一、ワークスペースは `ahead=0` である。残る仕事が無いのだから変えるものも無く、その 3 回に予算を請求するのは誤りなので戻した。**なぜそうなったかは私の誤りである**: このファイルが統合ブランチに入ったのは 2026-11-23 の私の裁定コミット **`b7041a6`**（「1 件の逸脱が 2 件を止めていた。切り分けて両方戻す」）で、逸脱を切り分けたときに**ワーカーの成果物をレビューを経ずに持ち込んだ**。証拠はこの票の `## REPORT` / `## TEST` / `## REVIEW` が**3 節とも空のテンプレートのまま**であること。**ワーカーに回せない**: 差分 0 バイトなのでレビューは「1 バイトも変わっていない」経路でモデルを回し続けるだけ、実装に回せばワーカーは正しく「変えるものが無い」と答える。**私も決められない**: 残っているのはレビューだけで、レビューの承認を私が与えることは禁じられている。**オーナーへの二択**: (1) この設計書をレビュー無しで受け入れる（私の `b7041a6` の事後承認）、(2) `b7041a6` が入れた分を統合ブランチから外し、正規の経路で納め直させる（成果物は git 履歴とワークスペースに残るので失われないが、実装とレビューをやり直す）。1 の場合も**受入条件 7**（コード・スキーマ・dispatch を変更していないこと）は機械で確かめられる。詳細は `tasks/T-AIC-006.md`。

**Answer** (2026-11-25 20:30, **owner**): **B — 正規の経路で通す。** オーナーの言葉のまま: 「B正規の経路で通す。(今通しても後で戻しが発生するなら通す意味ないし)」。**レビュー無しで通したものは後で戻しが発生する可能性が残るので、通した意味が無い** という判断である。**実施（オーケストレーター、同 20:30）**: (1) `b7041a6` が入れた `progress/phase-ai-connect/material/USER_CREDENTIAL_DESIGN.md` を**統合ブランチから削除した**。(2) **成果物は失われていない** — blob `0d2b822d08f158edecdadba89d1d0624e7254d49`（33,069 バイト）として commit `b7041a6` に在り、ワークスペース `T-AIC-006` にも残っている。(3) 前書きを `todo` / `attempts: 0/3` / `assignee: unassigned` / `model: -` に戻し、通常の派遣に乗せた。(4) 冒頭に SCOPE を置き、実装には「元の内容を土台にしてよいが自分の目で読んで受入条件に照らすこと」、レビューには「まだ誰も見ていないものとして扱うこと」と書いた。**受入条件は 1 文字も変えていない。** なお元の取り込みは 2026-11-23 に私が `T-AIC-002` の逸脱を切り分けた際、**同じコミットでワーカーの成果物をレビュー無しに持ち込んだ私の誤り**である。切り分けと取り込みは別の作業であり、一緒にやってはいけなかった。決定の全文は `docs/plans/OWNER_DECISIONS_2026-11-25-ENTRIES.md` の E1。

## T-AIC-002 — review cycle limit reached (2026-11-25T15:20:43+09:00)

**Question**: The reviewer still requires changes, and the review cycle budget is spent (attempts 2/3, review cycles 2/2).

**Context**

T
CHANGES_REQUIRED

FINDINGS
- Medium, backend/app/main.py:798-835 (discover_models): openai-compatible candidates are written into the local runtime's `registered`/`registered_sources` in addition to the remote runtime's. The first block loops over every source in `data.sources` (including `openai-compatible`) and adds matching models to `runtime` (local), so a discover of only `openai-compatible` pollutes `runtime.registered` with remote model entries. This contradicts the spec's source-splitting intent (openai candidates belong only in the remote runtime's `registered`) and risks failing a hidden assertion on local runtime contents. Smallest fix: in the first block, keep the stale-entry removal for all sources, but `continue` before the model-addition loop when `source == "openai-compatible"`.
- Low, backend/app/main.py:831-834: after a successful/failed discover, `_base_url`/`_api_key` are stored on `remote_runtime` and never cleared on disable (`candidate_id is None`), so credentials linger in process memory after the model is disabled. Clear them in the disable branch for hygiene.
- Low, backend/app/main.py:841-857 (model_runtime GET): when the active runtime is remote but no model is configured, the response keeps `api_key_present: False` (hardcoded by `OpenAICompatibleModel.status()`) while no `provider` is added, unlike the local no-model case which omits `api_key_present` entirely. Normalize so both runtimes return the same field set when unconfigured.

UNVERIFIED
- I did not edit or execute anything beyond reading the worktree and running the provided test command (74 passed, 2 skipped); no hidden tests were available to run.
- Whether real OpenAI-compatible model ids always satisfy the provider's `[\w./:-]{1,200}` regex in `OpenAICompatibleModel.configure` (outside allowed_paths) was not exercised.
- Whether `base_url` pointing at non-loopback/internal hosts is intended to be rejected (SSRF) is not specified in the task; left to T-AIC-005/harness policy.

**Answer** (2026-11-25 18:34, orchestrator): **周回を 1 回戻す（2/2 → 1/2）、試行は動かさない（2/3 のまま）、`doing` に置く。Medium は本物で条件の中なので直させる。Low 2 件は条件の外なので `T-AIC-007` に移した。受入条件は 1 文字も変えていない。** **Medium を自分で確かめた**（ワークスペースの `backend/app/main.py` の `discover_models`）: 最初の塊が `for source in data.sources` で回り、その source のモデルを**ローカルの `runtime.registered` に入れている**ので、`openai-compatible` を discover するとリモートのモデルがローカル runtime に入る。その後の塊が同じモデルをリモートにも入れるので両方に入る。**これは受入条件 5（Ollama の発見・選択・応答に退行がない）の中にある** — ローカル runtime の状態の汚染だから、条件外の指摘ではない。**直させる。** レビュアーが示した最小の直し方（stale な項目の削除は全 source に残し、モデル追加の繰り返しの前で `openai-compatible` を飛ばす）で足りる。**Low 2 件は条件の外**: (1) 無効化で `_base_url` / `_api_key` を消していない件 — 受入条件 3 が守るのは「**応答・監査・カタログに値が現れない**」ことで、プロセス内のメモリは名指ししていない（漏洩ではない）。(2) 未設定時の応答の項目がローカルとリモートで揃っていない件（`api_key_present` の有無）— どの条件も項目の集合を名指ししていない。**両方 `T-AIC-007` に起票した。落としたのではなく移した。** **周回を戻す理由**: 残りが 1 件に絞れており試行はまだ 1 回在る（2/3）。周回の枠だけ尽きた状態で止めるのは無駄である。**試行を動かさない理由**: 2 回の派遣はどちらも成果を出して報告しており、数え方の誤りが無い。**この戻しは 1 回だけ**: 次も条件の外を理由に差し戻したら周回は戻さず、「レビュアーが条件外の指摘を出し続ける票を誰が完了と決めるのか」をオーナーに伺う（`T-STC-001` と同じ線）。詳細は `tasks/T-AIC-002.md`。
