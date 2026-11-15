# Phase 進捗サマリ: `phase-<slug>`

- **対象 Phase**: `phase-<slug>`（`docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md` 参照）
- **対象ブランチ**: `phase/<slug>`（ベース: `main`）
- **最終更新日時**: `2026-11-12T13:00:00+09:00`
- **更新責任者**: オーケストレーター (`gpt-6-luna`) ※ワーカーによる編集禁止

---

## 1. Phase 完了条件（Gate Criteria）

- [ ] 対象要件 ID（`docs/plans/REQUIREMENTS_TRACEABILITY_MATRIX.md`）の全タスクが `status: done` であること
- [ ] Phase 節目のフルテストスイート検証が PASS していること
- [ ] `phase/<slug>` ブランチの GitHub Actions CI がすべてグリーン（`success`）であること
- [ ] 未解決の `blocked` タスクや人間判断待ち（Escalation）が残っていないこと

---

## 2. タスク一覧と現在状態

| Task ID | タイトル / 要件 ID | Weight | Status | Assignee | Model | Attempts | Worktree / Branch | Updated |
|---|---|---|---|---|---|---|---|---|
| `T-001` | （例）機能実装 (`REQ-XXX`) | `medium` | `todo` | `unassigned` | `-` | `0` | `task/T-001` | `2026-11-12T13:00:00+09:00` |

---

## 3. モデル別 QA 通過率集計（OpenCode 無料プール・agy 実績追跡）

`docs/agent/MODEL_ROTATION.md` §3 に基づき、各モデルの割当回数・QA 通過（`done`）回数・差し戻し回数・枠切れ（Quota）発生回数を集計する。

| Runner | Model | 割当回数 | QA 通過 (`done`) | レビュー/QA 差し戻し | 枠切れ切替 (Quota) | QA 通過率 |
|---|---|---|---|---|---|---|
| `agy` | `Gemini 4 Argon` | 0 | 0 | 0 | 0 | - |
| `agy` | `Claude Opus 5.5` | 0 | 0 | 0 | 0 | - |
| `agy` | `Claude Sonnet 5.5` | 0 | 0 | 0 | 0 | - |
| `agy` | `Gemini 3.8 Flash` | 0 | 0 | 0 | 0 | - |
| `agy` | `Gemini 4 Carbon` | 0 | 0 | 0 | 0 | - |
| `agy` | `GPT-OSS 120B` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/beam-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/big-pickle` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/deepseek-v4.1-flash-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/flint-40b-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/glm-5.3-flash-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/iceman-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/inkling-2-small-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/longcat-2.5-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/mimo-v2.6-flash-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/minimax-m3.1-flash-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/nemotron-3.5-lightning-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/nemotron-3.5-super-vl-free` | 0 | 0 | 0 | 0 | - |
| `ollama` | `ollama/gemma3:4b` | 0 | 0 | 0 | 0 | - |

---

## 4. Blocked タスク・人間へのエスカレーション事項

仕様解釈の曖昧さ、設計トレードオフ、試行上限（最大3回 / レビュー最大2周）到達、または全モデル枠枯渇により停止した項目を記録する。

- （現在なし）
