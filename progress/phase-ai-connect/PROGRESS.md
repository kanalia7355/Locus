# Phase `phase-ai-connect`: AIエージェント／プロバイダ接続の実装

- **作成**: 2026-11-22（owner 依頼による計画起票。実装の着手承認ではない）
- **目的**: Locus から外部AIプロバイダ／エージェントサービスへ接続できるようにする。
  現状は実働するモデル接続が Ollama ローカルのみで、外部接続の実装が見当たらない、
  という owner の困りごとへの対応。
- **Requirement IDs**: `HBR`（ハイブリッド基盤要件、`docs/planning/locus-hybrid-agent-requirements.md`）
  実装順序 2〜5 に対応する残部のうち、境界を壊さず進められる部分を切り出したもの。

---

## 1. 現状確認（2026-11-22、main ブランチ実コードで確認済み）

| 対象 | 状態 |
|---|---|
| `backend/app/local_model.py` | **唯一の実働モデル接続**。Ollama `http://127.0.0.1:11434/api/chat` へ httpx で POST。単発応答＋ストリーミング、`generate(model, text, citations, timeout_seconds, on_delta) -> (answer, model)`。ツールなし・再送なし・認証なしが明示された設計 |
| `backend/app/model_catalog.py` | モデル発見は Ollama `/api/tags` とローカルファイルのみ。`sources()` は `ollama` ＋ ファイルルート |
| `backend/app/agents/registry.py` | **metadata-only**。冒頭 docstring が「runner を実行しない／adapter を有効化しない／認証情報を処理しない／egress を開けない」と明記。`adapter_credentials` は presence-only（値の列を持たない）ことが回帰ガード付き |
| `POST /api/workspaces/{id}/agent-dispatch-attempts`（`backend/app/main.py`） | 実体は `registry.dispatch_attempt()` で、**常に 409 `Runner boundary is unproven; dispatch is disabled`** を返す拒否専用エンドポイント |
| `docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md` | Codex / Claude Code / Gemini CLI の認証供給方式（§4〜§6）と検証計画（§9）まで設計済み。ただし §12 で activation は未承認 |
| `loop_engine/model_gate.py` | C-min の閉じた契約検証のみ。I/O・認証情報を持たない（ゼロツール境界） |

**結論**: 実装が「見つからない」のは欠落ではなく、dispatch を開ける前提
（Runner 境界の証明）が未完了のため意図的に止められている。
一方、チャット／RAG 用途の **API プロバイダ接続はその前提なしに実装可能** で、
本フェーズはそちらを先行する。

## 2. 参考実装: opencode（github.com/anomalyco/opencode、dev ブランチ確認）

Locus への対応づけのみを借りる。コードの移植はしない。

| opencode の層 | ファイル | Locus での対応 |
|---|---|---|
| プロバイダ契約 `model(modelID, settings)`、パッケージ動的ロード | `packages/core/src/provider.ts` | 共通IFを `LocalModel.generate` のシグネチャに寄せて新アダプタを並べる（T-AIC-001） |
| プロトコル別 Route（Responses / Chat / Messages / Gemini 等）と統一イベントへの正規化 | `packages/ai/src/providers/*`, `packages/ai/src/protocols/*` | 最初は OpenAI互換 Chat の1プロトコルのみ。Anthropic 等は後続タスクで追加 |
| 認証の抽象化（Bearer / 任意ヘッダ、解決は実行時に遅延） | `packages/ai/src/route/auth.ts` | APIキーは環境変数からのみ解決し、DB・API応答には **presence（有無）だけ**を出す。既存の presence-only 原則と一致させる |
| モデルカタログ（models.dev を取得・キャッシュ） | `packages/core/src/models-dev.ts` | **真似しない**。Locus 既存の `ModelCatalog` を拡張する（T-AIC-002） |
| エージェント実行ループ（tool call の往復） | `packages/ai/src/llm.ts`, `packages/core/src/session/runner/llm.ts` | 本フェーズでは実装しない。ツール実行は C-min ゼロツール境界の外（別モジュール／Runner 側）の仕事（T-AIC-004） |
| Claude Agent SDK を LanguageModel としてラップ／ACP サーバ化 | `packages/core/src/plugin/provider/claude-agent/`, `packages/cli/src/acp/agent.ts` | CLI エージェントは自前再実装せず、公式CLI／opencode を外部アダプタとして呼ぶ案の根拠（T-AIC-004） |

## 3. 本フェーズの境界（全タスク共通・変更不可）

1. **ゼロツール境界を維持する**：本フェーズのアダプタはテキスト応答のみ。
   `tool_calls` を含む応答は `LocalModel` と同様に不正応答として拒否する。
   ファイル編集・コマンド実行を伴うエージェント実行は T-AIC-004 の設計ゲートを通すまで実装しない。
2. **認証情報の値を保持しない**：APIキーはサーバ環境変数からのみ読む。
   DB スキーマ・管理API・監査ログ・フロントに値を出さない（presence のみ）。
   `adapter_credentials` の presence-only 回帰ガードを壊さない。
3. **分類ポリシーを先に通す**：外部送信は workspace の分類上限
   （`classification_ceiling` / `egress_mode`）の判定を通過した場合のみ。
   分類不明・上限超過は送信前に拒否し、監査に残す。
4. **自動再送をしない**：`LocalModel` の既存方針（失敗は 502、自動リトライなし）を踏襲する。
5. **`loop_engine/**` を変更しない**：ガバナンス文書（`docs/agent/CONSTRAINTS.md` §5.3、
   `docs/agent/PROTOCOL.md` §2）がエージェントによる変更を禁じているため、
   本フェーズの allowed_paths には含めない。
6. **dispatch の 409 は本フェーズでは外さない**：T-AIC-001〜003 は
   既存の会話経路（`runtime.generate` 注入）を使うため dispatch 解禁は不要。
   解禁は T-AIC-004 の owner 決定事項。

## 4. タスク一覧

| ID | タイトル | 状態 | 依存 |
|---|---|---|---|
| T-AIC-001 | 共通プロバイダIF＋OpenAI互換アダプタ（バックエンド） | todo | なし |
| T-AIC-002 | カタログ／runtime設定／管理APIの拡張 | todo | T-AIC-001 |
| T-AIC-003 | 管理画面のプロバイダ選択UI（ModelSettings / ModelRuntime） | todo | T-AIC-002 |
| T-AIC-004 | CLIエージェント・アダプタの設計ゲート（設計のみ・owner決定事項） | blocked（owner決定待ち） | T-AIC-001〜003 の完了は不要。着手自体に owner 承認が要る |

## 5. 完了条件（フェーズ）

1. 管理者が OpenAI互換エンドポイントのモデルを発見・選択し、
   会話画面から外部モデルの応答（通常／ストリーミング）を受け取れる。
2. APIキーの値が DB・API応答・ログ・画面のどこにも現れないことがテストで検証されている。
3. 分類上限を超える workspace から外部モデルへ送信できないことがテストで検証されている。
4. Ollama ローカルモデルの既存挙動に退行がない（`tests/test_local_model.py` 等が green）。
5. dispatch の 409 拒否と presence-only ガードは従来どおり維持されている。

## ORCHESTRATOR — 票の配管だけ直した。設計は 1 行も変えていない (2026-11-22 14:10)

オーナーの草案を実行可能にするための機械的な修正のみ。
**境界（§3）・受入条件・実装方針は 1 つも変えていない。**
直した理由はすべて実測で確認したもの。

1. **ループがジョブを 1 件も見ていなかった。** `load_phase` は
   `progress/<phase>/tasks/*.md` を読むので、`progress/phase-ai-connect/` 直下では
   `phase phase-ai-connect: 0 job(s)` だった（実測）。`tasks/` に移した。
2. **`test_cmd` の `.venv313/Scripts/python.exe` はワークスペースに存在しない。**
   `.venv313` は `.gitignore` の `.venv*/` に入っており、ワークスペースへ共有されるのは
   `frontend/node_modules` と `.venv` の 2 つだけ（`share_installed_dependencies`、実測）。
   また `with_interpreter` が束縛するのは**裸の `python`** だけなので、
   パス指定はそのまま残って「見つからない」で落ちる。裸の `python` に直した
   （これが task ファイルの約束で、コントローラが自分の解釈器を当てる）。
3. **`depends_on` が本文にしかなかった。** frontmatter には無かったので
   `depends_on=[]`（実測）。コントローラは**軽いジョブを先に選ぶ**ので、
   `light` の `T-AIC-003` が `T-AIC-001` より先に走るところだった。
   `002 → 001`、`003 → 002` を frontmatter に入れた。
4. **`T-AIC-004` の `allowed_paths` が 2 つとも保護パスだった**
   （`docs/plans/`、`docs/planning/`。実測）。ジョブは保護パスに書けないので、
   範囲の検査が**絶対に通らない**票だった。`T-PH8-301/302/303` が同じ形で止まった
   先例があるので、同じ前例に倣って `progress/phase-ai-connect/material/` にした。
   **読む対象としての `docs/plans/...` は従来どおり**（読めるが書けない、の区別）。
   成果物を `material/` に置き、確定後にオーナーが設計正本へ反映する。
5. **`T-AIC-004` の `test_cmd: none (設計タスク...)`** はシェルにそのまま渡されて
   落ちる。`actionable` も偽になる（`test_command` が必要）。
   設計票でも「壊していないこと」を示す検査は要るので、
   `tests/test_agents_registry.py`（dispatch の 409 と presence-only の回帰ガード）を
   指定した。**受入条件 4「コード・スキーマ・dispatch を一切変更していない」を
   機械で確かめる**ことになる。

オーナーに決めていただきたい点は別途報告する（APIキーの置き場、分類ガードの置き場、
`T-AIC-004` の 4 つの決定事項）。
