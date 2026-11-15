# Phase 進捗サマリ: `phase-5-prototype`

- **対象 Phase**: プロトタイプ完成（`docs/plans/REQUIREMENTS_TRACEABILITY_MATRIX.md` の 92 要件 ID のうち、
  owner 承認を追加で要さずプロトタイプ範囲で閉じられる残件）。
- **対象ブランチ**: 統合ブランチ `loop/local-development`（ジョブは `loop/<TASK-ID>-<slug>` worktree）
- **最終更新日時**: `2026-11-15T17:30:00+09:00`
- **更新責任者**: `python -m jobloop`（決定論的コントローラ）と Claude Code。
  実装ワーカーは OpenCode の無料モデル、レビューは別の無料モデル（読取専用）。
- **起動根拠**: owner 指示 2026-11-15「ループ起動してジョブ単位で開発を進められる基盤を作成し、
  最終的なクリティカルな判断をユーザーに求める」「opencode の無料モデルをサブエージェントとして許可。
  usage が尽きたら自動で次のモデルへ」「まずはプロトタイプを完成させ、その後に仕様設計通りの拡張機能まで」。

---

## 1. Phase 完了条件（Gate Criteria）

- [ ] 本 Phase の全ジョブが `status: done`（試行上限 3・レビュー上限 2 以内）
- [ ] 統合ブランチ HEAD で GitHub Actions 3 ワークフローが green
- [ ] Phase 節目のフル検証（Python 全スイート・Vitest・Playwright・ruff/mypy/secret scan）が PASS
- [ ] `OWNER_DECISIONS.md` に未回答の判断要求が残っていないこと
- [ ] プロトタイプ範囲外（production TLS/MFA/実データ/外部コネクタ/ハイブリッド Runner）は
      繰延のまま。本 Phase で前倒ししない。

## 2. ジョブ一覧と現在状態

| Task ID | 要件 ID / 内容 | Weight | Status | Assignee | Model | Attempts | Updated |
|---|---|---|---|---|---|---|---|
| `T-PH5-101` | `DATA-014` 取り込み前インベントリと明示的な対象外理由 | `medium` | `todo` | `unassigned` | `-` | `0` | `2026-11-15T17:30:00+09:00` |
| `T-PH5-102` | `DATA-004` 検索・関連・出典・モデル文脈の各経路での現行 ACL 証明 | `medium` | `todo` | `unassigned` | `-` | `0` | `2026-11-15T17:30:00+09:00` |
| `T-PH5-103` | `UI-006` 能力を偽らない待ち時間・上限表示 | `light` | `todo` | `unassigned` | `-` | `0` | `2026-11-15T17:30:00+09:00` |

## 3. 本 Phase に入れない残件（根拠つき）

`REQUIREMENTS_TRACEABILITY_MATRIX.md` の gap state 集計（2026-11-15 時点）:
統合済み 41 / 完了条件充足 4 / 統合済み(prototype) 4 / 実装中 4 / 未着手 21 / Owner判断待ち 18。

本 Phase から除外する理由:

- `DATA-006` `DATA-007`（スキャナ・パーサのサンドボックス、対応形式、PDF/OCR）:
  owner 要望「資料は割と何でも対応したい」に直結するが、未知ファイルの解析はセキュリティ境界であり、
  承認済みの隔離設計が前提。`OWNER_DECISIONS.md` の判断要求として起票する。
- `DATA-013` `DATA-015`（本番ストア・保存期間）: owner 選定と運用検証が前提。
- `DATA-008`（保存先コネクタと元 ACL）: 研究ノートのみ提出済み、【要決定】が未解決。
- `HBR-001`〜`HBR-015`（ハイブリッド Runner）: 個別の承認 ADR とゲート通過が前提。
- `UI-007`（構造比較・プロット・分析）: 企画書 §4 では「後続の拡張」。拡張 Phase で扱う。
- `PROD-002/003`, `IAM-005/016/017`（本番配備・MFA・TLS・監査保護）: owner 判断待ち。

## 4. 進行管理

- ジョブ 1 件 = 実装（無料モデル）→ 決定論的ゲート（許可パス・保護パス・`test_cmd`・ruff・secret scan）
  → 別モデルの読取専用レビュー → Conventional Commit → 統合ブランチへ `--no-ff` マージ。
- 判断が必要になった時点でジョブは `blocked` になり、`OWNER_DECISIONS.md` に質問が追記される。
  他のジョブは止めない。
- 使用枠切れはモデルの失敗ではないため試行を消費せず、次の無料モデルへローテーションする。
- 運用手順は `docs/JOBLOOP.md`。
