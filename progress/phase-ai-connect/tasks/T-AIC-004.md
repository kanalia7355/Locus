---
id: T-AIC-004
phase: phase-ai-connect
status: todo
assignee: unassigned
model: unassigned
weight: medium
updated: 2026-11-22T13:56:00+09:00
attempts: 0
allowed_paths: progress/phase-ai-connect/material/
test_cmd: python -m pytest tests/test_agents_registry.py -q
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
