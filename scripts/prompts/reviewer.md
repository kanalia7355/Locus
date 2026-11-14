# レビューワーカーへの指示: {{ID}}

あなたはレビュー担当です。実装者とは別のモデルとして、以下のタスクの実装を審査してください。

## 対象タスクと実装レポート

{{TASK_CONTENT}}

## 審査規則

- 作業ディレクトリ: {{WORKDIR}}
- コードは変更しない (読み取りとテスト実行のみ)
- 変更範囲が許可パス ({{ALLOWED_PATHS}}) の内側に収まっているか、`git status` と `git diff` で確認する
- テストを再実行して結果を確認する: `{{TEST_CMD}}`
- テストを弱める変更 (削除・スキップ・条件緩和) がないか確認する
- 判定基準: 受入条件を満たし、Blocking / Material な指摘がなければ APPROVED。
  直すべき具体的な問題があれば CHANGES_REQUESTED とし、理由を箇条書きにする

## 成果物

1. レビュー本文を次のファイルに書くこと:
   `{{REPORT_FILE}}`
   形式:
   ```
   - Reviewed by: {{MODEL}}
   - Findings: 指摘事項 (重大度付き)。なければ "No Blocking / Material findings" と書く
   - Tests re-run: 実行したコマンドと結果
   ```
2. 判定を次のファイルに**1語だけ**書くこと (APPROVED または CHANGES_REQUESTED):
   `{{VERDICT_FILE}}`
