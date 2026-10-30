# Codex Loop Engineering — Bootstrap & Autonomous QA/PR Integration

## 目的

既存の「Codex Autonomous Loop Engineering — Implementation Specification」に基づき、VS CodeのCodex拡張から `$loop` を呼び出すだけで、自律的な実装・QA・PR作成・CI修正・安全な自動マージを開始できる環境を構築する。

対象：
- ローカル：`C:\Users\hirot\Locus`
- GitHub：`kanalia7355/Locus`
- GitHub認証：既存の `gh` 認証を利用
- 開発環境：Windows / PowerShell / VS Code / Codex

今回のGoalは開発環境のBootstrapである。Locus本体の未実装機能には着手しない。

既存コード、設計、AGENTS.md、Skillsを調査し、競合しない形で追加・統合する。

## 1. 必須成果物

以下を実装する。

### A. Codex起動Skill

`.agents/skills/loop/SKILL.md`

Frontmatter：

```yaml
---
name: loop
description: Start or resume autonomous implementation, QA, PR and safe merge workflows for the current repository.
---
```

`$loop` で明示的に呼び出せること。

起動時の動作：

1. 現在のリポジトリを確認。
2. Goal、タスク、設計、進捗を読み込む。
3. `loop doctor` を実行。
4. 実行中のControllerがあれば二重起動しない。
5. 未完了タスクがあれば継続実行を開始。
6. Goalが未設定なら必要な情報を案内。
7. 実行開始結果、ログ、状態確認方法を報告。

単に「ループしてください」というプロンプトを繰り返すSkillにしない。

Python Controllerを起動する実際の処理を実装すること。

### B. Loop Controller

最低限、以下を実装する。

```text
loop init
loop doctor
loop plan
loop start
loop pause
loop resume
loop stop
loop status
loop decisions
loop report
```

VS Code統合ターミナルから操作できること。

`loop start` は長時間実行を想定し、必要に応じて別プロセスで起動できるようにする。

停止・再開時に状態を失わないこと。

### C. Implementation Loop

```text
Task Selection
    ↓
Codex Implementation
    ↓
Local Verification
    ↓
Independent QA
    ↓
Commit & Push
    ↓
PR Creation
```

実装と検証の結果は永続化する。

同一タスクの試行は初回を含め最大3回。

失敗時はログを解析して次の試行に反映する。

3回失敗した場合はblockedに変更し、独立した次のタスクへ進む。

### D. GitHub Checks Repair Loop

PR作成後、GitHub Actionsの実行状況を監視する。

```text
PR Created
    ↓
GitHub Checks
    ↓
 ┌── Passed ──→ Merge Eligibility
 │
 ├── Failed ──→ Logs Analysis
 │                    ↓
 │                Codex Fix
 │                    ↓
 │                Local QA
 │                    ↓
 │                Push
 │                    ↓
 │              Recheck
 │
 └── Pending ──→ Wait / Poll
```

使用するGitHub CLI操作の例：

```powershell
gh pr checks <PR_NUMBER> --json name,state,bucket,link
gh run view <RUN_ID> --log-failed
gh pr view <PR_NUMBER> --json mergeable,reviewDecision,statusCheckRollup
```

実際のCLI引数はインストール済みバージョンで検証すること。

必須要件：

- PendingとFailedを区別する。
- CIの失敗ログを取得する。
- 原因を分類する。
- コード修正可能な失敗のみCodexへ渡す。
- 認証、課金、権限、GitHub障害は無理に修正しない。
- 修正後はローカルQAを再実行する。
- 修正をPushして新しいChecksを確認する。
- 古いCommit SHAのChecksを成功判定に使わない。
- Checks未作成、未実行、キャンセル、タイムアウトを成功扱いしない。
- 必須Checkが存在しない場合は自動マージしない。
- CI設定を緩和してChecksを通過させる行為は禁止。
- CI修正もタスク全体の最大3試行に含める。

## 2. QA Pipeline

以下を自動化する。

- Format
- Lint
- Type Check
- Unit Test
- Integration Test
- Build
- Security Scan
- Dependency Audit
- Secret Scan
- Architecture Compliance
- Goal Alignment Review

リポジトリの技術スタックを検出し、適切な検証コマンドを設定する。

実際に存在しないテストや検証コマンドを成功扱いしない。

QA実行結果を構造化して保存する。

### Independent QA

実装を行ったCodex実行とは別のコンテキストでレビューする。

レビュー担当は原則読み取り専用。

重大な問題があれば修正タスクへ戻す。

独立レビューは必須の機械的検証の代替にはならない。

## 3. GitHub Integration

`gh auth status`、`git remote -v`、`git status` を確認する。

PR作成者は、現在認証されている `kanalia7355` とする。

既存のGit履歴を保護する。

タスク単位でブランチを作成する。

Conventional Commitsを使用する。

PR本文には以下を含める。

- Goal
- Task ID
- Implementation Summary
- Files Changed
- QA Results
- Review Results
- Risk Assessment
- Approval Status
- CI Results

### Safe Auto Merge

次のすべてを満たす場合に限りマージする。

1. PRが低リスク。
2. 全必須Checksが成功。
3. 独立QAが合格。
4. 未解決のBlocking Findingがない。
5. 承認待ち事項がない。
6. GitHubの保護ルールを満たす。
7. 最新HEAD SHAで検証済み。
8. 自動マージ許可済みの変更範囲内。
9. マージ先が意図したブランチである。

GitHub側のAuto Merge機能が利用可能なら、それを優先する。

`gh pr merge --auto` の利用条件を検証する。

`--admin` による保護ルールの迂回は禁止。

Branch ProtectionまたはRulesetが未設定の場合は報告し、必要な設定を提案する。

設定変更に事前承認が必要な場合は承認待ちにする。

## 4. Deferred Approval

承認モードは `deferred`。

承認待ちのタスクが発生しても、依存しないタスクは継続する。

重大な変更は承認前に実行しない。

中リスク変更はPRまで作成可能だが、承認前にマージしない。

承認待ち事項は以下を保持する。

- Decision ID
- Task ID
- 対象変更
- リスク
- 判断理由
- 推奨案
- 選択肢
- 影響を受けるタスク

`loop decisions` で一覧表示し、一括判断できるようにする。

## 5. State & Recovery

SQLiteを正本として使用する。

以下を実装する。

- 原子的な状態更新
- 実行ロック
- タスク状態遷移
- 再試行回数
- PR番号の保存
- Commit SHAの保存
- CI実行IDの保存
- クラッシュ復旧
- 冪等な再開
- ログのローテーション
- 秘密情報のマスキング

PC再起動後も `loop resume` で再開可能にする。

ただし、PC停止中にローカル処理が継続するとは扱わない。

## 6. Configuration

`.loop/config.yaml` を用意する。

初期値：

```yaml
loop:
  max_attempts_per_task: 3
  max_concurrent_tasks: 1
  max_runtime_minutes: 360
  max_tasks_per_run: 20
  task_timeout_minutes: 30

qa:
  local_verification: true
  independent_review: true
  repair_failed_checks: true
  require_configured_checks: true

github:
  repository: kanalia7355/Locus
  base_branch: main
  create_pr: true
  auto_merge: safe
  require_current_head_checks: true
  bypass_protection: false

approval:
  mode: deferred
  require_preapproval_for_high_risk: true

security:
  allow_destructive_operations: false
  allow_production_changes: false
  allow_unrestricted_codex_execution: false
```

## 7. 実装順序

以下の順序で最後まで進める。

1. 既存環境の調査
2. 要件と設計の整合性確認
3. AGENTS.md整備
4. `$loop` Skill実装
5. Python Controller実装
6. Codex CLI Runner実装
7. 状態管理・復旧機構実装
8. QA Pipeline実装
9. GitHub Checks監視実装
10. CI失敗修正ループ実装
11. PR作成・Safe Merge実装
12. Deferred Approval実装
13. Unit / Integration / E2E Tests
14. 独立レビュー
15. 不具合修正
16. ドキュメント整備
17. 最終動作確認

問題が生じた場合は、解決可能なものを修正して続行する。

人間の判断が必要な事項は記録し、独立した作業を継続する。

## 8. Bootstrap Acceptance Test

今回の実装完了条件：

- `$loop` SkillがCodexに認識される。
- `loop doctor` が動作する。
- `loop start` が動作する。
- Codex CLIでサンプルタスクを実行できる。
- QA失敗を検出できる。
- 修正ループが動作する。
- 3回の試行上限が守られる。
- PR作成処理が動作する。
- GitHub Checksを取得できる。
- Checks失敗時に修正処理へ移行できる。
- Safe Mergeの条件判定が動作する。
- 承認待ち事項を保存できる。
- 再起動後に再開できる。
- 既存のLocus本体を破壊していない。

ローカルの自動テストは必須。

GitHubへの書き込みを伴うE2Eは専用の検証ブランチまたはテスト用リポジトリで実施する。

mainへの試験的マージは禁止する。

外部サービスの制約で検証できない機能は、未検証と明示する。

## 9. 今回の終了条件

環境構築が完了したら、以下を報告する。

1. 作成・変更したファイル
2. 実装した機能
3. テスト結果
4. GitHub連携状態
5. CI設定状態
6. 自動マージの有効・無効状態
7. 未解決事項
8. 次のターンで使用するコマンド

**今回のターンでは、Locus本体の自律開発ループを開始しない。**

環境構築と検証を終え、次のユーザーメッセージで `$loop` を実行できる状態にすること。

機能が未完成の場合は、完成したと報告しない。
