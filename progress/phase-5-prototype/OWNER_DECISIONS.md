# Owner decisions requested by the job loop

Each entry is a judgement the controller refused to make itself.

## T-PH5-103 — integration branch is dirty (2026-11-15T17:17:52+09:00)

**Question**: The main checkout has uncommitted changes, so the reviewed commit was not merged. Decide how to integrate it.

**Context**

commit=c05f7cac99de29a5da92bc45f6335fb332a2168f
M progress/phase-5-prototype/tasks/T-PH5-103.md

## T-PH5-101 — out-of-scope change (2026-11-15T20:49:08+09:00)

**Question**: The worker needed paths outside allowed_paths; widen the scope or split the job.

**Context**

outside allowed_paths: ['REPORT.md']

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
