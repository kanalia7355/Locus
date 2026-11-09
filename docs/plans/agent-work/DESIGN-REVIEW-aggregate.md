# DESIGN-REVIEW-aggregate — Independent review of the 5 approved-scope design packages

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Read-only
audit: modify ONLY this task file (append under ## Progress). Never push to
`main` or `loop/local-development`; no subagents of your own. NEVER touch the shared
`.venv`; use `.loop/runtime/qa-venv` if needed.

## Task

Perform an independent read-only review of the 5 approved-scope design packages that
were integrated into `loop/local-development` after the owner's Q1–Q7 decisions. The
packages are:

1. `docs/plans/HYBRID_STEP2_RECEIPT_CONTRACT.md` (R-2B-1, 633 lines) — receipt/envelope
   contract against ADR-0012 §4.1/ADR-0013/step-2
2. `docs/plans/HYBRID_ISOLATION_PROFILES.md` (R-ISO-1, 133 lines) — per-environment
   isolation profile matrix
3. `backend/app/service.py` + `frontend/src/AdminSettings.tsx` + tests (R-STORAGE-1,
   +146 lines) — manual-upload research flow improvements
4. `docs/plans/HYBRID_ISOLATION_ENGINEERING_DETAIL.md` (R-ISO-2, 238 lines) — isolation
   engineering detail
5. `docs/plans/HYBRID_ENGINEERING_DETAIL_INVENTORY.md` (R-ENG-1, 409 lines) — cross-cutting
   ENGINEERING_DETAIL inventory

**Audit for:**
- **Internal consistency**: no contradictions between the 5 packages (e.g., receipt
  contract vs isolation profiles vs engineering detail inventory)
- **Owner decision compliance**: each package respects Q1–Q7 boundaries
- **Safety boundaries maintained**: ADR-0011 zero-tool gate, ADR-0012 dual-plane
  separation, B6 dispatch rejection, no-egress, fail-closed semantics intact
- **No activation claims**: no package claims dispatch/isolation/credentials/egress/
  production activation — all maintain the design/recommendation layer
- **Unresolved items tracked**: all 【要決定】 markers are honest and not silently
  resolved; the owner's §4 unresolved list is not contradicted
- **Traceability**: each package cites its source requirements and classification record
  accurately
- **Code review (R-STORAGE-1 only)**: check the backend/frontend changes for correctness,
  security, ACL preservation, fail-closed behavior, and test coverage adequacy

**Verdict format**: consistent / findings (severity HIGH/MEDIUM/LOW, location, evidence,
recommended minimal fix — recommendations only, do not apply them).

**Completion gate:** a source-linked review report appended to this file under
## Progress with per-package verdicts and an aggregate verdict. Conventional Commit
(`docs(agent-work): ...`); push origin loop/design-review-aggregate; wait for branch CI
green; append progress + SHA + CI evidence.

## Process

Read AGENTS.md + docs/governance/DEVELOPMENT_POLICY.md, then the owner decisions
(docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md), then each of the 5 packages in full,
then the classification record (OWNER_QUEUE_CLASSIFICATION_2026-11-09.md) and the
resumable-jobs plan (RESUMABLE_JOBS_2026-11-09.md) for grounding. Self-review
adversarially. Conventional Commit; push origin loop/design-review-aggregate; repeat the
fix cycle until all applicable checks pass. Append progress + SHA + CI evidence.

Conventional Commit subject suggestion: `docs(agent-work): review the 5-package design aggregate`

## Progress

### 2026-11-10 — independent aggregate review

Reviewed the four design documents in full, the R-STORAGE-1 source diff at `56f85e0`, relevant service/scanner/API/UI code and tests, the owner classification record, the resumable-jobs plan, PRODUCT_SPEC, FINAL_ACCEPTANCE_CRITERIA, ADR-0012 and draft ADR-0013. The reviewed code is the same as `loop/local-development` at this review head (`dc79ac3`); no product files were changed. Tests/CI were not run for this read-only audit.

#### Package verdicts

1. **R-2B-1 — `HYBRID_STEP2_RECEIPT_CONTRACT.md`: consistent.** Its Tier 0 requirements preserve ADR-0012 §4.1, B6, E1/E2 independent live checks, fail-closed behavior, Plane-M zero-tool and no-egress (`§§1.1, 4–6`). Q1/Q2/Q4 policy boundaries and owner §4 open items are separated (`§§1.2–1.4, 9`); the proposed receipt does not claim approval or activation (`§10`). Classification references are consistent with the cited DP rows. The known placeholder-table/ADR-0013 “no receipt table” and mutability tensions are disclosed, not concealed (`§8.1`); source inspection confirmed the metadata placeholder and explicit dispatch rejection in `backend/app/agents/registry.py`.

2. **R-ISO-1 — `HYBRID_ISOLATION_PROFILES.md`: consistent.** It applies Q3 without a universal-VM mandate, keeps all four profiles inactive/unverified, and bars host fallback (`§§1–4`). The deny-all network boundary, no credentials/data/activation, and evidence limitations are explicit (`§§1, 5–8`). It appropriately leaves exact profile/risk acceptance, Runner trust, reachability, and credential supply gated; its traceability to Q3, ADR-0011/0012, the classification record and related step designs is plausible and internally aligned.

3. **R-STORAGE-1 — `backend/app/service.py`, `frontend/src/AdminSettings.tsx`, tests: findings.** ACL behavior and ingestion fail-closed behavior are preserved: authorization is rechecked before and after scanning (`service.py::_ingestion_allowed`, `process_next`), non-approved scans quarantine, and quarantined documents cannot expose chunks (`chunks`). The new status remains behind the existing system-admin check (`storage_status`); no connector/egress or ACL changes were found. The tests cover default-unavailable quarantine and a configured accepting scanner, but miss the configured-yet-unavailable scanner case described below.

   - **MEDIUM — scanner failure is still reported as a failed verdict, not an unavailable check.** Location: `backend/app/service.py:103–106, 2098–2108`; `backend/app/scanner.py:21–22, 51–52, 57–63`; `frontend/src/AdminSettings.tsx:552–556`; coverage in `tests/test_api.py:164–175, 183–209`. Evidence: `scanner_configured` only tests that the adapter is not `UnavailableScanner`; `ClamAVScanner` construction performs no connectivity check, and `scan()` returns `False` for lock contention, timeout/connection errors and other exceptions as well as a non-clean scan. `process_next()` also converts any scanner exception to `approved=False`. Thus a configured but unreachable/erroring scanner is labelled “安全検査を通過していない” and the admin UI says safety inspection is “有効”, indistinguishable from an actual rejection. This remains fail-closed (no unsafe ingestion observed), but the change does not fully deliver its stated distinction between a rejected scan and a check that could not run, and may mislead administrators. **Minimal recommendation:** preserve quarantine for every non-clean result, but represent clean / rejected / unavailable-or-error separately (or use a typed scanner result); report adapter configuration separately from operational/scan outcome. Add tests for configured scanner timeout/exception and explicit rejection, asserting both remain quarantined with truthful status/reason.

4. **R-ISO-2 — `HYBRID_ISOLATION_ENGINEERING_DETAIL.md`: consistent.** Scope rows DP-033, DP-042, DP-044–049, DP-051, DP-052 and DP-053a agree with the classification record (`§1`). Its staged-transfer, live-authority, binding, cancellation and evidence details remain conditional designs; the document repeatedly withholds endpoints, credentials and activation (`§§1.1, 2, 4, 6`). Profile evidence and skips are not overclaimed, and no unresolved owner decision is presented as settled.

5. **R-ENG-1 — `HYBRID_ENGINEERING_DETAIL_INVENTORY.md`: consistent.** The 14 receipt + 11 isolation + 0 storage ENGINEERING_DETAIL rows (25 total) match the classification table; DP-053b is correctly excluded as EXISTING_DECISION (`§1`). Coverage references match the named R-2B-1/R-ISO-2 sections (`§2`); TTL and trust/key/permission decisions remain gated (`§§3–4`), and the empty manual-upload engineering-detail group does not invent connector scope (`§5`). Candidate options are labelled unadopted and the non-weakening/non-activation limits are explicit (`§§3, 6`).

#### Aggregate verdict: findings

No HIGH finding. One MEDIUM R-STORAGE-1 reporting/coverage finding above; it does not identify an ACL bypass, fail-open ingestion, or hybrid activation. The four design packages are consistent with each other and with the reviewed Q1–Q7/ADR/classification constraints: B6 dispatch rejection, ADR-0011 zero-tool, ADR-0012 plane separation, default-deny/no-egress, and fail-closed behavior remain intact. All unresolved owner §4 choices remain visibly unresolved; no package claims dispatch, profile, credential, egress, real-data or production activation. Traceability checks found no material classification mismatch. Recommendation only; no fix applied.

- Review report commit: `37cc2aa33a24a0f13ea9a2eac28bece59fa8ec47`; pushed to `origin/loop/design-review-aggregate`.
- Exact-head branch CI for that commit: Prototype quality run [42681341941](https://github.com/kanalia7355/Locus/actions/runs/42681341941) — success. CI emitted only runner/action deprecation and image-migration annotations; no check failure.
