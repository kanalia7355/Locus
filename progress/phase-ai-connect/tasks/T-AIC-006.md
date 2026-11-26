---
id: T-AIC-006
phase: phase-ai-connect
status: review
assignee: agy
model: agy/gemini-4-carbon-low
weight: medium
updated: 2026-11-26T11:55:30+09:00
attempts: 0
allowed_paths: progress/phase-ai-connect/material/
test_cmd: python -m pytest tests/test_agents_registry.py -q
---

# Task `T-AIC-006`: 利用者ごとの資格情報をサーバで持つための設計（設計のみ）

## SCOPE — 実装とレビューへ（2026-11-25 20:30 追記。先に読むこと）

- **この票は一度、レビューを経ずに統合ブランチへ入ってしまった。**
  入れたのはオーケストレーターの裁定コミット `b7041a6`（2026-11-23）で、
  **私の誤りである。** オーナーの決定（2026-11-25、E1・選択 B）により、
  その分を統合ブランチから外し、**正規の経路で納め直す。**
- **成果物は失われていない。** 元の内容は commit `b7041a6` の
  blob `0d2b822d08f158edecdadba89d1d0624e7254d49`（33,069 バイト）として
  git 履歴に在り、ワークスペース `T-AIC-006` にも残っている。
  **実装は、これを土台にしてよい** — 一から書き直す必要はない。
  ただし**自分の目で読み、受入条件に照らして足りない所を直すこと。**
  「前に誰かが書いたから正しい」は根拠にならない。
- **レビューは、この設計書をまだ誰も見ていないものとして扱うこと。**
  過去の `## REPORT` / `## TEST` / `## REVIEW` が空のテンプレートなのは、
  レビューが一度も行われていないからである。
- **判断はこの票の受入条件に対して行うこと。** 条件の外で気づいたことは
  `## REVIEW` に所見として書き、`CHANGES_REQUIRED` の理由にしないこと
  （2026-11-25 の E3・選択 A による）。

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR`（必須要件 4）。
  **オーナー決定 2026-11-22**:「外部サービスの利用はユーザー毎に行えるようにしたいので、
  サーバー側でユーザーごとに管理したい」。
- **`todo` にした理由（2026-11-22）**: 3 点すべてに回答が出た。
  下の「オーナー決定（2026-11-22）」が正本である。
  **コードを書く票ではない。** 設計が決まる前に実装すると、受入条件が「動いた」になる。

- **なぜ設計を先に書くか（実測した事実）**:
  1. いまの `adapter_credentials` テーブルは
     `(runner_instance_id, adapter_id, state, checked_at)` で、**値の列が無い**
     （`backend/app/agents/registry.py:154-160`）。
  2. その形は**起動時に機械で守られている**。
     `credential_schema_is_presence_only()` が列の集合を照合し、違えば
     `RuntimeError("adapter_credentials schema is not presence-only")` で**起動を止める**
     （`registry.py:53-56, 186-187`）。
  3. つまり「サーバで値を持つ」は、**この不変条件に正面からぶつかる**。
     黙って回避してはいけない。意図して変えるなら、何を失うかを書いてから変える。

- **2 種類の資格情報を混ぜないこと**（ここが設計の中心）:

  | | (A) プロバイダの API キー | (B) エージェントの資格情報 |
  |---|---|---|
  | 例 | OpenAI 互換エンドポイントの鍵 | Claude Code / Codex のログイン |
  | 誰が呼ぶか | **サーバ**が HTTP を出す | エージェント本体が出す |
  | サーバが値を持つ必要 | **ある**（サーバが呼ぶので避けられない） | **無い**（端末側のログインで足りる） |
  | 既存設計 | 規定なし | `HYBRID_AGENT_ADAPTER_DESIGN.md` §4.2 Option 1 = 端末側保持 |

  **(A) は持たざるを得ないが、(B) は持たなくても要件を満たせる。**
  オーナーの要望は「チャット画面で接続した利用者が、モデル管理の部分で選択できること」
  であって、**サーバが利用者の Claude ログインを預かること**ではない。
  (B) を端末側に置いたままでも、その UX は成立する（選択は metadata で足りる）。
  **混ぜて 1 つの箱に入れると、(A) のために開けた穴から (B) が漏れる。**

- **Implementation Details**（`progress/phase-ai-connect/material/` に設計文書を書く。コードは書かない）:
  1. **(A) の保管方式を書く。保管先は決定済み（DB・暗号化）なので、設計するのは
     「どう守るか」である。** 少なくとも次を明記する。
     - **新テーブルの定義**（`adapter_credentials` には足さない。決定 3-a）。
       暗号文の列名は**値でないことが名前から分かる**形にする
       （例 `secret_ciphertext`）。平文列を作らない。
     - **暗号鍵（KEK）の置き場**。DB の中は不可（決定 2 の導出、下記）。
       サーバ環境変数か OS の資格情報ストアかを選び、**選ばなかった方の理由**を書く。
       `.env` 等を**リポジトリに置かない**ことを明記する。
     - **鍵の交換（rotation）**で既存の暗号文がどうなるか。
     - **出さない場所の一覧**: API 応答・監査・ログ・画面・例外メッセージ。
       presence（有無）だけを出す既存方針は維持する。
     - 失効（利用者の削除、鍵の無効化）でどうなるか。
     - **読めるのは誰か**: 復号できるのは**鍵の持ち主である利用者の要求を処理する
       経路だけ**。`system_admin` でも他人の値は読めない（決定 3）。
     - **主張の範囲を正直に書く**（`DOCUMENT_EXTRACTION_BOUNDARY.md` §5 と同じ作法）。
       守れるのは **アプリ経路と DB 読み取りに対して**である。
       サーバの**ホストに root 相当で入れる者**は KEK ごと取れるので、
       そこまでは守れない。**守れない保証を「守れる」と書かないこと。**
  2. **(B) は端末側のまま**（決定 1）。サーバは利用者の Claude / Codex ログインを
     預からない。`HYBRID_AGENT_ADAPTER_DESIGN.md` §4.2 Option 1 を維持する理由と、
     それでもオーナーの要望（チャット画面のモデル管理から選べる）が成立することを
     書く（選択は metadata で足りる）。**(A) の箱に (B) を入れないこと。**
  3. **`credential_schema_is_presence_only` をどう扱うか**を書く。
     - (A) を別テーブルにすれば、この guard は**そのまま維持できる**。
       推奨はこれ（guard を弱めない）。
     - 同じテーブルに値を足すなら、guard を外すことになる。
       **外すなら、代わりに何が守るのか**を書くこと。
  4. **「バグっても破れない」仕組みを設計する**（決定 3 の指示）。
     規約や査読ではなく、**機械が落とす**形にする。少なくとも次の 4 つを
     合否条件つきで設計する（実装は本票ではなく後続票）。
     a. **起動時ガード**: 新テーブルに平文の値を入れる列が無いことを起動時に照合し、
        違えば `RuntimeError` で**起動を止める**。
        既存の `credential_schema_is_presence_only()`（`registry.py:53-56, 186-187`）が
        先例であり、**同じ語彙・同じ失敗方式**にすること。新しい流儀を作らない。
     b. **復号経路の一点化**: 復号できる関数を 1 つに絞り、**要求者の利用者 ID を
        引数に取る**。他人の ID では例外。ID を省略して呼べる形にしない。
     c. **管理者でも読めないことの検査**: `system_admin` を持つ主体で他人の鍵を
        読もうとして**拒否されること**を検査で固定する（`registry.py:275, 725` に
        既存の `system_admin` 分岐があるので、そこに穴が開いていないことも見る）。
     d. **漏れの検査**: API 応答・監査レコード・ログ・例外文字列に暗号文の列名と
        値が現れないことを検査する。
     それぞれ「何をしたら落ちるか」を書くこと。落ちない検査は検査ではない。
  5. 上記以外の検証項目も、合否条件つきで列挙する
     （mock・合成データのみで実施できる範囲に限る）。

- **オーナー決定（2026-11-22）** — これが設計の前提である:
  1. **(B) エージェントの資格情報は端末側のまま。** 上の表の読みで合っている。
     サーバは利用者の Claude / Codex ログインを預からない。
  2. **(A) プロバイダの API キーは DB に置く**（暗号化して保存する）。
  3. **管理者でも他人の鍵の値は読めないようにする。**
     かつ「**バグらないように**」機械的な検査を付けること
     — つまり**規約ではなく、破れたら落ちる仕組み**にする。
- **決定から導いた判断（オーナーに聞き直さずに決めたこと。違えば覆してよい）**:
  - **KEK（暗号鍵）を DB の中に置くことはできない。** 決定 3 が
    「管理者でも値は読めない」なので、DB を読める者が復号できては決定が無効になる。
    よって鍵は**DB の外**（サーバ環境変数か OS の資格情報ストア）に置く。
    どちらを採るかは本票の設計で決める。
  - **(A) は `adapter_credentials` に足さず、新しいテーブルにする。**
    そうすれば `credential_schema_is_presence_only()` を**弱めずに**済む
    （不変条件を外さないで決定を満たせるなら、外さないのが正しい）。
  - **「管理者でも読めない」は守れる範囲を限って主張する。**
    アプリ経路と DB 読み取りには効くが、**ホストに root 相当で入れる者**には効かない。
    `DOCUMENT_EXTRACTION_BOUNDARY.md` §5 で採った作法（弱い方の保証しか主張しない）と
    同じにする。**強い方を書いたら受入条件 5 で落とす。**

## Acceptance Criteria

1. (A) と (B) の扱いが別々に書かれ、どちらも「出さない場所の一覧」を持っている。
   (B) は**端末側のまま**になっている（決定 1）。
2. (A) は **DB の新テーブル・保存時暗号化**で、**KEK は DB の外**に置く設計になっている
   （決定 2 とその導出）。採った置き場と、採らなかった方の理由が書かれている。
3. `credential_schema_is_presence_only` を**維持する**設計になっている
   （維持しない場合、代わりに何が守るのかが書かれている）。
4. **「管理者でも他人の値は読めない」を機械が守る形**で、Implementation Details 4 の
   a〜d の 4 つが**それぞれ「何をしたら落ちるか」つきで**書かれている（決定 3）。
   起動時ガードは既存 `credential_schema_is_presence_only()` と同じ失敗方式
   （`RuntimeError` で起動停止）であること。
5. **主張の範囲が正直である**: 「管理者でも読めない」がアプリ経路と DB 読み取りに
   限られること、ホストに root 相当で入れる者には効かないことが書かれている。
   守れない保証を主張していないこと。
6. 検証項目に合否条件が付いている。
7. **コード・スキーマ・dispatch の挙動を一切変更していない**
   （`tests/test_agents_registry.py` が従来どおり PASS することで示す）。
8. 変更が許可パス内に収まっている（`material/` のみ）。

## REPORT

- Implemented by:
- Changed Files:
- Summary:

## TEST

- Commands run:
- Results:

## REVIEW

- Reviewer:
- Findings:

## CONTAINMENT UNVERIFIED (2026-11-23T21:25:06+09:00)

The operator was editing the main checkout during this cycle, so the containment comparison was suspended. The worker's isolation was not verified for this attempt.

## WORKSPACE REBASED (2026-11-23T23:16:12+09:00)

The workspace was 2 commit(s) behind `loop/local-development` and had no work in progress, so it was reset onto the current branch. Nothing of this job's own was discarded.

## WORKSPACE REBASED (2026-11-25T12:43:04+09:00)

The workspace was 66 commit(s) behind `loop/local-development` and had no work in progress, so it was reset onto the current branch. Nothing of this job's own was discarded.

## OWNER DECISION REQUESTED (2026-11-25T12:47:36+09:00)

attempt limit reached: Three attempts did not satisfy the acceptance criteria; the job needs a human decision.

## ORCHESTRATOR RULING (2026-11-25 13:20)

**試行を 3/3 から 0/3 に戻す。ただし `blocked` のまま置く — これはオーナーの判断を待つ。
ワーカーに回してはならない。**

**3 回の「the worker changed nothing」は正直な報告だった。** この票の成果物
`progress/phase-ai-connect/material/USER_CREDENTIAL_DESIGN.md` は**既に統合ブランチに
存在する**（33,069 バイト）。ワークスペースの HEAD 版と本体の HEAD 版はバイト単位で同一で、
ワークスペースは `ahead=0` である。**残っている仕事が無いのだから、変えるものも無い。**
その 3 回に対して予算を請求するのは誤りなので戻す。

**なぜそうなったか — これは私の誤りである。** このファイルが統合ブランチに入ったのは、
2026-11-23 の私の裁定コミット **`b7041a6`（「1 件の逸脱が 2 件を止めていた。
切り分けて両方戻す」）** である。逸脱の切り分けをしたときに、**ワーカーの成果物を
レビューを経ずに統合ブランチへ持ち込んだ。** 証拠はこの票の記録そのもので、
`## REPORT` / `## TEST` / `## REVIEW` の 3 節が**いずれも空のテンプレートのまま**である。
この票は一度もレビューされていない。

**ワーカーに回せない理由**: 差分が 0 バイトなので、レビューに出しても
「対象が 1 バイトも変わっていない」経路に入り、モデルを回し続けるだけで何も決まらない。
実装に回しても、ワーカーは正しく「変えるものが無い」と答える。
**状態を動かして解ける種類の詰まりではない。**

**私が決めてはならない理由**: 残っているのはレビューだけであり、
**レビューの承認を私が与えることは禁じられている**（`Never: Mark a job done yourself,
or approve a review`）。受入条件 1〜8 を私が読んで「満たしている」と宣言することは、
その禁止を回り込むことになる。

**オーナーに伺う二択**（どちらも私には選べない）:

1. **この設計書をレビュー無しで受け入れる。** 私の `b7041a6` が既に統合ブランチへ
   入れてしまっているので、現状を事後承認する形になる。
2. **`b7041a6` が入れた分を統合ブランチから外し、この票に正規の経路で納め直させる。**
   成果物は git の履歴とワークスペースの両方に残っているので失われない。
   ただし 1 票分の実装とレビューをやり直すことになる。

**1 を選ぶ場合も、受入条件 7**（コード・スキーマ・dispatch を一切変更していないこと。
`tests/test_agents_registry.py` が従来どおり PASS）**は機械で確かめられる**ので、
それだけは別に確認できる。受入条件 1〜6 は文書の中身の判断なので人かレビュアーが要る。

## OWNER DECISION APPLIED — 正規の経路で納め直す (2026-11-25 20:30)

**オーナーの決定（2026-11-25、E1・選択 B）**:

> B正規の経路で通す。(今通しても後で戻しが発生するなら通す意味ないし)

**示された判断**: レビュー無しで通したものは、後で戻しが発生する可能性が残る。
それなら通した意味が無い。**「いま速いこと」より「戻しが起きないこと」を採る。**

### 私がしたこと

1. **`progress/phase-ai-connect/material/USER_CREDENTIAL_DESIGN.md` を
   統合ブランチから削除した。** `b7041a6` が入れた分である。
2. **成果物は失われていない。** 元の内容は
   blob `0d2b822d08f158edecdadba89d1d0624e7254d49`（33,069 バイト）として
   commit `b7041a6` に在り、ワークスペース `T-AIC-006` にも残っている。
   **復元に必要な情報はこの 2 行で足りる。**
3. **前書きを `todo` / `attempts: 0/3` / `assignee: unassigned` / `model: -` に戻した。**
   通常の派遣に乗る。
4. **冒頭に SCOPE を置いた** — 実装には「土台にしてよいが自分の目で読め」、
   レビューには「まだ誰も見ていないものとして扱え」と書いた。

### 変えていないこと

**受入条件は 1 文字も変えていない。** 受入条件 7（コード・スキーマ・dispatch を
変更していないこと）も含めてそのままである。

### 私の誤りについて

2026-11-23 に `T-AIC-002` の逸脱を切り分けたとき、**同じコミットで
ワーカーの成果物をレビュー無しに持ち込んだ**。切り分けと取り込みは別の作業であり、
一緒にやってはいけなかった。この票が 2 日間 `blocked` で止まり、
3 回の「the worker changed nothing」を記録し、
最後にオーナーの判断を要したのは、すべてその結果である。

## WORKSPACE REBASED (2026-11-26T11:50:17+09:00)

The workspace was 125 commit(s) behind `loop/local-development` and had no work in progress, so it was reset onto the current branch. Nothing of this job's own was discarded.

## ATTEMPT 1 — implementation by agy/gemini-4-carbon-low (2026-11-26T11:55:30+09:00)

REPORT
- Changed files and reasons:
  - [USER_CREDENTIAL_DESIGN.md](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-AIC-006/progress/phase-ai-connect/material/USER_CREDENTIAL_DESIGN.md): Created the design-only specification for per-user credential handling (`T-AIC-006`, `HBR` requirement 4), starting from git blob `0d2b822d08f158edecdadba89d1d0624e7254d49` and tightening it against all Acceptance Criteria (1–8) and phase boundaries:
    - Separated `(A)` provider API keys (stored encrypted in a dedicated DB table `user_provider_credentials` with AEAD + AAD + per-write random nonce) and `(B)` agent credentials (kept client-side per [HYBRID_AGENT_ADAPTER_DESIGN.md](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-AIC-006/docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md) §4.2 Option 1, explaining why model-management selection UX works via metadata alone), with explicit prohibited-output location tables for both `(A)` and `(B)`.
    - Specified KEK placement outside the DB via server environment variable / secret-manager env injection, documented why OS credential stores were not chosen as the default, prohibited committing `.env` or KEK literals to the repository, and defined key rotation (`kek_version` N → N+1 re-encryption) and revocation / user deletion behavior.
    - Preserved `credential_schema_is_presence_only()` in [registry.py](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-AIC-006/backend/app/agents/registry.py#L53-L56) and [registry.py](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-AIC-006/backend/app/agents/registry.py#L186-L187) unchanged by isolating `(A)` into a separate table, and removed banned column-name marker `"credential"` from the proposed non-secret label column (`display_label` instead of `credential_label`) so the startup guard (`§5a`) and table definition (`§2.1`) are self-consistent.
    - Designed the four mechanical guards (`5a` startup `RuntimeError` schema guard matching `credential_schema_is_presence_only()`, `5b` single decryption function requiring `requester_user_id` with AST boundary enforcement, `5c` explicit `system_admin` cross-user denial check including [registry.py](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-AIC-006/backend/app/agents/registry.py#L275) and [registry.py](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-AIC-006/backend/app/agents/registry.py#L725) boundary verification, and `5d` leak scanning across API responses, audit rows, logs, and exception strings for plaintext, `"secret_ciphertext"`, and ciphertext bytes), each with explicit fail/pass conditions, plus additional mock/synthetic verification cases (`VT-1`–`VT-5`, `NV-1`–`NV-5`) using the approved `sk-synthetic-01-not-a-real-key` fixture from [secret_scan.py](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-AIC-006/scripts/secret_scan.py#L41-L45).
    - Stated the security claim boundary honestly following [DOCUMENT_EXTRACTION_BOUNDARY.md](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-AIC-006/docs/architecture/DOCUMENT_EXTRACTION_BOUNDARY.md#L59-L89): protection holds against application paths and DB reads, and does not hold against host-root-equivalent actors who can read server environment variables or process memory alongside the DB.
- Inconsistencies found between documentation and code:
  - In [T-AIC-006.md](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-AIC-006/progress/phase-ai-connect/tasks/T-AIC-006.md) (`SCOPE` and `OWNER DECISION APPLIED`), the brief notes that the original artifact remained in workspace `T-AIC-006` as well as in git blob `0d2b822d08f158edecdadba89d1d0624e7254d49`; in actual workspace state after the branch reset onto `loop/local-development`, `progress/phase-ai-connect/material/USER_CREDENTIAL_DESIGN.md` was absent from the working tree while blob `0d2b822d08f158edecdadba89d1d0624e7254d49` was present in git object storage (`33,069` bytes).
  - [PROTOCOL.md](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-AIC-006/docs/agent/PROTOCOL.md#L30-L32) describes workers updating `progress/<phase>/tasks/<TASK-ID>.md` directly under the `pi` harness, whereas the active `jobloop` controller enforces `allowed_paths` (`progress/phase-ai-connect/material/` only) and records task progress deterministically from the worker's structured reply; followed the controller's `allowed_paths` boundary.
  - [.bootstrap/complete.json](file:///C:/Users/hirot/.jobloop-Locus/workspaces/T-AIC-006/.bootstrap/complete.json#L20-L43) records the historical ruff targets `backend tests scripts`, whereas the current controller gate and repository layout include `jobloop` (`ruff check backend tests scripts jobloop`).
- Risks left behind:
  - This task delivers a design gate document only; none of the runtime schema guards, encryption/decryption functions, API endpoints, or automated leak/authorization tests for `user_provider_credentials` exist in code until the follow-up implementation task lands.
  - As documented in `§2.7`, host-root-equivalent actors can access both the external KEK (environment/process memory) and the DB ciphertext, and audit-log tamper resistance (`T-T4`) remains a separate unimplemented work item.

TEST
- `Test-Path progress/phase-ai-connect/material/USER_CREDENTIAL_DESIGN.md` (before writing, to verify missing target document) -> `False` (exit 0)
- `.venv/Scripts/python.exe -V; .venv/Scripts/python.exe -m pip check` -> `Python 3.13.2`, `No broken requirements found.` (exit 0)
- `.venv/Scripts/python.exe -m pytest tests/test_agents_registry.py -q && ...` -> PowerShell 5.1 parser error (`The token '&&' is not a valid statement separator in this version.`, exit 1)
- `.venv/Scripts/python.exe -m pytest tests/test_agents_registry.py -q` -> `12 passed in 6.32s` (exit 0)
- `.venv/Scripts/python.exe -m ruff check backend tests scripts jobloop` -> `All checks passed!` (exit 0)
- `.venv/Scripts/python.exe -m ruff format --check backend tests scripts jobloop` -> `200 files already formatted` (exit 0)
- `.venv/Scripts/python.exe scripts/secret_

### Controller gates

- `scope`: green
- `task-verification`: green
- `secret-scan`: green

## WAITING FOR A REVIEWER (2026-11-26T11:55:30+09:00)

`agy/gemini-4-carbon-low` implemented this, and no other free model is off cooldown, so there is nobody to review it. Self-review is prohibited (CONSTRAINTS.md §5-5). This is a wait, not a decision: the job stays in `review` and the next cycle tries again once a model is back. Nothing was approved, nothing was merged.
