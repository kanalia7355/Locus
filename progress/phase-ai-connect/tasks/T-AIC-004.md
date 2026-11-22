---
id: T-AIC-004
phase: phase-ai-connect
status: blocked
assignee: unassigned
model: unassigned
weight: heavy
updated: 2026-11-22T13:56:00+09:00
attempts: 0
allowed_paths: progress/phase-ai-connect/material/
test_cmd: python -m pytest tests/test_agents_registry.py -q
---

# Task `T-AIC-004`: CLIエージェント・アダプタの設計ゲート（設計のみ）

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR`（必須要件 1・4・5・7、実装順序 3〜5）
- **Status の理由（blocked）**:
  本タスクは **owner 決定なしに着手しない**。下記「owner 決定事項」の回答が
  frontmatter の status を todo に変える条件である（planner の自動 unblock 対象外。
  blocker は古くなっていない——Runner 境界は依然として未証明）。
- **Background**:
  - ツール実行を伴うエージェント（Claude Code / Codex / Gemini CLI 等）の接続は、
    チャット用 API 接続（T-AIC-001〜003）とは別レイヤーの問題である。
  - 現状の遮断は意図的なもの:
    - `backend/app/agents/registry.py` は metadata-only を明記し、dispatch・
      adapter 有効化・認証情報処理・egress を行わない。
    - `POST /api/workspaces/{id}/agent-dispatch-attempts` は常に
      409 `Runner boundary is unproven; dispatch is disabled` を返す。
    - `docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md` §12 は activation を未承認としている。
  - 参考実装（opencode）:
    - `packages/core/src/plugin/provider/claude-agent/` —
      Claude Agent SDK を LanguageModel としてラップし、ツールは MCP 経由で橋渡しする。
    - `packages/cli/src/acp/agent.ts` — エージェント自身が ACP（Agent Client Protocol）
      のサーバとして振る舞い、`session/new` / `session/prompt` 等の JSON-RPC を受ける。
    - つまり「エージェント接続」は (a) 公式CLIを headless で起動する、
      (b) Agent SDK をライブラリとして埋め込む、(c) ACP / opencode のような
      既製エージェントを外部プロセスとして呼ぶ、の3経路がありうる。
- **Implementation Details**（設計文書の更新のみ。コードは書かない）:
  1. 上記3経路について、Locus の既存境界との適合を
     `HYBRID_AGENT_ADAPTER_DESIGN.md` に追記する:
     - 実行隔離（作業ディレクトリ、ファイルアクセス、ネットワーク）の強制方法
     - 認証情報の置き場（同文書 §4.2 Option 1 = CLIネイティブログイン・端末側保持
       を既定とし、サーバへ値を送る経路は設けない）
     - 分類ポリシーと egress 判定を dispatch のどの段階で通すか
     - 監査に残す項目（利用者、workspace、adapter、モデル、判定結果。本文は残さない）
     - 失敗・中断時の後始末（プロセス終了、途中成果物の扱い）
  2. Runner 境界の「証明」に必要な検証項目を、同文書 §9 の検証計画に
     具体的な合否条件つきで列挙する（mock／stub 認証のみで実施可能な範囲に限る）。
  3. dispatch の 409 を外す条件を「activation gate」として明文化し、
     本タスクの成果物は **次フェーズの実装タスク起票に必要な決定材料**とする。
- **owner 決定事項**（回答があるまで blocked）:
  1. 接続経路の第一候補はどれか: (a) 公式CLI headless / (b) Agent SDK 埋め込み /
     (c) ACP・opencode 等の既製エージェント呼び出し
  2. 最初の対応エージェントはどれか（Claude Code を想定するが未決定）
  3. 実行場所は Desktop Runner 前提でよいか（Server Runner での CLI 実行を許すか）
  4. dispatch 解禁の前提として、隔離の実証（コンテナ／OSサンドボックス）を
     どこまで要求するか
- **Acceptance Criteria**:
  1. 3経路の比較と推奨が、既存境界（ゼロツール境界、presence-only、
     分類ポリシー、監査）との適合表つきで設計文書に追記されている。
  2. Runner 境界の検証項目に合否条件が付いている。
  3. owner 決定事項への回答が記録され、次フェーズの実装タスクが起票可能な状態になる。
  4. **本タスクではコード・スキーマ・dispatch の挙動を一切変更していない。**
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
  - なし（設計タスク）
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
