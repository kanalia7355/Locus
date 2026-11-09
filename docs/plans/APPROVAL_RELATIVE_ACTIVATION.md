# Owner-relative execution windows

Authority: explicit owner instruction 2026-11-05 to implement approval-relative
short execution deadlines without changing the preapproved operation or budget.
Offline implementation only; no credential use, refresh, inference or Loop grant.

The approval target is an immutable versioned request without a ticking execution
expiry. It fixes purpose, source/runtime, workspace/artifact, profile, full v3 input
contract, history, independent review, model/destination/schema/argv, auth lifecycle
and one lifetime slot. Only the existing ApprovalQueue may record the owner's
actual exact-hash decision. In the SAME SQLite transaction it derives and records
one activation from that decision timestamp: trial expiry = decided + 180 seconds.
All profile/input/history/review registrations and derived permit commit atomically
with the approval. Pending, rejected or revised requests activate nothing.

The activation record is immutable and lifetime single-use even if no CLI launched.
A failed transaction rolls back approval and all derived state. A committed record
is recovered as-is, never renewed after restart, expiry, rejection/revocation,
unknown launch, another nonce or repeated approval. Existing journal and trial
single slot, strict ACL/lease/privacy, frozen input, single-send/no-replay and
normal receipt conditions remain. Legacy absolute permits are not migrated.

The existing bounded normal-run proposal likewise fixes duration and launch-window
length before approval; its start window begins at the exact owner decision,
not preparation. First adoption retains the existing thirty-minute duration;
resume retains the original run ID/deadline/counters. Normal v3 evidence remains
required before execution. No normal receipt is issued by this work.

A separately confirmed blocker was mutable background model-catalog updates
changing artifact hashes although the selected model was identical. An optional
profile-bound immutable catalog snapshot pins exact bytes/path/hash and model
restrictions instead. It never silently refreshes or broadens models/tools; old
profiles retain current admission. A changed snapshot, profile or request fails.
The actual operator config/catalog/auth files are never edited by this feature.

Tests must cover long approval waits, decision-relative deadlines, rollback,
concurrency/idempotence, stale context, tampering, revocation, expiry/restart,
legacy nonmigration, journal uncertainty, catalog substitution and unchanged
trial/normal boundaries. Independent review and full QA/CI precede any live grant.

## Agent-owned operation

After final source/QA/review, the agent materializes the reviewed stable request,
then uses `python -m loop_engine.cli prepare-trial --request <file>` to request
its exact hash. This is a pending proposal only; real profile/permit registration
occurs only in the actual owner decision transaction. The agent records the
owner's explicit reply through the existing decisions interface, then runs the
existing c-min-trial command. No additional owner terminal operation is needed.
A stale runtime/profile/catalog snapshot/QA/input at decision time rejects the
entire activation; a pending request is not permission to silently rebind it.
The lifetime activation prevents reauthorization even before a launch after
expiry. Any such hold requires an explicit owner reconciliation, never reset.

Frozen earlier approval documents still contain the absolute-expiry protocol;
this is a new version authorized by the owner's later instruction. Their bytes
and expired grants remain unchanged. The old generic path is not auto-migrated.
Normal v3 proof still requires independent actual evidence and cannot be issued
by converting a trial result. This work fixes approval timing, not that guarantee.
