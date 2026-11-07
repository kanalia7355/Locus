# services 段階からの登録完了

2026-11-01。旧 installer / 部分復旧ブロックを再実行しない。
現在は両アカウント、固定 runtime、設定と状態 ACL が存在し、両サービスは未作成。
両アカウントの LastLogon は空で、鍵移送は行われていない。

## 確認できた不具合

旧 `New-Object PSCredential('.\' + $account, $secure)` は、実際の Windows
PowerShell で PSCredential 型を返す一方、UserName が null になることを再現した。
以前の試験は型だけを確認し、ユーザー名の検証が不足していた。
明示的な `PSCredential::new` へ修正し、両役割・両 installer 経路で実際の
UserName と read-only SecureString を検証する試験を追加した。

## 対象と変更範囲

```powershell
.venv\Scripts\python.exe -m loop_engine.cli service-completion-bundle `
  --active-manifest <現在の配備manifestのSHA256> `
  --review-sid <確認済みReview SID> --merge-sid <確認済みMerge SID>
```

このコマンドは clean な同一 Git commit の installer 共通定義と completion template を
組み合わせ、自己完結した固定 helper とハッシュ付き manifest、管理者ブロックを作る。
コードを管理者で実行する前に生成物のハッシュを固定する。任意の外部ファイルを管理者で
dot-source しない。インタープリターや依存物の再取得・再配備は行わない。

管理者ブロックの実行は、**固定した両 SID の失われたサービス用パスワードを再生成し、
既存 runtime を使うサービス2つを作成する操作**である。SID、runtime、設定、状態、旧
intent は保持する。新しい source commit は helper の出自であり、既存 runtime の
source commit を最新版と偽装しない。両方の manifest hash を成功結果で区別する。
モードは prepare 固定で、鍵取込み・公開・merge・Controller 起動は行わない。

## 拒否する状態

- pin が不正・重複、operator/project/設定/役割/App ID が違う、prepare 以外の mode。
- 固定 runtime の全ファイル/ディレクトリ/ハッシュが違う、旧版や旧 intent が違う。
- SYSTEM 所有・保護 DACL、Sys/Admin の FullControl、operator/各役割の読取、
  各状態領域の役割専用 Modify 以外の権限がある。
- 既存サービス、アカウントのログオン歴・プロファイル・グループ所属・サービス利用。
- 状態領域に既知の合成 canary 以外がある。鍵取込み intent や既存データを含む。
- 既存 completion intent、未知の配備物、余分な空ディレクトリや変更された canary。

全 preflight 後、SYSTEM 専用の `service-completion-intent.json` を排他的に作成して
fsync する。パスワード変更直前にも使用状況を再取得する。別の管理者が同時に対象を
変更する運用は許容しない。途中失敗は保持し、同じ completion を再試行しない。
既存サービスを自動削除したり、再作成して応答不明を解消しない。

成功後は通常端末で health、鍵取込み、policy 読取を実測する。SCM が
[サービス利用者のプロファイルを読み込む](https://learn.microsoft.com/en-us/windows/win32/services/service-user-accounts)
仕様と、実際の起動・vault 永続化の証拠は区別する。

失敗結果は役割別 stage、例外型、HRESULT、取得可能な Win32 数値だけを返す。
例外メッセージ、引数、PSCredential、鍵・パスワードは出力しない。
秘密情報の再入力は不要。管理者操作が必要なのは現在のエージェント端末が非管理者のため。

この経路は新しい部分復旧 scope の最終（2回目）修正・再レビュー対象。
最終配備監査や無人稼働・自動マージ承認を代替しない。
