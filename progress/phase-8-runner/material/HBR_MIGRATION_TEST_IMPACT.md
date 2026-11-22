# 移行で落ちる既存テストの見積り（`HBR-003` / AC4）

`HBR_CLASSIFICATION_MODEL.json` の `migration` 各案について、採用した場合に
落ちると見積もる既存テストを挙げる。**テストは 1 つも変更していない。**
これは見積りであって修正ではない。

この文書がここにあるのは、レビュアーの指摘による。見積りを task ファイルの
`REPORT` にだけ書いていたため、**レビューできる差分の外**にあり、
`UNVERIFIED` として扱われていた。受入条件が証拠を差分の外に置かせていたのは
票の設計の誤りで、成果物として `material/` に置くのが正しい。

### 移行で落ちる既存テストの見積り`** という見出しを作り、
   `migration` の各案ごとに**表**で書くこと。

   | 案 (`id`) | 落ちると見積もるテスト（ファイル:case） | 根拠 |
   |---|---|---|

   - `HBR_CLASSIFICATION_MODEL.json` の各案の `breaks` と**行が対応**していること。
   - 「落ちるテストは無い」が結論なら、**そう書いて根拠を示す**
     （どう調べたか。grep なら条件を書く）。空欄は未達と同じ。
   - **テストは 1 つも変更しないこと。** これは見積りであって修正ではない。
2. **Medium を直す。** `paths.export.gate_location` が JSON（`service.py`）と
   設計（`registry.py` のリポジトリ層）で食い違っている。どちらが正しいかを決めて
   **両方を揃え**、決めた理由を 1 行書くこと。実装がこの JSON を読んで
   間違った層にゲートを置くと、境界が置かれていないのと同じになる。

受入条件は 1 つも変えていない。`review_cycles` を 2 → 1 に戻した。
**次に AC4 が無ければ、猶予は与えない。**

## ORCHESTRATOR — 試行を 1 回**延長**した（戻したのではない） (2026-11-22)

上の裁定で「残り 1 周」と書いたが、このジョブは `attempts 3/3` に達している。
`review` のままでは `stranded()` が `attempts < 3` を要求するため拾われず、
**裁定を書いただけで永久に止まる**状態だった（私の見落ち）。

そこで `attempts` を 2 にした。**これは復元ではなく延長である。**
3 回の試行はいずれも供給側の障害などではなく、中身の不足で消費されている。
延長する理由は 1 つだけ:

成果物（分類の契約 JSON と設計 5 節）は出来ており、欠けているのは AC4 の**見積り表 1 つ**と、`gate_location` の食い違い 1 か所。ただし AC4 は前回も指示した項目で、**2 度目の不履行**である。だから延長は 1 回だけで、やることを表の形まで指定した。

**延長はこれで終わり。** 次の 1 回で受入条件を満たさなければ、
このジョブは分割するか取り下げる。受入条件は 1 つも緩めていない。

## RESUMED GATES (2026-11-22T03:51:42+09:00)

- `scope`: green
- `task-verification`: green
- `python-lint`: green
- `python-format`: green
- `secret-scan`: green

## REVIEW by opencode/iceman-free (2026-11-22T03:52:41+09:00)

VERDICT
- CHANGES_REQUIRED

FINDINGS
- Medium, `progress/phase-8-runner/material/HBR_CLASSIFICATION_MODEL.json:36-39` / `progress/phase-8-runner/material/HBR_CLASSIFICATION_DESIGN.md:117` / `progress/phase-8-runner/material/T-PH8-303.md:117`: `paths.export.gate_location` is inconsistent across the delivered artifacts. The JSON contract sets `export.gate_location` to `backend/app/service.py`, while both design/material docs place export at `runner_artifacts 持ち出し前（レポジトリ層）` in `backend/app/agents/registry.py` (§5 table). Concrete failure: an implementation or downstream consumer treating `HBR_CLASSIFICATION_MODEL.json` as the machine-readable contract would wire the export classification gate at the wrong layer/boundary, creating a boundary mismatch for runner-artifact export handling. Smallest fix: decide the intended export enforcement boundary and make `export.gate_location` identical in `HBR_CLASSIFICATION_MODEL.json`, `HBR_CLASSIFICATION_DESIGN.md`, and `T-PH8-303.md`, with a one-line rationale in the REPORT.
- Medium, reviewed in-scope artifacts `progress/phase-8-runner/material/HBR_CLASSIFICATION_DESIGN.md`, `progress/phase-8-runner/material/HBR_CLASSIFICATION_MODEL.json`, `progress/phase-8-runner/material/T-PH8-303.md`, `tests/test_hbr_classification_contract.py`; AC4 / orchestrator ruling (2026-11-22): the required §4 existing-test impact estimate is not evidenced in the reviewed change. AC4 requires `REPORT` to include an estimate of which existing tests would fall for the §4 migration problem, and the 2026-11-22 orchestrator ruling explicitly requires a `## REPORT` heading `### 移行で落ちる既存テストの見積り` with a per-migration-plan table (`id`, 落ちると見積もるテスト, 根拠) corresponding to each `migration[].breaks` entry. The reviewed artifacts contain migration break descriptions, but no per-plan existing-test estimate/table and no investigation basis. Concrete failure: acceptance cannot be confirmed because reviewers/owners cannot identify the expected existing test blast radius per migration plan from the delivered evidence. Smallest fix: add the required `### 移行で落ちる既存テストの見積り` table to the task `## REPORT` (and/or an in-scope material artifact if that is the delivery target), mapping each `migration-plan-1`/`migration-plan-2` row to affected existing tests or explicitly "none found" with grep/search basis; do not modify existing tests.

UNVERIFIED
- Exact gate hook points in current runtime code. I confirmed the referenced files exist (`backend/app/service.py`, `backend/app/agents/registry.py`) and symbols named by the design exist (`send`, `_document`, `_can_read`, `_citations` in `service.py`; `chat_jobs` usage in `service.py`; `runner_artifacts` schema in `registry.py`), but I did not verify that each `gate_location` is the correct pre-assembly/pre-dispatch/persistence enforcement point in live behavior.
- End-to-end inherit-max enforcement. `tests/test_hbr_classification_contract.py` validates the JSON contract, `gate_location` file existence, inherits DAG acyclicity, and synthetic `_max_classification` cases (`confidential`+`public`→`confidential`, any `none`→deny, additional max cases), but there is no runtime/backend implementation in scope to prove enforcement across the 8 production paths.
- Task-level `REPORT` content outside the reviewed diff/allowed paths was inspected only for context; I did not treat it as accepted evidence satisfying AC4 because the required estimate table/heading is not present in the reviewed deliverable set.

## OWNER DECISION REQUESTED (2026-11-22T03:52:41+09:00)

review cycle limit reached: The reviewer still requires changes at the cycle limit.

## ORCHESTRATOR RULING — AC4 が 4 周目。調査はオーケストレータが行う (2026-11-22 04:30)

AC4（各移行案で落ちる既存テストの見積り）が**4 周目の不履行**。
前のシフトで見出しの名前と表の列まで指定したが、それでも出ていない。
前回「次に AC4 が無ければ猶予は与えない」と書いた。**猶予は与えない。**

ただし取り下げない。理由は、AC4 が**モデルに向いていない作業**だと分かったこと。
「どの既存テストが落ちるか」は、既存のテスト群を読んで影響範囲を推定する調査で、
成果物を書く作業とは種類が違う。4 周同じところで落ちているのは、
**私が渡し方を間違えている**という証拠でもある。

**この調査はオーケストレータが行う**（オーナー許可 2026-11-17）。
`migration` の各案について既存テストへの影響を自分で調べ、表として報告に書く。
**レビューは別の無料モデルが行う。**

併せて `paths.export.gate_location` の食い違い（JSON が `service.py`、
設計が `registry.py` のリポジトリ層）も私が決めて揃える。

受入条件は 1 つも変えていない。渡す相手を変えただけである。

## ORCHESTRATOR HOLDS THIS JOB (2026-11-22 04:30)

`blocked` にしてあるのは**オーナー待ちではなく、オーケストレータが実装/調査を
引き受けたため**にループへ出さないようにしているだけである。
`OWNER_DECISIONS.md` の該当エントリには回答済みなので、`diagnose` は
これを停止として数えない。作業が終わったら `review` に戻し、
**別の無料モデルがレビューする**。

## ATTEMPT — AC4 investigation by claude-opus-5 (orchestrator) (2026-11-22T06:40:00+09:00)

前のシフトの裁定どおり、AC4 が 4 周続いたのでオーケストレータが調査した。
**レビューは別の無料モデルが行う。**

REPORT

- `progress/phase-8-runner/material/HBR_CLASSIFICATION_MODEL.json`:
  `paths[export].gate_location` を `backend/app/service.py` →
  **`backend/app/agents/registry.py`** に直し、`gate_location_reason` を添えた。
  **根拠（実測）**: `runner_artifacts` テーブルは `registry.py:171` にしか存在せず、
  `service.py` には artifact を扱うコードが 1 行も無い
  （`Select-String -Path backend/app/*.py,backend/app/agents/*.py -Pattern artifact`
  の一致は `registry.py:171` のみ）。
  `service.py` に置くゲートは**データを見ない場所に置くゲート**で、
  置いていないのと同じになる。設計文書 §5 の「リポジトリ層」が正しい。

### 移行で落ちる既存テストの見積り

調べ方: `tests/*.py` を 2 段で絞った。(1) 回答・引用・取得の経路に触るもの
（`/api/chat` `/api/ask` `retrieve` `.chunks(` `_citations` `citation` のいずれかに一致）、
(2) そのうち**文書を先に作るもの**（`seed_synthetic` / `/api/documents` / `upload` に一致）。
(1) かつ (2) のファイルが、分類の既定値 `none` を持つ文書で回答経路を叩くことになる。
件数は各ファイルの `^def test_` の数。

| 案 (`id`) | 落ちると見積もるテスト（ファイル:件数） | 根拠 |
|---|---|---|
| `migration-plan-1`（移行期間の明示的 `unclassified`） | `test_ingestion_inventory.py`:15、`test_document_formats.py`:5、`test_api.py` のうち文書一覧・取り込み状況を表明するもの（21 件中の一部） | この案は移行期間中 `none`/`unclassified` を**通す**ので、回答経路は落ちない。落ちるのは**行の形**を表明しているもの — 分類列の追加で `documents` の形と `inventory` の払い出しが変わる。`breaks` の「DB マイグレーションにより分類列を追加」「検索フィルタとスコープ判定コードの更新」に対応。 |
| `migration-plan-2`（パス別の線引き。`answer`/`citation`/`export`/`runner_artifact` で `none` を拒否） | `test_api.py`:21、`test_local_model.py`:17、`test_chat_queue.py`:13、`test_delegations.py`:13、`test_concurrent_roles.py`:10、`test_security.py`:9、`test_chat_drain.py`:7、`test_retrieval_acl_paths.py`:7、`test_admin_project_storage_load.py`:6、`test_administration_audit.py`:5、`test_role_updates.py`:4、`test_custom_role_publication.py`:2、`test_audit_regressions.py`:2 = **合計 116 件 / 13 ファイル**。加えて `frontend/e2e/` のチャット画面を動かす spec（`appearance.spec.ts` の `askSomething` を通る検査、`workspace.spec.ts`） | 13 ファイルはいずれも**文書を作ってから回答・引用経路を叩く**。合成フィクスチャ（`tests/e2e_server.py` の `seed_synthetic` と各テストの upload）は分類を渡さないので、既定の `none` になる。`none` を回答経路で拒否すると、これら全部が 403/422 を受ける。`breaks` の「`answer`、`citation`、`export`、`runner_artifact` 経路で `none` を持つ文書に対する処理がすべて停止する」に対応。 |

**この見積りが示していること**: `migration-plan-2` の影響範囲は
`migration-plan-1` の約 5 倍で、しかも**フィクスチャ側を直さない限り**
既存の 116 件が一斉に落ちる。どちらを選ぶかはオーナーの判断（`selected` は `null` のまま）だが、
案 2 を選ぶなら**合成フィクスチャが分類を渡すようにする作業**が
移行計画の一部として必要になる。これは `breaks` に書かれていない項目なので、
見積りの副産物として記録しておく。
