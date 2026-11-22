---
id: T-AIC-002
phase: phase-ai-connect
status: todo
assignee: unassigned
model: unassigned
weight: medium
updated: 2026-11-22T13:56:00+09:00
attempts: 0
depends_on: T-AIC-001, T-AIC-005
allowed_paths: backend/app/model_catalog.py, backend/app/main.py, tests/test_model_catalog.py, tests/test_provider_openai_compatible.py
test_cmd: python -m pytest tests/test_model_catalog.py tests/test_provider_openai_compatible.py tests/test_local_model.py -q
---

# Task `T-AIC-002`: カタログ／runtime設定／管理APIの拡張

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR`（必須要件 2・8、実装順序 6「モデル・プロバイダー設定UIと
  既存RAG／Loopへの段階的統合」のバックエンド側）
- **Background**:
  - `ModelCatalog.sources()` は `ollama` とローカルファイルのみで、発見結果は
    `main.py` の discover ハンドラで `source_id == "ollama"` のものだけが
    `runtime.registered` に入る。外部プロバイダのモデルは発見も選択もできない。
  - opencode はモデルカタログを外部サービス（models.dev）から取得するが、
    Locus には自前のカタログ基盤があるため、取得方式は真似ずに
    **既存カタログへの source 追加**で拡張する（PROGRESS §2）。
  - 前提: T-AIC-001（OpenAI互換アダプタ）が done であること。
- **Implementation Details**:
  1. `backend/app/model_catalog.py`:
     - `sources()` に `{"id": "openai-compatible", "label": "OpenAI互換API", "kind": "remote"}`
       を追加する。
     - 発見は `GET {base_url}/models`（Bearer 認証）。**`base_url` と鍵は引数で受け取る**
       （環境変数を読まない。解決はハーネス層の仕事）。
       応答の `data[].id` をモデル候補として正規化し、
       既存の `_record` 形式（id / name / source_id / status）に合わせる。
     - 鍵が解決できない場合は source の status を `unavailable` とし、
       **理由にキーやURLの資格情報部分を含めない**。
     - 既存の安全策（deadline、サイズ上限、MockTransport 注入可能性）は維持する。
  2. `backend/app/main.py`:
     - discover ハンドラの `runtime.registered` 構築を source 別に分岐させ、
       `openai-compatible` の候補はリモート用 runtime の `registered` に入れる。
     - `GET /api/admin/models/runtime` の応答に `provider`（`ollama` |
       `openai-compatible`）と `api_key_present`（リモート時のみ、真偽値）を追加する。
       **キーの値そのものは絶対に含めない。**
     - `PUT /api/admin/models/runtime` は既存フィールド
       （`candidate_id` / `local_only_confirmed` / `timeout_seconds`）を維持したまま、
       候補の source に応じて使う runtime を切り替える。
       リモート候補の場合は `local_only_confirmed` の代わりに、
       **候補が発見済み登録に存在すること**をもって確認済みとする
       （ローカル専用フラグを外部モデルに流用しない）。
     - 監査 `model.configure` の記録先ラベルは provider を含める
       （例: `remote-model-runtime`）。監査にもキー値は書かない。
  3. **分類ガードは本票の仕事ではない。** オーナー決定 2026-11-22 により
     ハーネス層（`T-AIC-005`）に集約した。本票は**会話経路がハーネスを通ること**だけを
     担保する。ハーネスを迂回してアダプタを直接呼ぶ経路を作らないこと。
     （草案は置き場所を「実装時に合わせる」としていたが、`agents/registry.py` も
     service 層も本票の許可パスに入っていなかった。
     書けない場所を要求する票は `T-PH8-301/302/303` と `T-PH6-104` を止めた形である。）
  4. テスト:
     - `tests/test_model_catalog.py` に `/models` 発見の正常系／未設定時 unavailable を追加。
     - 管理API経由の往復（discover → runtime 選択 → 会話応答）は
       `tests/test_provider_openai_compatible.py` 側に MockTransport で追加。
     - runtime 応答・監査にキー値が含まれないこと、分類で拒否されることを検証する。
- **Acceptance Criteria**:
  1. 管理者が discover で OpenAI互換のモデル一覧を取得し、runtime に選択できる。
  2. 選択したリモートモデルで会話応答（通常／ストリーム）が返る。
  3. APIキーの値が runtime 応答・監査・カタログ応答のどこにも現れない。
  4. 会話経路が**ハーネスを通る**こと（アダプタを直接呼ぶ経路が無いこと）。
     分類／egress の拒否そのものの検証は `T-AIC-005` が持つ。
  5. Ollama の発見・選択・応答に退行がない。
  6. 変更が allowed_paths 内に収まっている。
- **Reviewer Model (実装モデルとは別モデルを指定)**: `<未割当>`

---

## REPORT

- **Implemented by**: `<assignee> (<model>)`
- **Attempt**: `0 / 3`
- **Changed Files**:
  - （未記入）
- **Summary**:
  - （未記入）

---

## TEST

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
