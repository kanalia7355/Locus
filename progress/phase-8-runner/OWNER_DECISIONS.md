# Owner decisions requested by the job loop

Each entry is a judgement the controller refused to make itself.

## T-PH8-301 — out-of-scope change (2026-11-20T02:26:50+09:00)



**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job.

**Context**

protected paths touched: ['docs/plans/HBR_DECISION_REGISTER.json']

**Answer** (2026-11-20, orchestrator): 票が矛盾していた。私の不備。本文は成果物を
`docs/plans/...` に置けと書いているのに、そこは保護パス。2026-11-19 の修正指示で
「成果物は `progress/phase-8-runner/material/` へ」と追記したが**本文を直さなかった**ので、
ワーカーは本文に従って保護パスに書いて止まった。本文のパスを書き換え、
`allowed_paths` を `progress/phase-8-runner/material/`（ディレクトリ）に広げ、
ワークスペースの成果物を保護パスから `material/` へ移した（中身は無変更）。
読む対象としての `docs/plans/...` は従来どおり。試行は 0 のまま `todo` に戻した。
受入条件は無変更。詳細は各 `tasks/T-PH8-30X.md`。
## T-PH8-302 — out-of-scope change (2026-11-20T02:44:04+09:00)



**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job.

**Context**

protected paths touched: ['docs/plans/HBR_PROVIDER_EGRESS_DECISION.md']

**Answer** (2026-11-20, orchestrator): 票が矛盾していた。私の不備。本文は成果物を
`docs/plans/...` に置けと書いているのに、そこは保護パス。2026-11-19 の修正指示で
「成果物は `progress/phase-8-runner/material/` へ」と追記したが**本文を直さなかった**ので、
ワーカーは本文に従って保護パスに書いて止まった。本文のパスを書き換え、
`allowed_paths` を `progress/phase-8-runner/material/`（ディレクトリ）に広げ、
ワークスペースの成果物を保護パスから `material/` へ移した（中身は無変更）。
読む対象としての `docs/plans/...` は従来どおり。試行は 0 のまま `todo` に戻した。
受入条件は無変更。詳細は各 `tasks/T-PH8-30X.md`。
## T-PH8-303 — out-of-scope change (2026-11-20T02:57:03+09:00)



**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job. — 4 path(s) the worker wrote outside its scope: fix_parenthesis.py, fix_test.py, fix_test2.py, progress/phase-8-runner/material/HBR_CLASSIFICATION_MODEL.json. Decide whether the job's scope was drawn too narrowly, or whether the worker should not have written them.

**Context**

outside allowed_paths: ['fix_parenthesis.py', 'fix_test.py', 'fix_test2.py', 'progress/phase-8-runner/material/HBR_CLASSIFICATION_MODEL.json']

**Answer** (2026-11-20, orchestrator): 票が矛盾していた。私の不備。本文は成果物を
`docs/plans/...` に置けと書いているのに、そこは保護パス。2026-11-19 の修正指示で
「成果物は `progress/phase-8-runner/material/` へ」と追記したが**本文を直さなかった**ので、
ワーカーは本文に従って保護パスに書いて止まった。本文のパスを書き換え、
`allowed_paths` を `progress/phase-8-runner/material/`（ディレクトリ）に広げ、
ワークスペースの成果物を保護パスから `material/` へ移した（中身は無変更）。
読む対象としての `docs/plans/...` は従来どおり。試行は 0 のまま `todo` に戻した。
受入条件は無変更。詳細は各 `tasks/T-PH8-30X.md`。
## T-PH8-304 — attempt limit reached (2026-11-20T03:12:14+09:00)



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
