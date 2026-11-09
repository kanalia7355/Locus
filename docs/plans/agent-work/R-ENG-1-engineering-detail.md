# R-ENG-1 — Bounded engineering-detail work across DP-001…072

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Docs-only task:
do NOT modify code, specs, tests, or the OWNER_DECISION_QUEUE. Never push to
`main` or `loop/local-development`; no subagents of your own. NEVER touch the shared
`.venv`; use `.loop/runtime/qa-venv` if needed.

## Task

Produce bounded engineering-detail design work for the DP rows explicitly classified
as `ENGINEERING_DETAIL` in `docs/plans/OWNER_QUEUE_CLASSIFICATION_2026-11-09.md`,
across the receipt, profile, and manual-upload groups. The owner's formal decisions
Q1–Q7 are recorded in `docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md`.

**Classified ENGINEERING_DETAIL rows relevant to design work (from the classification
record):** DP-001, DP-002, DP-003, DP-007, DP-008, DP-009, DP-012, DP-013, DP-014,
DP-016, DP-017, DP-019, DP-020, DP-023, DP-033, DP-042, DP-044, DP-045, DP-046,
DP-047, DP-048, DP-049, DP-051, DP-052, and DP-053a. DP-053b is separately
EXISTING_DECISION.

**Scope rules:**
- Start only rows whose dependencies and safety boundary permit work now.
- Package by the receipt, profile, or manual-upload groups (R-2B-1, R-ISO-1, R-STORAGE-1
  already cover the main design work; this task handles the remaining engineering details
  that don't overlap those deliverables).
- DP-046 numerical bounds inherit unresolved receipt TTL choices and CANNOT set them.
- DP-044/045/049 are contract-detail design only and require independent review.
- DP-053a evidence binding is design-only and does not activate a profile.
- Record technical options, evidence and consequences rather than introducing a new
  approval surface.
- Do NOT duplicate or override queue classifications.
- Do NOT re-open settled Q1–Q7; do NOT resolve owner §4 questions by inference.

**Safety boundary that must not change:** no weakening of ADR-0011/0012, B6, no-egress,
least privilege, current ACL, metadata-only audit or fail-closed behavior. Design
evidence never activates dispatch, isolation, credentials, egress, real data or production.

**Output:** Create `docs/plans/HYBRID_ENGINEERING_DETAIL_INVENTORY.md` (the design
package). This is documentation/design only, not product code.

**Completion gate:** each covered row is explicitly classified `ENGINEERING_DETAIL`;
its source and approved boundary are cited; required tests/review pass; any emerging
policy/scope choice is split out and returned as 【要決定】. Delivery/integration
requires exact-head gates and authorized branch workflow.

## Process

Read AGENTS.md + docs/governance/DEVELOPMENT_POLICY.md, then the owner decisions
(docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md), then the classification record
(docs/plans/OWNER_QUEUE_CLASSIFICATION_2026-11-09.md) to identify exactly which rows
are ENGINEERING_DETAIL, then the receipt contract
(docs/plans/HYBRID_STEP2_RECEIPT_CONTRACT.md), the isolation profiles
(docs/plans/HYBRID_ISOLATION_PROFILES.md), and the isolation engineering detail
(docs/plans/HYBRID_ISOLATION_ENGINEERING_DETAIL.md) to identify which engineering
details are already covered vs still needed. Self-review adversarially; run the
docs-applicable verification subset (ruff check + ruff format --check +
scripts/secret_scan.py via the qa-venv if needed). Conventional Commit
(`docs(plans): ...`); push origin loop/reng1-engineering-detail; repeat the fix cycle
until all applicable checks pass. Append progress + SHA + CI evidence to this file
under ## Progress at each step end and at task end, and push.

Conventional Commit subject suggestion: `docs(plans): author the engineering detail inventory`

## Progress

- 2026-11-09 (JST evening) — Step 1: Read AGENTS.md, DEVELOPMENT_POLICY.md, owner
  decisions Q1–Q7 (OWNER_DECISIONS_2026-11-09-EVENING.md), the classification record
  (OWNER_QUEUE_CLASSIFICATION_2026-11-09.md) and the three existing engineering
  deliverables (receipt contract R-2B-1, isolation profiles R-ISO-1, isolation
  engineering detail R-ISO-2). Confirmed the exact 25 ENGINEERING_DETAIL rows
  (14 receipt-group + 11 profile-group + 0 manual-upload-group; DP-053b excluded as
  EXISTING_DECISION) and identified which are already covered vs residual.
- 2026-11-09 — Step 2: Authored `docs/plans/HYBRID_ENGINEERING_DETAIL_INVENTORY.md`:
  coverage map for all 25 rows (citing, not duplicating, the classification record and
  the covering packages); residual receipt-group engineering detail (A-1 serialization/
  replay, A-2 issuer-key custody, A-3 metadata-only schema + immutable events, A-4
  reason enum, A-5 audit event names, A-6 expiry shape/clock with TTL numbers kept
  【要決定】 per DP-010/011 and inherited by DP-046, A-7 invalidation triggers) recorded
  as candidate options with evidence and consequences, nothing adopted; Group B fully
  covered by R-ISO-2 with the task's boundary conditions restated as travel-with-row
  constraints (DP-046 bounds inherit DP-010/011 and cannot be set; DP-044/045/049
  contract-detail design only; DP-053a evidence binding design-only, no activation);
  Group C recorded as containing no ENGINEERING_DETAIL row. Adversarial self-review
  (§7) and source-anchor verification (§8: registry.py 161/734, service.py
  1046–1075/1077, tests/test_agents_registry.py 293/339) performed. No code, spec,
  test or queue cell modified; nothing activated.
- 2026-11-09 — Step 3: Local verification via isolated `.loop/runtime/qa-venv`
  (recreated fresh with Python 3.13; shared `.venv` untouched):
  `ruff check .` PASS; `scripts/secret_scan.py` PASS (0 findings); `ruff format
  --check` — my file PASS; one pre-existing failure at HEAD unrelated to this task
  (`docs/requirements/AUTONOMOUS_LOOP_SPEC.md` would be reformatted; a spec file this
  docs-only task must not modify — recorded honestly, not "fixed" by weakening scope).
- 2026-11-09 — Step 4: Commit `44f769f9502c393bced96450ac4215f0e049f94e`
  (`docs(plans): author the hybrid engineering detail inventory`) pushed to
  `origin/loop/reng1-engineering-detail`.
- 2026-11-09 — Step 5 (task end): CI evidence on 44f769f:
  - Loop engine checks (run 42668253774) — **PASS** (ubuntu/windows × 3.11/3.13).
  - PR title convention (run 42668254164) — **PASS** (conventional-title).
  - Prototype quality (run 42668253831) — first attempt FAILED on a 120s timeout of
    `tests-quality-remaining` (docs-only change; unrelated); rerun of the failed job
    **PASS** in 3m48s. No test, workflow or gate was altered.
  All applicable checks pass. Task complete; no owner §4 item resolved; no quota
  error encountered.
