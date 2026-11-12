# agy へのブートストラップ指示 — Locus ハーネスの残り一式の生成

あなたは Antigravity CLI (agy) として、このリポジトリ（Locus）のルートで動いている。
今回のタスクは、自律開発ループのハーネスのうち、**まだ生成されていない残り一式**を
このリポジトリ内に生成すること。

設計判断はすべて確定済みであり、下記に埋め込んである。**設計を変更しないこと。**
判断できない点は推測で決めず、`docs/agent/BOOTSTRAP_TODO.md` に記録して先へ進むこと。

## 0. 現状（前提）

- ハーネスの心臓部 `.pi/extensions/harness/`（TypeScript 一式）は**配置済み**。
  中身は正として扱い、**生成・改変は一切しない**
- 以前、pi の無料モデルが一度ブートストラップを試みており、生成物が一部残っている
  可能性がある（`docs/agent/`、`.pi/settings.json` 等）。その生成物には構文の壊れた
  JSON や動かないコードが混ざっていた前例がある。**既存ファイルは鵜呑みにせず、
  内容を検証し、壊れていれば作り直すこと**
- `.pi/settings.json` が存在する場合、その中身は pi 公式の設定形式ではなく
  「ハーネスの構成メモ」である。扱いは §4-6 の通り

## 1. 確定済み設計

- **役割分担**
  - オーケストレーター＋QA: Codex CLI の Luna モデル。タスク分解、重み付け、割当、
    状態遷移、QA（受入条件とテスト結果の機械的な照合）を行う。**実装はしない**
  - 実装とレビュー: agy のモデル群と OpenCode 無料モデル。
    レビューは実装したモデルとは**別のモデル**が行う
  - ハーネス実行基盤: pi（配置済みの extension が 30分ポーリングと Luna 起動を担う）
  - 人間: 改善点の指示のみ
- **通信規約**
  - エージェント同士は直接通信しない。すべての連携は Markdown ファイル経由
  - ワーカーからオーケストレーターへの送信は禁止。ワーカーの仕事は
    進捗報告 md を書くところまで
  - オーケストレーターは `progress/` を **30分間隔** でポーリングする。
    ポーリング対象はメインチェックアウトの `progress/` で、ワーカーは自分の
    worktree の `progress/` に書き、サイクルのコミットに含める（マージで集約される）
- **サイクルとマージ**
  - 実装 → レビュー → QA を 1 サイクルとし、サイクル完了でコミットしてよい
  - マージ条件は **GitHub Actions の CI がグリーン**であること
  - ブランチ階層: main ← `phase/<slug>` ← worktree ごとのサブブランチ
  - Phase のループが完了したら Phase ブランチを main へ**自動マージ**する
  - 試行上限: 1タスクあたり最大 3 回、レビューサイクルは最大 2 周
    （上限に達したら blocked にして理由を書く）
- **実行境界**
  - Docker は使わない。ホストの CLI を直接実行し、認証はホストの既存ログインを流用
  - 全 CLI で skip-permissions（full-auto）前提。実行境界は git worktree の分離のみ
- **モデル制御（ハーネスが担う）**
  - タスクの重み（heavy / medium / light）でモデルを自動選択する
  - 使用量の上限に達したら、自動で候補列の次モデルへ切り替える
  - cooldown は絶対時刻で保持する
- **テスト**
  - テストは無駄に回さない。変更に関連する範囲だけを実行する（skill / hook で縛る）
  - フルスイートは Phase の節目でのみ実行する
- **完了の定義**
  - `docs/` の内容（フロー図・アーキテクチャを含む）を完全に実装し、本番運用できること
  - 物差し: `docs/plans/FINAL_ACCEPTANCE_CRITERIA.md` と
    `docs/plans/REQUIREMENTS_TRACEABILITY_MATRIX.md`
  - Phase 構成: `docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md` と
    `docs/plans/PHASE_STATUS.md` に沿う

## 2. 使用 CLI の呼び出し方（実機確認済み）

- **Codex**: codex-cli 0.167.1
  - Luna 起動の基本形:
    `codex exec --model gpt-6-luna --sandbox workspace-write --full-auto "<prompt>"`
- **agy**: 1.5.5、Google AI Pro（haodouz）でログイン済み
  - 基本形: `agy -p "<prompt>" --model "<表示名>" --dangerously-skip-permissions --print-timeout 30m`
  - モデルは表示名: Gemini 4 Argon / Gemini 4 Carbon / Gemini 3.8 Flash /
    Claude Opus 5.5 / Claude Sonnet 5.5 / GPT-OSS 120B
  - **agy の終了コードは信用しない**。成否は成果物ファイルとテスト結果で判定する
  - 枠は2プール制（推定）: Gemini 系と Claude / GPT 系が独立。それぞれ
    5時間枠＋週間枠。枠切れ時は `Individual quota reached ... Resets in <duration>`
    の形でリセットまでの時間が返るので、cooldown の終了時刻として記録する
- **OpenCode**: v2.2.7
  - 基本形: `opencode run --model opencode/<slug> --auto "<prompt>"`
  - 無料モデル（12種）: beam-free / big-pickle / deepseek-v4.1-flash-free /
    flint-40b-free / glm-5.3-flash-free / iceman-free / inkling-2-small-free /
    longcat-2.5-free / mimo-v2.6-flash-free / minimax-m3.1-flash-free /
    nemotron-3.5-lightning-free / nemotron-3.5-super-vl-free
  - ローカルモデル `ollama/gemma3:4b` は枠消費ゼロの最終 fallback（light の定型作業のみ）
- **Superpowers**（obra/superpowers）: ワーカーの品質底上げに使う skills
  フレームワーク。pi / Codex / OpenCode / Antigravity の全ハーネスに公式対応。
  ただし正は本書の PROTOCOL であり、Superpowers 側のワークフローが PROTOCOL と
  衝突する場合は **PROTOCOL を優先**し、衝突点は BOOTSTRAP_TODO に記録する

## 3. モデルローテーション表

| 重み | 候補列（上から順に試す） |
|---|---|
| heavy | agy: Gemini 4 Argon (High) → agy: Claude Opus 5.5 → agy: Claude Sonnet 5.5 |
| medium | agy: Gemini 4 Argon (Medium) → agy: Claude Sonnet 5.5 → OpenCode 無料プール |
| light | agy: Gemini 3.8 Flash / Gemini 4 Carbon → agy: GPT-OSS 120B → OpenCode 無料プール → ollama/gemma3:4b |

- 枠切れは「モデルの失敗」ではない。リトライせず候補列の次へ切り替える
- OpenCode 無料プールの内部順序は固定せず、カーソルで回す。QA 通過率を
  集計できる形にしておく
- 候補が全滅したら: cooldown 終了が最も早いモデルまで待機 → light は ollama へ →
  それでも無理なら blocked にして人間へ通知する（無言で止まらない）

## 4. 生成するファイル

### ドキュメント（`docs/agent/`）

1. `docs/agent/PROTOCOL.md`
   - ファイル所有権表（誰がどのファイルを書けるか）
   - status 語彙: todo → doing → review → qa → done / blocked
   - 進捗報告の frontmatter 規約（§5 の形式をそのまま規定する）
   - 30分ポーリングの手順、1サイクルの定義、コミット／マージ条件、試行上限
2. `docs/agent/MODEL_ROTATION.md` — §3 の表と切替ルールの文書化
3. `docs/agent/CONSTRAINTS.md` — §1 の実行境界・完了定義・禁止事項の集約
4. `docs/agent/BOOTSTRAP_TODO.md` — 生成中に不明で飛ばした点の一覧（空でも作る）

### プロンプト（`.pi/harness/prompts/`）

配置済みの extension は `.pi/harness/prompts/orchestrator.md` を読む仕様に
なっている。**パスとファイル名は厳密に一致させること**。

5. `.pi/harness/prompts/orchestrator.md` — Luna 用
   - 役割（割当・状態遷移・QA 照合のみ。実装禁止）
   - 入力: ポーリング差分の要約と、progress/・タスクファイルの読み方
   - 出力: ファイルの更新のみ（タスク割当、status 遷移、PROGRESS.md の集約）
   - 判断の境界: 仕様解釈、設計トレードオフ、blocked の解消判断は Luna では
     決めず、heavy モデルのレビューか人間へ escalate する形でファイルに残す
   - 枠切れ・試行上限時の振る舞い（blocked 化と理由の記録）
6. `.pi/harness/prompts/implementer.md` — ワーカー実装用
   - タスクファイルの読み方、自分の worktree で作業すること
   - 進捗報告の書き方（§5 の形式。自分のタスクファイルだけを書く）
   - テスト範囲の制約（関連テストのみ）、Superpowers の該当スキル
     （test-driven-development、systematic-debugging、
     verification-before-completion 等）を着手前に確認して従う旨
   - 禁止事項（他人のファイルの改変、オーケストレーターへの直接連絡の試み等）
7. `.pi/harness/prompts/reviewer.md` — レビュー用
   - 実装者と別モデルで使う前提。差分と受入条件を読み、指摘は進捗ファイルの
     REVIEW 欄へ書く。Superpowers の該当スキルを参照させる

### 進捗報告（`progress/`）

8. `progress/README.md` — 使い方（Phase 毎のディレクトリ、タスク毎のファイル、
   書く人の決まり、ポーリングで frontmatter だけ一次判定されること）
9. `progress/_template/PROGRESS.md` — Phase サマリの雛形（書くのはオーケストレーター）
10. `progress/_template/tasks/TASK-PROGRESS.md` — タスク進捗の雛形
    （書くのは担当ワーカーのみ。REPORT / TEST / REVIEW 欄を持つ）

### スキルと設定

11. `.pi/skills/test-scope/SKILL.md` — テスト範囲の縛り方
    （変更パス→テスト対応の原則、フルスイートを実行してよい条件）
12. `.pi/settings.json` の整理:
    - 既存の `.pi/settings.json` が §0 の「構成メモ」形式だった場合、その内容を
      検証し、構文が壊れていれば直したうえで `docs/agent/HARNESS_MANIFEST.json`
      へ移す（情報は失わない）
    - `.pi/settings.json` 自体は削除し、pi の既定動作に戻す
      （既定モデルの設定は人間がモデルピッカーで行う）
    - 既存が pi 公式形式の正しい設定だった場合は、そのまま触らない
13. `.gitignore` への追記: `.pi/harness/state.json`、`.pi/harness/logs/` 等の
    ランタイム生成物（既存の記述と重複させない）

### Superpowers の導入（試行）

14. 各 CLI への Superpowers 導入を試み、結果を BOOTSTRAP_TODO に記録する
    - pi: `pi install git:github.com/obra/superpowers`
    - Codex: プラグイン導入手順（`.codex/INSTALL.md`）に従う
    - OpenCode: リポジトリの `.opencode/INSTALL.md` の手順を実行させる
    - Antigravity（自分自身）: 公式対応ハーネスに含まれる。案内に従う
    - 対話操作が必要で自動化できないものは、無理に進めず「人間作業」として残す

## 5. 進捗報告の frontmatter 規約（厳密にこの形式）

配置済みの poll.ts はこの形式で読む。雛形と PROTOCOL は必ずこれに合わせること。

```yaml
---
id: T-001
phase: phase-<slug>
status: doing
assignee: agy
model: Gemini 4 Argon
weight: medium
updated: 2026-11-12T13:00:00+09:00
attempts: 1
---
```

- ファイル先頭が `---` で始まり、次の `---` で閉じる
- 値は単純なスカラーのみ（ネストや配列は使わない）
- `status` は §4-1 の語彙のみ。`updated` は ISO 8601 で、更新のたびに書き換える

## 6. 作業手順（agy 自身の進め方）

1. **現状把握**: `git status`、`AGENTS.md`、`CLAUDE.md`、`docs/plans/`、
   `.loop/config.yaml`、`.agents/skills/`、既存の生成物（§0）を読む。
   配置済みの `.pi/extensions/harness/` の中身も読み、生成物がその仕様
   （パスの前提、frontmatter 規約）と矛盾しないようにする
2. **計画**: 生成・修正の計画を `docs/agent/BOOTSTRAP_PLAN.md` に書いてから着手する
3. **生成**: §4 の順に生成・整理する。各ファイルの生成後に内容を自己点検する
   （パス、frontmatter、相互参照の整合。JSON はパースできるか必ず確認する）
4. **報告**: 生成物の一覧、既存生成物の検証結果（作り直したものがあれば理由）、
   未解決 TODO の要約を人間に報告する

## 7. 禁止事項

- `.pi/extensions/harness/`（配置済みの心臓部）の生成・改変・削除
- 仕様文書（`docs/planning/`、`docs/plans/`）の改変
- `loop_engine/` と `.loop/` の改変・削除
- git commit / push（生成物のコミットは人間が確認してから行う）
- 資格情報・API キーのファイルへの書き込み
- §1〜§3 に無い設計判断の追加（不明点は BOOTSTRAP_TODO 行き）
- ワーカー同士を直接通信させる仕組みの導入
