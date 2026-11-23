# Owner decisions requested by the job loop

Each entry is a judgement the controller refused to make itself.

## T-PH9-402 — worker wrote outside its workspace (2026-11-23T21:32:52+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=C:\Users\hirot\.jobloop-Locus\workspaces\T-PH9-402
marker=C:\Users\hirot\Locus\.jobloop\orchestrator-busy present=False
appeared:
 M scripts/shift_check.py
 M tests/test_shift_check.py


**Answer** (2026-11-23 22:50, orchestrator): **ワークスペースが完全に空で、作業の 100% が本体チェックアウトにあった**（`git status` が 1 行も無く `merge-base..HEAD` も 0 件）。零れたのではなく最初から本体で作業していた。既知の経路は潰して確認した: ジョブ文に本体の絶対パスは 0 件（2026-11-16 の経路ではない）、ワークスペースに自分の票はある、土台も本体と同じ `b7041a6`。**原因は未特定。** 本体の差分を**この票の許可パスだけ**（`scripts/shift_check.py`, `tests/test_shift_check.py`）で切り出してこの票のワークスペースへ適用し（同じ土台なので `git apply` がそのまま通った）、本体は戻した。**消していない。** 私はコードを 1 行も触っていないので、ゲートと独立レビューはそのまま通す。**試行は消費せず `review` に戻す**（再開は試行を使わずゲートを回し、落ちれば `doing` に戻る）。モデルの偏り（`iceman-free` が封じ込め停止 8 件）は `T-PH9-404` に起票。詳細は `tasks/T-PH9-402.md`。

## T-PH9-403 — worker wrote outside its workspace (2026-11-23T21:41:46+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/iceman-free
workspace=C:\Users\hirot\.jobloop-Locus\workspaces\T-PH9-403
marker=C:\Users\hirot\Locus\.jobloop\orchestrator-busy present=False
appeared:
 M jobloop/controller.py
 M jobloop/diagnose.py
 M tests/test_diagnose.py
 M tests/test_jobloop.py

**Answer** (2026-11-23 22:50, orchestrator): `T-PH9-402` と同じ形で、同じ扱いにした。**ワークスペースは完全に空**で、作業の 100%（`jobloop/controller.py`, `jobloop/diagnose.py`, `tests/test_jobloop.py`, `tests/test_diagnose.py`）が本体にあった。許可パスで機械的に切り分けたので `T-PH9-402` の分と混ざっていない。本体は戻し、作業はこの票のワークスペースへ移送した。**試行は消費せず `review` に戻す。** 原因は未特定で、計測は `T-PH9-404`。詳細は `tasks/T-PH9-403.md`。
