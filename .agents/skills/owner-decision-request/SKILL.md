---
name: owner-decision-request
description: Format and dispatch owner decision requests as a single consolidated checklist with checkboxes, source links, and grouped entries — never piecemeal, never re-asking approved items.
---

When the pipeline is blocked on decisions the owner must make, format the request as follows and commit it to the repository before surfacing it.

## When to use

- One or more items are classified `OWNER_DECISION_REQUIRED` in the queue classification record.
- Design or implementation work is gated on a decision the owner must record.
- The owner has not yet decided on items that were previously listed as 【要決定】.

## Format requirements

1.  **File naming**: `docs/plans/OWNER_CHECKLIST_YYYY-MM-DD.md`.
2.  **Structure**: one consolidated document with numbered entries — NOT piecemeal questions.
3.  **Per entry, always include:**
    - Target DP items (grouped; split multi-part items as DP-XXXa/DP-XXXb).
    - The question in one line.
    - Options (a)/(b)/(c)… stated by the source, cited as unapproved.
    - Recommended option with rationale.
    - 後回し可否 (can this be deferred? if so, until when?).
    - `☐ ______________________` checkbox for the OWNER DECISION.
4.  **Batch format**: include a "one-shot approval" example and an "individual approval" example so the owner can answer in a single sentence if desired.
5.  **Supplementary links**: link every source document referenced by the entries (proposal, classification, design packages, resumable jobs, deferred gates) with GitHub URLs.
6.  **Impact table**: include a table mapping each approved entry to the work it unblocks.
7.  **Safety boundary note**: always state that B6, ADR-0011/0012, no-egress and fail-closed boundaries are NOT changed by any decision — activation remains a separate gate.

## Hard rules

- **Never re-ask** items already resolved by owner decisions, ADRs or prior decisions.
- **Never invent** technical numbers, permissions, protocol names or activation claims not already in the source documents.
- **Group** related items into one entry (e.g. all trust/enrollment/key items into one cluster) — do not fragment into per-DP questions.
- **Cite** source documents for every recommendation; recommendations are NOT approval.
- **Commit** the checklist to the working branch and push; surface the GitHub link to the owner.
- **Separate** "must decide now" from "can be deferred" — mark the latter clearly.

## Example structure

```
# Owner確認・承認チェックリスト — YYYY-MM-DD

## 1. 残件一覧（OWNER_DECISION_REQUIRED — 全N件）

### Entry 1 — <topic>
- 対象: DP-XXX, DP-YYY
- 質問: <one line>
- 選択肢: (a) ... / (b) ... / (c) ...
- 推奨: <option> — <rationale>
- 後回し可否: <yes/no + condition>
- OWNER DECISION: ☐ ______________________

## 2. 一括承認の書き方

## 3. 補足資料リンク

## 4. 承認後のパイプライン（対応表）
```

## Reference implementation

See `docs/plans/OWNER_CHECKLIST_2026-11-11.md` for the format in practice.
