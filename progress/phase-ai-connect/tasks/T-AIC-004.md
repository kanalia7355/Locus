---
id: T-AIC-004
phase: phase-ai-connect
status: review
assignee: opencode
model: opencode/iceman-free
weight: medium
updated: 2026-11-22T17:01:21+09:00
attempts: 0
allowed_paths: progress/phase-ai-connect/material/
test_cmd: python -m pytest tests/test_agents_registry.py -q
reviewer: opencode/beam-free
---

# Task `T-AIC-004`: CLIエージェント・アダプタの設計ゲート（設計のみ）

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `HBR`（必須要件 1・4・5・7、実装順序 3〜5）
- **オーナー決定が出たので `todo` にした（2026-11-22）**:
  4 つの決定事項すべてに回答があった。下の「オーナー決定（2026-11-22）」が正本で、
  草案の「owner 決定事項」節は**回答済みとして書き換えてある**。
  `dispatch` の 409 を外すのは依然として別の決定であり、本票では外さない。
- **Background**:
  - ツール実行を伴うエージェント（Claude Code / Codex / Gemini CLI 等）の接続は、
    チャット用 API 接続（T-AIC-001〜003）とは別レイヤーの問題である。
  - 現状の遮断は意図的なもの:
    - `backend/app/agents/registry.py` は metadata-only を明記し、dispatch・
      adapter 有効化・認証情報処理・egress を行わない。
    - `POST /api/workspaces/{id}/agent-dispatch-attempts` は常に
      409 `Runner boundary is unproven; dispatch is disabled` を返す。
    - `docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md` §12 は activation を未承認としている。
  - 参考実装（opencode）:
    - `packages/core/src/plugin/provider/claude-agent/` —
      Claude Agent SDK を LanguageModel としてラップし、ツールは MCP 経由で橋渡しする。
    - `packages/cli/src/acp/agent.ts` — エージェント自身が ACP（Agent Client Protocol）
      のサーバとして振る舞い、`session/new` / `session/prompt` 等の JSON-RPC を受ける。
    - つまり「エージェント接続」は (a) 公式CLIを headless で起動する、
      (b) Agent SDK をライブラリとして埋め込む、(c) ACP / opencode のような
      既製エージェントを外部プロセスとして呼ぶ、の3経路がありうる。
- **Implementation Details**（設計文書の更新のみ。コードは書かない）:
  1. 決定 (b) Agent SDK 埋め込みについて、**埋め込み先 2 案**
     （Desktop Runner / サーバ）の比較を
     `progress/phase-ai-connect/material/HBR_AGENT_SDK_EMBEDDING.md` に書く。
     （`docs/plans/` は保護パスでジョブから書けないため、成果物はここに置く。
     読む対象としての `docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md` は従来どおり。
     確定後にオーナーが設計正本へ反映する。）
     対象は **Claude Code のみ**（決定 2）。書く項目:
     - 実行隔離（作業ディレクトリ、ファイルアクセス、ネットワーク）の強制方法
     - 認証情報の置き場（同文書 §4.2 Option 1 = CLIネイティブログイン・端末側保持
       を既定とし、サーバへ値を送る経路は設けない）
     - 分類ポリシーと egress 判定を dispatch のどの段階で通すか
     - 監査に残す項目（利用者、workspace、adapter、モデル、判定結果。本文は残さない）
     - 失敗・中断時の後始末（プロセス終了、途中成果物の扱い）
  2. Runner 境界の「証明」に必要な検証項目を、同文書 §9 の検証計画に
     具体的な合否条件つきで列挙する（mock／stub 認証のみで実施可能な範囲に限る）。
  3. dispatch の 409 を外す条件を「activation gate」として明文化し、
     本タスクの成果物は **次フェーズの実装タスク起票に必要な決定材料**とする。
- **オーナー決定（2026-11-22）** — これが設計の前提である:
  1. **接続経路は (b) Agent SDK 埋め込み。**
  2. **対応順は Claude Code → Codex → opencode。** 最初は Claude Code だけを設計する。
     3 つを同時に設計しない（1 つ目で分かることが 2 つ目の形を変える）。
  3. **「CLI かどうかはどうでもよい」。** 求められているのは
     **チャット画面で、接続した利用者がモデル管理の部分で選べること**。
     実行形態はその UX を満たす限り自由。
  4. **隔離の実証はやりやすい方で良い。**
- **オーナー回答から導かれる設計上の判断（設計文書に書くこと）**:
  - **「埋め込み」をどこに埋め込むかは、まだ決まっていない。** 決定 3 が
    「CLI かどうかはどうでもよい」なので、**Desktop Runner に埋め込む案**が
    既定の推奨になる。理由: 利用者の Claude ログインを**サーバが預からずに済み**、
    `HYBRID_AGENT_ADAPTER_DESIGN.md` §4.2 Option 1 と
    `credential_schema_is_presence_only` の不変条件を**壊さずに**
    求められた UX（モデル管理から選ぶ）を満たせる。
    サーバ埋め込みを採る場合は、サーバが利用者の資格情報を持つことになるので
    `T-AIC-006` の (B) の判断が先に必要になる。**両方の案を比較表で書くこと。**
  - **隔離は「やりやすい方」の既定を先例に合わせる。**
    `docs/architecture/DOCUMENT_EXTRACTION_BOUNDARY.md` §5 で実測済みのとおり、
    この機には `resource` モジュールが無く docker エンジンも動いていない。
    そこで採った結論は「**子プロセス系統では、ネットワーク遮断とメモリ上限を
    記録に主張しない**」である。エージェント隔離も**同じ前例に倣い**、
    主張できる保証と主張できない保証を表に分けて書くこと。
    **新しい隔離の物語を 2 本目として作らない。**
- **Acceptance Criteria**:
  1. **埋め込み先 2 案（Desktop Runner / サーバ）の比較と推奨**が、既存境界
     （ゼロツール境界、presence-only、分類ポリシー、監査）との適合表つきで
     `material/HBR_AGENT_SDK_EMBEDDING.md` に書かれている。対象は Claude Code のみ。
  2. **隔離で主張できる保証と主張できない保証が表に分かれている。**
     `DOCUMENT_EXTRACTION_BOUNDARY.md` §5 の先例と**同じ語彙**を使うこと。
     「弱い方の保証しか主張しない」を破っていないこと。
  3. Runner 境界の検証項目に**合否条件**が付いている
     （mock・合成データのみで実施できる範囲に限る）。
  4. **コード・スキーマ・dispatch の挙動を一切変更していない。**
     `tests/test_agents_registry.py` が PASS することで示す
     （dispatch の 409 と presence-only の回帰ガードが生きていること）。
  5. 変更が許可パス内に収まっている（`material/` のみ）。
- **Reviewer Model (実装モデルとは別モデルを指定)**: `<未割当>`

---

## REPORT

- **Implemented by**: `<assignee> (<model>)`
- **Attempt**: `0 / 3`
- **Changed Files**:
  - （未記入）
- **Summary**:
  - （未記入）

---

## TEST

- **Executed Commands**:
  - なし（設計タスク）
- **Result**:
  - （未記入）
- **Unmapped Changes (Phase 節目で確認が必要な変更ファイル)**:
  - なし

---

## REVIEW

### Review Cycle 1
- **Reviewer**: `<assignee> (<model>)`
- **Date**: `<ISO8601>`
- **Verdict**: `PENDING` (`APPROVED` | `CHANGES_REQUESTED` | `BLOCKED`)
- **Findings**:
  - （未実施）

## ATTEMPT 1 — implementation by opencode/iceman-free (2026-11-22T17:01:21+09:00)

## REPORT
- `progress/phase-ai-connect/material/HBR_AGENT_SDK_EMBEDDING.md`（新規）: T-AIC-004 の設計ゲート資料を作成。オーナー決定 2026-11-22 #1-#4 を前提に、Claude Code Agent SDK 埋め込み先の 2 案（Desktop Runner / サーバ）を比較し、既存境界（ゼロツール境界 / presence-only / 分類ポリシー / 監査）との適合表を記載。Desktop Runner 案を既定の推奨とし、サーバ案は `T-AIC-006 (B)` 未決のため非推奨/条件付きとした。実行隔離・Option 1 資格情報（CLI ネイティブログイン・端末側保持、サーバへ値を送る経路なし）・dispatch 段階の分類/egress 独立判定（D0-D6, E1/E2/B6）・監査項目（利用者/workspace/adapter/model/判定結果、本文なし）・失敗/中断時の後始末を明記。`DOCUMENT_EXTRACTION_BOUNDARY.md` §5 と同じ語彙の保証表（○/△/×、実時間上限・出力バイト数上限・環境変数の遮断・書込み先の限定・CPU時間/メモリ上限・ネットワーク遮断、`network: unverified`、ADR-0006 loopback 実測）で「主張できる保証/主張できない保証」を分離。mock/synthetic のみの Runner 境界検証項目（VT-C1..C5, NV-C1..C10）に合否条件を付与。dispatch 409 を外す activation gate（G0-G8）を定義し、本書が解除を承認しないことを明記。
- 変更なし（確認のみ）: `backend/app/agents/registry.py`, `tests/test_agents_registry.py`, schema/API/dispatch 挙動は未変更。`git status --short --branch` は `?? progress/phase-ai-connect/material/HBR_AGENT_SDK_EMBEDDING.md` のみ。

ドキュメントとコード/現状の不整合（調査で確認）:
- `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` は "DRAFT DESIGN PROPOSAL" 表記、一方 `docs/architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md` は "ACCEPTED"。境界内容は整合しているが、文書ステータス表現が揺れている。本設計は ADR-0012 accepted を上位境界として参照し、step2 は設計入力として扱った。
- `backend/app/agents/registry.py` 冒頭は "never dispatches..." と説明するが、`dispatch_attempt` は B6 の明示的 409 拒否を実装している。拒否ゲートとして意図的であり、`tests/test_agents_registry.py` もこの挙動を固定している（不整合というより命名/説明の読み違い余地）。
- `HYBRID_AGENT_ADAPTER_DESIGN.md` §6.2 は Claude Code Windows native を Option 1 direct としている。本タスクのオーナー決定 #3 により、Desktop Runner 埋め込み案を既定推奨として具体化した。これは Option 1（端末側保持）と矛盾せず、埋め込み先の選好を補う位置づけ。
- `progress/phase-ai-connect/material/` ディレクトリは作業前に存在しなかった（glob で該当ファイルなし）。許可パス内に新規作成した。

残リスク:
- `python scripts/secret_scan.py` が既存ファイルで失敗した（下記 TEST）。`progress/phase-6-extensions/OWNER_DECISIONS.md` と `progress/phase-6-extensions/tasks/T-PH6-104.md` の既存指摘であり、本変更・許可パス外のため未修正。コントローラの全ゲート通過には別途対処が必要。
- 本書は設計ゲートのみ。G1-G8（ADR-0013 receipt、境界証跡、credential boundary、classification/egress、T-T4 監査保護、cleanup 検証、Owner 承認）が未充足のため dispatch 409 は維持されるべき。
- 子プロセス系統の隔離は DOCUMENT_EXTRACTION_BOUNDARY §5 と同様、ネットワーク遮断・メモリ上限を主張できない。Desktop Runner 実装時にこの語彙/記録ルールを崩さないこと。

## TEST
- `python -m pytest tests/test_agents_registry.py -q`（作業後、CWD=worktree root）
  - 結果: PASS
  - 出力: `............                                                             [100%]` / `12 passed in 7.73s`
- `python -m ruff check backend tests scripts jobloop`
  - 結果: PASS
  - 出力: `All checks passed!`
- `python -m ruff format --check backend tests scripts jobloop`
  - 結果: PASS
  - 出力: `186 files already formatted`
- `python scripts/secret_scan.py`
  - 結果: FAIL（既存・許可パス外の指摘）
  - 出力: `Potential secret: progress\phase-6-extensions\OWNER_DECISIONS.md, lines [2081]` / `Potential secret: progress\phase-6-extensions\tasks\T-PH6-104.md, lines [1012]` / `Offline secret scan: 2 findings` / Exit code: 1
  - 補足: `git status --short --branch` で自分の変更は `?? progress/phase-ai-connect/material/HBR_AGENT_SDK_EMBEDDING.md` のみ。上記 2 件は本タスクで変更していない。
- `git status --short --branch`
  - 結果: `## loop/T-AIC-004-t-aic-004` / `?? progress/phase-ai-connect/material/HBR_AGENT_SDK_EMBEDDING.md`

## STATUS
ready-for-review

### Controller gates

- `scope`: green
- `task-verification`: green
- `secret-scan`: green

## REVIEW by opencode/beam-free (2026-11-22T17:03:34+09:00)

VERDICT
- APPROVED

FINDINGS
- Low, progress/phase-ai-connect/material/HBR_AGENT_SDK_EMBEDDING.md:39 — citation `HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md §1.1-B3` points to the wrong section; the B-rules (including B3 zero-tool/adapter separation) live in §1.2 of that document, not §1.1 ("Two planes, two module trees"). Smallest fix: change to `§1.2 B3`.
- Low, progress/phase-ai-connect/material/HBR_AGENT_SDK_EMBEDDING.md:41 — citation `HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md §3.1-E5/E6` points to the wrong section; E5/E6 (independent destination/egress gate and classification gate) are defined in §3.2 (Enforcement points), while §3.1 is "Policy fields". Smallest fix: change to `§3.2-E5/E6`.

UNVERIFIED
- I did not re-run `tests/test_agents_registry.py` or the secret scan; the controller's recorded gates (exit 0, 12 passed; secret scan 0 findings) are the authoritative evidence and I relied on them. I also did not verify the (absent) trailing newline is acceptable — no acceptance criterion requires it. No code, schema, or dispatch behavior was changed by this job, consistent with the single-file diff and the passing registry tests.
