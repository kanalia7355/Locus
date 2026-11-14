# Phase 進捗サマリ: `phase-4-closeout`

- **対象 Phase**: `PH-ROADMAP-3`（残部: ingestion 状態・再開性）＋ `PH-ROADMAP-4`（残部: streaming / queue priority・fairness / usability・accessibility audit）＋ 統合ゲート修復。`docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md` §4「Parallelizable work」の isolated 並行条件に基づくバッチ。
- **対象ブランチ**: `phase/4-closeout`（ベース: 現行統合ブランチ `loop/local-development`、タスクブランチ `task/<TASK-ID>`）
- **最終更新日時**: `2026-11-14T18:15:00+09:00`
- **更新責任者**: オーケストレーター (DeepAI Code thread d4a9ead3, owner 指示により 20 分間隔で担当)。※ワーカーによる編集禁止
- **起動根拠**: Owner 指示 2026-11-14「サブエージェント5体同時起動・20分おきオーケストレーション」。
  `DEVELOPMENT_POLICY.md` の単一実装エージェント原則と本バッチは矛盾するため、
  owner の明示指示により本バッチ限定で例外適用。安全策: 全タスク git worktree 分離、
  `main` 直接 push 禁止、実装モデル≠レビューモデル、試行上限 (3回) / レビュー上限 (2周) 遵守。

---

## 1. Phase 完了条件（Gate Criteria）

- [ ] 統合ゲート: `loop/local-development` HEAD で GitHub Actions 3 ワークフロー (Prototype quality / Loop engine checks / PR title convention) がすべて green
- [ ] 対象タスク 5 件がすべて `status: done`（試行上限内で）
- [ ] Phase 節目のフルテストスイート検証 (`scripts/verify.py --e2e --audit`) が PASS
- [ ] 未解決の `blocked` タスクや人間判断待ち (Escalation) が残っていないこと
- [ ] 本バッチはプロトタイプ範囲のみ。production TLS/MFA/実データ/外部コネクタ等は gate 付き繰延のまま（変更しない）

## 2. タスク一覧と現在状態

| Task ID | タイトル / 要件 ID | Weight | Status | Assignee | Model | Attempts | Worktree / Branch | Updated |
|---|---|---|---|---|---|---|---|---|
| `T-PH4-G1` | Prototype quality E2E timeout 修復 (統合ゲート解消) | `heavy` | `done` | `deepai` | `deepai/gemini-4-hydrogen` | `1` | 統合済み: `4fc9b48` (loop/local-development) | `2026-11-14T18:15:00+09:00` |
| `T-PH4-101` | ローカル LLM ストリーミング応答 (`PH-ROADMAP-4` 残部) | `heavy` | `todo` | `unassigned` | `deepai/kimi-k3.1-pro` | `0` | `task/T-PH4-101` | `2026-11-14T17:35:00+09:00` |
| `T-PH4-102` | 質問ジョブの優先度・公平性 (bounded queue, `PH-ROADMAP-4` 残部) | `medium` | `todo` | `unassigned` | `deepai/gpt-6.1-terra` | `0` | `task/T-PH4-102` | `2026-11-14T17:35:00+09:00` |
| `T-PH3-101` | 取り込み状態の粒度・再開性強化 (`PH-ROADMAP-3` 残部) | `medium` | `doing` | `deepai` | `deepai/deepseek-v4.1-flash` | `1` | `task/T-PH3-101` (thread mcp:ada6665a) | `2026-11-14T18:15:00+09:00` |
| `T-PH4-103` | アクセシビリティ・キーボード・モバイル監査と修正 (`PH-ROADMAP-4` 残部) | `medium` | `doing` | `deepai` | `deepai/minimax-m3.1-flash` | `1` | `task/T-PH4-103` (thread mcp:7ab0f9e1) | `2026-11-14T17:43:00+09:00` |

## 3. 統合 (マージ) 順序と衝突オーナー

`backend/app/service.py`・`frontend/src/App.tsx` は複数タスクのホットスポットのため、
統合はオーケストレーターが以下の順序で直列実施する（各マージ後に当該タスクの関連テストを再実行）。

1. `T-PH4-G1`（ゲート修復 — 最優先、`loop/local-development` へ早期マージ）
2. `T-PH3-101`（backend 主）
3. `T-PH4-102`（backend queue + ChatQueue UI）
4. `T-PH4-101`（streaming, backend + App.tsx）
5. `T-PH4-103`（accessibility, App.tsx 最後）

衝突時は後続タスクが rebase して解消する。オーケストレーター以外は `phase/4-closeout` や
`loop/local-development` にマージしない。

## 4. 進行管理

- **進捗ログ**:
  - 17:46 JST: `T-PH4-G1` 実装完了 → `status: review`。原因は回帰 (commit `89e71c4` の履歴ボタン表記変更に
    E2E ロケータが未追従)。修正は `frontend/e2e/workspace.spec.ts` ロケータ 1 行の最小変更。
    実装者証跡: 修正前 E2E 3/3 再現 FAIL、修正後 E2E 3/3 PASS・Vitest 79 green・lint/typecheck green。
  - 17:58 JST: `T-PH4-G1` の独立レビューを別モデル (deepai/glm-5.3-flash) で委譲開始 (round 1)。
  - 18:10 JST: レビュー **APPROVED** (round 1, 別モデル glm-5.3-flash; low 指攝 1件のみ・修正不要)。QA 照合 PASS で
    `status: done` → `task/T-PH4-G1` を `loop/local-development` に no-ff マージ (`4fc9b48`)。
    マージ HEAD で Vitest 79 passed (ローカル)。ローカル .venv は既知の `_cffi_backend` 破損のため E2E は
    worktree 内実証 (13/13 ×実装者・レビュアー, コード SHA 同一) を使用し、正本ゲートは push 後の exact-head CI。
  - 18:14 JST: `T-PH3-101` を起動 (thread mcp:ada6665a, running 確認)。
- 委譲レビューもアクティブ枠を消費するため、`T-PH3-101` の起動は次サイクルへ繰り越し。

- **起動キュー** (2026-11-14 17:43 JST): プラットフォームの同時実行上限 (アクティブ DeepAI スレッド 2) により、
  `T-PH4-G1` と `T-PH4-103` のみ起動済み。`T-PH3-101` → `T-PH4-102` → `T-PH4-101` はローリング起動
  （20分オーケストレーションでスロット空き時に起動）。5 体同時はプラットフォーム上限により不可能なため、
  owner 指示の趣旨（並列爆速）を上限内で最大化する。

- 20 分間隔のスケジュールタスクがこのスレッドへオーケストレーション起動する（owner 指示）。
  `PROTOCOL.md` の 30 分ポーリング (`pollIntervalMs=1,800,000`) はハーネス拡張側で継続。両者は競合しない。
- レビューは `status: review` 遷移時にオーケストレーターが frontmatter `reviewer: <runner>/<model>`
  を割当て、実装モデルと異なるモデルで独立実施する（最大 2 周回）。
- `loop_engine/**`, `docs/plans/**`, `docs/planning/**`, `.pi/**` は本バッチのどのタスクも触らない。
