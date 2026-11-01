# accounts 段階の部分配備からの復旧

2026-11-01。これは初回 installer の再実行ではなく、明示的に固定した部分状態だけを
対象にする新しい復旧経路。旧配備物・アカウントの削除、既存ファイルの上書きは行わない。
無人ループ・自動レビュー・マージの起動許可ではない。

## 診断根拠

所有者の管理者診断では Review 用アカウントに、service logon、interactive deny、
remote interactive deny がすべて設定済み。policy open/rights read は成功。
Review プロファイルは未登録、Merge アカウントと両サービスは未作成。
したがって権限付与を再度推測して変更する必要はない。元の CreateProfile 呼出しの
HRESULT は取得できておらず、具体的な OS エラー原因は未確定。

Windows の [Service User Accounts](https://learn.microsoft.com/en-us/windows/win32/services/service-user-accounts)
は SCM がサービス利用者のプロファイルを読み込む仕様を示す。installer は不要な
手動 CreateProfile を外し、サービスログオンに任せる。実配備でのプロファイル作成と
Credential Manager 永続化は、別途 health・再起動試験で確認する。

## 対象を固定する

```powershell
.venv\Scripts\python.exe -m loop_engine.cli service-bundle `
  --recover-partial-from <旧配備manifestのSHA256> `
  --review-sid <所有者の診断で確認したReviewアカウントSID>
```

両引数は必須の組。復旧情報は新しい manifest 自体のハッシュに含める。
通常の `service-bundle` は引き続き既存アカウントや配備先を拒否する。
生成する新しい管理者ブロックで、対象と説明を確認してから所有者が実行する。
復旧中は他の管理者処理で対象アカウント・プロファイル・グループ・SCMを変更しない。
利用状態とグループ所属はパスワード変更直前にも再取得するが、別管理者とのOS全体の
トランザクションを保証するものではない。

## 実行前の拒否条件

- 旧配備の SYSTEM 所有・保護 DACL が違う、Sys/Admin 以外のアクセスがある。
- 旧 manifest、全ファイルのハッシュ・在庫、operator、project が違う。
- 配備先に旧 runtime と manifest 以外の内容、復旧 intent、設定や状態領域がある。
- Review の名前・SIDが違う、無効、ログオン歴・プロファイル・サービス利用がある。
- Review がいずれかのローカルグループに所属する、Merge アカウントがある、
  または専用サービスがすでにある。

未知の状態を「直す」ために削除したり、名前だけで別アカウントを採用しない。
これは汎用のサービス更新・鍵更新・既存運用アカウントの復旧手段ではない。

## 変更するもの

全 preflight 後、SYSTEM 所有の公開情報だけの intent を排他的に作成・fsync する。
その後に新 runtime を別バージョンのディレクトリへ配備し、旧 runtime と manifest は
内容も ACL も保持する。

**失敗した初回処理の Review 用パスワードは失われているため、所有者が固定した
SID に対してだけ、新しいランダムパスワードを設定する。** SID・アカウントは保持する。
パスワードは SecureString とメモリ内 PSCredential で SCM へ渡し、ファイル・引数・
環境変数・ログへ出さない。Merge 用アカウントを新規作成し、承認済みのログオン権限、
SYSTEM 所有設定と役割別状態 ACL、制限した SCM 制御を設定する。

状態は `prepare` 固定。鍵の取込みはこの管理者処理では行わない。
途中失敗すると intent が残り、同じ復旧を自動再試行しない。パスワードをリセット済みか
不明な状態を成功と解釈しない。成功しても旧配備物と intent は削除しない。

## 検証と監査

ローカル試験と模擬ガードの結果は、実際の管理者復旧と区別する。復旧後には
[準備配備手順](WINDOWS_SERVICE_SETUP.md)の health・両鍵取込み・policy 読取・
サービス再起動による永続化を検証する。
合成ファイルの実ハッシュを使った preflight 試験では正常系と、SID/所有者差異、
manifest/ファイル改変、余分なファイル/空ディレクトリ、intent 残存、プロファイル、
サービス利用、グループ所属、既存Merge、ログオン済み状態の拒否を確認する。
OSのアカウント・ACL・registry・CIM読取はこの試験ではモック。実パスワード変更と
SCM 作成、管理者クラッシュ時の orchestration を実証した試験ではない。

初期準備実装の2回の再レビュー枠は使用済み。今回の新しい部分復旧経路は独立した
scope で初回セキュリティ監査を行い、初期 scope の監査や実配備成功を装わない。
最終配備監査、Controller 接続、仕様移行、実運転証拠、稼働承認は依然必要。
