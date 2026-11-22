---
id: T-AIC-006
phase: phase-ai-connect
status: blocked
assignee: unassigned
model: -
weight: medium
updated: 2026-11-22T14:30:00+09:00
attempts: 0
allowed_paths: progress/phase-ai-connect/material/
test_cmd: python -m pytest tests/test_agents_registry.py -q
---

# Task `T-AIC-006`: 利用者ごとの資格情報をサーバで持つための設計（設計のみ）

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR`（必須要件 4）。
  **オーナー決定 2026-11-22**:「外部サービスの利用はユーザー毎に行えるようにしたいので、
  サーバー側でユーザーごとに管理したい」。
- **`blocked` の理由**: 下の「オーナーに確認したいこと」に答えが出るまで着手しない。
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
  1. **(A) の保管方式**を決めて書く。少なくとも次を明記する。
     - 保管先（DB の新テーブルか、OS の資格情報ストアか）。
       オーナー回答 2026-11-16 E5 は「OS 管理で良い」だが、**サーバプロセスが
       複数利用者分を読む**用途では Windows の DPAPI は利用者単位で機能しない。
       採る案と、その制約を書くこと。
     - **保存時暗号化**をするか。するなら鍵の置き場（DB の中に鍵を置いたら暗号化の意味がない）。
     - **出さない場所の一覧**: API 応答・監査・ログ・画面・例外メッセージ。
       presence（有無）だけを出す既存方針は維持する。
     - 失効（利用者の削除、鍵の無効化）でどうなるか。
     - **誰が読めるか**: 他人の鍵が読めないことをどう保証するか。
       `system_admin` でも他人の鍵の**値**は読めない形にするか。
  2. **(B) をどうするか**を決めて書く。既定の推奨は「端末側のまま」。
     サーバで持つ案を採るなら、**presence-only の不変条件を変える理由**と、
     失うもの（サーバ侵害時の被害範囲）を明記すること。
  3. **`credential_schema_is_presence_only` をどう扱うか**を書く。
     - (A) を別テーブルにすれば、この guard は**そのまま維持できる**。
       推奨はこれ（guard を弱めない）。
     - 同じテーブルに値を足すなら、guard を外すことになる。
       **外すなら、代わりに何が守るのか**を書くこと。
  4. 受入条件に落とせる検証項目を、合否条件つきで列挙する
     （mock・合成データのみで実施できる範囲に限る）。

- **オーナーに確認したいこと**（これが決まるまで `blocked`）:
  1. **(B) は端末側のままで良いか。** 上の表の読みで合っているか。
     「Agent SDK 埋め込み」を **Desktop Runner に埋め込む**と読めば、
     サーバは利用者のログインを預からずに済む。その読みで良いか。
  2. (A) の鍵を**暗号化して DB に置く**ことを認めるか。
     認める場合、暗号鍵はサーバ環境変数／OS ストアのどちらに置くか。
  3. **管理者が他人の鍵の値を読めない**設計にするか
     （監査可能性と秘匿性のどちらを優先するか）。

## Acceptance Criteria

1. (A) と (B) の扱いが別々に書かれ、どちらも「出さない場所の一覧」を持っている。
2. `credential_schema_is_presence_only` を**維持する**設計になっている
   （維持しない場合、代わりに何が守るのかが書かれている）。
3. 検証項目に合否条件が付いている。
4. **コード・スキーマ・dispatch の挙動を一切変更していない**
   （`tests/test_agents_registry.py` が従来どおり PASS することで示す）。

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
