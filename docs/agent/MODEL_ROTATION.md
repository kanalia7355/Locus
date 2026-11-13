# モデルローテーションと枠制御 (`MODEL_ROTATION.md`)

本書はタスクの重み（`heavy` / `medium` / `light`）に応じたモデル選択順序、利用枠枯渇（Quota Exhaustion）時の自動切替ルール、および cooldown 管理規約を定義する。
実装ロジックは `.pi/extensions/harness/rotation.ts` および `state.ts` に対応する。

---

## 1. 重み別モデルローテーション表

タスクの重み（オーケストレーター `Luna` がタスク分解時に付与）に従い、以下の候補列を**上から順に**試す。

| 重み (`weight`) | 候補列（上から順に試す） | 主な用途 |
|---|---|---|
| **heavy** | 1. `agy`: `Gemini 4 Argon` (High)<br>2. `agy`: `Claude Opus 5.5`<br>3. `agy`: `Claude Sonnet 5.5` | 複雑なアーキテクチャ変更、セキュリティ・認可境界、難度の高いバグ修正、判断境界のエスカレーションレビュー |
| **medium** | 1. `agy`: `Gemini 4 Argon` (Medium)<br>2. `agy`: `Claude Sonnet 5.5`<br>3. `opencode`: OpenCode 無料プール（12種・カーソル巡回） | 標準的なバックエンド / フロントエンド機能実装、単体・結合テスト作成、通常コードレビュー |
| **light** | 1. `agy`: `Gemini 3.8 Flash`<br>2. `agy`: `GPT-OSS 120B`<br>3. `opencode`: OpenCode 無料プール（12種・カーソル巡回）<br>4. `ollama`: `ollama/gemma3:4b` | 定型的な修正、軽微な UI/文言調整、ボイラープレート生成、軽量な差分確認 |

> **注意（`Gemini 4 Carbon` の除外について）**: `Gemini 4 Carbon` は **対話画面専用・headless（`agy -p --model`）指定不可** である。headless 実行時の Available models に存在せず、指定するとエラーで失敗することが実機で確認済み（2026-11-12/13）のため、自動 dispatch の候補列（特に `light`）からは除外している。

### オーケストレーター（別枠）
- **オーケストレーター + QA**: Codex CLI (`gpt-6-luna`)
  - 起動コマンド: `codex exec --model gpt-6-luna --sandbox workspace-write --full-auto "<prompt>"`
  - 実装ワーカーのローテーションには含めず、割当・状態遷移・QA 照合専任とする。

---

## 2. 各 CLI の呼び出し形式とモデル識別子

### 2.1 Antigravity CLI (`agy` 1.5.5)
- **基本コマンド**:
  ```bash
  agy -p "<prompt>" --model "<表示名>" --dangerously-skip-permissions --print-timeout 30m
  ```
- **モデル指定（headless 指定可能な表示名）**:
  - `Gemini 4 Argon`（effort 目安: heavy は `high`、medium は `medium`）
  - `Gemini 3.8 Flash`
  - `Claude Opus 5.5`
  - `Claude Sonnet 5.5`
  - `GPT-OSS 120B`
  - ※ **`Gemini 4 Carbon` は対話画面専用・headless 指定不可**: `agy -p --model "Gemini 4 Carbon"` を実行すると Available models に存在せずエラー終了することが実機確認済み（2026-11-12/13）のため、自動 dispatch では使用しない。
- **成否判定の原則**: **`agy` の終了コードは信用しない。** 実行の成否は必ず成果物ファイル（進捗報告 md の更新や期待された差分）とテスト結果で判定する。
- **枠プール構造（2プール制）**:
  - `gemini` プール（headless 対象: `Gemini 4 Argon`, `Gemini 3.8 Flash` ※対話画面専用の `Gemini 4 Carbon` も同プール）
  - `claude-gpt` プール（`Claude Opus 5.5`, `Claude Sonnet 5.5`, `GPT-OSS 120B`）
  - それぞれ独立した **5時間枠＋週間枠** を持つ。

### 2.2 OpenCode CLI (`opencode` v2.2.7)
- **基本コマンド**:
  ```bash
  opencode run --model opencode/<slug> --auto "<prompt>"
  ```
- **無料プール対象モデル（12種・実機確認済み）**:
  1. `opencode/beam-free`
  2. `opencode/big-pickle`
  3. `opencode/deepseek-v4.1-flash-free`
  4. `opencode/flint-40b-free`
  5. `opencode/glm-5.3-flash-free`
  6. `opencode/iceman-free`
  7. `opencode/inkling-2-small-free`
  8. `opencode/longcat-2.5-free`
  9. `opencode/mimo-v2.6-flash-free`
  10. `opencode/minimax-m3.1-flash-free`
  11. `opencode/nemotron-3.5-lightning-free`
  12. `opencode/nemotron-3.5-super-vl-free`
- **ローカル最終 fallback（`light` の定型作業のみ）**:
  - `ollama/gemma3:4b`（枠消費ゼロ、`opencode run --model ollama/gemma3:4b --auto "<prompt>"` またはローカル Ollama 経路で実行）

---

## 3. 切替ルールと Cooldown 管理

### 3.1 枠切れ（Quota Exhaustion）の扱い
- **枠切れは「モデルの失敗」ではない**。タスクの試行回数（`attempts`）は増やさず、同じモデルでのリトライも行わずに、即座に候補列の次のモデルへ切り替える。
- 出力に `Individual quota reached ... Resets in <duration>`、`quota reached/exceeded/exhausted`、`usage limit`、`rate limit`、`429` 等が含まれる場合は枠切れと判定する（`rotation.ts` の `isQuotaError()`）。

### 3.2 Cooldown の絶対時刻保持
- 枠切れを検出した場合、`Resets in <hours>h <minutes>m` 等から解除時刻を算出し、`.pi/harness/state.json` の `cooldowns` 配列に **ISO 8601 の絶対時刻 (`until`)** として記録する。
- リセットまでの時間がメッセージから読み取れない場合は、既定値として **5時間（`DEFAULT_COOLDOWN_MS = 5 * 60 * 60 * 1000`）** の cooldown を設定する。
- Cooldown 中のモデルまたはプールは `filterAvailable()` により候補列から自動的に除外され、プロセス再起動後も `.pi/harness/state.json` から引き継がれる。

### 3.3 レビュー担当モデルの分離ルール
- `status: review` のタスクにレビューワーカーを割り当てる際、**そのタスクを実装したモデル（進捗ファイルの `model` に記録されているモデル）とは別のモデル**を候補列から選択しなければならない。

### 3.4 OpenCode 無料プールのカーソル巡回と QA 通過率の集計
- OpenCode 無料プールの内部順序は固定せず、`.pi/harness/state.json` の `freeCursor` を用いて `OPENCODE_FREE_MODELS[freeCursor % 12]` で順番に回す。
- **QA 通過率の集計**:
  - 各タスク進捗ファイル（`progress/<phase>/tasks/<TASK-ID>.md`）の frontmatter と履歴、および `progress/<phase>/PROGRESS.md` のモデル別実績テーブルに「担当モデル・試行回数・QA 通過（`done`）/ 差し戻し回数」を記録し、モデルごとの QA 通過率を集計・追跡できる形を維持する。

### 3.5 全候補が枯渇した場合の振る舞い
候補列のすべてのモデルが cooldown 中または利用不能となった場合は、以下の順序で対処する（**無言で停止してはならない**）：
1. **待機**: Cooldown 終了時刻（`until`）が最も早いモデルが復帰するまで待機する。
2. **ローカル fallback**: タスクの重みが `light`（定型作業）である場合は、`ollama/gemma3:4b` へフォールバックする。
3. **Blocked 化と人間への通知**: 上記でも実行できない場合は、タスクの `status` を `blocked` に更新し、`PROGRESS.md` およびタスク進捗ファイルに「全候補モデルの枠枯渇および最短解除予定時刻 (`until`)」を明記して人間へ通知する。
