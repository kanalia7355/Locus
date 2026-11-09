# Thirty-minute activation: observed gaps and bounded offline change request

2026-11-05 Asia/Tokyo. Proposal only. No live grant or permission change.

## Observed causes

The existing launch refuses a failed/stale normal C-min v3 receipt. That refusal
is correct. The last requested thirty-minute launch did not start a Controller.
The doctor hardening in this task prevents its Codex login/status subprocess when
that receipt is absent/stale; it preserves every existing readiness condition.
A valid receipt is evidence, not an independent fresh authentication permission.

The current normal permit requires one exact runtime, workspace artifact, run ID
and expiry. Controller.run creates a new run ID only after startup, and evaluation
and task workspaces have different absolute artifacts. A single static permit
cannot cover those calls. This is an activation/composition gap, not grounds to
remove the checks or accept a wildcard. A single trial result intentionally does
not activate normal development. Root profile/history/input/review/permit
registrations remain absent; historical service reservations remain held.

## Requested approval: offline implementation and tests only

Reuse Controller, StateStore, existing model invocation journal and C-min
preflight. Do not introduce an orchestrator, account, executor, App or service.

1. Let the deterministic Controller prepare a durable proposed run identity and
   scope before execution. An approved launch must adopt that same identity,
   preserving attempts, counters, dependencies and old invocation history. This
   cannot set control=running or authorize a model call during preparation.
2. Bind the proposed scope to repository identity, immutable Goal/spec/config,
   runtime/client/model/profile, integration branch loop/local-development,
   allowed paths backend/frontend/tests, allowed Worker/Reviewer/GoalEvaluator
   roles, requested thirty-minute duration and a finite approval/start window.
   Retain the six-hour ceiling, configured task/cycle/attempt/review limits and
   all single-send/no-replay and unknown-outcome holds. No unbounded run grant.
3. For each permitted call, derive the concrete managed workspace artifact and
   execution/task/attempt/role/schema/source identity inside the Controller.
   Verify against the approved immutable scope and durably reserve before CLI
   launch. Revalidate exact bindings before upstream reservation and proof.
   Model output cannot mint/modify scope; arbitrary paths/roles or a bare
   namespace/wildcard are not authorizations. Changed/unsettled state holds.
   This changes approval granularity: instead of the owner preapproving one
   workspace artifact, the owner delegates derivation of exact per-call artifacts
   within this bounded scope to the deterministic Controller. That limited
   delegation is the security-sensitive change requiring approval before code.
   Keep control/runtime/Goal/spec/config identities immutable. Legitimate product
   HEAD advancement after verified local delivery remains allowed; each call
   binds its exact integrated HEAD, with unexpected mid-call drift held.
4. Preserve normal receipt validation, zero-tool request/response gates, privacy,
   strict/runtime ACLs, credential lifetime and QA gates. A trial proof is only
   trial evidence: never copy it into normal-ready flags. Normal activation still
   needs separately authorized current-source capability evidence and explicit
   normal-run authorization. If those cannot be demonstrated with the existing
   proof contracts, remain BLOCKED and report the exact missing guarantee.
5. Test preparation/start/restart idempotence, expiry, wrong run/workspace/role,
   changed profile/spec/source, source escapes, duplicate and uncertain sends,
   prior exhausted attempts, cancellation and crash recovery using synthetic
   states. Independently review, run existing QA/CI, then commit/ordinary Push.

This proposal permits neither relaxing a receipt condition nor claiming that a
transport-only or synthetic proof establishes all normal-workspace guarantees.
Implementation must stop before any further safety exception is necessary.

## Separate real-operation decisions, not granted here

The official CLI can load and refresh existing ChatGPT credentials before the
inference relay sees a request. Its standard auth traffic is outside that gate;
the default OAuth endpoint is not proof of complete issuer-destination
enforcement. Existing-file save truncates/writes and may leave incomplete data
after a crash. Auth metadata change remains HOLD, never silent adoption/retry.

Owner must explicitly settle official-client credential use/automatic refresh
and existing auth.json/auth.lock persistence. No investigator credential reading,
export, migration, new login, custom OAuth, API key or metered API is included.
If refresh stays forbidden, the current CLI cannot be launched under a claim
that refresh is prevented. A valid receipt alone is not this permission.

Only after the exact current profile/command/full-input/workspace/source/history
bindings are finalized can one new trial permit be requested: at most one CLI
launch and one inference POST, shared180s execution deadline, no replay or retry.
The two old started reservations stay held; approval alone consumes no new slot.
The agent executes the internal command after approval; the owner does not run
Python. Thirty-minute multi-call inference needs its own explicit activation
approval, after the single trial succeeds and every normal gate is satisfied.

No actual credential operation, inference, ACL/group change, service operation,
main update or Loop launch is authorized by this offline proposal.
