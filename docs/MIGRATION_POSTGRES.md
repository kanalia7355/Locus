# SQLite から PostgreSQL への移行手順（`DATA-013`）

本書は、開発・プロトタイプ用の SQLite ストアから本番用の PostgreSQL ストアへデータを移行する手順と、現時点での検証範囲・未実施事項を記載する。

> **重要**: このリポジトリおよびオフライン検証環境には稼働中の PostgreSQL 実機と `psycopg` ドライバが含まれていないため、**本番 PostgreSQL 実機での疎通・移行確認は未実施である**（末尾の「実機で行う残りの確認（未実施）」を参照）。

---

## 1. アーキテクチャと Engine 選択規則

`Service` は `backend/app/storage.py` の `StorageEngine` プロトコルを介して DB にアクセスする。

- **`LOCUS_DATABASE_URL` 未設定（既定）**:
  - 従来どおり `SqliteEngine`（既定パス `storage/locus.sqlite3`）を使用する。開発環境の挙動は一切変わらない。
- **`LOCUS_DATABASE_URL` 設定時**:
  - `backend/app/storage_postgres.py` の `PostgresEngine` を選択する。
  - `psycopg` ドライバは `PostgresEngine.connect()` の内側で遅延 import される。
  - 起動時（`create_app()` および `PostgresEngine` 初期化時）に `validate_database_url()` が接続文字列を検証する。
    - 空文字、`sqlite:` や `http:` 等の非 PostgreSQL スキーム、データベース名欠落は拒否する。
    - 接続先ホストは loopback（`127.0.0.0/8`, `::1`, `localhost`）、プライベート LAN アドレス（`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7`）、ローカル Unix ドメインソケット、または社内ホスト名（単一ラベルホストまたは `.internal` / `.local` / `.lan` / `.corp` / `.intranet`）のみを許可し、パブリック IP や外部クラウドホストは拒否する。
    - 検証エラーおよび接続エラーのメッセージにはパスワードを含めない（`redact_database_url()` によりマスクする）。
  - `ALLOW_CLOUD_EGRESS` / `LOCAL_ONLY_MODE` のローカル専用ガードは緩和しない。

### 方言・型の対応方針

- **プレースホルダ**: `?` → `%s`（文字列リテラル・識別子・コメント内の `?` は保持）。
- **列型**:
  - `INTEGER` → `INTEGER`（真偽値として扱っている `0`/`1` 列を含む）
  - `TEXT` → `TEXT`（`documents.grants` 等の JSON 文字列列を含む）
  - `REAL` → `DOUBLE PRECISION`（Unix エポック秒の `float` をそのまま保持し、`timestamptz` には変換しない）
- **競合無視・Upsert**:
  - `INSERT OR IGNORE INTO ...` → `INSERT INTO ... ON CONFLICT DO NOTHING`
  - `INSERT OR REPLACE INTO ...` → 主キー列に対する `ON CONFLICT (...) DO UPDATE SET ...`
- **トリガ**:
  - SQLite の `CREATE TRIGGER ... BEGIN ... END`（`membership_role_insert` / `membership_role_update` / `membership_role_delete`、委任失効トリガ、監査追記専用・ハッシュ連鎖トリガ）は PL/pgSQL 関数 + `CREATE TRIGGER ... FOR EACH ROW EXECUTE FUNCTION ...` に変換する。
- **トランザクション分離レベル**:
  - `BEGIN IMMEDIATE` → `BEGIN ISOLATION LEVEL SERIALIZABLE`。
  - `serialization_failure`（SQLSTATE `40001`）発生時は**自動再試行せず** `StorageError` として送出し、呼び出し側の 5xx 応答に委ねる（監査行や副作用の二重実行を防ぐため）。
- **列メタデータ照会**:
  - `PRAGMA table_info(...)` → `information_schema.columns`（`table_schema = current_schema()`）への問い合わせに変換する。

---

## 2. 検索方式の扱い（本ジョブのスコープ外）

現在の語彙検索（`Service.send()` の文字 2-gram + 単語一致、`Service.related()`、`Service.documents()`）は SQLite FTS5 ではなく **Python 側の照合**で実装されている。そのため、ストレージエンジンを SQLite から PostgreSQL に切り替えても検索結果の挙動は変わらない。

PostgreSQL の全文検索（`tsvector`）およびベクトル検索（`pgvector`）の採用（`DATA-013` の索引技術部分）は**別ジョブ**のスコープであり、本手順・本実装には含めない。

---

## 3. スナップショット移行手順

`backend/app/storage.py` に engine 非依存のスナップショット関数を用意している。

- `export_snapshot(engine) -> dict`:
  - 外部キーの親→子順序（`SERVICE_SNAPSHOT_TABLES`、および Plane-R テーブルが存在する場合は `OPTIONAL_SNAPSHOT_TABLES`）に従って全テーブル・全行を読み出し、テーブルごとの件数（`counts`）、正規化 JSON の SHA-256 チェックサム（`checksums`）、全体チェックサム（`overall_checksum`）を含む辞書を返す。
  - `documents.grants` などの JSON 文字列列、`chunks.text` の本文、`audit` / `audit_chain` / `audit_chain_head` の全行を欠落なく保持する。
- `validate_snapshot(snapshot)`:
  - 必須テーブルの欠落、件数不一致、チェックサム不一致を検査し、異常時は `StorageError` を送出する。
- `import_snapshot(engine, snapshot) -> dict`:
  - スナップショットを検証したうえで、スキーマ初期化済みの空のターゲット engine に外部キー順序で全行を投入し、最後に `verify_snapshot(engine, snapshot)` で移行後の件数と SHA-256 チェックサムの一致を検証する。

### 手順ステップ（メンテナンスウィンドウ内）

1. **アプリケーションの停止とバックアップ取得**
   - Locus API ワーカーを停止し、書き込みが発生しない状態にする。
   - 既存の `storage/locus.sqlite3` のファイルコピーを保全する。

2. **SQLite からのスナップショット書き出し**
   ```powershell
   python -c "import json; from pathlib import Path; from app.service import Service; from app.storage import export_snapshot; svc = Service(Path('storage/locus.sqlite3')); snap = export_snapshot(svc._engine); svc.close(); Path('storage/migration_snapshot.json').write_text(json.dumps(snap, ensure_ascii=False), encoding='utf-8'); print('exported tables:', len(snap['tables']), 'overall_checksum:', snap['overall_checksum'])"
   ```
   - 書き出した `migration_snapshot.json` には利用者ハッシュや資料本文が含まれるため、権限を制限しリポジトリには絶対にコミットしないこと。

3. **PostgreSQL 側の空データベース準備とスキーマ初期化**
   - 社内ネットワークまたはローカルホスト上に空の PostgreSQL データベースを用意し、`psycopg`（3 系）を導入した本番実行環境で `LOCUS_DATABASE_URL` を設定する。
   - `Service` を一度起動して空スキーマ・トリガ・関数を適用する。

4. **PostgreSQL へのスナップショット投入と件数・チェックサム検証**
   ```powershell
   $env:LOCUS_DATABASE_URL = "postgresql://locus_app:<PASSWORD>@127.0.0.1:5432/locus"
   python -c "import json; from pathlib import Path; from app.service import Service; from app.storage import import_snapshot; snap = json.loads(Path('storage/migration_snapshot.json').read_text(encoding='utf-8')); svc = Service(Path('storage/unused.sqlite3')); result = import_snapshot(svc._engine, snap); print(result); svc.close()"
   ```
   - `import_snapshot()` は内部で `verify_snapshot()` を呼び出し、全テーブルの行数と SHA-256 チェックサムが元データと完全一致しない限り `StorageError` で失敗する。

5. **監査ハッシュ連鎖の整合性確認とスナップショットファイルの安全な削除**
   - 管理者 API `GET /api/admin/audit/integrity`（または `Service.verify_audit_chain()`）を実行し、`{"ok": true}` と `checked` 件数が `audit` 行数と一致することを確認する。
   - 一時作成した `storage/migration_snapshot.json` を削除する。

---

## 4. 実機で行う残りの確認（未実施）

本リポジトリには稼働中の PostgreSQL インスタンスおよび `psycopg` パッケージが存在せず、オフライン開発規約により外部通信・新規パッケージ導入を行わないため、**以下の項目は未実施であり、実機環境が用意された段階で検証する必要がある**:

1. **実機接続（`psycopg` ドライバ経由の疎通確認）**:
   - `pyproject.toml` への `psycopg` 依存追加（オーナー判断待ち）と、実稼働 PostgreSQL への接続・認証・TLS 接続確認、および `LOCUS_DATABASE_URL` を設定した状態での `pytest tests/test_storage_seam.py` 契約テスト実行。
2. **`SERIALIZABLE` 分離レベル下での同時実行挙動**:
   - 複数ワーカーまたは並行リクエストが競合した際に PostgreSQL が返す `serialization_failure`（SQLSTATE `40001`）の頻度、ロック競合、および呼び出し側での 5xx 応答・監査記録の挙動確認。
3. **トリガ移植の等価性（実機 PL/pgSQL 実行）**:
   - `membership_role_insert` / `membership_role_update` / `membership_role_delete`、委任失効トリガ群、追記専用トリガ、および PL/pgSQL 版 `audit_sha256()` 関数が実機 PostgreSQL 上で Python 側の `_audit_hash_payload()` とあらゆる浮動小数点時刻値で完全一致するハッシュを生成することの実機検証。
4. **全文検索・ベクトル検索の未着手**:
   - PostgreSQL の `tsvector` による全文検索および `pgvector` によるベクトル検索への移行は未着手であり、別ジョブで設計・実装・検証を行う。
