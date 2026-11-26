# 本番配備手順書（`PROD-002` / `PROD-003` / `IAM-017`）

本書は Locus を研究所・組織内の私設ネットワーク（LAN / VPN）へ本番配備する際の手順を定める。
設定名はすべて `backend/app/deployment.py` の起動検証と同一であり、配備前後には `python scripts/check_deployment.py` で手順書と実環境の一致を照合する。

---

## 1. 設定一覧（`backend/app/deployment.py` と同一の環境変数）

| 設定名 | 本番での必須値・条件 | 役割 |
|---|---|---|
| `APP_ENV` | `production` | 本番モードを有効化する（未設定時は開発用 `development`）。未知の値は起動拒否。 |
| `LOCUS_TLS_TERMINATION` | `native` または `proxy` | TLS 終端方式。未設定または未知の値は起動拒否。 |
| `LOCUS_TLS_CERT_FILE` | PEM 証明書ファイルの絶対パス（`native` 時必須） | サーバ証明書（中間 CA 証明書がある場合は連結 PEM）。実在・読取可能・有効期限内であること。 |
| `LOCUS_TLS_KEY_FILE` | PEM 秘密鍵ファイルの絶対パス（`native` 時必須） | サーバ秘密鍵。配備実行ユーザのみ読取可能な権限に制限すること。 |
| `LOCUS_TRUSTED_PROXY` | 私設 IP アドレス（`proxy` 時必須） | 前段で TLS を終端するリバースプロキシの私設アドレス（`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`）。公開 IP やワイルドカードは拒否。 |
| `LOCUS_PRIVATE_INTERFACE` | 私設 IP アドレス | 待ち受けを行う私設インタフェースのアドレス。`0.0.0.0`、`::`、ワイルドカード、公開 IP は起動拒否。 |
| `LOCUS_ALLOWED_HOSTS` | カンマ区切りのホスト名列挙 | 受け付ける `Host` ヘッダおよび `https://` Origin の明示列挙。未設定・空・`*` を含む値は起動拒否。 |
| `ALLOW_CLOUD_EGRESS` | `false` | クラウドへの外向き送信禁止フラグ。`true` や真偽値以外の文字列は起動拒否。 |
| `LOCAL_ONLY_MODE` | `true` | ローカル専用動作モード。`false` や真偽値以外の文字列は起動拒否。 |

---

## 2. TLS 証明書の入手・配置・更新手順

社内ネットワーク限定であっても、ブラウザから ID・パスワードで認証して利用するため HTTPS（TLS）を必須とする（オーナー決定 2026-11-16 テーマ 5）。組織の運用体制に応じて **(a) 社内 CA で発行** または **(b) 自己署名証明書 + 各端末への配布** のいずれかを選択する。

### 選択肢 (a): 社内 CA（組織内認証局）で発行する場合

組織内に既存のプライベート CA（Active Directory 証明書サービス、step-ca、OpenSSL 社内 CA 等）があり、利用端末に社内ルート CA 証明書が配布済みの場合に適する。

1. **秘密鍵と CSR（証明書署名要求）の作成**
   - Subject Alternative Name（SAN）に、`LOCUS_ALLOWED_HOSTS` に列挙する予定の FQDN（例: `locus.internal`）および必要に応じ私設 IP アドレスを必ず含める（現代のブラウザは Common Name のみでは検証を通さない）。
   ```bash
   openssl req -new -newkey rsa:2048 -nodes \
     -keyout server.key -out server.csr \
     -subj "/O=YourOrg/CN=locus.internal" \
     -addext "subjectAltName=DNS:locus.internal,IP:10.10.0.5"
   ```
2. **社内 CA による署名**
   - `server.csr` を社内 CA 管理者へ提出し、サーバ認証拡張（`serverAuth`）付きの PEM 証明書 `server.crt`（中間 CA がある場合はサーバ証明書 → 中間 CA の順で連結した `fullchain.pem`）を受領する。
   - **秘密鍵 `server.key` は配備ホスト外へ持ち出さない。**

### 選択肢 (b): 自己署名証明書を作成し、各利用端末へ配布する場合

社内 CA が無い小規模ラボ・閉域環境では、自己署名証明書を発行し、その公開証明書を利用者の各端末の信頼済みルートストアへ登録する。

1. **SAN 付き自己署名証明書と秘密鍵の作成**
   - 有効期間はブラウザの上限（398 日未満、推奨 365 日）以内とし、SAN に `LOCUS_ALLOWED_HOSTS` と一致するホスト名・IP を指定する。
   ```bash
   openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
     -keyout server.key -out server.crt \
     -subj "/O=LocusLab/CN=locus.internal" \
     -addext "subjectAltName=DNS:locus.internal,IP:10.10.0.5" \
     -addext "basicConstraints=critical,CA:TRUE" \
     -addext "keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign" \
     -addext "extendedKeyUsage=serverAuth"
   ```
2. **各利用端末への配布と信頼登録**
   - 公開証明書 `server.crt` のみを利用端末へ配布する（**`server.key` は絶対に配布しない**）。
   - 配付時に SHA-256 フィンガープリント（`openssl x509 -in server.crt -noout -fingerprint -sha256`）を別経路または管理手順で照合する。
   - 端末側の登録手順:
     - **Windows**: `certutil -addstore -f "Root" server.crt`（管理者権限）またはグループポリシーで「信頼されたルート証明機関」へ配布。
     - **macOS**: キーチェーンアクセスでシステムキーチェーンへ追加し「常に信頼」に設定。
     - **Linux / Firefox 等独自ストア**: `update-ca-certificates` への配置、またはブラウザのポリシー設定（`Certificates.ImportEnterpriseRoots`）を有効化。

### 置き場所とファイル権限（選択肢 (a)・(b) 共通）

- **配置先（リポジトリ外）**: 証明書と秘密鍵は Git 管理ツリーの外（保護された専用ディレクトリ）に置く。
  - Linux 例: `/etc/locus/tls/server.crt`、`/etc/locus/tls/server.key`
  - Windows 例: `C:\ProgramData\Locus\tls\server.crt`、`C:\ProgramData\Locus\tls\server.key`
- **権限（秘密鍵は配備実行ユーザのみ読取可）**:
  - **Linux**:
    ```bash
    chown root:locus /etc/locus/tls/server.crt /etc/locus/tls/server.key
    chmod 0640 /etc/locus/tls/server.crt
    chmod 0600 /etc/locus/tls/server.key   # または locus 専用実行ユーザ所有で 0600
    ```
    グループ・その他に権限ビットが付いている場合、`scripts/check_deployment.py` は非 0 で失敗する。
  - **Windows**:
    ```powershell
    icacls "C:\ProgramData\Locus\tls\server.key" /inheritance:r
    icacls "C:\ProgramData\Locus\tls\server.key" /grant:r "NT AUTHORITY\SYSTEM:(R)" "Administrators:(F)" "<配備サービス実行ユーザ>:(R)"
    ```
    一般利用者グループ（`Users` / `Everyone`）の読取権限を必ず除去する。

### 期限の確認方法と期限切れ時の更新・交換手順

- **期限の確認方法**:
  1. 自動検査スクリプトを実行する:
     ```bash
     python scripts/check_deployment.py
     ```
     出力の `OK: certificate subject=... not_after=...` で有効期限を確認できる（期限切れの場合は `FAIL: LOCUS_TLS_CERT_FILE: certificate has expired` で終了コード 1 となる）。
  2. OpenSSL で直接確認する場合:
     ```bash
     openssl x509 -in "$LOCUS_TLS_CERT_FILE" -noout -subject -issuer -dates
     ```
- **期限切れ前／期限切れ時の交換手順**:
  1. 期限到来の 30 日前を目安に、上記 (a) または (b) の手順で新しい証明書・鍵ペアを別名（`server.crt.new` / `server.key.new`）として生成する。
  2. 選択肢 (b)（自己署名）の場合は、切り替え前に新しい `server.crt` を各利用端末へ配布・登録する。
  3. 新しい秘密鍵に上記と同一の所有者・権限（`0600` または限定 ACL）を設定する。
  4. 既存の証明書・鍵を退避した上で所定パス（`LOCUS_TLS_CERT_FILE` / `LOCUS_TLS_KEY_FILE`、または前段プロキシ参照先）へ原子的に置き換える。
  5. `python scripts/check_deployment.py` を実行し、終了コード `0` と新しい `not_after` 日時を確認する。
  6. `native` 形態では Locus プロセスを再起動し、`proxy` 形態ではリバースプロキシを設定再読込（`reload`）する。
  7. ブラウザおよび `openssl s_client -connect <host>:<port>` で新しい有効期限の証明書が応答することを確認し、退避した旧秘密鍵を安全に削除する。

---

## 3. TLS 終端の 2 形態（`LOCUS_TLS_TERMINATION`）

### 形態 1: `LOCUS_TLS_TERMINATION=native`（Locus 自身が TLS を終端）

単一ホスト上で前段プロキシを置かず、Uvicorn 等に証明書・鍵を直接渡して HTTPS を張る構成。

```bash
export APP_ENV=production
export LOCUS_TLS_TERMINATION=native
export LOCUS_TLS_CERT_FILE=/etc/locus/tls/server.crt
export LOCUS_TLS_KEY_FILE=/etc/locus/tls/server.key
export LOCUS_PRIVATE_INTERFACE=10.10.0.5
export LOCUS_ALLOWED_HOSTS=locus.internal,10.10.0.5
export ALLOW_CLOUD_EGRESS=false
export LOCAL_ONLY_MODE=true
```

起動コマンド例:
```bash
uvicorn app.main:create_app --factory \
  --app-dir backend \
  --host "$LOCUS_PRIVATE_INTERFACE" --port 8443 \
  --ssl-certfile "$LOCUS_TLS_CERT_FILE" \
  --ssl-keyfile "$LOCUS_TLS_KEY_FILE" \
  --no-proxy-headers
```

### 形態 2: `LOCUS_TLS_TERMINATION=proxy`（前段リバースプロキシで TLS を終端）

同一ホストまたは同一私設セグメント内のリバースプロキシ（Nginx / Caddy / IIS 等）が HTTPS（443/tcp）を終端し、後段の Locus へ転送する構成。

- **前段プロキシの必須要件**:
  1. プロキシ自身は第 2 節の証明書・秘密鍵を用いて TLS 1.2 以上で待ち受け、平文 HTTP（80/tcp）での業務通信を受け付けない。
  2. プロキシから Locus への転送先は **`LOCUS_PRIVATE_INTERFACE`（例: `127.0.0.1` または私設 LAN アドレス）に限定**する。公開インタフェースへ転送してはならない。
  3. `LOCUS_TRUSTED_PROXY` に前段プロキシの私設 IP アドレス（同一ホストなら `127.0.0.1`、専用プロキシ機なら `10.10.0.1` 等）を明示する。未設定または公開 IP の場合、Locus は起動を拒否する。
  4. プロキシはクライアントからの生の `Host` ヘッダを保持（または許可ホストに固定）して転送し、外部から偽装可能な転送ヘッダを無条件に信頼しないこと。

```bash
export APP_ENV=production
export LOCUS_TLS_TERMINATION=proxy
export LOCUS_TRUSTED_PROXY=127.0.0.1
export LOCUS_PRIVATE_INTERFACE=127.0.0.1
export LOCUS_ALLOWED_HOSTS=locus.internal
export ALLOW_CLOUD_EGRESS=false
export LOCAL_ONLY_MODE=true
```

---

## 4. 待ち受け設定（`LOCUS_PRIVATE_INTERFACE`）と公開遮断の確認

- `LOCUS_PRIVATE_INTERFACE` には、配備ホストが持つ私設アドレス（`127.0.0.0/8`、`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`）の 1 つを明示指定する。
- 全インタフェース待ち受け（`0.0.0.0` や `::`）およびワイルドカードは、Wi-Fi・WAN・未認可セグメント等の公開インタフェースへ同時に口を開くため、`deployment.py` が起動時に拒否する。
- アプリケーション層でも `LOCUS_PRIVATE_INTERFACE` が属する私設ネットワーク以外の送信元 IP を `403` で拒否するが、**LAN 内に居ること自体は認可にならない**（全 API でセッション認証とロール・プロジェクト ACL が強制される）。
- **公開インタフェースに出ていないことの確認方法**:
  - Linux: `ss -tlnp` を実行し、Locus（および前段プロキシ）の Local Address が `LOCUS_PRIVATE_INTERFACE:<port>` のみであり、`0.0.0.0:<port>` や `*:<port>`、公開 NIC の IP が存在しないことを確認する。
  - Windows: `Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 8000,8443,443` を実行し、`LocalAddress` が私設アドレスのみであることを確認する。
  - 別セグメント／公開側ネットワークの端末から `curl --connect-timeout 3 https://<公開側IP>:<port>/api/health` を実行し、タイムアウトまたは接続拒否になることを確認する。

---

## 5. 許可ホスト（`LOCUS_ALLOWED_HOSTS`）の決め方とワイルドカード禁止の理由

- **決め方**: 利用者がブラウザの URL バーに入力する正式なホスト名（例: `locus.internal`）をカンマ区切りで最小限だけ列挙する。IP 直打ち運用を併用する場合のみ当該私設 IP も併記する。
  - Locus は `LOCUS_ALLOWED_HOSTS` から `TrustedHostMiddleware` の許可リストと、状態変更 API（POST/PUT/DELETE）に対する `https://<host>` の `Origin` 検査リストを導出する。
- **ワイルドカード（`*`）禁止の理由**:
  1. **DNS リバインディング攻撃の防止**: `*` を許すと、攻撃者が管理する外部ドメインを一時的に私設 IP へ解決させることで、社内ブラウザ経由でリクエストを送り込める。
  2. **Host ヘッダ汚染（Host Header Injection）の防止**: 任意の `Host` を受理すると、リダイレクト先や Origin 境界の検証が無力化される。
  3. **CSRF / Origin 境界の形骸化防止**: 本番の許可 Origin は `LOCUS_ALLOWED_HOSTS` から生成されるため、ワイルドカードを許すと許可画面以外のオリジンを排除できなくなる。

---

## 6. 外向き通信の遮断（アプリ層 + OS / ファイアウォール層）

研究データの機密保持のため、ローカル専用運用ではアプリケーション設定と OS / ネットワーク境界の**二重**で外向き通信を塞ぐ（`ARCHITECTURE.md` Deployment）。

1. **アプリケーション層の設定**:
   - `ALLOW_CLOUD_EGRESS=false` および `LOCAL_ONLY_MODE=true` を設定する（いずれかが逆の場合、Locus は起動を拒否する）。
2. **OS / ファイアウォール層の遮断**:
   - Locus 実行プロセス（または配備ホスト／VLAN）からの外向き通信を既定拒否（Default Deny）とし、社内 DNS・社内 NTP・社内連携ストレージ（許可された私設アドレスのみ）以外への送信、特にインターネット宛て `80/tcp`, `443/tcp`, `53/udp` を遮断する。
   - **Windows Defender ファイアウォール例**:
     ```powershell
     New-NetFirewallRule -DisplayName "Block-Locus-Outbound-Internet" `
       -Direction Outbound -Program "C:\path\to\.venv\Scripts\python.exe" `
       -RemoteAddress Internet -Action Block
     ```
   - **Linux（nftables / iptables / systemd）例**:
     専用実行ユーザ `locus` に対し、`uid-owner locus` で私設アドレス帯（`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`）以外への `OUTPUT` チェインを `DROP` / `REJECT` する。

---

## 7. 本番データストア（PostgreSQL）への参照

- オーナー決定 2026-11-16 テーマ 5（決定 3: `progress/phase-6-extensions/OWNER_DECISIONS.md`）により、**本番ストアは PostgreSQL** とし、SQLite は開発・プロトタイプ用途に限定される。
- ストレージ層の抽象化はジョブ `T-PH7-211` が担い、PostgreSQL エンジンの実装および SQLite からのデータ移行手順（スナップショット出力・投入・件数／チェックサム検証）はジョブ **`T-PH7-212`**（成果物 `docs/MIGRATION_POSTGRES.md`）が担う。本番切り替え時は本書の設定照合とあわせて `T-PH7-212` の移行手順を実施すること。

---

## 8. 配備後の確認手順

1. オフライン設定・証明書照合（ソケット非接続）:
   ```bash
   python scripts/check_deployment.py
   ```
2. 実地疎通・外向き遮断プローブ（任意、稼働中に明示実行）:
   ```bash
   python scripts/check_deployment.py --probe --port 8443
   ```
3. 続けて `docs/operations/PRODUCTION_VERIFICATION_CHECKLIST.md` の全項目（自動確認項目および人手確認項目）を実施し、記録を残す。
