---
id: T-AIC-001
phase: phase-ai-connect
status: todo
assignee: unassigned
model: unassigned
weight: medium
updated: 2026-11-22T13:56:00+09:00
attempts: 0
allowed_paths: backend/app/provider_openai_compatible.py, backend/app/main.py, tests/test_provider_openai_compatible.py
test_cmd: python -m pytest tests/test_provider_openai_compatible.py tests/test_local_model.py -q
---

# Task `T-AIC-001`: 共通プロバイダIF＋OpenAI互換アダプタ（バックエンド）

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR`（`docs/planning/locus-hybrid-agent-requirements.md` 必須要件 5・8、
  実装順序 2「共通Adapter」）
- **Background**:
  - 実働するモデル接続は `backend/app/local_model.py`（Ollama、127.0.0.1:11434）のみで、
    外部AIサービスへの接続実装が存在しない。
  - 参考: opencode は「プロバイダ契約→プロトコル別Route→トランスポート」の分離で
    多数のプロバイダを吸収している（`packages/core/src/provider.ts`、
    `packages/ai/src/providers/*`）。Locus では既存の会話経路が
    `runtime.generate(model, text, citations, timeout_seconds, on_delta)` の注入で
    動いているため、このシグネチャ互換のアダプタを並べるのが最小の接続方法になる。
- **Implementation Details**:
  1. 先に `backend/app/local_model.py` と `backend/app/main.py` の
     `generate` クロージャ（通常系／ストリーム系の2箇所）を読む。
  2. 新規 `backend/app/provider_openai_compatible.py` に
     `OpenAICompatibleModel` クラスを実装する。公開シグネチャは `LocalModel` と同一:
     - `configure(candidate, local_only, timeout_seconds)` / `status()` / `validate(...)` /
       `available()` / `generate(model, text, citations, timeout_seconds=None, on_delta=None)`
     - 内部差分は接続先と認証とワイヤ形式のみ:
       - POST `{base_url}/chat/completions`（OpenAI互換 Chat Completions 形式）。
         `base_url` は環境変数 `LOCUS_OPENAI_COMPATIBLE_BASE_URL` から読む
         （未設定なら configure を 422 で拒否）。
       - 認証は環境変数 `LOCUS_OPENAI_COMPATIBLE_API_KEY` を `Authorization: Bearer` に
         付ける。**値はクラス属性・例外メッセージ・ログ・`status()` の戻り値に含めない**
         （`status()` に出してよいのは `api_key_present: bool` まで）。
       - system プロンプトは `LocalModel._payload` と同一文面・同一の資料JSON形式を使う
         （資料内命令を実行させない方針をプロバイダ間で変えない）。
       - ストリーミングは SSE（`data:` 行、終端 `[DONE]`）をパースし、
         断片ごとに検証してから `on_delta` へ渡す。
  3. 応答検証は `LocalModel` の水準に合わせる:
     - HTTP 200 以外、モデル名不一致、空応答、長さ上限（20,000字）超過は不正応答。
     - **`tool_calls` を含む応答は拒否する**（ゼロツール境界。PROGRESS §3-1）。
     - 失敗は `fail(502, ...)` とし、**自動再送はしない**。
     - 同時実行は単一スロット（`threading.Lock` の非ブロッキング取得、占有時は 429）。
  4. `backend/app/main.py` の変更は最小限: `create_app` に
     `remote_model` 引数を追加し、会話経路の `runtime` 選択箇所だけを触る。
     既定（引数なし）は従来どおり `LocalModel`。**本タスクでは選択ロジック
     （どちらを使うかの決定）は実装しない**——それは T-AIC-002 の仕事で、
     ここでは差し替え可能であることの実証まで。
  5. テスト `tests/test_provider_openai_compatible.py` を新規作成する。
     `tests/test_local_model.py` と同型に、`httpx.MockTransport` のみを使い、
     **実ネットワークへ一切出ない**こと:
     - 正常応答（通常／ストリーム）の往復と、リクエストヘッダに
       Bearer が付いていること（テスト用ダミー値で検証）
     - APIキー未設定時の configure 拒否、`status()` にキー値が含まれないこと
     - `tool_calls` 付き応答・モデル名不一致・空応答・非200 の拒否
     - 占有時の 429、設定変更時の `validate` 409
- **Acceptance Criteria**:
  1. MockTransport 上で OpenAI互換エンドポイントとの通常／ストリーム応答が往復できる。
  2. APIキーの値が `status()`・例外・テスト出力のどこにも現れない。
  3. `tool_calls` 付き応答が拒否され、ツール実行に繋がらない。
  4. `tests/test_local_model.py` を含む既存テストに退行がない。
  5. 変更が allowed_paths 内に収まっている。
- **Reviewer Model (実装モデルとは別モデルを指定)**: `<未割当>`

---

## REPORT

<!-- 担当実装ワーカー (Implementer) のみが記入する。 -->

- **Implemented by**: `<assignee> (<model>)`
- **Attempt**: `0 / 3`
- **Changed Files**:
  - （未記入）
- **Summary**:
  - （未記入）

---

## TEST

<!-- .pi/skills/test-scope/SKILL.md に従い、関連テストのみを実行し、
     実際に実行したコマンドと結果を正確に記録すること。 -->

- **Executed Commands**:
  - （未記入）
- **Result**:
  - （未記入）
- **Unmapped Changes (Phase 節目で確認が必要な変更ファイル)**:
  - なし

---

## REVIEW

### Review Cycle 1
- **Reviewer**: `<assignee> (<model>)`
- **Date**: `<ISO8601>`
- **Verdict**: `PENDING` (`APPROVED` | `CHANGES_REQUESTED` | `BLOCKED`)
- **Findings**:
  - （未実施）
