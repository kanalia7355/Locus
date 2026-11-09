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

## Progress

- Reviewed required governance, assigned brief, source decision documents and cross-reference status records. Confirmed `.bootstrap/complete.json` exists and the working tree began clean on `loop/HYB-decision-package`; shared `.venv` was left untouched.
- Created `docs/plans/OWNER_DECISION_QUEUE_2026-11-09.md`, grouped by 2b, step 3, storage-ACL and housekeeping impact. It includes all 23 ADR-0013 questions, 30 Step-3 questions, all 12 numbered storage-plan §7 items (the task brief says 11; §7 has twelve), and 7 further open cross-document items. No source spec/code/test changed.
- QA: Ruff check passed with isolated Python 3.13 QA venv `.loop/runtime/qa-venv`; Ruff format check passed for 419 files with only the unrelated pre-existing `docs/requirements/AUTONOMOUS_LOOP_SPEC.md` excluded (the full check flags that untouched file at line 315); offline secret scan passed with 0 findings; markdown link/anchor audit passed (130 links, 0 invalid anchors); decision table audit passed (72 unique sequential IDs, 72 blank owner cells). No out-of-scope source file changed. The queue includes all source markers: ADR-0013 23, Step 3 30, storage plan 11.
- Adversarial self-review caught and corrected duplicate IDs, malformed/missing anchors, the count mismatch with the brief (storage plan has 11 markers but 12 numbered rows), and organization-surface wording. Final verification rerun: `.loop/runtime/qa-venv/Scripts/python.exe -m ruff check` PASS; `... -m ruff format --check --exclude 'docs/requirements/AUTONOMOUS_LOOP_SPEC.md'` PASS (419 files); `... scripts/secret_scan.py` PASS (0 findings); link audit PASS (130 links, 0 bad anchors); table audit PASS (72 unique sequential IDs, all 72 OWNER DECISION cells blank; source marker counts 23/30/11); `git diff --check` PASS. Full repository format check remains blocked by the existing unrelated formatting discrepancy at `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315`; it was not changed because scope is docs-only for the assigned files.
- Delivered queue commit: `04e5447c9f2e4d8795712b3d31d4aa6de1b283f6` (`docs(plans): consolidate pending owner decision queue`), pushed to `origin/loop/HYB-decision-package`; remote branch OID verified equal to this SHA. No PR was opened. Exact-SHA hosted CI all green: Prototype quality run `42552247545`, Loop engine checks run `42552247674` (four matrix jobs), PR title convention run `42552247648`. Checks correspond to the queue commit SHA.
- Final task-file/evidence update and its push remain pending.
