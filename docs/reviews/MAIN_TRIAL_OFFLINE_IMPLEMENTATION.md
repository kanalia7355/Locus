# Main delivery / C-min one-shot offline implementation

2026-11-03 Asia/Tokyo. Scope: disabled offline implementation; no live activation.

## Approval and retained authority

Before implementation both owner-approved document hashes matched:

- MAIN_FF_INTEGRATION_DESIGN.md: 34cdd903506410ed45d63d041517776f7a2b0134c08d2166d55c8ad57e5cfb8f
- C_MIN_SINGLE_CONNECTION_APPROVAL.md: eca090f9d22f4347e16ae371cba9106d6600906d0806b6a5eb9852e864a01af7

Those exact bytes are frozen with LF attributes. Their proposed/unimplemented
wording records the approval-time baseline; this report records subsequent work.
Owner approved offline work and additive Push commit CI only. Real authentication,
model inference, service operations, Loop startup, remote main mutation, protection
edits and production activation remain forbidden. No frozen Goal/config/task/run
budget was rewritten. Existing local_commit_push remains the configured mode.

## Implemented and intentionally unavailable

MainIntegration is an optional LocalDelivery post-Push dependency using StateStore,
GitManager source/tree binding and independent review records. Existing normal
delivery remains unchanged when absent. It enforces all six configured required
checks, exact SHA/workflow digest/publisher/latest attempt, whole-range review,
ancestry and immediately rechecked refs/CI. The journal separately stores main
intent, detailed CI evidence, reserved update, confirmed and recorded outcomes.
FULL SQLite durability and one unsettled promotion prevent duplicate mutations.
PolicyMigration excludes unresolved promotions. Cancellation permits only bounded
observation of an existing outcome; Controller does not complete/advance on stop.

The pure GraphQL payload pins main's beforeOid and source's before/after SHA with
force=false. Actual temporary bare tests exercise a paired Git ref transaction.
NO production GitHub promotion transport exists in this release; the optional
component rejects a backend not explicitly declared offline. No runtime config
selector or activation flag was added. This is an offline implementation, not an
already operational automatic-main feature. Hosted no-op-CAS/protection/permissions
and authenticated independent-review publication remain unverified contracts.

Conventional-title now additionally runs on non-main Push and validates actual
commit subjects/range, including HEAD equality and ancestry. Its original PR-title
check and all existing required job names/permissions remain. Nothing is marked
successful without validation; no required condition was removed.

The C-min command is now implemented:

    .venv\Scripts\python.exe -m loop_engine.cli c-min-trial --plan docs/plans/C_MIN_SINGLE_CONNECTION_APPROVAL.md --approval <exact-approved-trial-record-id>

It has NOT been run against the operator profile. A missing trial permit rejects
before inspecting operator configuration or launching CLI/auth. Use --status with
the same arguments for observational outcome status; it cannot retry a model.
The workspace is .loop/runtime/probes/c-min-single-validation, preserving existing
Docker allowed namespaces. Only the exact synthetic marker is allowed there.

The same C-min adapter/relay/journal checks a purpose-specific permit, approved
runtime/artifact/profile/history/offline review, full semantic input-array digest,
current QA image audit, one reserved lifetime slot, and shared <=180s deadline.
Normal preflight is unchanged. The trial branch verifies profile and source/audit
again after the response; privacy/peer/zero-definition/response gates remain.
Raw input, auth, model output/reasoning/stderr are not trial evidence. A false
intermediate proof is changed to passed only in the same transaction that completes
the invocation acknowledgement. Its purpose-scoped proof cannot satisfy normal
runtime readiness. Unknown/held results or new nonce/approval cannot replay a slot.

## Independent review

Fresh read-only /root/main_trial_offline_security_review applied security-audit,
architecture-review and quality-review. Initial request_changes; two bounded
fix/re-review cycles; final PASS for disabled offline scope, no blocking findings.
Reviewer did not run tests, contact network/services, access credentials, modify
files or delegate. Timing/usage unavailable. Final aggregate QA belongs to root.

Resolved initial findings: incompatible trial workspace; missing QA freshness;
CI journal fingerprint without detailed provenance; cancellation blocking outcome
observation. Final follow-up verifies adapter deadline clamp, post-response source
identity/audit check, strict permit types, malformed CI rejection and corresponding
negative tests. Old C-min audit was not reopened as a new unlimited repair budget.

| Reviewed source | SHA-256 |
| --- | --- |
| main_integration.py | 00a6c00b2d702a3ec6aa388fade1fe4f94f29235ca4b493ed6e03e56d180c352 |
| c_min_trial.py, executable-equivalent reviewed bytes | 56e927c9b946116b1aead71c6fe5f7ed12df9058617a3dc4460a1778e5d5182d |
| c_min_runtime.py | e0921a200fef86d4738623891e5f6dbf1d50be23243bfec87d693a0311fa62a2 |
| model_invocations.py | cd7c57ca5a552d9fe2d6f0070cf2a262e995aa73771c5995259ad3f80b095eae |
| local_delivery.py | b7c43286decddbf6d687900bb718cdcd45570cd3498c0e5517f8025f708f06f8 |
| controller.py | 6e030b32415d2b772ee4dd90da03be1c76a2867c2950d9ae26cbd0825d4241a8 |
| policy_migration.py | 59f912782141939e5a59877b71da89fd13175591fa33560a84c45e702e01cb95 |
| cli.py | 41e81a48bbc5085dac36cfabf9607137c7b00b035ef8619efa0fbf080e679ecc |
| check_commit_subjects.py | 765be186b3db63735812d45e4e9c2a2302e229579fcce1e008f3355517b0fa93 |
| pr-title.yml | 43efceabb46258f3e5e56c9b0ddfd3d35e0acdb9fd213cedbd914043ab6b495f |

Scanner adjunct: the public immutable PLAN_HASH constant was detected as high
entropy. Only a standard next-line public-reference annotation was added. Separate
read-only /root/ci_main_design_readonly_review verified its exact approved document
hash, line-limited annotation and byte equality to reviewed source after removing
ONLY two comment lines in memory. Current c_min_trial.py SHA256:
58d8477793b6ed8d1f7537b51b0786663d203fb439101469f23a5480b03ab4a2.
No executable code/scanner logic/test condition changed in that adjunct; core
review cycles were not restarted. Root's source scanner then reported0 findings.

## Verification evidence and limits

CI repair f5bba10 had full local QA582 passed/7 skipped and independent review.
Hosted run41493778984 proved Windows3.11 and Ubuntu3.11/3.13 success, but two OTHER
old compile tests timed out on Windows3.13. All four affected inspectors now use
explicit PSHOME Utility import/qualified Add-Type and stage markers, retain actual
native compilation and their original30s deadlines, and require ErrorAction Stop.
No claim is made that empty earlier stderr proved the exact timeout stage. Final
hosted success must be observed for the final pushed commit, not inferred here.

New targeted tests exercise malformed/failed/pending/cancelled/skipped/timed-out CI,
wrong SHA/publisher/attempt/workflow, missing QA/review/range proof, expiry, race,
lost reply, record failure, duplicate/resumed promotion, permission/protection
rejection, actual bare CAS/source race, post-cancellation LocalDelivery/Controller
observation, exact trial input rejection before send, source drift after response,
current/stale/failed/source-mismatched/missing real QA guard, acknowledgement rollback
with false proof, deadline clamp, nonce replay denial and normal-proof separation.
Kernel peer and native CLI identity are mocked in the new adapter tests; existing
real native/Job/Docker tests are separate evidence, never substituted by these mocks.

Final scripts/verify_loop.py --audit completed:632 passed,7 skipped in415.47s;
lint/format, strict native/Linux3.11 types, source secret scan, dependency consistency
and advisory audit passed. The skips are one Windows symlink privilege case and
six opt-in Docker cases. The six real Docker containment cases were separately
executed explicitly and passed in18.68s. Fixed native CLI cases ran against mocks;
hosted CI skips them when the fixed client is absent, never live evidence.
Exact-commit hosted job outcomes are recorded separately after actual completion.
Current offline PASS never establishes real auth/entitlement, official refresh
behavior or live Lite protocol compatibility.

## Decisions still separate

See C_MIN_LIVE_ACTIVATION_PROPOSAL.md and MAIN_PRODUCTION_ACTIVATION_PROPOSAL.md.
Multiple-workspace normal-run authorization remains outside the one-shot permit:
each current artifact contains an absolute workspace/settings binding. A future
run grant must bind each task/role/source/attempt/deadline rather than wildcard it.
Old v2 proof, exhausted task3/3, historical audit intents and expired run are not
reset. Production/Loop activation still requires actual current evidence and
separate owner permission.
