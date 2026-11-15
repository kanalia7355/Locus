# harness-core — Locus ハーネスの心臓部

`.pi/extensions/harness/` の TypeScript 一式。Muse が作成し、型チェック済み。
ブートストラップ側（pi / agy）はこれを**生成せず、配置だけ**を行う。

## 配置方法

このフォルダの `.pi/` を Locus リポジトリのルートにそのままコピーする。

```
locus/
  .pi/
    extensions/
      harness/
        index.ts        ← pi extension のエントリ
        config.ts       ← 既定値 (ポーリング30分、Luna のモデル ID 等)
        state.ts        ← .pi/harness/state.json の読み書き・cooldown 管理
        poll.ts         ← progress/ の差分検出
        rotation.ts     ← 重み別モデル選択・枠枯渇の検出と切替
        testscope.ts    ← 変更ファイル → 関連テストの対応付け
        git.ts          ← worktree / コミット / CI 確認 / マージ
        runners/
          exec.ts       ← 子プロセス実行 (Windows の npm シム対応)
          codex.ts      ← Luna (オーケストレーター) 起動
          agy.ts        ← Antigravity ワーカー起動
          opencode.ts   ← OpenCode ワーカー起動
```

## 設計上の前提

- pi ホスト API との接点は `index.ts` だけ。想定している API は
  「default export 関数が ExtensionAPI を受け取り、`pi.on("session_start" /
  "session_shutdown")` と `pi.registerCommand()` を使う」という最小形。
  実機の pi 1.5.2 で API の形が違えば、直すのは index.ts だけで済む
- ロジック本体のモジュールはホスト非依存。`tsc --noEmit` で検証済み
- Windows では codex / opencode が npm シム (.cmd) のため、`runners/exec.ts` は
  win32 で shell 経由起動にしている

## 未検証・要確認 (BOOTSTRAP_TODO 候補)

- Codex の Luna モデル ID が `gpt-6-luna` で正しいか (config.ts で変更可能)
- agy の effort (low/medium/high) を CLI から指定する方法
  (現状は rotation.ts のメタ情報のみで、起動引数には含めていない)
- CI グリーン判定は `gh run list` の最新 run の conclusion で見ている。
  repo の workflow 構成によっては job 単位の確認に変える必要がある
- ワーカー起動 → サイクル完了 → コミットまでの自動連結は index.ts の
  将来の拡張点。現段階ではポーリングと Luna 起動までが自動化範囲
