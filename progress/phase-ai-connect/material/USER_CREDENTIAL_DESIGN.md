# 利用者ごとの資格情報をサーバで持つための設計（設計のみ）

- 状態: **設計ゲート資料（実装なし）**。本書は (A) プロバイダの API キーの保管方式、(B) エージェントの資格情報の境界、機械的ガード、および検証項目を定める。`adapter_credentials` の schema、registry API、dispatch、テスト、資格情報の実読取/実転送/実供給、外部通信、B6 dispatch の解除は承認しない。
- 対象タスク: `progress/phase-ai-connect/tasks/T-AIC-006.md`（`HBR-005` — ハイブリッドエージェント必須要件 5 / Must #5。安定要件 ID スキームは `docs/plans/REQUIREMENT_ID_SCHEME.md` §E）。
- オーナー決定 2026-11-22（本書の前提、正本は T-AIC-006）:
  1. **(B) エージェントの資格情報は端末側のまま。** サーバは利用者の Claude / Codex ログインを預からない。
  2. **(A) プロバイダの API キーは DB に置く**（暗号化して保存する）。
  3. **管理者でも他人の鍵の値は読めないようにする。** かつ「**バグらないように**」機械的な検査を付けること（規約ではなく、破れたら落ちる仕組み）。
- 決定から導いた判断（オーナーに聞き直さずに決めたこと。違えば覆してよい）:
  - **KEK（暗号鍵）を DB の中に置くことはできない。** 決定 3 が「管理者でも値は読めない」なので、DB を読める者が復号できては決定が無効になる。よって KEK は **DB の外**（サーバ環境変数か OS の資格情報ストア）に置く。
  - **(A) は `adapter_credentials` に足さず、新しいテーブルにする。** そうすれば `credential_schema_is_presence_only()` を弱めずに済む。不変条件を外さないで決定を満たせるなら、外さない。
  - **「管理者でも読めない」は守れる範囲を限って主張する。** アプリ経路と DB 読み取りには効くが、ホストに root 相当で入れる者には効かない。`docs/architecture/DOCUMENT_EXTRACTION_BOUNDARY.md` §5 と同じ作法で、弱い方の保証しか主張しない。
- 根拠: `docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md` §1.2, §4.2（Option 1 = CLI ネイティブログイン・端末側保持）、`backend/app/agents/registry.py:53-56, 186-187`（`credential_schema_is_presence_only` / 起動時 `RuntimeError`）、`backend/app/agents/registry.py:154-160`（`adapter_credentials` presence-only schema）、`backend/app/agents/registry.py:275, 725`（既存 `system_admin` 分岐）、`tests/test_agents_registry.py`、`docs/architecture/DOCUMENT_EXTRACTION_BOUNDARY.md` §5、`progress/phase-ai-connect/material/HBR_AGENT_SDK_EMBEDDING.md` §3.1。

## 1. 2 種類の資格情報を混ぜない

オーナー要望は「チャット画面で接続した利用者が、モデル管理の部分で選択できること」であって、**サーバが利用者の Claude / Codex ログインを預かること**ではない。(A) のために開けた箱に (B) を入れない。

| | (A) プロバイダの API キー | (B) エージェントの資格情報 |
|---|---|---|
| 例 | OpenAI 互換エンドポイントの鍵、クラウド LLM API key | Claude Code / Codex / その他エージェントのログイン状態・トークン |
| 誰が呼ぶか | **サーバ**が HTTP を出す | エージェント本体（端末側 Runner / CLI）が出す |
| サーバが値を持つ必要 | **ある**（サーバが呼ぶので避けられない） | **無い**（端末側のログインで足りる） |
| 既存設計 | 本書で新規に定義（DB 暗号化保管） | `HYBRID_AGENT_ADAPTER_DESIGN.md` §4.2 Option 1 = 端末側保持 |
| 本書の扱い | §2, §4, §5, §6 で保管・防護・検査を設計する | §3 で端末側維持を明記する。サーバ保管しない |

### 1.1 (A) プロバイダの API キー — 出さない場所の一覧

(A) の**平文値**および**復号後の値**は、次の場所に出してはならない。許可されるのは「鍵の持ち主である利用者の要求を処理する復号経路」内部の一時的な使用と、§2.3 の暗号文としての DB 保管のみ。

| 場所 | 禁止する内容 | 許可する内容 |
|---|---|---|
| API 応答 | 平文値、復号後の値、暗号文、暗号文列名（`secret_ciphertext` 等）、KEK、復号エラーに含まれる値断片 | presence metadata のみ（登録有無、最終確認時刻、key version、状態）。値の有無だけを返す既存方針を維持する |
| 監査 | 平文値、暗号文、暗号文列名（`secret_ciphertext` 等）、KEK、復号後の値 | actor/user ID、owner user ID、provider/adapter 識別子、操作種別、成否/理由カテゴリ、時刻、相関 ID |
| ログ | 平文値、暗号文、暗号文列名（`secret_ciphertext` 等）、KEK、復号後の値、接続文字列に埋め込まれた鍵 | 操作名、理由カテゴリ、相関 ID、非秘密の件数 |
| 画面 | 平文値、復号後の値、暗号文、暗号文列名（`secret_ciphertext` 等） | マスク不要の「未登録 / 登録済み」表示、登録・更新・失効の操作結果。入力フォームは送信後に値を保持しない |
| 例外メッセージ / スタックトレース | 平文値、暗号文、暗号文列名（`secret_ciphertext` 等）、KEK、DB 行の生ダンプ | 固定のエラーカテゴリ（例: `credential_not_found`, `credential_access_denied`, `credential_decrypt_failed`） |
| job input / receipt / model context | 平文値、暗号文、暗号文列名（`secret_ciphertext` 等）、KEK | provider 選択に必要な非秘密 metadata（provider ID、credential record ID、存在可否） |
| リポジトリ / 設定ファイル | KEK、平文値、`.env` に実値を書くこと | KEK の**名前**（環境変数名）と設定説明のみ。実値はコミットしない |

### 1.2 (B) エージェントの資格情報 — 出さない場所の一覧

(B) はサーバが預からない。したがってサーバ側のどの保管場所にも値を置かない。

| 場所 | 禁止する内容 | 許可する内容 |
|---|---|---|
| サーバ DB（`adapter_credentials` を含む全テーブル） | Claude/Codex ログイン値、OAuth token、refresh token、session cookie、CLI auth file 内容、API key | presence metadata のみ（`enrolled/absent/revoked`, `checked_at`）。既存 `adapter_credentials` schema を維持する |
| API 応答 | 上記すべて | presence metadata のみ |
| 監査 | 上記すべて | adapter/runner/workspace/policy の非秘密 metadata、判定結果、理由カテゴリ |
| ログ | 上記すべて | 非秘密の操作名・理由カテゴリ・相関 ID |
| 画面 | 上記すべて | 「接続済み / 未接続 / 失効」等の presence 表示 |
| 例外メッセージ | 上記すべて | 固定のエラーカテゴリ |
| job input / receipt / model context | 上記すべて | adapter/model 選択 metadata、binding/policy の非秘密参照 |

## 2. (A) プロバイダの API キーの保管方式

保管先はオーナー決定により **DB（暗号化して保存）**。本節は「どう守るか」を設計する。

### 2.1 新テーブル（`adapter_credentials` には足さない）

(A) の暗号文は **新しい専用テーブル**に置く。既存 `adapter_credentials`（`registry.py:154-160`、`runner_instance_id, adapter_id, state, checked_at`）は presence-only のまま変更しない。

提案テーブル名: `user_provider_credentials`（実装時の最終名は既存命名規約に合わせてよいが、`adapter_credentials` とは別であること）。

| 列 | 型（論理） | 意味 | 値/非値 |
|---|---|---|---|
| `id` | TEXT PK | credential record ID | 非秘密 |
| `owner_user_id` | TEXT NOT NULL | 鍵の持ち主の利用者 ID。復号の認可はこの値に束縛する | 非秘密 |
| `provider_id` | TEXT NOT NULL | 対象 provider / 接続先識別子 | 非秘密 |
| `display_label` | TEXT | 利用者が識別するための表示名 | 非秘密（平文値を入れない） |
| `secret_ciphertext` | BLOB/TEXT NOT NULL | AEAD で暗号化した暗号文。**名前から値でないことが分かる**。平文を入れない | 暗号文（DB 内では保護されるが、KEK 漏えい時は復号されうる） |
| `cipher_alg` | TEXT NOT NULL | 暗号アルゴリズム識別子（例: `aes-256-gcm`） | 非秘密 |
| `kek_version` | INTEGER NOT NULL | 暗号化に使った KEK の版 | 非秘密 |
| `nonce` | BLOB/TEXT NOT NULL | AEAD nonce/IV。再利用禁止 | 非秘密（ただし値ではない） |
| `aad_scope` | TEXT NOT NULL | AAD に含めたスコープ識別子（`owner_user_id`, `provider_id`, record ID 等の固定形式） | 非秘密 |
| `state` | TEXT NOT NULL | **固定値ドメイン**（`CHECK(state IN ('active','revoked','deleted_pending'))`）で固定するライフサイクル状態。`enrolled` / `absent` / `revoked`（presence-only 語彙）との対応付けは **vocabulary mapping decision** として明示的に下ろすまで、本設計では暗黙に対応付けを行わない | 非秘密 |
| `created_at` | REAL/TIMESTAMP NOT NULL | 作成時刻 | 非秘密 |
| `updated_at` | REAL/TIMESTAMP NOT NULL | 更新時刻 | 非秘密 |
| `revoked_at` | REAL/TIMESTAMP NULL | 失効時刻 | 非秘密 |
| `last_used_at` | REAL/TIMESTAMP NULL | サーバが復号して使用した最終時刻（任意、記録するなら非秘密） | 非秘密 |

明示的に**作らない列**: `secret`, `secret_value`, `api_key`, `plaintext`, `token`, `password`, `credential`, `value`, `material` 等、平文値を入れられる名前/意味の列（`secret_ciphertext` 以外の禁止 marker を含む列も作らない）。将来の migration でも、厳密な許可列集合（exact column set）照合と禁止 marker 検査の二段の起動時ガードで強制する（§5a）。

### 2.2 暗号鍵（KEK）の置き場

KEK は **DB の外**に置く。DB の中に置くことは不可（決定 2 の導出: DB を読める者が復号できては「管理者でも他人の値は読めない」が無効になる）。

| 選択肢 | 採否 | 理由 |
|---|---|---|
| **サーバ起動時に注入される環境変数 / secret manager からの環境変数注入** | **採用** | DB と分離でき、Windows/Linux/コンテナのデプロイ境界で一貫して運用しやすい。secret manager（クラウド/オンプレの vault 製品）を使う場合も、アプリプロセスへは起動時環境変数注入として渡し、アプリは注入元の製品 API に依存しない設計にできる。アクセスはプロセス起動権限とデプロイ設定に限定できる。 |
| OS の資格情報ストア（Windows Credential Manager / macOS Keychain / Linux secret service 等） | **不採用** | ホスト統合は強いが、OS・デスクトップセッション有無・ヘッドレス実行・コンテナ環境で挙動差と API 差が大きい。Locus は LAN 配備・FastAPI サーバとして複数 OS（Windows 開発機・Linux CI/本番・コンテナ）で動きうるため、既定設計を OS 資格情報ストア依存にすると運用分岐・ヘッドレス解錠課題・検証面が増えるため採らない。 |

KEK 運用ルール:

- KEK 実値を**リポジトリに置かない**。`.env` 等をリポジトリに置かない（コミットしない）。サンプル設定、テスト fixture、ドキュメント、コミットメッセージにも実値を書かない。
- `.env.example` 等に書く場合も変数名と説明のみとし、実値は禁止する。
- KEK はアプリが通常の API 応答・監査・ログ・例外に出さない。設定診断は「設定済み / 未設定」の presence のみ。
- KEK は少なくとも 256-bit 相当の強度を持つランダム値とし、平文パスワード文字列をそのまま KEK にしない（必要なら KDF を別設計で定めるが、KDF パラメータや salt も秘密扱いの混同を避ける）。

### 2.3 保存時暗号化

- アルゴリズムは AEAD（例: AES-256-GCM）を第一候補とする。実装時に具体ライブラリ/プリミティブを固定するが、本設計では「認証付き暗号であること」「nonce 再利用禁止」「AAD を使うこと」を要件とする。
- AAD には少なくとも `owner_user_id`, `provider_id`, record ID（または同等の不変スコープ）を含める。これにより、暗号文を別利用者/別 provider レコードへ差し替える攻撃を検知できる。
- 暗号化はサーバ内の復号経路と対になる 1 箇所の暗号化経路に集約する（§5b の一点化方針と対称）。
- DB に保存されるのは `secret_ciphertext`, `nonce`, `cipher_alg`, `kek_version`, `aad_scope` 等の暗号化 metadata のみ。平文値は DB に書かない。

### 2.4 鍵の交換（rotation）

- KEK は `kek_version` で版管理する。既存の暗号文レコードはそれぞれ自分を暗号化した `kek_version` を保持するため、新 KEK 追加直後も旧 KEK が環境に残っている間はそのまま復号可能であり、即座に読めなくなることはない。
- rotation 手順（設計）:
  1. 新 KEK（version N+1）をデプロイ環境に追加する。旧 KEK（version N）も既存暗号文の復号のため一時的に併存させる。
  2. 新規書き込み・更新はすべて version N+1 で暗号化し、`kek_version = N+1` を記録する。
  3. 既存の暗号文レコード（`kek_version = N`）は、バックグラウンド再暗号化ジョブまたは次回更新時に「旧 KEK（N）で復号 → 新しい `nonce` を生成して新 KEK（N+1）で再暗号化 → `secret_ciphertext`, `nonce`, `kek_version = N+1`, `updated_at` を更新」を 1 トランザクション境界で実行する。
  4. 全アクティブレコードが `kek_version = N+1` へ移行し、検査で `kek_version = N` のアクティブ行が 0 件であることを確認した後、旧 KEK（N）をデプロイ環境から削除する。
- rotation 中の失敗は fail-closed: 再暗号化できないレコードを平文化したり黙ってスキップして完了扱いしたりしない。旧 KEK が削除された後に旧版の暗号文が残っていた場合は復号失敗（固定エラーカテゴリ）となり、平文フォールバックはしない。
- KEK 漏えいが疑われる場合は、鍵交換だけでなく当該 KEK で保護されていた provider API key 自体の provider 側失効・再発行を利用者/運用手順に要求する（DB 上の再暗号化は既に流出した KEK と暗号文の組からの復号を止められないため）。

### 2.5 失効（利用者の削除、鍵の無効化）

| 事象 | 設計 |
|---|---|
| 利用者が鍵を無効化 | `state='revoked'`, `revoked_at` を記録し、同一トランザクションまたは即時処理で不要になった暗号文の利用を遮断する（復号経路は `state == 'active'` 以外を拒否して値を返さない。物理削除または空バイト化を行う場合も通常経路からの即時利用不能を先に保証する）。 |
| 利用者が削除された | 当該 `owner_user_id` に紐づく `user_provider_credentials` 行をカスケード削除または即座に `state='revoked'` 化して暗号文を消去対象にする。削除/失効処理は監査可能な非秘密 metadata のみ残し、平文値も暗号文もログに出さない。 |
| provider 側で鍵が無効化された | 外部呼び出し失敗（401/403 相当）や利用者の明示操作により `state='revoked'` へ更新できる設計にする。サーバは失効状態の鍵を復号・送信に使わない。 |
| KEK が失われた | 既存の暗号文は復号不能になる。これは可用性の喪失であり、平文漏えい防止を優先する（fail-closed）。復旧は利用者による鍵の再登録で行う。KEK バックアップはデプロイ責任だが、バックアップも DB 外の秘密として扱う。 |

### 2.6 読めるのは誰か

- **復号できる主体**: **鍵の持ち主である利用者の要求を処理する、サーバ内の認可済み経路だけ**（`requester_user_id == owner_user_id` が成立する実行経路のみ）。
- **復号できない主体**: 他の一般利用者、**`system_admin` を含むすべての管理者**、組織管理者/委任管理者、監査閲覧者、サポート UI、一般的な DB 読み取りクエリ、ログ閲覧者。
- `system_admin` は利用者管理・ポリシー管理・システム運用の権限を持っても、**他人の provider API key の平文値を復号・取得する権限は持たない**（決定 3）。管理・運用に必要な情報は presence metadata（登録有無、状態、最終更新時刻、`kek_version`）のみで提供する。
- 所有者本人であっても、API 応答や画面に平文値を再表示する経路は作らない。更新時は「新しい値を上書き登録する」操作のみを提供する。

### 2.7 主張の範囲（正直に書く）

`docs/architecture/DOCUMENT_EXTRACTION_BOUNDARY.md` §5 の作法に従い、守れる保証と守れない保証を明確に分ける。**弱い方の保証しか主張しない。守れない保証を「守れる」と書かない。**

| 保証 | アプリ経路 / 通常の DB 読み取り | サーバのホストに root 相当で入れる者（OS 管理者 / コンテナホスト root / プロセス・メモリ・環境変数読取可） |
|---|---|---|
| API 応答・監査・ログ・画面・例外に平文値や暗号文が出ない | ○（§5 の機械検査で固定） | × プロセスやバイナリを改変・アタッチできれば任意の出力経路を作られうる |
| `system_admin` でも他人の鍵の値をアプリ経路で読めない | ○（§5b/§5c の機械検査で固定） | × ホスト root 相当は認可コードを迂回・改変できる |
| DB の行を読み取っただけでは平文値が分からない | ○（DB には暗号文のみ保存し、KEK は DB 外に置くため） | × ホスト root 相当はサーバ環境変数やプロセスメモリから KEK ごと取得して DB の暗号文を復号できる |
| KEK が DB の中に無い | ○ | × DB 外（環境変数）にあっても、ホスト root 相当からは読める |
| リポジトリ漏えいだけで鍵が漏れない | ○（KEK 実値・`.env`・平文鍵をリポジトリに置かない） | - |

この設計が**守れる範囲と守れない範囲の結論**:

- **守れるのはアプリ経路と DB 読み取りに対してである。** アプリ上の `system_admin` 権限者や、DB ファイル / DB ダンプだけを読める者は、KEK を持たず復号経路の所有者検査も通過できないため、他人の平文値を読めない。
- **サーバのホストに root 相当で入れる者には効かない。** ホストの root / Administrator、ハイパーバイザ/クラウド基盤管理者、サーバプロセスの環境変数やメモリダンプを読める者は、KEK と DB 内の暗号文の両方を取得して復号できるため、そこまでは守れない。
- 暗号化して DB に置くことをもって「誰に対しても絶対に漏れない」とは主張しない。また、HSM による非輸出鍵保証や監査ログ改竄耐性（`T-T4`）は本書の保証範囲に含めない。

### 2.8 オーナー決定の適用範囲と、既存設計境界との decision delta

本書は 2026-11-22 のオーナー決定を前提に (A) の DB 保存設計（§2.1–§2.7）を組み立てた design-only の文書である。
本決定が、既存設計と食い違う点（「プロバイダ資格情報の Locus 側へのコピーは禁止」という
`docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md` §1.2 boundary 1 / §4.4、同 design §4.4 の
「Locus-side credential vault」Rejected、同 design §3、docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md §2.4
「No Locus-side copy」、docs/security/HYBRID_AGENT_THREAT_MODEL.md T-I3、必須要件
docs/plans/locus-hybrid-agent-requirements.md Must 5「認証情報を原則として利用者の端末に保持」）との間にある
**decision delta** を、ここでは明示する。設計ゲート資料として本書が実装を承認するものではない（§7）。

- **decision delta**: オーナー決定（2026-11-22、T-AIC-006 本票のオーナー決定）は、
  **(A) プロバイダの API キー** の保存姿勢を「Locus 側に持たない」から「DB に暗号化して保持する」へ移す
  設計判断を行った。supersede の対象は **平文 credential bytes の Locus 側保管の禁止** の範囲内であり、
  (A) の AEAD 暗号文 DB 保管は別の扱いとして設計されている（§2.1–§2.7）。この design が上書きを承認するのは
  **設計**であり、実装承認ではない。
- **supersede の適用範囲**: **(A) プロバイダ API キー** は owner decision 2026-11-22 により §2.1–§2.7 の
  DB 暗号化保管設計が採用された。**(B) エージェント資格情報** は supersede しない（§3 端末側保持を維持）。
- **HBR-005 / Must #5 との関係**: 既定では「認証情報は利用者端末に保持」(Must 5) である。オーナー決定は
  その**保存先に関する設計判断**を 2026-11-22 に更新したものであり、必須要件 ID（`HBR-005`）そのものを
  削除・弱めたものではない（決定と提案の分離、GOV-005）。owner decision が旧「No Locus-side copy」境界を
  上書きしたのは (A) のサーバー側保管の設計のみである。
- **矛盾を解消したつもりにしない**: §2.7 の主張の範囲（アプリ経路と DB 読み取りに対する暗号化、
  ホスト root 相当の弱い保証）は decision delta の上で維持される。旧境界を「解除」したのではなく、
  owner の明示的決定により (A) の保管方式を設計として更新したに過ぎない。

## 3. (B) エージェントの資格情報は端末側のまま

決定 1: **(B) は端末側のまま**とする。サーバは利用者の Claude Code / Codex 等のログインを預からない。

### 3.1 `HYBRID_AGENT_ADAPTER_DESIGN.md` §4.2 Option 1 を維持する理由

- `docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md` §4.2 Option 1（CLI ネイティブログイン・端末側保持）では、エージェント CLI / SDK は利用者端末（または専用 Runner プロファイル）側の公式認証ストアを直接使い、Locus サーバは資格情報のバイト列に一切触れない。
- エージェント通信はエージェント本体が直接出すため、サーバが HTTP リクエストを組み立てる (A) とは異なり、サーバがログイン トークンやセッション秘密を持つ技術的必然性が無い。
- もしサーバが利用者の Claude / Codex ログインを預かると、サブスクリプション規約・端末束縛トークンの扱い・サーバ侵害時の影響半径・資格情報転送経路のすべてで不要なリスクを背負う。Option 1 を維持すれば、Locus サーバからは漏えいしようがない（持たないものは漏れない）。
- よって `adapter_credentials` テーブル（`registry.py:154-160`）は `(runner_instance_id, adapter_id, state, checked_at)` の presence metadata のみを維持し、サーバへ (B) の資格情報値を送る経路は設けない。

### 3.2 それでもオーナーの要望（チャット画面のモデル管理から選べる）が成立する理由

オーナーの要望は「チャット画面で接続した利用者が、モデル管理の部分で選択できること」であり、**選択 UI に必要なのは資格情報の値ではなく metadata である**。

| UX 要素 | サーバが持つもの（metadata のみ） | サーバが持たないもの（端末側に留まる） |
|---|---|---|
| モデル管理・チャット画面での選択肢表示 | `agent_adapters` カタログ、`workspace_adapter_bindings`、ポリシーの `adapter_allowlist`、presence 状態（`enrolled` / `absent` / `revoked`） | ログイン値、OAuth/refresh token、API key |
| 接続済みかどうかの表示 | `adapter_credentials.state` と `checked_at`、非秘密のヘルス状態（`adapter_health`） | CLI auth file（`~/.claude/` や `~/.codex/` 等）の中身、セッション秘密 |
| 利用者・ワークスペースごとの選択状態 | 利用者/workspace と許可済み adapter/model ID の紐づけ metadata | 他人の資格情報値 |
| 実際のエージェント実行（将来 B6 解除後） | 認可済み job envelope / metadata のみ | 端末側 Runner / エージェント本体が自身の保持するログイン状態で実行する |

したがって、(B) を端末側に置いたままでも、チャット画面のモデル管理から選んで使う UX は完全に成立する。

### 3.3 (A) の箱に (B) を入れない

- 新テーブル `user_provider_credentials`（§2.1）は **(A) プロバイダの API キー専用**とする。Claude Code / Codex のログイン トークン、OAuth 資格情報、CLI 設定ファイル断片をここに入れてはならない。
- (B) の有無管理は既存の `adapter_credentials`（presence-only）だけを使い続ける。(A) と (B) を 1 つのテーブルや共通 DTO に混ぜると、(A) の復号経路という「値を読む穴」から (B) が漏れる構造になるため、スキーマ・型・サービス層のすべてで分離する。

## 4. `credential_schema_is_presence_only` の扱い

### 4.1 結論: そのまま維持する（推奨案を採用）

既存の `credential_schema_is_presence_only()` は**一切弱めず、そのまま維持する**。

- `backend/app/agents/registry.py:53-56` の `credential_schema_is_presence_only(connection)` は、`adapter_credentials` の列集合が `CREDENTIAL_COLUMNS = frozenset({"runner_instance_id", "adapter_id", "state", "checked_at"})` と完全一致することを検証する。
- `backend/app/agents/registry.py:186-187` は `AgentRegistry.__init__` 内でこれを呼び、偽であれば `RuntimeError("adapter_credentials schema is not presence-only")` を送出して**起動を止める**。
- (A) を別テーブル `user_provider_credentials` に分離することで、`adapter_credentials` には 1 列も追加しない。これにより、`credential_schema_is_presence_only()` と `tests/test_agents_registry.py`（`test_adapter_credentials_schema_is_presence_only_and_rejects_secret_columns` 等）を無変更で PASS させ続けられる。

### 4.2 理由（同じテーブルに足す案を採らない理由）

- もし `adapter_credentials` に暗号文列を足すと、`credential_schema_is_presence_only()` を外すか書き換えることになり、(B) エージェント資格情報に対して「サーバは値も暗号文も一切持たない」という機械的不変条件が失われる。
- 仮に外すなら代替として「許可された暗号文列のみを認め、(B) の行では暗号文列を `NULL` 強制する CHECK 制約＋新スキーマ起動時ガード」で守る必要が生じるが、(A) と (B) で主キー粒度も異なる（(A) は `owner_user_id` 単位、(B) は `runner_instance_id` × `adapter_id` 単位）ため、1 テーブルに混ぜる利点が無く事故面だけが増える。
- よって既存テーブルには手を触れず、`credential_schema_is_presence_only()` を維持し、新テーブルには同型の専用起動時ガード（§5a）を追加する。

## 5. 「バグっても破れない」仕組み（機械が落とす 4 つの設計）

決定 3 に従い、コーディング規約や人手レビュー頼みではなく、**違反したら機械が即座に落とす**形で次の a〜d を設計する（実装は後続票）。

### 5a. 起動時ガード（新テーブルの平文列禁止）

| 項目 | 設計内容 |
|---|---|
| **対象** | 新テーブル `user_provider_credentials`（§2.1）の DB スキーマ |
| **仕組み** | `registry.py:53-56, 186-187` の `credential_schema_is_presence_only()` を先例とし、**同じ語彙・同じ失敗方式**で関数 `provider_credential_schema_is_ciphertext_only(connection: sqlite3.Connection) -> bool`（仮称）を実装する。`PRAGMA table_xinfo(user_provider_credentials)` で実列集合を取得し、(1) 事前定義した `PROVIDER_CREDENTIAL_COLUMNS`（`frozenset`、暗号文列は `secret_ciphertext` のみで平文列を含まない）と完全一致すること、かつ (2) `secret_ciphertext` 以外のいかなる列名にも禁止 marker（`"token"`, `"secret"`, `"password"`, `"credential"`, `"value"`, `"material"`, `"api_key"`, `"plaintext"`, `"raw"`）が含まれないこと、および `state` 列の CHECK 制約値が §2.1 で固定した値ドメイン `('active','revoked','deleted_pending')` と一致すること、の **3 点照合**を行う。ストア初期化時に偽なら `raise RuntimeError("user_provider_credentials schema is not ciphertext-only")` で**起動を止める**。警告ログで続行しない。新しい流儀を作らない。値を固定した以上、既存 presence-only 語彙（`enrolled` / `absent` / `revoked`）との対応付けは暗黙に決めず、**vocabulary mapping decision**（既存語彙との対応付けの明示的決定）を下ろすまで、この新状態ドメインを導入しない。 |
| **何をしたら落ちるか（合否条件）** | **FAIL（落ちる条件）**: マイグレーションや `ALTER TABLE` 等で `api_key`, `secret_value`, `plaintext`, `raw_token` などの平文値用列や未許可列を 1 列でも追加する、またはテーブルが空（未作成）のまま検査を呼ぶと、ガード関数が `False` を返し、初期化処理が `RuntimeError` を送出してアプリ起動自体が失敗する（もし `RuntimeError` が送出されずに起動続行したらテスト FAIL）。<br>**FAIL（追加条件）**: §2.1 で固定した `state` の CHECK 値ドメイン（`('active','revoked','deleted_pending')`）と異なる場合（新状態語彙の追加、`CHECK` 制約の緩和、自由文字列化など）もガードは `False` を返し、初期化が `RuntimeError` で起動を止める。<br>**PASS（合格条件）**: 列集合が許可された暗号化・非秘密列集合と完全一致し、`state` の CHECK 値ドメインも固定ドメインと一致しているときのみ `True` を返し、正常に起動する。 |

### 5b. 復号経路の一点化

| 項目 | 設計内容 |
|---|---|
| **対象** | `user_provider_credentials.secret_ciphertext` を復号して平文 API キーを取り出す全コード経路 |
| **仕組み** | 復号処理を行う関数を専用モジュール内の **ただ 1 つの関数**（例: `decrypt_user_provider_credential(connection, *, requester_user_id: str, credential_id: str) -> str`）に限定する。`requester_user_id` はデフォルト値を持たない必須引数とし、空文字や `None` や省略を許さない。関数内部でレコードの `owner_user_id` と `state == 'active'` を引き、`requester_user_id != row["owner_user_id"]` の場合は**無条件に認可例外（拒否）を送出**し、AEAD 復号処理自体を呼ばない（`is_admin` / `system_admin` フラグは引数にも分岐にも一切受け取らない）。さらに AST 静的検査テスト（`tests/test_agents_registry.py:352-381` の AST 境界テストと同方式）で、当該一点化関数以外のモジュールが AEAD 復号プリミティブや `secret_ciphertext` 列の SELECT を行っていないことを機械検査する。 |
| **何をしたら落ちるか（合否条件）** | **FAIL（落ちる条件）**: (1) `requester_user_id` を省略または `None` / 空文字で呼ぶと `TypeError` または認可例外で落ちる（引数省略可能なデフォルト値を関数シグネチャに足したらシグネチャ検査テストが FAIL）。(2) `requester_user_id != owner_user_id`（他人の ID）で呼ぶと認可例外が送出されて復号値は返らない（値が返ったらテスト FAIL）。(3) 一点化関数の外に 2 つ目の復号呼び出しや `secret_ciphertext` の直接読み出しを書くと AST 静的検査テストが FAIL する。<br>**PASS（合格条件）**: 復号関数がコードベース内で 1 箇所のみであり、`requester_user_id == owner_user_id` かつ `state == 'active'` のときのみ復号が成功し、それ以外はすべて例外で拒否される。 |

### 5c. 管理者でも読めないことの検査

| 項目 | 設計内容 |
|---|---|
| **対象** | `system_admin` を持つ主体による他人の (A) 資格情報の取得・復号・利用試行、および既存 `registry.py` の `system_admin` 分岐との境界 |
| **仕組み** | アプリ認可において、管理権限（`actor.system_admin == True`）と資格情報復号権限（`actor.id == owner_user_id`）を完全に切り離す。`backend/app/agents/registry.py:275`（`_admin`）および `registry.py:725`（`dispatch_attempt`）には既存の `if not actor.system_admin:` 分岐があるが、`registry.py` は Plane-R の metadata-only ストアであり `user_provider_credentials` を import も参照もしない境界を維持する。新設する資格情報管理 API / ハーネス経路でも、`system_admin` によるバイパス分岐（`if actor.system_admin: allow`）を設けないことを回帰テストで固定する。 |
| **何をしたら落ちるか（合否条件）** | **FAIL（落ちる条件）**: 利用者 `alice` が登録した鍵に対し、`system_admin=True` を持つ管理者 `admin` のトークン／主体 ID で (1) 復号一点化関数、(2) 外部モデル呼び出し経路（他人の `credential_id` 指定）、(3) 管理・一覧・詳細 API のいずれかを呼んだとき、例外／403（または 404）で拒否されずに HTTP 200 で値や暗号文が返る、または外部送信に使えてしまう、あるいは `registry.py:275, 725` 経由で `user_provider_credentials` にアクセスできる穴が開いた場合、テストが即座に FAIL する。<br>**PASS（合格条件）**: `system_admin` 主体による他人の鍵の復号・利用・値取得がすべて拒否（403/認可例外、監査に `denied` 記録）され、管理 API 応答にも presence metadata 以外は一切含まれない。 |

### 5d. 漏れの検査

| 項目 | 設計内容 |
|---|---|
| **対象** | API 応答（正常系・異常系 JSON）、`audit` テーブルのレコード、アプリログ出力（`caplog`）、送出される例外文字列（`str(exc)` / `repr(exc)`） |
| **仕組み** | `scripts/secret_scan.py` の許可済み合成フィクスチャ（`sk-synthetic-01-not-a-real-key`）をテスト用の API キーとして登録し、登録・一覧取得・本人利用・他人/`system_admin` による拒否・復号失敗（不正 nonce / 不正 KEK）・DB エラー・失効の各経路を一通り実行した上で、全 HTTP レスポンス本文、全 `audit` 行の全列、全ログレコード文字列、捕捉した例外メッセージ文字列を走査し、(1) 平文値 `sk-synthetic-01-not-a-real-key`、(2) 暗号文の列名文字列 `"secret_ciphertext"`、(3) DB に保存された実際の暗号文バイト列／エンコード文字列（hex / base64）がいずれも **0 件**であることを assert する。 |
| **何をしたら落ちるか（合否条件）** | **FAIL（落ちる条件）**: API 応答の JSON キーや値、監査ログの `target_id` / 詳細、ロガー出力、または `HTTPException.detail` や内部例外メッセージのどこかに、合成キー平文値、列名 `"secret_ciphertext"`、または暗号文の実値断片が 1 箇所でも現れたら assert が落ちてテスト FAIL となる（例: `SELECT *` の辞書をそのまま API 応答やログに出すバグや、復号エラーに暗号文を埋め込むバグで確実に落ちる）。<br>**PASS（合格条件）**: 全検査対象の出力において、平文値・`"secret_ciphertext"` 列名・暗号文実値の出現数がすべて 0 件である。 |

## 6. 追加の検証項目（合否条件つき、mock・合成データのみ）

実物の API キー、実プロバイダ通信、実ユーザーデータは一切使用しない。合成キーには `scripts/secret_scan.py` の `SYNTHETIC` に登録済みの `sk-synthetic-01-not-a-real-key` 〜 `sk-synthetic-04-not-a-real-key` のみを用い、KEK にはテスト実行時にランダム生成したインメモリバイト列（リポジトリにリテラルを書かない）を用いる。

### 6.1 正検証（Positive Tests）

| ID | 検証項目 | 手順（mock / 合成データのみ） | 合否条件（PASS / FAIL） |
|---|---|---|---|
| VT-1 | (A) 暗号化保存と presence 応答 | 利用者 `alice` で合成キー `sk-synthetic-01-not-a-real-key` を登録し、API 応答と DB の `user_provider_credentials` 行を検査する。 | **PASS**: API 応答は presence metadata（`id`, `provider_id`, `state='active'`, 時刻等）のみで平文・暗号文を含まず、DB の `secret_ciphertext` は平文と異なり AEAD タグ検証が通る。**FAIL**: 平文保存されるか API に値・暗号文が出る。 |
| VT-2 | 所有者本人の復号成功 | `requester_user_id == alice.id` で一点化復号関数を呼び出す。 | **PASS**: 元の合成キー文字列が内部呼び出し元に返り、監査に非秘密の利用記録が残る。**FAIL**: 本人なのに拒否されるか、ログ・監査に値が出る。 |
| VT-3 | KEK ローテーション（N → N+1） | 版 1 の一時 KEK で暗号化保存後、版 1 と版 2 の KEK を両方注入して再暗号化処理を実行し、その後版 1 の KEK を外して版 2 のみで復号する。 | **PASS**: 再暗号化前（版 1+2 併存中）も再暗号化後（版 2 のみ）も `alice` 本人経路で復号でき、DB の `kek_version` が `2` になり `nonce` が新しくなっている。**FAIL**: 再暗号化後に版 1 KEK 無しで読めない、または同じ `nonce` が再利用される。 |
| VT-4 | 鍵の失効と利用者削除時の無効化 | `alice` が鍵を失効させるケースと、別利用者 `bob` 削除時のクリーンアップケースを実行し、その後に本人 ID で復号関数を呼ぶ。 | **PASS**: いずれも `state='revoked'` または行削除となり、本人 ID でも復号関数が例外で拒否する。**FAIL**: 失効・利用者削除後に復号値が返る。 |
| VT-5 | (B) presence-only と既存回帰の維持 | `tests/test_agents_registry.py` を実行し、`adapter_credentials` スキーマ・Plane-R import 境界・B6 409 拒否を検査する。 | **PASS**: `credential_schema_is_presence_only()` が `True` であり、`tests/test_agents_registry.py` の全テストが PASS する。**FAIL**: 既存テストが 1 件でも失敗する。 |

### 6.2 負検証（Negative Tests）

| ID | 検証項目 | 手順（mock / 合成データのみ） | 合否条件（PASS / FAIL） |
|---|---|---|---|
| NV-1 | AAD 差し替え（レコード間コピー）検知 | `alice` の暗号文レコードの `secret_ciphertext` と `nonce` を、SQL で直接 `bob` の行（`owner_user_id = bob.id`）へコピーし、`bob` として復号を試みる。 | **PASS**: AAD（`owner_user_id` 等を含む）不一致により AEAD 認証タグ検証が失敗し、固定エラーカテゴリの例外で拒否され平文は一切得られない。**FAIL**: コピーした暗号文が `bob` として復号できてしまう。 |
| NV-2 | KEK 未設定・不正形式時の fail-closed | KEK 環境変数が未設定または長さ不足の状態で、(A) の登録および復号を試行する。 | **PASS**: 平文保存や空鍵暗号化へフォールバックせず、明示的な設定エラーで即座に拒否され、DB に行が作られない。**FAIL**: 平文や固定既定鍵で保存・続行してしまう。 |
| NV-3 | nonce 再利用禁止の検証 | 同一利用者・同一プロバイダ・同一合成キーで 2 回登録／更新を行い、保存された `nonce` と `secret_ciphertext` を比較する。 | **PASS**: 2 回の `nonce` と `secret_ciphertext` がいずれも異なる（暗号論的乱数による毎回新規生成）。**FAIL**: 同一 `nonce` または同一暗号文が生成される。 |
| NV-4 | (A) と (B) の混在拒否 | (A) 登録 API にエージェント CLI 種別（`claude-code` 等の runner adapter 用種別）を渡す、または `adapter_credentials` に値列を追加する操作を試みる。 | **PASS**: 前者はバリデーション（422）で拒否され、後者は `credential_schema_is_presence_only()` が `False` となり起動停止する。**FAIL**: いずれかが通ってしまう。 |
| NV-5 | 監査失敗時のロールバック | `test_audit_failure_rolls_back_registry_mutation` と同様に、監査関数が例外を送出する stub を注入して鍵登録・失効を呼ぶ。 | **PASS**: トランザクションがロールバックされ、`user_provider_credentials` に未監査の変更が残らない。**FAIL**: 監査記録なしに鍵の登録や変更がコミットされる。 |

## 7. 非目標 / 本書が承認しないこと

- 本票でのプロダクトコード、DB スキーマ、マイグレーション、API、テストの変更（本票は設計のみ）。
- `adapter_credentials` の変更、`credential_schema_is_presence_only()` の緩和、B6 dispatch 409 拒否の解除。
- (B) エージェントの資格情報（Claude Code / Codex 等のログイン）のサーバ側保管・転送・供給。
- 実プロバイダへの外部通信および実資格情報の使用。
- サーバのホストに root 相当で入れる攻撃者に対する秘密保護の主張、および監査ログ改竄耐性（`T-T4`）の代替。

## 8. 受入条件との対応表

| 受入条件 | 本書の該当箇所 |
|---|---|
| 1. (A) と (B) の扱いが別々に書かれ、どちらも「出さない場所の一覧」を持っている。(B) は端末側のまま | §1, §1.1, §1.2, §3（§3.1〜§3.3） |
| 2. (A) は DB の新テーブル・保存時暗号化で、KEK は DB の外に置く設計。採った置き場と採らなかった方の理由 | §2.1, §2.2, §2.3（rotation §2.4、失効 §2.5、読める主体 §2.6 も明記） |
| 3. `credential_schema_is_presence_only` を維持する設計（および同テーブル案を採らない理由と代替条件） | §4（§4.1, §4.2） |
| 4. 「管理者でも他人の値は読めない」を機械が守る形で a〜d の 4 つが「何をしたら落ちるか」つきで書かれ、起動時ガードは既存と同じ失敗方式（`RuntimeError` で起動停止） | §5（§5a, §5b, §5c, §5d） |
| 5. 主張の範囲が正直：アプリ経路と DB 読み取りに限られ、ホストに root 相当で入れる者には効かないことが書かれ、守れない保証を主張していない | §2.7 |
| 6. 検証項目に合否条件が付いている（mock・合成データのみ） | §5a〜§5d, §6（§6.1 VT-1〜VT-5, §6.2 NV-1〜NV-5） |
| 7. コード・スキーマ・dispatch の挙動を一切変更していない（`tests/test_agents_registry.py` PASS） | §7、および実行検証（TEST 欄） |
| 8. 変更が許可パス内に収まっている（`progress/phase-ai-connect/material/` のみ） | `progress/phase-ai-connect/material/USER_CREDENTIAL_DESIGN.md` のみ |
