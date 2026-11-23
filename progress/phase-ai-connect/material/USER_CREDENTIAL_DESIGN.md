# 利用者ごとの資格情報をサーバで持つための設計（設計のみ）

- 状態: **設計ゲート資料（実装なし）**。本書は (A) プロバイダの API キーの保管方式、(B) エージェントの資格情報の境界、機械的ガード、および検証項目を定める。`adapter_credentials` の schema、registry API、dispatch、テスト、資格情報の実読取/実転送/実供給、外部通信、B6 dispatch の解除は承認しない。
- 対象タスク: `progress/phase-ai-connect/tasks/T-AIC-006.md`（`HBR` 必須要件 4）。
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
| API 応答 | 平文値、復号後の値、暗号文、KEK、復号エラーに含まれる値断片 | presence metadata のみ（登録有無、最終確認時刻、key version、状態）。値の有無だけを返す既存方針を維持する |
| 監査 | 平文値、暗号文、KEK、復号後の値 | actor/user ID、owner user ID、provider/adapter 識別子、操作種別、成否/理由カテゴリ、時刻、相関 ID |
| ログ | 平文値、暗号文、KEK、復号後の値、接続文字列に埋め込まれた鍵 | 操作名、理由カテゴリ、相関 ID、非秘密の件数 |
| 画面 | 平文値、復号後の値、暗号文 | マスク不要の「未登録 / 登録済み」表示、登録・更新・失効の操作結果。入力フォームは送信後に値を保持しない |
| 例外メッセージ / スタックトレース | 平文値、暗号文、KEK、DB 行の生ダンプ | 固定のエラーカテゴリ（例: `credential_not_found`, `credential_access_denied`, `credential_decrypt_failed`） |
| job input / receipt / model context | 平文値、暗号文、KEK | provider 選択に必要な非秘密 metadata（provider ID、credential record ID、key version の参照可否ではなく存在可否） |
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
| `credential_label` | TEXT | 利用者が識別するための表示名 | 非秘密（平文値を入れない） |
| `secret_ciphertext` | BLOB/TEXT NOT NULL | AEAD で暗号化した暗号文。**名前から値でないことが分かる**。平文を入れない | 暗号文（DB 内では保護されるが、KEK 漏えい時は復号されうる） |
| `cipher_alg` | TEXT NOT NULL | 暗号アルゴリズム識別子（例: `aes-256-gcm`） | 非秘密 |
| `kek_version` | INTEGER NOT NULL | 暗号化に使った KEK の版 | 非秘密 |
| `nonce` | BLOB/TEXT NOT NULL | AEAD nonce/IV。再利用禁止 | 非秘密（ただし値ではない） |
| `aad_scope` | TEXT NOT NULL | AAD に含めたスコープ識別子（`owner_user_id`, `provider_id`, record ID 等の固定形式） | 非秘密 |
| `state` | TEXT NOT NULL | `active` / `revoked` / `deleted_pending` 等の状態 | 非秘密 |
| `created_at` | REAL/TIMESTAMP NOT NULL | 作成時刻 | 非秘密 |
| `updated_at` | REAL/TIMESTAMP NOT NULL | 更新時刻 | 非秘密 |
| `revoked_at` | REAL/TIMESTAMP NULL | 失効時刻 | 非秘密 |
| `last_used_at` | REAL/TIMESTAMP NULL | サーバが復号して使用した最終時刻（任意、記録するなら非秘密） | 非秘密 |

明示的に**作らない列**: `secret`, `secret_value`, `api_key`, `plaintext`, `token`, `password`, `credential`, `value`, `material` 等、平文値を入れられる名前/意味の列。将来の migration でも同じ禁止を起動時ガードで強制する（§5a）。

### 2.2 暗号鍵（KEK）の置き場

KEK は **DB の外**に置く。DB の中に置くことは不可（決定 3 の導出: DB を読める者が復号できては「管理者でも他人の値は読めない」が無効になる）。

| 選択肢 | 採否 | 理由 |
|---|---|---|
| **サーバ起動時に注入される環境変数 / secret manager からの注入** | **採用（推奨）** | DB と分離でき、Windows/Linux/コンテナのデプロイ境界で運用しやすい。secret manager（クラウド/オンプレの vault 製品）を使う場合も、アプリプロセスへは起動時注入として渡し、アプリは注入元の製品 API に依存しない設計にできる。アクセスはプロセス起動権限とデプロイ設定に限定できる。 |
| OS の資格情報ストア（Windows Credential Manager / macOS Keychain / Linux secret service 等） | 不採用（代替としては有効） | ホスト統合は強いが、OS/デスクトップセッション/ヘッドレス/コンテナで挙動差が大きい。Locus は LAN 配備・FastAPI サーバとして複数 OS で動きうるため、最初の設計を OS ストア依存にすると運用分岐と検証面が増える。将来、単一ホスト配備プロファイルで追加採用する余地はあるが、本設計の既定にはしない。 |

KEK 運用ルール:

- KEK 実値を**リポジトリに置かない**。`.env`、サンプル設定、テスト fixture、ドキュメント、コミットメッセージに実値を書かない。
- `.env.example` 等に置くのは変数名と説明のみ（例: `LOCUS_PROVIDER_CREDENTIAL_KEK_<version>=<set-at-deploy-time>` のような名前だけ。実値は禁止）。
- KEK はアプリが通常の API 応答・監査・ログ・例外に出さない。設定診断は「設定済み / 未設定」の presence のみ。
- KEK は少なくとも 256-bit 相当の強度を持つランダム値とし、平文パスワード文字列をそのまま KEK にしない（必要なら KDF を別設計で定めるが、KDF パラメータや salt も秘密扱いの混同を避ける）。

### 2.3 保存時暗号化

- アルゴリズムは AEAD（例: AES-256-GCM）を第一候補とする。実装時に具体ライブラリ/プリミティブを固定するが、本設計では「認証付き暗号であること」「nonce 再利用禁止」「AAD を使うこと」を要件とする。
- AAD には少なくとも `owner_user_id`, `provider_id`, record ID（または同等の不変スコープ）を含める。これにより、暗号文を別利用者/別 provider レコードへ差し替える攻撃を検知できる。
- 暗号化はサーバ内の復号経路と対になる 1 箇所の暗号化経路に集約する（§5b の一点化方針と対称）。
- DB に保存されるのは `secret_ciphertext`, `nonce`, `cipher_alg`, `kek_version`, `aad_scope` 等の暗号化 metadata のみ。平文値は DB に書かない。

### 2.4 鍵の交換（rotation）

- KEK は `kek_version` で版管理する。暗号文レコードは自分を暗号化した `kek_version` を保持する。
- rotation 手順（設計）:
  1. 新 KEK（version N+1）をデプロイ環境に追加する。旧 KEK（version N）も復号のため一時的に残す。
  2. 新規書き込み/更新は version N+1 で暗号化する。
  3. 既存レコードはバックグラウンド再暗号化ジョブまたは次回更新時に再暗号化する。再暗号化は「旧 KEK で復号 → 新 KEK で暗号化 → `kek_version` 更新」を 1 トランザクション境界で扱う。
  4. 全レコードが N+1 へ移行し、監査/検査で N が残っていないことを確認した後、旧 KEK をデプロイ環境から削除する。
- rotation 中の失敗は fail-closed: 再暗号化できないレコードを平文化・無効化して放置しない。旧 KEK が利用可能な間は旧暗号文を読めるが、新規平文保存はしない。
- KEK 漏えいが疑われる場合は、鍵交換だけでなく当該 KEK で保護されていた provider API key の失効/再発行を利用者・運用手順に要求する（暗号化は漏えい後の無効化を代替しない）。

### 2.5 失効（利用者の削除、鍵の無効化）

| 事象 | 設計 |
|---|---|
| 利用者が鍵を無効化 | `state=revoked`, `revoked_at` を記録。暗号文は即時に使用不能扱いにし、復号経路は revoked を返して値を返さない。物理削除は保持ポリシーに従う別処理でよいが、通常経路からは読めないことを先に満たす。 |
| 利用者が削除された | 当該 `owner_user_id` の credential record を失効または削除対象にする。削除ジョブは監査可能な metadata のみ残し、平文値をログに出さない。 |
| provider 側で鍵が無効化された | Locus は presence/state を `revoked` または `invalid` 相当へ更新できる設計にする。サーバは無効鍵を使い続けない。 |
| KEK が失われた | 暗号文は復号不能になる。これは可用性の喪失であり、平文漏えい防止を優先する。復旧は利用者の再登録で行う。KEK バックアップはデプロイ責任だが、バックアップも DB 外の秘密として扱う。 |

### 2.6 読めるのは誰か

- **復号できる主体**: 鍵の持ち主である利用者の要求を処理する、サーバ内の認可済み経路だけ。
- **復号できない主体**: 他の利用者、`system_admin` を含む管理者、監査閲覧者、サポート UI、一般的な DB 読み取りクエリ、ログ閲覧者。
- `system_admin` は利用者管理・ポリシー管理・システム運用の権限を持っても、**他人の provider API key の平文値を復号する権限は持たない**（決定 3）。必要な運用情報は presence metadata（登録有無、状態、最終更新時刻、key version）で提供する。
- 所有者本人であっても、API 応答で平文値を返す通常経路は作らない。本人確認済みの更新/置換 UI は「新しい値を入力して置換する」形にし、既存値の再表示はしない。

### 2.7 主張の範囲（正直に書く）

`DOCUMENT_EXTRACTION_BOUNDARY.md` §5 の作法に従い、守れる保証と守れない保証を分ける。**弱い方の保証しか主張しない。**

| 保証 | アプリ経路 / 通常の DB 読み取り | ホスト root 相当 / プロセス完全掌握 / メモリダンプ |
|---|---|---|
| API 応答・監査・ログ・画面・例外に平文が出ない | ○（§5 の機械検査で固定） | △ プロセスが掌握されると任意の出力経路を作られうる |
| `system_admin` でも他人の値を通常経路で読めない | ○（§5b/5c で固定） | × root 相当は認可コードを迂回/改変できる |
| DB の行を読んだだけでは平文が分からない | ○（暗号文のみ保存） | × KEK も取得できれば復号されうる |
| KEK が DB に無い | ○ | × ホスト root 相当は環境変数・プロセスメモリ・秘密ストア注入経路を読める可能性がある |
| リポジトリ漏えいだけで鍵が漏れない | ○（KEK 実値を置かない） | - |

この設計が**主張しないこと**:

- ホストに root 相当で入れる者、ハイパーバイザ/クラウド管理者、プロセスメモリを読む者、デプロイ秘密をすべて取得できる者に対して平文を守れる、とは主張しない。
- 暗号化して DB に置くことをもって「絶対に漏れない」とは主張しない。
- 監査ログ改竄耐性、バックアップ媒体の物理保護、HSM 相当の非輸出保証は本書の範囲外であり、別タスクで扱う。

## 3. (B) エージェントの資格情報は端末側のまま

決定 1: (B) は端末側のまま。サーバは利用者の Claude / Codex ログインを預からない。

### 3.1 維持する既存方針

- `HYBRID_AGENT_ADAPTER_DESIGN.md` §4.2 Option 1（CLI ネイティブログイン・端末側保持）を維持する。
- `adapter_credentials` テーブル（`registry.py:154-160`）は presence metadata のみを保持する: `(runner_instance_id, adapter_id, state, checked_at)`。値の列は持たない。
- `credential_schema_is_presence_only()`（`registry.py:53-56`）と起動時ガード（`registry.py:186-187`）は維持する。
- Locus サーバへ資格情報値（API key, OAuth token, refresh token, session cookie, CLI auth file 内容）を送る経路を設けない。

### 3.2 それでも UX が成立する理由

オーナー要望は「チャット画面で接続した利用者が、モデル管理の部分で選択できること」である。この UX は **metadata で成立する**。

| UX 要素 | サーバが持つもの | サーバが持たないもの |
|---|---|---|
| モデル/アダプタ選択肢の表示 | adapter catalog、workspace binding、policy allowlist、presence state（enrolled/absent/revoked） | ログイン値、トークン |
| 接続状態の表示 | `state`, `checked_at`, 非秘密の診断カテゴリ | CLI auth file 内容、セッション秘密 |
| 利用者ごとの選択 | 利用者/workspace と adapter binding の関連 metadata | 他人の資格情報値 |
| 実際の実行 | Desktop Runner / 端末側が自身の保持する認証状態で実行する（B6 解除前提条件は別途） | サーバが代理でログインすること |

したがって、(B) をサーバ保管に変えなくても、チャット画面のモデル管理から選ぶ UX は成立する。

### 3.3 (A) の箱に (B) を入れない

- `user_provider_credentials`（§2.1）は (A) 専用。Claude/Codex ログイン値、Runner の認証状態、CLI auth file を入れない。
- (B) の状態表現は既存 `adapter_credentials` の presence-only を使い続ける。新テーブルへ移したり、暗号文列を足したりしない。
- 実装時のコードレビュー/検査では、(A) テーブルへの書き込み経路が provider API key 用 DTO/サービスに限定されていることを確認する（agent login 系の型・経路を受け付けない）。

## 4. `credential_schema_is_presence_only` の扱い

### 4.1 結論: 維持する

既存 guard は**そのまま維持する**。変更しない。

- `backend/app/agents/registry.py:53-56` の `credential_schema_is_presence_only()` は、`adapter_credentials` の列集合が `{"runner_instance_id", "adapter_id", "state", "checked_at"}` であることを検査する。
- `backend/app/agents/registry.py:186-187` は初期化時にこれを呼び、偽なら `RuntimeError("adapter_credentials schema is not presence-only")` で起動を止める。
- `tests/test_agents_registry.py` の関連回帰（schema/import boundary/B6/registry acceptance）は従来どおり PASS することを本設計の受入条件とする。

### 4.2 理由

- (A) は新テーブル `user_provider_credentials` に置くため、`adapter_credentials` の列集合を変える必要がない。
- guard を弱めると、将来の変更が (B) に値列を混入させても起動時に止まらなくなる。決定 1（(B) は端末側のまま）を機械的に守るため、guard は維持する。
- 本設計は「不変条件を外さないで決定を満たせるなら、外さない」に従う。

### 4.3 もし同じテーブルに値を足す案を採るなら（非推奨・本設計では採用しない）

本設計はこの案を採用しない。参考として、採る場合に必要な条件だけを書く:

- `credential_schema_is_presence_only()` を外す代わりに、(A) 用暗号文列のみを許可し、平文列・(B) 用値列を禁止する新しい厳密な allowlist guard が必要になる。
- (A)/(B) 混在の監査、移行、API、テスト、監査ログ漏えい面が増える。
- 既存テストが guard の存在とメッセージに依存しているため、変更は広範囲に波及する。
- **したがって採用しない。**

## 5. 「バグっても破れない」機械的ガード

決定 3: 規約や査読ではなく、**機械が落とす**形にする。以下 4 つはすべて、実装時に合否条件つき検査として固定する。**落ちない検査は検査ではない。**

### 5a. 起動時ガード（新テーブルの平文列禁止）

| 項目 | 内容 |
|---|---|
| 対象 | `user_provider_credentials`（§2.1）の schema |
| 検査 | 起動時にテーブルの実列集合を照合する。許可された列集合から外れる列、または平文値を入れられる名前/意味の列（`secret`, `secret_value`, `api_key`, `plaintext`, `token`, `password`, `credential`, `value`, `material` 等の禁止 marker。marker 一覧はテストで固定）が存在したら拒否する。`secret_ciphertext` は暗号文列として許可されるが、平文列として扱わない。 |
| 失敗方式 | 既存 `credential_schema_is_presence_only()` と**同じ語彙・同じ失敗方式**にする。guard 関数は偽を返し、初期化は `RuntimeError` で**起動を止める**。既存先例は `registry.py:186-187` の `RuntimeError("adapter_credentials schema is not presence-only")` であり、新テーブルの guard も同じ形（例: `RuntimeError("user_provider_credentials schema is not presence-only")` のような明示的メッセージ）で失敗させる。警告ログだけで続行しない。新しい流儀を作らない。 |
| 何をしたら落ちるか | migration や手作業で `api_key TEXT` / `secret_value TEXT` / `plaintext TEXT` 等の列を追加する、または許可外の列を追加する → guard が偽 → 初期化が `RuntimeError` を送出 → アプリ起動失敗。 |
| 先例 | `backend/app/agents/registry.py:53-56`（`credential_schema_is_presence_only`）, `:186-187`（`RuntimeError("adapter_credentials schema is not presence-only")`）。新しい流儀を作らない。 |

### 5b. 復号経路の一点化

| 項目 | 内容 |
|---|---|
| 対象 | (A) の `secret_ciphertext` を復号できるコード経路 |
| 設計 | 復号できる関数を **1 つ**に絞る。関数は `requester_user_id` と `owner_user_id`（または owner に束縛された record を取得するための同等の必須引数）を**必須**で取り、`requester_user_id != owner_user_id` なら例外を送出する。`requester_user_id` を省略できるオーバーロード、既定値 `None`、内部で「admin なら許可」する分岐を作らない。 |
| 追加制約 | 暗号文を直接 SELECT してアプリ層で ad-hoc に復号する経路を禁止する。DB アクセス層は暗号文を返す内部型を狭くし、通常の API/サービス層は presence DTO しか扱えないようにする。 |
| 何をしたら落ちるか | `requester_user_id` を省略した呼び出し、`requester_user_id != owner_user_id` の呼び出し、または一点化関数の外で復号を行うコードが追加される → 単体テスト/静的検査/コードレビューゲート（実装タスクで具体化）が失敗する。特に「他人の owner_user_id で復号成功」はテスト失敗。 |
| 実装時の検査例 | `decrypt_provider_secret_for_owner(*, requester_user_id: str, owner_user_id: str, record_id: str) -> SecretStr/bytes` のような keyword-only 必須引数。`system_admin=True` 引数を足す変更はテストで落とす。 |

### 5c. 管理者でも読めないことの検査

| 項目 | 内容 |
|---|---|
| 対象 | `system_admin` 権限を持つ主体による他人の (A) 平文値の読取 |
| 設計 | `system_admin` は管理 API で presence metadata を見られてもよいが、他人の `secret_ciphertext` を復号する経路には入れない。復号経路は role ではなく所有者一致で認可する（§5b）。 |
| 既存コードの確認点 | `backend/app/agents/registry.py:275, 725` に既存の `system_admin` 分岐がある。実装時は、provider credential の読取/復号/表示経路に同種の `if actor.system_admin: allow` を追加していないことを確認する。registry の管理操作権限と credential 平文読取権限を混同しない。 |
| 何をしたら落ちるか | `system_admin` actor が他人の owner_user_id を指定して復号 API/サービスを呼ぶテストで、平文が返る・復号が成功する・HTTP 200 で値が見える、のいずれかが起きたら FAIL。期待結果は deny（403/404/固定エラーカテゴリ。情報漏えいを避けるため存在秘匿が必要なら 404 でもよいが、監査には denied を残す）。 |
| 追加の負検証 | system_admin が DB から暗号文行を取得できても、アプリ通常経路がそれを復号して返さないこと。監査/ログ/例外にも値が出ないこと（§5d と併せて確認）。 |

### 5d. 漏れの検査

| 項目 | 内容 |
|---|---|
| 対象 | API 応答、監査レコード、ログ、例外文字列、画面描画用 DTO、job input/receipt/model context |
| 検査 | synthetic な provider key（例: `TEST-PROVIDER-KEY-SYNTHETIC-0000`）と、暗号文列名/関連値（`secret_ciphertext`, 実際の ciphertext bytes の代表表現）を fixture に使い、通常経路・エラー経路・管理経路の出力をスキャンする。 |
| 何をしたら落ちるか | API JSON、監査行、ログキャプチャ、例外メッセージ、HTTP エラーボディ、画面用シリアライズ結果のいずれかに synthetic 平文値または `secret_ciphertext` 列の生値が含まれたら FAIL。テストは「含まれていないこと」を具体文字列で assert する。 |
| 例外メッセージの扱い | 復号失敗や DB エラーの内部例外をそのまま利用者へ返さない。固定カテゴリへ正規化する。スタックトレースは開発ログでも secret redaction を通すか、そもそも値を例外に載せない設計にする。 |

## 6. 検証項目（合否条件つき、mock/合成データのみ）

実資格情報、実 provider endpoint、実ユーザーデータ、外部通信は禁止。fixture は synthetic key / stub KEK / stub DB / stub audit sink のみ。

### 6.1 正検証

| ID | 項目 | 手順（mock/synthetic） | 合否条件 |
|---|---|---|---|
| VT-1 | (A) 保存と presence 表示 | synthetic key を登録する。 | DB には `secret_ciphertext` 等の暗号化 metadata のみ保存され、平文列は存在しない。API は presence metadata のみ返し、平文を返さない。 |
| VT-2 | 所有者本人の復号経路 | `requester_user_id == owner_user_id` で復号関数を呼ぶ。 | 復号が成功し、返却は内部使用に限定される。API 応答/監査/ログに平文が出ない。 |
| VT-3 | KEK rotation | version N で暗号化したレコードを version N+1 へ再暗号化する。 | 再暗号化後に N+1 で復号でき、N+1 以外の古い KEK が無い状態でも読める。旧 KEK 除去後に N 専用レコードが残っていれば検査が FAIL。 |
| VT-4 | 失効 | owner が credential を revoke する。 | `state=revoked` になり、以後の復号/利用は拒否される。監査には非秘密 metadata のみ残る。 |
| VT-5 | (B) presence-only 維持 | agent adapter credential の enrolled/absent/revoked を記録する。 | `adapter_credentials` の列集合は従来どおり。`credential_schema_is_presence_only()` は真。`tests/test_agents_registry.py` が PASS。 |

### 6.2 負検証

| ID | 項目 | 手順（mock/synthetic） | 合否条件 |
|---|---|---|---|
| NV-1 | 平文列追加の起動拒否 | `user_provider_credentials` に `api_key TEXT` 等の禁止列を足した fixture DB を起動する。 | 起動時 guard が `RuntimeError` で起動停止。警告だけで続行しない。 |
| NV-2 | 他人の復号拒否 | `requester_user_id != owner_user_id` で復号関数を呼ぶ。 | 例外/deny。平文は返らない。監査に denied が残る。 |
| NV-3 | system_admin の他人読取拒否 | `system_admin` actor が他人の credential を復号/取得しようとする。 | 拒否される。HTTP 200 で値が返らない。平文/暗号文が応答・監査・ログ・例外に出ない。 |
| NV-4 | requester 省略拒否 | `requester_user_id` を省略/`None` で復号関数を呼ぶ API 形を作ろうとする。 | 型/シグネチャ/テストで失敗する。省略可能な呼び出しが存在したら FAIL。 |
| NV-5 | API/監査/ログ/例外の漏れ検査 | synthetic key `TEST-PROVIDER-KEY-SYNTHETIC-0000` を使い、成功・拒否・復号失敗・DB エラーの各経路を実行する。 | どの出力にも synthetic 平文値と `secret_ciphertext` の生値が現れない。現れたら FAIL。 |
| NV-6 | DB 読み取りだけでは平文不可 | DB から `user_provider_credentials` 行を直接読む。 | 得られるのは暗号文と非秘密 metadata のみ。平文値は含まれない。 |
| NV-7 | (A)/(B) 混在拒否 | agent login 系の値を (A) テーブルへ書く経路、または provider key を `adapter_credentials` へ書く経路を作る。 | schema guard / 型境界 / テストで拒否される。`adapter_credentials` は presence-only のまま。 |
| NV-8 | KEK 未設定時の fail-closed | KEK なしで (A) の登録/復号を行う。 | 平文保存へフォールバックしない。明示的なエラーで失敗し、監査/ログに KEK 値は出ない。 |

### 6.3 証跡要件

- 証跡は synthetic fixture、KEK version、DB schema snapshot、相関 ID、実行コマンドに束縛する。
- SKIPPED/BLOCKED は証拠ではない。未実施は未実施と記録する。
- 実資格情報・実 provider endpoint・実ユーザーデータを使った検証は本タスクの対象外。

## 7. 非目標 / 本書が承認しないこと

- `adapter_credentials` の schema 変更、registry API の挙動変更、dispatch/B6 の変更。
- 実資格情報の読取/転送/供給、実 provider 呼び出し、外部通信。
- (B) エージェントログインのサーバ保管。
- KEK 管理の本番運用手順（HSM、クラウド KMS 製品選定、バックアップ媒体管理）の確定。
- 監査ログ保護（T-T4: 改竄耐性・アクセス制御・保持）の解消。本書の漏れ検査は必要条件であり、T-T4 の代替ではない。
- ホスト root 相当の攻撃者に対する平文保護の主張。

## 8. 受入条件との対応

| 受入条件 | 本書の対応 |
|---|---|
| 1. (A)/(B) が別々に書かれ、両方に出さない場所一覧。(B) は端末側のまま | §1, §1.1, §1.2, §3 |
| 2. (A) は DB 新テーブル・保存時暗号化・KEK は DB 外。採用理由と不採用理由 | §2.1, §2.2, §2.3 |
| 3. `credential_schema_is_presence_only` を維持（または代替 guard） | §4（維持を採用） |
| 4. 管理者でも他人の値は読めないことを機械が守る形で a〜d。起動時ガードは同じ失敗方式 | §5a-§5d |
| 5. 主張の範囲が正直。ホスト root 相当には効かない | §2.7 |
| 6. 検証項目に合否条件 | §6 |
| 7. コード・スキーマ・dispatch 挙動を変更しない | 非目標 §7、実行結果は TEST で示す |
| 8. 変更が許可パス内 | `progress/phase-ai-connect/material/USER_CREDENTIAL_DESIGN.md` のみ |
