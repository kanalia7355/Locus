# PH2-RV-phase2-review

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Use the isolated
QA venv `.loop/runtime/qa-venv` (recreate if missing: Python313 venv +
`pip install -e ".[dev]" -r backend/requirements.lock`); NEVER touch the shared
`.venv` (broken). Never push to `main` or `loop/local-development`; no subagents.

Full process: read `AGENTS.md` + governance docs first; create your worktree with
`git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/<SLUG> -b loop/<SLUG> origin/loop/local-development`;
implement; self-review adversarially; run the full QA cycle until ALL green
(full pytest tests -q --ignore=tests/e2e, ruff check + format --check, mypy
backend/app, secret scan; plus frontend lint/test/build/playwright when UI
touched); Conventional Commit; push; wait branch CI; fix/re-push until green
(bounded); append progress + SHA + CI evidence here. Branch deleted after
integration.

---

# PH2-RV — Independent review of the Phase-2 aggregate (RE-DISPATCH after 429)

Read the ORIGINAL brief in `docs/plans/agent-work/PH2-RV-phase2-review.md` (main
checkout or worktree) — the review criteria are unchanged. The first dispatch
died with the provider 429 before producing findings.

Review target: the Phase-2 aggregate at `loop/local-development` HEAD (98fda8d
or later): PH2-B concurrent roles + deny (`10ee9c4`), PH2-E combined-roles UI
(`9738ca2`), PH2-D delegation (`3150f6b`), PH2-C storage-ACL research
(`0e06107`), PH2-CA completion audit docs. Verify the binding owner conditions
(`docs/plans/PHASE2_DELEGATION_SPEC.md` section 8 resolution banner,
`OWNER_DECISION_REGISTER.md` RESOLVED 2026-11-09) against the REAL authorization
code paths (document read/retrieve, chat dispatch, attachments) — not just test
existence. Hunt for privilege escalation, expired/revoked grants still
authorizing, grantor-authority-loss gaps, audit misses, delegation-X-roles-deny
interactions. Spot-check >=10 code paths and the recorded QA counts. Verdict:
accept / accept after minor fixes / needs major rework, with severity,
location, evidence, fix recommendations appended to THIS file's Progress
section. You are a REVIEWER: modify only docs/plans/agent-work/PH2-RV-phase2-review.md
(append under ## Progress), no commits/pushes/worktrees/subagents.

## Progress

### Independent aggregate review — 2026-11-09

**Verdict: accept after minor fixes.** No critical/high authorization defect was
identified in the reviewed prototype paths. The Phase-2 aggregate is suitable
for main integration only after the full-suite verification discrepancy below
is resolved by a clean run in the supported QA/CI environment; do not treat this
review as evidence that my local full suite passed.

**Review baseline and method.** Reviewed `loop/local-development` at HEAD
`6deef1458b83e16cc40c3d555e5de8ae2742f117` (later than requested
`98fda8d`). The application changes at `10ee9c4` (roles/deny), `9738ca2` (UI),
`3150f6b` (delegation), and `0e06107` (research) are present; comparison against
`951c3cf` found no later changes to the authorization source or the relevant
role/delegation tests. Read the binding §8 decision banner and
`OWNER_DECISION_REGISTER.md` resolution, PH2-B/D/E task evidence, PH2-CA audit,
Phase status/reconciliation, implementation and regressions. Spot-checked the
following real code paths (more than the requested ten):

1. `Service._delegation_authority` / `_permission_ceiling_for_grantor`:
   checks enabled grantor, project membership/current roles, project owner or
   project-scoped `organization_admin` plus effective `manage_roles`, current
   allowed requested permissions, and the `NON_ADMIN`/per-held-role ceiling.
   Grant authority itself cannot be supplied by a delegated permission.
2. `create_delegation`: authenticates the live session inside the serialized
   DB transaction; rejects self-grant/unknown or administrative permissions and
   invalid `retrieve` without `read`; enforces TTL 900–604800 seconds (default
   86400); scopes to one project; audits mutation in-transaction.
3. Grant-family/version handling: authorization selects only the maximum current
   version and excludes any version with lifecycle events. Revoked versions are
   retained; renewal creates a new version and an ended prior version, while
   scope/permission expansion creates a new family rather than widening one.
4. `_delegated_permissions`: checks recipient account enabled, obtains current
   time on checks, denies at `now >= expires`, filters ended/superseded grants,
   and re-evaluates grantor authority. Invalid clock/data fails closed.
5. `_permissions`: combines current role allows and grants, subtracts all
   project-scoped explicit denies, and removes `retrieve` unless `read` remains.
   `_role_access` requires actual membership before grant contribution is
   evaluated, so delegation does not create project membership.
6. Project listing and role/member administration use live permission
   calculation/`require`; role holding grants are bounded by the administrator's
   non-admin ceiling (and by the intersection of each held role for non-admins).
   Role/denial changes are transactionally audited.
7. `_can_read` and `_document` gate direct document metadata/body retrieval on
   current operation permission plus ownership or matching publication-role and
   operation grant. Attachments require owner and the exact conversation ID;
   publication cannot grant attachments.
8. `documents`, `chunks`, and `related` recheck current read/retrieve authority;
   related results independently filter every candidate document by both read
   and retrieve. Not-ready data is not returned as chunks.
9. `upload` and `_ingestion_allowed` check current upload permission and, for
   attachments, the owner's conversation/retrieve gate. `process_next` checks
   before invoking the scanner and again before publishing indexed chunks, so
   queued work does not preserve the grant.
10. `_conversation`, conversation listing, and conversation history preserve
    conversation ownership and live retrieve permission. History filters
    attachment rows and citations against current access.
11. `_citations` filters each source live; `_generated` hides the entire answer
    if any recorded citation is no longer retrievable, preventing partial stale
    disclosure.
12. `send` validates supplied attachment ownership/status, filters retrieval,
    reauthenticates/rechecks citations and attachments before model dispatch,
    then rechecks after model return before storing the answer. A failed recheck
    prevents result persistence.
13. `enqueue_chat` checks owner conversation and attachments at submission;
    worker execution returns through `authenticate` and `send`, which re-resolves
    current grants instead of using the queued job as authority.
14. `revoke_delegation`/`cancel_delegation` authenticate the current session,
    limit the actor to the grantor/recipient respectively, append an event and
    audit idempotently; subsequent permission checks filter that grant.

Role/deny regressions and delegation regressions include the allow-union/deny-
wins interaction, project scope, membership independence, expiry at the exact
boundary, grantor role-loss invalidation, self-escalation, family renewal,
recipient cancellation, attachment/document expiry, and an in-flight model
recheck. Targeted tests run in this review: `pytest tests/test_delegations.py
tests/test_concurrent_roles.py tests/test_admin_project_storage_load.py
tests/test_api.py -q` — **35 passed**. Ruff check and scoped format check passed
(128 files); `mypy backend/app` passed (9 files); offline secret scan reported
0 findings. Frontend lint passed; Vitest **64 passed** (14 files); frontend
production build passed. Playwright was not rerun in this review; PH2-E's
recorded branch evidence is 12 Chromium tests.

**QA finding — low severity, integration gate (environment-specific).** The
recorded PH2-CA evidence reports `1156 passed / 18 skipped` (1174 collected)
on its stated audit baseline and records green hosted workflows at `a473bf6`
and `5dceb62`. I attempted the full command at this review checkout using the
isolated `.loop/runtime/qa-venv`: `pytest tests -q --ignore=tests/e2e`. Result:
**1156 passed, 9 skipped, 9 failed** (1174 collected). All nine failures are
Windows native-CLI conformance tests in `test_loop_c_min_native.py`,
`test_notification_native.py`, and `test_trial_input_native_v2.py`; their
shared failure is `StopIteration` because the locally installed
`models_cache.json` has no `gpt-6.1-sol` entry. This is an environment/fixture
mismatch, not a Phase-2 code failure, but it means the recorded full-suite
pass was not reproduced in this local environment. Recommendation: rerun the
required full suite on the supported pinned-tool fixture or exact CI matrix,
and preserve its result before integration. Do not skip/alter these tests to
force green. The docs' recorded counts/CI correspond to prior identified SHAs,
not this review HEAD; no new CI result for `6deef14` was independently queried.

No other finding warrants a code fix from this read-only review. The known
limitations are accurately stated in PH2-CA: delegation UI is not implemented,
org-wide delegation is deferred, and source-storage ACL implementation is
planning-only. Recommendation: record the successful supported-environment
re-run, then proceed with the existing integration gate; keep those scoped
follow-ups explicit.
