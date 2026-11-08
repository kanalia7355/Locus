# 現状報告・判断要求・仕様設計まとめ (2026-11-09)

この文書は、(1) 進行状態、(2) オーナー判断を仰いでいる事項、(3) 詳細な仕様設計を
一箇所にまとめたものである。判断が必要な項目には [決定要求] を付す。ここでの
「推奨」は実装側の提案であり、承認されない限り何も確定しない。

---

## 1. 進行状態

### 1.1 完了済み（main反映含む）

| 项 | 内容 | 証跡 |
|---|---|---|
| Phase 0 | ブートストラップ・ガバナンス・検証基盤 | `.bootstrap/complete.json` |
| **Phase 1 認証**（完了・mainマージ済み） | 回復フロー／アカウント停止切替／Web利用者追加／レース修正 | main `75d4e0a`（squash）, バージョン 0.2.0, 集約独立レビュー accept, 正確HEADでCI全緑 |
| ハイブリッド step 1 | 脅威モデル（独立レビュー済み・fix適用済み） | `docs/security/HYBRID_AGENT_THREAT_MODEL.md` |
| ハイブリッド step 2 設計 | Agent Registry／Adapter／Workspace Policy 設計書（3レビューサイクル完了） | `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` |
| ADR-0012 | デュアルプレーン境界（**owner承認済み**、活性化は未承認のまま分離） | `docs/architecture/decisions/0012-...md` |
| **スライス2a**（新・統合済み） | メタデータのみのAgent Registry＋versioned不変ポリシー＋dispatch拒否ゲート | 統合 `282e864`, 統合後回帰 1136 passed/9 skipped |
| PH1-P4A | 実行中質問の協調キャンセル（優先度1） | 統合 `5a7848c`, CI全緑, pytest 1117 passed |
| PH2-A | 委任仕様書（ドラフト・要決定12項目） | 統合 `99bb041`, `docs/plans/PHASE2_DELEGATION_SPEC.md` |

### 1.2 実行中

| ジョブ | 内容 | 状態 |
|---|---|---|
| PH2-B | 兼任（複数役職union）＋明示deny権限の実装 | 実装・QA完了、ブランチCI最終確認中（3/4ジョブ緑、windows-3.11実行中） |
| PH2-2AR | スライス2aの独立レビュー | **完了: accept after minor fixes**（MEDIUM 1件→修正ジョブへ） |

### 1.3 待ち・発注予定

| ジョブ | 内容 | ブロッカー |
|---|---|---|
| スライス2a修正 | 監査とレート制限の順序整理（下記2.1） | なし（次の空きスロットで発注） |
| PH1-P4B再起動 | 管理project・保存先設定＋負荷表示 | なし（draft保存済み、再開指示済み） |
| PH2-C | 元保存先ACL対応の調査・設計 | なし |
| PH2-D | 期限付き委任の実装 | **[決定要求] 下記2.2の回答** |
| 比較表・削除操作 | Phase 4残件（優先度4・5） | P4A/P4B統合後（App.tsx競合回避） |

### 1.4 環境上の注意

- 共有 `.venv` がPython 3.10.6/依存欠落に置き換わっている（出所不明）。隔離QA環境
  `.loop/runtime/qa-venv`（Python 3.13＋固定依存）で全検証を実施中。復元のご指示があれば対応する。
- DeepAIレーンに日次429が発生したことがある（2026-11-08）。スロット投入は段階的に行う。

---

## 2. [決定要求] オーナー判断一覧

### 2.1 （判断不要・報告）スライス2aレビューの軽微修正
独立レビューのverdictは accept after minor fixes。MEDIUM 1件:
`backend/app/agents/registry.py` で未認証/非admin要求がレート制限**前に**監査され、
監査テーブルを成長させ得る。また不正なリクエストボディが認証前に422となる経路がある。
**対応方針**: レート制限→認証→監査の順序に整理し、認証前422の経路を認証後に統一。
既存テストの削除・緩和はしない。 owner判断は不要（既存境界の強化）。次スロットで実施。

### 2.2 [決定要求] PH2-A 委任仕様の要決定12項目（PH2-D実装の前提）

`docs/plans/PHASE2_DELEGATION_SPEC.md` §8 より。各項目に選択肢と推奨を示す。

| # | 項目 | 選択肢 | 推奨 |
|---|---|---|---|
| 1 | 既定/最大/最小TTL | (a) 既定24h・最大7日・最短15分 (b) 既定1h・最大24h (c) 固定値のみ | **(a)** 仮パスワードの24h運用と整合 |
| 2 | 再委任（delegate→第三者） | (a) 不許可 (b) 許可・深さ1 (c) 許可・連鎖 | **(a)** 連鎖監査の複雑さを避ける |
| 3 | 付与・取消の権限者 | (a) project owner＋org admin (b) system_adminのみ (c) grant権限自体を委任可能に | **(a)** grant権限の委任は不可 |
| 4 | org全体付与の可否 | (a) 当面project scopedのみ (b) org grantも実装 | **(a)** org移行時の連鎖失効は後続判断 |
| 5 | 付与者の権限喪失時の挙動 | (a) live無効化・fail closed (b) 存続（付与時点で確定） | **(a)** セキュリティ既定に整合 |
| 6 | 受領者による取消 | (a) 許可（自己取消・冪等・監査） (b) 付与者のみ | **(a)** |
| 7 | 再付与の同一性 | (a) 同family新version・scope変更は新family・重複dedupe (b) 常に新family | **(a)** 監査の追跡性 |
| 8 | 時刻基準とclock skew | (a) SQLiteのepoch秒継続・本番DB選定時に再決定 (b) 今すぐUTC固定仕様 | **(a)** 既存方針継続 |
| 9 | 管理権限（manage_roles等）の委任可否 | (a) 不許可（NON_ADMIN ceiling維持） (b) 一部許可 | **(a)** 既存のrole editor制約と整合 |
| 10 | membershipなしでの資料アクセス付与 | (a) 不許可（membershipは独立ゲート） (b) 許可（grantがmembershipを兼ねる） | **(a)** |
| 11 | 失効/取消grantの保持 | (a) 監査保持・実grant即時無効・保持期間は本番配備Phaseで決定 (b) 即時削除 | **(a)** 監査連鎖の保全 |
| 12 | 取消と要求の競合の応答意味論 | (a) 次認可ポイントで確実に拒否（応答はベストエフォート） (b) 同期的中断保証 | **(a)** 既存の「次認可チェックで反映」方針と同一 |

**回答形式**: 「1,3,5,9,10 は推奨どおり。2 は (b)」のように番号指定で可。
全項目推奨どおりなら「全て推奨案で確定」で足りる。回答後、PH2-D（委任実装）を
ジョブとして起動する。

### 2.3 [決定要求] その他の未決事項（現時点で着手可能なものはなし）

| 項目 | 状態 | 再提示タイミング |
|---|---|---|
| 隔離技術（OS/コンテナ） | 未決定 | 実装順3（Runner実装）着手前 |
| Runner信頼ルート・enrollment | 未決定 | 実装順3着手前 |
| 監査ログの改竄耐性・保持 | 未決定（活性化ブロッカー） | Runtime活性化前 |
| 同時実行・期限・取消の数値 | 未決定 | スライス2b/3設計検証後 |
| health checkによる認証probe | 不許可（安全性検証後に再判断） | アダプター活性化前 |
| 実データ利用 | 不承認（合成データ限定を継続） | 常時保留 |
| LAN外Runner到達 | 不承認 | 常時保留 |
| cloud egress有効化 | 不承認（allowlistedは非稼働プレースホルダー） | owner承認＋境界検証後 |

---

## 3. 詳細な仕様設計（確定済み・実装中の設計の要点）

### 3.1 ADR-0012: デュアルプレーン境界（承認済み）

- **Plane M**（既存のモデル要求経路）: C-minゼロツール境界で完全凍結。厳密な
  要求/応答強制は `loop_engine/audit_transport.py`＋`loop_engine/model_gate.py`
  （`c_min_runtime.py`が接続）。`toolless_boundary.py`は起動設定・診断probeのみ。
- **Plane R**（Agent Runtime）: ツール実行を担う別モジュールツリー。
  境界規則 B1–B7（import分離・fail-closed `UnprovenBoundary`実行ガード・能力宣言の
  「stripではなくreject」・レジストリ中立性など）。静的import検査で全方向を検証。
- **承認≠活性化**: スライス2a（メタデータ）のみ実装許可。dispatch可能コードには
  別途「ジョブ承認ADR」が必須。B6が有効な間、Control Planeは全dispatch要求を
  明示的に拒否・監査する（Runner不在への依存ではなく拒否自体をテスト）。

### 3.2 スライス2a: Agent Registry / Workspace Policy（統合済み・レビュー修正中）

- **テーブル群**（メタデータのみ・秘密情報は保持しない）:
  `workspace_policies`（不変・versioned。編集は新version生成、既存bindingは旧version参照）、
  `workspaces`, `runner_instances`, `agent_adapters`, `adapter_capabilities`,
  `workspace_adapter_bindings`, インスタンススコープの `adapter_health`・
  `adapter_credentials`（presence-only。secret様カラムの存在を検出する静的チェック付き）
- **Admin API**: create/list/disable。system_admin上限・トランザクション内
  metadata-only監査・レート制限。能力宣言は未知フィールドを422+監査で拒否。
- **dispatchゲート**: B6有効中は全dispatch/enqueue要求をenqueue前に明示拒否＋監査。
- **明示的に含まないもの**: 実行・隔離・egress・receipt解決・`allowlisted`の有効化
  （既定denyの非稼働プレースホルダーとしてのみ存在）。

### 3.3 委任仕様（PH2-A ドラフト: 要決定回答後に確定）

- **付与モデル**: 付与者（actor）・スコープ（project。orgは要決定#4）・権限subset・
  期限を持つ不変・versionedなgrant行。全変更はトランザクション内metadata-only監査。
- **期限**: 全認可ポイントでlive再検証（キャッシュ不可）。期限切れは即時拒否。
  TTL値は要決定#1。
- **取消**: Phase 1の「無効化→session完全失効」パターンを踏襲。実行中操作は
  次認可ポイントで拒否（要決定#12）。
- **自己昇格拒否**: 付与者自身の実効上限がハードキャップ。subsetのみ付与可能。
  管理権限は委任不可（要決定#9）。
- **兼任/明示denyとの整合**（PH2-B実装中）: union権限の中で委任はsubsetをさらに
  狭めるのみ。denyは委任によっても解除されない。
- **回帰計画**: 「異なる利用者/組織/権限変更中の全データ経路」「委任subset/scope/
  expiry」「自己昇格拒否」を網羅する否定系テスト一式。

### 3.4 兼任・明示deny（PH2-B: 実装・CI確認中）

- **兼任**: 同一project内で複数roleを保有。実効権限は保有roleのunion。
  各roleは既存のsubset制限・非管理上限を逸脱しない。組み合わせによる昇格経路なし。
- **明示deny**: 同一スコープ内でallowに優先。既定はdeny-by-defaultのまま。
  denyは他roleや委任によってcross-scopeで解除されない。優先規則をコードコメントで文書化。
- 監査は従来どおりトランザクション内metadata-only。

### 3.5 Phase 4残件の設計メモ（承認済み優先順）

1. **実行中質問の取消**（統合済み）: 協調キャンセルフラグ。実行中の単一有界HTTP呼び出し
   は中断しない。完了時にterminal cancelledへ遷移し、回答は保存・表示されない。
   cancel/完了の競合は単一のterminal状態に決着。冪等・owner限定・監査。
2. **管理project・保存先・負荷表示**（P4B実装中）: 既存backend状態のread-only表示と
   既存設定の明示ガード付き管理。外部保存先・egressは常に既定denyのプレースホルダー。
3. **比較表の構造化表示**（未着手）。
4. **削除操作**（未着手・要確認/認可/監査/誤操作対策を必須）。

---

## 4. 次のアクション（owner判断の有無によらず実行）

1. スライス2aの軽微修正（2.1）を空きスロットで実施 → 再レビュー（最大2サイクル規則内）
2. PH2-B統合（CI緑確認後）
3. PH1-P4B再起動・PH2-C発注
4. 2.2の回答受領後: PH2-D（委任実装）を起動
5. Phase 2完了条件の充足を確認し、独立レビュー→CI全緑→main自動マージ→バージョン更新
