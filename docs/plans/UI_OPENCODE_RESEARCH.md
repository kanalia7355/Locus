# UI 研究：OpenCode 実装調査とチャット中心 UI 設計

記録日：2026-11-11
スロット：V-UI-OPENCODE RESEARCH（研究・設計のみ。本スロットで UI コードは変更しない）
状態：設計参照用。実装は別スロットで承認済み範囲から実施する。

## 0. 参照情報

- 対象：github.com/anomalyco/opencode の `dev` ブランチ
- 固定コミット：`59ed43f0b8da891f03a7333d540a7b0c428049ea`（`git ls-remote` で取得した dev 先端を浅いクローンして読んだ。参照日 2026-11-11）
- 参照範囲：`packages/app`、`packages/ui`、`packages/session-ui`、`packages/desktop`、各パッケージの `AGENTS.md`
- ライセンス：`packages/ui/LICENSE` およびリポジトリルートの `LICENSE` は **MIT License, Copyright (c) 2025 opencode**。本スロットでコードを直接再利用した箇所は**ゼロ**（設計参照のみ）。将来の直接再利用時は「9. 直接コード再利用時の記録」の形式で記録する。
- 通信範囲：この公開リポジトリの読み取りのみ。その他の外部通信は行っていない。

## 1. OpenCode 調査結果

### 1.1 全体構成

OpenCode は Bun + SolidJS + Effect のモノレポで、UI を 3 層に分離している。

| 層 | パッケージ | 責務 |
|---|---|---|
| デザインシステム | `packages/ui` | 基本部品（card、collapsible、context-menu、file-icon、animated-number、text-shimmer、spinner、error-details など）、アイコン、モーション、テーマ、i18n、typography。`data-component` / `data-slot` 属性と CSS カスタムプロパティで構成 |
| 会話レンダリング | `packages/session-ui` | タイムライン投影（`timeline/projection.ts`）、メッセージ部品（`message/current-message.tsx`）、ツール表示（`tools/tool-renderer.tsx`、`tool-status-title`、`tool-count-summary`）、Markdown ストリーミング（`markdown-worker.ts`、`markdown-stream.ts`）、添付カード（`attachment-card.tsx`） |
| アプリシェル | `packages/app` | セッション管理（`session/`）、コンポーザ（`composer/`）、サイドバー・タブ（`shell/`）、モデル選択（`providers/models/`）、設定、デスクトップ統合 |

`packages/desktop` は Electron（main / preload / renderer、MessagePort RPC、永続化は SQLite）。本スロットでは参照のみ。

### 1.2 特徴的なパターン

1. **状態機械の徹底**（`packages/app/AGENTS.md`「State Machines」）：ライフサイクルは 1 つの判別可能なユニオン型と純粋な `transition(state, event)` で表現。ブール値や nullable の「実行中」フラグを禁止。`attempt` id を状態に持たせ、遅れて到着した結果を破棄。副作用はエッジのドライバで実行し、結果はイベントとして返す。前例：`composer/machine.ts`、`attachments/upload-machine.ts`、`model-chip-machine.ts`、`timeline/turn-phase-machine.ts`。
2. **タイムライン投影**（`session-ui/src/timeline/projection.ts`、1200 行）：メッセージ列 → 表示行の純粋な投影。ユーザー発言・アシスタント部品・ツールグループ・通知を安定キー付きの行に変換し、行単位でメモ化。ストリーミング中の更新が全体の再描画を起こさない。
3. **ツール実行表示**（`tools/tool-renderer.tsx`、2700 行）：`read/list/glob/grep/browser/webfetch/websearch/subagent/shell/execute/edit/write/patch/question/skill` の各ツール種別に対応。`tool-status-title` は実行中→完了のタイトルを共通接頭辞の分割でアニメーション遷移（`prefers-reduced-motion` 対応あり）。`tool-count-summary` は実行済みツール数をカウント表示。`tool-error-card` は失敗を明示。読み取り系ツールのグループ化で開閉状態を管理。
4. **ストリーミング描画**：Markdown 解析を Web Worker に分離し、増分レンダリング。`paced-text-machine` で文字の表示速度を制御。`turn-phase-machine` でターン（思考・実行・回答）の段階を表現。
5. **コンポーザ**（`composer/machine.ts`）：`idle / held / running / preparing / handing-off` の送信状態機械。送信中も下書きを保持し、失敗時は復帰。`model-chip-machine` はカタログ未ロード時に 10 秒の猶予でクリックを延期し、タイムアウトを明示。
6. **添付**（`composer/attachments/upload-machine.ts`）：アップロードはプロセス全体で管理（コンポーザを閉じても継続）。60 秒の停滞タイムアウト、ドラフト単位のスコープ、進捗付きエントリ。
7. **セッション管理**（`session/`）：カーソルページングのセッション一覧、複数セッションのタブ、fork / revert / delete の各状態機械、参照メニュー。
8. **モデル切替**（`providers/models/`）：セッション単位のモデル選択。コンポーザ内のモデルチップ → 検索付き選択ダイアログ、プロバイダグループ、エージェントとモデルの分離。
9. **セキュリティの注意**（`packages/app/AGENTS.md`「Insecure Origins (HTTP LAN)」）：プレーン HTTP の LAN 配信を前提に、`crypto.randomUUID()` など `[SecureContext]` 専用 API をレンダラで直接呼ばない、非 SecureContext でフォールバックを用意する、という規律が明文化されている。
10. **その他**：i18n キーの強制（英語文字列の直接記述を禁止）、Suspense ガード、`strobe` によるベンチマーク、`prefers-reduced-motion` の尊重。

## 2. 比較表

| # | OpenCode パターン | Locus 現状 | 判定 | 理由 |
|---|---|---|---|---|
| 1 | 3 層分離（ui / session-ui / app） | `App.tsx` 1979 行 + フラットなコンポーネント群（`AdminSettings`、`Delegations`、`IngestionProgress`、`ModelRuntime`、`ModelSettings`、`ProvisionUser`、`RelatedDocuments`、`StructuredCitationText` など） | 適応 | チャット領域を既存の React 構成内で `ChatView` / `ChatMessage` / `ChatComposer` などへ分離する。新パッケージは作らず、`packages/ui` 相当のデザインシステムは作らない（基準見た目を維持するため） |
| 2 | 状態機械（純粋 transition、attempt id、遅延結果の破棄） | `useState` の boolean と `busy` フラグの散在 | 適応 | チャット送信・ジョブポーリング・添付に React で同じ規律（判別可能なユニオン + 純関数 + 遅延結果の破棄）を適用。ライブラリ不使用 |
| 3 | タイムライン投影（安定キー付き行） | `messages.map` による全体描画 | 適応 | メッセージ列を投影関数で行に変換し、キーで安定化。ポーリング更新時の再描画を最小化 |
| 4 | ツール実行表示（tool-renderer、status title、counts） | バックエンドにツールループが存在しない（RAG 検索 + 生成のみ） | 見送り | 存在しないバックエンド機能を「実行中」として描画することは禁止。ツールループが実装されるまでは、処理状態表示（§4.5）に統合して見せる。ツールループの実装は【要決定】 |
| 5 | Markdown ストリーミング（Worker、増分） | 同期生成（`svc.send`）または 202 キューイング + ポーリング。回答はプレーンテキスト | 見送り | バックエンドがストリーミングを提供しない限り実現できない。SSE などストリーミング導入は【要決定】 |
| 6 | ターン段階機械（turn-phase-machine） | `chat_job` の `status` ポーリング | 適応 | キューイング・実行中・完了・失敗・キャンセルを統一した処理状態表示（§4.5）に整理。バックエンドの既存 `status` 値をそのまま使う |
| 7 | コンポーザ送信状態機械（idle/held/running/preparing/handing-off） | `send()` で `busy` を立てるだけ | 適応 | 送信中も下書きを保持し、失敗時復帰する。既存の `Attachment` 状態管理と統合 |
| 8 | 添付のプロセス全体管理（停滞タイムアウト） | 添付は資料（`documents`）として作成し、`status`（queued/scanning/ready）を追跡 | 部分適応 | 既存の添付状態表示は実装済み（未解析・失敗・参照可能の区別あり）。バックエンドにアップロード進捗 API がないため進捗バーは見送り。停滞タイムアウトの概念は将来の参考 |
| 9 | モデル切替（セッション単位、モデルチップ、選択ダイアログ） | モデルはグローバル実行時設定（`ModelRuntime`、`/admin/models/runtime`）。管理者のみ変更可能 | 見送り | バックエンドが単一のグローバルモデルを前提とする。セッション単位の切替はバックエンド変更（モデル選択の保存・権限・カタログ）が必要で【要決定】。現状の表示は「モデル」を既存の回答フットノートに維持 |
| 10 | セッション一覧（カーソルページング）+ タブ | `history` ページ（会話一覧）と `openConversation`。サイドバーには会話一覧がない | 適応 | 会話履歴のサイドバー統合は**基準画面からの逸脱**（§4.2）。逸脱理由とともに【要決定】。ページングは既存 API で問題なし |
| 11 | fork / revert / delete の各状態機械 | 会話削除のみ | 見送り | fork / revert はバックエンド変更が必要。削除は既存実装を維持 |
| 12 | 参照メニュー・クォート | 出典（citations）パネルと原文参照（`openSource`）は実装済み | 見送り | 既存の `StructuredCitationText` + `RelatedDocuments` で要件を満たす。基準見た目を変更しない |
| 13 | デスクトップ（Electron） | ブラウザアプリ（LAN 配信） | 見送り | Locus は LAN デプロイのブラウザアプリ。スコープ外 |
| 14 | i18n キー規律 | 日本語の直接記述 | 見送り | 日本語単一の製品。i18n 框架の導入は不要 |
| 15 | `[SecureContext]` API の警備（`crypto.randomUUID` の回避） | `frontend/src/App.tsx:613` で `crypto.randomUUID()` を直接使用。開発は localhost だが LAN 配信はプレーン HTTP の想定 | 適応 | OpenCode と同じ問題の潜在バグ。LAN の非 SecureContext で TypeError になる。実装スロットで `uuid` 生成のフォールバックを導入（権限境界に影響しない小修正） |
| 16 | デザインシステム（data-component、トークン） | `styles.css`（1035 行） | 見送り | 基準画像の見た目を維持する。既存 CSS を段階的に整理しつつ、新規デザインシステムは作らない |
| 17 | 遅い動作の尊重（`prefers-reduced-motion`） | `styles.css:1006` で対応済み | 維持 | 既存実装を維持 |
| 18 | 管理メニューの権限応じた表示 | `user.system_admin` / `can()` による表示制御 | 維持 | 既存実装を維持。§5 のサーバー側認可の原則を継続 |
| 19 | Suspense ガード | Suspense を使わない React 19 | 適応 | 対応する課題はなく、ローディング状態の明示（§4.5）に統合 |
| 20 | 作業中インジケータ（`session-working-indicator`） | ポーリング中の処理状態は `ChatQueue` で表示済み | 適応 | 統一処理状態表示（§4.5）に含める |

## 3. ターゲットのチャット中心 UI 設計

### 3.1 原則

- 基準（`UI_IMPLEMENTATION_BASELINE.md` と `ui-baseline-chat.png`）を保存する。配置・アイコン・入力欄・操作は基準のまま。
- 逸脱は本文書に理由を書き、必要なものは【要決定】としてオーナー承認を得る。
- 未完成のバックエンド機能を完了として描画しない。ツールループ・ストリーミング・セッション単位モデル切替はバックエンドが実装されるまで表示しない。
- 開発モックと実行結果を区別する。現在の実行時はローカルモデル（`/admin/models/runtime`）で、`generate` が無い場合の表示は「モデルが有効になっていません」の既存メッセージを維持。

### 3.2 会話の描画（§2 の #1、#3、#7 を適用）

現在の `exchange` 構造（ユーザー発言は右寄り淡い背景、回答は本文、出典、フットノート）を維持する。改善点：

- `messages` を投影関数で「会話行」に変換し、`message.id` を安定キーとして使用する。ポーリングでの回答確定時は該当行のみ再描画する。
- `ChatView` / `ChatMessage` / `ChatComposer` にコンポーネントを分離する（`App.tsx` から抽出）。`App.tsx` の他のページは既存のまま。
- `ChatComposer` は送信状態機械（`idle / sending / preparing / queued / failed`）を持つ。失敗時は下書きを復帰する。既存の `attachment` 配列と `busy` フラグを統合する。

### 3.3 会話履歴（§2 の #10）

現状：サイドバーはナビゲーションのみ（`chat`、`shared`、`personal`、`history`、管理グループ）。`history` ページで会話一覧を表示する。

案：`history` ページを維持したまま、チャットページのサイドバーに「最近の会話」を追加する（OpenCode の `recent-sessions` に相当）。ただし、これは基準画面にない要素を加えるため**逸脱**である。

- 逸脱理由：OpenCode の会話操作（会話を開くたびにページを移動する）は、チャット中心の利用を妨げる。利用者は「資料を調べる」と「過去の会話」の間を移動する頻度が高い。
- 案の詳細：サイドバー内の「資料・調査」グループの下に、現在のプロジェクトの最近の会話を最大 10 件表示する（`GET /api/conversations` で取得済み）。選択は既存の `openConversation` を使用。`history` ページの機能は維持・削減しない。
- 判定：【要決定】（基準画面からの逸脱のためオーナー承認を得る）

### 3.4 添付（§2 の #8）

現状：プラス SVG アイコン、ファイル選択とドロップ、添付名と取り外しアイコン、処理状態（`uploading` / `queued` / `scanning` / `ready` / `failed` + `reason`）の表示は基準どおり実装済み。

追加の改善（承認済み範囲）：

- 添付の失敗状態を `document-row` と同じ視覚言語で統一（`statusName` と `reason` の表示）。
- 添付の取り外しは既存の `removeAttachment` を維持。
- 進捗バーは見送り（バックエンドにアップロード進捗 API がない）。

### 3.5 参照資料（§2 の #12）

現状：出典（citations）パネル、原文参照、`StructuredCitationText`、`RelatedDocuments` は実装済み。基準のまま維持する。

### 3.6 統一処理状態表示（§2 の #6、#20）

現状：`ChatQueue` でポーリング中のジョブを表示し、`cancelPendingJob` でキャンセル。`IngestionProgress` で取り込み状況を表示。

改善案：チャット画面の 1 か所で処理状態を統一表示する（OpenCode の `turn-phase-machine` + `session-working-indicator` + `tool-count-summary` に相当）。

- 状態：`queued`（待機中） / `running`（生成中） / `completed` / `failed`（`reason` 付き） / `cancelled`。
- 表示は「処理中」の 1 行 + `role="status"`（`aria-live` は既存の `messages` に維持）。
- 取り込み中の添付と処理中のジョブを同じ視覚言語で区別する（バックエンドの `status` 値をそのまま表示）。
- モデル名は既存の回答フットノート（`message.model`）を維持。セッション単位のモデル切替は表示しない（§4.4）。

### 3.7 モデル切替（§2 の #9）

現状：モデルはグローバル実行時設定（管理者のみ変更可能）。セッション単位の切替はバックエンドが対応していない。

案：**セッション単位の切替は表示しない**。バックエンドが対応するまで、コンポーザにモデルチップを置かない。

- 理由：未完成のバックエンド機能を完了として描画しない。
- 【要決定】バックエンドでセッション（または会話）単位のモデル選択を保存する仕様を入れる場合、`/api/conversations` に `model` を追加し、カタログを提供する。その場合に OpenCode の `model-chip-machine`（遅延ロードの規律）を参考にする。

### 3.8 権限の表示（§2 の #18）

現状：`user.system_admin` と `can()` による表示制御。管理メニューは権限に応じて表示。

改善案：`role` が `read` と `retrieve` に分かれる点を、チャットで明示する。`retrieve` がない場合の「参照範囲」セレクトは既存どおり、`can("retrieve")` が false の場合に「参照できる資料はありません」系の表示へ誘導する。基準のまま。

## 4. 管理者専用のループ進行状況可視化

### 4.1 現状

`loop_engine` は `StateStore`（SQLite）でタスク、実行、遷移、エビデンス、PR を記録する。`loop_engine/controller.py` が実行を管理する。**バックエンド HTTP API ではループ状態を提供していない**。管理画面（`load`、`ingestion`、`audit`）は Locus 製品の運用データ（チャット、資料、操作記録）であり、ループ状態ではない。

### 4.2 設計

- ループ状態は `loop_engine/state_store.py` の `StateStore`（SQLite）にあり、`tasks`、`task`、`transition`、`evidence`、`get_pr`、`get_checkpoint` で読める。
- 管理画面に「ループの進行」ページを追加する（`運用・記録` グループの下）。`system_admin` のみ表示。
- 表示内容：タスク一覧（`task_id`、状態、`attempt`、`effective_risk`、実行結果、PR の有無）、`phase` 進捗（計画・実装・検証・QA・レビュー・マージ）、レビュー・QA の結果（`evidence`、`get_pr`）。
- ループの実行状態は `loop_engine` の運用責任であり、UI は読み取り専用。UI から状態を変更しない。

### 4.3 サーバー側認可（必須）

- ループ状態の読み取りは `GET /api/admin/loop`（例）の新規エンドポイントで、`Actor` が `system_admin` であることを**サーバー側で**確認する。
- UI は `system_admin` のみで表示するが、表示はサーバー認可の上に成り立つ。サーバー側で拒否された場合、UI は「このページを表示する権限がありません」と表示する。
- ループ状態を含む読み取りは**権限の境界を変更しない**。`system_admin` は既存の管理権限と同じ。

### 4.4 判定

- 【要決定】バックエンドにループ状態の読み取りエンドポイント（`system_admin` 限定）を追加するか。ループ状態は Locus 製品の運用データではなく、開発運用の状態であり、`/api/admin` に露出する可否をオーナーが決める。
- 【要決定】エンドポイントを追加する場合、`StateStore` は SQLite で、バックエンドと同じファイルを開く並行アクセスの可否（`readonly` 接続）をオーナーが決める。

## 5. 利用者・管理者の表示権限分離（サーバー側認可必須）

### 5.1 原則

1. **表示は許可の写像**。UI はサーバーが返すデータに基づいて表示する。UI は権限を判定しない。
2. **サーバー側認可は必須**。管理画面のデータは、`system_admin` であることをサーバー側で確認する。UI はサーバーが拒否した場合は「このページを表示する権限がありません」を表示する。
3. **権限境界は変更しない**。チャットの `read` / `retrieve`、資料の `read` / `retrieve` / `upload` / `publish`、管理画面の `system_admin` は既存のまま。
4. **UI は権限不足を隠す**。`can("retrieve")` が false の場合、`retrieve` が不要な操作の表示を維持し、`retrieve` が必要な操作を表示しない。既存の `can()` による制御を維持。

### 5.2 現状の確認

- `user.system_admin` による管理メニューの表示制御：実装済み。
- `can("retrieve")` によるチャットの参照範囲制御：実装済み。
- `can("manage_roles")` による役割管理の表示制御：実装済み。
- サーバー側の認可は `Actor` と `Principal` で実装済み（`backend/app/service.py`）。権限チェックは `self._can_read(db, actor, ...)` で実装済み。
- 現状で問題点は見つかっていない。本スロットでは変更しない。

## 6. バックエンド・認証・RAG・権限・Loop-Engine 互換性注記

### 6.1 チャット API

- `POST /api/conversations/{conversation}/messages`（`backend/app/main.py:389`）：同期生成（`generate` あり）または 202 キューイング（`ModelBusy` の場合）。**ストリーミングは提供しない**。
- `GET /api/chat-jobs/{job}`（`backend/app/main.py:440`）：ジョブ状態のポーリング。`cancel` あり。
- UI は既存のポーリングを維持する。ストリーミングは【要決定】。

### 6.2 RAG と出典

- 検索は `backend/app/service.py`（`svc.send`）の `candidates` で、キーワードと日本語の文字 bigram のスコアリング。`citations` は `chunk` ベース。
- `send` は、回答生成の前後に、`_can_read`、`_conversation`、`_citations` で再検証する（権限の失効・変更を検出）。
- UI は既存の citations と出典の表示を維持する。`StructuredCitationText` と `RelatedDocuments` は変更しない。

### 6.3 認証

- `POST /api/auth/login`、`GET /api/auth/me`、パスワード変更、ログアウト（`backend/app/main.py`）。
- クッキー認証。`token` はモデル生成の再検証に使用する。
- UI は既存の `AccessForm` と `must_rotate` の処理を維持する。
- チャット送信時の `send` は、生成の前後に `_authenticate` で再検証する。UI の変更はこれに影響しない。

### 6.4 権限

- 権限は `read` / `retrieve` / `upload` / `publish` + プロジェクト役割。`_can_read` で実装。
- `system_admin` は管理権限。`manage_roles` は役割管理。
- 本スロットの変更は既存の権限に影響しない。新規の管理画面は `system_admin` 限定のサーバー側認可を必要とする（§4.3）。

### 6.5 Loop-Engine

- `loop_engine` は独立した運用状態（`StateStore`）を持ち、`loop_engine/controller.py` が実行を管理する。
- バックエンドとは **無関係**（`loop_engine` は Locus 製品 API にループ状態を提供していない）。
- ループ状態の可視化は【要決定】（§4.4）。

### 6.6 `crypto.randomUUID` の問題（§2 の #15）

- `frontend/src/App.tsx:613` で `crypto.randomUUID()` を直接使用している。
- 開発は `http://localhost:5174` で行う（`vite.config.ts`）。開発は SecureContext で動作する。
- LAN 配信（`http://` で非 localhost）は `isSecureContext === false` になるため、`TypeError` になる。
- OpenCode は同じ問題を明文規律で回避している（`packages/app/AGENTS.md`「Insecure Origins (HTTP LAN)」）。
- 承認済み範囲の実装として、`App.tsx` の `crypto.randomUUID()` をフォールバック付きの `uuid` 生成に置き換える（権限境界に影響しない小修正）。実装スロットで実施する。

## 7. 段階的実装計画

### 7.1 承認済み範囲で実施する（スロット W 以降）

1. **潜在バグ修正**：`crypto.randomUUID()` のフォールバック（§6.6）。権限境界に影響しない。
2. **チャットのコンポーネント分離**：`App.tsx` のチャット領域を `ChatView` / `ChatMessage` / `ChatComposer` に分離し、投影関数を導入（§3.2）。基準の見た目を維持。
3. **統一処理状態表示**：`ChatQueue` の処理状態を統一した表示に整理（§3.6）。既存の `status` 値をそのまま使用し、未完成のバックエンド機能を完了として描画しない。
4. **添付表示の統一**：添付の失敗状態を既存の `statusName` と `reason` で統一（§3.4）。
5. **モデル切替の表示**：セッション単位の切替は表示しない（§3.7）。現状の `message.model` のフットノートを維持。

### 7.2 【要決定】（オーナー承認が必要）

1. **会話履歴のサイドバー統合**（§3.3）：基準画面からの逸脱。オーナーが承認するか。
2. **SSE によるストリーミング**（§3.2 依存）：バックエンドの変更（生成 API の SSE 化、`chat_job` の接続）を含む。オーナーが決める。
3. **セッション単位のモデル切替**（§3.7）：バックエンドの変更（モデル選択の保存・カタログ・権限）。オーナーが決める。
4. **ツールループ**（§2 の #4）：バックエンドのツール実行（Locus 製品の RAG にツール実行を入れる）は本スロットの範囲外。オーナーが決める。
5. **管理者専用ループ進行状況の可視化**（§4）：バックエンドにループ状態の読み取りエンドポイント（`system_admin` 限定）を追加するか、SQLite の並行アクセスを許可するか。オーナーが決める。
6. **アップロード進捗の表示**（§3.4）：バックエンドにアップロード進捗 API を追加するか。オーナーが決める。

## 8. 直接コード再利用時の記録

本スロットでコードを直接再利用した箇所はゼロ。将来の直接再利用時は、以下の形式でファイルごとに記録する。

| 再利用ファイル | ライセンス | 著作権 | 依存 | 上流ソース |
|---|---|---|---|---|
| （例）`packages/app/src/composer/machine.ts` の状態機械 | MIT | Copyright (c) 2025 opencode | `@opencode/util/uuid`、SolidJS なし（純粋関数） | `https://github.com/anomalyco/opencode/blob/59ed43f0b8da891f03a7333d540a7b0c428049ea/packages/app/src/composer/machine.ts` |

- 再利用は MIT に基づき、著作権表示を保持する。`packages/ui/LICENSE`（MIT, Copyright (c) 2025 opencode）を参照。
- SolidJS に依存するコード（`createStore`、`createMemo` など）は、React に移植するため**直接再利用ではなく適応**（§2 の判定）。`packages/ui` はデザインシステムとして見た目を借りず、基準の見た目を維持する。
- `packages/ui` のコードをコピーする場合、`data-component` / `data-slot` 属性と CSS トークンを移植する意味が薄い（基準見た目を維持するため）。直接再利用は `packages/ui` を避け、`session-ui` / `app` の純粋関数（状態機械、投影）を優先する。

## 9. 制約遵守確認

- 権限境界の変更：なし（§5）。新規管理画面は `system_admin` 限定のサーバー側認可を前提とする。
- 外部通信・認証情報・エージェント実行：なし（§0）。ネットワークはこの公開リポジトリの読み取りのみ。
- 未完成のバックエンド機能を完了として描画：なし（§3.1、§3.7）。ツールループ・ストリーミング・セッション単位モデル切替は表示しない。
- 動作している機能の不用意な置き換え：なし（§3.2〜§3.5）。基準の見た目と既存の出典・添付・権限の表示は維持。
- 開発モックと実行結果の区別：なし（§3.1）。チャットの実行時はローカルモデル（`/admin/models/runtime`）で、`generate` が無い場合の表示は既存の「ローカルモデルが有効になっていません」のエラーメッセージを維持。
- 基準画面からの逸脱：§3.3（会話履歴のサイドバー統合）のみ。理由とともに【要決定】。
