# Windows App サービスの準備配備

2026-11-01。ADR0007/0008 の承認済み隔離方式を、まず `prepare` モードで配備する。
このモードは health、鍵取込み、認証確認、固定した policy 読取だけを提供する。
レビュー公開・マージ・Controller 起動・任意 API は提供しない。

## 配備物と権限

- `service-bundle` は clean な Git commit のソースから専用配備物を作る。
  CPython 3.14.10 x64 embeddable と依存 wheel は固定 SHA256 と照合する。
  開発用 venv、gh 認証、秘密鍵は配備物に含めない。
- 配備先は `C:\ProgramData\LocusLoopServicesV1`。既存の同名配備先、
  アカウント、サービスがあれば上書きせず停止する。失敗時も削除しない。
- 標準ローカルユーザー `locus_loop_review` / `locus_loop_merge` と
  `LocusLoopReviewV1` / `LocusLoopMergeV1` サービスを作る。
  別々のランダムパスワードはメモリ内で作り SCM に設定する。対話/RDPログオンを拒否する。
- コード・設定は SYSTEM 所有で管理者以外には書込不可。各状態領域は他方の役割に非公開。
  サービスは Manual 起動で、自動再起動を設定しない。
  元の利用者にはサービスの参照・開始・停止だけを許し、設定変更は許さない。
- ローカル pipe は所有者と全 DACL を確認してから送信する。サーバーは実際の
  呼出元 SID で認可する。鍵は pipe 内だけを通り、引数・環境変数・ファイルには渡さない。

## 一度だけ管理者が行う作業

通常のプロジェクト端末で作る：

```powershell
.venv\Scripts\python.exe -m loop_engine.cli service-bundle
```

表示された `source_commit`、`manifest_sha256` と配備先を確認する。
出力の `admin_command` ファイルにある **ブロック全体をコピーして** 管理者の
64-bit PowerShell で実行する。ファイルには公開のパスとハッシュだけがあり、鍵は含まない。
単にそのファイルをスクリプトとして実行したり、`Invoke-Expression` で読み込まない。
ブロックは helper を期待ハッシュで検証し、新しい Windows Temp ファイルへ移し、
読取ハンドルで変更・削除を防いでから Windows PowerShell を起動する。
実行ポリシーを迂回しない。ポリシーで拒否された場合は止めて報告する。

成功時の公開 JSON は `installed=true`、`mode=prepare`、`activated=false`。
失敗時の stage と reason だけを共有すればよい。パスワード・PEM は共有しない。
部分配備後に再実行しても自動修復しない。残存物を調査してから復旧手順を決める。

### 現在の部分配備

所有者の実行は `accounts` で停止した。通常権限での観測では Review アカウントが
存在し、Merge アカウント・両サービス・Review プロファイルは未作成。
配備先は存在する。生成パスワードは保存しない設計のため、プロセス終了後に
そのパスワードを取り出して再開することはできない。既存物を削除したり、
アカウントを名前だけで自動採用してパスワードを変更したりしない。
`Inspect-LocusLoopServiceAccounts.ps1` は読み取り専用の診断で、固定した2役割の
存在、公開SID、プロファイル登録、3つのログオン権限、API戻りコードだけを返す。
鍵・パスワードの読取、アカウント/権限/サービス変更、外部通信は行わない。
通常権限の権限一覧読取は Access Denied だった。管理者の診断結果を待って
失敗したAPIを絞り、その後に明示的な既存物確認付きの復旧手順を用意する。

管理者の追加診断で、Review の3ログオン権限すべて成功を確認した。
新しい [部分復旧経路](WINDOWS_SERVICE_RECOVERY.md)は旧 manifest と Review SID を
固定し、未使用アカウントのパスワードだけを再生成する。通常の installer 再実行とは別。

## 配備後に通常端末で検証する作業

```powershell
.venv\Scripts\python.exe -m loop_engine.cli service-health
.venv\Scripts\python.exe -m loop_engine.cli service-provision review
.venv\Scripts\python.exe -m loop_engine.cli service-provision merge
.venv\Scripts\python.exe -m loop_engine.cli service-policy
```

既存の Windows Credential Manager の鍵をメモリ内で取り込み、各サービス利用者の
Credential Manager に保存する。PEM の再入力は不要。応答不明の取込みは intent を
保持して再送を拒否する。元の鍵・GitHub Secrets はこの手順では削除しない。

health では実 SID、配備ハッシュ、他方の vault 鍵不在、他方状態領域の読取拒否、
sealed ソースの書込拒否を実測する。別 SID での通信、SCM 起動/停止、再起動後の
資格情報永続化を含めた証拠は、実配備してから記録する。現在の同一 SID の kernel
試験を、その証拠として扱わない。

## 残る稼働条件

保護 DB に結合した独立レビュー authority、公開/merge の Controller 接続、承認付き
凍結仕様移行、writer 制限の実証、障害/権限取消/復旧試験、連続実運転、最終監査と
所有者の稼働承認が別途必要。[要件一覧](UNATTENDED_READINESS.md)を参照する。
この配備だけで無人ループが完成したとは判定しない。

公開仕様：
[Named pipe ACL](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)、
[SCM の権限](https://learn.microsoft.com/en-us/windows/win32/services/service-security-and-access-rights)、
[Python 3.14.10](https://www.python.org/downloads/release/python-31410/)。
