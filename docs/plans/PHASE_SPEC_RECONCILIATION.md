# Phase別仕様差分と統合条件

2026-11-06。基準: docs/planningの3文書・基準画像、PRODUCT_SPEC、ARCHITECTURE、ROADMAP。
これは未完了の機能を除外する計画ではない。試作版の承認範囲と製品完成条件を区別する。
Phase完了の宣言は、以下の不足解消、対応する独立レビュー、正確なHEADの全CI成功を必要とする。
新しい所有者指示によりPhase完了後のmainマージは許可されたが、未完了Phaseを
含む現在のPR #7全体を、そのままPhase完了の証拠とは扱わない。

| Phase | 仕様との照合・既存実装 | 未解消差分 | 完了を証明する検証 |
|---|---|---|---|
| 0 基盤 | FastAPI/React、固定依存、lint/types、Python/UI/browser、secret scan、Actionsあり。f316b4fはPush/PR両系統6実行12checks成功 | ホスト側の監査者権限制限は手続き的。保護API403で現在のmain保護を検証できない。ホスト側egress制限も未検証。開発Loop30分完走は未証明 | 必須ローカルQAと正確なHEADの全CI、実行境界・運用承認の確認。CI成功とLoop稼働は別判定 |
| 1 認証 | Argon2id、仮パスワード期限/一回性、初回変更、session失効/期限、rate limit。test_security/api/audit_regressions | 回復/MFA、本番TLS・session配備、Web利用者追加・停止操作が未完成。現状CLI provisioningとWeb一覧 | 初回変更/期限/失効/不正利用の回帰、回復方式確定後の否定系、実配備検証 |
| 2 認可・管理 | 組織/project境界、private履歴/添付、live資料grant、custom role作成/更新、subset制限、監査。test_custom_role_publication/role_updates/administration_audit | 期限付き委任は409で無効。Web所属/project管理、兼任/明示deny/元保存先ACL対応、期限・取消仕様が未確定または未実装 | 異なる利用者/組織/権限変更中の全データ経路、委任subset/scope/expiryと自己昇格拒否 |
| 3 資料・検索 | UTF-8 txt/md/csv256KiB、queue/cancel、lexical検索、実chunk出典、削除/失効。ClamAV任意adapter模擬検証。test_scanner/api/security | SQLiteは開発用代替で本番DB/保存分離/バックアップ復旧が未確定。保存先接続、フォルダ再帰一覧・件数/容量/対象外理由、PDF/OCR、元原本への導線、差分更新、再開/失敗分再処理、見積り/通知、vector検索。実ClamAV未検証 | 保存先→一覧→取り込み→質問→原本の代表シナリオ、変更/削除/ACL伝播、故障・再開・上限・実スキャナー |
| 4 UI・複数人利用 | 基準の配置/220ms/reduced-motion/SVG/IME/drop共通処理、状態/出典/private履歴、mobile browser検証。2026-11-06:単一model枠の前に到着順の対話待機列を実装。model使用中の質問は202で受付し、待機/実行中/完了/失敗/取消を表示、待機中のみ取消可、完了後の回答は会話履歴から取得（切断・再接続の結果取得）。待機上限300秒、全体16件・個人2件の開発用上限。既存の同步応答契約（model空き時200、検索のみ200）は不変 | 管理メニューのproject/保存先/負荷/保存削除画面不足。実行中質問の中断は不可（実行中表示のみ）。逐次表示なし。比較表の構造化表示なし。待機列の公平性は到着順のみで、優先度・利用者別分配は未対応 | 基準画像と現画面の比較、keyboard/mobile/long-name、複数人対話+取り込み負荷・切断取消、状態と通知の正確性。対話待機列の回帰: test_chat_queue 8件（取消・実行・所有者分離・session失効・上限・期限・再起動）とfrontend ChatQueue 3件 |
| 5 拡張 | 許可sourceの語句由来関連図、Ollama生成/保存/入力出典のいずれかが失効した場合に回答全体を非表示、model候補検出。test_related_documents/local_model/model_catalog | 意味的GraphRAG/graph index、plot/データ探索、cloud policy/router未実装。HFファイルは候補までで実行不可 | graph全探索ACL/根拠、plot入力/実行境界、provider別認可。承認済み合成Ollamaの成功はこれらを証明しない |

## 具体的な不整合の修正

App.tsx設定説明の「原文検索のみ」は任意Ollama生成実装と矛盾していたため、
既定は原文検索、管理者が明示有効化した場合のみ生成、と訂正する。
UI基準画像の表・PDF名・値はサンプルであり、その文言一致自体は受入条件にしない。
ただし実用的な比較/表表示やPDF原本参照が完成したとも扱わない。

## 実装順と判断が必要な箇所

1. 説明不整合を修正し既存UI QAを実行。既存の検証・入力契約は変更しない。
2. 各Phaseの既存機能を回帰確認し、製品要件に対する不足を独立レビューする。
3. 資料一覧・進捗UIなど承認済み範囲の不足を埋める。保存先の資格情報、
   元ACL対応、認証回復、管理委任、保存期間、LAN公開、cloud送信は既存の未決事項。
   これらを単なるPhase実装指示から自動確定しない。具体案と影響をまとめて確認する。
4. Phaseの仕様差分がなくなった時点で、独立レビューと全必須CIを確認してmainへ統合。
   競合・不明な保護状態・未解決重大指摘があればマージしない。

現時点で製品仕様全体に対する完了Phaseを新たに認定していない。
旧PHASE_STATUS冒頭の日付と表は初期試作範囲を表し、追記との時間差がある。
ADR0002の初期「modelなし・remote操作なし」は後続の個別承認で拡張された履歴であり、
現在のOllama/専用branch Push機能が未承認という意味ではない。

## 今回の検証

説明修正後のfrontend unit38 PASS、lint PASS、TypeScript/Vite build PASS、
Chromium実API E2E9 PASS。既存テストの削除・条件変更はない。
独立レビュー初回の文言指摘（入力の一件失効でも回答全体非表示）と、
本番DB/egress/復旧の照合漏れを修正。新しいHEADのCIはPush後に別途確認する。

## 2026-11-06 対話待機列の実装（Phase 4 差分の一部解消）

ui-and-multiuser-design.md の「対話の待機列：公平な順番・取消・期限」および
「切断後の処理継続・再接続時の結果取得・取消」に基づき、単一model枠の前に
到着順の待機列を実装した。

- backend: `chat_jobs` 表、`POST /api/conversations/{id}/messages` はmodel枠が
  空いている場合は従来どおり同期200を返し、占有中のみ202（job受付）を返す。
  `GET/DELETE /api/chat-jobs/{id}`（所有者限定、参照レート制限付き）。
  実行は既存の`svc.send`経由で、実行時に再認証・権限・添付・model設定を再確認。
  二重実行防止はstatus遷移の単一トランザクションで行う。待機中のみ取消可、
  実行中は取消不可を明示。待機上限300秒、全体16件・個人2件は開発用安全上限
  （取り込みqueueと同水準で、検証済み利用者能力ではない）。
- 再起動時は非終了jobを「再起動により中止」で失敗化し、待ち状態のまま残留させない。
  認証失効時はjob失敗理由に「ログイン状態が変わりました」を表示し送信しない。
- frontend: 送信が202の場合、質問の下に待機/実行中の状態行と（待機中のみ）
  取り消し操作を表示。既存のデザイン基準（装飾なし・role=status）を踏襲。
  2秒間隔の状態確認はunmount・ページ移動で中止し（会話の切替は継続）、
  失敗時は停止と案内を表示。完了時は同一会話なら回答を再取得、
  別会話なら履歴案内を通知。
- 既存の入力契約は不変: 検索のみ・model空き時の200応答、およびmodel利用中の
  429（LocalModel単体契約）は据え置き。queueは同期送信の失敗を待機列に置き換える
  唯一の経路として付加的に動作する。
- 検証: backend test_chat_queue 10件PASS（初回8件+レビューで判明した
  「枠が空く前に拾った場合は行列に戻る」回帰1件と「30回の連続再試行でも
  queued維持・課金1件・新規送信可能・解放後に完了」回帰1件）、既存test群を
  含む全backend suite（e2e除く）PASS、frontend unit46 PASS（新規3件含む）、
  lint/format/typecheck/build PASS、Chromium E2E10 PASS、secret scan 0件。
  実model・実複数人負荷の検証ではない。公平性は到着順のみ。
- 独立レビュー（読み取り専用、別fresh context）第1回: 重大指摘1件
  （model枠が空く前にworkerがjobを拾うと失敗化していた）と低重要度2件
  （enqueue時のレート制限二重課金、_fail_chatのstatusガード欠落）を修正し、
  回帰テストを追加。frontendの状態確認は会話切替では止めず、
  unmount・画面移動で中止する（別会話の完了通知のため）。
- 独立レビュー第2回の探針検証で新たな重大指摘1件を修正: 待機中の再試行が
  毎回ユーザー単位のチャット制限を消費し、約5秒で投入枠を使い切って
  ジョブを恒久失敗させていた。待ち行列からの実行では制限を課金しない
  （提出時に1回だけ課金）。workerはmodel枠の占有中は対話キュー処理を
  飛ばす（非取得の参考チェック、競合時は再行列経路で処理）。
  _fail_chatは実際に失敗化できたときだけ監査記録を書く。
