---
id: T-AIC-007
phase: phase-ai-connect
status: todo
assignee: unassigned
model: -
weight: light
depends_on: T-AIC-002
allowed_paths: backend/app/main.py, tests/test_model_catalog.py
test_cmd: python -m pytest tests/test_model_catalog.py -q
updated: 2026-11-25T18:50:00+09:00
attempts: 0
---

# Task `T-AIC-007`: リモートモデルを無効にしたとき、資格情報と応答の形を後始末する

## SCOPE — レビュアーへ（先に読むこと）

- **この票は `T-AIC-002` のやり直しではない。** あの票の受入条件は
  discover と選択・会話応答・**API キーの値が runtime 応答／監査／カタログ応答に
  現れないこと**・会話経路がハーネスを通ること・Ollama の退行なし・許可パス内の 6 つで、
  **プロセス内のメモリに残ることと、未設定時の応答の項目の揃え方は名指ししていない**。
  だからこの票に分けた。
- **判断はこの票の受入条件に対して行うこと。** 条件の外で気づいたことは
  `## REVIEW` に所見として書き、`CHANGES_REQUIRED` の理由にしないこと。

## TASK DEFINITION (Assigned by Orchestrator)

- **なぜこの票があるか**: 2026-11-25 15:20 の `T-AIC-002` のレビューが Low として
  挙げた 2 件がそのまま根拠である。どちらも本物だが、あの票の受入条件の外にある。

- **1 件目: 無効にしても資格情報がメモリに残る**
  - `backend/app/main.py`（`discover_models` の末尾、`remote_runtime._base_url` と
    `remote_runtime._api_key` を置く箇所。2026-11-25 18:50 時点で 831〜834 行目付近）。
    discover が成功すると `_base_url` / `_api_key` が `remote_runtime` に残る。
    **モデルを無効にする経路（`candidate_id` が `None`）で消していない**ので、
    無効にした後もプロセスの中に残り続ける。
  - **これは漏洩ではない**（`T-AIC-002` の受入条件 3 が守る「応答・監査・カタログに
    値が現れない」は別に満たされている）。残すべきでないものを残しているという話である。

- **2 件目: 未設定時の応答の項目が、ローカルとリモートで揃っていない**
  - `backend/app/main.py` の `model_runtime` の GET（同 841〜857 行目付近）。
    動いている runtime がリモートで、まだモデルを選んでいないとき、応答は
    `api_key_present: False` を持つ（`OpenAICompatibleModel.status()` が固定で返す）が
    `provider` は付かない。ローカルの未設定時は `api_key_present` を**そもそも出さない**。
    **同じ「未設定」で項目の集合が違う**ので、画面側が二通りの形を扱う必要が出る。

- **Implementation Details**:
  1. 無効にする経路で `_base_url` / `_api_key` を消すこと。
     **消す場所は 1 つにまとめること**（無効化が複数の入口から呼ばれるなら、
     後始末を関数にして呼ぶ）。
  2. 未設定時の応答の項目をどちらかに揃えること。
     **どちらに揃えたかと、その理由を REPORT に書くこと**
     （`api_key_present` を両方出す／両方出さない、どちらでもよい）。
     既に画面側が読んでいる項目を消すなら、**消して困らないことを確かめてから**にする
     （`frontend/` はこの票の許可パスの外なので、読んで確かめるだけ。変更しない）。
  3. `OpenAICompatibleModel.status()` は許可パスの外である。そこを直す必要があると
     判断した場合は、**直さずに REPORT に書いて次の票へ回すこと**。

## ACCEPTANCE CRITERIA

1. リモートモデルを無効にした後、`_base_url` と `_api_key` が残っていないことを
   示すテストがある（discover で設定 → 無効化 → 消えていることを確認）。
2. 無効化が複数の入口から起きる場合、**どの入口からでも消える**ことを示すテストがある。
   入口が 1 つだけなら、1 つであることを REPORT に書けばよい。
3. 未設定時の応答の項目が、ローカルとリモートで**同じ集合**であることを示すテストがある。
4. `T-AIC-002` の受入条件 3（API キーの値が runtime 応答・監査・カタログ応答の
   どこにも現れない）に**退行がない**ことを示すテストが、引き続き緑である。
5. `python -m pytest tests/test_model_catalog.py -q` が緑。
   `python -m ruff check backend tests scripts jobloop` と
   `python -m ruff format --check backend tests scripts jobloop` が緑。
   `python scripts/secret_scan.py <変更したファイル>` が 0 findings。
6. 資格情報らしい文字列を検査に埋める必要がある場合は、**走査が許している値だけ**を
   使うこと（`sk-synthetic-0N-not-a-real-key` の形。他の値は走査が落ちる）。
7. 変更が `allowed_paths` 内に収まっている。
