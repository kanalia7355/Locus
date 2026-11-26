# Owner decisions requested by the job loop

Each entry is a judgement the controller refused to make itself.

## T-PH9-402 — worker wrote outside its workspace (2026-11-23T21:32:52+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=<workspaces>\workspaces\T-PH9-402
marker=.\.jobloop\orchestrator-busy present=False
appeared:
 M scripts/shift_check.py
 M tests/test_shift_check.py


**Answer** (2026-11-23 22:50, orchestrator): **ワークスペースが完全に空で、作業の 100% が本体チェックアウトにあった**（`git status` が 1 行も無く `merge-base..HEAD` も 0 件）。零れたのではなく最初から本体で作業していた。既知の経路は潰して確認した: ジョブ文に本体の絶対パスは 0 件（2026-11-16 の経路ではない）、ワークスペースに自分の票はある、土台も本体と同じ `b7041a6`。**原因は未特定。** 本体の差分を**この票の許可パスだけ**（`scripts/shift_check.py`, `tests/test_shift_check.py`）で切り出してこの票のワークスペースへ適用し（同じ土台なので `git apply` がそのまま通った）、本体は戻した。**消していない。** 私はコードを 1 行も触っていないので、ゲートと独立レビューはそのまま通す。**試行は消費せず `review` に戻す**（再開は試行を使わずゲートを回し、落ちれば `doing` に戻る）。モデルの偏り（`iceman-free` が封じ込め停止 8 件）は `T-PH9-404` に起票。詳細は `tasks/T-PH9-402.md`。

## T-PH9-403 — worker wrote outside its workspace (2026-11-23T21:41:46+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=<workspaces>\workspaces\T-PH9-403
marker=.\.jobloop\orchestrator-busy present=False
appeared:
 M jobloop/controller.py
 M jobloop/diagnose.py
 M tests/test_diagnose.py
 M tests/test_jobloop.py

**Answer** (2026-11-23 22:50, orchestrator): `T-PH9-402` と同じ形で、同じ扱いにした。**ワークスペースは完全に空**で、作業の 100%（`jobloop/controller.py`, `jobloop/diagnose.py`, `tests/test_jobloop.py`, `tests/test_diagnose.py`）が本体にあった。許可パスで機械的に切り分けたので `T-PH9-402` の分と混ざっていない。本体は戻し、作業はこの票のワークスペースへ移送した。**試行は消費せず `review` に戻す。** 原因は未特定で、計測は `T-PH9-404`。詳細は `tasks/T-PH9-403.md`。

## T-PH9-402 — worker wrote outside its workspace (2026-11-23T23:03:23+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=<workspaces>\workspaces\T-PH9-402
marker=.\.jobloop\orchestrator-busy present=False
appeared:
 M backend/app/main.py
 M scripts/shift_check.py
 M tests/test_shift_check.py
?? backend/app/deployment.py


**Answer** (2026-11-23 23:30, orchestrator): `appeared` の 4 行のうち `backend/app/main.py` と `backend/app/deployment.py` は **`T-PH7-223` の許可パス**で、この票のものではない（1 つのチェックアウトを順に使うので前の票の汚れが積まれる）。この票の 2 ファイルは、22:50 に移送した分が**ワークスペースに残っている**。本体に再出現した写しは ws 版と食い違っていた（本体 317 行 / ws 319 行）ので**混ぜず**、退避して本体だけ戻した。**試行は消費せず `review`。** 原因は記録が本体の絶対パスを教えていたことで、`T-PH9-406` に起票した。詳細は `tasks/T-PH9-402.md`。

## T-PH9-403 — worker wrote outside its workspace (2026-11-23T23:07:04+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=<workspaces>\workspaces\T-PH9-403
marker=.\.jobloop\orchestrator-busy present=False
appeared:
 M backend/app/main.py
 M tests/test_api.py
?? tests/test_production_startup.py

**Answer** (2026-11-23 23:30, orchestrator): **いま本体にこの票のファイルは 1 つも無い**。22:50 に移送した作業はワークスペースに 4 ファイルとして残っている。この停止は同じサイクル中に別の票が汚した分を拾ったものである。**試行は消費せず `review`。** 原因と対処は `T-PH9-406`。詳細は `tasks/T-PH9-403.md`。

## T-PH9-408 — review cycle limit reached (2026-11-24T11:49:12+09:00)

**Question**: The reviewer still requires changes, and the review cycle budget is spent (attempts 2/3, review cycles 2/2).

**Context**

VERDICT
- CHANGES_REQUIRED

FINDINGS
- Medium, scripts/supervise_loop.py:122-139, `cooldown_wait` does not fully guard corrupted roster state: (a) a non-finite `cooldown_until` (`NaN`/`Infinity`, which `float()` accepts and Python's `json` parser accepts) is not skipped — `remaining <= 0` is False for `NaN`, so the entry yields a `nan` wait that shadows any real earlier cooldown (since `min(backoff, nan) == backoff`), causing the supervisor to miss a wake-up for a model that is actually about to return; (b) a roster file that is not valid UTF-8 raises `UnicodeDecodeError` out of `Roster._state()` (which only catches `OSError`/`JSONDecodeError`) and crashes the idle branch. Fix: wrap `roster._state()` in `try/except Exception` (return `None` on failure) and skip any entry whose `until` is not finite (e.g. `if not math.isfinite(until): continue`).

UNVERIFIED
- Whether `jobloop.cli.installed_models()` (spawns `opencode models`, up to 180s) on every idle cycle is acceptable latency in the target environment; not exercised by the test suite, which patches it. Also, I did not re-run the suite in the read-only review context; relied on the controller's recorded gate results (67 passed, lint/format/secret-scan green).


**Answer** (2026-11-24 12:30, orchestrator): VERDICT を自分で読み、指摘を実装で確かめた。**2 件とも本物**（`NaN` の `cooldown_until` が最短の冷却を覆い隠す／`Roster._state()` が `UnicodeDecodeError` を捕まえずアイドル経路が落ちる。`installed_models()` の try/except は `idle_wait` を覆っていない）。**ただしどちらもこの票の受入条件に無い** — 壊れたロスターへの堅牢性を書き落としたのは私である。**`T-PH9-410` に移した（削っていない）。** `UNVERIFIED` の遅延懸念には私が答えた: 照会はアイドル分岐の中だけで、失敗時は通常の待機に落ちるので許容できる。**周回を 1 回戻し（2/2 → 1/2）、試行は動かさず `review` に戻す。** 受入条件は 1 文字も緩めていない。詳細は `tasks/T-PH9-408.md`。

## T-PH9-407 — worker wrote outside its workspace (2026-11-24T11:59:10+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=<workspaces>\workspaces\T-PH9-407
marker=<repo-root>\.jobloop\orchestrator-busy present=False
appeared:
 M scripts/shift_check.py
 M tests/test_shift_check.py

**Answer** (2026-11-24 12:30, orchestrator): `T-PH9-402` / `T-PH9-403` と同じ形で、**ワークスペースは完全に空**（コミット 0・変更 0）、作業の 100% が本体チェックアウトにあった（`scripts/shift_check.py` 本体 336 行 / ws 321 行、`tests/test_shift_check.py` 353 / 282）。原因は `T-PH9-406` に起票済みの経路で、その修正はまだ入っていない。本体の差分をこの票の許可パスだけで切り出してワークスペースへ適用し、本体は戻した。**消していない。コードは 1 行も書いていない。** **試行は消費せず `review`。** 詳細は `tasks/T-PH9-407.md`。

## T-PH9-410 — worker wrote outside its workspace (2026-11-24T12:36:58+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=<workspaces>\workspaces\T-PH9-410
marker=<repo-root>\.jobloop\orchestrator-busy present=False
appeared:
 M jobloop/roster.py
 M scripts/supervise_loop.py
 M tests/test_jobloop.py


**Answer** (2026-11-24 13:30, orchestrator): ワークスペースに変更が 1 件も無く、作業は全部本体にあった。中身で帰属を確かめた（`roster.py` の `except Exception` ＋ stderr 行はこの票の受入条件 2・4、`supervise_loop.py` の `math.isfinite` は受入条件 1）。許可パスだけ切り出してワークスペースへ移送し、本体は戻した。**消していない。コードは書いていない。試行は消費せず `review`。** 詳細は `tasks/T-PH9-410.md`。

## T-PH9-404 — integration branch is dirty (2026-11-24T12:42:21+09:00)

**Question**: The main checkout has uncommitted changes, so the reviewed commit was not merged. Decide how to integrate it.

**Context**

commit=319a089b7037c97e2e7eea40b3a6b57fd4afb3be
foreign (判定に使った未コミットのパス):
 M jobloop/roster.py  → T-PH9-401, T-PH9-404, T-PH9-409, T-PH9-410 の許可パス
 M scripts/supervise_loop.py  → T-PH6-109, T-PH6-113, T-PH6-124, T-PH9-408, T-PH9-410 の許可パス
 M tests/test_jobloop.py  → T-PH6-109, T-PH6-113, T-PH6-124, T-PH6-127, T-PH9-401, T-PH9-403, T-PH9-404, T-PH9-405, T-PH9-406, T-PH9-408, T-PH9-409, T-PH9-410 の許可パス

not used for decision (判定に使っていない: progress/ と平易化ページ):
 M progress/phase-9-loop-health/OWNER_DECISIONS.md
 M progress/phase-9-loop-health/tasks/T-PH9-404.md
 M progress/phase-9-loop-health/tasks/T-PH9-408.md
 M progress/phase-9-loop-health/tasks/T-PH9-410.md


**Answer** (2026-11-24 13:30, orchestrator): この票の落ち度ではない。`foreign` は `T-PH9-410` が本体に書いた `jobloop/roster.py` と `scripts/supervise_loop.py` で、中身が 410 の受入条件そのものだった。この票の成果は無傷（`319a089` が積まれ、レビュー 1 周済み）。**私の計測ミスを記録する**: `git merge-base FETCH_HEAD HEAD` で数えたら `FETCH_HEAD` が無く `HEAD..HEAD` にフォールバックして「コミット 0 件」と出たため、**成果が消えたと誤認しかけた**。黙って 0 を返す数え方は消失と区別できない。本体は綺麗にした。**試行も周回も動かさず `review`。** 詳細は `tasks/T-PH9-404.md`。

## T-PH9-406 — worker wrote outside its workspace (2026-11-24T13:03:48+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=<workspaces>\workspaces\T-PH9-406
marker=<repo-root>\.jobloop\orchestrator-busy present=False
appeared:
 M jobloop/selfrepair.py
 M tests/test_selfrepair.py

**Answer** (2026-11-24 13:30, orchestrator): **スコープを広げた。私の書き落としである。** この票は `redact` の自己修復を直せと要求しているが、`redact` の実体は `jobloop/selfrepair.py` にあり、それを `allowed_paths` に入れていなかった。**変更が必要とするモジュールは「スコープが狭すぎた」側の誤りなので、公開の場で広げる**（`jobloop/selfrepair.py` と `tests/test_selfrepair.py` を追加）。作業は失われていない — ワークスペースの `tests/test_selfrepair.py` は 143 行で本体の写し（81 行）より充実しており、`jobloop/selfrepair.py` は同一だった。本体の写しは退避して外した。**試行は消費せず `review`。** 詳細は `tasks/T-PH9-406.md`。

## T-PH9-410 — worker wrote outside its workspace (2026-11-24T13:47:07+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=<workspaces>\workspaces\T-PH9-410
marker=<repo-root>\.jobloop\orchestrator-busy present=False
appeared:
 M jobloop/roster.py
 M scripts/supervise_loop.py
 M tests/test_jobloop.py


**Answer** (2026-11-24 14:30, orchestrator): 13:30 に移送した作業は**ワークスペースに健在**（`jobloop/roster.py`・`scripts/supervise_loop.py`・`tests/test_jobloop.py` の 3 件）。本体に再び現れた分は **`T-PH9-409` の仕事と同じファイルで重なっていた**ので、混ぜずに本体を戻した（詳細は `tasks/T-PH9-409.md`）。**この票は何も失っていない。試行も周回も動かさず `review`。** なお `T-PH9-406` のワーカーがこの票の受入条件 1・2 と同じ主題の検査を自分のワークスペースに書いてしまっていたので、**この票の検査が正本である**と 406 側に伝えた。詳細は `tasks/T-PH9-410.md`。

## T-PH9-406 — worker stopped for a decision (2026-11-24T13:59:26+09:00)

**Question**: The required `python -m pytest tests/test_jobloop.py tests/test_selfrepair.py -q` still has 3 failures in `tests/test_jobloop.py` because `jobloop/roster.py` raises `UnicodeDecodeError` on non-UTF8 roster files; fixing that requires changing `jobloop/roster.py`, which is outside T-PH9-406 allowed_paths. May I include the minimal `jobloop/roster.py` fix (treat unreadable/non-UTF8 roster state as em

**Context**

_root -q` (workdir `<workspaces>\workspaces\T-PH9-406`)  
  Result: `11 passed in 1.26s`
- `python -m pytest tests/test_jobloop.py tests/test_selfrepair.py -q` (workdir `<workspaces>\workspaces\T-PH9-406`)  
  Result: `3 failed, 78 passed in 20.22s`  
  Failures: `tests/test_jobloop.py::test_idle_wait_skips_nonfinite_cooldown_and_uses_real_one`, `tests/test_jobloop.py::test_roster_state_treats_unreadable_file_as_empty`, `tests/test_jobloop.py::test_unreadable_roster_does_not_crash_idle_wait` — all fail with `UnicodeDecodeError` from `jobloop/roster.py:67` (`Path.read_text(encoding="utf-8")`) when reading a deliberately non-UTF8 roster file.
- `python -m ruff format jobloop/controller.py jobloop/selfrepair.py tests/test_jobloop.py tests/test_selfrepair.py` (workdir `<workspaces>\workspaces\T-PH9-406`)  
  Result: `1 file reformatted, 3 files left unchanged`
- `python -m ruff check backend tests scripts jobloop` (workdir `<workspaces>\workspaces\T-PH9-406`)  
  Result: `All checks passed!`
- `python -m ruff format --check backend tests scripts jobloop` (workdir `<workspaces>\workspaces\T-PH9-406`)  
  Result: `190 files already formatted`
- `python scripts/secret_scan.py jobloop/controller.py jobloop/selfrepair.py tests/test_jobloop.py tests/test_selfrepair.py` (workdir `<workspaces>\workspaces\T-PH9-406`)  
  Result: `Offline secret scan: 0 findings`


**Answer** (2026-11-24 14:30, orchestrator): **いいえ。`jobloop/roster.py` には触らないこと。** よく聞いてくれた（勝手に広げずに止まったのは正しい）。落ちている 3 件は **`T-PH9-410` の受入条件 1・2 と同じ主題**で、410 は `review` にあり既にその修正を持っている。測った結果、3 件は統合ブランチにもこのワークスペースの `HEAD` にも無く、**作業木にだけある**（票の取り違えで書かれた）。**その 3 件をこの票の変更から外すこと。** この票の成果は `jobloop/controller.py`（記録に絶対パスを書かない）と `jobloop/selfrepair.py`（`redact` を書き換える側に倒す）とその検査である。外せば `test_cmd` は通る見込み。通らなければまた聞いてよい。**試行は消費せず `review`。** 詳細は `tasks/T-PH9-406.md`。

## STATUS
needs-owner-decision: The required `python -m pytest tests/test_jobloop.py tests/test_selfrepair.py -q` still has 3 failures in `tests/test_jobloop.py` because `jobloop/roster.py` raises `UnicodeDecodeError` on non-UTF8 roster files; fixing that requires changing `jobloop/roster.py`, which is outside T-PH9-406 allowed_paths. May I include the minimal `jobloop/roster.py` fix (treat unreadable/non-UTF8 roster state as empty and record the fact) so AC5 can pass, or should this be handled as a separate scoped job?

## T-PH9-409 — worker wrote outside its workspace (2026-11-24T14:04:37+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=<workspaces>\workspaces\T-PH9-409
marker=<repo-root>\.jobloop\orchestrator-busy present=False
appeared:
 M jobloop/roster.py
 M tests/test_jobloop.py

**Answer** (2026-11-24 14:30, orchestrator): この票の作業は**本体にしか無く**、しかも本体の `jobloop/roster.py` に **`T-PH9-410` の仕事が同じファイルで重なっていた**（この票: `EXHAUSTION_RETRY_WINDOW_SECONDS` / `EXHAUSTION_COOLDOWN_CAP` と倍々の説明。410: `import sys` と `except Exception`）。**パス単位で切り分けられないので、手で行を選ぶのは当て推量になる。やらない。** 410 は自分のワークスペースに同じ仕事を持っているので、本体の写しは退避して本体を戻した。**この票はワークスペースでやり直しになる（正直に書く）。** 失われないよう、測った 3 つの値と方針（窓 30 分・上限 24 時間・通常消費なら連続記録を戻す）は裁定本文に記録した。**試行は消費せず `doing`。** 詳細は `tasks/T-PH9-409.md`。

## T-PH9-410 — review cycle limit reached (2026-11-24T14:46:06+09:00)

**Question**: The reviewer still requires changes, and the review cycle budget is spent (attempts 2/3, review cycles 2/2).

**Context**

Using quality-review to [set the review approach for this task].Using security-audit to [complete the ordered review skill sequence, then verification-before-completion for the evidence gate].

**VERDICT**
- CHANGES_REQUIRED

**FINDINGS**
- Medium, `jobloop/roster.py:76-80` (dispatch-path reader; same change-set files via `jobloop/controller.py:667`), residual broken-roster hole: the ticket's fix closed the two reported failure modes — `cooldown_wait` now skips non-finite/non-dict cooldown entries (`scripts/supervise_loop.py:134-135`) and `Roster._state` now catches any read failure and logs one line (`jobloop/roster.py:69-71`) — but `Roster.available()` still runs `spent.get(name, {}).get("cooldown_until", 0) <= self.now` with no entry/type/finiteness validation. A corrupt roster entry therefore still crashes the loop, just one hop further down than the ticket addressed: concrete failing input is a roster file containing `{"opencode/a-free": 42}` (or `{"opencode/a-free": {"cooldown_until": "soon"}}`); sequence is idle → `cooldown_wait` correctly skips the bad entry and falls to backoff → dispatch → `Roster.pick()` → `available()` → `AttributeError`/`TypeError` → unhandled in `Controller` (`jobloop/controller.py:667`) → supervisor crash loop. The ticket's headline ("壊れたロスターでループを落とさない") is therefore not fully met by this diff. Smallest fix: apply the same defensive guard in `available()` (skip non-dict / unparseable / non-finite entries) and add a regression test through `pick()`.

**UNVERIFIED**
- I did not re-run the test suite or any command myself; the controller-recorded gates stand (task-verification exit 0 / 75 passed; python-lint, python-format, secret-scan all green) and were not re-executed per job instruction.
- The corrupt-entry dispatch failure above was derived by code reading (`jobloop/roster.py:76-80`, `jobloop/controller.py:667`), not by execution, so its runtime behaviour is traced rather than directly reproduced.


**Answer** (2026-11-24 15:30, orchestrator): **レビュアーが正しい。走らせて確かめた。** `{"opencode/a-free": 42}` で `AttributeError`、`{"cooldown_until": "soon"}` で `TypeError` が `Roster.available()` から出る（`available()` は `pick()` が呼ぶ**派遣経路**）。**前回の 408 とは違い、これは範囲外ではない** — 表題が「壊れたロスターでループを落とさない」なのだから、派遣経路に残った穴はこの票の仕事である。移す先は無い。**周回を 1 回戻し（2/2 → 1/2）、試行は動かさず `doing` に戻す。** 残りは `available()` の防御 1 箇所と `pick()` を通した回帰検査 1 件だけで、既に直っている 2 件を再提起しないよう carve-out を本文冒頭に書いた。詳細は `tasks/T-PH9-410.md`。

## T-PH9-411 — worker wrote outside its workspace (2026-11-24T14:56:08+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/flint-40b-free
workspace=<workspaces>\workspaces\T-PH9-411
marker=<repo>\.jobloop\orchestrator-busy present=False
containment opencode/flint-40b-free: 1/5 stops/dispatches
appeared:
 M scripts/secret_scan.py
 M tests/test_secret_scan.py


**Answer** (2026-11-24 15:30, orchestrator): ワークスペースに変更が 1 件も無く、作業は本体にあった（`secret_scan.py` 本体 199 / ws 152 行、`test_secret_scan.py` 122 / 76 行）。どちらもこの票の許可パスなので切り出してワークスペースへ移送し、本体は戻した。**消していない。試行は消費せず `review`。** 詳細は `tasks/T-PH9-411.md`。

## T-PH9-406 — integration branch is dirty (2026-11-24T15:06:56+09:00)

**Question**: The main checkout has uncommitted changes, so the reviewed commit was not merged. Decide how to integrate it.

**Context**

commit=c6c0c4a7eab03e38676cf533e1ceffc5254ed0a5
foreign (判定に使った未コミットのパス):
 M scripts/secret_scan.py  → T-PH4-103, T-PH6-109, T-PH6-113, T-PH6-124, T-PH9-411 の許可パス
 M tests/test_secret_scan.py  → T-PH6-109, T-PH6-113, T-PH6-124, T-PH9-411 の許可パス

not used for decision (判定に使っていない: progress/ と平易化ページ):
 M progress/phase-9-loop-health/OWNER_DECISIONS.md
 M progress/phase-9-loop-health/tasks/T-PH9-406.md
 M progress/phase-9-loop-health/tasks/T-PH9-410.md
 M progress/phase-9-loop-health/tasks/T-PH9-411.md

**Answer** (2026-11-24 15:30, orchestrator): 巻き添えである。`foreign` は `T-PH9-411` の仕事で、この票の作業はワークスペースに健在。本体は綺麗にした。**試行は消費せず `review`。** **皮肉だが**: この票が直す経路（記録が本体の絶対パスを教える）が未修正なので逃亡が続き、その巻き添えでこの票が止まっている。**単一監督に戻した 15:00 以降も逃亡は起きている**ので（`T-PH9-411` が実例）、二重起動は単独犯ではなく、この経路は実在する。**通すのが最優先。** 詳細は `tasks/T-PH9-406.md`。

## T-PH9-406 — the merge conflicted (2026-11-24T15:29:14+09:00)

**Question**: The reviewed work no longer applies to the integration branch, so the merge was aborted and nothing was committed. Decide whether the job redoes its work on the current branch.

**Context**

commit=c6c0c4a7eab03e38676cf533e1ceffc5254ed0a5
branch=loop/T-PH9-406-t-ph9-406
Auto-merging jobloop/controller.py
CONFLICT (content): Merge conflict in jobloop/controller.py
Auto-merging tests/test_jobloop.py
CONFLICT (content): Merge conflict in tests/test_jobloop.py
Automatic merge failed; fix conflicts and then commit the result.


**Answer** (2026-11-24 16:30, orchestrator): **現在の統合ブランチの上でやり直す。** マージは中止済み（`MERGE_HEAD`/`UU` なし、確認済み）。衝突は `jobloop/controller.py` と `tests/test_jobloop.py`。**原因は私の並べ方の誤り** — `T-PH9-404` が 14:4x にマージされ、この票と同じ 3 ファイル（`controller.py` 13 行・`roster.py` 175 行・`test_jobloop.py` 116 行）を動かした。406 と 410 を依存なしで同時に `review` に置いたのが私である。**古い枝をそのまま採らない**（11-21 に `T-PH6-113` で`test.fail` を復活させかけた）。枝に入った 404 の計数・休止は重複して書かないこと。**試行は消費せず `doing`。** この票は今の最優先である（未修正のこの経路で今日 6 件以上が逃げ、`T-PH6-104` は 6 回・`T-PH6-127` は 4 回止められた）。詳細は `tasks/T-PH9-406.md`。

## T-PH9-410 — the merge conflicted (2026-11-24T15:38:51+09:00)

**Question**: The reviewed work no longer applies to the integration branch, so the merge was aborted and nothing was committed. Decide whether the job redoes its work on the current branch.

**Context**

commit=872485682402cbc68f30dbc54fe0e777497d1e94
branch=loop/T-PH9-410-t-ph9-410
Auto-merging jobloop/roster.py
CONFLICT (content): Merge conflict in jobloop/roster.py
Auto-merging tests/test_jobloop.py
Automatic merge failed; fix conflicts and then commit the result.

**Answer** (2026-11-24 16:30, orchestrator): 同じ原因（`T-PH9-404` のマージ）で衝突した（`jobloop/roster.py`。`tests/test_jobloop.py` は自動合流できた）。**順番を付けた**: `depends_on` に `T-PH9-406` を追加し、406 の後に回す（両票が `tests/test_jobloop.py` を触るため）。**現在の枝でやり直し**、404 が入れた 175 行の上に防御を重ねること。15:30 に実測した `Roster.available()` の穴（`AttributeError`/`TypeError`）も同じ `available()` に入れる。**試行は消費せず（2/3）、周回は 1/2 のまま `doing`。** 詳細は `tasks/T-PH9-410.md`。

## T-PH9-406 — the merge conflicted (2026-11-25T10:04:32+09:00)

**Question**: The reviewed work no longer applies to the integration branch, so the merge was aborted and nothing was committed. Decide whether the job redoes its work on the current branch.

**Context**

commit=c6c0c4a7eab03e38676cf533e1ceffc5254ed0a5
branch=loop/T-PH9-406-t-ph9-406
Auto-merging jobloop/controller.py
CONFLICT (content): Merge conflict in jobloop/controller.py
Auto-merging tests/test_jobloop.py
CONFLICT (content): Merge conflict in tests/test_jobloop.py
Automatic merge failed; fix conflicts and then commit the result.

**Answer** (2026-11-25 10:35, orchestrator): **現在の統合ブランチの上でやり直す。試行は消費せず `doing`。** 原因はワーカーではなく仕組みである。`Controller.refresh()` は自分のコミットを持つワークスペースのリセットを意図的に拒否するため（2026-11-21 にレビュー済み 5 件を消した事故への対策で、拒否自体は正しい）、毎サイクル古い木でゲートが通り、マージだけが衝突し、`resume` は試行を消費しないので永久に繰り返していた。**2026-11-24 16:30 の同趣旨の裁定は実行されていなかった**（停止記録のコミットが昨日と同一の `c6c0c4a`）。状態を書き換えても基点は動かないので、あの裁定には実行する手段が無かった。実測: 基点 `30be2e8`（11-24 12:31）で **31 commits 遅れ**、作業はまだ必要（足す 5 本のテストはいずれも統合ブランチに無い）。**私が手でワークスペースを現在の枝へリセットした**（`behind=0`/`ahead=0`/汚れなし）。元のコミットはタグ `stale/T-PH9-406-1125` に保全し、捨てていない。古い枝をそのまま採らないこと。仕組みの欠陥は `T-PH9-414` に起票した。詳細は `tasks/T-PH9-406.md`。

## T-PH9-406 — out-of-scope change (2026-11-25T13:21:07+09:00)

**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job. — 1 path(s) the worker wrote outside its scope: test_output.txt. Decide whether the job's scope was drawn too narrowly, or whether the worker should not have written them.

**Context**

outside allowed_paths: ['test_output.txt']

**Answer** (2026-11-25 14:35, orchestrator): **屑である。削除して `doing` に戻し、試行は消費しない（1/3 のまま）。** 実測: `test_output.txt`（183 バイト）の中身は pytest の出力そのもの（`77 passed in 25.57s`）で、変更が参照している実体ではない。この票の実作業は `selfrepair.py` / `test_jobloop.py` / `test_selfrepair.py` の 3 ファイルに未コミットで健在。**ワーカーの逸脱ではなく、範囲が狭すぎたのでもない。** `gates.litter` が掃かなかった理由が本当の原因で、仕組みの側にある: 掃き出しは拡張子ではなく**参照**で判定し、範囲内のテキストが緩いパスを言及していれば掃かずに止める（正しい設計）。ところがこの票は範囲に `tests/test_jobloop.py` を含み、**そのファイル自身が `"test_output.txt"` を試験データとして持っている** — 屑掃除そのものの試験だからである（436・444・474・477・480 行）。つまり**屑掃除の試験を含む票は、自分の試験データに守られて自分の屑を掃けない**。`check_select3.py` や `debug_test.py` も同じ試験データに出るので同じことが起きる。仕組みの側は `T-PH9-416` に起票した。詳細は `tasks/T-PH9-406.md`。

## T-PH9-406 — worker stopped for a decision (2026-11-25T15:43:23+09:00)

**Question**: AC3's tracked-file guard cannot pass inside this ticket's allowed_paths — six tracked, non-protected files still contain a repository root (`docs/APP_PROVISIONING.md`, `docs/report/IMPLEMENTATION_STATUS_AND_BLOCKERS.html`, `docs/requirements/LOOP_BOOTSTRAP_SPEC.md`, `progress/phase-6-extensions/OWNER_DECISIONS.md`, `progress/phase-9-loop-health/OWNER_DECISIONS.md`, `tests/test_release_test_ports.p

**Context**

:2726`, `progress/phase-9-loop-health/OWNER_DECISIONS.md:245`), and the latter also has absolute `workspace=`/workdir lines. The docs claim is not true of the tree.

Risk left behind: AC3's guard is **not** delivered (see STATUS). Also unchanged and out of scope: `jobloop/roster.py` still lets `UnicodeDecodeError` escape on a non-UTF-8 roster (`T-PH9-410`).

TEST

- `python -m pytest tests/test_jobloop.py tests/test_selfrepair.py -q` — before changes: `77 passed in 25.26s`; after: `79 passed in 25.08s` (exit 0).
- `python -m ruff check backend tests scripts jobloop` — `All checks passed!`
- `python -m ruff format --check backend tests scripts jobloop` — `192 files already formatted`
- `python scripts/secret_scan.py jobloop/controller.py jobloop/selfrepair.py tests/test_jobloop.py tests/test_selfrepair.py` — `Offline secret scan: 0 findings`
- AC3 measurement (inline scan of `git ls-files`, excluding `jobloop.gates.PROTECTED`, over both the checkout root and the local `origin` path): 6 tracked non-protected files still contain a root — `docs/APP_PROVISIONING.md`, `docs/report/IMPLEMENTATION_STATUS_AND_BLOCKERS.html`, `docs/requirements/LOOP_BOOTSTRAP_SPEC.md`, `progress/phase-6-extensions/OWNER_DECISIONS.md`, `progress/phase-9-loop-health/OWNER_DECISIONS.md`, `tests/test_release_test_ports.py`. That is why no AC3 test was added: it would fail the verification command.

STATUS
needs-owner-decision: AC3's tracked-file guard cannot pass inside this ticket's allowed_paths — six tracked, non-protected files still contain a repository root (`docs/APP_PROVISIONING.md`, `docs/report/IMPLEMENTATION_STATUS_AND_BLOCKERS.html`, `docs/requirements/LOOP_BOOTSTRAP_SPEC.md`, `progress/phase-6-extensions/OWNER_DECISIONS.md`, `progress/phase-9-loop-health/OWNER_DECISIONS.md`, `tests/test_release_test_ports.py`) and the task forbids rewriting existing progress records — may I redact them by widening allowed_paths, or should AC3 exclude non-record documentation and pre-existing records?

**Answer** (2026-11-25 17:30, orchestrator): **ワーカーの報告は正しく、止めて訊いたのも正しい。範囲の引き方と条文の両方が私の誤りだったので両方を直した。`doing` で続行、試行は 1/3 のまま。** 実測（`git ls-files` 全 825 件）: 本体ルートを含む追跡ファイルは **50 件**、うち 44 件は `docs/plans/` 配下で**保護パス**なので対象外 — ワーカーの「6 件」は正しい。残りのうち **2 件は正当な試験データ**（`tests/test_release_test_ports.py` は開発サーバのコマンドラインを模し、`tests/test_selfrepair.py` は `REPO` 定数）で、**AC3 を字句どおり適用するとこの 2 本が永久に落ちる** — `T-PH9-416` と同じ「検査が自分の試験に負ける」形で、条文を書いた私の誤りである。残り **3 件は本物の違反**（手で保守されている文書）で、この票の許可パスの外にあったのでワーカーは正しく手を止めた。**範囲の引き方が狭すぎた。** `progress/` の 2 件（計 32 箇所）は**私が自分で消した**（決定記録をワーカーに編集させるのは避けた）。直した内容: (1) **AC3 の条文を書き換えた**（追記ではなく置換）。試験データとして本体パスを要するテストを**パス 1 件ずつ・理由つきで**除外してよいと明記し、前方一致やディレクトリ単位の除外は禁じた。**条文を落としたのではなく実現可能な側へ書き直した** — 守りたい性質は変えていない。(2) **許可パスに 3 文書を足した**（要求と許可を一致させた。逸脱の事後合法化ではない）。残りは 3 文書を `<repo>` のような相対表記に置き換えること（意味を残し、行ごと削らない）。**この票が通れば `T-PH9-414`・`415`・`416` が動き出すので今の最優先である。** 詳細は `tasks/T-PH9-406.md`。

## T-PH9-410 — attempt limit reached (2026-11-25T20:52:18+09:00)

**Question**: Three attempts did not satisfy the acceptance criteria; the job needs a human decision.

**Context**

the worker changed nothing

**Answer** (2026-11-25 21:21, orchestrator): **試行を 2/3 に戻す（16:30 の裁定が置いた数に戻すだけで、前の周の分は戻さない）。周回は動かさない（1/2）。`doing` に置く。受入条件も許可パスも変えていない。** **20:51 の派遣は試行ではない**: 20:51:22 に派遣され **56 秒**で上限に当たり、その間に `WORKSPACE NOT REBASED`（93 commit 遅れ・1 commit 進み）が記録されている。ワークスペースには 2026-11-24 に **`APPROVED`** を受けたコミット `8724856` がそのまま在ったので、**ワーカーは正しく「変えるものが無い」と答えた**。**2026-11-24 16:30 に命じたやり直しは一度も走っていない** — `refresh()` が「進んでいる」ワークスペースを reset しない（2026-11-21 の事故の後の正しい番人）ため土台が進まず、古いコミットが居座っていた。**順番を付けた私が土台のことを忘れていた。** **`T-PH9-414` が 19 分遅れで間に合った**: この票が escalate した 20:52 の 19 分後、21:10 に `b43381b` がマージされ、`Controller.advance_base()`（手の tag と reset を置き換えるために書かれ、作業木が汚れていれば拒否する）が使えるようになった。**使った** → `preserved at = stale/T-PH9-410-1125`、`behind=0 ahead=0`、作業木は綺麗。**成果は失われていない**（`git show stale/T-PH9-410-1125`。`roster.py` +31 / `supervise_loop.py` +3 / `test_jobloop.py` +176）。**これ以降、同じ状態は試行を使わない** — `T-PH9-414` が `already_conflicted_ahead()` を実装の入口に置いたので、次からは試行を消費する前に「the merge conflicted」で止まる。**やり直す先はもう別のファイルである**: `roster.py` はあのコミットの後に 2 回動いた（`T-PH9-404` の 175 行と、**私が今夜入れた第 2 段**。`eligible()` の書き換え、`AGY_ROLES`/`agy_role()`/`_agy_rank()` の追加、`pick()` への `role` 追加）。`merge-tree` で確かめたところ `roster.py` は衝突し `tests/test_jobloop.py` は自動合流できる。**同じ守りを今の形の上に書き直させる**: `_state()` が壊れた JSON で落ちない／`available()` と `_cooled_down()` が非 dict・非数値・非有限（NaN・±inf）で落ちない（**いまの `_cooled_down(spent.get(name, {}))` の形に合わせること** — 古いコミットは `available()` の戻り値の作り方ごと書き換えていたが、その形はもう無い）／`supervise_loop.py` に同じ有限性の守り／11-24 14:46 のレビューが挙げた穴／`APPROVED` 時の Low（`-inf` の場合を足せば `math.isfinite` の有無が観測可能になる）。**私が今夜足した所も見させる**: `agy_role()` と `_agy_rank()` は文字列だけを見るので壊れた記録では落ちないと**私は読んでいるが、走らせていない** — 確かめて REPORT に書くこと、**私の読みを根拠にしないこと**。**オーナーに伺うことが 1 つ増えた**: `advance_base()` の説明文が「無人のジョブが衝突した土台を自分で捨ててよいかは未決」と残している。今回は私が明示的に呼んだので未決には触れていないが、**同じ状態は必ずまた起きる**（今日 `T-PH6-104` と `T-PH9-410` の 2 件）。**「無人のときに自動で土台を進めてよいか」を伺う** — 自動化すれば止まらなくなるが、**レビュー済みの成果を機械が捨てる**ことを許す意味でもある（成果は `stale/...` に残るが、やり直しは発生する）。詳細は `tasks/T-PH9-410.md`。

## ORCHESTRATOR NOTE — 「無人のジョブが土台を自分で進めてよいか」の前提を測り直した (2026-11-26 07:18)

**裁定ではない。何も変えていない。** 2 点だけ記録する。

**1. 06:22 の報告で私が書いたことを訂正する。** あのとき「`T-PH9-413`（監督は 1 台だけ）と
`T-PH9-409`（枠切れの冷却を延ばす）が通ったことで実害の出方が変わった」と書いたが、
**測っていなかった。** 測ると**変わっていない**。

```text
f6e7605 (T-PH9-409)  jobloop/roster.py, tests/test_jobloop.py
4c46e81 (T-PH9-413)  scripts/supervise_loop.py, tests/test_jobloop.py
```

**どちらも `jobloop/controller.py` に触っていない。** `advance_base()` の説明文
（`controller.py:513`）は「無人のジョブが衝突した土台を自分で捨ててよいかは未決」を
そのまま残しており、**この問いは一字も動いていない。** お返事の判断材料として
「状況が変わった」と読まれては困るので、取り消す。

**2. そのうえで、今朝はじめて「流れているとき」の費用が測れた。**

これまでの 4 件（`T-PH6-104` / `T-PH9-410` / `T-PH6-121` / `T-PH6-127`）は、
**供給が止まっている時間に私が手で掃除していた。** 今朝 04:34〜05:52 の 78 分は
違った —— **8 件がマージされた**（`T-PH9-410`/`412`/`409`/`413`、
`T-PH6-127`/`121`/`128`/`130`）。

**この間、土台のずれで失った試行は 0 である。** ただしその理由は仕組みではない。
**01:20 と 01:24 に私が起きていて、派遣される前に `T-PH6-127` と `T-PH7-223` の
2 件を保全したからである**（`stale/T-PH6-127-1126`、`stale/T-PH7-223-1126`）。

**つまり判断材料はこう変わった。** 問いの中身は同じだが、**待ち行列が
1 供給窓あたり 8 件流れるようになったので、ずれの溜まる速さが上がった。**
掃除が人の起床時刻に依存している状態は、動きが遅いうちは成り立っていた。
**自動化しない代償は、これまで「試行の消費」だったが、今後は「夜間に誰も
掃除しない時間が長い票ほど確実に 1 回無駄に派遣される」という形になる。**

**急ぎではない。** いま `blocked` になっている票にこの問いは関わっていない。

## ORCHESTRATOR NOTE — `PREFERRED` の上位に、もう存在しないモデルが居る（2026-11-26 10:18）

**これはオーナーの判断を求めるものではない。** `roster.py` が空くまで
起票を待つという私の判断と、その根拠の記録である。

### 測ったこと

`jobloop/roster.py` の `PREFERRED` は「実装の能力順、良い方から」と
書かれた 11 件の並びである。`.jobloop/roster.json` と突き合わせると、
**そのうち 5 件が現在の提供一覧に無い。**

```text
PREFERRED 1 番目  glm-5.3-flash-free        状態ファイルに冷却記録のみ、8 日前で失効
PREFERRED 3 番目  minimax-m3.1-flash-free   同じく 9 日前で失効
PREFERRED 4 番目  longcat-2.5-free          同じく 3 日前で失効
PREFERRED 9 番目  inkling-2-small-free      状態ファイルに記録が無い
（PREFERRED 外）  qwen4-max-free            2 日前で失効
```

`shift_check` が数える 20 件にこれらは入っていない。**提供側の品揃えから
消えたのであって、冷却されているのではない。** 失効しているので、
もし一覧に戻れば即座に使える状態で待っている。

### 害の程度 —— 派遣は壊れていない

`PREFERRED` は候補の**並び順**であって資格条件ではない
（資格は接頭辞と `-free` 接尾辞で決まる）。一覧に無い名前は単に飛ばされる。
**従って派遣の挙動は正しい。** 実際、今朝の 08:27 の回転は
存在する 5 件を順に試しており、消えた名前で時間を無駄にしていない。

害は読む側に出る。(a) この並びを読んだ当番は「一番良い無料モデルは
`glm-5.3-flash-free` だ」と理解する。手に入らない。(b) 並びの注釈は
「未掲載のモデルは CLI の順で**この後ろに**付くので、新しい無料モデルは
すぐ使えるが、根拠のあるモデルを追い越すことはない」と言っている。
**その「根拠のあるモデル」の上位 2 件が存在しない**ので、
新顔は実在しない 2 件の下に並べられている。順位としては無害だが、
「根拠に基づく序列」という説明は 11 件中 5 件について成り立っていない。

### なぜいま起票しないか

直す場所は `jobloop/roster.py` で、**`T-PH9-418` がそのファイルを
持っている**（道具非対応モデルの除外）。同じファイルに 2 票を並べると
衝突する。`T-PH9-418` が通ったら起票する。

これは `T-PH9-418` 自身と同じ扱いである —— あの票も
`T-PH9-410` が `roster.py` を手放すまで待たせた。

## ORCHESTRATOR NOTE — 一過性の `endpoint is unavailable` に 6 時間の冷却が付く（2026-11-26 11:17）

**これもオーナーの判断を求めるものではない。** 同じく `roster.py` が空くまで
起票を待つ判断と、その根拠である。上の 10:18 の申し送りと同じ待ち条件で、
直す場所も同じファイルなので、`T-PH9-418` の次にまとめて起票する。

### 測ったこと

今朝、無料枠に**新顔が 1 件増えた**。`shift_check` の数が
20 件から 21 件になっている。`opencode/seaglass-alpha-free` である。

10:31:06 に `T-PH9-417` の派遣で 1 回試され、こう答えた。

```text
rotated - opencode/seaglass-alpha-free endpoint is unavailable
```

回転は正しく次へ進み、試行も消費していない。そこは問題ない。
問題はそのあとに書かれた状態である。

```text
cooldown_until  残り 313 分（6 時間後 = 16:31 ごろ）
exhausted_streak  1
dispatches  1
```

**`endpoint is unavailable` に、枠切れと同じ 6 時間の冷却が付いた。**
`exhausted_streak` も 1 に上げられている —— 枠が尽きたわけではないのに、
枠切れの数え上げに入っている。

### なぜ気になるか —— ただし今日は損していない

枠切れは「割り当てを使い切った」という状態で、6 時間待つのは理に合う。
`endpoint is unavailable` は**供給側の一時的な不調**で、
次の瞬間に戻っていることも有る。同じ 6 時間を課すと、
**新しい無料モデルが一度ぐずついただけでその日は失われる。**
いま無料枠が一日のうち何時間も丸ごと尽きている状況では、
使える供給を 1 件増やせるかどうかは小さくない。

**ただし今日の実害は 0 である。** 11:12:06 の派遣では
`agy/gemini-4-carbon-low` が 11:05 に復帰していて、11:12:07 に
実際に仕事を始めた（`agy.EXE` PID 49312、4 分後も生存）。
`seaglass` が休んでいても、仕事は止まっていない。
**だから急ぎではない。** 測れたことを残すだけにする。

### 判断を要する点（起票するときに実装者へ渡す）

`Ending.OUTAGE` と `Ending.EXHAUSTED` を**冷却の長さで区別するか**。
短すぎれば壊れた提供元を何度も叩き、長すぎれば今回のように
使える供給を捨てる。`exhausted_streak` を枠切れ以外で上げないことは
区別の前提として要る —— いまの数え方では、不調 1 回が
「枠切れ 1 回」として記録されている。

## ORCHESTRATOR NOTE — 第2段への問い合わせは 1 件 45 秒かかる（2026-11-26 13:19）

**オーナーの判断を求めるものではない。** 上の 10:18・11:17 と同じ
`roster.py` 待ちの 3 件目として記録する。**いま実害は出ていない。**
出る条件のほうが本題なので、それを書き残す。

### 測ったこと

`T-PH9-417` のレビュー担当探しで、第2段を 6 件続けて試した。

```text
12:47:14  resuming
12:47:58  rotated - agy/gemini-4-argon-low is out of usage      44 秒
12:48:41  rotated - agy/gemini-4-argon-medium is out of usage   43 秒
12:49:25  rotated - agy/gemini-4-argon-high is out of usage     44 秒
12:50:10  rotated - agy/gemini-4-carbon-medium is out of usage  45 秒
12:50:55  rotated - agy/gemini-4-carbon-high is out of usage    45 秒
12:51:41  rotated - agy/gemini-4-hydrogen-low is out of usage   46 秒
          → 1 件の票で 276 秒
```

**1 件あたり 43〜46 秒である。** 同じ「枠切れ」の問い合わせを
第1段（`opencode.exe`）にすると **3 秒**で返る —— 今朝 08:27 の回転が
5 件で 15 秒だった。`agy.EXE` は起動そのものが重い。

### 今日は損していない

276 秒を使った直後、周回は 240 秒の待機に入った。**ほかにやることが
無い時間に使われたので、失ったものは無い。** 試行も消費していない。

### 害が出る条件

**第1段に 1 件でも生きているモデルが有り、かつ第2段が枯れているとき。**
いまの順番は第1段が先なので（`roster.py` の設計どおり）この条件は
満たされにくい。満たされるのは、第1段が全滅して第2段に落ちた直後に
第1段の 1 件が冷却から戻る、という並びのときである。そのとき
第2段の死んだ 6 件を 4 分半かけて確かめてから第1段に戻ることになる。

### 起票するときに渡す判断点

**`agy/*` の 1 件が「枠切れ」と答えたら、同族 10 件をまとめて休ませるか。**
今日の実測は両方の読みを許す。08:27 に 10 件が数秒差で冷却に入ったのは
共通の枠を示すが、11:05 に `carbon-low` だけが 47 分早く戻って
80 分働いたのは共通でないことを示す。**どちらとも言えない。**
まとめて休ませると、いまの `carbon-low` の 80 分を捨てることになる。
**だから「まとめて休ませる」を既定にしてはいけない。**
測るべきは、1 件が枠切れを返したあと**同族の別の 1 件が実際に働けた例が
有るか**である。今日の記録にその例は無い（`carbon-low` が働いたのは
冷却が明けてからで、他が枠切れを返している最中ではない）。

## T-PH9-418 — out-of-scope change (2026-11-26T13:45:01+09:00)

**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job. — 1 path(s) the worker wrote outside its scope: jobloop/controller.py. Decide whether the job's scope was drawn too narrowly, or whether the worker should not have written them.

**Context**

outside allowed_paths: ['jobloop/controller.py']

**Answer** (2026-11-26 14:21) — **当番の誤りである。許可パスを広げた。**
受入条件 1 が「判定の根拠（応答の文言か、能力の問い合わせか）を報告に
書くこと」と要求しているのに、応答の文言が読める場所（`controller.py` の
回転処理）を許可パスに入れていなかった。条件が構造上必要としている
モジュールであり、拾い食いではない。`jobloop/controller.py` を
**回転処理の 1 箇所に限って**許可パスに追加し、その限定を票の SCOPE に
書いた。受入条件は 1 つも変えていない。`scripts/shift_check.py` は
追加していない —— 受入条件 3 は `roster.py` 側の除外だけで満たされる
（`shift_check` は `Roster.available()` を呼んでいる）。

## T-PH9-419 — worker wrote outside its workspace (2026-11-26T13:55:55+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/nemotron-3.5-lightning-free
workspace=T-PH9-419
marker=.jobloop/orchestrator-busy present=False
containment opencode/nemotron-3.5-lightning-free: 2/38 stops/dispatches
appeared:
 M scripts/shift_check.py
 M tests/test_jobloop.py

**Answer** (2026-11-26 14:21) — **停止は正しい。ワーカーの逸脱である。**
`marker present=False`、当番は本体チェックアウトを触っていない。
この票のワークスペースは**完全に空**で、唯一の写しが本体チェックアウトに
有った。差分を `.jobloop-Locus/escaped/2026-11-26/T-PH9-419-main-checkout.patch`
に退避し（消していない）、`git checkout --` で木を戻した。`status` を
`todo` に戻し、`depends_on` に `T-PH9-418` を足して同じテストファイルの
競合を外した。試行は消費されていない。封じ込め比 3/39 は休ませる水準に遠い。

## T-PH9-420 — worker wrote outside its workspace (2026-11-26T14:00:49+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/nemotron-3.5-lightning-free
workspace=T-PH9-420
marker=.jobloop/orchestrator-busy present=False
containment opencode/nemotron-3.5-lightning-free: 3/39 stops/dispatches
appeared:
?? REPORT

**Answer** (2026-11-26 14:21) — **停止は正しいが、出たのは報告ファイル 1 本
だけである。** この票の実装はワークスペースに正しく残っている
（`jobloop/controller.py` + `tests/test_jobloop.py`）。`REPORT` を
`.jobloop-Locus/escaped/2026-11-26/T-PH9-420-REPORT.txt` に退避して木から
外し、ワークスペースの差分も保険として写した。`status` を `todo` に
戻した。レビューを通っていないので、再派遣で実装者が自分で報告すること。

## ORCHESTRATOR NOTE — 封じ込めの比率は一生分なので、今まさに暴れている 5 分が見えない（2026-11-26 14:23）

**オーナー決定ではない。** 直す場所（`jobloop/roster.py`）を `T-PH9-418` が
握っているので起票を見送った記録である（`T-PH9-418` 自身が `T-PH9-410` を
待ったのと同じ扱い）。

測ったこと。`opencode/nemotron-3.5-lightning-free` は今日 13:55 と 14:00 の
**5 分間に 2 回**、本体チェックアウトに書いた。それでも封じ込めの集計は
**3/39** で、しきい値（`CONTAINMENT_MIN_DISPATCHES = 5` 以上の派遣で
`CONTAINMENT_RATE = 0.5`）に対して 7% である。**休ませる判定には永久に
届かない。** 残りの 1 回は 2026-11-24 で、2 日前である。

比率が一生分の派遣で割られているので、**39 回の正常な派遣が、いま続けて
起きている逸脱を薄めている。** 新しいモデルは 5 回で判定されるのに、
働いてきたモデルは何回逸脱しても判定されない —— 向きが逆である。

**今日の損は実際に出た。** 14:00 に落ちた `REPORT` のせいで、14:03 に
`T-PH6-129` の `abe554a`（`APPROVED` 済み）が
`integration branch is dirty` でマージできず、当番が手で木を戻すまで
phase-6 の 3 票（`T-PH6-129`, `T-PH6-135`, `T-PH6-136`）が止まった。
1 本のよそのファイルが枝ごと止める、2026-11-20 と同じ形である。

起票するときの判断点（決めてはいない）:

- 直近の窓（たとえば直近 10 派遣）での比率を併用するのか、
  **連続 2 回の逸脱それ自体**を休ませる条件にするのか
- 窓を入れると、2026-11-24 のように**当番自身のコミットが原因だった**
  誤検知が一気に効きやすくなる。あの日の 6 件のうち 5 件は当番のもので、
  いまは `progress/` を除外して直っているが、除外の穴が 1 つ出れば
  即座にモデルを休ませることになる。**窓は厳しくする変更である**ことを
  票に書くこと

## ORCHESTRATOR 実測 — 休ませたら 3 件のマージを失っていた（2026-11-26 17:19）

**オーナー決定ではない。** 14:23 の申し送り（封じ込めの比率が一生分なので
直近の連続した逸脱が見えない）に、**反対側の材料**が同じ日に出たので足す。

14:23 の時点では、`opencode/nemotron-3.5-lightning-free` が 5 分間に 2 回
逸脱したのに比率 3/39 では永久に休まない、という片側しか無かった。
その後こうなった。

逸脱はさらに 2 回増えた（合計 5/47）。

```text
14:33  T-PH6-131   ?? tests/test_ingestion_record.py
16:42  T-PH7-212   本体チェックアウトに 6 本。pyproject.toml を含む
```

**同じモデルが、同じ日にこれを出した。**

```text
13:29  T-PH9-417   merge   ← このモデルがレビュアー
16:45  T-PH7-213   merge   ← このモデルが実装（試行 2）
16:49  T-PH7-215   merge   ← このモデルが実装。受入条件 3 の
                             「守りを外すと検査が落ちる」ことまで
                             自分で確かめている
```

`T-PH6-129`（`APPROVED` 済みで待機中）のレビュアーもこのモデルである。

**つまり 14:23 の時点で「連続 2 回で休ませる」を入れていたら、今日の
マージ 3 件と承認 1 件を失っていた。** 比率が一生分であることは
欠陥だが、**この 1 件に関しては結果として正しく振る舞っていた**。

票を書くときの判断点が 1 つ増えた（決めていない）:

- 休ませる判定を**役割ごとに分ける**余地がある。このモデルの逸脱は
  **3 回すべて実装の派遣**で起きており、レビューの派遣では起きていない
  （レビュアーはワークスペースに書かない）。実装だけ止めてレビューは
  残す形は、今日の実測では損が小さい
- ただしそれは `roster.py` の `pick(role=...)` に休ませ方の軸を足す話で、
  **`T-PH9-422`（出る前に止める）が効けば不要になる**。先に 422 を
  測ってから決めるほうが安い


## T-PH9-421 — worker wrote outside its workspace (2026-11-26T18:00:55+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=T-PH9-421
marker=.jobloop/orchestrator-busy present=False
containment opencode/iceman-free: 1/29 stops/dispatches
appeared:
 M jobloop/controller.py
?? tests/test_jobloop_containment.py


**Answer** (2026-11-26 21:32, orchestrator): **決定は要らない。18:25 に処理済みで、いま `todo`・試行 0/3 で順番待ちに居る。** 18:00 の派遣は仕事を丸ごと本体チェックアウトに落とした（`jobloop/controller.py` に 82 行、`tests/test_jobloop_containment.py` に 171 行、ワークスペースは空）。全部 `escaped/2026-11-26/T-PH9-421-*` に保全し、18:21 に本体を戻した。**手で合流させていない。** 逸脱の escalation は試行を消費しないので 0/3 のままである。20:48 にワークスペースが現在の枝へ揃えられた（21 コミット遅れ、仕事は無し）。この票の値打ちは変わっていない —— `T-PH6-129` の承認済みコミットがよそのファイル 1 本で 3 回マージできなかった損は、この票が機械的に無くす。

## T-PH9-422 — worker wrote outside its workspace (2026-11-26T18:16:41+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=T-PH9-422
marker=.jobloop/orchestrator-busy present=False
containment opencode/iceman-free: 2/30 stops/dispatches
appeared:
 M jobloop/worker.py
?? tests/test_jobloop_worker_cwd.py


**Answer** (2026-11-26 21:32, orchestrator): **決定は要らない。この票は 20:48 にマージされた（`2e7d5fd`）。** 18:16 の派遣は自分自身の題目どおりに逸脱し（`worker.py` に 250 行、検査 121 行が本体チェックアウトへ）、保全・復旧して `todo` に戻した（試行は消費されていない）。20:20 の再派遣は**逸脱せずに通った**ので、18:25 に記録した「次の派遣でもう一度逸脱したら opus が実装する」という境目は**発動していない**。無料モデルが実装し、第 2 層が独立にレビューした。**ただし入ったのは守りの形だけで、逸脱そのものは直っていない** —— 続きと、当番が測って分かったことは、このファイル末尾の `T-PH9-422 / T-PH9-423` の項目に書いた。

## 申し送り: モデルを休ませる話は、原因ではなかった（2026-11-26 18:25）

14:23 に「封じ込めの比率は一生分なので、今まさに暴れている 5 分が見えない」
と書き、17:19 にその反対側（同じモデルが同じ日に 3 件マージしている）を
書いた。**18:18 の実測で、この議論ごと前提が崩れた。** 記録に残す。

17:48・18:00・18:16 の 3 件が立て続けに逸脱した。その間、
`nemotron-3.5-lightning-free` の封じ込め停止は **5 → 6 の +1 しか増えて
いない**。つまり **3 件のうち 2 件は別のモデルである。**

今日時点で逸脱しているモデルは 4 つ:

```
opencode/nemotron-3.5-lightning-free   6 / 51
opencode/iceman-free                   2 / 31
opencode/flint-40b-free                1 / 27
opencode/deepseek-v4.1-flash-free      1 / 16
```

**1 つのモデルの癖ではない。経路の欠陥である。** 休ませる案（二回連続で
休ませる / 家族ごと冷やす / 窓を入れる）は、どれも原因ではなく症状を
叩くので、**`T-PH9-422` より先にやってはいけない**。17:19 に「役割で
分ければよいかもしれない」と書いた筋も同じ理由で後回しにする。
`jobloop/roster.py` 側の申し送り 2 件（古い `PREFERRED`、OUTAGE と
EXHAUSTED の冷却の長さ）は、これとは別の話なので有効なまま残る。

### 今日の損の大きさ

今日の逸脱は **7 件**（13:55 / 14:00 / 14:33 / 16:42 / 17:48 / 18:00 /
18:16）。ループが動き始めてからの通算 47 件のうち 7 件が今日である。
16:00 以降の 5 件の派遣のうち、マージまで行ったのは `T-AIC-006` の 1 件だけ。
**出力の約 8 割が、レビューできない木に落ちている。**

逸脱の escalation は試行を消費しないので、票は損をしていない（今日
戻した 7 票すべて試行 0）。損をしているのは**時間**で、1 件あたり
10〜25 分である。

### opus が実装に入る境目を先に決めた（ご指示の範囲内）

ご指示は「どうにもできない場合にのみ opus による実装を許可」である。
**いまはまだそこではない**と判断した。17:31 に `T-AIC-006` が同じ経路で
マージまで行っているので、経路が完全に死んでいるとは言えない。
`T-PH9-422` は試行 0/3 で、先頭に置き直した。

**次の派遣でもう一度逸脱したら、そこで opus が実装する。** その時点で
「逸脱を直す票が、逸脱のせいで作れない」ことが 2 回測れており、経路が
自分を直せないという意味になる。票の側にも同じことを書いた。
ご指示と違う判断をしたい場合はここに上書きしてください。

## 申し送り: 逸脱は `opencode` 経路だけで起きている（2026-11-26 19:19）

18:25 に「1 つのモデルの癖ではなく経路の欠陥」と書いた。**19:19 に
その経路が特定できた。** `.jobloop/roster.json` を層ごとに足した数字:

```
agy        0 停止 /  81 派遣      ← 第 2 層。一度も外していない
ollama     0 停止 /   6 派遣
opencode  11 停止 / 172 派遣      ← 第 1 層（無料）。ここだけ
```

`jobloop/worker.py` には `run_agy` と `run_opencode` の 2 つが有り、
**違いは 1 つだけ**である。`agy` にはプロセスの作業ディレクトリをそのまま
使う形しか無く、`opencode` には**再利用される常駐サービス**が有って、
`--standalone` がそれを避けるための旗である。その旗が間欠で効いていない。
`T-PH9-422` の票にこの手がかりを書いた。

### ご判断いただきたいこと: 直るまでの間、実装を第 2 層に回すか

ご指示は「無料モデルを用いて実装を進めて」です。**私の推奨は A（変えない）**
ですが、数字が出たのでお伺いします。

- **A. 変えない（推奨）** —— 無料層のまま。今日はこの経路で **20 件
  マージしている**ので、経路は壊れきってはいない。逸脱の escalation は
  試行を消費しないので、票は損をしない。損は時間だけで、重い票は
  `T-PH9-422` の後ろに回して止血した（`T-PH7-212`）。
- **B. 直るまで実装を `agy` に回す** —— 逸脱 0/81 の実測が有る。ただし
  `jobloop/roster.py` の役割割り当てを変える**実装**が必要で、
  第 2 層には使用量の費用がかかります。ご指示とも逆向きです。
- **C. 無料層のまま、重い票だけ第 2 層に** —— 1 回 30 分を失う票だけ
  守る形。これも `roster.py` の変更が必要です。

B か C をご希望の場合はここに書いてください。何も無ければ A で進めます。

### 今日の逸脱の通算（19:19 時点）

10 件（13:55 / 14:00 / 14:33 / 16:42 / 17:48 / 18:00 / 18:16 /
18:24［当番のマーカーが隠した］/ 19:11 / 19:18［`T-PH7-214`、進行中］）。
通算 47 → 以降も増えている。いっぽう**今日のマージは 20 件**で、
これも今日が最多である。両方が同時に起きている。

## T-PH9-421 — worker stopped for a decision (2026-11-26T22:01:05+09:00)

**Question**: `tests/test_jobloop.py` (outside `allowed_paths`) has two existing tests (`test_containment_judgement_still_stops_and_clean_runs_still_pass` with `?? escaped.py x` and `test_containment_rest_is_readable_in_log_and_diagnose` with `?? leaked.py abc123`) that assert untracked unreferenced files in the main checkout escalate; should `tests/test_jobloop.py` be updated (e.g., to use tracked `M` paths fo

**Context**

file in the main checkout stopped the job. Under `T-PH9-421` AC1 (using `gates.litter`'s reference-based criterion, not file extensions), those unreferenced untracked files are swept instead of escalating, causing those two existing tests in `tests/test_jobloop.py` (which is outside `allowed_paths`) to fail.
- Risk: `test_main_checkout_untracked_litter_is_swept_and_recorded` also failed because `self.changed_path("?? REPORT\tabc123")` returned `"REPORT\tabc123"` rather than `"REPORT"`.

TEST
- `python -m ruff format jobloop/controller.py tests/test_jobloop_containment.py; python -m ruff check backend tests scripts jobloop; python -m ruff format --check backend tests scripts jobloop; python scripts/secret_scan.py jobloop/controller.py tests/test_jobloop_containment.py; python -m pytest tests/test_jobloop_containment.py tests/test_jobloop.py -q`: `ruff check` passed, `ruff format --check` passed (213 files), `secret_scan.py` passed (0 findings), `pytest` had 3 failed, 103 passed (`test_main_checkout_untracked_litter_is_swept_and_recorded`, `tests/test_jobloop.py::test_containment_judgement_still_stops_and_clean_runs_still_pass`, `tests/test_jobloop.py::test_containment_rest_is_readable_in_log_and_diagnose`).
- `python -m ruff format --check backend tests scripts jobloop; python -m pytest tests/test_jobloop_containment.py -q`: `ruff format --check` passed (213 files), `pytest` had 1 failed, 2 passed (`test_main_checkout_untracked_litter_is_swept_and_recorded`).

STATUS
needs-owner-decision: `tests/test_jobloop.py` (outside `allowed_paths`) has two existing tests (`test_containment_judgement_still_stops_and_clean_runs_still_pass` with `?? escaped.py x` and `test_containment_rest_is_readable_in_log_and_diagnose` with `?? leaked.py abc123`) that assert untracked unreferenced files in the main checkout escalate; should `tests/test_jobloop.py` be updated (e.g., to use tracked `M` paths for those escalation tests) or should `T-PH9-421`'s sweep criterion exclude `.py` files?


**Answer** (2026-11-26 22:18, orchestrator): **`tests/test_jobloop.py` を触って
よいことにしました。許可パスに足し、触れる範囲を受入条件 7 として書きました。
試行は 0/3 のまま、`doing` に置きました。受入条件は 1 つも緩めていません。**

**ワーカーの問いが正しく、当番の落ち度です。** この票は「本体チェックアウトに
現れた**未追跡で参照されていない屑 1 本**では止めない」という契約に変える票です。
ところが `tests/test_jobloop.py` の既存 2 件が、まさにその場合に止まることを
**古い契約のまま表明**していました（`?? escaped.py x` と `?? leaked.py abc123`）。
許可パスの外なので、ワーカーは**勝手に直さず訊いて止まりました。正しい順序です。**

14:25 に当番は「新しい検査を別ファイルに書けば `tests/test_jobloop.py` を
4 票が同時に握らずに済む」と考えて許可パスを狭く引きました。**新しい表明に
ついてはその通りですが、既存の表明が同じ契約を握っていることを見落として
いました。**

**白紙委任にはしていません。** 触れるのは名前を挙げた 2 件の「逸脱の材料」の
行だけで、`def test_` の本数が減らないこと（103 本）と、差し替え前後の材料と
件数の両方を貼ることを条件にしました。あの 2 件が確かめているのは
「**本物の逸脱なら止まる**」と「**休ませた記録が読める**」であって
「未追跡の屑 1 本で止まる」ことではないので、材料を追跡ファイルの行に
差し替えても性質は残ります。**緩和ではなく、契約が変わった側への差し替えです。**

## T-PH9-405 — attempt limit reached (2026-11-26T22:28:24+09:00)

**Question**: Three attempts did not satisfy the acceptance criteria; the job needs a human decision.

**Context**

the worker changed nothing

## T-PH9-420 — worker stopped for a decision (2026-11-26T22:34:01+09:00)

**Question**: Existing test `test_the_record_names_the_cli_that_actually_ran_the_session` (`tests/test_jobloop.py:2754`) asserts that `task.fields["model"]` is set to `"agy/gemini-4-carbon-low"` when `worker.Ending.UNAVAILABLE` is returned, which directly conflicts with T-PH9-420 AC2 (a model that fails during rotation must not remain in `model`). Should `test_the_record_names_the_cli_that_actually_ran_the_sess

**Context**

nd `secret_scan.py` in the background and waiting for them to finish.
REPORT
- `jobloop/controller.py`: Removed the unconditional `set_fields(task, status="todo", assignee="unassigned", model="-")` from the `if not model:` (`no-model`) branch and moved `task = self.set_fields(task, status="doing", assignee=model.split("/", 1)[0], model=model)` to after the `Ending.UNAVAILABLE` and `Ending.TIMEOUT` rotation branches, as requested by the Attempt 1 review.
- `tests/test_jobloop.py`: Updated `test_all_models_rotated_then_no_model_resets_frontmatter` to test `Ending.UNAVAILABLE` (`"does not support tools"`) followed by `Ending.OUTAGE` and `no-model`, plus AC3 (later model in rotation succeeds).
- **Conflict found**: Moving `set_fields` after `Ending.UNAVAILABLE` causes the existing test `test_the_record_names_the_cli_that_actually_ran_the_session` (`tests/test_jobloop.py:2754`) to fail, because that test dispatches `Ending.UNAVAILABLE` and asserts `task.fields["model"] == "agy/gemini-4-carbon-low"`. Modifying existing tests is prohibited by the job boundary.

TEST
- `python -m pytest tests/test_jobloop.py -q`: `2 failed, 102 passed in 38.52s` (`test_the_record_names_the_cli_that_actually_ran_the_session` failed at `tests/test_jobloop.py:2754` with `AssertionError: assert '-' == 'agy/gemini-4-carbon-low'`; `test_all_models_rotated_then_no_model_resets_frontmatter` failed at `tests/test_jobloop.py:3520` with `AssertionError: assert 'attempt-failed' == 'review'`).

STATUS
needs-owner-decision: Existing test `test_the_record_names_the_cli_that_actually_ran_the_session` (`tests/test_jobloop.py:2754`) asserts that `task.fields["model"]` is set to `"agy/gemini-4-carbon-low"` when `worker.Ending.UNAVAILABLE` is returned, which directly conflicts with T-PH9-420 AC2 (a model that fails during rotation must not remain in `model`). Should `test_the_record_names_the_cli_that_actually_ran_the_session` be updated to use `Ending.COMPLETED` (or `FAILED`) instead of `Ending.UNAVAILABLE`?
