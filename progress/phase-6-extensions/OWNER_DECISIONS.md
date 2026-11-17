# Owner decisions — 2026-11-16 回答分

`docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html`（やさしい解説ガイド、6 テーマ）に対する
オーナー回答を、**逐語**・**実装としての解釈**・**これで解禁される作業**・**残る懸念**の
4 点で記録する。解釈はオーナーの言葉ではないので、取り違えがあれば上書きする。

凡例: 【回答】= オーナー逐語 / 【解釈】= 実装が従う規則 / 【解禁】= 着手可能になる要件 ID /
【申し送り】= 実装が同意していない、または確認を要する点。

---

## テーマ 1 — 別の作業部屋（Runner）で AI やツールを動かすルール（Entry 1〜5）

参照: `docs/plans/OWNER_CHECKLIST_2026-11-11.md` Entry 1〜5、`ADR-0012`、`ADR-0013`、`HBR-001`〜`HBR-015`

### E1 許可証（リース）の期限

【回答】「一か月」

【解釈】Runner に渡す一回限りのリースの既定 TTL を **1 か月（30 日）**とする。
開発側の推奨（既定 24 時間・上限 7 日）はオーナー判断で上書きされた。TTL は設定値とし、
失効・取消は即時反映（取消された lease は次の検証で拒否）とする。

【解禁】`HBR` のリース発行・検証まわり。

【申し送り】TTL が長いほど「漏れた通行証が使える時間」も長い。取消（revoke）と
利用履歴の記録を必須にして補う方針で進める。短縮の指示があればいつでも設定で変えられる。

### E2 承認の役割

【回答】「管理者が事前に許可しているとログイン認証を試みるタブが表示される」

【解釈】**新しい承認係ロールは作らない**。既存の `system_admin` が事前に許可を与え、
許可済みの利用者にだけ、外部 AI/ツールの認証を行うタブ（UI 導線）が出る。
未許可なら導線そのものを出さない（かつサーバ側でも拒否する。表示は許可の写像であって
許可の代わりではない）。

【解禁】Runner 承認 UI と、その `system_admin` 限定のサーバ側認可。

### E3 通信していい範囲

【回答】「社内回線内でよい」

【解釈】Runner と本体の通信は**社内ネットワーク内に限定**する。外向きの通信は既定で拒否し、
許可する宛先は設定で明示列挙する。

### E4 パスワード（鍵）の渡し方

【回答】「渡していい」

【解釈】外部 AI を使う際の資格情報は、仲介役（broker）経由で Runner に渡してよい。
リポジトリ・ログ・進捗記録に資格情報を書かない規則は従来どおり変更しない。

### E5 本人確認と鍵管理

【回答】「OS 管理で良い気がするが、ローカル LAN 内で運用する前提なのでハッキングの恐れは
ないはずなので考慮する必要がないのでは」

【解釈】鍵は **OS 標準の資格情報ストアに保管**する（Windows 資格情報マネージャ等）。
Runner の本人確認は、登録時の一回限りの合言葉で足りるものとし、重い相互認証は入れない。

【申し送り】「LAN 内だから攻撃がない」という前提には実装として同意していない。
LAN 内でも、踏み台になった端末・持ち込み端末・同一 LAN の別部署からの到達は起こりうる。
ただし**コストの判断はオーナーの領分**なので、重い相互認証は入れずに進める。その代わり、
費用がほぼゼロで効く次の 2 つだけは入れる: ① Runner 登録時の一回限り合言葉、
② リースの利用記録（誰のどの lease が、いつ、どの Runner で使われたか）。
これらは後から本人確認を強める場合の土台にもなる。

---

## テーマ 2 — 「資料は割と何でも対応したい」とウイルス検査

参照: `DATA-006`、`DATA-007`、`progress/phase-5-prototype/PROGRESS.md` §3

【回答】「opencode や claude, chatgpt などで許容されている形式データはすべて許容。
あとから追加するのが面倒。研究支援用のツールなので危ないデータを入れるのは本人のせいなのでは
ないか？ サンドボックス案でよい」「ウイルス対策はやれるとこでやってよい。docker でも
ローカル PC でも」

【解釈】

1. **対応形式は「広く許容」を既定とする**。具体的には、テキスト系（`.txt` `.md` `.csv`
   `.json` `.yaml` `.xml` `.html` と各種ソースコード拡張子）、文書系（PDF / Word / Excel /
   PowerPoint）、画像（PNG / JPEG / GIF / WebP、必要に応じ OCR）を対象にする。
   形式は**コードに直書きせず設定表**にし、追加が設定変更だけで済むようにする
   （「あとから追加するのが面倒」への対応）。
2. **抽出処理はサンドボックス内で行う**。本体プロセスで未知ファイルを解析しない。
   実行環境は Docker が使える場合は Docker、使えない場合はローカル PC 上の
   権限制限付き子プロセス（ネットワーク遮断・書込み先限定・CPU/メモリ/時間の上限）とする。
   どちらで走ったかは取り込み記録に残す。
3. **ウイルス検査は「できる範囲で」**。検査ソフトが動いていない環境では、取り込みを
   止めるのではなく「未検査」と明示して通す既定に変更してよい。ただし既定値は運用設定とし、
   厳格運用（未検査なら隔離）も選べるようにする。

【解禁】`DATA-006` `DATA-007`、および取り込み UI の形式表示。

【申し送り】「危ないデータを入れるのは本人のせい」は、**被害が本人に閉じる場合にのみ**
成り立つ。Locus は共有ツールなので、悪意あるファイルが開かれた瞬間に被害は
サーバ側（＝全員の資料）へ及びうる。サンドボックス採用はその差を埋めるためであり、
その前提で「広く許容」を実装する。

---

## テーマ 3 — 同時利用時の待ち時間

参照: `UI-006`、`progress/phase-4-closeout/tasks/T-PH4-105.md`

【回答】「待機列を複数本に」（選択肢 c）

【解釈】モデル実行のスロットを 1 本から **N 本（設定値）**へ拡張する。
既存の公平配分（1 人あたりの同時実行上限）は維持し、N 本すべてを 1 人が占有しないようにする。
N の既定値は、計測（`scripts/measure_capacity.py`）の実測に基づいて決める。
待機上限 300 秒と行列上限（全体 16 件・1 人 2 件）は、N 本化後に再計測してから見直す。

【解禁】`UI-006` の能力表示確定、同時利用の拡張。

【申し送り】スロットを増やすとメモリ / GPU の消費が比例して増える。配備先の実機性能で
N の上限が決まるので、N は設定値のままにし、起動時に実測して超過なら警告する。

---

## テーマ 4 — 共有フォルダ・オンラインストレージ連携

参照: `DATA-008`、`PHASE2_STORAGE_ACL_RESEARCH.md`

【回答】「win 共有フォルダ、GoogleDrive、BOX 等々」「チェック頻度は 10 分おき程度か、
権利設定に変更があったら発火するようにする」

【解釈】

1. 接続先は **Windows 共有フォルダ（SMB）・Google Drive・Box** を対象にする。
   最初に作るのは共通の取り込みインタフェースで、接続先ごとの実装は差し替え可能にする。
2. **既定の巡回間隔は 10 分**（設定値）。加えて、接続先の**権限設定の変更を検知したら
   即時に発火**する（Drive/Box は変更通知 API、SMB は ACL のハッシュ比較）。
3. 元の保存先で閲覧権を失った利用者は、Locus 側の検索結果・出典・過去の回答からも
   同時に見えなくなること。これは連携実装の受入条件とする。

【解禁】`DATA-008`。ただし接続先 3 種は**別々のジョブ**に分ける。

---

## テーマ 5 — 本番公開の準備

参照: `PROD-002` `PROD-003`、`IAM-005` `IAM-016` `IAM-017`、`DATA-013` `DATA-015`

【回答】「id と password の発行をしてログインする流れで固まったはず」
「通信の暗号化は必要。社内ネットワーク内想定だが、web UI のため id と password のある人は
ブラウザで使用したいはず」「postgres の方が良いのでは」
「デフォルト、1 年にして管理者に期限が来たらポップアップとして通知するようにしたら。
ログの改ざん防止はよしなにやって」「管理画面は別の機能の配線が終わってから実装」

【解釈】

1. **認証は ID + パスワードの発行とログイン**で確定。`IAM-005`（MFA）は**実装しない**。
2. **通信は TLS 必須**。社内ネットワーク限定で配信するが、ブラウザから使う以上 HTTPS を張る。
   証明書の入手方法（社内 CA / 自己署名 + 配布）は配備手順の課題として別途詰める。
3. **本番ストアは PostgreSQL**。SQLite は開発・プロトタイプ用として残す。
   全文検索・ベクトル検索の方式は PostgreSQL 採用を前提に設計し直す。
4. **保存期間の既定は 1 年**。期限到来時は管理者に画面通知（ポップアップ）を出し、
   削除は管理者の操作で行う（無人で消さない）。
5. **監査ログの改ざん防止は実装側に一任**。追記のみ・連鎖ハッシュ・取得専用の経路で実装する。
6. **組織全体の管理画面（Entry 6）は後回し**。他機能の配線が終わってから着手する。

【申し送り】MFA は 2026-11-09 の記録では「本番必須」として整理されていた。本回答で
**不要**に変わったため、`IAM-005` の扱いを「実装しない（オーナー判断 2026-11-16）」へ改める。
ID + パスワードのみの場合、パスワード流出がそのまま全資料の閲覧につながるので、
代わりに次を既定にする: パスワードの最低強度、失敗回数による一時ロック、
既存の `must_rotate`（発行時と管理者によるリセット後の初回ログインで必ず変更させる仕組み。
定期変更の強制ではない）、ログイン履歴の管理者可視化。

---

## テーマ 6 — AI が自動でプログラムを書いて本番へ合流するルール

参照: `LOOP-003/006/008/012〜014/018/020〜022`

【回答】「人が見てない無監視状態で自動で動かしてよいし、チェック結果を認めて仕組化してよい。
main へマージさせていい。」「問題があればあとでその変更履歴を削除させるので進める。」

【解釈】

1. **無人自動実行を許可**する。ジョブは監視なしで走ってよい。
2. **別モデルによる読取専用レビューの合格を、独立した合格として扱ってよい**。
   実装したモデルが自分のジョブをレビューできない規則は維持する。
3. **統合ブランチから `main` への合流を許可**する。手順は一本化して、
   「統合ブランチで全ジョブ done → CI green → PR 作成 → CI green を確認してマージ」とする。
   `main` への直接 push・履歴の書き換え・フック/CI の迂回は従来どおり行わない
   （「あとで変更履歴を削除させる」場合も、巻き戻しは revert コミットで行えば履歴が残り、
   かつ安全に戻せる。`main` の歴史を消す操作は実行前に必ず確認する）。
4. 無人実行でも**停止条件は維持**する: 封じ込め違反・保護パスへの書込み・試行上限・
   レビュー上限・判断を要する場面では停止してここに質問を書く。

---

## UI 方針

【回答】「UI に関して `docs/plans/UI_OPENCODE_RESEARCH.md` を参考にしたいところではある。
元々、chatgpt や claude のようなサービスと同様の UI で管理しやすいすっきりとした管理画面で
簡単に設定可能という設計であったためである。」

【解釈】`UI_OPENCODE_RESEARCH.md` §7.2 の【要決定】のうち、次を**承認**として扱う。

| 項目 | 決定 |
|---|---|
| §3.3 会話履歴のサイドバー統合（基準画面からの逸脱） | 承認。チャット画面のサイドバーに最近の会話を出す |
| §3.2 SSE ストリーミング | 承認済み・**実装済み**（`T-PH4-102`） |
| §4 管理者専用のループ進行状況可視化 | 後回し（テーマ 5「管理画面は配線後」に従う） |
| §3.7 セッション単位のモデル切替 | 見送り継続（バックエンドが単一グローバルモデル前提） |
| §2 #4 ツールループ | 見送り継続（バックエンドに存在しない機能を描画しない） |
| §6.6 `crypto.randomUUID()` のフォールバック | 承認（LAN の非 SecureContext で TypeError になる実バグ） |
| §3.2 `ChatView`/`ChatMessage`/`ChatComposer` 分離と投影関数 | 承認 |

「すっきりした管理画面で簡単に設定可能」は、設定項目を機能ごとにまとめ、
既定値のまま使えること（必須入力を増やさないこと）を受入条件に含める。

---

## この記録の使い方

- ここで決まった項目は `PROGRESS.md` のジョブへ変換する。決定のない項目はジョブにしない。
- 【申し送り】はオーナーの決定を覆すものではない。実装が取る補償手段を明示しているだけで、
  不要と指示されれば外す。

## T-PH6-103 — worker wrote outside its workspace (2026-11-16T16:33:55+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/flint-40b-free
workspace=C:\Users\hirot\.jobloop-Locus\workspaces\T-PH6-103

**Answer** (2026-11-16, orchestrator): メインチェックアウトを調査し復元した。
逃げていたのは `backend/app/main.py` `backend/app/service.py` の変更と、新規の
`backend/app/formats.py` `tests/test_document_formats.py`。内容は本ジョブの正当な実装に
見えたが、**隔離されていない変更はレビューできない**ので破棄した（参考用の写しのみ退避）。
復元後に `tests/test_api.py` 22 件 green を確認。

根本原因はまだ特定できていない。分かっていること:
① 同じジョブの 1 回目は `opencode/longcat-2.5-free` が **900 秒で応答なし（timeout）**で終わり、
② 枠切れでローテーションし、③ 3 回目の `opencode/flint-40b-free` の後に封じ込め違反が検出された。
ワークスペース側は**無変更**（ワーカーは自分のクローンに一切書いていない）。
timeout で停止させたワーカーの子プロセスが生き残って後から書いた可能性と、
ワーカーがプロジェクト根をメインチェックアウトに解決した可能性の両方が残っている。
特定できるまで本ジョブは再投入しない。コントローラ側の固めは Claude Code が直接行う
（ループ自身の改修をジョブにすると、走っているループが自分を書き換えることになる）。

## T-PH6-114 — 作図と、資料に根拠のない生成の扱い (2026-11-16T19:00:00+09:00)

**Question**: 次の 3 点を決めてください。
(1) 回答を部分ごとに「資料に基づく / 添付データから計算 / モデルの知識」と示す案でよいか。
(2) 作図は A（モデルは数値だけ出し、描画はアプリ側。コード実行なし）か、
    B（モデルにコードを書かせて実行。任意コード実行になるためサンドボックスが前提）か。
(3) 資料に根拠のない質問に答えてよいか。答える場合、その回答に出典は付かない。

**Context**

オーナー指示 2026-11-16「既存の許可範囲ファイルを参照しつつ、新規に貼られたデータファイル
などを用いて図の作成とか普通の生成 AI ができることも行えるようにしたい」。

これは見た目の追加ではなく製品の約束の変更にあたる。現行は「回答は必ず資料が根拠で出典が付く。
根拠が無ければ推測しない」。一般生成を混ぜると、利用者が資料由来とモデルの作文を区別できなくなる。
開発側の推奨は (1) よい、(2) A から始める、(3) 答えてよいが出典が付かないことを画面で明示する。

**Answer** (2026-11-17):

1. **出どころの表示**: 「回答の文章の隣に引用資料をラベルで付けるのはよい」。
   回答の各段落・各主張の隣に、根拠となった資料をラベルとして出す。
   **絵文字は使わない**（オーナー明示。以後 UI 全体の規則とする）。
2. **作図の方法**: **B を採用**。「AI が python コードを動かして作図するのがいい」。
   ただし「**隔離部屋が完成したら取り組むこと**」。したがって `T-PH6-104`
   （サンドボックスの実行境界）が `done` になるまで着手しない。`depends_on` に入れた。
3. **資料に根拠のない質問**: 「応えて良い」。あわせて、チャット領域の上部に中央詰めで
   **「Locusは間違えることがあります。重要な情報は確認してください。」**を常時表示する。

【申し送り】B（コード実行）は、ファイル解析より踏み込んだ境界になる。解析は
「攻撃者が選んだ**データ**を読む」のに対し、作図は「モデルが書いた**命令**を実行する」。
`T-PH6-104` の境界をそのまま使い回すのではなく、作図用に次を追加する前提で進める:
実行するのは生成されたコードのみで利用者の資料原本は読み取り専用で渡す、
出力は画像 1 枚と標準出力に限る、ネットワークは遮断、実行時間とメモリは作図用に別枠。
これらは `T-PH6-114` の受入条件に落とす。

## UI 指摘 — 実物を操作して (2026-11-17)

**Answer**（記録のみ。質問ではなくオーナーからの指示）:

1. 上部の帯を本文のスクロールから分離する（`T-PH6-109`。実測で確認済み:
   本文を少しスクロールしただけで帯の位置が `y=-111` になり画面外へ出る）。
2. ナビを「資料を調べる / チャット」で分けない。代わりに **「新しいチャット」**を
   SVG アイコン付きのボタンとして置く（`T-PH6-112`）。
3. 参照範囲は**モデル選択バーと同じ形の滑らかなドロップダウン**にし、
   チャット入力欄の中に置く。OS 標準の `<select>` は使わない（`T-PH6-111`）。
4. チャット画面を開いている間、**入力欄は常に画面下部に固定**する（`T-PH6-111`）。
5. 絵文字は使わない（上記 1. と同じ規則）。

## T-PH6-109 — worker wrote outside its workspace (2026-11-17T11:21:44+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/glm-5.3-flash-free
workspace=C:\Users\hirot\.jobloop-Locus\workspaces\T-PH6-109

**Answer** (2026-11-17, orchestrator): 誤検知。ワーカーは自分のクローンの中にだけ書いており、メインチェックアウトにワーカー由来のファイルは無かった。原因は封じ込め判定が`HEAD` を含んでいたことで、ループ実行中のオーケストレーターのコミットで `HEAD` が動いた。判定を未コミットの状態だけに変更し、回帰テストで固定した。試行は消費していないので、ワークスペースを残したまま `resume-one` で再開する。詳細は各 task ファイルの裁定に記録。
## T-PH6-111 — worker wrote outside its workspace (2026-11-17T11:35:07+09:00)

**Question**: The main checkout changed while the job ran, so this work is unreviewable. Inspect and restore the checkout before the job is retried.

**Context**

model=opencode/glm-5.3-flash-free
workspace=C:\Users\hirot\.jobloop-Locus\workspaces\T-PH6-111

**Answer** (2026-11-17, orchestrator): 誤検知。ワーカーは自分のクローンの中にだけ書いており、メインチェックアウトにワーカー由来のファイルは無かった。原因は封じ込め判定が`HEAD` を含んでいたことで、ループ実行中のオーケストレーターのコミットで `HEAD` が動いた。判定を未コミットの状態だけに変更し、回帰テストで固定した。試行は消費していないので、ワークスペースを残したまま `resume-one` で再開する。詳細は各 task ファイルの裁定に記録。


## T-PH6-109 — worker stopped for a decision (2026-11-17T12:28:47+09:00)

**Question**: appearance.spec.ts:146 の test.fail 印は、本件の修正で帯が固定されたことで「期待に反して成功」の失敗に変わっており、印のコメントは T-PH6-109 のジョブで印を消すよう指示しているが、appearance.spec.ts は本ジョブの allowed_paths 外なので消せない — この印の削除を本ジョブの許可パス拡張で行うのか、別途（オーナーまたは後続ジョブ）で消すのかを決めてください。

**Context**

ows the old name; the 6 pre-existing combined-run failures in (c) remain; on the chat page the composer sits marginally higher than before on an empty conversation (content now scrolls inside `.main` instead of the page; no test asserts this); running e2e locally required a gitignored `.venv` bridged to the existing environment's packages via a `.pth` file — no packages were installed and nothing outside the workspace was written.

TEST
- `npx playwright test e2e/workspace.spec.ts -g "the topbar stays visible"` (separate-test version, before the fix): 1 failed — `pageScrollY` was 64, reproducing the page-level scroll that takes the topbar off screen.
- Same test after the CSS fix: 1 passed.
- `npx playwright test e2e/workspace.spec.ts`: 13 passed (13/13, including the strengthened scroll test).
- `npx playwright test e2e/appearance.spec.ts`: 6 passed, 1 failed — only the `test.fail` marker inversion「Expected to fail, but passed」at line 146; the T-PH6-111 marker (message box) still fails as expected.
- `npx playwright test` (full, with my changes): 7 failed / 18 passed — the same 6 login-collision failures observed on the stashed baseline (6 failed / 19 passed) plus the designed marker inversion; `a11y.spec.ts` 5/5 passed in every full run.
- `npm --prefix frontend run test` (controller command, run twice): 15 files / 95 tests passed.
- `npm run typecheck`: PASS. `npm run lint`: only the pre-existing `no-misleading-character-class` error in untouched `appearance.spec.ts`.
- `python -m ruff check backend tests scripts jobloop`: All checks passed. `python -m ruff format --check backend tests scripts jobloop`: 160 files already formatted. `python scripts/secret_scan.py`: 0 findings.
- `grep -c "研究資料室" frontend/src/App.tsx`: 0.

STATUS
needs-owner-decision: appearance.spec.ts:146 の test.fail 印は、本件の修正で帯が固定されたことで「期待に反して成功」の失敗に変わっており、印のコメントは T-PH6-109 のジョブで印を消すよう指示しているが、appearance.spec.ts は本ジョブの allowed_paths 外なので消せない — この印の削除を本ジョブの許可パス拡張で行うのか、別途（オーナーまたは後続ジョブ）で消すのかを決めてください。

**Answer** (2026-11-17, orchestrator): オーナー判断ではなく範囲の問題なので私が裁定した。印はその修正が入った証拠なので、**消すのは同じジョブの仕事**。両ジョブの許可パスに `frontend/e2e/appearance.spec.ts` を加え、自分の修正に対応する `test.fail` 印 1 つだけを外すこと、外したあとそのテストが本物の合格として通ることを受入条件に足した。あわせて報告された eslint の `no-misleading-character-class` は**私が入れた欠陥**で、先に直した（T-PH6-111 のワーカーの指摘。ワーカー側の対応は不要）。
## T-PH6-111 — worker stopped for a decision (2026-11-17T12:42:08+09:00)

**Question**: frontend/e2e/appearance.spec.ts は許可パス外なので触れませんでしたが、その中の test.fail("the message box stays reachable") には「Fixed by T-PH6-111 — remove this marker in that job」とあり、今回の修正でこのテストは合格に反転し、次回の --e2e 実行で browser-e2e ゲートが赤くなります。このマーカー1行の削除だけ許可パスに加えて私が消してよいか、それともマージ直後にオーナーが消すか（同じファイル21行目に基底コミット時点から存在する eslint エラー no-misleading-character-class も CI の frontend-lint を赤くしています。そちらの扱いも併せてご指定ください）、どちらで進めるべきかの判断をお願いしま

**Context**

error (`no-misleading-character-class`, introduced in today's commit `5620ee3`), so `frontend-lint` fails on the unmodified head too (verified by stashing my changes). This job's gates do not include lint, but hosted CI's `verify.py` runs it.
- Risks left behind: jsdom cannot compute layout, so the fixed-composer behavior is verified structurally plus as a stylesheet contract; real-layout confirmation depends on the Playwright test currently inverted by the `test.fail` marker. The pre-existing lint error and the e2e marker are both outside my paths and unresolved.

TEST
- `npm --prefix frontend run test -- --run src/App.test.tsx` (before implementation): 4 new tests failed as expected, 17 existing passed.
- `npm --prefix frontend run test -- --run src/App.test.tsx` (after implementation): 21 passed.
- `npm --prefix frontend run test`: 99 passed (15 files), twice (final run fresh).
- `npm --prefix frontend run typecheck`: PASS.
- `npm --prefix frontend run lint`: FAIL — `frontend/e2e/appearance.spec.ts 21:45 error no-misleading-character-class`; reproduced on the unmodified head via `git stash` → pre-existing, not caused by this change.
- `python -m ruff check backend tests scripts jobloop`: "All checks passed!".
- `python -m ruff format --check backend tests scripts jobloop`: "160 files already formatted".
- `python scripts/secret_scan.py`: "Offline secret scan: 0 findings".
- Playwright e2e was not run (not this job's verification command); expected state after this change: the `test.fail` marker test will pass and be reported as a failure.

STATUS
needs-owner-decision: frontend/e2e/appearance.spec.ts は許可パス外なので触れませんでしたが、その中の test.fail("the message box stays reachable") には「Fixed by T-PH6-111 — remove this marker in that job」とあり、今回の修正でこのテストは合格に反転し、次回の --e2e 実行で browser-e2e ゲートが赤くなります。このマーカー1行の削除だけ許可パスに加えて私が消してよいか、それともマージ直後にオーナーが消すか（同じファイル21行目に基底コミット時点から存在する eslint エラー no-misleading-character-class も CI の frontend-lint を赤くしています。そちらの扱いも併せてご指定ください）、どちらで進めるべきかの判断をお願いします。

**Answer** (2026-11-17, orchestrator): オーナー判断ではなく範囲の問題なので私が裁定した。印はその修正が入った証拠なので、**消すのは同じジョブの仕事**。両ジョブの許可パスに `frontend/e2e/appearance.spec.ts` を加え、自分の修正に対応する `test.fail` 印 1 つだけを外すこと、外したあとそのテストが本物の合格として通ることを受入条件に足した。あわせて報告された eslint の `no-misleading-character-class` は**私が入れた欠陥**で、先に直した（T-PH6-111 のワーカーの指摘。ワーカー側の対応は不要）。


## T-PH6-109 — worker stopped for a decision (2026-11-17T13:30:48+09:00)

**Question**: Should the job be closed as delivered while leaving `frontend/index.html` (`<title>研究資料室 · Locus</title>`) untouched, or should you authorize expanding the allowed paths by a one-line change to make that title Locus-only?

**Context**

ATION_BASELINE.md, ui-and-multiuser-design.md, demo fragment) still use the old name; treated as reference material and out of scope.
- Prettier is a devDependency wired into no script or gate; all four touched files already fail `prettier --check` at HEAD due to CRLF endings, while the enforced format gate is `ruff format`, which passes.

Risks left behind:

- The full E2E suite (`npm run test:e2e`) shows 7 failures from cross-spec user-ID reuse colliding with rotated passwords; these were reproduced identically on unmodified HEAD and are pre-existing, not caused by this change.
- The `frontend/index.html` title residual requires an owner decision before it can be fixed.

TEST

- `npm --prefix frontend run test` → PASS (fresh): Test Files 15 passed (15), Tests 95 passed (95), Duration 21.72s.
- `npm --prefix frontend run typecheck` → PASS (fresh): `tsc -b` completed with exit 0.
- `npm --prefix frontend run lint` → PASS (fresh): `eslint . --max-warnings 0` completed with exit 0.
- `npm --prefix frontend run test:appearance` → PASS (fresh): 7 passed (16.1s); the single `✘`-labeled line is T-PH6-111's expected-failure marker and passed as expected.
- `python -m ruff check backend tests scripts jobloop` → PASS: All checks passed!
- `python -m ruff format --check backend tests scripts jobloop` → PASS: 160 files already formatted.
- `python scripts/secret_scan.py` → PASS: Offline secret scan: 0 findings.
- Earlier in attempt 2, on the same final diff: RED confirmed with the old CSS (`pageScrollY` expected 0, received 64); GREEN after the fix. `npx playwright test e2e/workspace.spec.ts` → 13 passed (31.2s). Full `npm run test:e2e` → 18 passed / 7 failed, with the same failures reproduced on unmodified HEAD (pre-existing).

STATUS
- needs-owner-decision: Should the job be closed as delivered while leaving `frontend/index.html` (`<title>研究資料室 · Locus</title>`) untouched, or should you authorize expanding the allowed paths by a one-line change to make that title Locus-only?

**Answer** (2026-11-17, orchestrator): 範囲の問題なので私が裁定した。ブラウザのタブも画面なので、`frontend/index.html` を T-PH6-109 の許可パスに加え、`<title>` を Locus のみにすることを受入条件にした。確認手段を `App.tsx` の grep に狭めていた私の起票の欠陥で、レビュアの指摘が正しい。`docs/planning/` 配下は基準記録なので変更しない。

## GOV-002 / UI 参照資料 — 2026-11-17 の指示

【回答】「サブエージェント起動してガンガン進めていいので起票ガンガンしましょう」
「UI 系に関しては opencode の UI や google が出している
https://github.com/GoogleChrome/modern-web-guidance などを使用して進めてください」

【解釈】

1. **要件 `GOV-002`（No routine implementation subagents）への回答として扱う。**
   起票・調査・設計の下書きにサブエージェントを使ってよい。
   ただし次は維持する: 実装したモデルが自分のジョブをレビューしない、
   成果物は私が読んでから取り込む、サブエージェントにオーナー判断をさせない。
2. UI は opencode の実装（命名・設定画面の作り）に加えて、
   **Google Chrome の `modern-web-guidance`** を参照する。
   新しいという理由だけで採用せず、採否と理由を記録する。

【申し送り】`CLAUDE.md` と `AGENTS.md` は現在「サブエージェント駆動開発・
並列エージェント起動を行わない」と明記しており、本指示と食い違う。
実態に合わせて両ファイルを更新することを提案する（governance の文面変更は
オーナー承認が要るため、ここでは提案に留める）。食い違いを放置すると、
次に別の担当が読んだときにどちらが正かが分からなくなる。


## T-PH6-109 — out-of-scope change (2026-11-17T16:42:16+09:00)

**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job.

**Context**

outside allowed_paths: ['test-results/.last-run.json']

**Answer** (2026-11-17, orchestrator): オーナー判断ではない。範囲外として報告されたのは画面検査ゲート自身が書いた `test-results/.last-run.json` と、ワーカーがテスト出力を読むために作った作業ファイル。ゲートを `frontend/` から起動するよう直し（`.gitignore` が覆う場所に成果物が出る）、3 件とも試行を戻して再開する。範囲判定そのものは緩めない。
## T-PH6-113 — out-of-scope change (2026-11-17T16:55:38+09:00)

**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job.

**Context**

outside allowed_paths: ['frontend/test-output.txt', 'frontend/test-results.txt']

**Answer** (2026-11-17, orchestrator): オーナー判断ではない。範囲外として報告されたのは画面検査ゲート自身が書いた `test-results/.last-run.json` と、ワーカーがテスト出力を読むために作った作業ファイル。ゲートを `frontend/` から起動するよう直し（`.gitignore` が覆う場所に成果物が出る）、3 件とも試行を戻して再開する。範囲判定そのものは緩めない。
## T-PH6-115 — out-of-scope change (2026-11-17T17:07:18+09:00)

**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job.

**Context**

outside allowed_paths: ['test-results/.last-run.json']

**Answer** (2026-11-17, orchestrator): オーナー判断ではない。範囲外として報告されたのは画面検査ゲート自身が書いた `test-results/.last-run.json` と、ワーカーがテスト出力を読むために作った作業ファイル。ゲートを `frontend/` から起動するよう直し（`.gitignore` が覆う場所に成果物が出る）、3 件とも試行を戻して再開する。範囲判定そのものは緩めない。


## T-PH6-109 — out-of-scope change (2026-11-17T21:13:29+09:00)

**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job.

**Context**

outside allowed_paths: ['test-results/.last-run.json']

## T-PH6-113 — out-of-scope change (2026-11-17T21:35:45+09:00)

**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job.

**Context**

outside allowed_paths: ['frontend/test-output.txt', 'frontend/test-results.txt']

## T-PH6-115 — out-of-scope change (2026-11-17T21:38:36+09:00)

**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job.

**Context**

outside allowed_paths: ['test-results/.last-run.json']

## T-PH6-124 — out-of-scope change (2026-11-17T22:28:50+09:00)

**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job.

**Context**

outside allowed_paths: ['frontend/errors.txt', 'frontend/filtered.txt', 'frontend/install-eslint.txt', 'frontend/install-final.txt', 'frontend/install-log.txt', 'frontend/install2.txt', 'frontend/install3.txt', 'frontend/install4.txt', 'frontend/install5.txt', 'frontend/install6.txt', 'frontend/install7.txt', 'frontend/install8.txt', 'frontend/lint-apits.txt', 'frontend/lint-check.txt', 'frontend/lint-final.txt', 'frontend/lint-final2.txt', 'frontend/lint-new.txt', 'frontend/lint-output.txt', 'frontend/lint-output2.txt', 'frontend/lint-restricted-syntax.txt', 'frontend/lint-verify.txt', 'frontend/lint_result.txt', 'frontend/output.txt', 'frontend/package-lock.json', 'frontend/package.json', 'frontend/powershell-lint.txt', 'frontend/pw-build.txt', 'frontend/pw-eslint.txt', 'frontend/pw-eslint2.txt', 'frontend/pw-lint.txt', 'frontend/pw-test.txt', 'frontend/src/api.ts', 'frontend/test-all.txt', 'frontend/test-exist.txt', 'frontend/test-final.txt', 'frontend/test-output.txt', 'frontend/test.txt', 'frontend/typecheck-out.txt', 'frontend/typecookerrt.txt', 'frontend/typecookout.txt', 'frontend/vitest-out.txt']
