---
id: T-AIC-005
phase: phase-ai-connect
status: todo
assignee: unassigned
model: -
weight: medium
updated: 2026-11-22T14:30:00+09:00
attempts: 0
allowed_paths: backend/app/harness.py, tests/test_harness_egress.py
test_cmd: python -m pytest tests/test_harness_egress.py tests/test_agents_registry.py tests/test_api.py -q
---

# Task `T-AIC-005`: 外部送信のハーネス層（分類ガードの一点集約）

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR`（必須要件 5・7）。
  **オーナー決定 2026-11-22**:「ハーネス層を作成してそこに分類ガードを置く」。
- **なぜこの票があるか**: 草案の `T-AIC-002` §3 は分類ガードの置き場所を
  「実装時に既存のポリシー判定に合わせる」と**未確定**にしていた。
  未確定のスコープは今日までに 3 件のジョブを止めている
  （`T-PH6-104` は許可パスから外した `service.py` を必要とする受入条件が残っていた）。
  オーナーの指示どおり**置き場所を先に決め、1 つの通り道にする**。
- **設計の要点**: 外部へ出る経路は**この層を通る以外にない**ようにする。
  アダプタ（`T-AIC-001`）は**運び屋**で、判定も資格情報の解決もしない。

  ```
  会話経路 → harness.send(actor, workspace, model, text, citations, on_delta)
                 1. 分類・egress の判定（不明＝拒否）
                 2. 利用者ごとの資格情報の解決（T-AIC-006 の設計に従う）
                 3. 監査（判定結果・宛先・利用者・workspace。本文は残さない）
                 4. アダプタ呼び出し（鍵は引数で渡す）
  ```

- **Implementation Details**:
  1. 新規 `backend/app/harness.py` に `Harness` を実装する。
     公開面は 1 つだけ: `send(...)`。**アダプタを直接呼ぶ経路を他に作らない。**
  2. **判定（分類・egress）**:
     - workspace の `classification_ceiling` と `egress_mode` を読む。
     - `egress_mode` が `local_only` なら**外部送信を拒否**する
       （現在のスキーマは `CHECK(egress_mode IN ('local_only'))` なので、
       いまは**常に拒否**になる。これは正しい。解禁は別の決定であり、
       **この票でスキーマを変更しない**）。
     - 分類が判定できない場合は**拒否**する（「不明＝拒否」。要件 5）。
     - 拒否は `fail(403, ...)` とし、理由に資格情報・URL・本文を含めない。
  3. **資格情報は受け取るだけ**: `Harness` は解決の*呼び出し*を行うが、
     保管方式は `T-AIC-006` の設計が決める。本票では
     `resolve_credential(actor) -> str | None` という**注入される関数**を受け取る形にし、
     既定の実装は「常に `None`（＝未設定として拒否）」とする。
     **本票で鍵の保管・復号・環境変数読み取りを実装しない。**
  4. **監査**: 判定結果（許可／拒否と理由の種別）、利用者、workspace、宛先の種別、
     モデル名を残す。**本文・資格情報・URL の資格情報部分は残さない。**
     既存の監査ポートを使い、新しい監査基盤を作らない。
  5. `loop_engine/**` を変更しない。`backend/app/agents/registry.py` も変更しない
     （ポリシーは**読む**だけ。読み取り関数は注入で受け取る）。

## Acceptance Criteria

1. `tests/test_harness_egress.py` に次の合成テストがある。
   - `egress_mode` が `local_only` の workspace からの送信が **403 で拒否**され、
     アダプタが**一度も呼ばれない**こと（呼ばれたら落ちるスパイで示すこと）。
   - 分類が判定できない workspace からの送信が **403 で拒否**されること。
   - 拒否が監査に残り、**本文・資格情報が監査に現れない**こと。
   - `resolve_credential` が `None` を返すとき**拒否**されること（既定で閉じている）。
   - 許可された場合にアダプタへ渡る引数に、鍵が**引数として**渡ること
     （クラス属性やグローバルに置かれていないこと）。
2. **外部送信の経路がこの層以外に無いこと**を示すこと。
   どう確かめたかを報告に書く（grep の条件など）。
3. `python -m pytest tests/test_harness_egress.py tests/test_agents_registry.py tests/test_api.py -q` が PASS。
   `ruff check` / `ruff format --check` が PASS。
4. 既存テストの削除・skip・緩和は禁止。変更は許可パス内に収まる。
   **スキーマを変更しない。** `egress_mode` の `CHECK` を広げない。

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
