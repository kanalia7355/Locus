# Codex Autonomous Loop Engineering — Implementation Specification

## 0. Mission

Codexを用いた自律継続型ソフトウェア開発基盤を実装する。

ユーザーはVS CodeのCodex拡張を主な操作インターフェースとして使用する。バックグラウンドの継続実行にはCodex CLIを使用する。

本システムは、ユーザーがGoalを与えると、AIが設計、タスク分解、実装、検証、修正、レビュー、GitHub PR作成を進めることを目的とする。

人間の確認が必要な事項は原則として承認待ちキューに保存し、他に実行可能なタスクがある限り開発を継続する。

本指示書に従い、設計、実装、テスト、ドキュメント整備を順次実施すること。

### 絶対条件

1. 既存プロジェクトの機能を破壊しない。
2. 特定の言語・フレームワークに依存しない。
3. 実行状態を永続化する。
4. Codexのセッション終了後も再開可能にする。
5. AIの自己申告のみでタスクを完了扱いにしない。
6. 通常開発ではサブエージェントを起動しない。
7. 重要変更とPRマージ前は独立したコンテキストでレビューする。
8. 同一タスクの実装試行は初回を含め最大3回とする。
9. 機密情報をプロンプト、ログ、Gitに記録しない。
10. 人間の承認が必要な操作を迂回しない。
11. Goal、仕様、検証条件をAIの都合で緩和しない。
12. 承認されていない変更をmainへ反映しない。
13. 実行可能な検証手段がない場合、合格と判定しない。
14. 既存のAGENTS.mdやSkillsを無断で上書きしない。

## 1. Technology Stack

- Python 3.11以上
- Codex CLI
- VS Code Codex拡張
- Git
- GitHub CLI（gh）
- GitHub Actions
- pytest
- JSON Schema
- YAML
- SQLite（永続状態の正本）
- Markdown（人間向けの設計・進捗・判断記録）

CLI、認証方式、サンドボックス、出力形式については実装時点のCodex公式仕様を確認すること。非公開APIや未確認のCLIオプションを使用しない。

Python依存関係は `pyproject.toml` で管理する。

## 2. Repository Structure

以下を基準構成とする。

```text
project/
├── AGENTS.md
├── .agents/
│   └── skills/
│       ├── goal-planning/
│       │   └── SKILL.md
│       ├── architecture-review/
│       │   └── SKILL.md
│       ├── task-planning/
│       │   └── SKILL.md
│       ├── implementation-loop/
│       │   └── SKILL.md
│       ├── quality-review/
│       │   └── SKILL.md
│       ├── security-audit/
│       │   └── SKILL.md
│       └── decision-triage/
│           └── SKILL.md
├── .loop/
│   ├── config.yaml
│   ├── goal.md
│   ├── requirements.md
│   ├── architecture.md
│   ├── acceptance.md
│   ├── progress.md
│   ├── decisions.md
│   └── schemas/
│       ├── task.schema.json
│       ├── result.schema.json
│       └── decision.schema.json
├── loop_engine/
│   ├── cli.py
│   ├── controller.py
│   ├── scheduler.py
│   ├── codex_runner.py
│   ├── state_store.py
│   ├── verification.py
│   ├── reviewer.py
│   ├── approval.py
│   ├── git_manager.py
│   ├── github_manager.py
│   ├── recovery.py
│   ├── security.py
│   └── reporting.py
├── scripts/
│   └── verify.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── .github/
│   └── workflows/
│       └── loop-ci.yml
└── pyproject.toml
```

実行時データは `.loop/runtime/` に格納する。

SQLite DB、ロック、セッションログ、一時ファイル、認証情報はGit管理から除外する。

共有すべき設計・設定・タスク仕様はGit管理し、実行時状態とは分離する。

## 3. AGENTS.md

AGENTS.mdには以下の規則を実装する。

### 3.1 Startup

Codexは作業開始時に以下を確認する。

1. Goal
2. Requirements
3. Architecture
4. Acceptance Criteria
5. 現在のタスク
6. 過去の失敗記録
7. 変更可能範囲
8. 承認待ち事項
9. 利用可能なSkills

### 3.2 Implementation Rules

- タスク単位で作業する。
- 指定タスク以外を無断で変更しない。
- 変更前に関連コードを調査する。
- 必要なテストを実装する。
- 仕様に反する近道を禁止する。
- 検証を通す目的でテストを削除・弱体化しない。
- テスト失敗を隠蔽しない。
- 未完了事項を完了と報告しない。
- 作業終了時に構造化結果を返す。
- 進捗はControllerが永続化する。

### 3.3 Git Rules

Conventional Commitsを使用する。

例：

- feat: add document search API
- fix: handle invalid permissions
- refactor: simplify query pipeline
- test: cover authentication failures
- docs: update architecture

mainへの直接コミットは禁止。

履歴改変、強制Push、保護ブランチへの直接Pushは禁止。

### 3.4 Review Rules

通常開発でサブエージェントは起動しない。

独立レビューは別のCodex実行コンテキストで行う。

レビュー担当は原則として読み取り専用で、コードを直接修正しない。

レビューで問題が検出された場合、結果を実装担当へ返す。

## 4. Goal Planning

Goal入力から次を生成する。

1. 要求仕様
2. 非機能要件
3. アーキテクチャ
4. 技術的制約
5. 受け入れ基準
6. タスク依存グラフ
7. リスク一覧
8. 人間の判断が必要な事項

曖昧な要求を無断で確定しない。

判断を保留できる場合は、仮定と影響範囲を記録し、独立したタスクから先に実装する。

高リスクまたは不可逆な設計判断は事前承認を必要とする。

## 5. Task Model

各タスクに最低限以下を保持する。

```json
{
  "id": "TASK-001",
  "title": "Implement authentication API",
  "status": "ready",
  "priority": 50,
  "dependencies": [],
  "acceptance_criteria": [
    "Valid users can authenticate",
    "Invalid credentials are rejected"
  ],
  "verification_profile": "backend",
  "attempts": 0,
  "max_attempts": 3,
  "risk_level": "medium",
  "requires_approval": false,
  "branch": null,
  "worktree": null,
  "last_error": null
}
```

### Status

- planned
- ready
- running
- verifying
- reviewing
- completed
- blocked
- awaiting_approval
- failed
- cancelled

状態遷移を明示的に定義し、不正な遷移を拒否する。

タスクの依存関係に循環がないことを検証する。

## 6. Task Scheduler

Schedulerは次の順序で処理する。

1. 依存タスクが完了しているものを抽出する。
2. 承認待ちの依存関係を持つタスクを除外する。
3. リスクと優先度を評価する。
4. 実行可能なタスクを選択する。
5. 実行前にロックを取得する。
6. Codex Workerへ渡す。

承認待ちタスクが存在しても、独立したタスクがあれば処理を継続する。

実行可能タスクが存在しない場合は、理由を記録して待機または停止する。

初期バージョンは並列実行せず、1タスクずつ処理する。

## 7. Codex Execution

Codex CLIを非対話実行するRunnerを実装する。

Runnerの責務：

- CLI存在確認
- 認証状態の確認
- バージョン確認
- タスクプロンプト生成
- 作業ディレクトリ指定
- プロセス起動
- タイムアウト管理
- 標準出力・標準エラー取得
- 構造化結果の検証
- 終了コードの確認
- 実行履歴保存

Codexの実装結果はJSON Schemaに従って返す。

最低限の結果：

```json
{
  "task_id": "TASK-001",
  "status": "implemented",
  "summary": "Authentication API implemented",
  "files_changed": [
    "src/auth.py"
  ],
  "tests_added": [
    "tests/test_auth.py"
  ],
  "issues": [],
  "approval_requests": []
}
```

AIが返した成功状態は暫定結果として扱う。

最終的な成功判定はControllerが行う。

Codex CLIの実行時には最小権限のサンドボックスを使用する。

承認回避を目的とする無制限実行オプションは禁止する。

## 8. Implementation Loop

実装ループは以下のとおり。

```python
while controller.can_continue():
    task = scheduler.next_ready_task()

    if task is None:
        controller.handle_idle_state()
        break

    for attempt in range(task.attempts, 3):
        result = runner.execute(task)
        verification = verifier.run(task)

        state.record_attempt(
            task,
            result,
            verification
        )

        if verification.passed:
            break

    if not verification.passed:
        state.mark_blocked(task)
        continue

    review = reviewer.evaluate(task)

    if review.has_blocking_findings:
        state.mark_blocked(task)
        continue

    github.create_or_update_pr(task)
    state.mark_implementation_complete(task)
```

上記は概念コードであり、実装時には以下を必須とする。

- プロセス起動失敗と実装失敗を区別する。
- 検証不能時に成功扱いしない。
- レビュー失敗時も修正可能なら残り試行枠を使う。
- 3回の試行後はblockedへ移行する。
- PR作成だけでタスク完了としない。
- CI合格、レビュー、マージ、承認状態を別々に管理する。
- 中断時に再実行しても二重PRや二重コミットを発生させない。

## 9. Verification

検証は段階的に実施する。

### Level 1 — Static

- フォーマット
- Lint
- 型チェック
- 構文検査

### Level 2 — Functional

- Unit Tests
- Integration Tests
- API Contract Tests

### Level 3 — Security

- 依存関係の脆弱性
- 秘密情報混入
- 危険な権限変更
- 認証・認可の問題
- 不適切な外部通信

### Level 4 — Goal Alignment

- 要求仕様との整合性
- アーキテクチャ制約
- 受け入れ基準
- 未実装項目
- 回帰リスク

検証プロファイルはプロジェクトごとに設定できるようにする。

実行できない検証は `skipped` として記録する。

必須検証がskippedの場合は自動マージ不可とする。

検証スクリプトの変更は、実装対象コードとは別に審査する。

## 10. Independent Review

独立レビューは以下の場合に実行する。

- 重要なアーキテクチャ変更
- 認証・認可変更
- 外部通信・データアクセス変更
- 重要な依存関係追加
- PRマージ前

実装担当とレビュー担当は実行コンテキストを分離する。

レビュー担当には以下を提供する。

- Goal
- Requirements
- Architecture
- Acceptance Criteria
- Diff
- Test Results

レビュー担当の出力：

- severity
- file
- finding
- evidence
- recommended_action
- blocking

レビュー結果は構造化して保存する。

独立レビューによる修正サイクルは原則最大2回とし、全体の実装試行上限3回を超えない。

レビューが合格してもCIを省略しない。

## 11. Deferred Approval

承認方式はDeferredとする。

### Automatic

- 通常の機能実装
- テスト追加
- 軽微な修正
- ドキュメント更新
- 許可済み範囲内のリファクタリング

### Deferred Review

- 中程度の内部設計変更
- 新規依存ライブラリ
- 非破壊的なAPI変更
- 非公開設定の変更

Deferred Review対象はPRとして保存できるが、承認前の自動マージは禁止する。

### Mandatory Pre-Approval

- 本番環境への変更
- 外部公開
- 機密情報へのアクセス権拡大
- 破壊的データ操作
- 認証・認可の重大な変更
- 課金を伴う操作
- リポジトリ保護設定の変更
- 承認ポリシーそのものの緩和

承認待ち事項は以下を保持する。

```json
{
  "id": "DEC-001",
  "task_id": "TASK-008",
  "category": "architecture",
  "risk": "medium",
  "question": "Approve new caching dependency?",
  "options": [
    "approve",
    "reject",
    "revise"
  ],
  "status": "pending",
  "blocking_tasks": [
    "TASK-009"
  ]
}
```

承認は `approve`、`reject`、`revise` をサポートする。

人間が後から一括判断できるCLIを実装する。

承認記録には対象変更のハッシュ、判断日時、判断者、判断理由を残す。

## 12. Persistent State

SQLiteを状態の正本とする。

最低限のテーブル：

- goals
- tasks
- task_dependencies
- executions
- verification_results
- reviews
- decisions
- pull_requests
- checkpoints
- events

状態変更はトランザクションで行う。

重要なイベントは追記型ログに記録する。

進捗MarkdownはDBから生成する。

二重起動を防ぐため、プロジェクト単位の実行ロックを実装する。

## 13. Recovery

以下の障害から復旧可能にする。

- Codexの異常終了
- VS Codeの終了
- PC再起動
- ネットワーク切断
- GitHub APIエラー
- CI失敗
- タイムアウト
- 状態更新中のクラッシュ

再起動時には実行中タスクを検査する。

残存プロセス、Worktree、Git状態、PR状態を照合する。

不明な状態のタスクを無条件に再実行しない。

再実行前に重複操作の危険性を評価する。

## 14. GitHub Integration

GitHub CLIを利用する。

タスクごとにブランチを作成する。

命名規則：

`loop/TASK-001-short-description`

原則としてGit Worktreeで作業を分離する。

PR本文に以下を記載する。

- Task ID
- Goalとの関係
- 実装内容
- 変更ファイル
- テスト結果
- レビュー結果
- リスク
- 承認状態

### Safe Auto Merge

次のすべてを満たす場合に限り、自動マージを許可する。

1. 低リスク変更である。
2. 必須CIがすべて合格している。
3. 独立レビューで重大な指摘がない。
4. 承認待ち事項がない。
5. 保護ブランチのルールを満たす。
6. 最新のベースブランチに対して検証済みである。
7. 変更対象が自動マージ許可範囲内である。
8. 人間が事前に自動マージを許可している。

上記を満たさないPRは保留する。

GitHubの保護ルールや必須レビューを迂回しない。

PR作成・マージ操作には最小権限の認証を使用する。

## 15. CLI Interface

以下のコマンドを提供する。

```bash
loop init
loop plan
loop start
loop pause
loop resume
loop stop
loop status
loop decisions
loop approve DEC-001
loop reject DEC-001
loop report
loop doctor
```

各コマンドは `python -m loop_engine.cli` からも呼び出せるようにする。

`loop start` は明示的なユーザー操作で起動する。

`loop stop` は実行中プロセスを安全に停止し、状態を保存する。

`loop doctor` は環境、認証、Git、依存関係、設定を検査する。

## 16. Safety and Resource Limits

以下の設定を実装する。

```yaml
loop:
  max_attempts_per_task: 3
  max_review_cycles: 2
  max_concurrent_tasks: 1
  max_runtime_minutes: 360
  max_tasks_per_run: 20
  task_timeout_minutes: 30

approval:
  mode: deferred
  require_preapproval_for_high_risk: true

github:
  auto_merge: safe
  protect_default_branch: true

security:
  allow_production_changes: false
  allow_destructive_operations: false
  allow_unrestricted_execution: false
```

利用するCodexの認証方式に応じて、使用量・費用の制限を追加する。

API利用額を正確に取得できない環境では、金額上限が保証されていると表示しない。

時間、タスク数、実行回数による制限を必須とする。

## 17. Implementation Phases

### Phase 1 — Foundation

- CLI
- 設定管理
- SQLite
- JSON Schema
- 状態遷移
- ロック
- ログ

### Phase 2 — Planning

- Goal解析
- 要求定義
- 設計生成
- タスク分解
- 依存関係管理
- Skills

### Phase 3 — Execution

- Codex CLI Runner
- タスク実行
- タイムアウト
- 最大3回の再試行
- 自動検証
- 状態保存

### Phase 4 — Review and Approval

- 独立レビュー
- セキュリティ検証
- Deferred Approval
- 承認キュー
- 一括判断

### Phase 5 — GitHub

- Worktree
- Conventional Commits
- PR生成
- CI確認
- Safe Auto Merge

### Phase 6 — Recovery and E2E

- クラッシュ復旧
- 二重実行防止
- GitHub障害への対応
- End-to-Endテスト
- ドキュメント整備

各Phase終了時に検証する。

未完了のPhaseを完了扱いにしない。

## 18. Acceptance Criteria

以下を満たした場合に実装完了とする。

- Goalからタスクを生成できる。
- タスクの依存関係を管理できる。
- Codex CLIで実装タスクを実行できる。
- テスト失敗時に最大3回まで試行できる。
- 失敗タスクを保留して別タスクへ進める。
- 承認待ち事項を保存できる。
- 人間が後から承認・却下できる。
- セッション終了後に再開できる。
- GitHub PRを作成できる。
- 安全条件を満たすPRのみ自動マージできる。
- 必須CIを迂回できない。
- 状態の二重更新を防止できる。
- 終了時に進捗レポートを生成できる。
- 外部サービスをモックしたE2Eテストが通過する。
- 実際のCodex CLIとGitHubを使用した限定的な統合テストが可能である。

## 19. Development Instructions

実装はPhase 1から順番に開始すること。

各Phaseで次のサイクルを実施する。

1. 現状を調査する。
2. 実装計画を作成する。
3. 必要なファイルを実装する。
4. テストを追加する。
5. 検証する。
6. 問題があれば修正する。
7. 独立レビューを実施する。
8. 進捗を保存する。
9. 次のPhaseへ進む。

判断が必要な事項は承認キューへ記録する。

承認不要の作業が残っている限り、作業を継続する。

実装不能な要件、CLI仕様上の制約、認証の問題、重大な安全上の問題が発生した場合は、事実と影響範囲を記録する。

問題を隠して代替実装を成功扱いしない。

最後に、実装済み機能、未実装機能、検証結果、残存リスク、使用方法を報告する。
