# HYB-DECISION-PACKAGE — consolidated owner decision queue

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Use the isolated
QA venv `.loop/runtime/qa-venv` if you need to run anything (recreate if missing:
Python313 venv + `pip install -e ".[dev]" -r backend/requirements.lock`); NEVER touch
the shared `.venv` (broken). Never push to `main` or `loop/local-development`; no
subagents of your own. Docs-only task: do NOT modify code, specs or tests.

Full process: read `AGENTS.md` + governance docs first; implement; self-review
adversarially; run at least the fast verification subset that applies to docs-only
changes (ruff check + format --check, secret scan); Conventional Commit
(`docs(plans): ...`); push your dedicated branch; wait branch CI; fix/re-push until
green or recorded blocked; append progress + SHA + CI evidence here. Branch deleted
after integration.

---

## Task

The pipeline is blocked on owner decisions scattered across three documents. Produce
ONE consolidated decision queue so the owner can decide everything in a single pass
and unblock hybrid implementation step 2b/3 and the storage-ACL slices.

Sources (all pending 【要決定】 items, plus explicitly-open owner items):
1. `docs/architecture/decisions/0013-job-approval-authorization-receipt.md` (23 items)
2. `docs/plans/HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md` (30 items)
3. `docs/plans/PHASE2_STORAGE_ACL_IMPLEMENTATION_PLAN.md` (11 items)
4. Cross-check `docs/plans/OWNER_DECISION_REGISTER.md`, `PHASE_STATUS.md` and
   `MASTER_IMPLEMENTATION_ROADMAP.md` for any further open items (e.g. org-level
   surface decisions) and include them.

Deliverable: a NEW file `docs/plans/OWNER_DECISION_QUEUE_2026-11-09.md` containing:
- A numbered decision table: ID (e.g. DP-001), source document + section link,
  one-line question, options where the source defines them, the source's
  recommendation (if any), what each decision unblocks (2b/3 slice, storage-ACL
  slice number), and a blank "OWNER DECISION" column to fill in.
- Group decisions by pipeline impact: (a) blocks hybrid step 2b, (b) blocks step 3,
  (c) blocks storage-ACL implementation, (d) housekeeping.
- Do NOT weaken, rewrite or answer any source item. Copy the semantics verbatim or
  link precisely; this is an index/queue, not a re-decision. Do NOT mark anything
  decided; every item stays 【要決定】 until the owner decides.
- Mark clearly which items are safety-boundary (approval authority, egress,
  isolation activation, credentials) — those cannot proceed without explicit owner
  approval per the standing rules.

QA: docs-only — ruff/format/secret-scan subset + link-integrity spot check
(every table row's source reference resolves to a real section).

Conventional Commit subject suggestion: `docs(plans): consolidate pending owner decision queue`
