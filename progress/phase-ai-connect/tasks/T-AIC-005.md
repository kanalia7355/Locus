---
id: T-AIC-005
phase: phase-ai-connect
status: doing
assignee: opencode
model: opencode/iceman-free
weight: medium
updated: 2026-11-22T17:11:28+09:00
attempts: 1
allowed_paths: backend/app/harness.py, tests/test_harness_egress.py
test_cmd: python -m pytest tests/test_harness_egress.py tests/test_agents_registry.py tests/test_api.py -q
---

# Task `T-AIC-005`: 外部送信のハーネス層（分類ガードの一点集約）

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR`（必須要件 5・7）。
  **オーナー決定 2026-11-22**:「ハーネス層を作成してそこに分類ガードを置く」。
- **なぜこの票があるか**: 草案の `T-AIC-002` §3 は分類ガードの置き場所を
  「実装時に既存のポリシー判定に合わせる」と**未確定**にしていた。
  未確定のスコープは今日までに 3 件のジョブを止めている
  （`T-PH6-104` は許可パスから外した `service.py` を必要とする受入条件が残っていた）。
  オーナーの指示どおり**置き場所を先に決め、1 つの通り道にする**。
- **設計の要点**: 外部へ出る経路は**この層を通る以外にない**ようにする。
  アダプタ（`T-AIC-001`）は**運び屋**で、判定も資格情報の解決もしない。

  ```
  会話経路 → harness.send(actor, workspace, model, text, citations, on_delta)
                 1. 分類・egress の判定（不明＝拒否）
                 2. 利用者ごとの資格情報の解決（T-AIC-006 の設計に従う）
                 3. 監査（判定結果・宛先・利用者・workspace。本文は残さない）
                 4. アダプタ呼び出し（鍵は引数で渡す）
  ```

- **Implementation Details**:
  1. 新規 `backend/app/harness.py` に `Harness` を実装する。
     公開面は 1 つだけ: `send(...)`。**アダプタを直接呼ぶ経路を他に作らない。**
  2. **判定（分類・egress）**:
     - workspace の `classification_ceiling` と `egress_mode` を読む。
     - `egress_mode` が `local_only` なら**外部送信を拒否**する
       （現在のスキーマは `CHECK(egress_mode IN ('local_only'))` なので、
       いまは**常に拒否**になる。これは正しい。解禁は別の決定であり、
       **この票でスキーマを変更しない**）。
     - 分類が判定できない場合は**拒否**する（「不明＝拒否」。要件 5）。
     - 拒否は `fail(403, ...)` とし、理由に資格情報・URL・本文を含めない。
  3. **資格情報は受け取るだけ**: `Harness` は解決の*呼び出し*を行うが、
     保管方式は `T-AIC-006` の設計が決める。本票では
     `resolve_credential(actor) -> str | None` という**注入される関数**を受け取る形にし、
     既定の実装は「常に `None`（＝未設定として拒否）」とする。
     **本票で鍵の保管・復号・環境変数読み取りを実装しない。**
  4. **監査**: 判定結果（許可／拒否と理由の種別）、利用者、workspace、宛先の種別、
     モデル名を残す。**本文・資格情報・URL の資格情報部分は残さない。**
     既存の監査ポートを使い、新しい監査基盤を作らない。
  5. `loop_engine/**` を変更しない。`backend/app/agents/registry.py` も変更しない
     （ポリシーは**読む**だけ。読み取り関数は注入で受け取る）。

## Acceptance Criteria

1. `tests/test_harness_egress.py` に次の合成テストがある。
   - `egress_mode` が `local_only` の workspace からの送信が **403 で拒否**され、
     アダプタが**一度も呼ばれない**こと（呼ばれたら落ちるスパイで示すこと）。
   - 分類が判定できない workspace からの送信が **403 で拒否**されること。
   - 拒否が監査に残り、**本文・資格情報が監査に現れない**こと。
   - `resolve_credential` が `None` を返すとき**拒否**されること（既定で閉じている）。
   - 許可された場合にアダプタへ渡る引数に、鍵が**引数として**渡ること
     （クラス属性やグローバルに置かれていないこと）。
   - **植える鍵の文字列は決まっている。** `sk-synthetic-01-not-a-real-key` から
     `sk-synthetic-04-not-a-real-key` のいずれかを使うこと
     （複数要るときは別の番号を使う）。
     **これ以外の鍵らしい文字列は secret-scan が落とす。**
     この票の試行 1 が `sk-live-SUPERSECRET` と `sk-test-injected-key` で
     落ちたのは**検査の書き方としては正しく、名前が許可集合の外だっただけ**である。
     許可は `scripts/secret_scan.py` の `SYNTHETIC` にある**完全一致の閉じた集合**で、
     パターンではない（`sk-synthetic-05-...` も末尾を足したものも落ちる。
     `tests/test_secret_scan.py` が両方向を固定している）。
2. **外部送信の経路がこの層以外に無いこと**を示すこと。
   どう確かめたかを報告に書く（grep の条件など）。
3. `python -m pytest tests/test_harness_egress.py tests/test_agents_registry.py tests/test_api.py -q` が PASS。
   `ruff check` / `ruff format --check` が PASS。
4. 既存テストの削除・skip・緩和は禁止。変更は許可パス内に収まる。
   **スキーマを変更しない。** `egress_mode` の `CHECK` を広げない。

## REPORT

- Implemented by:
- Changed Files:
- Summary:

## TEST

- Commands run:
- Results:

## REVIEW

- Reviewer:
- Findings:

## ATTEMPT 1 — implementation by opencode/iceman-free (2026-11-22T17:11:28+09:00)

## REPORT
- `backend/app/harness.py` (new): Added `Harness` as the single external-send choke point. `send(...)` is the only public surface. It reads workspace policy via injected `get_policy`, denies when `egress_mode` is `local_only` or not an explicitly allowed mode, denies when `classification_ceiling` cannot be determined (missing/unknown/`none`), resolves credentials only through injected `resolve_credential(actor) -> str | None` (default returns `None`, so closed by default), emits audit records through the injected existing audit port (`audit` callable, same shape as `service._audit`), and only then calls the injected adapter with `credential=...` as an argument. Denials use `fail(403, "外部送信は許可されていません")` with no credential/URL/body in reason; audit records include actor, workspace, destination type (`external_model`), model name, outcome, and reason type, and never include body/credentials.
- `tests/test_harness_egress.py` (new): Added synthetic tests covering the AC: `local_only` rejects with 403 and adapter spy is never called; unknown/missing classification rejects with 403; denial is audited and audit blob contains no body/credential; default `resolve_credential` returning `None` rejects; allowed injected-policy case calls adapter once and passes key as `credential` argument, with checks that key is not stored on harness/adapter class attrs.

Inconsistencies found between documentation/job intent and existing code:
- T-AIC-005 states "外部送信の経路はこの層を通る以外にない". Current codebase still contains pre-existing HTTP model-call modules outside this ticket's allowed paths: `backend/app/local_model.py` (localhost Ollama via `httpx`) and `backend/app/provider_openai_compatible.py` (OpenAI-compatible endpoint via `httpx`, takes `api_key` arg). I did not modify them (outside `allowed_paths`). I verified with grep: `Select-String -Path backend\app\*.py,backend\app\**\*.py -Pattern 'httpx|requests\.|urllib\.request|aiohttp|openai|http\.client'` shows those two modules plus harness-local references; `Select-String -Path backend\app\*.py,backend\app\**\*.py -Pattern '\bsend\('` excluding `harness.py` shows only `service.send`/conversation flow and `main.py` routing, no harness bypass. The harness is now the designated/implemented single guard for future external egress; wiring existing callers through it is follow-up work outside this ticket.

Risks left behind:
- Existing `local_model.py` / `provider_openai_compatible.py` are not routed through `Harness`; until integrated, the "only this layer" property is enforced for new harness-based paths but not retrofitted to these pre-existing modules.
- The "allowed" path is currently reachable only through injected policy because DB schema constrains `egress_mode` to `local_only`; this is intentional per ticket, but real egress remains closed until a separate decision/schema change and caller integration.
- Harness audit calls the injected audit port directly; when used outside an explicit transaction manager, persistence semantics depend on the caller's DB mode (service uses `isolation_level=None` and its own tx management). Tests confirm audit rows are written with `service._audit`.

## TEST
- `python -m pytest tests/test_harness_egress.py -q` (before fixing a self-inflicted spy assertion) — `5 passed, 1 failed`; failure was in test assertion `secret not in repr(vars(adapter))` because spy stores call args; fixed test to assert key not stored on harness/adapter class attrs per AC intent, no production behavior change.
- `python -m pytest tests/test_harness_egress.py tests/test_agents_registry.py tests/test_api.py -q` — `40 passed in 25.45s`
- `python -m ruff check backend tests scripts jobloop` — `Found 7 errors` (E501/I001 in new files), auto-fixed with `ruff check --fix` and `ruff format`.
- `python -m ruff format --check backend tests scripts jobloop` — `2 files would be reformatted, 186 files already formatted` before fix; after fix `188 files already formatted`.
- `python -m ruff check backend tests scripts jobloop` (after fix) — `All checks passed!`
- `python -m ruff format --check backend tests scripts jobloop` (after fix) — `188 files already formatted`
- `python -m pytest tests/test_harness_egress.py tests/test_agents_registry.py tests/test_api.py -q` (after format/fix) — `40 passed in 25.80s`

## STATUS
ready-for-review

### Controller gates

- `scope`: green
- `task-verification`: green
- `python-lint`: green
- `python-format`: green
- `secret-scan`: FAILED
