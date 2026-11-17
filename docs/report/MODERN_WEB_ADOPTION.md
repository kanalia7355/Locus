# Locus の UI を標準機能に寄せる — 採否の記録

出典: `GoogleChrome/modern-web-guidance`
（`skills/modern-web-guidance/guides/` 配下の該当ガイドを実際に参照した。
対応状況の記述はそのガイドの記載をそのまま引いている）。
あわせて opencode の UI 規律（`docs/plans/UI_OPENCODE_RESEARCH.md`、
とくに「Insecure Origins (HTTP LAN)」）を前提にしている。

判断日: 2026-11-17。配備前提: **社内 LAN・プレーン HTTP**（`OWNER_DECISIONS.md` テーマ 5 で
本番は TLS 必須と決まっているが、現状の開発・検証はプレーン HTTP で行われている）。

---

## 0. 先に測った 2 つの環境事実（採否の根拠になっている）

この 2 つは推測ではなく、この調査の中で実際に実行して確かめた。

1. **`jsdom` 29.1.1 は `<dialog>` の `showModal()` も Popover API も持たない。**
   実測: `typeof el.showModal` → `undefined`、`"popover" in HTMLElement.prototype` → `false`。
   したがって **`npm --prefix frontend run test`（ゲートの検証コマンド）だけでは
   ネイティブの最前面レイヤの挙動を一切証明できない**。
   標準機能へ寄せるジョブは、
   (a) `frontend/src/test-setup.ts` に最小限の代替実装を置いて単体テストを通す、
   (b) **本物の証明は `frontend/e2e/appearance.spec.ts` に置く**、の両方が必要になる。
   これを飛ばすと「単体テストは緑、画面は壊れている」が起きる。

2. **Playwright は `chromium` 1 本しか走らせていない**（`frontend/playwright.config.ts`）。
   つまり `test:appearance` が緑でも「Firefox と Safari で動く」ことは何も示さない。
   Chromium 限定の機能は、e2e が緑でも採ってはいけない。この表の「採らない」の
   いくつかはこの理由による。

---

## 1. 採否の表

| ガイド項目 | 採る | 理由 / 採らない理由 | ジョブ |
|---|---|---|---|
| `ui-components/dialog` — 自前オーバーレイをやめ `<dialog>` + `showModal()` | **採る** | Baseline（Safari 15.4 / Firefox 98、2022-03 以降広く利用可能）。いまの出典モーダル（`App.tsx:1457-1503`）は `role="dialog"` / `aria-modal` / **35 行の自前 Tab 巡回**を手で書いている。ネイティブなら背景の `inert` 化・フォーカス封じ込め・Esc・`::backdrop`・最前面レイヤが全部無償。自前のトラップは `getClientRects()` で可視判定している分だけ賢いが、`inert` な領域・シャドウ境界・ブラウザ UI へのフォーカス移動は再現できていない | **T-PH6-116**（既存の出典モーダル）／設定ダイアログは **T-PH6-112 への修正指示 A** |
| `ui-behaviors/prevent-page-scroll-under-modal-dialog` — `dialog:modal` と `dialog::backdrop` に `overscroll-behavior: contain` | **採る**（上乗せとして） | `html`/`body` に `overflow: hidden` を当てる手口を使わずに済む。非スクロール容器への完全対応は Chrome 144+ / Firefox 150+、Safari 未対応だが、**未対応でも悪化しない**（いまが素のまま）。ガイドの指示どおり `@supports` での機能判定はしない（全ブラウザが対応を名乗るため判定が無意味） | T-PH6-116 |
| `ui-behaviors/light-dismiss-a-dialog` — `closedby="any"` で背景クリックを閉じる | **一部採る** | Chrome 134+ / Edge 134+ / Firefox 141+、**Safari 未対応**。既存要件（T-PH6-112「背景クリックで閉じる」）は Safari でも満たさねばならないので、`closedby="any"` は付けるが**背景クリックの JS フォールバックは残す**。属性だけに頼って要件を落とすのは不可 | T-PH6-116、T-PH6-112 修正指示 A |
| `ui-behaviors/declarative-dialog-popover-control` — `command="show-modal"` / `commandfor` | **採らない** | Baseline になったのが 2025-12（Chrome 135+ / Safari 26.2+）で日が浅く、React 19.3 側の属性透過も検証していない。`onClick` から `ref.showModal()` を呼ぶのは 1 行で、置き換えて得るものが無い。新しいから使う、はしない | — |
| `ui-behaviors/animate-to-from-top-layer` — `@starting-style` / `transition-behavior: allow-discrete` / `overlay` | **入りだけ採る** | `@starting-style`（Chrome 117+ / Firefox 129+ / Safari 17.5+）と `transition-behavior`（Chrome 117+ / Firefox 129+ / Safari 17.4+）は使える。**`overlay` は Chromium 専用**なので、閉じるときのアニメーションは Firefox/Safari で成立しない。入場だけ付け、退場は即時にする。なお `styles.css:1018-1026` の `prefers-reduced-motion` 一括停止がそのまま効くので、追加の配慮は要らない（確認済み） | T-PH6-116（任意。受入条件にはしない） |
| `ui-atoms/viewport-aware-dropdowns` — Popover API | **採る** | Baseline 2025-01-27（Chrome 116+ / Edge 116+ / Firefox 125+ / Safari 17+）。参照範囲チップの「外側クリックで閉じる」「Esc で閉じる」「最前面に出す」が標準の light dismiss で済み、自前の `document` クリック購読が消える | **T-PH6-117** |
| 同ガイド — **CSS アンカー配置**（`position-area` / `position-try-fallbacks`） | **採らない** | ガイドの記載どおり **Chrome 157+ / Edge 157+ / Safari 27+、Firefox 未対応**。社内の誰がどのブラウザで開くか決まっていない画面で、位置計算が黙って崩れる機能は入れられない。ポリフィル（`@oddbird/css-anchor-positioning`）は、この用途（入力欄が画面下部に固定されている＝チップの座標がほぼ動かない）には過剰。開くときに `getBoundingClientRect()` を 1 回読んで `position: fixed` の座標を決めれば足りる | T-PH6-117 に「採らない」として明記 |
| 同ガイド — `role="menu"` / `aria-haspopup` を安易に付けない | **採る** | ガイドが明示的に禁じている。参照範囲は値の選択なので `role="listbox"` + `aria-expanded`（T-PH6-111 で実装済み）が正しく、`menu` にしてはいけない | T-PH6-117（既存の ARIA を壊さないことを受入条件にする） |
| `visual-design/dark-mode` — `:root { color-scheme: light dark }` と `<meta name="color-scheme">` | **採る** | 2022 年以降広く利用可能。これが無いと、トークンを暗くしてもスクロールバー・フォーム部品・`input` の既定描画が明るいままで、暗い画面に白い枠が残る。`<meta>` + 直後のインラインスクリプトは、T-PH6-110 の受入条件 5「明るい配色が一瞬見えてから暗くなることがない」を**正攻法で満たす唯一の手段**（CSS だけでは初期描画に間に合わない） | **T-PH6-118**（`frontend/index.html` が T-PH6-110 の許可パス外のため分離） |
| `visual-design/dark-mode` — `light-dark()` | **採る** | Baseline 2024-05。トークンを 1 か所で明暗 2 値として書けるので、`@media` ブロックの二重管理が消える。ただし**利用者の 3 択（ライト/システム/ダーク）は `color-scheme` の値を切り替える形で実装しなければならない**（`light-dark()` は使用中の `color-scheme` しか見ないので、クラス付与では効かない）。この制約は T-PH6-110 の設計を縛るので修正指示に出す | T-PH6-110 修正指示 B、T-PH6-118 |
| `visual-design/dark-mode` — `accent-color` / `scrollbar-color` | **採る**（上乗せ） | `accent-color` は広く利用可能。`scrollbar-color` は 2025-12 に newly baseline と新しいが、未対応でも既定のスクロールバーが出るだけで悪化しない。ガイドの注意（最低 3:1、アニメーションさせない）に従う | T-PH6-118 |
| **oklch** | **採らない** | 対応状況の問題ではない（十分使える）。採らない理由は**必要が無い**こと。配色は `docs/planning/UI_IMPLEMENTATION_BASELINE.md` で承認された 13 個の手で選んだ固定値で、プログラムで明度ランプを生成していない。oklch が効くのは生成する場合で、ここでは既に承認された値を別の記法で書き直すだけになり、レビュー済みの値を壊す危険だけが増える | — |
| `visual-design/contrast-color` — `contrast-color()` | **採らない** | Baseline 2026-04-10 でまだ 7 か月。加えて `--color-on-accent` は設計判断として選ばれた値で、自動で黒白に寄せる対象ではない | — |
| `css/size-aware-styling` — 容器クエリ | **採る** | Baseline 2023-02（Chrome 105 / Firefox 110 / Safari 16）。いまの `styles.css` は `@media` だけで分岐しており、**サイドバーを開いているときの実際のチャット列幅を知らない**。ビューポート 1280px でもサイドバーが開いていれば本文は 1000px 前後で、同じ分岐が当たってしまう。これは「幅で崩れる」系の不具合が将来また出る構造的な原因 | **T-PH6-121** |
| `forms/form-fields-automatically-fit-contents` — `field-sizing: content` | **採る** | **Baseline 2026-06-16**（Chrome 123+ / Firefox 152+ / Safari 26.2+）。入力欄の高さを内容に合わせて伸ばすのに `scrollHeight` を読む JS が不要になる。未対応ブラウザは固定高のまま（＝いまと同じ）に落ちる。`width`/`height` の明示指定が勝つので、既存の指定を `auto` に戻す必要がある点だけ注意 | **T-PH6-122** |
| `ui-behaviors/scroll-target-on-load` — `scroll-initial-target` | **採らない** | Chrome 133+ / Edge 133+ のみ、Firefox・Safari 未対応。さらにガイドが明記するとおり**視覚位置だけ動いてフォーカスは動かない**。既存の `App.tsx:581` の `scrollIntoView({ block: "nearest" })` で足りている | — |
| スクロール余白（`scroll-padding-block`）— 最後の発言が入力欄の裏に隠れる問題 | **採る** | ただし**この問題の本当の解は標準機能ではなく構造**で、入力欄をスクロール容器の**外**に出すこと（T-PH6-111 が実施）。`scroll-padding-block` が必要になるのは別の場面で、`scrollIntoView` で発言へ飛んだときに、上の注意書き（T-PH6-115）と下の入力欄の裏に着地しないようにするため。この 2 つを混同しないこと | **T-PH6-120** |
| スクロールアンカリング（`overflow-anchor`） | **何もしない（採る＝触らない）** | 既定が `auto` で、SSE で上に内容が増えても読んでいる位置がずれないのは**既定の動作**。やってはいけないのは `overflow-anchor: none` を書くことで、これを書かない限り対応は不要。将来壊さないよう invariant だけ置く | T-PH6-120（検査 1 本） |
| ストリーミング中の「下端追従」 | **標準機能に無い** | 「利用者が下端にいるときだけ自動追従し、上に戻って読んでいるときは追従しない」は、どのガイドにも対応する基本機能が無い。自前で書くしかない。ここで標準機能を探して時間を使わないこと | 既存実装のまま（修正指示 C で検査のみ追加） |
| `accessibility/respect-os-text-scale` — ルートの `font-size` を上書きしない / `rem` で書く | **採る（重い）** | `styles.css:26` に **`:root { font-size: 14px }`** がある。ガイドが明示的に禁じている書き方で、OS とブラウザの文字サイズ設定を無効化する。WCAG 1.4.4 の観点でも素の不具合。`styles.css` は `px` が 227 箇所、`rem` が 2 箇所なので、作業量は本物 | **T-PH6-119** |
| 同ガイド — `<meta name="text-scale" content="scale">` | **採る（おまけとして）** | Chrome 146+ / Edge 146+ のみで Firefox・Safari 未対応だが、未対応ブラウザでは単に無視される。`rem` 化を済ませた後でのみ意味を持つので、同じジョブの最後に置く | T-PH6-119 |
| `forms/validate-input-after-interaction` + `accessibility/accessible-error-announcement` — `:user-invalid` と `aria-invalid` の同期 | **採る** | 両方 Baseline 2023-11（Chrome 119 / Firefox 88 / Safari 16.5）。ログイン・パスワード変更・利用者追加のフォームは `required` を付けているだけで（`App.tsx:188,200,215,227,1878`）`aria-invalid` が無い。ガイドの指摘どおり **Firefox と Safari は空の `required` を読み込み時点から invalid として公開する**ので、`aria-invalid="false"` を初期値として置くことまでやる必要がある | **T-PH6-123** |
| `prefers-reduced-motion` | **採る＝既に対応済み（確認した）** | `styles.css:1018-1026` に `transition`/`animation`/`scroll-behavior` の一括停止がある。追加実装は不要。**ただし 1 つ穴がある**: この一括停止は CSS 由来の動きだけを止め、JS から `scrollIntoView({ behavior: "smooth" })` のように明示指定した動きは止められない。いまは `App.tsx:581` が `block: "nearest"` のみで `behavior` を指定していないので実害は無い（確認済み）。今後 `behavior: "smooth"` を書くなら `matchMedia` で分岐が必要 | 修正指示 C（規律として記録） |
| `security/passkeys` 系（9 ガイド）・`pwa/install-web-app` | **採らない** | WebAuthn と Service Worker は SecureContext 専用で、プレーン HTTP の LAN 配信では動かない。加えて認証は「ID + パスワードの発行とログイン」で確定し MFA は実装しないとオーナーが決めている（`OWNER_DECISIONS.md` テーマ 5）。要件としても不要 | — |
| **SecureContext 専用 API を使わない**（opencode の規律） | **採る。未解決の実例が 1 件ある** | `crypto.randomUUID` は `api.ts:212` で対処済み。しかし **`ProvisionUser.tsx:44` の `navigator.clipboard.writeText` が未対処**で、これも SecureContext 専用。いまは `try/catch` に入っているので画面は落ちず「コピーできませんでした」と出るだけだが、**LAN では常に失敗するボタンが置かれている**状態になる。落ちないので `appearance.spec.ts` の「自前のコードが例外を投げない」検査にも引っかからない。再発防止の検査も要る | **T-PH6-124** |
| `security/sanitize-untrusted-html`（`setHTML` / Sanitizer） | **採らない（いまは）** | `frontend/src` に `innerHTML` も `dangerouslySetInnerHTML` も**無い**（確認済み）。React のエスケープで足りている問題に API も依存関係も足さない。対応状況も Chrome 146+ / Firefox 148+ で Safari 未対応と狭い。**ただし規律として残す**: T-PH6-114 で回答の Markdown 描画や作図結果の埋め込みに進むなら、その時点で再評価する。それまでは「`innerHTML` を書かない」という検査だけ置く | T-PH6-124（検査 1 本） |
| `security/trusted-types` | **採らない** | 上と同じ理由。`innerHTML` 系の経路が無いので強制すべき対象が無い。Safari 未対応 | — |
| `security/restrict-outbound-connections` — `Connection-Allowlist` ヘッダ | **採らない** | Chrome 152+ / Edge 152+（2026-08）のみ、Firefox・Safari 未対応 | — |
| 同ガイドの CSP フォールバック | **採る。ただしこのフェーズの仕事ではない** | 現状、`backend/app/main.py:292` が API 応答に `default-src 'none'; frame-ancestors 'none'` を付けているが、**画面本体（HTML と JS）を配る経路が本番でまだ決まっていない**（`StaticFiles` のマウントも無く、いまは Vite の開発サーバが配っている）。`<meta http-equiv="Content-Security-Policy">` で入れる案は検討して**却下**した: Vite の HMR が `ws:` とインラインスタイルを要るため開発と `test:appearance` ゲートを壊し、しかも `frame-ancestors` と `report-to` は meta では効かない。**本番配信ジョブ（テーマ 5 の配備手順）の受入条件に回す**のが正しい置き場所 | 新規ジョブは作らない。修正指示 D として本番配信側へ申し送り |
| `security/local-network-access` | **該当しない** | このガイドは「公開オリジンのページが LAN 内の別ホストへ繋ぐ」話で、Locus は画面と API が同一オリジン。`targetAddressSpace` も `local-network` 権限も使う場面が無い。**ただしこのガイドの一文は裏から効く**: 「Local Network Access の権限は `http://` のトップレベル文脈では自動的に拒否される」。LAN プレーン HTTP では権限系 API に望みが無い、という上の判断を裏書きしている | — |
| `ui-atoms/single-line-overflow` | **採らない（既存のままでよい）** | `appearance.spec.ts` に「右端を越えて描画されない」invariant が既にあり、長い資料名の問題はそこで守られている。ガイドが足すのは「切れているときだけフェードさせる」などの演出で、`UI_IMPLEMENTATION_BASELINE.md` の装飾を増やさない方針に反する。スクロール駆動アニメーションは Firefox 159+ とかなり新しい | — |
| `ui-components/menu` / `app-menus` / `tabs` / `toolbar` | **参考にとどめる** | 設定ダイアログの左タブは T-PH6-112 で決まった形があり、呼び名は opencode の公式日本語訳に合わせる決定も済んでいる。ここで別の作法を持ち込むと決定済みの設計を揺らすだけ | — |
| `forms/ime-safe-enter-submit` | **採る＝既に対応済み（確認した）** | `App.tsx:1256-1266` が `event.nativeEvent.isComposing` と `event.keyCode !== 229` の**両方**を見ており、ガイドの「推奨される戦略 1」そのまま。日本語入力の変換確定で送信されない。**申し送り**: ガイドは Safari が `isComposing` 未対応（WebKit bug 165004）と書いているが、`keyCode === 229` 側の判定が Safari でも効くので実害は無い見込み。新しいジョブは不要 | 修正指示 C（規律として記録） |

---

## 2. 既存ジョブへの修正指示

新規ジョブと重複させないため、既に起票済みの 4 件には**修正だけ**を入れる。

### 修正指示 A — `T-PH6-112`（設定ダイアログ）

まだ `allowed_paths: 未確定` なので、確定時に次を**最初から**組み込む。後から直すと差分が倍になる。

1. 設定ダイアログは `<dialog>` を `showModal()` で開く。
   **`role="dialog"` と `aria-modal="true"` を自分で書かない**（ネイティブの modal に付けると
   かえって読み上げが二重になる。ガイドの禁止事項）。自前のフォーカストラップも書かない。
2. 名前は `aria-labelledby` でダイアログ見出しに結ぶ。`autofocus` は最初のタブ、
   または最も安全な操作（閉じる）に置く。
3. 「Esc で閉じる」は無償で入る。**「背景クリックで閉じる」は `closedby="any"` を付けた上で、
   Safari 向けに背景クリックの JS フォールバックも残す**（`closedby` は Safari 未対応）。
4. 閉じる操作は `<form method="dialog">` を使えば JS 不要。
5. `dialog:modal { overscroll-behavior: contain }` と
   `dialog::backdrop { overflow: hidden; overscroll-behavior: contain }` を入れる。
   `html`/`body` に `overflow: hidden` を当てる手口は使わない。
6. **`test_cmd` を `npm --prefix frontend run test` のままにしない。**
   実測で jsdom 29.1.1 に `showModal()` は無いので、単体テストだけではダイアログの
   モーダル性を一切証明できない。`allowed_paths` に
   `frontend/src/test-setup.ts` と `frontend/e2e/appearance.spec.ts` を含め、
   `test_cmd` は `npm --prefix frontend run test && npm --prefix frontend run test:appearance` とする。
7. 設定ダイアログに置く項目のうち、ダークモードの 3 択は `T-PH6-110` の実装を**呼ぶだけ**にする
   （ここで作り直さない）。

### 修正指示 B — `T-PH6-110`（ダークモード）

1. 実装詳細に次を足す: **`:root` に `color-scheme: light dark` を宣言する。**
   これが無いとトークンを暗くしてもスクロールバーとフォーム部品が明るいまま残る。
2. 受入条件 5（明るい配色が一瞬見えてから暗くなることがない）の**手段を指定する**。
   CSS だけでは初期描画に間に合わない。`frontend/index.html` の
   `<meta name="color-scheme">` と直後のインラインスクリプトで解決する。
   このファイルは本ジョブの許可パス外なので、**`T-PH6-118` に切り出した**。
   T-PH6-110 側は受入条件 5 を「`T-PH6-118` で満たす」と書き換え、
   本ジョブでは `theme.ts` の純粋関数と暗い側のトークンまでを担当する。
3. **利用者の 3 択は `color-scheme` の値を切り替える形で実装すること**（クラス付与ではなく）。
   トークンを `light-dark()` で書く場合、`light-dark()` は使用中の `color-scheme` しか見ないため、
   クラスで分岐すると利用者の選択が効かない。`theme.ts` の出力は
   `"light" | "dark" | "light dark"` の 3 値（システム追従は `light dark`）にする。
4. 受入条件 2「暗い配色が明るい側の単純な反転ではないこと」は維持。
   `light-dark()` を使っても明暗 2 値を別々に書くので、この条件と矛盾しない。

### 修正指示 C — `T-PH6-111`（入力欄の固定と参照範囲）

このジョブは実装済みでレビュー待ちなので、**作り直しを命じない**。記録だけ残す。

1. `isComposing` + `keyCode === 229` の二重判定（`App.tsx:1256-1266`）は
   `forms/ime-safe-enter-submit` の推奨そのままで、**正しい。変更不要**。
   レビューで「冗長だから片方消す」と言われないように、ここに根拠を残す。
2. Popover API への載せ替えは**このジョブではやらない**。マージ後の `T-PH6-117` で行う。
   いま差し込むと、レビュー待ちの差分をもう一度動かすことになる。
3. 受入条件 4・5（入力欄が見えている / 最後の発言が隠れない）の本当の根拠は
   「入力欄をスクロール容器の外に出した」という**構造**であり、`scroll-padding` ではない。
   `scrollIntoView` での着地位置は別問題で、`T-PH6-120` が扱う。
4. 受入条件の番号が重複している（4 と 5 が 2 回ずつ）。振り直す。

### 修正指示 D — `T-PH6-115`（注意書きの常時表示）と本番配信側への申し送り

1. `T-PH6-115` の注意書きは `.messages`（スクロール容器）の**外**か `sticky` で置くことになるが、
   どちらにしても `scrollIntoView` の着地点がこの帯の裏に入る。
   受入条件に「`scroll-padding-block-start` を注意書きの高さ分確保する」を足すか、
   さもなくば `T-PH6-120` の `depends_on` に入れる。後者を推す（1 か所で面倒を見るため）。
2. **本番配信ジョブへの申し送り**（このフェーズのジョブにはしない）:
   画面本体を配る経路を決める際、応答ヘッダに
   `Content-Security-Policy: default-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`
   を付けることを受入条件に含める。`<meta http-equiv>` 版は Vite の HMR を壊し、
   `frame-ancestors` が効かないので採らない。`Connection-Allowlist` ヘッダは
   Chrome 152+ 専用なので採らない。

---

## 3. 新規ジョブ一覧

| ID | 内容 | weight | depends_on |
|---|---|---|---|
| `T-PH6-116` | 出典モーダルを `<dialog>` + `showModal()` に移し、自前フォーカストラップを撤去する | medium | — |
| `T-PH6-117` | 参照範囲のポップアップを Popover API に載せ替える（アンカー配置は採らない） | medium | `T-PH6-111` |
| `T-PH6-118` | `color-scheme` を宣言し、初期描画のちらつきを `<meta>` で止める | light | `T-PH6-110` |
| `T-PH6-119` | ルートの `font-size: 14px` を撤去し、OS の文字サイズ設定に従う | heavy | — |
| `T-PH6-120` | 発言へ飛んだときに注意書きと入力欄の裏へ着地しないようにする | light | `T-PH6-111`, `T-PH6-115` |
| `T-PH6-121` | チャット列を容器クエリで分岐させる（サイドバーの開閉を幅判定に反映する） | medium | `T-PH6-112` |
| `T-PH6-122` | 入力欄の高さを `field-sizing: content` で内容に合わせる | light | `T-PH6-111` |
| `T-PH6-123` | 入力検証を `:user-invalid` に合わせ、`aria-invalid` を同期する | medium | — |
| `T-PH6-124` | SecureContext 専用 API の使用を止め、再発を検査で止める | light | — |

すべてのジョブに、`frontend/e2e/appearance.spec.ts` への検査追加を受入条件として入れている。
`screen-invariants` スキルの規律（まず壊れていることを**測る**、次に通す）に従うこと。
