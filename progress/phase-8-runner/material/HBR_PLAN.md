# HBR-001〜015（ハイブリッド Runner）着手計画

- 作成: 2026-11-17。対象: `docs/plans/REQUIREMENTS_TRACEABILITY_MATRIX.md` の `HBR-001`〜`HBR-015`
  （同ファイル 58〜72 行目、および 157〜171 行目のギャップ注記）。
- 前提の決定: `docs/plans/OWNER_DECISIONS_2026-11-10-ENTRIES.md`（Entry 1〜6、2026-11-10 正式決定）、
  `progress/phase-6-extensions/OWNER_DECISIONS.md` テーマ 1（E1〜E5、2026-11-16 回答）。
- 本文書は設計を**作らない**。既にある設計を指し、無いものを名指しし、ジョブに割る。

---

## 0. 結論（先に）

1. **設計の不足はこのブロックの主な障害ではない。** 15 要件のうち 9 件
   （`HBR-004` `HBR-005` `HBR-006`(一部) `HBR-007` `HBR-010` `HBR-011` `HBR-012` `HBR-013` `HBR-014`(一部)）は、
   既存の `docs/plans/HYBRID_*.md` に実装可能な粒度の設計がある。再設計は不要。
2. **止めているのは 3 つ。** (a) `ADR-0013` が DRAFT のままで、dispatch 可能なコードが禁止されている
   （`docs/architecture/decisions/0013-job-approval-authorization-receipt.md` 3〜12 行目）。
   (b) 隔離技術の選定と残余リスク受諾が未記録（`HYBRID_ISOLATION_PROFILES.md` §8）。
   (c) 外部 AI プロバイダ宛ての外向き通信が一度も承認されていない（`HYBRID_AGENT_ADAPTER_DESIGN.md` §11 AD-7）。
3. **設計そのものが無いのは 2 件だけ。** `HBR-008`（設定 UI）と `HBR-003`（分類の実データモデル）。
   `HBR-003` は実装も皆無で、`documents` テーブルに分類列が無く（`backend/app/service.py` 444〜450 行目）、
   `service.py` 全 3,279 行に `classification` の語が 1 件も無い。
4. 2026-11-16 のオーナー回答 E1〜E5 は、**2026-11-10 の Entry 1 と 1 箇所で矛盾する**（§4 所見 1）。
   先に突き合わせないと、レシート TTL の実装値が決まらない。

---

## 1. 要件ごとの到達度

凡例: **設計済** = 実装可能な粒度の記述が既にある（引用節を示す）。
**要決定** = 設計はあるがオーナー判断が空。**未設計** = 文書が存在しない。

| ID | 既に設計されている内容（出典） | 設計済だが未実装 | 設計が無い／要決定 |
|---|---|---|---|
| `HBR-001` ワークスペース単位の実行先選択 | `HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` §3.1（`runner_types` 既定は空＝実行不可）、§2.1（`workspaces.runner_instance_id` は種別でなく実体に束縛）。実装済メタデータ: `backend/app/agents/registry.py` 83〜118 行・137〜146 行 | 実行時に「この workspace は desktop のみ」を強制する点。現状 B6 で dispatch 自体が拒否されるため強制点が存在しない | 配備単位（Server/Desktop どちらを先に作るか）は隔離プロファイル選定と同一の未決。UI は `HBR-008` と同じく未設計 |
| `HBR-002` 組織ポリシーの上限 | 同 §3.2 E3（capability ≤ policy、narrow のみ）、E7（既存ロール上限）。実装済: `registry.py` `_policy` 291〜319 行、`_capabilities` 619〜635 行（未知キーは剥がさず拒否） | 実行時強制（E3 が働く dispatch 経路が無い） | **「組織」層そのものが無い。** Entry 6 で組織レベル UI は作らないと決定済みなので、要件文の「組織ポリシー」を workspace policy＋既存ロール上限で満たすという解釈が、どの文書にも書かれていない（§4 所見 4） |
| `HBR-003` 分類と派生データの方針 | 同 §3.1（`classification_ceiling` 既定 `none`、`derived_classification` は inherit-max、未分類は常に拒否）、§3.2 E6（プロンプト・添付組み立て前の関門）、§5.3 slice 2c | — | **実質未設計。** 文書・チャンク・回答・引用に分類値をどう持たせるか、誰が付けるか、既存データ（分類列なし）をどう扱うかが無い。`documents`（`service.py` 444〜450 行）に列が無く、`service.py` に実装が 0 件 |
| `HBR-004` OS による Runner 隔離 | `HYBRID_ISOLATION_PROFILES.md` §3（W-D/W-S/L-D/L-S の候補行列）・§5（ファイル／プロセス／ネットワーク／後片付け）・§6（正検証と負プローブの対応表）・§7（証跡パッケージ）。`HYBRID_ISOLATION_ENGINEERING_DETAIL.md` §3.2（テスト族 `CFG` `FS` `PROC` `NET` `RES` `XFER` `AUTH` `OUT` `CXL` `CLEAN` `B6` `EVID`）・§3.3（PASS/FAIL/BLOCKED/SKIPPED 規則）・§4（証跡束縛と失効）・§5（プロファイル別チェックリスト）。`HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md` §2（Windows/Linux 技術比較） | 何も実装されていない（`runner/` ディレクトリ自体が存在しない） | **技術選定と残余リスク受諾が未記録**（`HYBRID_ISOLATION_PROFILES.md` §8）。E1〜E5 はここを埋めていない。これ以上の設計は不要、選定が要る |
| `HBR-005` プロバイダ識別と端末資格情報 | `HYBRID_AGENT_ADAPTER_DESIGN.md` §5（Codex CLI / Claude Code / Gemini CLI / ローカル LLM の調査）・§6.1 選定規則（Option 0 → 1 → 2 → 拒否）・§6.2 アダプタ×プラットフォーム選定表・§7（broker BR-1〜BR-4 比較）・§9（合成資格情報のみの検証計画）・§10（可用性行列）。`HYBRID_RUNNER_TRUST_DESIGN.md` §2.4（鍵族の分離不変条件） | presence メタデータのみ実装済（`registry.py` 154〜160 行、`credential_schema_is_presence_only` 53〜56 行） | `ADAPTER` §11 の `AD-1`〜`AD-7` が未決。オーナー E4「渡していい」は Option 2（broker）を解禁しうるが、**どの broker か（AD-3）は未決**で、同設計 §6.2 の既定選定は今も Option 1（直接） |
| `HBR-006` エージェント実行の監査 | `HYBRID_RUNNER_TRUST_DESIGN.md` §10（`trust.*` イベント分類 11 種と各々が暴くべき不正）。`HYBRID_STEP2_RECEIPT_CONTRACT.md` §7。`ADR-0013` §8（`agent.receipt.*` は提案形） | 既存 audit ポートはあるが Runner 実行の記録対象が存在しない | **監査ログの保護・改竄耐性・保持が未設計**（脅威 `T-T4`、`ADR-0012` B7 が未解決と明記、`TRUST` §12 で保護クラスが要決定）。イベント名の確定も要決定 |
| `HBR-007` 認証済み Runner トランスポート | `HYBRID_RUNNER_COMMUNICATION_DESIGN.md` §2（トポロジ、Runner 発信のみ、job サンドボックスはネットワーク無し）・§3.1（mTLS、`runner_instance_id` 束縛、TLS は認可でない）・§3.2（`CP-ENROLL` `CP-CONTROL` `CP-RESULT` `CP-DNS` と「その他すべて拒否」の表）・§3.3（エンドポイント承認の 5 段ステートマシン）・§5（検証計画）・§6（活性化証跡 10 項目）。`HYBRID_RUNNER_TRUST_DESIGN.md` §4 | 何も実装されていない | 配備固有値が未決: LAN セグメントと CP の正確な宛先、名前解決に依存するか、TLS バージョン／暗号／鍵寿命（`TRUST` §12 の 9 パラメータ全部） |
| `HBR-008` プロバイダ・ランタイム設定 UI | **なし。** 参照できるのはオーナー E2 の 1 行「管理者が事前に許可しているとログイン認証を試みるタブが表示される」だけ | — | **未設計。** `frontend/src/` に runner/adapter 関連ファイルは 0 件（`grep -rln "runner|Runner|adapter" frontend/src` が空）。UI は許可の写像であって許可ではない、という原則だけが E2 の解釈欄にある |
| `HBR-009` Plane-M ゼロツール関門の維持 | `ADR-0011`、`ADR-0012` B1。既存実装とゼロツール退行スイートがある（`loop_engine/model_gate.py` ほか、`tests/unit/test_loop_tool_surface.py`、`tests/unit/test_loop_c_min.py`） | 境界側は実装済。残るのは Plane R を足すときに壊れないことの固定 | 要決定なし。マトリクスの `未着手` は「ハイブリッド要件群としての」状態であり、既存 Loop 部分が無いという意味ではない（同マトリクス 66 行目が明言） |
| `HBR-010` B1〜B7 モジュール／トランスポート分離 | `HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` §1.1（2 プレーン 2 モジュール木）・§1.2（B1〜B7）・§1.5（逐語保持する境界） | **パッケージ全体の双方向 import グラフ検査と動的 import 検査が無い。** 現状は Plane-M import の片側チェックのみ（`tests/test_agents_registry.py`） | 要決定なし。早期に取れる |
| `HBR-011` ゲート通過まで dispatch を明示的に拒否 | 同 §2.2・§3.3。実装済: `registry.py` `dispatch_attempt` 716〜734 行（Runner の有無に関係なく 409、拒否も監査）、`backend/app/main.py` 865 行のルート | 状態は `実装中`。残りは PH2-2AR の MEDIUM 1 件と exact-head CI 証跡 | 要決定なし |
| `HBR-012` Runner 登録とポリシー不変性 | 同 §2.1。実装済: `registry.py` 83〜110 行（`no_insert_replace`／`no_update`／`no_delete` の 3 トリガ）、版付きバインド 137〜146 行 | 状態は `実装中`。残りは `HBR-011` と同じ MEDIUM/CI | 要決定なし |
| `HBR-013` ジョブレシートと成果物来歴 | `HYBRID_STEP2_RECEIPT_CONTRACT.md` §2.1（レシート論理フィールド 15 項目と各々の検証点）・§2.2（ジョブエンベロープ）・§2.3（束縛トレース）・§4（E1/E2 の責務分担）・§5（fail-closed 行列）・§6（オンライン要件）。`HYBRID_ISOLATION_ENGINEERING_DETAIL.md` §2.2（DP-042/044〜048 の失効・参照・新鮮度・再送・束縛権威）・§2.3（DP-049 成果物の完全性と解放規則）。`ADR-0013` §1〜§8 | **全部未実装。** テーブルは metadata placeholder のみ（`registry.py` 161〜183 行）、発行・検証コードは無い | `ADR-0013` が DRAFT。同 §「Owner decisions this ADR requests」の 8 項目のうち、2026-11-16 回答で埋まるのは 4（TTL の既定値のみ）と 7（新規権限なし）。最大 TTL・絶対失効か deadline 連動か・時刻権威・スキュー許容・付与者権限喪失時の扱い・保持は未決 |
| `HBR-014` 受付・期限・キャンセル | `ADR-0012` のキャンセル安全性（確認できるまで終端にしない）。`HYBRID_ISOLATION_ENGINEERING_DETAIL.md` §2.4（DP-051: 数値は一切決めない、機構欠落はプロファイル失格）・§3.2 `CXL` テスト族 | `deadline_seconds` と `concurrency_limit` は CHECK で NULL 固定（`registry.py` 94〜95 行）＝意図的に無効 | 数値と機構が未決。**オーナー テーマ 3 の「待機列を複数本に」は Plane-M のモデルスロットの話であり、Plane R の受付制御ではない**（`HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` §3.2 末尾が両者の混同を明示的に禁止）。流用不可 |
| `HBR-015` プロバイダ別サポートと利用条項 | `HYBRID_AGENT_ADAPTER_DESIGN.md` §8（アダプタ別の実行制約と利用条件棚卸し）・§10（可用性行列）。`HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` §2.4（記録スキーマ承認、個別活性化は別ゲート） | **記録テーブルはあるが書き込む経路が無い。** `provider_contract_verifications`（`registry.py` 126〜131 行）に INSERT するコードも API も存在せず、参照は `tests/test_agents_registry.py` 336 行のスキーマ確認だけ | `AD-1`（検証を行うか・受入形式）と `AD-5`（アダプタ有効化リスト）が未決 |

---

## 2. 既存設計で答えが出ている要件（再設計を禁ずる）

次の作業で「設計から書き起こす」のは重複であり、やってはならない。該当節を読んで実装・選定するだけでよい。

- 隔離の検証内容（`HBR-004`）: `HYBRID_ISOLATION_ENGINEERING_DETAIL.md` §3.2 の 12 テスト族が、
  そのまま受入条件として使える粒度で書かれている。新しいテスト計画を書き起こさず、この表の ID を引く。
- 隔離の証跡と失効（`HBR-004`/`HBR-006`）: 同 §4.1 の証跡マニフェスト 8 フィールドと §4.2 の失効規則。
- エンドポイント承認手順（`HBR-007`）: `HYBRID_RUNNER_COMMUNICATION_DESIGN.md` §3.3 の 5 段
  （設計 → 検証 → 独立レビュー → 個別オーナー承認 → 運用活性化）。段を飛ばす設計を書かない。
- 登録の儀式（`HBR-007`）: `HYBRID_RUNNER_TRUST_DESIGN.md` §5.1 の 5 手順と §5.2 の fail-closed 却下 11 ケース。
  オーナー E5 の「一回限りの合言葉」はこの §5.1 手順 2〜3 と同一であり、追加設計は要らない。
- 鍵の保管（`HBR-005`）: 同 §3.1 の Windows/Linux 比較、§3.2 の保護実証 6 項目、§3.3 の残余リスク文。
  オーナー E5 の「OS 管理で良い」はこの設計の採択そのもの。
- レシートの論理契約（`HBR-013`）: `HYBRID_STEP2_RECEIPT_CONTRACT.md` §2.1〜§2.3 と §5 の fail-closed 行列。
- 資格情報供給の選択肢（`HBR-005`）: `HYBRID_AGENT_ADAPTER_DESIGN.md` §6.1 選定規則と §7 の broker 比較。
- 権限の割り当て（`HBR-006`/`HBR-008`）: `HYBRID_RUNNER_TRUST_DESIGN.md` §6（新規権限を作らず既存
  `system_admin` に対応付け、`organization_admin` や project スコープのロールは対象外）。
  オーナー E2 の「新しい承認係は作らない」と一致しており、再検討不要。

## 3. 設計も実装も無いもの（新規に書く必要がある）

1. **`HBR-008` 設定・認証 UI。** 文書ゼロ、コードゼロ。E2 の「許可済みの利用者にだけタブが出る」を
   どの画面にどう出すか、サーバ側認可とどう二重化するかを書く必要がある。
2. **`HBR-003` 分類のデータモデル。** 既存の取り込み・検索・引用経路に分類値を通す設計が無い。
   既定 fail-closed を既存データに適用すると、分類列を持たない既存文書が全部拒否されるため、
   移行の扱いを決めずに実装すると現行機能が壊れる。
3. **監査ログの保護（`HBR-006` の後半）。** `ADR-0012` B7 が未解決と明言しており、どの文書も
   改竄耐性・アクセス制御・保持期間を設計していない。
4. **`HBR-002` の「組織」の定義。** Entry 6 で組織レベル UI を作らないと決めた結果、
   要件文の組織ポリシーを何が担うのかが宙に浮いている。

---

## 4. 所見（矛盾・欠落。塗り潰さずに記録する）

1. **レシート TTL が二重に決まっている。** `OWNER_DECISIONS_2026-11-10-ENTRIES.md` Entry 1 は
   「既定 24 時間・最大 7 日間・猶予なし」を**正式決定**として記録済み。一方
   `progress/phase-6-extensions/OWNER_DECISIONS.md` テーマ 1 E1 は「一か月」で、解釈欄に
   「開発側の推奨（既定 24 時間・上限 7 日）はオーナー判断で上書きされた」と書いてある。
   前者は推奨ではなく既に下された決定なので、**新しい回答による決定の上書き**として扱う必要がある。
   さらに 2 点が宙に浮く: (a) **最大 TTL は回答されていない**（7 日のままなら「既定 1 か月・最大 7 日」で矛盾する）。
   (b) 11-16 の回答は「リース」の語を使っており、Entry 1 の対象は「ジョブレシート」。
   1 ジョブ 1 回の認可（`RECEIPT_CONTRACT` §2.1 `job_id`「one receipt authorizes exactly one job」）に
   1 か月の寿命を与える意味なのか、Runner 登録のリースに与える意味なのかが判定できない。
   → `T-PH8-301` で突き合わせ、オーナーに 1 問だけ返す。
2. **E4「渡していい」は Entry 4 の段階制約を飛ばしている。** Entry 4 は「現段階では実認証情報の供給を許可しない」
   「broker 採用時は検証証跡・独立レビュー・個別 Owner 承認が必要」と決定済み。
   11-16 の E4 はその最後の個別承認に当たるとも読めるが、`ADAPTER` §11 `AD-3`（BR-1/BR-2/BR-3 のどれか）が
   未決のままなので、**何を承認したのかが特定できない**。設計側の既定は今も Option 1（CLI 直接）であり、
   broker は未選定（同 §6.2 最終行）。
3. **E3「社内回線内でよい」と「外部 AI を動かす」は、そのままでは両立しない。** §5 で単独の最大課題として扱う。
4. **`HBR-002` の組織層。** §3 の 4 点目と同じ。Entry 6（組織 UI なし）と要件文（組織ポリシー統制）の
   整合が文書化されていない。実装前に 1 行の解釈が必要。
5. **ロードマップの要件 ID に誤りがある。** `docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md` の H3 行は
   対象を `HBR-001–007, HBR-010–016` と書くが、`HBR-016` は存在しない（マトリクスは 015 まで）。表記の誤り。
6. **`HYBRID_SKILLS_INTEGRATION_DESIGN.md` は HBR 要件を 1 つも扱っていない。** 内容は
   `obra/superpowers` 由来の Loop オーケストレータ向け Markdown スキルの取り込み（P0 3 件）であり、
   ハイブリッド Runner の設計文書ではない。名前が `HYBRID_` で始まるため同一ブロックに見えるが、
   `HBR-*` のどの行の根拠にもならない。ハイブリッド設計の在庫を数えるときに混ぜないこと。
7. **`HYBRID_ISOLATION_PROFILES.md` §9 と `HYBRID_STEP3_*.md` §2 は VM 前提の強さが食い違う。**
   step3 は Windows/Linux ともに VM 第一を「提案」し、profiles 側は「普遍的な義務に昇格させない」と
   明示的に否認している。profiles 側が後発かつ上位（step3 を設計入力として引用している）なので、
   profiles の立場が現行。step3 の VM 第一を既定として実装してはならない。
8. **独立レビューはどの設計にも入っていない。** `ISOLATION_PROFILES` §9 末尾・`TRUST` §11 条件 7 ともに
   「このタスクはサブエージェント委譲を禁止されているため独立レビューは未実施」と記録している。
   活性化前のゲートとして全件残っている。計画上、レビュー枠を各ジョブに持たせる必要がある。

---

## 5. 最大の未解決設計課題（1 つだけ挙げるなら）

**外部 AI プロバイダ宛ての外向き通信を、どの境界で、誰の判断で許すか。**

- 要件 `HBR-001` は「外部 AI/ツールを隔離された作業部屋で動かす」ことであり、Codex CLI / Claude Code /
  Gemini CLI はいずれも各社 API への外向き通信が無ければ 1 文字も生成しない。
- 一方、確定している境界は全部その逆を向いている。
  - オーナー E3「社内回線内でよい。外向きは既定で拒否、許可する宛先は設定で明示列挙」。
  - `HYBRID_RUNNER_COMMUNICATION_DESIGN.md` §3.2 最終行: インターネット・クラウド・**プロバイダ API** は
    `DENY`、例外には個別のエンドポイント設計・検証・独立レビュー・オーナー承認が必要。
  - 同 §2: **ジョブサンドボックス自身はネットワークを一切持たない**。通信できるのは Runner ホストの
    転送プロセスのみで、その許可はジョブに継承されない。
  - `HYBRID_AGENT_ADAPTER_DESIGN.md` §11 `AD-7`: 「CLI 自身の外向きプロバイダ宛先を egress として
    承認するか」は未決のオーナー判断。
  - コードも閉じている: `egress_mode` は `CHECK(egress_mode IN ('local_only'))`、
    `destination_allowlist` は `CHECK(destination_allowlist='[]')`（`registry.py` 90〜92 行）。
    `allowlisted` は非実効のプレースホルダであり、値・スキーマ・コードを作ること自体が禁止
    （`HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` §3.1）。
- したがって、隔離技術を選び、Runner を登録し、トランスポートを実装し、レシートを発行し終えても、
  **外部 AI は 1 回も呼べない。** この 1 点を解かずに下流を実装すると、最後に使えない機能が残る。
- 問いの形にすると: 「ジョブサンドボックスをネットワーク無しに保ったまま、プロバイダ API への通信を
  どこに置くか。(a) CLI をサンドボックス内で走らせ、そのサンドボックスにだけ宛先限定の穴を開ける
  （`§2` のネットワーク無し原則を変更する＝境界変更）。(b) Runner ホスト側の仲介プロセスが
  プロバイダ通信を代行し、ジョブはそのプロセス経由でしか外に出られない（`ADAPTER` §7 BR-4 の
  ローカルプロキシに近く、同設計は Q4 のもとでこれを却下済み）。(c) 外部 AI は使わず
  ローカル LLM（Option 0）だけを Runner で動かす（`ADAPTER` §6.2 の既定で、唯一いま成立する選択肢）。」
- `T-PH8-302` はこの 3 択をオーナーが選べる形に整えるジョブで、**他のどの実装ジョブよりも先に答えが要る**。

---

## 6. 依存順のジョブ分割

### 6.1 依存の骨格

```
T-PH8-301 (ADR-0013 の決定確定)
   ├─> T-PH8-307 レシート発行/検証 (E1)      ─┐
   ├─> T-PH8-308 runner_contract スキーマ      ├─> T-PH8-311 mTLS ─> T-PH8-312 E2 再検査
   └─> T-PH8-314 監査イベント                 ─┘
T-PH8-302 (外向き通信の 3 択/AD-7)  ─> T-PH8-316 アダプタ資格情報 ─> T-PH8-317 条項記録
T-PH8-303 (分類の設計)             ─> T-PH8-306 分類の実装 ─> T-PH8-315 成果物来歴
T-PH8-304 (隔離プロファイル選定書) ─> T-PH8-305 攻撃プローブ ─> T-PH8-309/310 登録・鍵
独立に着手可: T-PH8-319 (B1 import グラフ), T-PH8-320 (2a 残指摘), T-PH8-321 (ゼロツール退行固定)
```

### 6.2 完全なチケットを書いたもの（`tasks/` 配下）

| ID | 内容 | 要件 | 拾えるか |
|---|---|---|---|
| `T-PH8-301` | `ADR-0013` を 2026-11-16 回答で埋め、残決定を機械可読レジスタにする | `HBR-013` `HBR-011` | 拾える |
| `T-PH8-302` | 外部プロバイダ宛て通信の 3 択をオーナー判断可能な形にする（`AD-7`/Entry 3） | `HBR-001` `HBR-005` `HBR-007` | 拾える |
| `T-PH8-303` | 分類のデータモデルと既存データ移行の設計 | `HBR-003` | 拾える |
| `T-PH8-304` | 隔離プロファイル選定書（W-D/W-S/L-D/L-S から 1 つに絞る判断材料） | `HBR-004` | 拾える |
| `T-PH8-305` | 隔離境界を攻撃する合成プローブ・ハーネス | `HBR-004` `HBR-010` | **拾えない**（設計承認待ち） |

### 6.3 残りのジョブ（1 行ずつ）

| ID | 内容 | 要件 | depends_on | weight | `allowed_paths` | 先に決める必要があること |
|---|---|---|---|---|---|---|
| `T-PH8-306` | 分類の実装（E6: 取り込み・検索・回答・引用の全経路で未分類を拒否） | `HBR-003` | 303 | heavy | 未確定 | 既存文書の移行扱い（`T-PH8-303` の承認）。fail-closed を既存データに当てる範囲 |
| `T-PH8-307` | レシート発行と E1 再検査（slice 2b 相当。dispatch は開けない） | `HBR-013` | 301 | heavy | 未確定 | `ADR-0013` の承認と最大 TTL・時刻権威・スキュー |
| `T-PH8-308` | `runner_contract/` 版付き閉スキーマ（通信なし、直列化と拒否のみ） | `HBR-010` `HBR-013` | 301 | medium | `runner_contract/`, `tests/` | 直列化形式と schema_version の採番（`ADR-0013` 項目 2） |
| `T-PH8-309` | Runner 登録（pending → 一回限り合言葉 → 指紋二面確認）。鍵生成は行わない | `HBR-007` `HBR-012` | 304, 310 | heavy | 未確定 | 合言葉の寿命（`TRUST` §12）、どの OS プリンシパルに束ねるか |
| `T-PH8-310` | OS 資格情報ストアの保護実証（`TRUST` §3.2 の 6 項目、合成鍵のみ） | `HBR-005` | 304 | heavy | 未確定 | 対象ビルドの確定。Linux はファイル保管の残余リスク受諾（`TRUST` §3.3） |
| `T-PH8-311` | mTLS トランスポート（`CP-ENROLL`/`CP-CONTROL`/`CP-RESULT`、宛先は設定値） | `HBR-007` | 308, 309 | heavy | 未確定 | LAN セグメントと CP の正確な宛先、TLS パラメータ、`CP-DNS` を使うか |
| `T-PH8-312` | Runner 側 E2 再検査（レシート・失効・実体一致・ポリシー版を実行直前に再取得） | `HBR-013` `HBR-007` | 307, 311 | heavy | 未確定 | オンライン権威が落ちたときの挙動は fail-closed 固定だが、問い合わせ先が `T-PH8-311` 依存 |
| `T-PH8-313` | 受付・期限・キャンセルの計測と実装（`CXL` テスト族） | `HBR-014` | 305, 312 | heavy | 未確定 | 数値（同時実行・期限・キャンセル待ち）は計測後のオーナー判断。テーマ 3 の N は流用不可 |
| `T-PH8-314` | 監査イベント（`trust.*` と `agent.receipt.*`）の実装 | `HBR-006` | 301 | medium | 未確定 | イベント名の確定（`ADR-0013` 項目 6）と保護クラス（B7 未解決） |
| `T-PH8-315` | 成果物の来歴と解放関門（E9: 出典削除・失効で派生物を無効化） | `HBR-013` `HBR-003` | 306, 312 | heavy | 未確定 | 物理削除と保持期間（`HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` §6.6 で要決定） |
| `T-PH8-316` | アダプタ資格情報の供給（Option 1 か broker か）の実装 | `HBR-005` | 302, 310 | heavy | 未確定 | `AD-2`（CLI 自身のサンドボックスを境界と認めるか）、`AD-3`（broker 選定）、`AD-4`（API キー可否） |
| `T-PH8-317` | プロバイダ条項検証の記録経路（`provider_contract_verifications` に書く API） | `HBR-015` | 316 | medium | `backend/app/agents/`, `backend/app/main.py`, `tests/` | `AD-1`（受入形式）、`AD-5`（有効化リスト） |
| `T-PH8-318` | 設定・認証 UI（許可済み利用者にだけタブ、サーバ側でも拒否） | `HBR-008` | 316 | heavy | `frontend/src/`, `tests/` | UI の設計自体が存在しない。先に画面設計を起票すること |
| `T-PH8-319` | パッケージ全体の双方向 import グラフ検査（動的 import 含む） | `HBR-010` | なし | medium | `tests/` | なし。いま着手可 |
| `T-PH8-320` | slice 2a の MEDIUM 残指摘の解消と exact-head CI 証跡の取得 | `HBR-011` `HBR-012` | なし | light | `backend/app/agents/`, `tests/` | PH2-2AR の指摘本文の特定（レビュー記録の参照） |
| `T-PH8-321` | ゼロツール退行スイートを Plane R 追加後も壊れないよう固定 | `HBR-009` | 308 | medium | `tests/` | なし |
| `T-PH8-322` | 組織ポリシー上限の実行時強制（capability ≤ policy を dispatch 経路で） | `HBR-002` | 307 | medium | 未確定 | 「組織」を何が担うかの 1 行解釈（§4 所見 4） |
| `T-PH8-323` | ワークスペース単位の実行先選択の実行時制約（Server/Desktop） | `HBR-001` | 305, 312 | medium | 未確定 | 配備するプロファイルの選定（`T-PH8-304` の結果） |

### 6.4 いま拾えるジョブは 7 件

`T-PH8-301` `302` `303` `304` `308` `319` `320`（＋`321` は 308 のあと）。
それ以外は全部、セキュリティ境界か未決のオーナー判断に当たっている。
境界側のジョブは `allowed_paths: 未確定` にしてあり、`jobloop/tasks.py` 66〜68 行の判定で
ループが拾わない。これは放置ではなく、受入条件が「動いた」に退化するのを防ぐための停止である。
