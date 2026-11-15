# Phase 進捗サマリ: `phase-4-closeout`

- **対象 Phase**: `PH-ROADMAP-3`（残部: ingestion 状態・再開性）＋ `PH-ROADMAP-4`（残部: streaming / queue priority・fairness / usability・accessibility audit）＋ 統合ゲート修復。`docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md` §4「Parallelizable work」の isolated 並行条件に基づくバッチ。
- **対象ブランチ**: `phase/4-closeout`（ベース: 現行統合ブランチ `loop/local-development`、タスクブランチ `task/<TASK-ID>`）
- **最終更新日時**: `2026-11-15T14:50:00+09:00`
- **更新責任者**: 2026-11-15 より owner 直接指示に基づく単一エージェント運用 (Claude Code)。
  DeepAI 全モデルのアカウント枠枯渇と codex 使用禁止により、サブエージェント方式のオーケストレーションは継続不能。
  `CLAUDE.md` / `AGENTS.md` の単一実装エージェント原則へ復帰し、実装・検証・記録を同一エージェントが担当する
  （別モデル独立レビューは実施不能のため、各タスクの REVIEW 欄に既知の逸脱として明記する）。
- **起動根拠**: Owner 指示 2026-11-14「サブエージェント5体同時起動・20分おきオーケストレーション」。
  `DEVELOPMENT_POLICY.md` の単一実装エージェント原則と本バッチは矛盾するため、
  owner の明示指示により本バッチ限定で例外適用。安全策: 全タスク git worktree 分離、
  `main` 直接 push 禁止、実装モデル≠レビューモデル、試行上限 (3回) / レビュー上限 (2周) 遵守。

---

## 1. Phase 完了条件（Gate Criteria）

- [x] 統合ゲート: `loop/local-development` `64e439b` で 3 ワークフロー (Prototype quality / Loop engine checks / PR title convention) がすべて green。`6d7d918` (T-PH4-101) でも 3 ワークフローすべて green
- [x] 対象タスク（当初 5 件＋フォローアップ 2 件 = `T-PH4-G1` / `T-PH4-101` / `T-PH4-102` / `T-PH3-101` / `T-PH4-103` / `T-PH3-102` / `T-PH4-104`）がすべて `status: done`
- [x] Phase 節目のフル検証: ローカルで全チェックを個別実行し PASS (Python 1149 + integration/e2e 66、Vitest 88、Playwright 18、ruff/mypy/secret scan/build)。予算付き `verify.py` は Windows では `python-tests` が 120 秒上限で必ず timeout するため、同等判定は hosted CI を正本とする
- [x] 未解決の `blocked` タスクなし（`T-PH4-103` は 2026-11-15 に解消）。残る人間判断待ちは「別モデル独立レビューの要否」のみ（各タスク REVIEW 欄に記録）
- [ ] 本バッチはプロトタイプ範囲のみ。production TLS/MFA/実データ/外部コネクタ等は gate 付き繰延のまま（変更しない）

## 2. タスク一覧と現在状態

| Task ID | タイトル / 要件 ID | Weight | Status | Assignee | Model | Attempts | Worktree / Branch | Updated |
|---|---|---|---|---|---|---|---|---|
| `T-PH4-G1` | Prototype quality E2E timeout 修復 (統合ゲート解消) | `heavy` | `done` | `deepai` | `deepai/gemini-4-hydrogen` | `1` | 統合済み: `4fc9b48` (loop/local-development) | `2026-11-14T18:15:00+09:00` |
| `T-PH4-101` | ローカル LLM ストリーミング応答 (`PH-ROADMAP-4` 残部) | `heavy` | `done` | `claude-code` | `claude-opus-5` | `1` | 統合ブランチへ直接実装 | `2026-11-15T15:50:00+09:00` |
| `T-PH4-102` | 質問ジョブの優先度・公平性 (bounded queue, `PH-ROADMAP-4` 残部) | `medium` | `done` | `claude-code` | `gpt-6.1-terra` (実装) → `claude-opus-5` (検証・記録) | `1` | 統合済み: 統合ブランチへ 3-way 適用 | `2026-11-15T14:45:00+09:00` |
| `T-PH3-101` | 取り込み状態の粒度・再開性強化 (`PH-ROADMAP-3` 残部) | `medium` | `done` | `deepai` | `deepai/deepseek-v4.1-flash` | `2` | 統合済み: `548cb55` (loop/local-development) | `2026-11-14T20:00:00+09:00` |
| `T-PH4-103` | アクセシビリティ・キーボード・モバイル監査と修正 (`PH-ROADMAP-4` 残部) | `medium` | `done` | `claude-code` | `minimax-m3.1-flash` → `claude-opus-5` (CI 修復) | `3` | 統合 `7b2b3d9` + secret scan 修復 (資格情報リテラル排除) | `2026-11-15T14:40:00+09:00` |
| `T-PH3-102` | live フローでの indexing 段の観測・取消 (T-PH3-101 フォローアップ) | `light` | `done` | `claude-code` | `claude-opus-5` | `1` | 統合ブランチへ直接実装 | `2026-11-15T14:55:00+09:00` |
| `T-PH4-104` | 出典ダイアログのスクロール追従 (E2E 既存失敗・CI でも再現) | `light` | `done` | `claude-code` | `claude-opus-5` | `1` | 統合ブランチへ直接実装 | `2026-11-15T15:20:00+09:00` |
| `T-PH4-105` | 代表的な同時利用・処理能力の実測 (`PH-ROADMAP-4` 最終残件) | `medium` | `done` | `claude-code` | `claude-opus-5` | `1` | owner 回答 (同時10・口座30〜40) に基づき実測 | `2026-11-15T16:40:00+09:00` |

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

## 2c. 2026-11-15 owner 直接指示サイクル（単一エージェント復帰）

- 14:00 JST: owner 指示により Claude Code 単独で再開。`docs/planning/**` を読み直し、
  製品目的（機密性と閲覧権限を保った研究資料の根拠付き活用）と Phase 4 残件の整合を確認。
  `docs/planning/**` は改変していない（`CONSTRAINTS.md` §5-2 遵守）。
- 14:10 JST: **`T-PH4-103` の CI 赤を解消**。原因は a11y.spec の静的パスワード定数。
  spec 内で生成済みの一意な利用者 ID から導出する最小修正で、スキャン設定・assertion は未変更。
- 14:15 JST: **偽グリーンの根本原因を是正（恒久対策）**。`detect_secrets` が既定エンコーディングで
  読めないファイルを無言で読み飛ばすため、Windows (cp932) では日本語を含む UTF-8 ファイルが
  丸ごと未走査だった。`scripts/secret_scan.py` の子プロセスに `PYTHONUTF8=1` を付与し、
  ローカルと hosted CI の走査対象を一致させた。対照実験で検知・非検知の両方を確認済み。
- 14:20 JST: **ローカル検証環境を CI と一致させた**（自己改善）。`.venv` は Python 3.10 で
  `_cffi_backend` / `pydantic_core` / `librt` が壊れており、backend テスト・mypy・Playwright E2E が
  ローカルで一切実行できなかった（これが「ローカル実証は worktree 内のみ」という従来の制約の正体）。
  CI と同じ Python 3.13 + `backend/requirements.lock` + `-e .[dev]` で再作成し、
  旧環境は `.venv310-broken` として退避。以後ローカルでフル検証が可能。
- 14:30 JST: **`T-PH4-102` を統合**。枠枯渇で worktree に未コミット残存していた実装差分を
  3-way で統合ブランチへ適用し、受入条件照合とフル検証を実施して `done`。
- 14:45 JST: フル検証結果（統合 HEAD、ローカル）:
  Python 1144 passed / 3 skipped ＋ integration・e2e 66 passed / 6 skipped、
  ruff check green / 142 files formatted / mypy 9 files clean、
  Vitest 15 files 85 passed、typecheck・lint・build green、secret scan 0 findings、
  Playwright E2E 18 件中 17 passed。
  失敗 1 件（`workspace.spec.ts:180` の `dialog.scrollTop > 0`）は**本サイクルの変更前 HEAD でも同一に再現**する
  既存不具合のため、`T-PH4-104` として起票（アサーション緩和は禁止と明記）。
- 14:55 JST: **`T-PH3-102` 完了**。`indexing` 段のポーリング継続・取消ボタン表示・`statusName` を修正。
  添付ファイルも同じ `documents` テーブルの `indexing` 段を通るため、指摘の 2 箇所に加えて
  添付ポーリングの 2 箇所も同時に修正し、`api.ts` の `ingesting()` に判定を一本化した。
  対照実験で新規テストの退行検知を確認（旧条件に戻すと失敗）。
- 15:00 JST: **仕組みの追加**: `.agents/skills/local-ci-parity/SKILL.md` を新設し `SKILLS_REGISTRY.md` に登録。
  本サイクルで判明した偽グリーンの原因（スキャナのエンコーディング依存、`.venv` の Python 版差、
  `verify.py` の予算と「最初の失敗で後続チェックが走らない」挙動、CRLF/LF）を手順として固定化し、
  以後のエージェントが同じ罠に落ちないようにする。
- 15:10 JST: push 後の hosted CI (`ec946b3`, run 43682050295) で **secret scan が 0 findings に回復**し、
  Python 全テスト・frontend lint/tests/build も green。CI が初めて E2E 段まで到達し、
  ローカルで見つけた `workspace.spec.ts:180` の失敗を**同一内容で再現**した（18 件中 17 passed）。
  → `T-PH4-104` は Linux/Windows 共通の実不具合と確定。
- 15:20 JST: **`T-PH4-104` 完了**。原因は `T-PH3-101` の再開可能インデックス化により `_index()` が
  `index_checkpoint+1` 頁から処理するようになった一方、e2e fixture が本文差し替え後に
  checkpoint を戻さず 1 頁目を再インデックスしていなかったこと（出典ダイアログの本文が短くなり
  スクロールが発生しない）。fixture の UPDATE に `index_checkpoint=0` を追加して解消。
  ローカル E2E 18/18 green。プロダクトコードとアサーションは未変更。
- 15:50 JST: **`T-PH4-101` 完了（Phase 4 残件の最後）**。ローカル LLM の逐次応答を SSE で実装。
  `POST /api/conversations/{id}/messages/stream` を追加し、断片は `send()` の既存の権限・添付・引用
  再確認をすべて通したあとにのみ流れる。回答の確定コミットは従来どおり `send()` の単一トランザクション。
  取消は既存の `DELETE /chat-jobs/{id}` をそのまま使い、断片間（0.25 秒間隔）で検知して中断し、
  部分回答は履歴に残さない。モデル未設定・セッション無し・スロット占有では SSE を開始せず 409 を返し、
  クライアントは従来の `POST /messages`（待機列 202 経路）へ自動フォールバックする。
  `stream` を無視するデーモンには 1 断片として自動劣化する。外部送信は追加なし。
  新規テスト: バックエンド 5 件・Vitest 2 件。合成 Ollama スタブを NDJSON 対応にし、
  生成回答の E2E が逐次経路を通るようにした（E2E 18/18 green）。
- 16:00 JST: Phase 4 の残件を `docs/plans/PHASE_STATUS.md` と突き合わせた結果、
  「measured representative concurrency/capacity」のみが未了。代表ワークロード（同時利用者数・
  資料の形式と量・実行機器・成功基準）が `docs/planning/research-app-concept.md` §5 で未決のため、
  推測で数値目標を作らず `T-PH4-105` を **`blocked`（owner 判断待ち）** として起票した。
- 残る人間判断待ち: (1) `T-PH4-105` の代表ワークロード決定、
  (2) 本サイクル実装分（特に `T-PH4-101` の SSE 経路）への別系統独立レビューの要否。
- 16:40 JST: **`T-PH4-105` 完了（owner 回答で blocked 解除）**。owner 想定は同時 10 件・常時 30〜40 アカウント・
  資料形式は「割と何でも」。`scripts/measure_capacity.py`（合成データとスタブモデルのみ）で実測:
  40 アカウント発行＋割当 1.12 秒 / 初回ログイン＋回転 中央値 0.074 秒 / 合成資料 60 件が ready まで 0.57 秒 /
  同時 10 人・応答 2 秒で 10 件すべて回答（待ち最大 22.1 秒、同一利用者の連続実行 0 回）。
  導かれる限界: モデルスロット 1 本の直列処理のため、同時 10 人を取りこぼさない条件は
  **1 応答 ≒ 30 秒以内**（`CHAT_WAIT_SECONDS=300` による）。10 人が各 2 件出すと全体上限 16 を超える。
  資料形式は現状 UTF-8 の txt/md/csv・256 KiB のみで、PDF/Office/バイナリは Phase 3 繰延（要 owner 承認）。
  → 2 件を owner 判断事項として `T-PH4-105` に記録。
- 16:55 JST: **独立レビュー（別モデル `claude-sonnet-5`・読取専用）を実施**（owner 指示）。対象は本サイクル全体
  `4d07db3..HEAD`。結果 **APPROVED（阻害なし）＋ 非阻害 2 件**。2 件とも即日修正:
  (1) Medium: SSE 開始後にスロットが取られた場合のレート上限二重計上 →
      クライアント再送をやめ、サーバ側で待機列へ投入して `event: queued` を返す方式に変更
      （計上 1 回を検証するテストを追加、`event: fallback` は廃止）。
  (2) Low: `T-PH4-102` / `T-PH4-103` の `allowed_paths` が実際の変更範囲と乖離 →
      frontmatter を実態に合わせ、改訂理由の表を各タスクに追記（監査可能性の回復）。
  レビュアーが自力検証できなかった点（テストの再実行・CI の再確認）は所見どおり記録に残す。
- 17:10 JST: **独立レビュー round 2（修正後の再レビュー、上限内）= APPROVED（追加要求なし）**。
  レビュアーが確認した点: サーバ側待機列投入が `enqueue_chat` の全チェック（会話所有・200 件上限・
  添付状態・1 会話 1 件・全体/利用者別キュー上限）をそのまま通ること、`_finish_chat` が取消要求を
  同一トランザクション内で判定するため「取消が勝つ」順序に競合がないこと、`generate_later` が
  `on_delta`/`events` から完全に分離されていること、新規 2 テストが空虚でなくレート上限の計上回数を
  直接測っていること、`allowed_paths` の追記が実差分と一致すること、`event: fallback` の残骸がないこと。
  非阻害の残置（新規ではない）: busy→待機列投入の際に元のストリーム job に `chat.failed` の監査行が
  残る（メタデータのみ・挙動に影響なし）。レビュアーはテストを自力実行していない（code tracing のみ）。
- 注意: `scripts/verify.py` の `python-tests` 予算は 120 秒で、Windows ローカルでは
  Python スイート（約 630 秒）が必ず `timeout` になる。ローカルではグループを直接実行して検証し、
  予算付き `verify.py` の判定は hosted CI を正本とする。

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
