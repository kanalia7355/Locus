# 本番運用確認チェックリスト（`PROD-003` / `IAM-017` / `PROD-002`）

本書は、`docs/operations/PRODUCTION_DEPLOYMENT.md` に従って配備した Locus 本番環境が要件を満たして稼働していることを確認するための運用チェックリストである。

## 凡例（自動確認と人手確認の区別）

各チェック項目の先頭には、`scripts/check_deployment.py`（既定のオフライン実行）で自動検査できるか否かを次の印で明記する。

- **`[AUTO]`**: `python scripts/check_deployment.py`（引数なし・オフライン実行）によって機械的に自動確認できる項目。スクリプトが終了コード `0` を返すことで合格と判定できる。
- **`[MANUAL]`**: `scripts/check_deployment.py` の既定実行では判定できないため、**人が実機・ブラウザ・ネットワーク境界でコマンドや画面を実行して目で確認する**項目（一部は `--probe` オプションで補助できるが、最終判定は人が行う）。

各項目は **「担当」「実行内容」「合格基準」** の 3 点をすべて満たしたときにチェックを入れること。

---

## 1. 設定値・証明書・鍵のオフライン照合

- [ ] `[AUTO]` **本番モードとローカル専用フラグの整合** — 担当: 配備担当者 / 実行内容: 配備先環境で `python scripts/check_deployment.py` を実行し、`APP_ENV`、`ALLOW_CLOUD_EGRESS`、`LOCAL_ONLY_MODE` の検査結果を確認する / 合格基準: 標準エラーに `FAIL` が 1 行も出ず、終了コード `0` で `Deployment verification passed.` が表示されること。
- [ ] `[AUTO]` **TLS 終端方式と必須設定の整合** — 担当: 配備担当者 / 実行内容: `python scripts/check_deployment.py` を実行し、`LOCUS_TLS_TERMINATION`（`native` 時は `LOCUS_TLS_CERT_FILE` と `LOCUS_TLS_KEY_FILE`、`proxy` 時は `LOCUS_TRUSTED_PROXY`）および `LOCUS_PRIVATE_INTERFACE`、`LOCUS_ALLOWED_HOSTS`（`*` 不使用）の照合結果を確認する / 合格基準: 終了コード `0` であり、`OK: private_interface=...` と `OK: allowed_hosts=...` に意図した私設アドレスと許可ホスト名のみが出力されること。
- [ ] `[AUTO]` **サーバ証明書の有効期限と秘密鍵の保護権限（`native` 構成時）** — 担当: 配備担当者 / 実行内容: `python scripts/check_deployment.py` を実行し、`LOCUS_TLS_CERT_FILE` の有効期間と `LOCUS_TLS_KEY_FILE` の読取可否・権限検査結果を確認する / 合格基準: 終了コード `0` で `OK: certificate subject=... issuer=... not_before=... not_after=...` が出力され、現在時刻が有効期間内かつ秘密鍵の内容が一切出力されていないこと。
- [ ] `[MANUAL]` **証明書の出自・SAN・端末信頼チェーンの確認** — 担当: インフラ／セキュリティ管理者 / 実行内容: 利用者端末のブラウザまたは `openssl s_client -connect <許可ホスト>:<port> -servername <許可ホスト>` で接続し、提示された証明書の発行者（社内 CA または事前配布した自己署名証明書）と SAN、有効期限を確認する（`proxy` 構成の前段証明書もここで確認する） / 合格基準: 承認された社内 CA または配布済み自己署名証明書とフィンガープリント・発行者が一致し、ブラウザに証明書警告が出ず、`notAfter` まで十分な残日数があること。
- [ ] `[MANUAL]` **Windows ACL を含む秘密鍵の最小権限確認** — 担当: インフラ管理者 / 実行内容: Linux では `stat -c "%a %U:%G" "$LOCUS_TLS_KEY_FILE"`（またはプロキシ秘密鍵）、Windows では `icacls <秘密鍵パス>` を実行する / 合格基準: 配備サービス実行ユーザおよび OS 管理者のみに読取権限があり、`Users`・`Everyone`・他サービスアカウントに読取権限が無いこと。

---

## 2. ネットワーク境界・待ち受け・外向き通信の遮断

- [ ] `[MANUAL]` **待ち受けが私設インタフェースに限定されていること** — 担当: インフラ管理者 / 実行内容: 配備ホスト上で Linux なら `ss -tlnp`、Windows なら `Get-NetTCPConnection -State Listen` を実行して Locus（および前段プロキシ）の待ち受けアドレスを確認する / 合格基準: 待ち受けソケットの Local Address が `LOCUS_PRIVATE_INTERFACE` の私設 IP のみであり、`0.0.0.0`、`::`、または公開 NIC のアドレスで LISTEN していないこと。
- [ ] `[MANUAL]` **公開インタフェース・未認可セグメントから到達できないこと** — 担当: ネットワーク管理者 / 実行内容: 許可された私設セグメント外（ゲスト Wi-Fi、WAN 側、別 VLAN 等）の端末から `curl -k --connect-timeout 5 https://<配備ホストの他セグメントIPまたはホスト>:<port>/api/health` を実行する / 合格基準: TCP 接続がタイムアウトもしくは拒否される（またはアプリ到達時でも `403` で拒否される）こと、かつ業務レスポンスが一切返らないこと。
- [ ] `[MANUAL]` **外向き通信が OS / ファイアウォール層でも遮断されていること** — 担当: ネットワーク／インフラ管理者 / 実行内容: Locus 実行ユーザ権限で配備ホストから `python scripts/check_deployment.py --probe` または `curl --connect-timeout 5 https://1.1.1.1` を実行する / 合格基準: 外部インターネット宛ての通信がファイアウォールによりタイムアウトまたは接続拒否（`blocked as expected`）となり、外部への TCP 接続が成立しないこと。

---

## 3. セッション保護と認可（`IAM-017` / `PROD-002`）

- [ ] `[MANUAL]` **セッション cookie に `Secure`・`HttpOnly`・`SameSite=Strict` が付与されること** — 担当: 配備担当者 / 実行内容: 私設 LAN 内の端末から `curl -i -X POST https://<許可ホスト>/api/auth/login -H "Origin: https://<許可ホスト>" -H "Content-Type: application/json" -d '{"username":"<検証用ID>","password":"<検証用PW>"}'` を実行し、応答ヘッダの `Set-Cookie`（および `/api/auth/logout` 時の削除 `Set-Cookie`）を確認する / 合格基準: `locus_session` の `Set-Cookie` ヘッダに `Secure`、`HttpOnly`、`SameSite=Strict`、`Path=/api` がすべて含まれていること。
- [ ] `[MANUAL]` **未認証アクセスおよび非管理者による管理経路アクセスが拒否されること** — 担当: セキュリティ確認担当者 / 実行内容: ① cookie 無しで `curl -i https://<許可ホスト>/api/projects` を実行し、② `system_admin` ではない一般ロール（`researcher` 等）でログインしたセッション cookie を用いて `curl -i https://<許可ホスト>/api/admin/audit` を実行する / 合格基準: ① 未認証の `/api/projects` が HTTP `401` となり、② 非管理者の `/api/admin/audit` が HTTP `403` となって管理情報・監査ログ本文が一切返らないこと（LAN 接続のみでは権限が付与されないこと）。
