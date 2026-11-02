# Main fast-forward delivery extension — proposed, not activated

Owner request: 2026-11-03. This document requests **offline implementation only**.
No main write, protection edit, PR, App/Broker activation or Loop launch follows
from approval. Existing local_commit_push remains unchanged and selected.

## Current evidence and conflict

LocalDelivery records commit/integration/development Push in task checkpoints;
Controller marks completion only after publisher complete=true. StateStore is
the transactional authority. GitManager already reconciles parent/tree/binding.
Extend these components, not scheduling or execution infrastructure.

Read-only GitHub inspection found main requires one approving PR review,
last-pusher separation, administrators enforced, strict required checks from
GitHub Actions app15368. The main ruleset26268631 is disabled; branch protection
is still active. Existing gh user has repository push/admin permission; that is
NOT permission to bypass protection or proof that a main update would succeed.
With present protection a PR-free update must HOLD. Do not attempt to discover
permission by writing. Future protection changes require a separate precise
owner decision. No changes are proposed or executed by this implementation.

The configured conventional-title check currently runs ONLY on pull_request.
Therefore a pushed development SHA cannot satisfy the whole configured set.
Propose ADDING a push Conventional Commits validation to the existing workflow
under the same job name while preserving its PR-title check on PR events. Validate
the actual pushed commit range, reject malformed/empty/unknown inputs; never
publish a synthetic success or remove a required check. No policy file migration
is included in this approval. Actions receive no extra publication privileges.

## Smallest extension

Optional post-development-Push gate owned by LocalDelivery; keep its existing
mode's behavior intact. A separately approved future mode requires this gate's
complete receipt before Controller may complete the task or evaluate next HEAD.
No new worker, daemon, orchestrator, main checkout or merge commit. No default
enablement or production main transport is enabled in the offline deliverable.

Policy binds repository node ID/name, origin, source refs/heads/loop/local-development,
target refs/heads/main, required workflow paths/digests, check names/publisher app,
QA/review policy and deadline. Unknown fields or changed policy hold. Production
selection must use the existing explicit PolicyMigration and activation approval.

QA/review receipt must match task/checkpoint binding, parent/prospective tree,
committed tree and exact committed SHA; no changed/unreviewed source is covered.
First promotion needs an independent aggregate review of the WHOLE main..target
range, including historical development commits; per-task review alone cannot
retroactively certify the accumulated branch. Stop for missing evidence.

## Exact-SHA CI and atomic mutation

Read ALL pages of push workflow runs/jobs for target SHA, approved branch/repo,
workflow identity, latest run attempt and trusted Actions publisher. Every required
job must exist exactly as expected, completed/success. Pending holds without model
retry; failure/cancelled/skipped/timed-out/unknown/missing/stale/other-SHA hold.
Refresh CI immediately before mutation and on every reconciliation. Persist run,
attempt, job IDs, SHA, conclusion and policy fingerprint; names alone are insufficient.

Re-read remote main and development ref; fetch/verify exact object identities using
GitManager and prove main is an ancestor of target. No divergence reconciliation,
force flags, protection bypass, replacement commit, or fallback mutation method.

Proposed GitHub operation: GraphQL updateRefs with two RefUpdates, force=false:
main beforeOid=observedMain, afterOid=verifiedTarget; development beforeOid=target,
afterOid=target. Thus both source stability and main comparison are server-atomic.
GitHub documents beforeOid as the prerequisite and all updates atomic:
https://docs.github.com/en/graphql/reference/git#updaterefs
If a source no-op update is unsupported, HOLD; do not silently omit the guard.
Ordinary git push alone cannot bind the operator-observed old main, because its
fresh advertisement could accept another ancestor update. --force-with-lease is
not used. Local bare tests use git update-ref transactions with old OIDs, plus
explicit ancestry validation, as a simulation, not proof of GitHub enforcement.

Existing gh authentication is used only through gh subprocess, no token extraction
or file/env token provisioning. Network failures, GraphQL errors, insufficient
permissions, PR protection and ruleset changes hold. Read-only permission results
never certify future mutation authority. No transport invokes a GitHub mutation
in offline tests or this work session.

## Durable state and recovery

Separate main-promotion journal in the SAME StateStore database, keyed by
repository/target-ref/target-SHA and source QA/review/policy binding. Development
published_head and pushed_head remain separate; never undo their successful
delivery after main failure. FULL SQLite durability, BEGIN IMMEDIATE and one
unfinished promotion per target ref. All intentions precede possible side effects.

States: ci_pending -> ci_verified -> update_reserved -> remote_confirmed ->
recorded. held is a stop requiring reconciliation, not task success. An immutable
entry records before/after, policy, QA/review/CI evidence and run/deadline. Claim
and phase changes use transactions/CAS. No nonce/run-ID change bypasses an
unsettled operation. Do not reset task attempts, review caps or shared deadlines.

After restart, revalidate bindings/policy/CI and query BOTH refs. If remote main
equals target, reconcile the recorded original intent and persist confirmation
without resending; if main equals before but update was reserved/uncertain, hold
and require reconciliation rather than blind replay. Any other ref holds. A
recorded completion is checked against remote state before reuse; deleted or
subsequently advanced refs are not silently accepted as the exact target receipt.
Failure to commit the confirmation leaves durable update_reserved; later exact
observation can finish recording without a second update. Deadline/cancellation
prohibits new mutation, but read-only reconciliation can preserve known outcomes.
Controller must not advance to next task when main-gated delivery is incomplete.

## Offline acceptance / limits

Unit plus temporary bare-repository tests cover required jobs success/failure/
pending/cancel/missing/wrong SHA/attempt/publisher; source/main races; divergence;
pre-send reservation failure; lost reply after actual ref update; confirmation DB
failure; process restart; duplicate delivery; forbidden permissions/protection;
expired budget; source mismatch; retained development history; Controller hold.
Existing local_commit_push regressions must pass unchanged. Independent read-only
security/architecture review is mandatory with at most two fix/re-review cycles.

Offline PASS is not GitHub policy/API compatibility evidence. Production requires
separate activation approval and an approved protection configuration that permits
the operation while preserving independently reviewed exact-SHA checks. No such
configuration is selected here. Main remains untouched and current normal mode
continues to stop after development-branch Push.

## Approval requested

Approve the disabled, mock/bare-only extension and additive push commit check
above, preserving all current gates. This changes a delivery trust boundary and
is not inferred from the request to investigate. No auth, model, service, main,
protection mutation or production activation is included. Real-connection approval
is a separate document and decision.
