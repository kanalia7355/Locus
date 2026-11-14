# Phase 進捗サマリ: `phase-4-closeout`

- **対象 Phase**: `PH-ROADMAP-3`（残部: ingestion 状態・再開性）＋ `PH-ROADMAP-4`（残部: streaming / queue priority・fairness / usability・accessibility audit）＋ 統合ゲート修復。`docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md` §4「Parallelizable work」の isolated 並行条件に基づくバッチ。
- **対象ブランチ**: `phase/4-closeout`（ベース: 現行統合ブランチ `loop/local-development`、タスクブランチ `task/<TASK-ID>`）
- **最終更新日時**: `2026-11-14T19:55:00+09:00`
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
| `T-PH4-102` | 質問ジョブの優先度・公平性 (bounded queue, `PH-ROADMAP-4` 残部) | `medium` | `doing` | `deepai` | `deepai/gpt-6.1-terra` → 引継ぎ (枠切れ) | `1` | `task/T-PH4-102` (実装完了・未コミット, クォータ回復後 17:26 JST に記録引き継ぎ) | `2026-11-14T20:25:00+09:00` |
| `T-PH3-101` | 取り込み状態の粒度・再開性強化 (`PH-ROADMAP-3` 残部) | `medium` | `done` | `deepai` | `deepai/deepseek-v4.1-flash` | `2` | 統合済み: `548cb55` (loop/local-development) | `2026-11-14T20:00:00+09:00` |
| `T-PH4-103` | アクセシビリティ・キーボード・モバイル監査と修正 (`PH-ROADMAP-4` 残部) | `medium` | `blocked` | `deepai` | `deepai/minimax-m3.1-flash` | `3` (試行上限) | 統合 `7b2b3d9`; secret scan (a11y.spec L23-24) で CI 赤 → owner 判断待ち | `2026-11-14T20:15:00+09:00` |
| `T-PH3-102` | live フローでの indexing 段の観測・取消 (T-PH3-101 フォローアップ) | `light` | `todo` | `unassigned` | `-` | `0` | 未起動 (キュー) | `2026-11-14T20:00:00+09:00` |

## 2b. レビュー指揗に基づくフォローアップ起票

- `T-PH3-101` 独立レビュー round 1 指摘 4 (Medium) を受けて `T-PH3-102` を起票
  (App.tsx/api.ts の indexing 表示・取消・ポーリング統合。許可パス: App.tsx, api.ts, App.test.tsx)。
  スロット空き時に T-PH4-101 と並行起動可 (ファイル競合なし)。
  - 19:52 JST: `T-PH4-103` attempt 3 (a11y.spec 自己完結化 `0d274fc`) を no-ff マージ (`7b2b3d9`)。
    ローカル: Vitest 15 files / 84 passed。push 後 hosted CI で Prototype quality / Loop engine checks の
    両方が **offline secret scan 2 findings** (`a11y.spec.ts` L23-24 のパスワード定数リテラル) で失敗。
    Python 1068 passed / engine 907 passed / ローカル a11y E2E 5/5 は全 green。
  - 20:15 JST: `T-PH4-103` は attempt 上限 3/3 到達のため **`blocked`** (owner 判断待ち)。
    機械的 1 行修正 (静的リテラル排除) の許可を owner に依頼。scan 設定・テスト弱体化は提案しない。
  - 20:25 JST: `T-PH4-102` 引き継ぎ (gemini-4-carbon) も **theos_insufficient で失敗** — DeepAI クォータは
    全モデル共通 (回復 2026-11-15 17:26 JST)。ワーカー新規起動は本日中に不可能。
    codex は owner 指示により使用禁止。T-PH4-102 は実装・検証済み (worktree 未コミット差分) で
    記録・コミットのみ残存。次回スケジュール起動ではクォータ回復を確認してから再委譲する。
  - 20:12 JST: `T-PH4-102` 引き継ぎを **gemini-4-carbon** (未使用モデル) で再試行 (既存 worktree 束縛)。
    codex は owner 指示により使用禁止。
  - 19:31 JST: `T-PH3-101` を no-ff マージ (`548cb55`)。マージ HEAD ローカル検証: pytest 4スイート 34 passed,
    ruff format 142 files already formatted。セキュリティ審査合格 (per-page ACL 維持・シード緩和は権限昇格なし)。
  - 19:32 JST: 私の docs コミット `c83a672` のタイトルが 100 文字制約超過で PR title convention が赤
    (push レンジバリデーション)。履歴書き換えは禁止のため記録のみ、以後タイトル 100 文字以内を徹底。
    Prototype quality も a11y.spec 未修復のため継続赤 (T-PH4-103 attempt 3 修復中)。
  - 19:34 JST: `T-PH4-102` 引き継ぎ (kimi-k3.1-pro) も **theos_insufficient で失敗** — クォータは
    モデル横断で共有 (回復 2026-11-15 17:26 JST)。実装・検証済み差分は worktree に残存。
    **cross-provider fallback**: codex/gpt-6-astra に検証・記録・コミット完了を委譲 (task 上は
    ローテーション、attempts 1 のまま)。`T-PH4-101` (kimi-k3.1-pro 予定) は deepai 側クォータ状況を
    次回確認してから起動 (必要ならモデル変更)。

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
  - 18:11-18:12 JST: `T-PH3-101` (39fcd3a) と `T-PH4-103` (8311f48→2ee968f) が実装完了 → 両者 `status: review`。
    許可パス遵守を差分で確認済み。`T-PH4-103` は a11y.spec.ts 新規410行 + App.tsx/styles.css 最小修正。
  - 18:19 JST: 両タスクの独立レビューを別モデル (deepai/glm-5.3-flash) で並行委譲 (round 1)。
  - 18:29 JST: `T-PH4-103` レビュー round 1 = **CHANGES_REQUIRED** (必須 F1 Medium: sidebar Escape がデスクトップでも
    発火しベースライン外の折りたたみ。修正はビューポートゲート1行)。REVIEW 欄に全文記録して `status: doing` に
    差戻しし、修正指示を送信 (review round 2)。F2/F3 は非阻塞。指摘に基づき F3 は G1 スコープと確認 (既に統合済み)。
  - 18:30 JST: 修正指示を `T-PH4-103` スレッドへ送信、再実装開始。
  - 18:59 JST: `T-PH4-103` F1 修正完了 (`44569be`, attempts 2)。Escape ハンドラにビューポートゲート実装、
    デスクトップ幅 Escape assert を a11y.spec.ts に追加、Vitest 83 passed・a11y 5/5・typecheck/lint green、
    既存 E2E 12/13 (1件は base 未更新に起因する G1 スコープ既存課題、変更前後で同一)。→ `status: review`。
  - 19:07 JST: `T-PH4-103` レビュー round 2 (2周目・上限) を委譲開始。
  - 19:07 JST: `T-PH3-101` レビュー round 1 = **CHANGES_REQUIRED** (既存 8 テスト破壊: seed_synthetic が
    `cancelled` 化 [High]、`related()` IndexError [High]、ruff format ゲート落ち [Medium]。
    セキュリティ/ACL 審査は合格・新規設計は高評価)。REVIEW 欄に全文記録して `status: doing` へ差戻し、
    修正指示を送信 (round 2・最終周回)。範囲外指摘 (App.tsx/api.ts の indexing 表示) は別タスク起票予定。
  - 19:09 JST: `T-PH4-103` レビュー round 2 = **APPROVED** (F1 解消確認、reviewer が REVIEW 記録をブランチへ
    コミット済み 1fcb0e2)。QA PASS → `status: done`。
  - 19:11 JST: `T-PH4-102` が判断待ちで停止 (推測実装を回避: ChatQueue.tsx 未存在・Load API 完全一致テストが
    許可パス外)。オーケストレーター裁定後に実装再開。
  - 19:13 JST: `T-PH3-101` round 2 修正完了 (`a4fae87`, status: review, attempts 2)。
  - 19:18 JST: `T-PH4-102` が実装完了直後 (backend 41 / frontend 26 テスト green, mypy/ruff green) に
    **gpt-6.1-terra のクォータ枯渇** (theos_insufficient, 2026-11-15 08:26 UTC 回復) で fail。
    実装差分は worktree に未コミットで残存。枠切れは試行消費ではない (PROTOCOL §5.4) ため
    attempts 1 のまま、次スロットで**別モデルの引き継ぎワーカー**を同一 worktree/branch で起動する
    (REPORT 未記入・コミット未実施を完了させる)。検証済み実装内容: fair-share スケジューラ
    (`last_chat_user` 排他の round-robin)、`/api/admin/load` へ `queued_per_user` 追加、
    App.tsx 待機表示の文言追記。オーケストレーター裁定: ChatQueue.tsx を allowed_paths から除外し App.tsx (待機表示) を許可、
    Load 分布追加と test_admin_project_storage_load.py の**追記形式の拡張**を許可 (緩和禁止)。
    裁定をタスクファイルに記録して実装再開。
  - 19:13 JST: `T-PH4-103` を no-ff マージ (`ea6b508`)。マージ HEAD ローカル: Vitest 15 files / 83 passed,
    typecheck green。push 後 hosted CI で **Prototype quality FAIL**: 新規 a11y.spec.ts 5件全て
    `ログインに失敗しました: test-researcher-5` — spec が ambient DB 状態 (採番済ユーザー) に依存し,
    CI fresh DB で存在しないことが原因。attempt 3 (最終) で a11y.spec.ts 自己完結化の修復指示を送信。
    workspace.spec.ts 13/13 は引き緑 (G1 修正が有効)。
    レビュー完了後に統合順序 §3 (PH3-101 → PH4-102 → PH4-101 → PH4-103) でマージし、
    スロット空き時に `T-PH4-102` / `T-PH4-101` を起動する。
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
