---
id: T-AIC-007
phase: phase-ai-connect
status: review
assignee: opencode
model: opencode/flint-40b-free
weight: light
depends_on: T-AIC-002
allowed_paths: backend/app/main.py, tests/test_model_catalog.py
test_cmd: python -m pytest tests/test_model_catalog.py -q
updated: 2026-11-26T11:48:32+09:00
attempts: 0
reviewer: agy/gemini-4-carbon-low
---

# Task `T-AIC-007`: リモートモデルを無効にしたとき、資格情報と応答の形を後始末する

## SCOPE — レビュアーへ（先に読むこと）

- **この票は `T-AIC-002` のやり直しではない。** あの票の受入条件は
  discover と選択・会話応答・**API キーの値が runtime 応答／監査／カタログ応答に
  現れないこと**・会話経路がハーネスを通ること・Ollama の退行なし・許可パス内の 6 つで、
  **プロセス内のメモリに残ることと、未設定時の応答の項目の揃え方は名指ししていない**。
  だからこの票に分けた。
- **判断はこの票の受入条件に対して行うこと。** 条件の外で気づいたことは
  `## REVIEW` に所見として書き、`CHANGES_REQUIRED` の理由にしないこと。

## TASK DEFINITION (Assigned by Orchestrator)

- **なぜこの票があるか**: 2026-11-25 15:20 の `T-AIC-002` のレビューが Low として
  挙げた 2 件がそのまま根拠である。どちらも本物だが、あの票の受入条件の外にある。

- **1 件目: 無効にしても資格情報がメモリに残る**
  - `backend/app/main.py`（`discover_models` の末尾、`remote_runtime._base_url` と
    `remote_runtime._api_key` を置く箇所。2026-11-25 18:50 時点で 831〜834 行目付近）。
    discover が成功すると `_base_url` / `_api_key` が `remote_runtime` に残る。
    **モデルを無効にする経路（`candidate_id` が `None`）で消していない**ので、
    無効にした後もプロセスの中に残り続ける。
  - **これは漏洩ではない**（`T-AIC-002` の受入条件 3 が守る「応答・監査・カタログに
    値が現れない」は別に満たされている）。残すべきでないものを残しているという話である。

- **2 件目: 未設定時の応答の項目が、ローカルとリモートで揃っていない**
  - `backend/app/main.py` の `model_runtime` の GET（同 841〜857 行目付近）。
    動いている runtime がリモートで、まだモデルを選んでいないとき、応答は
    `api_key_present: False` を持つ（`OpenAICompatibleModel.status()` が固定で返す）が
    `provider` は付かない。ローカルの未設定時は `api_key_present` を**そもそも出さない**。
    **同じ「未設定」で項目の集合が違う**ので、画面側が二通りの形を扱う必要が出る。

- **Implementation Details**:
  1. 無効にする経路で `_base_url` / `_api_key` を消すこと。
     **消す場所は 1 つにまとめること**（無効化が複数の入口から呼ばれるなら、
     後始末を関数にして呼ぶ）。
  2. 未設定時の応答の項目をどちらかに揃えること。
     **どちらに揃えたかと、その理由を REPORT に書くこと**
     （`api_key_present` を両方出す／両方出さない、どちらでもよい）。
     既に画面側が読んでいる項目を消すなら、**消して困らないことを確かめてから**にする
     （`frontend/` はこの票の許可パスの外なので、読んで確かめるだけ。変更しない）。
  3. `OpenAICompatibleModel.status()` は許可パスの外である。そこを直す必要があると
     判断した場合は、**直さずに REPORT に書いて次の票へ回すこと**。

## ACCEPTANCE CRITERIA

1. リモートモデルを無効にした後、`_base_url` と `_api_key` が残っていないことを
   示すテストがある（discover で設定 → 無効化 → 消えていることを確認）。
2. 無効化が複数の入口から起きる場合、**どの入口からでも消える**ことを示すテストがある。
   入口が 1 つだけなら、1 つであることを REPORT に書けばよい。
3. 未設定時の応答の項目が、ローカルとリモートで**同じ集合**であることを示すテストがある。
4. `T-AIC-002` の受入条件 3（API キーの値が runtime 応答・監査・カタログ応答の
   どこにも現れない）に**退行がない**ことを示すテストが、引き続き緑である。
5. `python -m pytest tests/test_model_catalog.py -q` が緑。
   `python -m ruff check backend tests scripts jobloop` と
   `python -m ruff format --check backend tests scripts jobloop` が緑。
   `python scripts/secret_scan.py <変更したファイル>` が 0 findings。
6. 資格情報らしい文字列を検査に埋める必要がある場合は、**走査が許している値だけ**を
   使うこと（`sk-synthetic-0N-not-a-real-key` の形。他の値は走査が落ちる）。
7. 変更が `allowed_paths` 内に収まっている。

## CONTAINMENT UNVERIFIED (2026-11-25T20:26:07+09:00)

The operator was editing the main checkout during this cycle, so the containment comparison was suspended. The worker's isolation was not verified for this attempt.

## ATTEMPT 1 — implementation by opencode/flint-40b-free (2026-11-25T20:26:12+09:00)

Baseline is green (24 passed, 2 skipped). Now let me add the failing regression tests first, per the method.Both new tests fail exactly as the job predicted. Now let me implement the fix in `backend/app/main.py`.The target suite is green. Now checking the neighboring suites for regressions.The scan flagged my synthetic key: the scanner only allows the closed set `sk-synthetic-0[1-4]-not-a-real-key`. Let me use an allowed fixture value.mypy was already red at HEAD (7 pre-existing errors); my early-return added one more of an already-existing error class. Let me restructure the GET to keep the original single-return shape and avoid adding new mypy errors.The only runtime-disable entry is the `candidate_id: null` branch of the single `PUT /api/admin/models/runtime` handler — confirmed single-entry. Let me strengthen the disable test's response assertion.Final regression sweep of the neighboring suites against the finished code:REPORT
- what I changed and why, file by file:
  - `backend/app/main.py`:
    - Added a `clear_remote_runtime_credentials()` helper inside `create_app` (after the chat-runtime proxy): drops `remote_runtime._base_url` / `remote_runtime._api_key` under the remote runtime's settings lock.
    - `PUT /api/admin/models/runtime` disable branch (`candidate_id is None`): after the disable `configure`, when the disabled target is the remote runtime it now calls the clearing helper, so the discovered endpoint/key do not survive in process memory; the disabled answer also drops `api_key_present` so a disabled runtime answers with the same item set as a never-configured one.
    - `GET /api/admin/models/runtime`: when no model is configured, the adapter-fixed `api_key_present` is dropped, so the unconfigured response carries the same item set for local and remote runtimes.
  - `tests/test_model_catalog.py`:
    - `test_disabling_remote_model_clears_endpoint_and_key`: discover (openai-compatible) → configure → disable, then asserts the endpoint and key are cleared and the disable answer is unconfigured-shaped.
    - `test_unconfigured_runtime_response_shape_is_local_and_remote_equal`: unconfigured runtime response must equal the local unconfigured status (same item set, no `provider`/`api_key_present`).
- decision taken for the "unconfigured response items" alignment: **both omit `provider`/`api_key_present` when no model is configured**. Reason: the never-configured local shape is pinned by existing exact-equality assertions in `tests/test_local_model.py` (outside this task's allowed paths, so not modifiable here), and the frontend (`frontend/src/ModelRuntime.tsx`) only renders provider/API-key lines when `current.provider` is present, so omitting unconfigured fields is safe without touching `frontend/` (read-only during this task).
- inconsistency found between documentation and code: the pre-existing code comment ("Only add provider/api_key_present when a model is configured. This preserves backward compatibility…") already encoded the intended unconfigured shape; the defect was that `OpenAICompatibleModel.status()` unconditionally emitted `api_key_present` and the handler never neutralized it for the unconfigured case.
- risk left behind: after disable, the chat-runtime proxy still references the remote runtime object as its active target (now credential-free, model=None), so generation stays guarded by the `if not model` checks; registered-candidate bookkeeping (`registered`/`registered_sources`) is not cleared on disable, which was outside this task's scope.

TEST
- Commands and real results:
  - `python -m pytest tests/test_model_catalog.py -q` → `26 passed, 2 skipped in 5.41s` (the 2 skips are pre-existing Windows symlink-fixture skips; before my change the same file was `24 passed, 2 skipped`).
  - `python -m ruff check backend tests scripts jobloop` → `All checks passed!`
  - `python -m ruff format --check backend tests scripts jobloop` → `192 files already formatted`
  - `python scripts/secret_scan.py backend/app/main.py tests/test_model_catalog.py` → `Offline secret scan: 0 findings`
  - Neighboring regression suites (`tests/test_provider_openai_compatible.py`, `tests/test_local_model.py`, `tests/test_model_slots.py`, `tests/test_chat_queue.py`, `tests/test_chat_drain.py`, `tests/test_api.py`, `tests/test_audit_regressions.py`, `tests/test_security.py`) → `116 passed`.
  - `python -m mypy backend/app` → 7 pre-existing errors, identical set to the unmodified HEAD baseline (verified via stash); no new type errors introduced.
- Failures first, then fix: both new tests failed before the implementation (disable test: `assert remote._base_url is None` → got `'https://api.example.invalid/v1'`; unconfigured-shape test: response contained extra `{'api_key_present': False}` vs local shape). After the implementation: all green as above.

STATUS
ready-for-review

### Controller gates

- `scope`: green
- `task-verification`: green
- `python-lint`: green
- `python-format`: green
- `secret-scan`: green

## RESUMED GATES (2026-11-26T11:48:32+09:00)

- `scope`: green
- `task-verification`: green
- `python-lint`: green
- `python-format`: green
- `secret-scan`: green

## REVIEW by agy/gemini-4-carbon-low (2026-11-26T11:50:12+09:00)

VERDICT
- APPROVED

FINDINGS
- Medium, backend/app/main.py:895-937 (`configure_model`): `clear_remote_runtime_credentials()` is only invoked in the `candidate_id is None` branch when `target is remote_runtime`, leaving two sequences where `remote_runtime` is unconfigured/inactive while its `_base_url` and `_api_key` survive in process memory: (1) admin discovers `openai-compatible` with `base_url`/`api_key`, never selects a remote candidate (`chat_runtime.active` remains `runtime`), and calls `PUT /api/admin/models/runtime` with `candidate_id: None` — `target is remote_runtime` is `False`, so the helper is skipped and `remote_runtime._base_url`/`_api_key` remain set; (2) admin discovers and configures a remote model (`chat_runtime.active = remote_runtime`), then switches directly to a local Ollama candidate via `PUT /api/admin/models/runtime` (`candidate_id: <ollama_id>`) — `chat_runtime.active` switches to `runtime` without disabling or clearing `remote_runtime`, leaving `_base_url`/`_api_key` in memory (and `remote_runtime.model` still populated on the inactive instance). Not treated as `CHANGES_REQUIRED` per the task's `## SCOPE` instruction because AC1/AC2 specify the explicit disable path (`candidate_id is None` after remote selection). Smallest fix (for a follow-up): call `clear_remote_runtime_credentials()` unconditionally in the `candidate_id is None` branch, and when switching `chat_runtime.active` from `remote_runtime` to `runtime`, reset `remote_runtime` (`remote_runtime.configure(None, False)`) and call `clear_remote_runtime_credentials()`.

UNVERIFIED
- Did not re-run `pytest`, `ruff`, `mypy`, or `secret_scan.py` (relied on the deterministic controller gate results provided in the prompt, per instructions; note 2 symlink tests in `tests/test_model_catalog.py` were skipped due to Windows symlink privileges).
- Neighboring test suites (`tests/test_provider_openai_compatible.py`, `tests/test_local_model.py`, frontend Vitest suite) were inspected statically by reading source files rather than executed in this review session, as `task-verification` runs `tests/test_model_catalog.py` only.
- Live HTTP behavior against a real OpenAI-compatible server was not verified (tests use `httpx.MockTransport`).
