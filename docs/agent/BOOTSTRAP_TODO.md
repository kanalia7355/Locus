# ブートストラップ未決事項・要確認リスト (`BOOTSTRAP_TODO.md`)

作成・更新日時: 2026-11-12T14:18:00+09:00

本書は `AGY_BOOTSTRAP_PROMPT.md` に従い、ハーネス一式の生成中に判断を保留した点、配置済みコア（`.pi/extensions/harness/`）との仕様上の注意点、Superpowers との衝突点、および人間による確認・作業が必要な項目を記録する。

---

## 1. 既存生成物の検証で見つかった不要ファイル（人間による削除確認待ち）

### TODO-01: リポジトリルート直下の `index.ts` と `state.ts` の削除
- **現象**: リポジトリルート直下に untracked ファイルとして `index.ts` と `state.ts` が残っている。
- **検証結果**:
  - 前回の pi 無料モデルによるブートストラップ試行の残骸である。
  - `index.ts` は 8行目に `#` が混入しており TypeScript として構文エラーになる上、ルート直下に存在しない `./poll` を import している。
  - `state.ts` は `const hasActive = false; hasActive = true;` や `Record<string, unknown>` に対する未型付けプロパティアクセスなど複数の構文・型エラーを含み、配置済みコア `.pi/extensions/harness/state.ts` のスキーマとも一致しない。
- **判断保留の理由**: `AGY_BOOTSTRAP_PROMPT.md` §4 で削除が明示されているのは `.pi/settings.json` のみであり、`AGENTS.md` の既存ファイル保護原則に従い無断削除を控えた。
- **推奨対応（人間作業）**:
  ```powershell
  Remove-Item .\index.ts, .\state.ts
  ```

---

## 2. 配置済みコア (`.pi/extensions/harness/`) に関する未検証・将来拡張点

`.pi/extensions/harness/` は §0・§7 により改変禁止であるため、以下の点はコードを変更せずここに記録する（`.pi/README.md` の記載事項を含む）。

### TODO-02: ワーカー自動起動および worktree → メイン `progress/` 集約の連結
- **内容**:
  - `.pi/extensions/harness/index.ts` のコメント（10〜11行目）および `.pi/README.md` にある通り、現在の `index.ts` は「30分ごとにメインチェックアウトの `progress/` をポーリングし、差分があれば Luna (`codex`) を起動する」ところまでを自動化している。
  - 一方、§1 の確定設計では「ワーカーは自分の worktree の `progress/` に書き、サイクルのコミットに含める（マージで集約される）」「実装 → レビュー → QA を 1 サイクルとし、サイクル完了でコミットしてよい」と定められている。
- **課題**:
  1. `index.ts` から `runners/agy.ts` や `runners/opencode.ts` を呼び出してワーカー（Implementer / Reviewer）を自動ディスパッチするループ連結部が将来拡張点として残っている（あるいは Luna が `workspace-write` 内でどこまで起動・worktree 参照を行うかの運用確定が必要）。
  2. ワーカーが自身の worktree 内の `progress/` だけを更新し、サイクル完了（`qa` → `done`）までコミット・マージされない場合、メインチェックアウトの `progress/` だけを見る `poll.ts` ではサイクル途中の変化（`doing` → `review` → `qa`）を検知できない。
- **暫定措置**: `.pi/harness/prompts/orchestrator.md` および `implementer.md` / `reviewer.md` では、worktree 内の進捗ファイルとメインチェックアウトの `progress/` の同期（または worktree 横断の確認）について注意書きを記載した。実運用前に `index.ts` / `poll.ts` で全 worktree の `progress/` を走査するか、ワーカー終了時にメイン `progress/` へ反映するかを人間側で判断されたい。

### TODO-03: `poll.ts` が `progress/_template/` 配下もスキャン対象にすることへの留意
- **内容**: `poll.ts` の `listMarkdownFiles()` は `progress/` 配下のすべての `.md` ファイルを再帰的に走査し、frontmatter に `status` または `updated` があるものを `PollState` に含める。
- **影響**: `progress/_template/tasks/TASK-PROGRESS.md` は §5 の frontmatter 規約を満たす必要があるため、初回ポーリング時に `_template/tasks/TASK-PROGRESS.md` が差分として1回検出される（2回目以降は `state.json` のスナップショットと一致するため検出されない）。
- **暫定措置**: `.pi/harness/prompts/orchestrator.md` に「`_template/` で始まるパスがポーリング差分に含まれていても、テンプレートであるためタスク割当・状態遷移の対象外（無視）とすること」を明記した。

### TODO-04: Codex の Luna モデル ID (`gpt-6-luna`) の実機確認
- **内容**: `.pi/extensions/harness/config.ts` では `lunaModel: "gpt-6-luna"` が設定されている。Codex CLI 0.167.1 の実環境で `gpt-6-luna` がそのまま通るか（アカウントの 엔タイトルメントや別名でないか）は初回ポーリング実行時に確認が必要。

### TODO-05: `agy` の effort (`low` / `medium` / `high`) の CLI 引数指定方法
- **内容**: `rotation.ts` では `heavy` に `effort: "high"`、`medium` に `effort: "medium"` がメタ情報として定義されているが、`runners/agy.ts` の起動引数には含まれていない（`agy` CLI のフラグ仕様が未確定のため）。当面はオーケストレーターまたはプロンプト側で深さを指示する形としている。

### TODO-06: GitHub Actions CI グリーン判定の粒度 (`git.ts`)
- **内容**: `git.ts` の `ciConclusion()` は `gh run list --branch <branch> --limit 1 --json status,conclusion` で最新1件の workflow run のみを判定している。Locus リポジトリには複数の workflow（`quality.yml`, `loop-ci.yml`, `pr-title.yml` 等、`.loop/config.yaml` では `verify`, `engine (...)`, `conventional-title`）が存在するため、全必須 workflow がグリーンであることを確認するには複数 run / check suite を確認する拡張が望ましい。

### TODO-07: OpenCode 無料プールのモデル別 QA 通過率の永続化先
- **内容**: §3 で「OpenCode 無料プールの内部順序は固定せず、カーソルで回す。QA 通過率を集計できる形にしておく」と規定されているが、改変禁止の `.pi/extensions/harness/state.ts` には `freeCursor` のみがあり統計フィールドが無い。
- **措置**: `progress/_template/PROGRESS.md`（Phase サマリ）および `TASK-PROGRESS.md` にモデル別 QA 通過・差し戻し集計テーブルを設け、オーケストレーター（Luna）が集計・記録する形にした。

### TODO-08: `.pi/extensions/harness/tsconfig.json` の単体 `tsc` 実行時の `@types/node` 解決
- **内容**: ルートには `node_modules` が無く `frontend/node_modules` に `@types/node` があるため、ルートで `tsc --project .pi/extensions/harness/tsconfig.json --noEmit` を実行する際は `--typeRoots frontend/node_modules/@types` を付与する必要がある。

---

## 3. Superpowers (`obra/superpowers`) と PROTOCOL の衝突点

`AGY_BOOTSTRAP_PROMPT.md` §2・§4-14 に従い、Superpowers 側のワークフローと本リポジトリの `PROTOCOL.md` / `CONSTRAINTS.md` が衝突する箇所を以下に記録する。プロンプトおよび規約文書ではすべて **PROTOCOL を優先**するよう明記済みである。

1. **`subagent-driven-development` / `dispatching-parallel-agents` の禁止**:
   - Superpowers の基本ワークフロー（`README.md` §The Basic Workflow 4）はサブエージェントを直接起動してタスクを並列・連続処理する設計になっているが、本ハーネスでは「ワーカー同士やワーカーから他エージェントへの直接起動・通信は禁止（すべての連携は `progress/` の Markdown 経由）」かつ `AGENTS.md` / `.agents/skills/SKILLS_REGISTRY.md` でも両スキルは **Prohibited** である。ワーカーはサブエージェントを起動してはならない。
2. **`using-git-worktrees` / `finishing-a-development-branch` の扱い**:
   - Superpowers の `using-git-worktrees` はパッケージの自動インストールや自由なブランチ作成を行い、`finishing-a-development-branch` はワーカー自身に対話的なマージ・PR作成・worktree 削除を行わせるが、本ハーネスではブランチ階層（`main ← phase/<slug> ← worktree サブブランチ`）とコミット・マージ条件（1サイクル完了時コミット、CI グリーンでマージ）がハーネスとオーケストレーターの管理下に置かれるため、ワーカーが勝手に `main` や `phase/<slug>` へマージ・push・worktree 削除を行ってはならない。
3. **`test-driven-development` におけるテスト実行範囲の制限**:
   - Superpowers の TDD スキルはテストスイートの頻繁な実行を促すが、本ハーネスでは `.pi/skills/test-scope/SKILL.md` により「変更ファイルに関連するテストのみ実行可、フルスイートは Phase の節目のみ」と厳格に制限する。
4. **`brainstorming` の対話ステップの抑止**:
   - ハーネスから `--full-auto` / `--dangerously-skip-permissions` / `--auto` で非対話起動されたワーカーが Superpowers の `brainstorming` スキルを発火させて人間への質問待ちで停止しないよう、ワーカーは割り当てられたタスクファイルの受入条件を直接実装し、本当に判断不能な点のみ `status: blocked` としてファイルに記録して終了する。

---

## 4. Superpowers の各 CLI への導入試行結果

`AGY_BOOTSTRAP_PROMPT.md` §4-14 に基づき、4つの CLI ハーネスへの `obra/superpowers` 導入を試行・検証した結果を記録する。

| 対象 CLI | 試行・確認コマンド / 方法 | 結果 | 詳細・インストール先 / 人間作業 |
|---|---|---|---|
| **pi** | `pi install git:github.com/obra/superpowers` | **導入完了（自動）** | `C:\Users\hirot\.pi\agent\git\github.com\obra\superpowers` にクローン・登録完了。 |
| **Antigravity (`agy`)** | `agy plugin install https://github.com/obra/superpowers` | **導入完了（自動）** | `C:\Users\hirot\.gemini\config\plugins\superpowers` に15スキル一式がインストール済み（`[ok] superpowers ✔ skills : 15 installed`）。 |
| **OpenCode** | `.opencode/INSTALL.md`（V2 `>=2.0.4` 手順）の確認 | **導入済み確認** | `C:\Users\hirot\.config\opencode\opencode.json` に `"plugins": ["superpowers@git+https://github.com/obra/superpowers.git"]` が設定済みであり、`C:\Users\hirot\.cache\opencode\npm\git-superpowers-0958a5557860\1794379136965\node_modules\superpowers` にパッケージ展開済みであることを確認。 |
| **Codex** | 上流リポジトリの `.codex/INSTALL.md` 確認 → `README.md` §Codex CLI 確認 | **人間作業として保留（対話 TUI 必須）** | 上流 `obra/superpowers` では `.codex/INSTALL.md` が廃止され、Codex CLI の対話 TUI（`codex` 起動後に `/plugins` → `superpowers` を検索 → `Install Plugin` を選択）または Codex App の Plugins サイドバーから導入する方式になっている。対話操作が必要なため §4-14 に従い人間作業として残す（なお、本ハーネスで Codex `gpt-6-luna` は実装を行わないオーケストレーター兼 QA である）。 |
