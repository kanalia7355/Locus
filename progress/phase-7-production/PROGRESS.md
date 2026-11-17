# Phase 進捗サマリ: `phase-7-production`

- **対象 Phase**: 本番運用に必要な土台。オーナー決定 2026-11-16 テーマ 4・5 で方針が確定し、
  いままで**決まっているのに起票していなかった**領域を job にしたもの。
- **対象ブランチ**: 統合ブランチ `loop/local-development`（ジョブはリポジトリ外のローカルクローン）
- **最終更新日時**: `2026-11-17T15:30:00+09:00`
- **更新責任者**: `python -m jobloop`（決定論的コントローラ）と Claude Code。
- **起票経緯**: オーナー指示 2026-11-17「起票ガンガンしましょう」。
  下書きはサブエージェントが作成し、Claude Code が機械検査（`test_cmd` の形・保護パス・
  未確定スコープの整合・絵文字・本文中の絶対パス）と内容確認を通してから取り込んだ。

---

## 1. Phase 完了条件（Gate Criteria）

- [ ] 本 Phase の全ジョブが `status: done`
- [ ] 統合ブランチ HEAD で GitHub Actions 3 ワークフローが green
- [ ] Phase 節目のフル検証（Python 全スイート・Vitest・Playwright・ruff/mypy/secret scan）が PASS
- [ ] `OWNER_DECISIONS.md` に未回答の判断要求が残っていないこと
- [ ] **実データを入れないこと**。本 Phase は「本番に切り替えられる状態を作る」までで、
      実際の切り替え（証明書の調達・PostgreSQL への実データ移行・実アカウントの発行）は
      オーナーの運用判断であり、ここでは行わない。

## 2. ジョブ一覧

| Task ID | 要件 ID / 内容 | Weight | Status |
|---|---|---|---|
| `T-PH7-201` | `DATA-008` 保存先コネクタの共通インタフェースと巡回（合成コネクタのみ） | `heavy` | `todo` |
| `T-PH7-202` | `DATA-008` Windows 共有フォルダ（SMB）コネクタ | `heavy` | `todo` |
| `T-PH7-203` | `DATA-008` Google Drive コネクタ | `heavy` | `todo`（スコープ未確定） |
| `T-PH7-204` | `DATA-008` Box コネクタ | `heavy` | `todo`（スコープ未確定） |
| `T-PH7-211` | `DATA-013` ストレージ層の継ぎ目（挙動不変） | `heavy` | `todo` |
| `T-PH7-212` | `DATA-013` PostgreSQL engine と移行手順 | `heavy` | `todo` |
| `T-PH7-213` | `DATA-015` 保存期間 1 年・期限通知・管理者操作による削除 | `medium` | `todo` |
| `T-PH7-214` | `IAM-016` 監査記録の改ざん防止（追記のみ・連鎖ハッシュ・検知） | `medium` | `todo` |
| `T-PH7-221` | `IAM-005` 代替: パスワード最低強度と失敗時の一時ロック | `medium` | `todo` |
| `T-PH7-222` | `IAM-005` 代替: ログイン履歴の管理者可視化 | `medium` | `todo` |
| `T-PH7-223` | `PROD-002` `PROD-003` `IAM-017` 本番起動要件（TLS と私設インタフェース） | `medium` | `todo` |
| `T-PH7-224` | `PROD-003` 配備手順と運用確認（設定が文書どおりかを検査する） | `medium` | `todo` |

## 3. 着手順と依存

1. `T-PH7-211`（継ぎ目）→ `T-PH7-212`（PostgreSQL）。継ぎ目が無いまま engine を足すと
   `service.py` の SQL 発行箇所すべてに分岐が散る。
2. `T-PH7-201`（共通インタフェース）→ `T-PH7-202`（SMB）。`203` `204` は資格情報と
   変更通知 API の扱いが未設計なのでスコープ未確定のまま。
3. `T-PH7-221` `T-PH7-222` `T-PH7-223` は互いに独立。先に流してよい。
4. `T-PH7-213` `T-PH7-214` は継ぎ目の有無に関わらず SQLite 上で実装できる。

## 4. 着手前に Claude Code が済ませること

- **`psycopg` の依存追加**（`pyproject.toml` の `[project.optional-dependencies]`、版は固定）。
  `pyproject.toml` は保護パスであり、依存の追加は出自の判断（`GOV-006`）を伴うので
  ジョブにはしない。`T-PH7-212` はドライバが宣言済みである前提で実装する。

## 5. 本 Phase に入れない残件（根拠つき）

- 実データでの本番配備そのもの（証明書の調達、PostgreSQL への実移行、実アカウント発行）:
  実装と手順の用意までが本 Phase。切り替えの実行はオーナーの運用判断。
- `HBR-*`（ハイブリッド Runner 15 件）: `phase-8-runner` で扱う。
- 組織全体の管理画面: オーナー回答「他機能の配線が終わってから」。
