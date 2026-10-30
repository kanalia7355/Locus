# ローカル開発・検証の手順

本実装は合成データ専用の開発プロトタイプです。実研究資料を投入しないでください。製品全体の完成や本番運用の承認を示すものではありません。承認範囲と差分は [ADR 0002](architecture/decisions/0002-development-prototype.md) に記録しています。

## 環境

- Windows: Python 3.13、Node.js 22.16以上、npm。依存関係は `.venv` と `frontend/node_modules` に隔離。
- `backend/requirements.lock` と `frontend/package-lock.json` で解決済みバージョンを固定。
- Dockerの起動、PostgreSQL、外部モデル・サービスへの接続は不要。
- `scripts/setup.ps1` はパッケージレジストリとPlaywright配布先にアクセスします。既存文書を置換しません。

```powershell
./scripts/setup.ps1
./.venv/Scripts/python.exe scripts/verify.py --e2e --audit
```

Linux CIでは `python3.13 -m venv .venv`、`.venv/bin/python -m pip install -r backend/requirements.lock`、`cd frontend` で `npm ci` と `npx playwright install --with-deps chromium` を実行します。

## 初回アカウントと合成資料

アプリには既定の利用者・パスワードがありません。ローカル端末の管理者が対話式CLIで仮パスワードを設定します。パスワードを引数やコマンド履歴に書かないでください。

```powershell
$env:PYTHONPATH = 'backend'
./.venv/Scripts/python.exe -m app.cli project --project development --org development --name 検証用プロジェクト
./.venv/Scripts/python.exe -m app.cli provision --username local-admin --system-admin
./.venv/Scripts/python.exe -m app.cli assign --username local-admin --project development --role project_lead
./.venv/Scripts/python.exe -m app.cli seed-synthetic --username local-admin --project development
```

`seed-synthetic` は固定された合成テキストだけを投入します。ファイル指定や任意本文の引数はありません。`--shared` を付ける場合は、この検証用プロジェクトのproject_lead・researcher・viewerに閲覧とチャット参照を許可します。

新しい利用者も同じ `provision` / `assign` 手順で発行します。初回ログイン時に14〜128文字の新しいパスワードへ変更します。仮パスワードは24時間で失効し、一度ログインすると再利用できません。セッションは無操作30分・絶対8時間で失効します。パスワード変更時は他のセッションも破棄します。開発版にパスワード回復機能はありません。

## 起動

別々のPowerShellで実行します。

```powershell
./scripts/start-backend.ps1
```

```powershell
./scripts/start-frontend.ps1
```

ブラウザで `http://127.0.0.1:5174` を開きます。APIは `http://127.0.0.1:8000`。この端末では5173がOSにより使用不可だったため、フロントエンドを5174に固定しています。ポートを変更する場合はAPI・ViteのHost/Origin許可リストとブラウザテストも同時に変更してください。公開インターフェースへのバインドやプロキシ経由の運用は未承認です。

## 検証可能な操作

- ログイン、初回変更、ログアウト、所属プロジェクトの切り替え。
- 個人資料、ロールとプロジェクト範囲を限定した共有資料、本人だけの会話履歴。
- 合成サンプルへの「成膜条件」などの質問、原文抜粋と実際のページ・chunkの確認。
- ファイル選択・ドロップ添付、状態表示、個別取り外し。本文検査が未接続の場合は隔離し、検索・会話には使いません。
- プロジェクト内の非管理ロールのテンプレート選択・複製作成・操作チップ・適用範囲プレビュー。
- 本人が管理できる資料の明示的な公開先設定。会話添付は公開対象にできません。
- システム管理者の利用者一覧、本文を含まない監査メタデータ。

回答はローカルの語句検索からの引用です。LLM・埋め込み・ベクトル検索は実装しておらず、モデルの回答として表示しません。検索候補や出典は現在の権限で再評価し、履歴に原文抜粋を固定保存しません。

## データと制限

開発データは `storage/locus.sqlite3` に保存され、Gitの対象外です。SQLiteの暗号化、本番バックアップ、保持期間や復旧手順は未決です。削除操作はアプリ上の原文・索引・関連添付を削除しますが、ディスク上の安全な消去を保証しません。

通常のアップロードはUTF-8のtxt/md/csv・256 KiB以内。任意のスキャナをHTTPや環境変数から有効にする機能はありません。検査機能が未接続なら隔離します。PDF/OCR/NAS/Drive連携、ウイルス検査エンジンの本番接続、ローカルモデル、GraphRAG・分析プロット・クラウド接続は未実装です。

管理委任・回復・LAN公開は無効です。ブラウザCookieはローカルHTTP開発用で、本番のTLS/Secure Cookie設定はありません。外部AIへの通信経路はありませんが、配備環境の送信遮断は未検証です。開発機能の状態を本番の安全性認証として扱わないでください。

## 品質・監査

`scripts/verify.py` は失敗時に停止し、`.bootstrap/verification.json` に実行結果を保存します。`--audit` は依存関係のアドバイザリ照会でネットワークを使います。秘密情報のスキャンは `--no-verify` でオフライン実行し、検出値自体はログに出しません。合成テスト用パスワードだけを明示的に除外します。

CIファイルは用意していますが、GitHubへの接続・push・PR作成・保護ブランチ・必須チェック・マージは実行も検証もしていません。ローカルGitブランチは `chore/bootstrap-prototype` です。

実装は単一エージェント、別エージェントは独立した読み取り専用監査だけに限定しました。Codexのこの実行環境には、監査エージェントへのファイル権限・追加起動・使用量上限を強制する設定が公開されていません。その制約は手続き上のものであり、ランタイムで強制済みとは主張しません。Claude CLIの存在だけで、現在のCodexセッションへフックが適用されるとは扱いません。
