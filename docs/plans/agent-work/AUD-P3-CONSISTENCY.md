# AUD-P3-CONSISTENCY — post-integration documentation consistency audit

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Read-only
audit: modify ONLY this task file (append under ## Progress). Do not edit other docs,
code, specs or tests. Never push to `main` or `loop/local-development`; no subagents.

Full process: read `AGENTS.md` + governance docs first; audit; self-review
adversarially; append findings + verdict here; Conventional Commit
(`docs(agent-work): ...`); push your dedicated branch; wait branch CI; append
progress + SHA + CI evidence.

---

## Task

Independent read-only consistency audit of the documents produced and integrated
during the 2026-11-09 Phase-2 completion and hybrid-preparation batch:

1. `docs/architecture/decisions/0013-job-approval-authorization-receipt.md` (ADR-0013, DRAFT)
2. `docs/plans/HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md`
3. `docs/plans/PHASE2_STORAGE_ACL_IMPLEMENTATION_PLAN.md`
4. `docs/plans/PHASE2_DELEGATION_SPEC.md` (section 8 banner + binding conditions)
5. `docs/plans/PHASE_STATUS.md`, `docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md`,
   `docs/plans/OWNER_DECISION_REGISTER.md`, `docs/plans/STATUS_AND_DECISIONS_2026-11-09.md`

Audit for:
- **Traceability**: every claim in the new docs maps to a real requirement/ADR/
  owner decision; no invented authority; no decision presented as made that is
  still 【要決定】; decision counts consistent across documents.
- **No spec weakening**: nothing dilutes ADR-0012's approval gates, the zero-tool
  boundary, synthetic-data-only rule, no-egress condition, or existing tests.
- **Status accuracy**: PHASE_STATUS / roadmap rows vs. the actual integrated state
  (delegation UI done, org-level deferred, storage-ACL planning open, MFA required
  for final product, deployment gate deferred).
- **Internal contradictions** between ADR-0013 and the HYB-A2 proposals
  (e.g. receipt semantics vs. runner trust-root assumptions).

Verdict: consistent / findings (severity HIGH/MEDIUM/LOW, location, evidence,
recommended minimal fix — recommendations only, do not apply them).

Conventional Commit subject suggestion: `docs(agent-work): audit post-phase-2 documentation consistency`

## Progress

### 2026-11-09 — audit executed (read-only)

- Read `AGENTS.md` + `docs/governance/DEVELOPMENT_POLICY.md` + this brief. Audited the eight
  batch documents against the integrated state (worktree HEAD `bd883b9` lineage of
  `loop/local-development`; integrated delegation UI `c1c5f4c`→`a445b3f`→`84dc1eb`, phase-2
  main merge `c307939`/`1284f4f`/`6e970ee`, version 0.3.0 in pyproject/frontend/loop_engine).
- Every code-level claim in ADR-0013 and the storage-ACL plan was re-verified against source:
  `NON_ADMIN` (service.py:25), delegation tables/triggers (144–267), TTL 900–604800 default
  86400 (create_delegation), `dispatch_attempt` 409 "Runner boundary is unproven" (registry.py:734),
  `egress_mode` CHECK `local_only` / `destination_allowlist='[]'` / `classification_ceiling` default
  'none' / `deadline_seconds IS NULL` (registry.py:85–94), storage plan's schema/upload/two-check/
  `AdminStorage`/"未実装・無効（既定拒否）" citations all present. ADR-0012 §4.1 receipt quote,
  step-2 design §2.1/§2.6/§6.11 quotes, threat-model T-T1/T-S1/T-R1/T-E1 + follow-up 3, and the
  zero-tool test paths (`tests/unit/test_loop_tool_surface.py` etc.) all check out.
- **No spec weakening found.** ADR-0012 approval gates, the B6 gate (§9 of ADR-0013; §1.2/§5 of
  HYB-A2), the zero-tool boundary, synthetic-data-only and no-egress conditions are preserved in
  every reviewed doc; no existing test was weakened (the 409→422/403 replacement in
  `tests/test_api.py` is the replacement PHASE2_DELEGATION_SPEC §7 explicitly authorizes for an
  approved PH2-D; the 5/4-line ADR-0012 edit is the owner-approved meaning-preserving wording
  correction, register B-4).
- Verdict: **findings** — 1 HIGH, 4 MEDIUM, 3 LOW below. Recommendations only; nothing applied.

### Findings

**F1 — HIGH — `docs/plans/PHASE_STATUS.md`: duplicate, contradictory Phase-2 completion
records; delegation-UI status contradicts itself and the integrated state.**
- Location: line 9 (Phase-2 table row), line 12 (Phase-5 row), lines 50–96 (first "Phase 2
  completion declaration"), lines 301–337 (second declaration with the identical heading).
- Evidence: lines 9/12/81–82 say the delegation grant/revoke UI is **NOT implemented**
  ("backend APIs exist; tracked remaining Phase-2 web item"), while lines ~325–327 say
  "the delegation management UI is implemented". The code shows the UI **is** integrated
  (`frontend/src/Delegations.tsx` + `Delegations.test.tsx`; integrated 2026-11-09 09:52 via
  `84dc1eb`). Moreover the second declaration was written at `664b401` (2026-11-09 08:41)
  **before** the UI commits `c1c5f4c`/`a445b3f`/`84dc1eb` existed — a premature
  "implemented" claim at its own SHA. The two declarations also give different QA evidence for
  the same audit (line 68: "1156 passed / 18 skipped (1174 collected)" vs line 328: "1156
  passed/9 skipped"), and the first's "NEXT GATE: the aggregate independent review … before any
  main integration" (line 94) is superseded by the second (PH2-RV verdict recorded; main merge
  `c307939` completed). Neither section cites the UI integration SHAs.
- Recommended minimal fix (docs-only, owner-visible status file): mark the first declaration and
  the line-9/line-12 table cells as a dated superseded snapshot pointing to the current
  declaration; consolidate the UI status in one place and record the integration SHAs
  (`c1c5f4c`/`a445b3f`/`84dc1eb`); reconcile the 18-vs-9 skipped counts (or state the two
  environments) so the evidence is not self-contradictory.

**F2 — MEDIUM — `docs/plans/PHASE2_DELEGATION_SPEC.md`: header/grounding/observations are
stale and now factually false against the shipped code, contradicting its own §8 banner.**
- Location: line 3 ("Status: design draft … **not approved**"), lines 12–15 ("endpoint …
  currently always returns that 409. Keep the endpoint disabled (409) until the spec is
  approved and PH2-D is implemented"), lines 430–433 ("The code contains no delegation storage
  or active grant logic at all: it is only a disabled placeholder"), line 359 (retain the 409
  regression) vs line 366+ (§8 "RESOLVED … PH2-D implementation is AUTHORIZED").
- Evidence: PH2-D is implemented and verified (`delegation_families/grants/events` at
  service.py:144–190, `create_delegation` at 1331, live endpoints in `backend/app/main.py`
  returning 201), and the 409 placeholder test was replaced per §7. A reader following the
  header/grounding text would describe — or worse, restore — a disabled endpoint that no
  longer exists.
- Recommended minimal fix: add a dated status banner at the top (and a one-line note above the
  grounding and source-observation sections) recording that the owner resolution (register
  RESOLVED 2026-11-09 §A) superseded the draft status and that PH2-D was implemented at
  `3150f6b`; keep the historical text verbatim below the banner.

**F3 — MEDIUM — `docs/plans/OWNER_DECISION_REGISTER.md`: open-decision tables contradict the
RESOLVED section in the same file.**
- Location: line 24 ("All remain **open / awaiting owner**; there is no decision in this
  register to resolve any of them") and line 41 ("All entries are **open / awaiting owner**.
  PH2-D remains blocked.") vs line 64+ ("## RESOLVED 2026-11-09": AUD-1 findings 1–10 resolved,
  all 12 PH2-A items approved, PH2-D unblocked).
- Evidence: same-file contradiction; also AUD-1-07's "current fail-closed endpoint remains" is
  no longer true. Risk: decisions already given get re-requested (the resolution itself says
  "do not re-request decisions already given") or cited as open.
- Recommended minimal fix: add a dated supersede banner at the top of each open-decisions table
  pointing to the RESOLVED 2026-11-09 section; do not rewrite the historical rows.

**F4 — MEDIUM — `docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md`: not refreshed after the
2026-11-09 owner resolution it postdates.**
- Location: §1 rule 7 ("Delivery mode is unresolved …", "until a valid authorized mechanism is
  selected"), §4 Controller-track item 4 and §5 integration rules ("do not use the unapproved
  Main production proposal"), §4 product-track item 1 ("PH2-D remains blocked until all
  applicable decisions are answered"), PH-ROADMAP-2 row ("**In progress, not phase complete at
  the audited baseline**"), header ("Baseline: … HEAD `27c5a1d` (2026-11-09)").
- Evidence: the owner resolution recording commit `10d9fd0` (B-2: post-phase automatic main
  merge formally adopted; PH2-A items approved) precedes the roadmap's last edit `30491c8`
  (same day, 14:14), yet the roadmap still presents main delivery as unresolved and PH2-D as
  blocked; PH2-D was integrated at `3150f6b`, Phase 2 declared complete, and main integration
  completed (`c307939`, PR #8). Also the baseline hash `27c5a1d` was committed 2026-11-08
  09:32 JST, not 2026-11-09. Batch-wide date labels (2026-11-09) vs commit dates (2026-11-08)
  add evidence-tracing ambiguity.
- Recommended minimal fix: add a dated addendum/supersede note to rule 7, the P2-closeout gate
  and the PH-ROADMAP-2 row recording the B-2 adoption, the resolution, the PH2-D integration
  and completion (with SHAs), while keeping the baseline snapshot intact; correct or annotate
  the baseline date; cite commit SHAs with timestamps alongside date labels.

**F5 — MEDIUM — ADR-0013 (`docs/architecture/decisions/0013-…receipt.md`) §3: revocation
candidate (b) is internally inconsistent with the ADR's own mandatory property and in tension
with HYB-A2's online-revocation requirement.**
- Location: ADR-0013 §3 mandatory paragraph ("Any mechanism must make revocation take effect
  before the *next* enforcement point (a revocation between enqueue and execution must be
  visible to the Runner's recheck)") vs candidate (b) "Signed revocation lists / short-lived
  receipts — … revocation propagates via signed lists the runner caches"; HYB-A2
  (`docs/plans/HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md`) §3.2 Revocation ("Maintain
  authoritative online active/revoked status … check it at … immediately before execution …
  No offline grace period for job execution") and §4.2 ("Re-check … online").
- Evidence: a cached signed revocation list cannot make a revocation issued after the last
  refresh "visible to the Runner's recheck"; it only bounds staleness. If the owner selects
  (b) reading ADR-0013 alone, it collides with HYB-A2's and the step-2 design's online-check
  envelope requirement. (All other ADR-0013↔HYB-A2 intersections checked — E1/E2 independence,
  runner-instance binding, issuer/trust-key separation, "B6 not lifted", "signature ≠
  authorization" — are consistent.)
- Recommended minimal fix (recommendation only): in ADR-0013 §3, re-label (b) as unable to
  satisfy the mandatory visibility property except as a bounded-staleness fallback explicitly
  subordinate to it, and note the alignment requirement with HYB-A2 §3.2/§4.2 (or align the
  two candidate sets).

**F6 — LOW — HYB-A2 header authorization pointer is not resolvable against the register.**
- Location: HYB-A2 line 3: "Prepared for owner decision items 4/5 under the 2026-11-09 owner
  policy B-5/B-6/B-10".
- Evidence: register RESOLVED §B maps B-5 to production DB/search design comparisons and B-6
  to LAN-deployment verification plans — neither names isolation/trust-root; STATUS doc §2.3
  lists isolation technology as row 2 and Runner trust root as row 3 (not 4/5); only the task
  brief (`agent-work/HYB-A2-isolation-trust-proposals.md`) uses "items 4/5". The proposal's
  substance is authorized design work, but the citation cannot be verified from the batch
  documents alone.
- Recommended minimal fix: replace with explicit pointers (e.g., register RESOLVED §B items
  5/6/8/10 quoted, or the task brief path) so the authority for the proposal is traceable.

**F7 — LOW — ADR-0013 §Context citation error: "whose §2 open items 1–12".**
- Location: ADR-0013 lines 52–53, citing `docs/plans/PHASE2_DELEGATION_SPEC.md`.
- Evidence: the spec's open items are in its §8 (the status doc's are §2.2); the spec's §2 is
  "Expiry, renewal, and live rechecks". The referenced resolution exists; only the section
  pointer is wrong.
- Recommended minimal fix: correct to "§8 open items 1–12" (or "STATUS_AND_DECISIONS §2.2").

**F8 — LOW — QA/code-evidence drift inside "verified" sections.**
- Location/evidence: ADR-0013 "Current state of the code (verified)" cites `dispatch_attempt`
  "line ~716" (actual 734) and `create_role`/`update_role` "lines ~2696/2738" (actual
  2742/2784) without the "line numbers are indicative" disclaimer the storage plan carries;
  PHASE_STATUS line ~76 says "tests/test_delegations.py 10" (11 test functions at head).
- Recommended minimal fix: add the same indicative-line-number disclaimer to ADR-0013 or pin
  exact SHAs next to line-number citations; correct the test count (or state the counting
  method). No functional impact.

### Positive checks (recorded, no action)
- Decision counts consistent: 12 PH2-A items (3 with added conditions + 9 as-recommended)
  match across register §A, delegation-spec §8 banner, PHASE_STATUS declarations and STATUS
  §2.2; MFA status (required for final product, prototype deferral standing) consistent across
  register B-3, PHASE_STATUS, roadmap P6 and STATUS §2.3.
- No decision is presented as made while still 【要決定】 in ADR-0013 (23 markers), HYB-A2
  (30 markers) or the storage plan (11 markers); all three keep proposal-only status language.
- Status-accuracy items named in the brief verified against the integrated state: delegation
  UI done, org-level delegation deferred, storage-ACL planning open/要決定, MFA required for
  final product, deployment gate deferred — accurate in the newest PHASE_STATUS declaration;
  the contradictions are the staleness findings F1–F4 above.

### 2026-11-09 — self-review and commit

- Adversarial self-review: re-checked each finding's SHA/line evidence with git (commits
  `666abc1`, `664b401`, `c307939`, `10d9fd0`, `30491c8`, `3150f6b`, `84dc1eb`) and source
  reads; confirmed F1's premature-UI claim by `git cat-file -e 664b401:frontend/src/Delegations.tsx`
  (absent); confirmed no test weakening (`git diff 27c5a1d..HEAD -- tests/` = additions + the
  §7-authorized 409 replacement); confirmed findings do not overlap with slot A's decision
  package (that slot consolidates 【要決定】 items into a new file; this audit only reports).
  Peer message from slot A (HYB-DECISION-PACKAGE) acknowledged: file-disjoint
  (`OWNER_DECISION_QUEUE_2026-11-09.md` vs this task file); no coordination action required.
- Read-only audit respected: only this task file modified.

