# Locus 進捗報告ディレクトリ (`progress/`) の使い方

このディレクトリは、Locus 自律開発ハーネスにおいてオーケストレーター（Codex / `gpt-6-luna`）と各ワーカー（`agy` / OpenCode 無料モデル / `ollama`）が連携するための **唯一の通信チャネル** です。
エージェント同士は直接通信を行わず、すべてこのディレクトリ配下の Markdown ファイルを介して状態遷移・作業報告・レビュー・QA 照合を行います。

---

## 1. ディレクトリ構成

Phase ごとにディレクトリを切り、その中に Phase サマリ（`PROGRESS.md`）とタスクごとの進捗ファイル（`tasks/<TASK-ID>.md`）を配置します。

```text
progress/
  README.md                         ← 本ファイル（使い方と規約）
  _template/                        ← 新規 Phase / タスク作成用の雛形（直接タスクとして使わない）
    PROGRESS.md                     ← Phase サマリの雛形（オーケストレーター用）
    tasks/
      TASK-PROGRESS.md              ← タスク進捗の雛形（ワーカー記入用）
  phase-<slug>/                     ← 各 Phase の実作業ディレクトリ（例: phase-3-ingestion/）
    PROGRESS.md                     ← 当該 Phase の全体進捗サマリ
    tasks/
      T-001.md                      ← 個別タスクの進捗・テスト・レビュー記録
      T-002.md
```

---

## 2. 書く人の決まり（ファイル所有権）

詳細は [`docs/agent/PROTOCOL.md`](../docs/agent/PROTOCOL.md) を参照してください。

1. **`progress/<phase>/PROGRESS.md`（Phase サマリ）**:
   - **書く人**: オーケストレーター（`gpt-6-luna`）**のみ**。
   - ワーカー（実装者・レビュアー）はこのファイルを書き換えてはなりません。
2. **`progress/<phase>/tasks/<TASK-ID>.md`（タスク進捗ファイル）**:
   - **初期作成・割当・QA 判定（`todo` / `qa` → `done` / `blocked`）**: オーケストレーター（`gpt-6-luna`）。
   - **`## REPORT` 欄・`## TEST` 欄・`status: review` への更新**: そのタスクを担当する **実装ワーカー（Implementer）のみ**。
   - **`## REVIEW` 欄・`status: qa`（または差し戻し `doing` / `blocked`）への更新**: 実装者とは別モデルの **レビューワーカー（Reviewer）のみ**。
   - ワーカーは**自分が担当するタスクのファイル1つだけ**を自分の git worktree 内で更新し、1サイクルのコミットに含めます（マージによりメインチェックアウトの `progress/` へ集約されます）。

---

## 3. ポーリングによる一次判定と Frontmatter 規約

`.pi/extensions/harness/poll.ts` は **30分間隔** でメインチェックアウトの `progress/` 配下の `.md` ファイルを走査します。

### 一次判定の仕組み
- `poll.ts` は Markdown の本文を読まず、**ファイル先頭の YAML frontmatter（`---` から次の `---` まで）の `status` と `updated` だけ**を前回スナップショット（`.pi/harness/state.json`）と比較します。
- `status` または `updated` のいずれかが変化していたファイルだけが「変化あり」と一次判定され、オーケストレーター（`gpt-6-luna`）へ差分として渡されます。
- したがって、**タスク進捗ファイルを更新する際は、必ず frontmatter の `updated` を現在時刻（ISO 8601）に書き換えてください**（`updated` と `status` の両方が同じままだと、本文を書き換えてもポーリングで検知されません）。

### 厳守すべき Frontmatter 形式（タスク進捗ファイル用）

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

- ファイルの**1行目が必ず `---`** で始まり、次の `---` で閉じること。
- 値はすべて **単純なスカラー（1行の文字列または数値）のみ** とし、ネストや配列は使用しないこと。
- `status` は `todo` / `doing` / `review` / `qa` / `done` / `blocked` の6語彙のみを使用すること。
- **注意**: `PROGRESS.md` や `README.md` には `status:` / `updated:` を含む frontmatter を付けないでください（タスクファイルとして誤検知されるのを防ぐため）。
