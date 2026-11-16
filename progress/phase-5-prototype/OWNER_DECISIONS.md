# Owner decisions requested by the job loop

Each entry is a judgement the controller refused to make itself.

## T-PH5-103 — integration branch is dirty (2026-11-15T17:17:52+09:00)

**Question**: The main checkout has uncommitted changes, so the reviewed commit was not merged. Decide how to integrate it.

**Context**

commit=c05f7cac99de29a5da92bc45f6335fb332a2168f
M progress/phase-5-prototype/tasks/T-PH5-103.md

**Answer** (2026-11-15, orchestrator): 範囲は広げず、コントローラ側の欠陥として直した。コントローラは自分の進捗記録だけを先にコミットし、他人の未コミット変更がある場合はマージせず停止する（`commit_progress_records`）。本ジョブはその後マージ済み。
## T-PH5-101 — out-of-scope change (2026-11-15T20:49:08+09:00)

**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job.

**Context**

outside allowed_paths: ['REPORT.md']

**Answer** (2026-11-15, orchestrator): 許可パスを広げない。`REPORT.md` は成果物ではなくワーカーの報告であり、返答本文に書くもの。ブリーフに「allowed_paths の外にファイルを作らない（やったことを書いただけのファイルも含む）」を明記して再発を止めた。
## T-PH5-101 — review cycle limit reached (2026-11-15T21:02:51+09:00)

**Question**: The reviewer still requires changes at the cycle limit.

**Context**

, "content_length": int}`) or unpack/validate at the boundary.
- Low — backend/app/service.py and tests/test_ingestion_inventory.py — `accepted` overpromises for cases the candidate shape cannot express: size 0 (or a whitespace-only body) is reported `accepted`, yet `upload` rejects it with 422 (`not content.strip()`, service.py:2227). Inherent to the spec's name+bytes-only input, so not a defect introduced here, but the API contract should document that `accepted` means "passes all checkable rules", not "upload will succeed". Smallest fix: one doc sentence on the endpoint/method; no behavior change.
- Low — backend/app/service.py:1140-1141 — the comment "apply checks in the same order as ``upload``" remains inaccurate (upload validates payload before `require` at :2217-2235; inventory authorizes first). No runtime impact. Smallest fix: correct the comment.

UNVERIFIED
- Controller gates (35 passed, ruff check/format, secret-scan, scope) were not re-run by me, per instructions; my assessment is static against the provided diff and the worktree files. AC5 (no regression in tests/test_api.py) rests on the controller's recorded `task-verification` result.
- The intended semantics of the spec's "インベントリ自体を拒否する" (detail 4 / AC3) vs per-candidate `not_permitted` cannot be resolved from the task file; flagged for the controller/owner, not decided here.
- The delegation lazy-invalidation write path was verified by code reading only; reachability in a live call requires seeded expired/corrupt grants, which I did not exercise (no mutation, no test execution).
- Pydantic v2 behavior of `Field(max_length=200)` on a `list` field and `strict=True` int handling of JSON booleans for `size` were not executed; presumed as the controller recorded, not material to the findings.
- Worktree byte-identity and the allowed-paths guarantee rest on the controller's scope gate and the read-only `git diff --stat`/`status` I ran (no state-changing git commands, no files created/modified/deleted).

**Answer** (2026-11-15, orchestrator): レビュー上限で `blocked` になったため、受入条件を一切緩めずに実装を引き継いだ。実体のある指摘 2 件（共有定数が `upload` 側で共有されていない／read-only の主張が `require` 経由で破れる）を解消し、drift を検出する回帰テストを追加した。コミット `c2cd24a`、マージ `eb6dd38`。
## T-PH5-101 — review cycle limit reached (2026-11-15T21:11:38+09:00)

**Question**: The reviewer still requires changes at the cycle limit.

**Context**

new tests asserting 200+`not_permitted` behavior would need corresponding adjustment to align with the spec's deny-by-default requirement.)

3. **LOW — `main.py:93` `InventoryCandidate` inherits `BaseModel` instead of `Input`**: `InventoryCandidate` is defined as `class InventoryCandidate(BaseModel)` but should be `class InventoryCandidate(Input)` to inherit the `model_config = ConfigDict(extra="forbid")` from `Input`. This means unknown fields (e.g., a `"content"` field) are silently dropped at the API level rather than rejected with 422, which contradicts task detail 5: "入力検証は既存の `Input` モデルに合わせ".

4. **MEDIUM — `service.py:56-58` module-level constants defined but not used by `upload`**: `MAX_NAME_LENGTH`, `MAX_CONTENT_BYTES`, and `ACCEPTED_EXTENSIONS` are defined at module level and used by the `inventory` method, but `upload` (service.py:2217-2257) still hard-codes the literals `160`, `262144`, and `{".txt", ".md", ".csv"}`. This violates task detail 3 ("判定規則を二重実装しないこと（共通化するか、同じ定数・同じ関数を参照する)") — any future change to upload's security limits (e.g., DATA-007 format extensions) would silently leave inventory reporting stale verdicts, creating the exact dual-maintenance failure the task prohibits. The smallest fix: make `upload` reference the module-level constants (and `IN_FLIGHT_LIMIT`/`OWNER_IN_FLIGHT_LIMIT`/`DOCUMENT_LIMIT`/`OWNER_DOCUMENT_LIMIT`) instead of its own literals.

**Answer** (2026-11-15, orchestrator): この回のレビューは**過去の指摘の復唱**だった。3 件すべてを現物と突き合わせ、`service.py:1153` `service.py:1114` `main.py:100` がそれぞれ指摘を否定していることを確認したうえで無効とした（裁定表は`tasks/T-PH5-101.md` に記録）。原因はレビュー用 diff に新規ファイルが含まれていなかったことで、`git add --intent-to-add --all` を先に行う方式へ修正済み。
## UNVERIFIED

- The actual implemented code cannot be re-executed per the read-only review constraint; the controller's prior verification (37 passed, all checks green) is accepted at face value, but the above findings represent static code-analysis issues visible in the diff against the acceptance criteria.
- Whether the `try/except HTTPException` around `require` was intentionally added to handle the spec's ambiguity between "inventory self-rejected (403)" vs "per-candidate `not_permitted` (200)" cannot be resolved from the diff alone; this is flagged for owner/controller arbitration.
