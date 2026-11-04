# C-min derived initial message ID: offline implementation evidence

2026-11-04, Asia/Tokyo. Offline scope only; no live execution permission.

## Approved inputs and scope

Before source changes, the final design SHA-256 was computed and presented to the owner:
`05ebaeb6cdbd3b082356f987a8f017dd4921059b6f29640f8dbaef64912e5f10`
for `docs/plans/C_MIN_DERIVED_INSTRUCTION_ID_ADDENDUM.md`. The approved bytes are unchanged and pinned to LF in Git.
The separately approved v2 metadata addition remains bound to SHA-256
`6f84090f99d0cd5fc6d921ea935d05b8c45a36049184a3832ef38429820bf605`.

The explicit v3 contract permits one new generated slot only: `body.input[0].id`.
It recomputes `msg_` plus UUIDv5(UUIDv5(NAMESPACE_OID, canonical current thread UUID), exact approved base instruction text).
UUIDv5 format alone never authorizes an ID. Exact developer role, content, provenance,
text hash, model, destination and execution permissions remain enforced.
V1 and v2 do not accept this new slot. Trial authorization additionally requires the
permit version to equal the normalized contract version and its full fingerprint.
Existing zero-tool checks, unchanged upstream header allowlist, original body hash,
atomic durable generated-ID claims and no-replay trial reservations remain in place.
No new executor, orchestration framework or product feature was introduced.

## Independent security review

A separate read-only reviewer examined the implementation. Initial review found one
blocking version-binding gap: a permit could name a different supported version than
its hashed contract. The implementer fixed this and added all six unequal v1/v2/v3
version pairs as rejection tests. Fix/re-review cycle 1 returned no findings and no
remaining blocking issue. The reviewer independently ran pure validator tests
(40 passed, 7 deselected); it did not access credentials, provider connections,
services, durable production state or modify source. No second fix cycle was needed.

## Verification

Related verification: 131 passed, including native mock conformance and abnormal
input, stale/reused values, incorrect derivation, schema/permission changes,
version mismatch, tool response, lost response and changed source tests.
The real pinned CLI uses only synthetic homes and loopback mock endpoints:
one fixture-capture launch is followed by two different validating launches using
one frozen contract. Both validating launches passed; their process identities
and request hashes differ. No real authentication or model inference occurred.
The existing failing native test was repaired rather than skipped.

Full engine QA (`scripts/verify_loop.py --audit`) passed: 818 passed, 7 skipped
in 469.82 seconds. Skips are six opt-in Docker containment cases and one synthetic
symlink case unavailable to this Windows account. Lint, format, native and Linux
3.11 type checks, PowerShell cold/warm checks, secret scan, dependency consistency
and dependency advisory audit passed. The project itself is not published on PyPI
and is excluded by the dependency auditor. Related and full totals overlap.

The QA image was rebuilt through the existing trusted build/audit path because its
previous audit expired. Current immutable image:
`sha256:41f2d777ef27d669f841ac4e34911ca8c2fa82249152c23c1c5891f305ebcb1f`,
build timestamp 1793750400, source hash
`5bf1c4012fc9f5ffcc666eac55c19f423688bb815d817adc9e6ffc7b8bd2f8cd`.
Freshness and dependency manifest equality were checked before source-only,
network-disabled product QA. Product QA (`scripts/verify.py --e2e`) exited 0
in 104.613 seconds: Python 784 passed / 63 platform-or-opt-in skips, frontend
11 passed, Chromium E2E 5 passed; lint, type checks and build passed. Two
non-failing SQLite ResourceWarnings were reported by Python 3.13. The source-only
image audit passed; exact-commit GitHub CI is checked after Push.
The first product QA wrapper failed to persist its result due to an incorrect
ProcessResult attribute name; it is not counted as success and was rerun with
the corrected evidence wrapper, without changing product tests or timeouts.

## Remaining single-live-trial blockers

1. Reconcile both historical isolated audit trial records and their outcomes using
   bounded, nonsecret read-only evidence. Ordinary access is denied; missing evidence
   cannot grant new trial budget. Preserve prior attempts, uncertainty and consumed budget.
2. Register and validate the actual normal auth profile using metadata only: canonical
   path, owner, ACL, attributes and no reparse points. The existing-file exception does
   not guarantee encryption at rest. This change did not read, copy or modify auth.json.
3. Resolve explicit permission for official CLI authentication lifecycle/startup behavior
   with that existing-file profile. No auth refresh, migration or configuration changes
   were attempted here.
4. Freeze the actual finite synthetic trial template, current source/CLI/model/destination,
   workspace, profile metadata, history, remaining budget and purpose-specific expiring
   one-send permit. Obtain separate owner permission for one normal ChatGPT connection.
   Unknown outcomes must remain non-retryable.
5. Preserve the old failed v2 runtime receipt. Offline v3 conformance is not a successful
   live v3 receipt; a single-purpose trial receipt cannot authorize normal Development Loop.
   Worker/Reviewer/GoalEvaluator need their own exact workspace and execution bindings
   before a separately authorized 30-minute Loop trial. The conservative Git/LFS startup
   guard also remains a normal-Loop blocker, without a bypass or blanket exception.

No real auth/model calls, audit service operations, main changes, PR creation,
automatic merge or unattended Loop were performed. Only the authorized development
branch may receive the verified commit.

## Historical documentation discrepancy

The frozen approved addendum still says "NOT approved or implemented" and describes
the earlier failing two-launch test. Those are historical design-stage statements.
Owner approval and the implementation/tests above supersede that status; changing
those bytes would invalidate the approved hash. The historical test filename
`test_trial_input_native_v2.py` is retained, but its explicit contract is now v3.
