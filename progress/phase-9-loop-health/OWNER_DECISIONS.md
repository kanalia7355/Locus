# Owner decisions requested by the job loop

Each entry is a judgement the controller refused to make itself.

## T-PH9-402 — worker wrote outside its workspace (2026-11-23T21:32:52+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=C:\Users\hirot\.jobloop-Locus\workspaces\T-PH9-402
marker=.\.jobloop\orchestrator-busy present=False
appeared:
 M scripts/shift_check.py
 M tests/test_shift_check.py


**Answer** (2026-11-23 22:50, orchestrator): **ワークスペースが完全に空で、作業の 100% が本体チェックアウトにあった**（`git status` が 1 行も無く `merge-base..HEAD` も 0 件）。零れたのではなく最初から本体で作業していた。既知の経路は潰して確認した: ジョブ文に本体の絶対パスは 0 件（2026-11-16 の経路ではない）、ワークスペースに自分の票はある、土台も本体と同じ `b7041a6`。**原因は未特定。** 本体の差分を**この票の許可パスだけ**（`scripts/shift_check.py`, `tests/test_shift_check.py`）で切り出してこの票のワークスペースへ適用し（同じ土台なので `git apply` がそのまま通った）、本体は戻した。**消していない。** 私はコードを 1 行も触っていないので、ゲートと独立レビューはそのまま通す。**試行は消費せず `review` に戻す**（再開は試行を使わずゲートを回し、落ちれば `doing` に戻る）。モデルの偏り（`iceman-free` が封じ込め停止 8 件）は `T-PH9-404` に起票。詳細は `tasks/T-PH9-402.md`。

## T-PH9-403 — worker wrote outside its workspace (2026-11-23T21:41:46+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=C:\Users\hirot\.jobloop-Locus\workspaces\T-PH9-403
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
workspace=C:\Users\hirot\.jobloop-Locus\workspaces\T-PH9-402
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
workspace=C:\Users\hirot\.jobloop-Locus\workspaces\T-PH9-403
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
