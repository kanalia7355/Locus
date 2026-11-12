# Locus ハーネス 実行境界・完了定義・制約事項 (`CONSTRAINTS.md`)

本書は `AGY_BOOTSTRAP_PROMPT.md` §1・§7 で確定した自律開発ループの実行境界、テスト制約、完了の定義、および絶対禁止事項を集約する。すべてのエージェント（オーケストレーター・実装ワーカー・レビューワーカー）は本書を遵守しなければならない。

---

## 1. 実行境界（Execution Boundary）

- **Docker 不使用**: ハーネスによるワーカー起動では Docker コンテナを使用しない。ホスト OS 上の CLI（`codex`, `agy`, `opencode`）を直接実行し、認証はホストの既存ログイン状態をそのまま流用する。
- **Full-Auto / Skip-Permissions 前提**:
  - Codex: `--sandbox workspace-write --full-auto`
  - Antigravity (`agy`): `--dangerously-skip-permissions --print-timeout 30m`
  - OpenCode: `--auto`
- **Git Worktree による分離**:
  - ワーカー間の実行境界は **git worktree の分離のみ** で担保する。
  - 各ワーカーは割り当てられた自身の worktree 内でのみファイルの読み書き・テスト実行を行い、メインチェックアウトや他ワーカーの worktree に直接手を加えてはならない。
- **ブランチ階層**:
  - `main` ← `phase/<slug>` ← worktree ごとのサブブランチ
  - サブブランチから `phase/<slug>`、および Phase 完了時の `phase/<slug>` から `main` へのマージは、**GitHub Actions の CI がグリーン（`success`）**であることを必須条件とする。

---

## 2. テスト実行の制約（Test Scope）

- **無駄なテスト実行の禁止**:
  - ワーカーが実装・修正サイクルごとにフルテストスイートを実行することを禁止する。
  - 変更したファイルに関連する最小限のテストのみを実行する（詳細は `.pi/skills/test-scope/SKILL.md` および `.pi/extensions/harness/testscope.ts` に従う）。
  - ドキュメント（`.md`、`docs/`、`progress/`）やハーネス設定（`.pi/`）のみの変更ではテストを実行しない。
- **フルスイートを実行してよい条件**:
  - **Phase の節目**（Phase 内の全タスクが完了し、`phase/<slug>` ブランチを `main` へマージする直前の最終検証）でのみフルスイートを実行する。

---

## 3. 完了の定義（Definition of Done）

Locus 開発ループ全体の完了は、単なるプロトタイプ動作や個別タスクの消化ではなく、以下をすべて満たすことと定義する。

1. **設計・仕様の完全実装**:
   - `docs/` 配下（フロー図・アーキテクチャ・セキュリティ境界・UI ベースラインを含む）の内容を完全に実装し、本番運用できる状態にすること。
2. **合否判定の物差し（Acceptance Authority）**:
   - [`docs/plans/FINAL_ACCEPTANCE_CRITERIA.md`](../plans/FINAL_ACCEPTANCE_CRITERIA.md) の全受入条件を満たすこと。
   - [`docs/plans/REQUIREMENTS_TRACEABILITY_MATRIX.md`](../plans/REQUIREMENTS_TRACEABILITY_MATRIX.md) の全要件 ID（92 ID）について実装・テスト・レビュー・統合の証跡が揃っていること。
3. **Phase 構成と進行基準**:
   - [`docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md`](../plans/MASTER_IMPLEMENTATION_ROADMAP.md) および [`docs/plans/PHASE_STATUS.md`](../plans/PHASE_STATUS.md) に沿って Phase を進め、各 Phase の完了条件と CI グリーンを満たして `main` へ統合すること。

---

## 4. 試行上限と Superpowers の優先順位

- **試行上限**:
  - 1タスクあたりの実装試行は **最大 3 回**（`attempts <= 3`）。
  - 1試行あたりのレビューサイクルは **最大 2 周**。
  - 上限に達した場合は推測やテスト弱体化で突破しようとせず、`status: blocked` にして理由と証跡を進捗ファイルに記録する。
- **Superpowers との優先順位**:
  - ワーカーの品質底上げに `obra/superpowers` のスキル群（`test-driven-development`, `systematic-debugging`, `verification-before-completion` 等）を活用する。
  - ただし **正本は `docs/agent/PROTOCOL.md`** であり、Superpowers 側のワークフロー（例: `subagent-driven-development` や `dispatching-parallel-agents` によるサブエージェント直接起動、独自のブランチ完了手順、フルテスト強制など）が PROTOCOL や本書の制約と衝突する場合は、**常に PROTOCOL および本書を優先**する。

---

## 5. 禁止事項（Prohibitions）

以下の行為は理由を問わず厳禁とする。

1. **ハーネス心臓部の改変禁止**: `.pi/extensions/harness/` 配下の TypeScript ファイル一式の生成・改変・削除。
2. **仕様・計画文書の改変禁止**: `docs/planning/` および `docs/plans/` 配下の仕様・計画文書の改変（人間または明示的に承認された専用監査タスクを除く）。
3. **既存ループエンジンの改変禁止**: `loop_engine/` および `.loop/` の改変・削除。
4. **オーケストレーターによる実装禁止**: `gpt-6-luna`（オーケストレーター）がプロダクトコードやテストコードを直接編集すること。
5. **同一モデルによるセルフレビュー禁止**: タスクを実装したモデルと同じモデルが当該タスクの `REVIEW` を行うこと。
6. **エージェント間の直接通信禁止**: ワーカー同士、またはワーカーからオーケストレーターへ Markdown ファイルを通さずに直接通信・プロセス起動を行う仕組みの導入。
7. **秘密情報の書き込み禁止**: 資格情報（Credentials）、API キー、トークン、パスワード等をリポジトリ内のファイルや進捗報告・ログへ書き込むこと。
8. **テスト・受入条件の弱体化禁止**: テストや CI をグリーンにする目的で既存のテストケースを削除・緩和したり、受入条件を書き換えたりすること。
9. **無断の設計判断追加禁止**: `PROTOCOL.md`・`MODEL_ROTATION.md`・本書および仕様書に根拠のない設計判断を推測で追加すること（判断できない点は `blocked` またはエスカレーションとして記録する）。
