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
