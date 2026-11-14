# 自律開発システム設計 レビュー報告レポート（ワーカー視点・v2 論点統合）

- **作成日**: 2026-11-13
- **レビュー担当**: Gemini 4 Hydrogen（light クラス・駆動される側ワーカー視点）
- **対象資料**:
  - [`docs/report/AUTONOMOUS_DEV_SYSTEM_DESIGN.md`](./AUTONOMOUS_DEV_SYSTEM_DESIGN.md)（Argon 第1・第2ラウンド統合設計書）
  - [`docs/plans/DESIGN-CONSULT-BRIEF-v2.md`](../plans/DESIGN-CONSULT-BRIEF-v2.md)（設計相談ブリーフ v2）
  - [`docs/plans/HYDROGEN-REVIEW-BRIEF.md`](../plans/HYDROGEN-REVIEW-BRIEF.md)（レビュー依頼ブリーフ）
  - 現行ハーネス実装: [`.pi/extensions/harness/`](../../.pi/extensions/harness/)

---

## 1. 総合評価

Argon による第2ラウンド統合設計（薄型ランナー ＋ `task-ctl` ＋ ステートレス `codex exec` ＋ 同期ワーカー）は、従来の「30分タイマー待ち」と「Markdown 本文の正規表現パースによるタスク消失」という2大敗因を的確に捉えており、**方向性として非常に合理的**です。特に `verdict_for: <attempts>.<review_round>` による古い `APPROVED` 誤認の防止と、`Allowed Paths ∩ git status` によるパス限定コミットは実事故に直結する有効な設計です。

一方で、**実際に駆動される light クラスワーカーの視点**および **v2 ブリーフの最新状況（Phase 2 進行中・GitHub Actions CI 不調・CRLF 事故）** に照らすと、このまま実装に入ると止まる・誤動作する「残存する穴」と「MVP として過剰な複雑さ」が複数残っています。本レポートではそれらを整理し、実装前の確定仕様として報告します。

---

## 2. 残っている穴と解消仕様（レッドチーム検証）

### 2.1 状態遷移の競合・未定義の組み合わせ

| # | 発見した穴 | 発生シナリオ | 解消仕様（実装前に決めるべき事項） |
|---|---|---|---|
| **H-1** | **初回 `todo → doing` 時の `attempts` 値が未定義** | §3.1 の例は `status: doing` で `attempts: 1` だが、Step 1 の `transition` 仕様では `qa-fail` のときだけ `attempts + 1` と書かれている。`attempts: 0` のまま進むと `verdict_for` が `0.1` になり上限判定が1回分ズレる。 | `todo → doing` の初回遷移時に `task-ctl` が **`attempts` を `0 → 1` にセット** し、以降のインクリメントは `qa-fail` 時または `review_round` 上限到達時のみ行うよう明記する。 |
| **H-2** | **`review_round` 上限到達時のリセット漏れ** | `CHANGES_REQUESTED` が2回続いて `attempts + 1`（`doing` へ戻す）になった際、`review_round` を `0` に戻す規定が抜けているため、次のレビューで `review_round` が `3` になる。 | `attempts` を `+1` して `doing` に戻す遷移（QA 差し戻し・レビュー2周上限のいずれでも）では、必ず **`review_round: 0`, `verdict: NONE`, `verdict_for: -` をセットで初期化** する。 |
| **H-3** | **`doing → review` の二重インクリメント** | Step 3 では「ランナーが `transition --to review` を叩く」、Step 4 では「プロンプトでワーカーに `task-ctl` を使わせる」とあり、両方が叩くと `review_round` が `0 → 1 → 2` に跳ぶ。 | **`status` / `review_round` の遷移権限はランナー専任に統一** する（ワーカーはコードとレポート出力のみ行い、状態遷移コマンドを叩かせない）。 |
| **H-4** | **Stage 1（`## REVIEW` 末尾10行正規表現救済）の逆流リスク** | レビュアーが `task-ctl verdict` を忘れた時の救済として「`## REVIEW` 末尾10行の `Verdict: APPROVED` を拾う」設計になっているが、前サイクルの末尾表記が残っていた場合に誤って今サイクルの判定として吸い上げる。 | **Stage 1（本文の正規表現救済）を廃止** し、後述の `--json-schema` 出力または構造化 JSON ファイルで判定を受け取る。取得できなければ Stage 2（`attempts` 据え置きで別モデル再試行）に倒す。 |

### 2.2 worktree と台帳ファイルの二重化（Source of Truth 衝突）

- **穴の内容**: 設計書 §2【穴2】では、ワーカーが `.pi/worktrees/<ID>` 内で作業・台帳更新を行い、QA 合格後にメインツリーへ `tasks/<ID>.md` をコピーする構成になっている。この結果、**作業中の最新 `tasks/<ID>.md` は worktree 内にしか存在せず、メインツリーの `progress/` は古いまま** になる。
  - メインツリー側で `task-ctl scan` を回してもワーカーの進捗（`review` / `verdict`）が見えない。
  - 途中で PC やランナーがクラッシュして再起動した場合、メインツリーだけ見ると「まだ `doing` で止まっている」と誤認する。
  - メインツリーに未コミットファイル（例: `docs/report/` 等）があると、`git checkout phase/<slug>` や `git merge --no-ff` が失敗してループ全体が停止する。
- **解消仕様**:
  - **MVP（直列1タスク運用）では worktree 分離自体を削り、`phase/<slug>` ブランチ上で直接作業してパス限定コミットを行う**（後述 §4）。これにより台帳の正本が1つになり、二重化・コピー漏れ・マージ失敗が消滅する。

### 2.3 停止条件の抜け

1. **GitHub Actions CI 枠切れ・外部障害時の無限停止 / 無限リトライ**:
   - [`DESIGN-CONSULT-BRIEF-v2.md`](../plans/DESIGN-CONSULT-BRIEF-v2.md) に記された通り、GitHub Actions が無料枠上限等で短時間失敗を続ける場合、`gh run watch` で CI green を必須ゲートにすると、コードとテストが完璧でも Phase 完了・停止ができなくなる。
   - **対策**: 「コード変更とローカルの関連／フルテスト全 PASS、および `phase/<slug>` への `git push` 完了」をもって **『技術完了・CI 確認保留（`main` マージのみ保留）』として安全停止** する分岐を設ける。
2. **Stagnation Breaker（連続3サイクル変化なし停止）の誤発火**:
   - 429 や無変更タイムアウトが3モデル連続で起きたとき、`status` もコミットも進まないため「停滞（空回り）」と誤判定され、次の有効モデルを試す前に停止してしまう。
   - **対策**: Stagnation カウンタは **「ワーカーが実際に編集または正常終了（非 Quota・非タイムアウト）したにもかかわらず前進しなかったサイクル」だけ** をカウントする。
3. **`git push` 失敗時の検知抜け**:
   - ユーザーの確認窓は GitHub であるため、ローカルでは全タスク `done` でも `git push` がネットワークや認証エラーで連続失敗（例: 3回）した場合は、「未同期（`push_failed`）」として明示エラー停止する条件を追加する。

---

## 3. ワーカー側（light モデル）の実行可能性と負荷軽減設計

light クラスのワーカー（`Gemini 4 Hydrogen` / OpenCode 無料モデル群）に課される作法の実行可能性を評価し、失敗率を下げる改善案を提示します。

| 作法 | 可否 | 失敗・忘れやすい場面 | ワーカー負担を下げる改善案（機械側へ寄せる） |
|---|---|---|---|
| **レビュー完了時の `task-ctl verdict` 実行** | **△ 要注意** | 指摘事項を書き終えて満足し最後のコマンドを忘れる／worktree パスや Windows パス指定を誤ってエラーのまま終了する／タイムアウト直前でテキストだけ返して終わる。 | **`agy --output-format json --json-schema`**（`agy --help` で確認済み）で `{ "verdict": "APPROVED" \| "CHANGES_REQUESTED", "findings": [...] }` を返させ、**ランナーが `task-ctl verdict` を叩く**。OpenCode 等の場合は末尾にコピペ可能な1行コマンドを渡すか、`.pi/harness/verdicts/<ID>.txt` に1語だけ書かせる。 |
| **frontmatter を触らず本文だけ書く** | **○（事故リスク有）** | `write_file(Overwrite: true)` でタスクファイル全体を再生成してしまい、先頭の `---` や改行コード（CRLF）、クォートを壊す。 | **ワーカーに `tasks/<ID>.md` 自体を触らせない。** ワーカーは `.pi/harness/tmp/<ID>-report.md`（作業報告専用ファイル）だけを作成し、ランナーが `tasks/<ID>.md` の `## REPORT` / `## REVIEW` へ機械的に差し込む。 |
| **`allowed_paths` 内のみ編集する** | **○** | 前方一致の境界が曖昧なとき、または `allowed_paths` 外の共通ファイル修正が必須と判明したときに無理なハックを書く。 | プロンプトに **「許可パス外の変更が必要だと判明したら、編集せず即座に `BLOCKED` 理由を報告して終了せよ」** と逃げ道を明記する。ディレクトリ指定は必ず末尾 `/` を付ける規約にする。 |
| **前任の WIP（未完了変更）からの再開** | **○（情報補強が必須）** | 「変更がある」だけのメモだと、light モデルは最初から全ファイル調査をやり直し、再び15分で時間切れになる。 | ランナーが自動で **`git diff --stat` ＋ 前任ログ（`.pi/harness/logs/<ID>.log`）の末尾40行 ＋ 「調査をやり直さず `git diff` と指定テストだけ確認して残りを仕上げよ」** をプロンプトに注入する。 |
| **light タイムアウト（実装15分 / レビュー10分）** | **○** | 環境探索（`.venv` と `.venv313` の違い等）や対象テストファイルの探索だけで数分〜10分を浪費する。 | プロンプトに **「そのまま実行できるテストコマンド1本（例: `.\.venv313\Scripts\python.exe -m pytest tests/test_delegations.py -x -q`）」** を必ず展開して渡す。 |

---

## 4. v2 ブリーフ追加論点への見解と MVP 削減案

[`DESIGN-CONSULT-BRIEF-v2.md`](../plans/DESIGN-CONSULT-BRIEF-v2.md) の「今の状態」および「追加で聞きたいこと（質問5・6）」に対する回答です。

### 4.1 質問6：現行 pi ハーネス vs 新方式、および Phase 2 残り3タスクの試運転
- **結論**: **現行の `.pi/extensions/harness/`（ポーリング型）は停止し、新ランナー（直列・イベント駆動 MVP）に一本化すべき** です。
- **理由**:
  1. 現行ハーネス（[`poll.ts`](../../.pi/extensions/harness/poll.ts) / [`dispatch.ts`](../../.pi/extensions/harness/dispatch.ts)）の CRLF 修正を配置して並行稼働させると、同じ `progress/` ディレクトリと `.pi/harness/state.json` を2つの仕組みが取り合い、二重起動や状態破壊が起きます。
  2. 今夜まさに起きた「CRLF でタスクが消えた」事故は、新ランナーの Step 1（`task-ctl scan` による BOM/CRLF 正規化＋`corrupt` 強制可視化）で根本解決します。
- **試運転の最小スコープ**: ご提案の通り、**Phase 2（`progress/phase-2-authz/`）の残り3タスク（`002` の状態確認・コミット、`003` の実装完了、`001` の `blocked` 理由解消）** がサイズ・検証対象として最適です。

### 4.2 質問5：Codex goal ループ案（`AGENTS.md` 追記ドラフト）について
- ※ 本ワークスペース上の [`DESIGN-CONSULT-BRIEF-v2.md`](../plans/DESIGN-CONSULT-BRIEF-v2.md) には「別添の `AGENTS.md` 追記ドラフト」の本文実体が同梱されていなかったため、ドラフト個別の文面批評は行えません。
- 一般論として「Codex 対話セッションの goal ループがシェル経由で `agy` / `opencode` を呼ぶ方式」を採る場合でも、**① 状態遷移と停止条件（アクティブ0件で終了）は `AGENTS.md` の自然言語ルールだけに頼らず `task-ctl` 等のコード側で物理強制すること、② ワーカーの標準出力を Codex のコンテキストに直接流し込まずログファイルへ逃がすこと** の2点が不可欠です。

### 4.3 MVP として削るべき部分 vs 絶対に入れるべき部分
- **削る（過剰な複雑さ）**:
  1. **worktree 作成・コピー・マージ手順** → 直列 MVP では `phase/<slug>` ブランチ上で直接作業し、**「コード成果物のパス限定コミット」と「台帳コミット」を2コミットに分けるだけ** に簡素化する（Windows での worktree ロック問題と台帳二重化を同時に回避）。
  2. **OpenCode 無料プールの Tier-A / Tier-B 分類と 3階層 Cooldown** → 最初は `pool:agy:<pool>` と `model:opencode/<slug>` の2階層のみ。
  3. **Stage 1（`## REVIEW` 末尾10行の正規表現救済）** → 誤認の温床を断つため廃止。
- **絶対に入れる（light モデルの成功率を跳ね上げる2点）**:
  1. **自己完結型の `dispatch-prompt.md` 生成（50行以内）**: 規約ファイル群を自力で探して読ませるのではなく、ランナーが「許可パス」「実行テストコマンド（`.venv313` 等を明記）」「受入条件」「WIP 差分要約」だけをコンパクトに展開して渡す。
  2. **Implementer 終了後のランナー側テストプリチェック**: レビュアーを起動する前に、ランナー自身が指定テストコマンドを実行して PASS を確認する。落ちていればレビュアーを呼ばず、テストエラー末尾を添えて即差し戻す。

---

## 5. 実行系・モデル制約の自己申告（`Gemini 4 Hydrogen` 実機確認）

1. **`agy` headless 実行の可否・正式名・effort**:
   - 本環境で `agy models` を実行して実機確認した結果、`Gemini 4 Hydrogen` は **headless 利用可能モデル一覧に含まれています**。
   - 確認された正式 ID と `--model` 指定用の表示名（4段階）は以下の通りです：
     - `gemini-4-hydrogen-low` / `Gemini 4 Hydrogen (Low)`
     - `gemini-4-hydrogen-medium` / `Gemini 4 Hydrogen (Medium)`
     - `gemini-4-hydrogen-high` / `Gemini 4 Hydrogen (High)`
     - `gemini-4-hydrogen-xhigh` / `Gemini 4 Hydrogen (XHigh)`
   - `agy --help` では `--effort (low|medium|high|xhigh|max)` オプションも定義されていますが、現行の [`agy.ts`](../../.pi/extensions/harness/runners/agy.ts#L31-L40) では `--model` に `"Gemini 4 Hydrogen (Medium)"` のように effort サフィックスを含めた表示名を渡す仕様になっています。
2. **light クラスワーカーとしての実務上の限界**:
   - **コンテキスト圧迫による末尾作法の脱落**: 複数の長大な規約文書を読み込んだ後に、巨大ファイル（例: [`service.py`](../../backend/app/service.py) 約2,900行、[`App.tsx`](../../frontend/src/App.tsx) 約2,000行）を横断調査させると、最後に実行すべき定型コマンド（`task-ctl` 等）を落とすリスクが上がります。変更対象ファイルを絞り、プロンプトを自己完結化することが重要です。
   - **Markdown 全体上書きによる書式破壊リスク**: frontmatter と本文が混在するファイルを直接編集させると、改行コードや末尾の書式を崩すリスクがあります。専用レポートファイル出力または `--json-schema` 出力に限定する方が安全です。
   - **環境パスの探索コスト**: `.venv`（Python 3.10 で非互換）と `.venv313`（Python 3.13 で動作）が混在する環境では、テストコマンドに明示的な実行パスが書かれていないと、環境エラーの調査だけで試行時間の大半を消費します。
