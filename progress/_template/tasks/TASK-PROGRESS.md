---
id: T-001
phase: phase-<slug>
status: doing
assignee: agy
model: Gemini 4 Argon
weight: medium
updated: 2026-11-12T13:00:00+09:00
attempts: 1
---

# Task `T-001`: <タスクタイトル>

## TASK DEFINITION (Assigned by Orchestrator)

- **Requirement IDs**: `<PROD-XXX / IAM-XXX / DATA-XXX / UI-XXX / HBR-XXX / LOOP-XXX>`
- **Worktree / Branch**: `<worktree-path>` (`<subbranch-name>`, base: `phase/<slug>`)
- **Allowed Paths**:
  - `<path/to/allowed/file_or_dir>`
- **Acceptance Criteria**:
  1. <受入条件 1>
  2. <受入条件 2>
- **Reviewer Model (実装モデルとは別モデルを指定)**: `<未割当 または モデル表示名/slug>`

---

## REPORT

<!-- 担当実装ワーカー (Implementer) のみが記入する。
     変更したファイル一覧、実装内容の要約、受入条件との対応、
     およびレビュー差し戻し時は各指摘への対応内容を記録すること。 -->

- **Implemented by**: `<assignee> (<model>)`
- **Attempt**: `1 / 3`
- **Changed Files**:
  - `<path/to/file>`
- **Summary**:
  - （未記入）

---

## TEST

<!-- 担当実装ワーカー (Implementer) のみが記入する。
     .pi/skills/test-scope/SKILL.md に従い、変更に関連するテストのみを実行し、
     実際に実行したコマンドと結果 (PASS / FAIL / SKIP) を正確に記録すること。
     実行していないテストを PASS と記載してはならない。 -->

- **Executed Commands**:
  - `python -m pytest tests/test_<stem>.py -x -q`
- **Result**:
  - （未記入）
- **Unmapped Changes (Phase 節目で確認が必要な変更ファイル)**:
  - なし

---

## REVIEW

<!-- 実装ワーカーとは別モデルのレビューワーカー (Reviewer) のみが記入する。
     最大 2 周 (Cycle 1 / Cycle 2) まで。
     承認時は frontmatter の status を qa へ、差し戻し時は doing (上限到達時は blocked) へ更新すること。 -->

### Review Cycle 1
- **Reviewer**: `<assignee> (<model>)`
- **Date**: `<ISO8601>`
- **Verdict**: `PENDING` (`APPROVED` | `CHANGES_REQUESTED` | `BLOCKED`)
- **Findings**:
  - （未実施）
