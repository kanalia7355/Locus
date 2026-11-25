# Phase `phase-storage-connect`: ストレージコネクタ（エクスプローラー／Google Drive／Box）

- **作成**: 2026-11-22（owner 依頼による計画起票）
- **接続対象（owner 決定 2026-11-22）**:
  1. **エクスプローラー** — Locus が稼働するマシン上のローカルフォルダ
     （Windows エクスプローラーで見えるフォルダ。以下「ローカルフォルダ」）
  2. **Google Drive**
  3. **Box**
- **位置づけ**: これは owner 決定 Q5（2026-11-09）で「後のフェーズに延期」とされた
  オンラインストレージ／ローカルフォルダ・コネクタを、上記3対象に限って
  前倒しで開くフェーズである。Q5 の他の対象（NAS 等）は引き続き延期。
  Q6（ソース側の権限喪失時は即アクセス拒否、保持／削除とは分離）は本フェーズでも維持する。

---

## 1. 現状確認（2026-11-22、main ブランチ実コードで確認済み）

| 対象 | 状態 |
|---|---|
| 取り込み経路 | 手動アップロードのみ。`Service.upload(actor, project, name, content, kind)`（`backend/app/service.py`）→ `documents` テーブル（status: queued）→ スキャン／索引 → 検索・引用 |
| 対応形式 | **UTF-8 テキスト（.txt / .md / .csv）、256 KiB 以内、ファイル名 160 字以内**。これが現行の取り込み制約であり、コネクタもこの範囲に合わせる（PDF 等の対応拡張は本フェーズの範囲外） |
| `documents` テーブル | `id / owner_id / project_id / kind / name / content / status / reason / conversation_id / grants / created`。**ソース（出所）を表す列がない**ため、出所管理は T-STC-001 で別テーブルとして追加する |
| スキャナ | `backend/app/scanner.py`（ClamAV 連携、fail-closed）。コネクタ経由の文書も必ずこの経路を通す |
| ローカルパスの安全検査 | `backend/app/model_catalog.py` に `reparse()`（リパースポイント検査）、`local_volume()`、`checked_directories()` が既にある。ローカルフォルダコネクタはこれを再利用する |
| ポリシー | workspace ポリシーに `destination_allowlist` / `egress_mode` / 分類上限がある（`backend/app/agents/registry.py`）。外部コネクタの可否はこの枠で制御する |
| コネクタ実装 | **存在しない**。R-STORAGE-1 タスクが「コネクタは実装しない（owner Q5 で延期）」と明記した上で手動アップロードを整備した経緯がある |

## 2. 共通設計（全タスク共通）

### 2.1 コネクタ共通インターフェース

各コネクタは次の2操作だけを持つ（同期エンジンが残りを担う）:

- `list_items(cursor) -> (items, next_cursor)`:
  対象フォルダ配下の項目を列挙する。各項目は
  `{external_id, name, revision（版を表す値）, content_hash, size, modified_at}`。
- `fetch_content(external_id) -> bytes`:
  項目の内容を取得する。**書き込み・削除は行わない（読み取り専用）**。

差分検知はプロバイダ固有の版情報を使う:
ローカル = mtime＋SHA-256、Google Drive = `headRevisionId`／`md5Checksum`、
Box = `sha1`／`file_version`。
（計画は当初 Drive の Changes API の page token も挙げていたが、`T-STC-003` の本文は
将来の最適化として採らないと書いている。**本文が正しい** — 2 つの指示が食い違うと
ワーカーは本文を採るので、計画側を本文に合わせた。page token 方式は採らない。）

### 2.2 同期エンジン（T-STC-001）

- 列挙 → 対応形式フィルタ（.txt/.md/.csv、UTF-8、256 KiB）→
  未登録または revision 変化ありのものだけ取得 →
  **`Service.upload()` を経由して**登録する（ACL・上限・監査・スキャンを迂回しない）。
- 出所は新テーブル `document_origins` に記録する:
  `document_id, connector_id, external_id, external_revision, content_hash, source_label, synced_at`。
  `documents` 本体のスキーマは変更しない。
- 対象外形式・上限超過は「スキップ」として件数のみ記録する（内容は記録しない）。
- 同期は手動トリガー（管理API）から開始し、定期実行は本フェーズでは行わない。

### 2.3 認証情報の扱い（AI接続フェーズと同原則）

- 資格情報の**値を DB・API応答・監査・画面に出さない**。管理画面は presence のみ。
- Google Drive / Box とも、初版は **サービスアカウント方式**とする
  （対象フォルダをサービスアカウントに共有する運用）。
  ユーザー個別 OAuth は refresh token の保持先が新たな設計判断になるため本フェーズの範囲外。
  - Google Drive: サービスアカウント JSON キーはサーバ上のファイルパスを
    環境変数で指す。スコープは `drive.readonly` のみ。
    JWT 署名には既存依存の `cryptography` を使い、新規 SDK 依存を増やさない
    （REST API を httpx で直接呼ぶ）。
  - Box: CCG（Client Credentials Grant）。client ID / secret は環境変数。
    Box 管理者によるアプリ承認が前提条件（owner 側の手続き）。

### 2.4 境界（変更不可）

1. **読み取り専用**：どのコネクタもソース側への書き込み・削除・共有変更を行わない。
2. **取り込み経路を迂回しない**：全コンテンツは `Service.upload()` と
   スキャナ（fail-closed）を通す。コネクタ都合で ready に直接しない。
3. **権限喪失は即拒否（Q6）**：同期時にソース側で消えた／権限を失った項目は、
   対応する Locus 文書への読み取り・検索・引用を拒否する。
   物理削除（保持ポリシー）は別判断とし、本フェーズではアクセス拒否まで。
4. **分類ポリシー先行**：workspace の分類上限・egress が許可しない接続は
   設定・同期とも拒否し、監査に残す。
5. **`loop_engine/**` を変更しない**（ガバナンス文書による）。
6. **対応形式を広げない**：PDF・Office 形式の取り込みは本フェーズの範囲外。
   ただし Google Docs 形式のファイルは Drive の export（text/plain）で
   テキスト化できる場合に限り対象とする（T-STC-003）。

## 3. タスク一覧

| ID | タイトル | 状態 | 依存 |
|---|---|---|---|
| T-STC-001 | コネクタ共通基盤（IF／出所テーブル／同期エンジン／管理API） | todo | なし |
| T-STC-002 | ローカルフォルダ（エクスプローラー）コネクタ | todo | T-STC-001 |
| T-STC-006 | 一覧が途中で失敗したときに取消を走らせない守りの退行テスト | todo | T-STC-001 |
| T-STC-003 | Google Drive コネクタ（サービスアカウント／読み取り専用） | todo | T-STC-001 |
| T-STC-004 | Box コネクタ（CCG／読み取り専用） | todo | T-STC-001 |
| T-STC-005 | 管理画面UI＋権限喪失時のアクセス拒否の統合検証 | todo | T-STC-002〜004 |

## 4. 完了条件（フェーズ）

1. 管理者が3種のコネクタを設定し、対象フォルダから対応形式の文書を
   Locus のプロジェクトへ取り込める（手動アップロードと同じ検索・引用ができる）。
2. 再同期で変更のない文書が二重登録されない。変更された文書は新しい版として扱われる。
3. 資格情報の値が DB・API応答・ログ・画面のどこにも現れないことがテストで検証されている。
4. ソース側で削除／権限喪失した文書が、Locus 側で即座に参照できなくなる（Q6）。
5. 手動アップロードの既存挙動に退行がない。

## ORCHESTRATOR — 巡回対象に入れる前に配管を直した (2026-11-22 15:10)

オーナーの指示（2026-11-22）により、本フェーズを監督の巡回対象に入れた。
入れる前に、**5 票すべてが 1 試行も通らない状態**だったのを直した。
設計・受入条件・境界は 1 行も変えていない。詳細は各票の末尾の節にある。

| 直したもの | なぜ致命的だったか |
|---|---|
| `test_cmd` の `.venv313/Scripts/python.exe` → 素の `python` | `.venv313` は `.gitignore` で無視されジョブのクローンに無い（実測）。束縛されるのは**先頭が素の `python`** のときだけ。直前の状態なら 5 票 15 試行が全滅していた |
| `depends_on` を frontmatter に追加 | 依存は本文と上の表にはあったが、コントローラは frontmatter しか見ない。土台（`T-STC-001`）より先に派遣されていた |
| `T-STC-003` / `004` の `allowed_paths` から `pyproject.toml` を削除 | 保護パスなので票に何と書いてもジョブからは書けない。「許可してある」と書いた票は phase-8 で 3 件のジョブを失わせた |
| `model: unassigned` → `-` | 他フェーズと表記を揃えた |

**オーナー側の前提手続きが残っている**（コード外・これが無くても実装とテストは進む）:
Google Cloud で Drive API を有効化しサービスアカウントと JSON キーを発行、
対象フォルダをそのアカウントへ共有（`T-STC-003`）。Box は管理者によるアプリ承認（`T-STC-004`）。
**テストはすべてモックで完結する**設計なので、鍵が無くてもフェーズは完了まで進める。
実環境での疎通確認だけが鍵待ちになる。
