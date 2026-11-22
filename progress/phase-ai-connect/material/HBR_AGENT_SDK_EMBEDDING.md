# HBR Agent SDK 埋め込み設計ゲート（Claude Code / 設計のみ）

- 状態: **設計ゲート資料（実装なし）**。本書は比較・検証条件・activation gate を定める。adapter の有効化、資格情報の読取/転送/供給、provider login、外部通信、B6 dispatch の解除は承認しない。
- 対象: **Claude Code のみ**（オーナー決定 2026-11-22 #2）。Codex / opencode は後続設計とし、本書では同時に設計しない。
- 根拠: オーナー決定 2026-11-22（`progress/phase-ai-connect/tasks/T-AIC-004.md` 正本）、`docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md`（特に §1.2, §4.2, §5.2, §9, §12）、`docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md`（§1.2 B1-B7, §2.4）、`docs/architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md`、`docs/architecture/DOCUMENT_EXTRACTION_BOUNDARY.md` §5、`backend/app/agents/registry.py`、`tests/test_agents_registry.py`。
- 確定後の反映先: `docs/plans/` 配下の設計正本は本ジョブの `allowed_paths` 外のため、本書を material として置く。正本反映は別タスク/オーナー操作で行う。

## 1. 決定の前提（2026-11-22）

| # | 決定 | 本書への拘束 |
|---|---|---|
| 1 | 接続経路は **(b) Agent SDK 埋め込み** | CLI headless 起動や ACP 外部プロセス呼び出しを本設計の主経路にしない。Claude Code Agent SDK をライブラリとして埋め込む前提で比較する。 |
| 2 | 対応順は **Claude Code → Codex → opencode** | 比較・検証・activation gate の対象は Claude Code のみ。Codex/opencode 固有の差分は「後続で再評価」と明記し、先に一般化しない。 |
| 3 | **CLI かどうかはどうでもよい。求められるのはチャット画面で、接続した利用者がモデル管理の部分で選べること** | 実行形態は UX を満たす限り自由。埋め込み先は UX・境界適合・資格情報不変条件で選ぶ。 |
| 4 | **隔離の実証はやりやすい方で良い** | ただし「弱い方の保証しか主張しない」を破らない。`DOCUMENT_EXTRACTION_BOUNDARY.md` §5 の先例に倣い、主張できる保証と主張できない保証を分ける。 |

決定 3 から導かれる設計判断: 埋め込み先はまだ未確定だが、**Desktop Runner 埋め込み案を既定の推奨**とする。理由は、利用者の Claude ログインをサーバが預からずに済み、`HYBRID_AGENT_ADAPTER_DESIGN.md` §4.2 Option 1（CLI ネイティブログイン・端末側保持）と `credential_schema_is_presence_only` の不変条件を壊さずに、モデル管理から選ぶ UX を満たせるため。サーバ埋め込み案は、サーバが利用者の資格情報を持つ構造になり得るため、`T-AIC-006` の (B) 判断が先に必要になる。

## 2. 埋め込み先 2 案の比較（Claude Code Agent SDK）

比較対象は「Claude Code Agent SDK をどこに埋め込むか」の 2 案のみ。いずれも B6 dispatch 拒否、Plane M ゼロツール境界、presence-only、分類/egress 独立ゲート、監査境界を前提とする。

| 観点 | 案 A: Desktop Runner 埋め込み（既定の推奨） | 案 B: サーバ埋め込み（T-AIC-006 (B) 待ち） |
|---|---|---|
| 実行場所 | 利用者端末上の Desktop Runner プロセス。SDK/CLI 実行は端末ローカル。 | Locus サーバ（Control Plane と同一信頼域または近接したサーバ側実行域）。 |
| UX（モデル管理から選ぶ） | 満たせる。モデル管理 UI は Control Plane のメタデータ/許可状態を表示し、実際の SDK 実行は Desktop Runner へ dispatch する。 | 満たせるが、端末ログイン状態とサーバ実行の橋渡しが必要になり、資格情報境界が複雑化する。 |
| 実行隔離の強制点 | Desktop Runner が作業ディレクトリ、ファイルアクセス、ネットワーク、環境変数、実時間/出力上限を適用してから SDK を起動する。強制は Runner ホスト/OS 機構に依存し、未検証なら B6 fail-closed。 | サーバ側コンテナ/プロセス境界で強制する必要がある。マルチテナント/共有サーバでは隔離破りの影響半径が大きい。 |
| 認証情報の置き場 | **Option 1（CLI ネイティブログイン・端末側保持）**を既定とする。Claude Code の公式ログイン状態は端末の CLI/OS が管理する領域に留め、Locus は presence/health metadata のみ扱う。サーバへ資格情報値を送る経路は設けない。 | サーバが SDK 実行主体になると、サーバが資格情報を読める/保持する構造を取りやすい。これは Option 1 と `credential_schema_is_presence_only` の不変条件に緊張を作る。採用するなら T-AIC-006 (B) で資格情報保持方針を先に決める。 |
| 分類ポリシー / egress 判定 | Control Plane が E1（enqueue 前）で policy/classification/destination/receipt を検査。Desktop Runner が E2（実行直前）で同じ束縛を再検査。分類と egress は独立ゲート。 | 同じ E1/E2 構造は必要だが、サーバ内実行では「Runner が別信頼域」という前提が弱まり、監査/責任分界の説明が難しくなる。 |
| 監査 | Control Plane は利用者・workspace・adapter・model・判定結果・理由カテゴリ・policy version・receipt/binding の結果を記録。本文/資格情報/生トークンは記録しない。Desktop Runner は実行開始/終了/失敗/cleanup 結果を同じ相関 ID で返す。 | サーバ実行でも同項目は必要。加えてサーバ側で資格情報や provider 応答本文に触れる設計は監査漏えい面が増えるため不適合。 |
| 失敗・中断時の後始末 | Runner が SDK/子プロセス系統を kill、ジョブ一時領域を cleanup、成果物を quarantine/invalidated 扱い、Control Plane に terminal 状態を返す。未確認 cleanup は成功扱いしない。 | サーバ実行ではサーバプロセス/共有ファイルシステム/他ジョブへの影響を切り分ける必要があり、後始末の blast radius が大きい。 |
| 主なリスク | 端末環境差、Desktop Runner 配備/更新、端末がオフライン時の実行不可。 | 資格情報集中、サーバ侵害時の影響拡大、`T-AIC-006` (B) 未決、presence-only 不変条件を破る実装へ寄りやすい。 |
| 推奨 | **既定の推奨**。決定 3 の UX を満たしつつ、Option 1 / presence-only / Plane R 分離に整合しやすい。 | **現時点では非推奨**。T-AIC-006 (B) でサーバ保持方針と監査/責任分界が承認されるまで設計候補に留める。 |

## 3. 既存境界との適合表

| 既存境界 | 出典 | 案 A: Desktop Runner 埋め込み | 案 B: サーバ埋め込み | 判定 |
|---|---|---|---|---|
| ゼロツール境界（Plane M） | ADR-0012, ADR-0011, `HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` §1.1-B3 | Plane M は従来どおり tool declaration を拒否。Claude Code Agent SDK のツール実行は Plane R（Desktop Runner）でのみ行う。Control Plane は metadata/receipt/binding のみ。 | Plane M/Plane R のコード境界は保てるが、同一サーバ信頼域に実行系が近づくため運用上の誤結合リスクが高い。 | A: 適合しやすい / B: 条件付き |
| presence-only（資格情報値を保存しない） | `HYBRID_AGENT_ADAPTER_DESIGN.md` §1.2, §4.2, `backend/app/agents/registry.py` `adapter_credentials` schema, `credential_schema_is_presence_only`, `tests/test_agents_registry.py` | 端末側 CLI ログイン状態を使い、Locus は `enrolled/absent/revoked` と `checked_at` 等の presence metadata のみ記録。サーバへ値を送らない。 | サーバ実行は資格情報値の読取/注入/保持に踏み込みやすい。presence-only を維持するには broker/keystore/非輸出性の追加証明が必要。 | A: 適合 / B: T-AIC-006 (B) が先 |
| 分類ポリシー（分類と egress の独立ゲート、fail-closed） | ADR-0012 §4, `HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` §3.1-E5/E6, `HYBRID_AGENT_ADAPTER_DESIGN.md` §1.2 | E1 で Control Plane が分類上限・destination allowlist・local_only/allowlisted 状態を判定。E2 で Desktop Runner が実行直前に再確認。未分類/不明/未承認は deny。 | 同じゲートは定義できるが、サーバ実行主体が広い権限を持つ場合に bypass 面積が増える。 | A: 適合 / B: 条件付き |
| 監査（metadata only、本文/資格情報なし） | ADR-0012 B7, `HYBRID_AGENT_ADAPTER_DESIGN.md` §1.2, `HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` §2.1/§2.6 | 監査は actor/workspace/adapter/model/policy version/判定結果/理由カテゴリ/相関 ID を記録。prompt 本文、tool 出力本文、資格情報値は記録しない。 | サーバ実行で資格情報や本文に触れる経路が増えると、監査境界の逸脱リスクが増える。 | A: 適合 / B: 条件付き |

### 3.1 不変条件（本設計で破ってはならない）

- `credential_schema_is_presence_only` が真であること。`adapter_credentials` は presence metadata のまま維持する。
- B6 dispatch 拒否は有効なまま。Runner/registry/本書の存在は activation 根拠にならない。
- 分類許可と egress 許可は独立判定。片方の許可をもう片方の許可として扱わない。
- Plane M に tool declaration を注入しない。Agent SDK の tool 実行は Plane R のみ。
- 監査・receipt・job input・model context に資格情報値や本文を入れない。

## 4. 実行隔離・資格情報・判定点・監査・後始末

### 4.1 実行隔離（Desktop Runner 埋め込み案）

| 項目 | 強制方法 | 備考 |
|---|---|---|
| 作業ディレクトリ | ジョブごとに専用 workspace/scratch ディレクトリを割り当て、SDK/CLI の cwd をその配下に固定する。 | パスは job envelope に含めるが、資格情報値は含めない。 |
| ファイルアクセス | 許可された workspace/scratch のみ読み書き可。ホームディレクトリ、他 workspace、資格情報ストア、Control Plane DB へのアクセスを deny。 | OS 強制が未証明の環境では「強制した」と主張しない。§5 の表に従う。 |
| ネットワーク | provider egress は別ゲート（AD-7 / Entry 3 系）。既定は deny。許可済み宛先がない限り SDK の外向き通信を許可しない。 | 子プロセス系統でネットワーク遮断を主張できない場合は `network: unverified` と記録する。 |
| 環境変数 | SDK 起動時は最小環境変数のみ渡す。資格情報値、Locus セッション、無関係な秘密を継承しない。 | 親環境の漏れは負検証で確認する。 |
| 実時間 / 出力 | 実時間上限・stdout/stderr 上限・プロセス系統 kill を必須にする。 | 上限超過は隔離/失敗として扱い、成功扱いしない。 |
| CPU / メモリ | docker/cgroup 等で強制できる場合のみ主張する。Windows 子プロセス系統では主張しない。 | §5 の先例に従う。 |

### 4.2 認証情報の置き場

- 既定は `HYBRID_AGENT_ADAPTER_DESIGN.md` §4.2 Option 1: **CLI ネイティブログイン・端末側保持**。
- Locus サーバへ資格情報値（API key, OAuth token, refresh token, session cookie, CLI auth file 内容）を送る経路は設けない。
- Control Plane / registry が保持してよいのは presence metadata のみ（例: enrolled/absent/revoked, checked_at, adapter binding, policy version echo）。値を保持する列/フィールドは追加しない。
- Desktop Runner は Claude Code の公式認証操作を端末の認証ストア経由で行う。Runner は認証結果の成否と非秘密の診断カテゴリだけを Control Plane に返す。
- サーバ埋め込み案を採る場合は、この節を満たせない可能性が高い。採用前に T-AIC-006 (B) で資格情報保持・責任分界・監査・漏えい時の扱いを決定する。

### 4.3 分類ポリシーと egress 判定の dispatch 段階

| 段階 | 実施主体 | 判定 | fail-closed 条件 |
|---|---|---|---|
| D0 UI 選択 | チャット/モデル管理 UI | 利用者が選べるのは、許可済み workspace binding と表示可能な adapter/model metadata のみ。未許可 adapter は表示しないか disabled 表示。 | 許可状態が不明なら選択不可。 |
| D1 Enqueue 前（E1） | Control Plane | actor 権限、workspace 有効性、exact policy version、adapter allowlist、runner binding、receipt 有効性、分類上限、egress mode/destination を検査。 | receipt 欠落/失効/不一致、policy 不一致、分類不明、destination 未承認、B6 active は reject。 |
| D2 Dispatch 前 | Control Plane | B6 gate を評価。現在は常に reject（409 `Runner boundary is unproven; dispatch is disabled`）。将来 gate 通過後も E1 再評価結果が current であることを要求。 | B6 active、境界未検証、監査保護未整備、T-T4 未解決は reject。 |
| D3 Runner 受領直前（E2） | Desktop Runner | 署名/完全性付き job envelope、receipt、policy version、workspace binding、adapter binary identity、destination、classification を再検査。 | envelope 不正、replay/expiry、policy 変更、revocation、binding 不一致は reject。 |
| D4 SDK 起動直前 | Desktop Runner | 作業ディレクトリ、環境変数最小化、ファイルスコープ、ネットワーク設定、監査相関 ID、cleanup handler を準備。 | 隔離セットアップ未完了、cleanup handler 未設定、監査初期化失敗は起動しない。 |
| D5 実行中 | Desktop Runner | 許可済み destination のみ通信可。分類上限を超える入力/添付/成果物は投入・出力しない。 | 想定外 destination、分類不明派生物、policy 失効検知は中断。 |
| D6 終了/中断後 | Desktop Runner + Control Plane | terminal 状態、cleanup 結果、監査イベント、成果物の quarantine/invalidated 判定を確定。 | cleanup 未確認は成功にしない。 |

### 4.4 監査に残す項目

監査は metadata only。以下を記録対象とし、本文は記録しない。

| 項目 | 記録 | 記録しない |
|---|---|---|
| 利用者 | actor/user ID、認可判定の主体 | パスワード、トークン、セッション秘密 |
| workspace | workspace ID、policy ID/version、binding ID | workspace 内文書本文 |
| adapter | adapter ID/type、binary/version pin、runner instance ID | adapter 設定に含まれうる秘密値 |
| モデル | 選択された model ID/alias、provider/SDK 識別子 | prompt/response 本文、思考過程本文 |
| 判定結果 | allow/deny、reason category、どのゲートで停止したか（E1/E2/B6/classification/egress/cleanup） | 失敗時の生スタックに含まれる秘密値 |
| 実行 | job/receipt/envelope 相関 ID、開始/終了時刻、terminal status、cleanup status | ツール実行の生入出力本文 |
| 成果物 | artifact ID/digest、classification/invalidation 状態 | artifact 内容そのもの |

### 4.5 失敗・中断時の後始末

1. **起動前失敗**: SDK を起動しない。enqueue/dispatch/runner いずれの段階でも deny を監査し、部分的な job 状態を残さない。
2. **実行中失敗/中断**: Runner は SDK/子プロセス系統へ terminate を送り、猶予後に kill する。キャンセルは「確認できるまで terminal にしない」（ADR-0012 の安全意味論）。
3. **一時ファイル**: job 専用 scratch を削除または隔離。削除失敗は `cleanup_unverified` として記録し、成功扱いしない。
4. **途中成果物**: 完全性・由来・分類・policy version が確定しない成果物は公開/再利用しない。`invalidated` または quarantine 扱いとし、再利用前に再検証する。
5. **監査**: 開始したが terminal 化できなかった場合も、最後に観測した状態と cleanup 未確認を記録する。監査書き込み失敗時は fail-closed（成功応答を返さない）。
6. **資格情報**: cleanup 対象に資格情報値をコピーしない。ログ/一時ファイル/例外メッセージへの出力を禁止する。

## 5. 隔離の保証表（DOCUMENT_EXTRACTION_BOUNDARY §5 と同じ語彙）

前例: `docs/architecture/DOCUMENT_EXTRACTION_BOUNDARY.md` §5。Windows では `resource` モジュールが無く docker エンジンも動いていないため、子プロセス系統でネットワーク遮断・メモリ上限を主張しない。**弱い方の保証しか主張しない。**

### 5.1 主張できる保証 / 主張できない保証

| 保証 | docker / 強制されたコンテナ系統（実証済みの場合のみ） | 子プロセス系統（現状の既定） |
|---|---|---|
| 実時間上限 | ○ | ○ |
| 出力バイト数上限 | ○ | ○ |
| 環境変数の遮断 | ○ | ○ |
| 書込み先の限定 | ○（read-only + tmpfs / mount 制御） | **△ 作業ディレクトリ外への書込みを止める強制力は無い** |
| CPU 時間・メモリ上限 | ○ | **× Windows では主張しない** |
| ネットワーク遮断 | ○ | **× 主張しない（ADR-0006 で loopback が通った実測あり）** |

### 5.2 記録ルール

- 子プロセス系統で走った場合、監査/実行記録は **ネットワーク遮断・メモリ上限を主張していない**こと。
- 子プロセス系統では、socket 制限や環境変数除去の入口側対策を置いてよいが、それは**境界ではない**。記録は `network: unverified` のままにする。
- docker 系統の証跡が無い実行を docker 相当として記録しない。SKIPPED/BLOCKED な検査を証拠として扱わない。
- 「たぶん大丈夫」に書き換えない。未検証は未検証として残す。

## 6. Runner 境界の検証項目（mock/synthetic data のみ）

`HYBRID_AGENT_ADAPTER_DESIGN.md` §9 の安全検証方針を、Claude Code Agent SDK 埋め込み（Desktop Runner 既定案）向けに具体化する。実資格情報、実 provider login、外部通信は禁止。fixture は synthetic token / stub CLI / stub SDK / stub keystore / stub Control Plane のみ。

### 6.1 正検証（positive）

| ID | 項目 | 手順（mock/synthetic） | 合否条件 |
|---|---|---|---|
| VT-C1 | Option 1 認証成立 | Desktop Runner テスト環境で stub Claude Code auth store に synthetic token を置き、stub SDK が認証操作を実行する。 | stub SDK が成功を返し、Control Plane には成功/失敗カテゴリのみ記録される。token 値はログ/receipt/job input/model context に出ない。 |
| VT-C2 | presence-only 記録 | 認証成功/不在/失効の synthetic ケースを投入する。 | `adapter_credentials` 相当の記録は state/checked_at 等の presence metadata のみ。`credential_schema_is_presence_only` 相当検査が真。 |
| VT-C3 | E1/E2 判定順序 | synthetic job envelope で D1→D2→D3→D4 の順に通過させる。 | 各段階の判定結果が相関 ID で監査され、B6 active 時は D2 で reject される。 |
| VT-C4 | 実時間/出力上限 | 無限ループ stub SDK と大量出力 stub SDK を実行する。 | 実時間上限超過は kill + terminal failure、出力上限超過は打ち切り + terminal failure。Control Plane は成功扱いしない。 |
| VT-C5 | cleanup 成功 | 正常終了 stub SDK を実行し、scratch に synthetic file を作る。 | job 終了後に scratch cleanup が確認され、監査に cleanup success が記録される。 |

### 6.2 負検証（negative）

| ID | 項目 | 手順（mock/synthetic） | 合否条件 |
|---|---|---|---|
| NV-C1 | 資格情報値の非露出 | synthetic token `MOCK-CLAUDE-0000` を store に置き、job input/receipt/audit/model context/exception message をスキャンする。 | すべて 0 件。いずれかに出た場合は FAIL。 |
| NV-C2 | tool 実行プロセスからの credential 読取拒否 | stub tool-executing process が auth store/env/memory dump 相当 fixture を読みに行く。 | 読取は denied。denied を証明できない場合は「未検証」であり PASS にしない。 |
| NV-C3 | Control Plane / 他 identity からの読取拒否 | stub Control Plane identity、interactive user identity、別 runner instance identity が auth store を読みに行く。 | すべて denied。 |
| NV-C4 | 分類不明入力の拒否 | classification 未設定の synthetic attachment/input を D1 に投入する。 | prompt/context assembly 前に deny。local fallback 実行はしない。 |
| NV-C5 | 未承認 egress の拒否 | allowlist 外 destination への synthetic 接続要求を発生させる。 | 接続前に deny。B6/egress gate の監査が残る。 |
| NV-C6 | B6 dispatch 拒否 | runner/adapters/presence metadata が揃った fixture でも dispatch を試行する。 | 409 `Runner boundary is unproven; dispatch is disabled`。job receipt/artifact は作られない。 |
| NV-C7 | policy/version 不一致の拒否 | enqueue 後に policy version を更新した synthetic ケースを E2 で再検査する。 | E2 で reject。古い receipt で実行しない。 |
| NV-C8 | cleanup 未確認の非成功扱い | terminate 後に cleanup handler が失敗する synthetic ケースを作る。 | terminal status は success にならない。`cleanup_unverified`/failure が監査される。 |
| NV-C9 | 子プロセス系統の記録偽装防止 | 子プロセス系統で実行した記録を生成する。 | 記録は `network: unverified` を含み、ネットワーク遮断・メモリ上限を主張しない。主張した場合は FAIL。 |
| NV-C10 | 本文非記録 | prompt/response/tool output に synthetic marker を入れて実行する。 | audit/receipt/job metadata に marker が出ない。必要な相関情報は ID/カテゴリのみ。 |

### 6.3 証跡要件

- 証跡は synthetic fixture、stub バイナリ、stub SDK、pinned version、OS/build、runner build、policy snapshot、相関 ID に束縛する。
- SKIPPED/BLOCKED は証拠ではない。未実施は未実施と記録する。
- 実資格情報・実 provider endpoint・実ユーザーデータを使った検証は本計画の対象外。

## 7. Activation gate（dispatch 409 を外す条件）

本節は **dispatch 409 を外す条件の定義**であり、解除の承認ではない。現状 `POST /api/workspaces/{id}/agent-dispatch-attempts` は 409 `Runner boundary is unproven; dispatch is disabled` を返し続けなければならない。

### 7.1 gate を開ける前に必要なもの

| Gate | 条件 | 根拠 | 状態 |
|---|---|---|---|
| G0 B6 | B6 明示拒否が維持され、runner 不在/存在のどちらでも dispatch 前に拒否される。 | ADR-0012 B6, `registry.py` `dispatch_attempt`, `tests/test_agents_registry.py` | 現在維持。解除しない。 |
| G1 Dual-plane | Plane M/Plane R 分離、B1-B7、import boundary、tool 非注入が回帰テストで固定されている。 | ADR-0012 | ADR-0012 accepted だが、SDK 埋め込み実装時に再確認が必要。 |
| G2 Approval ADR | dispatch-capable code の前提となる approval/authorization ADR（ADR-0013 系）が承認され、receipt 発行/検証/失効/replay 防止が実装・検証済み。 | ADR-0012 §4, ADR-0013, Step2 design | 未充足。 |
| G3 Boundary evidence | §6 の VT/NV が対象 OS/build/SDK version で実施され、PASS/FAIL/BLOCKED が証跡化されている。SKIPPED は証拠扱いしない。 | HBR design §9, 本書 §6 | 未充足。 |
| G4 Credential boundary | Option 1 の端末側保持が確認され、Control Plane/他 identity/tool process への credential export が否定される。presence-only schema が維持される。 | §4.2, §3.1 | 未充足。 |
| G5 Classification/egress | 分類ゲートと egress ゲートが独立に実装・検証され、未承認 destination は deny。AD-7 / provider egress 承認が別途ある。 | ADR-0012 §4, HBR §1.2 | 未充足。 |
| G6 Audit/T-T4 | 監査イベントが metadata only で記録され、監査ログ保護（T-T4: 改竄耐性/アクセス制御/保持）の activation blocker が解消されている。 | ADR-0012 B7 | 未充足。 |
| G7 Cleanup/failure | 中断・kill・cleanup 未確認・途中成果物 invalidation の fail-closed 動作が検証されている。 | ADR-0012, 本書 §4.5 | 未充足。 |
| G8 Owner approval | 実際の adapter activation、credential supply/login、provider egress、dispatch 解除について個別の Owner 承認がある。 | HBR §12, ADR-0012 | 未充足。 |

### 7.2 409 解除の判定ルール

- G0-G8 のいずれかが欠ける場合、dispatch は 409 のまま維持する。
- 「テストが一部通った」「Runner がインストールされた」「UI で選べるようにした」は解除条件ではない。
- 解除は Claude Code adapter 単位・環境単位・証跡束縛で行う。Codex/opencode へ自動拡大しない。
- 解除後も E1/E2 の再検査、receipt 失効、policy 変更、egress 未承認、cleanup 未確認は fail-closed。

## 8. 非目標 / 本書が承認しないこと

- dispatch 409 の解除、adapter activation、Runner 登録/有効化。
- 実資格情報の読取/転送/供給、provider login、実外部通信。
- `backend/app/agents/registry.py`、schema、API、テストの変更。
- Codex / opencode の同時設計。
- サーバ埋め込み案の採用（T-AIC-006 (B) 未決）。
- 子プロセス系統におけるネットワーク遮断・メモリ上限の主張。

## 9. 次の実装タスク起票に必要な決定材料

1. **T-AIC-006 (B)**: サーバ埋め込みが必要になる場合の資格情報保持方針。不要なら Desktop Runner 案を維持。
2. **ADR-0013 系**: receipt 発行/検証/失効/replay 防止の承認。
3. **AD-7 / egress**: Claude Code provider endpoint の個別承認。分類許可とは別ゲート。
4. **T-T4**: 監査ログ保護（改竄耐性・アクセス制御・保持）。
5. **Desktop Runner 配備設計**: runner identity、enrollment、更新、端末オフライン時 UX、job cancellation。
6. **§6 検証実装**: mock/stub fixture と証跡フォーマット。実行は別承認後。