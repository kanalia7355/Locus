# Owner確認・承認チェックリスト — 2026-11-11 時点

**Status:** この文書は v0.4.0 に統合された設計成果物と、オーナー判断項目の確認・承認用チェックリストです。各項目の詳細はリンク先の完全版を参照してください。

**2026-11-11 更新:** 以下の Entry 1〜6 は **2026-11-10 にオーナーにより正式決定済み**（[OWNER_DECISIONS_2026-11-10-ENTRIES.md](OWNER_DECISIONS_2026-11-10-ENTRIES.md)、Q1〜Q7 の補完、`OWNER_DECISION_REQUIRED` を全件解消）。§1 は決定値の記録に更新済み。Entry 1〜6 が直接決定しなかった項目は §1-bis のとおり **【要決定】／別途承認** のまま維持される。

---

## 1. Entry 1〜6 — **全件 RESOLVED（2026-11-10 記録）**

元の質問・選択肢・推奨の詳細（8フィールド形式）は [OWNER_QUEUE_CLASSIFICATION_2026-11-09.md](OWNER_QUEUE_CLASSIFICATION_2026-11-09.md) §OWNER_DECISION_REQUIRED 参照。以下は決定値の確定記録。

### Entry 1 — Receipt TTL（既定値・上限値） — **RESOLVED: 選択肢(a)を承認する**
- **対象:** DP-010, DP-011
- **決定値:** 既定TTL **24時間** ／ 最大TTL **7日間**。失効は Control Plane を権威とする絶対 epoch-seconds。**猶予期間なし**。期限切れ Receipt の再利用禁止。
- **自動再発行:** 事前承認範囲内ジョブは現在の権限・ポリシー再検証後に新しい Receipt を自動発行できる（延長ではなく新しい認可判断）。権限失効・ポリシー変更・承認範囲外操作では自動発行禁止。
- **分離:** Receipt TTL と委任権限 TTL（PH2-A-01: 24h/7d/15min）は別概念として管理。
- **OWNER DECISION:** ✅ **RESOLVED** — [Entry 1](OWNER_DECISIONS_2026-11-10-ENTRIES.md#entry-1--receipt-ttl--選択肢aを承認する)

### Entry 2 — 承認用の新規権限の要否 — **RESOLVED: 選択肢(a)を承認する（新規権限なし）**
- **対象:** DP-021
- **決定値:** `approve_jobs` 等の専用権限は**追加しない**。承認権限は既存の Owner／Grantor／管理者ロールおよび権限モデルから導出。
- **個人Workspace:** Q2 で承認された範囲内で本人による自己承認を認める。**組織・共有Workspace:** 既存の管理者統制と承認者の権限上限を維持。
- **制約:** 上位ポリシー・明示的拒否・membership条件・委任制限を回避してはならない。承認主体と実行主体の分離が必要なケースでは既存の安全要件を維持。
- **OWNER DECISION:** ✅ **RESOLVED** — [Entry 2](OWNER_DECISIONS_2026-11-10-ENTRIES.md#entry-2--ジョブ承認専用権限--選択肢aを承認する)

### Entry 3 — Runner通信トポロジと境界越えエンドポイント — **RESOLVED: 選択肢(a)を承認する（設計承認）**
- **対象:** DP-031, DP-032
- **決定値:** 認証済みLAN内部チャネル（認証・認可・暗号化）を基本方式として**設計承認**。エンドポイント・ポート・プロトコル・方向・境界は明示し、個別に設計・検証・独立レビュー・**別途 Owner 承認**を要する。許可以外への通信は拒否、インターネット/外部クラウド/未承認LAN/プロバイダーAPIへの暗黙許可なし。検証できない経路は fail-closed。
- **範囲:** ファイアウォール変更・ポート開放・Runner通信開始の実行承認ではない。リモート Runner／外部ネットワークは初期設計の最終要件から削除せず別途設計。
- **OWNER DECISION:** ✅ **RESOLVED** — [Entry 3](OWNER_DECISIONS_2026-11-10-ENTRIES.md#entry-3--runner通信トポロジ--選択肢aを承認する)

### Entry 4 — プロバイダー認証情報の供給 — **RESOLVED: 選択肢(a)を承認する（設計・検証のみ。実供給は未承認）**
- **対象:** DP-034b
- **決定値:** **現段階で Runner への実認証情報供給は許可しない。** Codex CLI・Claude Code 等の公式にサポートされた認証・実行方式を優先。Adapter ごとに認証方式・利用条件・隔離環境での動作・資格情報の保護方法を検証。broker-mediated 方式は設計・比較し、採用時は検証証跡・独立レビュー・個別 Owner 承認が必要。
- **不変制約:** 資格情報をジョブ入力・Receipt・監査ログ・モデルコンテキストへ混入させない。安全な供給を実証できない Adapter は当該環境で拒否。非公式な認証回避・サブスクリプション制限迂回は禁止。
- **範囲:** 設計・検証を認めるものであり、実アカウントのログイン・認証情報の読み出し・転送・供給の承認ではない。
- **OWNER DECISION:** ✅ **RESOLVED** — [Entry 4](OWNER_DECISIONS_2026-11-10-ENTRIES.md#entry-4--aiプロバイダー認証情報の供給--選択肢aを承認する)

### Entry 5 — Runnerの信頼・登録・鍵管理方式（クラスタ） — **RESOLVED: 推奨構成を承認する（設計方針承認）**
- **対象:** DP-035, DP-036, DP-037, DP-038, DP-039, DP-040, DP-041, DP-043b（8項目）
- **決定値:** OS keystore 保護のインスタンス別 Runner 識別情報／検証済み標準 TLS／認証済み管理者による一回限りチャレンジ登録／インスタンスと登録済み ID の厳密な束縛／失効可能な Runner ID／実測・検証結果に基づく鍵ローテーション／鍵喪失・侵害時の revoke-then-re-enroll／登録・更新・失効・復旧操作の監査。
- **必須としない:** 独自 CA、専用ハードウェア認証、複数管理者クォーラム（必要性が実証されない限り）。
- **検証条件:** OS keystore 利用可能性検証、鍵・認証情報の保護実証、Runner 登録/失効権限の既存 RBAC 対応付け、鍵更新/失効/復旧時の権限拡大なし検証、侵害時のジョブ停止/結果保留/再登録手順定義、暗号方式/鍵寿命/ローテーション周期の標準方式+検証結果に基づく確定、独立レビュー。
- **範囲:** 信頼基盤の**設計方針の承認**であり、実鍵の発行・Runner 登録・通信接続・実行活性化の承認ではない。
- **OWNER DECISION:** ✅ **RESOLVED** — [Entry 5](OWNER_DECISIONS_2026-11-10-ENTRIES.md#entry-5--runner信頼登録鍵管理--推奨構成を承認する)

### Entry 6 — 組織モデルと残余の管理UI/受領側UI — **RESOLVED: 選択肢(c)を承認する（受領側UIのみ）**
- **対象:** DP-071
- **決定値:** **委任を受ける側の UI 改善を優先**。現在のプロジェクトスコープの委任・権限モデルを維持。UI 設計は委任の有効期限・付与元・権限範囲・失効状態・自己失効操作を利用者が理解できるものとし、UI 非表示だけに依存せずバックエンドで権限検証。
- **組織拡張:** 組織レベルの委任拡張は**現時点では実装しない**（初期設計の最終要件からは削除しない。後続 Phase で要件・依存関係・受入条件を明示）。
- **OWNER DECISION:** ✅ **RESOLVED** — [Entry 6](OWNER_DECISIONS_2026-11-10-ENTRIES.md#entry-6--組織管理ui受領側ui--選択肢cを承認する)

## 1-bis. 残存する genuinely-open 項目 — **【要決定】／別途承認のまま**

Entry 1〜6（および Q1〜Q7）が直接決定しなかった項目。承認済みとみなしてはならない（[Q1〜Q7 §4](OWNER_DECISIONS_2026-11-09-EVENING.md)、[Owner §2](OWNER_DECISIONS_2026-11-10-ENTRIES.md)）:

| 項目 | 状態 |
|---|---|
| Runner↔CP の具体的エンドポイント・ポート・プロトコルの個別承認（Entry 3 は設計承認のみ） | 【要決定】／別途承認 |
| 実認証情報の供給・プロバイダー認証の活性化（Entry 4 は設計・検証のみ） | 【要決定】／別途承認 |
| 実鍵の発行・Runner 登録・通信接続・実行活性化（Entry 5 は設計方針承認のみ） | 【要決定】／別途承認 |
| 未検証の隔離プロファイルの個別承認（Q3 の方針は決定済み、プロファイル個別は未承認） | 【要決定】 |
| B6 dispatch 解除、Runner 実ジョブ実行 | 【要決定】／別途承認 |
| 未承認の外部通信・egress、実データの使用、本番公開 | 【要決定】 |
| 本番 retention/audit（D-1〜D-3 ゲート）、Clock skew tolerance、Receipt 保持期間（DP-022/Q7トラック）等の技術値 | Q7トラック／ENGINEERING_DETAIL |

---

## 2. 決定の記録

Entry 1〜6 は 2026-11-10 に [OWNER_DECISIONS_2026-11-10-ENTRIES.md](OWNER_DECISIONS_2026-11-10-ENTRIES.md) として正式記録済み（Q1〜Q7 の補完）。トレーサビリティ（Entry → DP → 決定値 → 実装成果物）は [OWNER_DECISION_REGISTER.md](OWNER_DECISION_REGISTER.md) §Entry 1–6 参照。以下の記入例は歴史的参考として保持:

**全推奨案を承認する場合:**
> Entry 1〜6すべて推奨案を承認する。

**個別に承認する場合:**
> Entry 1は(a)で承認、Entry 3は(c)で維持、Entry 5は推奨案で承認、Entry 6は後回し。

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

## 4. 承認後のパイプライン（2026-11-10 決定後の実績）

Entry 1〜6 の決定により、以下の作業が承認済み範囲で開始・実施されました（実行・通信・資格情報・実データ・本番の活性化は引き続き別途承認）:

| Entry承認 | 解放される作業 | 現状（2026-11-11） |
|---|---|---|
| Entry 1 (Receipt TTL) | 2b受信契約の数値確定 → テスト+エンベロープ新鮮度配線 | 実装中（slot Q、[P1-RECEIPT](agent-work/P1-RECEIPT.md)） |
| Entry 2 (新規権限) | 2b承認フロー認証参照の確定 | 実装中（同上、Entry 1 と同一パッケージ） |
| Entry 3 (Runner通信) | ステップ3通信設計+ファイアウォール検証計画+信頼ルート検証テスト範囲 | 設計納品済み（[HYBRID_RUNNER_COMMUNICATION_DESIGN.md](HYBRID_RUNNER_COMMUNICATION_DESIGN.md)、slot P3） |
| Entry 4 (資格情報供給) | アダプタ毎の資格情報供給設計+broker証拠テスト+活性化判断 | 設計納品済み（[HYBRID_AGENT_ADAPTER_DESIGN.md](HYBRID_AGENT_ADAPTER_DESIGN.md)、slot P4） |
| Entry 5 (Runner信頼/登録/鍵管理) | Runner識別/登録/ローテーション設計確定+ステップ3信頼実装 | 設計納品済み（[HYBRID_RUNNER_TRUST_DESIGN.md](HYBRID_RUNNER_TRUST_DESIGN.md)、slot P2） |
| Entry 6 (組織モデル) | 受領側委譲UIの精緻化 | UIリサーチ納品済み（[UI_OPENCODE_RESEARCH.md](UI_OPENCODE_RESEARCH.md)、slot V）／実装進行中（slot W） |

**維持される安全境界:** B6 dispatch拒否ゲート、ADR-0011ゼロツール境界、ADR-0012デュアルプレーン分離、no-egress、fail-closed — 承認された判断によっても変更されません（活性化は別途個別承認が必要）。
