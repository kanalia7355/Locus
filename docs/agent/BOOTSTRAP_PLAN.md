# Locus ハーネス ブートストラップ計画 (`BOOTSTRAP_PLAN.md`)

作成日時: 2026-11-12T14:15:00+09:00
作成者: Antigravity CLI (`agy` / Gemini 4 Argon)

本計画書は `AGY_BOOTSTRAP_PROMPT.md` §6-2 に基づき、自律開発ループ用ハーネスの残り一式を生成・整理する手順を定める。

---

## 1. 現状把握と既存生成物の検証結果

1. **配置済みコア (`.pi/extensions/harness/`)**
   - `index.ts`, `config.ts`, `state.ts`, `poll.ts`, `rotation.ts`, `testscope.ts`, `git.ts`, `runners/{exec,codex,agy,opencode}.ts`, `tsconfig.json` がすべて配置済みであることを確認した。
   - **仕様の要点（生成物と整合させる前提）**:
     - `config.ts`: `pollIntervalMs = 30 * 60 * 1000` (30分)、`lunaModel = "gpt-6-luna"`、`agyPrintTimeout = "30m"`、`processTimeoutMs = 35 * 60 * 1000`、`stateFile = ".pi/harness/state.json"`、`progressDir = "progress"`、`promptsDir = ".pi/harness/prompts"`。
     - `index.ts`: `.pi/harness/prompts/orchestrator.md` を読み込み、`## 今回のポーリング差分` を末尾に付与して `runLuna()` を起動する。
     - `poll.ts`: `progress/` 配下の全 `.md` ファイルを走査し、先頭の `--- ... ---` から単純な `key: value` 行を抽出し、`status` または `updated` が存在するファイルを追跡対象とする。
     - `rotation.ts`: `heavy` / `medium` / `light` の重み別候補列、`*opencode-free*` マーカーの `freeCursor` 解決、`Resets in ...` からの cooldown 解析（既定5時間）を実装済み。
     - `testscope.ts`: `progress/`, `docs/`, `.pi/` および全 `.md` ファイルをテスト対象外とし、Python (`tests/**/test_<stem>.py` → `python -m pytest <rel> -x -q`) と JS/TS (`*.{test,spec}.{ts,tsx}` → `npm --prefix frontend test -- <rel>`) を解決する。対応付け不能なファイルは `unmapped` に分類する。
   - 本ディレクトリ配下は §0・§7 に従い **一切改変しない**。
2. **既存の `.pi/settings.json`**
   - 検証結果: JSON 構文としては有効（パース可能）だが、中身は pi 公式の `settings.json` スキーマではなく、`pi` / `codex` / `agy` / `opencode` / `superpowers` / `workflow` を記述した §0 記載の「ハーネスの構成メモ」形式であることを確認した。
   - 処置計画 (§4-12): 内容を欠損なく `docs/agent/HARNESS_MANIFEST.json` へ移行（および `rotation.ts` / `config.ts` との対応関係を補完整理）したうえで、`.pi/settings.json` を削除して pi の既定動作に戻す。
3. **既存の `.pi/harness/state.json`**
   - 検証結果: `state.ts` の `HarnessState` (`version: 1`, `lastPollAt`, `progressSnapshot`, `cooldowns`, `freeCursor`, `lastCycleNote`) に完全準拠した有効な JSON。ただしランタイム生成物であるため `.gitignore` の除外対象に追加する。
4. **リポジトリルート直下の `index.ts` および `state.ts`（前回の無料モデル試行の残骸）**
   - 検証結果: ルート直下の `index.ts`（8行目に `#` 構文エラーあり、存在しない `./poll` を import）と `state.ts`（`const hasActive = false; hasActive = true;` 等の型・構文エラーあり、`.pi/extensions/harness/state.ts` とは異なる独自スキーマ）は、§0 で言及された前回の pi 無料モデルによる失敗試行の残骸である。
   - 処置計画: `AGY_BOOTSTRAP_PROMPT.md` §4 で削除が明示されているのは `.pi/settings.json` のみであり、`AGENTS.md` の「既存ファイルの無断上書き・削除禁止」およびプロンプトの「判断に迷う点は勝手に決めず `docs/agent/BOOTSTRAP_TODO.md` に記録して先へ進む」に従い、ルート直下の `index.ts` / `state.ts` は勝手に削除せず `docs/agent/BOOTSTRAP_TODO.md` に検証結果と削除推奨コマンドを記録する。
5. **既存のディレクトリ状況**
   - `.pi/skills/test-scope/` は空ディレクトリとして存在。`docs/agent/`、`.pi/harness/prompts/`、`progress/` は未作成。

---

## 2. 生成・整理の順序と内容（`AGY_BOOTSTRAP_PROMPT.md` §4 準拠）

### Step A: ドキュメント群（`docs/agent/`）
1. `docs/agent/PROTOCOL.md`
   - ファイル所有権表（オーケストレーター `Luna`、実装ワーカー、レビューワーカー、ハーネス `pi`、人間の書込権限と対象パス）
   - `status` 語彙と状態遷移 (`todo` → `doing` → `review` → `qa` → `done` / `blocked`)
   - 進捗報告の frontmatter 規約（§5 の YAML スカラー形式、`poll.ts` の挙動との整合）
   - 30分ポーリングの手順、1サイクル（実装 → レビュー → QA → コミット）の定義、ブランチ階層 (`main` ← `phase/<slug>` ← worktree サブブランチ)、CI グリーンによるマージ条件、Phase 完了時の `main` 自動マージ、試行上限（最大3回・レビュー最大2周）
2. `docs/agent/MODEL_ROTATION.md`
   - §3 の重み別モデルローテーション表（`heavy` / `medium` / `light`）
   - 枠枯渇（Quota Reached）の扱い（失敗カウント非加算、即座に次候補へ切替、絶対時刻での cooldown 保持）
   - OpenCode 無料プール（12種）のカーソル巡回と QA 通過率集計の仕組み
   - 全候補枯渇時の待機・fallback（`ollama/gemma3:4b`）・`blocked` 化と人間への通知ルール
3. `docs/agent/CONSTRAINTS.md`
   - §1・§7 の実行境界（Docker 不使用、ホスト CLI 直接実行、worktree 分離のみ、skip-permissions 前提）
   - 完了の定義（`docs/plans/FINAL_ACCEPTANCE_CRITERIA.md`, `REQUIREMENTS_TRACEABILITY_MATRIX.md`, `MASTER_IMPLEMENTATION_ROADMAP.md`, `PHASE_STATUS.md`）
   - テスト実行制約（変更関連テストのみ、フルスイートは Phase の節目のみ）
   - 禁止事項一覧（`.pi/extensions/harness/` 改変禁止、仕様文書改変禁止、`loop_engine/`・`.loop/` 改変禁止、秘密情報書込禁止、ワーカー間直接通信禁止、Superpowers との衝突時は PROTOCOL 優先）
4. `docs/agent/BOOTSTRAP_TODO.md`
   - 生成中に確認した未確定事項・衝突点・人間確認事項を記録（逐次更新し、Step E の Superpowers 導入試行結果も反映する）。

### Step B: プロンプト群（`.pi/harness/prompts/`）
5. `.pi/harness/prompts/orchestrator.md` — Codex (`gpt-6-luna`) 用プロンプト
6. `.pi/harness/prompts/implementer.md` — ワーカー実装用プロンプト
7. `.pi/harness/prompts/reviewer.md` — ワーカーレビュー用プロンプト（実装モデルとは別モデルで実行）

### Step C: 進捗報告ディレクトリ・テンプレート（`progress/`）
8. `progress/README.md` — ディレクトリ構成、ファイル所有権、`poll.ts` の frontmatter スキャン仕様の説明（注意: `poll.ts` は `progress/` 配下の全 `.md` で `status` / `updated` frontmatter を持つものをスキャンするため、README とテンプレート自体の扱いに留意し、テンプレートの frontmatter が誤ってタスクとして認識されないよう配慮または `BOOTSTRAP_TODO.md` に挙動を明記する）
9. `progress/_template/PROGRESS.md` — Phase サマリの雛形（オーケストレーター記入用）
10. `progress/_template/tasks/TASK-PROGRESS.md` — タスク進捗の雛形（担当ワーカー・レビュアー記入用、`REPORT` / `TEST` / `REVIEW` 欄と §5 準拠の frontmatter を持つ）

### Step D: スキルと設定整理
11. `.pi/skills/test-scope/SKILL.md` — `testscope.ts` の仕様と一致した変更パス→テスト対応原則、フルスイート実行条件の定義
12. `.pi/settings.json` の整理 — 内容を検証・整形して `docs/agent/HARNESS_MANIFEST.json` へ保存し、`.pi/settings.json` を削除
13. `.gitignore` への追記 — `.pi/harness/state.json`, `.pi/harness/state.json.tmp`, `.pi/harness/logs/` 等を既存エントリと重複しないよう末尾へ追記

### Step E: Superpowers の導入試行と記録
14. `pi`, `Codex`, `OpenCode`, `Antigravity` それぞれに対する Superpowers 導入状況の確認・試行を行い、結果と PROTOCOL との衝突点（`subagent-driven-development` 等の扱い）を `docs/agent/BOOTSTRAP_TODO.md` に記録する。

---

## 3. 自己点検項目
- すべての生成パスが `AGY_BOOTSTRAP_PROMPT.md` §4 および `.pi/extensions/harness/config.ts` の定数と完全一致していること。
- YAML frontmatter が §5 および `poll.ts` の `parseFrontmatter` 正規表現 (`^([A-Za-z0-9_-]+):\s*(.*)$`) と完全互換であること。
- `docs/agent/HARNESS_MANIFEST.json` が `JSON.parse` でエラーなくパースできること。
- 禁止対象ファイル（`.pi/extensions/harness/*`, `docs/planning/*`, `docs/plans/*`, `loop_engine/*`, `.loop/*`）に一切変更がないことを `git status` / `git diff` で確認すること。
