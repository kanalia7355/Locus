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
| 4 UI・複数人利用 | 基準の配置/220ms/reduced-motion/SVG/IME/drop共通処理、状態/出典/private履歴、mobile browser検証 | 管理メニューのproject/保存先/負荷/保存削除画面不足。公平な対話queue/待機取消/再接続結果取得/監視なし。同時model1件で競合429。逐次表示なし。比較表の構造化表示なし | 基準画像と現画面の比較、keyboard/mobile/long-name、複数人対話+取り込み負荷・切断取消、状態と通知の正確性 |
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
