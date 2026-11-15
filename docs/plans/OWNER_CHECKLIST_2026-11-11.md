# Owner確認・承認チェックリスト — 2026-11-11 時点

**Status:** この文書は v0.4.0 に統合された設計成果物と、残るオーナー判断が必要な6項目をまとめた確認・承認用チェックリストです。各項目の詳細はリンク先の完全版を参照してください。

---

## 1. 残件一覧（OWNER_DECISION_REQUIRED — 全6件）

Q1〜Q7 + 既存ADRで解決された項目を除く、** genuinely open** なオーナー判断のみ。詳細（8フィールド形式）は [OWNER_QUEUE_CLASSIFICATION_2026-11-09.md](OWNER_QUEUE_CLASSIFICATION_2026-11-09.md) §OWNER_DECISION_REQUIRED 参照。

### Entry 1 — Receipt TTL（既定値・上限値）
- **対象:** DP-010, DP-011
- **質問:** ジョブレシートの既定TTLと最大TTLは？
- **選択肢:** (a) 委譲前例に合わせる（既定24h/最大7日 — 提案値、未承認） / (b) 実行ウィンドウ連動の短め設定 / (c) オーナー指定値
- **推奨:** (a) + 絶対epoch-seconds失効 + 猶予なし + 範囲内ジョブ自動再発行
- **後回し可否:** 2b実装前に必要。設計作業は継続可。
- **OWNER DECISION:** ☐ ______________________

### Entry 2 — 承認用の新規権限の要否
- **対象:** DP-021
- **質問:** `approve_jobs` 等の新規権限を追加するか、既存ロールから導出するか？
- **選択肢:** (a) 新規権限なし（既存grantor/ownerロールから導出） / (b) 専用権限+上限を追加 / (c) その他
- **推奨:** (a) — 特権拡散を避け、単一権限モデルを維持
- **後回し可否:** 2b実装前に必要。
- **OWNER DECISION:** ☐ ______________________

### Entry 3 — Runner通信トポロジと境界越えエンドポイント
- **対象:** DP-031, DP-032
- **質問:** Runner↔Control-Plane通信の許可範囲は？
- **選択肢:** (a) 認証済みLAN内部チャネルのみ+個別エンドポイント承認 / (b) 全エンドポイント個別列挙 / (c) 現状維持（デフォルト拒否）
- **推奨:** (a) — 正確なエンドポイントを提案・検証・独立レビュー後個別承認、デフォルト拒否維持
- **後回し可否:** Runner通信活性化前に必要。設計・デスク検証は継続可。
- **OWNER DECISION:** ☐ ______________________

### Entry 4 — プロバイダー認証情報の供給
- **対象:** DP-034b
- **質問:** Runnerジョブ内の外部AI認証情報をどう供給するか？
- **選択肢:** (a) broker-mediated供給（証拠+個別承認後） / (b) 供給なし（資格情報を隔離できないアダプタは当該プラットフォームで利用不可）
- **推奨:** Q4のもと、アダプタ毎に検証→broker供給は証拠+個別承認後。現時点では供給なし。
- **後回し可否:** 資格情報活性化前に必要。
- **OWNER DECISION:** ☐ ______________________

### Entry 5 — Runnerの信頼・登録・鍵管理方式（クラスタ）
- **対象:** DP-035, DP-036, DP-037, DP-038, DP-039, DP-040, DP-041, DP-043b（8項目）
- **質問:** Runnerのトラストアンカー、暗号プロファイル、PKI、keystore、登録/失効権限、鍵寿命/ローテーション、再登録/復旧規則は？
- **推奨:** OS keystore保護の最小per-instance識別 + vetted TLS + 認証済み管理者one-useチャレンジ結合 + 測定ローテーション + 喪失/侵害時revoke-then-re-enroll + カスタムCA/ハードウェア/クォーラムなし
- **後回し可否:** Runner登録/活性化前に必要。
- **OWNER DECISION:** ☐ ______________________

### Entry 6 — 組織モデルと残余の管理UI/受領側UI
- **対象:** DP-071
- **質問:** 組織レベル管理UIの要否と受領側UIの精緻化範囲は？
- **選択肢:** (a) 組織レベルUIなし（プロジェクトスコープのみ） / (b) 組織モデルを先に定義→UI設計 / (c) 受領側UI精緻化のみ
- **推奨:** (c) 先に実施。(b)は要件が実際に必要になった時点で別途設計提案
- **後回し可否:** **後回し可**。(b)は後回し可。
- **OWNER DECISION:** ☐ ______________________

---

## 2. 一括承認の書き方

**全推奨案を承認する場合:**
> Entry 1〜6すべて推奨案を承認する。

**個別に承認する場合:**
> Entry 1は(a)で承認、Entry 3は(c)で維持、Entry 5は推奨案で承認、Entry 6は後回し。

**後回しを指定する場合:**
> Entry 1, 2, 5のみ今判断。Entry 3, 4, 6は後回し。

---

## 3. 補足資料リンク（v0.4.0 @ main）

### 判断基盤資料

| 資料 | 内容 | 行数 |
|---|---|---|
| [OWNER_DECISION_PROPOSAL_2026-11-09.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/OWNER_DECISION_PROPOSAL_2026-11-09.md) | DP-001〜072 統合提案書（エグゼクティブサマリ+一貫性チェック+残るOwner決定点） | 301 |
| [OWNER_DECISIONS_2026-11-09-EVENING.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md) | Q1〜Q7 正式記録 | 85 |
| [OWNER_DECISION_QUEUE_2026-11-09.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/OWNER_DECISION_QUEUE_2026-11-09.md) | 72項目キュー（OWNER DECISION欄はQ1〜Q7参照で埋め済み） | 115 |
| [OWNER_QUEUE_CLASSIFICATION_2026-11-09.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/OWNER_QUEUE_CLASSIFICATION_2026-11-09.md) | 5区分再分類（81行：72+9分割） | 230 |

### 実行計画資料

| 資料 | 内容 | 行数 |
|---|---|---|
| [RESUMABLE_JOBS_2026-11-09.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/RESUMABLE_JOBS_2026-11-09.md) | 承認済み範囲で開始可能なジョブ一覧 | 74 |
| [DEFERRED_WITH_GATES_2026-11-09.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/DEFERRED_WITH_GATES_2026-11-09.md) | 後続Phase延期項目+着手条件・受入ゲート | 66 |
| [MASTER_IMPLEMENTATION_ROADMAP.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md) | マスターロードマップ（Q1-Q7反映済み更新セクション含む） | 132+ |

### 設計ドキュメント（v0.4.0に統合済み）

| 資料 | 内容 | 行数 |
|---|---|---|
| [HYBRID_STEP2_RECEIPT_CONTRACT.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/HYBRID_STEP2_RECEIPT_CONTRACT.md) | 受信契約+2b設計 | 633 |
| [HYBRID_ISOLATION_PROFILES.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/HYBRID_ISOLATION_PROFILES.md) | 隔離プロファイル設計 | 133 |
| [HYBRID_ISOLATION_ENGINEERING_DETAIL.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/HYBRID_ISOLATION_ENGINEERING_DETAIL.md) | 隔離ENGINEERING_DETAIL | 238 |
| [HYBRID_ENGINEERING_DETAIL_INVENTORY.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/HYBRID_ENGINEERING_DETAIL_INVENTORY.md) | ENGINEERING_DETAIL棚卸し | 409 |

### 再評価原典（推奨レイヤー）

| 資料 | 対象DP | 行数 |
|---|---|---|
| [OWNER_REEVAL-A-RECEIPT.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/OWNER_REEVAL-A-RECEIPT.md) | DP-001…023 receipt/2b | 767 |
| [OWNER_REEVAL-B-ISOLATION.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/OWNER_REEVAL-B-ISOLATION.md) | DP-024…053 isolation/trust | 358 |
| [OWNER_REEVAL-C-STORAGE-MISC.md](https://github.com/kanalia7355/Locus/blob/main/docs/plans/OWNER_REEVAL-C-STORAGE-MISC.md) | DP-054…072 storage+misc | 248 |

### コード実装（v0.4.0に含まれる）

| ファイル | 変更内容 |
|---|---|
| `backend/app/scanner.py` | タイプ付きスキャナー結果（clean/rejected/unavailable分離） |
| `backend/app/service.py` | ステータス処理（fail-closed維持） |
| `frontend/src/AdminSettings.tsx` | 有効/検査不能/拒否 UI表示 |

---

## 4. 承認後のパイプライン

オーナー判断が記録されると、以下の実装が承認済み範囲で開始可能になります:

| Entry承認 | 解放される作業 |
|---|---|
| Entry 1 (Receipt TTL) | 2b受信契約の数値確定 → テスト+エンベロープ新鮮度配線 |
| Entry 2 (新規権限) | 2b承認フロー認証参照の確定 |
| Entry 3 (Runner通信) | ステップ3通信設計+ファイアウォール検証計画+信頼ルート検証テスト範囲 |
| Entry 4 (資格情報供給) | アダプタ毎の資格情報供給設計+broker証拠テスト+活性化判断 |
| Entry 5 (Runner信頼/登録/鍵管理) | Runner識別/登録/ローテーション設計確定+ステップ3信頼実装 |
| Entry 6 (組織モデル) | 受領側委譲UIの精緻化 |

**維持される安全境界:** B6 dispatch拒否ゲート、ADR-0011ゼロツール境界、ADR-0012デュアルプレーン分離、no-egress、fail-closed — 承認された判断によっても変更されません（活性化は別途個別承認が必要）。
