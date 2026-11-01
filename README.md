# Research AI bootstrap v3

2026-10-29 更新。v2の内容を維持し、企画とUI実装基準を追加したパッケージ。

## 最初に読む文書

1. [今回の企画・アプリ構成](docs/planning/research-app-concept.md)
2. [UI実装基準](docs/planning/UI_IMPLEMENTATION_BASELINE.md)
3. [UI・添付・権限・複数人利用の設計](docs/planning/ui-and-multiuser-design.md)
4. [UI基準画像](docs/planning/ui-baseline-chat.png)

チャットはChatGPTに近い配置と操作を基準とする。SVGアイコンによるサイドバー開閉・添付・送信、新規会話、ドラッグ＆ドロップ添付を採用する。常設の操作案内文や入力欄の発光・強調枠は付けない。

共有保存先への接続は管理者が担当する。個人資料と会話添付は共有資料と分ける。公開先はロールと適用範囲で設定する。モデル・接続方式・同時利用性能は未確定で、デモの数値は能力の保証ではない。

## デモ参照ソース

`docs/planning/demo-source.fragment.html` は最終デモの参照用HTML断片。会話内のプレビュー環境用で、Reactアプリの実装や単体起動できるページではない。SVGアイコンはプレビュー環境のLucideを利用する。実装時はReactの同等コンポーネントに移す。外部接続・本文の読み取り・送信・権限制御・モデル実行は実装していない。

## 既存文書との関係

v2の開発・セキュリティ・運用文書は残している。画面の判断は今回追加したUI実装基準を参照し、古い見た目の案に戻さない。その他の未決事項は確定扱いにしない。元のZIP内にある初期化・インストールなどの手順は、今回の梱包作業では実行していない。

このZIPに認証情報や実際の研究資料は含めていない。基準画像とデモの資料名・回答・利用者はサンプル。

## ローカル検証用実装（2026-10-31）

上記は元の配布パッケージの説明。ユーザー承認により、合成データ専用のReact/FastAPI開発プロトタイプを追加した。起動・初回アカウント発行・検証は [開発手順](docs/DEVELOPMENT.md)、各段階の実装範囲と残件は [Phase状況](docs/plans/PHASE_STATUS.md) を参照。

実研究資料、本番運用、LAN公開、管理委任、外部AI接続は対象外。通常アップロードは検査機能が未接続なら隔離される。SQLiteと語句検索は開発用の差し替え可能な実装であり、本番のDB・ベクトル検索・モデル選定を確定しない。

## 自律開発Controller（2026-10-31追加）

2026-11-02の通常配送方針は [ローカルコミット＋開発ブランチへのPush](docs/LOCAL_COMMIT_PUSH_LOOP.md)。既存Controllerを使い、ローカルQA・独立レビュー後にコミットとPushを行う。PR・専用App・Broker・自動マージは必須としない。以下のApp/merge稼働手順は従来モード用であり、新モードの起動条件ではない。凍結済み設定の移行と実行境界の有効な検証は引き続き必要。

研究支援アプリと独立したPython CLI基盤を `loop_engine/` に追加。[完全指示書](docs/requirements/AUTONOMOUS_LOOP_SPEC.md)、[利用方法と未完了の実機ゲート](docs/LOOP_ENGINE.md)、[各Phaseの実装状況](docs/plans/LOOP_IMPLEMENTATION.md) を参照。ローカル・モック検証の成功を、実機での自律実行や安全な自動マージの完成とは扱わない。

専用 GitHub App / Merge Broker の設計は実装着手を承認済み。[登録手順と稼働前の残件](docs/BROKER_SETUP.md) を参照。App 登録と自動マージの稼働許可は別であり、現在はマージを保留している。

無人運転に必要な要件と実測・模擬検証の区別は [稼働準備一覧](docs/UNATTENDED_READINESS.md) を参照。
`python -m loop_engine.cli activation-readiness --live --pull 6` は現在の残件を読み取り専用で確認する。
