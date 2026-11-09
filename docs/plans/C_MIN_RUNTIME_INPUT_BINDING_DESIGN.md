# C-min one-shot input binding: design requiring approval

2026-11-03 Asia/Tokyo. Design only. No runtime, ADR, policy, permission, attempt,
authentication, service or model execution changes are authorized by this file.
Baseline source: c8d0b45795e1bc0bba9643911c32372eed366de0.

## Decision and scope

Replace the trial-only preapproved whole-input hash comparison with a closed,
versioned static-template hash AND a durable full-request hash bound to one owned
CLI launch. Validate a finite list of generated fields before constructing that
comparison. Forward the original validated request bytes unchanged. Do not erase,
rewrite or canonicalize the body sent to the provider. No generic UUID/time/path
removal, instruction suppression, open-ended matching or retry is permitted.

Reuse c_min_trial, c_min_runtime, InvocationJournal, OwnedCliPeer, AuditRelay,
StateStore and the official pinned CLI. Do not add an executor/orchestrator, change
Controller/QA/local_commit_push, or apply this trial exception to normal workers.
The existing whole-input comparator remains operative until separate approval
and implementation. Legacy permits must never fall back into the new contract.

## Evidence and limitations

Earlier native mock investigation used two isolated synthetic-home launches,
local fake responses, nonfunctional test credentials, no operator auth and zero
real provider requests. Message IDs, turn IDs, fractional Unix seconds and one
arg0 directory path differed. The analysis-only projected digests matched after
those specific substitutions. This establishes a hypothesis, not an approved
template, operator-profile equivalence, valid auth, live protocol support or
completed input-binding implementation. No captured body was retained in logs.

The pinned public source revision is 6ff1e1ca3b30fc8b914720681fcf5fe62e95f856:

- [ResponseItemId](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/protocol/src/response_item_id.rs)
  creates prefixed IDs using UUIDv7; deserialization itself remains permissive.
- [Message metadata](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/protocol/src/models.rs)
  documents create_time as fractional Unix seconds and preserves existing turn IDs.
- [Turn metadata](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/core/src/turn_metadata.rs)
  includes a UUIDv7-based turn constructor. The exact trial path must still be
  checked against source plus the future native mock fixture.
- [arg0 lifecycle](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/arg0/src/lib.rs)
  creates a per-session directory below CODEX_HOME/tmp/arg0-windows, retains its
  lock and creates the two Windows batch helpers; it also attempts stale cleanup.
- [Environment renderer](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/core/src/context/environment_context.rs)
  emits ordered filesystem entries. Reordering them is not an allowed exemption.

Current official [credential-storage documentation](https://learn.chatgpt.com/docs/auth#credential-storage)
confirms file storage is sensitive. It does not specify these pinned internal
wire fields. The existing-file exception remains metadata-only for this code;
official documentation is not evidence of current authentication or entitlement.

## Fixed contract and the two hashes

An offline-reviewed, owner-approved manifest must contain an exact parsed request
template, exact permitted header presence/static values and exact ordered slot
descriptors. Template material is public CLI instructions and synthetic data only.
It also binds CLI binary/source/catalog/config/privacy options, model gpt-6.1-sol,
built-in openai, verified TLS destination
https://chatgpt.com/backend-api/codex/responses, the fixed synthetic prompt/schema,
workspace absolute path and marker, profile metadata fingerprint, QA audit,
runtime source identity, role=trial, owner, permit and history reconciliation.
No API key, proxy/provider substitution, increased permissions or tools allowed.

Define fingerprint using the existing deterministic JSON fingerprint function:

1. static_hash = fingerprint({domain:c-min-trial-input-contract-v1, template,
   slots, fixed_headers, fixed_launch_contract}). The template contains typed
   structural placeholders ONLY at enumerated slots, not magic strings that may
   occur inside arbitrary prompt text. Static values remain exact, including
   absence/presence, ordered messages, roles, all other text/provenance, schema,
   tools/additional_tools and configuration. No semantic equivalence allowance.
2. request_hash = SHA256(original bounded HTTP body bytes), computed after full
   validation. Persist it with static_hash, permit hash, invocation ID, launch
   identity, generated-value fingerprints and deadline BEFORE upstream_reserved.
   Recheck the immutable body and launch/path evidence immediately before the
   existing upstream reservation. The actual send uses those same bytes.

Credentials and account headers are excluded from both hashes and every record.
Validate their existing bounded single-header contract in relay memory only.
Do not read/hash an auth file to build either hash. The changed guarantee is that
a human approves static content plus finite generation rules, rather than every
future byte in advance. Full-body identity remains fixed once the single owned
launch has supplied its first admissible packet. This is a safety-boundary change.

## Finite generated slots

Slots are exact JSON pointers, or exact header names, with fixed count, type,
prefix/version, source, time bounds and equality groups. No regex applied to all
strings, arbitrary XML paths, optional-field guessing or first-request auto-learn.
Maximum 64 slots per approved manifest, which must also list exact expected counts.
Unknown/additional/missing fields or a new wire version HOLD before upstream bytes.

| Field class | Admission rule | Ownership and replay binding |
| --- | --- | --- |
| Message IDs | Only manifest-listed item positions; exact msg_ prefix and lower-case canonical RFC UUIDv7 suffix, variant/version checked; timestamp in launch interval | Unique per message; fingerprints cannot occur in any prior binding row; one exact authenticated CLI sender |
| turn_id / root_turn_id | Only exact listed metadata/header locations; canonical UUIDv7 and declared equality groups | Fresh current turn; equality across specified body/decoded-header fields; never accept an unrelated value because it is a UUID |
| create_time | Only listed metadata locations; finite JSON number, not bool/string/NaN/Infinity; fractional Unix seconds | Inside the current launch/request interval; no historical-message allowance |
| Session/thread/request IDs | Exact finite slots only; their pinned producer's concrete UUID version/prefix and equality groups, including thread.started output where available, must be established offline first | Same launched process and invocation; fresh IDs and no previous fingerprints; no automatic allowance for all metadata |
| One arg0 filesystem path | Exactly one approved environment text span at one fixed input/content position, under one read-only entry | Fresh directory identity owned by the same operator, associated with the same CLI invocation; details below |

The previous five-item mock (developer/developer/developer/user/user) is only a
candidate inventory. It is NOT granted as a wildcard shape or live manifest.
The exact full SCHEMA and final invocation may produce another shape: that shape
must be explicitly audited and frozen offline before any live approval. The
analysis-only 78d1d9... digest is not an authorization hash. No actual profile is
registered and no live permit is synthesized while preparing this design.

Top-level prompt_cache_key and client_metadata IDs, if present, are part of this
inventory too. Stable installation/window identifiers must be exact reviewed
nonsecret profile bindings, not universally allowed UUIDs. Decode embedded JSON
using strict duplicate-free parsing; require exact known fields, types, paths and
cross-field relations. Session_id/X-Client-Request-Id/X-Codex-Turn-Metadata headers
must have matching explicit rules. Unknown context/headers cannot bypass the
template through an opaque string. Existing protocol/privacy header gates stay.

## Process, clock and temporary-path provenance

The issuing authority for generated values is the exact pinned CLI instance:
OwnedCliPeer authenticates kernel TCP PID/SID, retained process handle, creation
time, image and live Job membership, both before validation and before reservation.
Bind those facts to the invocation ID claimed BEFORE launch. Never infer issuer
from UUID shape, owner SID, a claimed JSON field or a directory's name alone.
Retain process identity until termination; PID reuse, another user's connection,
another same-user CLI process, a dead child or changed executable HOLD.

Capture controller UTC and monotonic clocks before resume. The original absolute
permit window is at most180s, including all preparation; no renewed clock/window
on restart. Generated timestamps and UUIDv7 embedded milliseconds must be within
[resume_utc-2s, request_utc+2s] AND the original permit interval. UTC vs monotonic
elapsed divergence over2s HOLD; do not silently widen skew. Persist the original
times; after any reserved launch a restart cannot rebind or relaunch the process.

The arg0 path is validated at its exact text span, not normalized across the
whole XML document. Reject DTD/entities, repeated nodes, extra attributes, mixed
content and alternate representations. Reconstruct the approved literal string
with just its single validated escaped path and compare every remaining byte.
No XML sorting, whitespace collapse, case/slash folding of surrounding text or
re-rendering of other permissions. Path representation itself must match the
single pinned Windows rendering in the manifest.

Require canonical local fixed-drive path exactly
<registered CODEX_HOME>/tmp/arg0-windows/codex-arg0<6 ASCII alphanumeric>.
Reject reparse/symlink/UNC/device/ADS/dot-segment/hard-link aliases, directory
replacement, extra path components or a write permission at the read-only slot.
The directory must be absent from the bounded prelaunch namespace snapshot, have
creation time within the launch window, operator owner and restrictive allow-only
ACLs on it, its parents and its fixed expected children. Validate by retained
metadata handles and volume/file IDs, holding them without delete sharing through
the upstream decision; use metadata access, never credential data access.
Exactly .lock, apply_patch.bat and applypatch.bat are allowed; establish their
pinned public producer contract offline. No executing a helper and no helper data
read is needed for this metadata/issuer policy. Recheck handles/names/ACL/identity
before reservation; inaccessible or ambiguous evidence HOLD without repair.
Bound the prelaunch snapshot to256 children and metadata examination to the
remaining absolute deadline. An oversized namespace stops, not a partial scan.

The combination of authenticated producer, fixed source path construction,
fresh namespace/time/identity and static environment template establishes
invocation association under the existing trusted-CLI/control-plane assumption.
File owner/ctime alone is NOT proof of which process originally created a file;
this design does not claim a kernel filesystem-creator attestation. A compromised
CLI, malicious same-principal controller or administrator is outside the current
boundary and can falsify provenance. No new handle-table/memory snapshotter or
credential access is proposed. If stronger adversarial same-principal creator
proof is required, this minimal design must remain held for a separate decision.

The official CLI's arg0 startup writes/cleanup under the existing home are real
lifecycle effects, distinct from credentials. Offline approval covers synthetic
homes only. A future live approval must explicitly scope the CLI's own arg0
lifecycle and ordinary auth lifecycle; this design grants neither. The agent
does not delete stale directories or modify auth/config/ACLs to make checks pass.

## Durable reservation, uniqueness and recovery

Keep the existing lifetime c_min_trials slot=1 and existing model_invocations
sequence: prepared -> launch_reserved -> request_validated -> upstream_reserved
-> terminal_validated -> cli_validated -> completed. Keep atomic trial/result
acknowledgement. No invocation ID, owner/nonce, changed deadline or new plan can
give an uncertain trial a second call or free a consumed slot.

Add one small typed binding table to the SAME StateStore, not a new state store:
one UNIQUE invocation_id and one UNIQUE replay fingerprint per dynamic ID/path
identity namespace. Multiple occurrences in declared equality groups share one
value row; two different messages may not reuse a message ID. Store only bounded
nonsecret identities/hashes/times/status. Never raw prompt/XML/body, auth/header
values, model response/reasoning or credential content. Reserve ALL aliases and
the full request binding in one synchronous=FULL/BEGIN IMMEDIATE transaction
coupled to the existing request_validated transition. A conflict rolls back all
new rows, then holds the existing trial; no partial acceptance or stale overwrite.

Use a stable domain separator for replay fingerprints across contract revisions,
not a permit-dependent salt that would let old IDs through a new contract. A
contract-version mismatch is independently a hard rejection. Keep replay rows
after failures/completion; no cleanup, nonce reuse or clock expiry releases them.
Old pre-contract records lacking ID fingerprints are NOT asserted as fully
covered: their current reservations/history must be reconciled and their old
timestamp ranges rejected. Trust in the pinned fresh, non-resume CLI is required
for identifiers lacking pre-contract records; a strict claim about every ID ever
created on the machine cannot be made from this database.

After reserving a launch, any duplicate request or process restart HOLD even if
the full-body digest matches. A crash before/after the binding transaction or
upstream reservation never permits resending. Recovery observes existing rows and
peer/deadline/result evidence only. It cannot reconstruct a fresh launch from
saved values or infer success from HTTP200. Missing/uncertain result stays held;
acknowledged result may be reported idempotently without a model call. Expired or
missing records never imply additional budget. Recheck exact permit/profile/
runtime/history/QA deadline before upstream; a changed approval or cancelled
operation stops. The original response tool-call gate and zero-tool checks remain.

## Current history, budget and permit reconciliation

Read-only observation on2026-11-03: SQLite opened with URI mode=ro/query_only;
StateStore constructor (which creates tables) was NOT used.

- control=stopped. Old run eafbe75fe98343dcbb07069f77e469e3 deadline
  1793438356.0965943 is expired; consumed_seconds=314.31721839999955.
  This is controller time usage, not the ChatGPT subscription's remaining quota.
- TASK-001 remains completed, attempts3/3. No attempt reset or task transition.
- No c_min_live_permit, c_min_auth_profile, c_min_trial_permit,
  c_min_trial_history or c_min_trial_offline_review metadata exists.
  model_invocations and c_min_trials tables are absent in the actual root state.
  Mock databases are not evidence of new real allowance or successful trial.
- Pending dependency2/merge1/publication1/scope4/security1 decisions remain pending.
  One historical approved scope decision is not this future permit.
- Historical reports document TWO prior isolated-audit intents: original unknown;
  later diagnostic blocked at upstream_response/policy/HTTP200. Ordinary bounded
  read attempts for the exact nonsecret synthetic-model-proof.json and
  transport-model-proof.json both returned Access Denied. No ACL/elevation,
  backup privilege, auth file, login/status or service operation was used.

Thus current protected phases/hashes and cumulative remaining authorization are
UNVERIFIED, not zero consumed and not one available. An owner-assisted existing
read-only diagnostic must include BOTH fixed trial records (the earlier four-
record diagnostic did not include the later transport record). It must expose
only finite phases/hashes/identity and purpose, validate path/ACL/size, never open
credential/ciphertext/model output, and make no service/auth/state changes.
Its exact reviewed command and any necessary administrator action are a separate
step, not permission granted by this implementation proposal. Preserve all old
intents, even unknown/failed. Future trial approval must explicitly grant at most
ONE additional cumulative call/launch against that reconciled history.

## v3 proof and workspace permissions

Current live-runtime.json is passed=false, surface_version2 with no_tools=false,
fresh_request=false. It cannot satisfy v3 or be upgraded by editing flags. A new
trial-purpose proof must bind the reviewed runtime, new input contract, full
request/launch/permit/history identities, one call, completed request and response
gates, validated CLI schema, unchanged profile/QA/privacy and authoritative atomic
acknowledgement. Keep prior evidence unchanged and report all unverified checks.

The one-shot proof is NOT a normal-development receipt or a multi-workspace grant.
Normal require_receipt still requires surface_version3, c-min-lite-v3, response/
auth/live verification, no_tools/fresh_request and exact current runtime identity.
Do not change its gates or copy trial passed into a normal receipt automatically.

Worker/Reviewer/GoalEvaluator artifacts include absolute workspace paths. Future
normal-run permission must bind each role/task/spec/source snapshot/workspace/
attempt/schema/policy/deadline to its specific invocation; one synthetic workspace
cannot authorize another, a successor task or all loop/* paths. Their read-only
model process and separate source-only QA/writes/Push remain unchanged. The normal
run grant, current QA audit, Git-attributes assessment, protected history, normal
v3 proof and explicit30-minute trial permission remain separate startup holds.
No normal workspace authorization is implemented by this proposal.

## Proposed edits after approval and offline acceptance

1. Trial-only binding validator in c_min_trial (or a small pure helper), explicit
   versioned permit selector/manifest digest. Existing v0 exact-hash permits either
   use their original comparator or reject; no auto-upgrade/fallback.
2. c_min_runtime/OwnedCliPeer expose bounded nonsecret retained launch identity,
   UTC/monotonic anchors, arg0 prelaunch snapshot and retained metadata handles.
3. InvocationJournal/StateStore adds atomic binding/uniqueness records to the
   request_validated transition. No separate orchestrator, attempts or ledger.
4. AuditRelay validates the trial's finite non-auth header contract before the
   upstream reservation; original body and existing tool/response gates remain.
5. Tests, native mock fixtures, source/runtime manifest coverage, and independent
   security re-review. No actual profile registration or real permit creation.

Required tests: fixed text/roles/order/model/provider/destination/schema/permission
tampering; unknown slots/headers/provenance; embedded tools and returned tool
events; UUID version/prefix/time/collision/cross-run reuse; equality-group mismatch;
bool/string/nonfinite times; clock skew/expiry/PID reuse/wrong peer/dead process;
stale/foreign/extra/changed/oversized/reparse/ADS arg0 namespace; directory/name/
ACL/identity races; duplicate requests; crash at every reservation/result boundary;
concurrent claims; fsync/commit failure; old permit downgrade; proof not enabling
normal work; auth-content-open/read/copy/log tripwires; original QA/review/delivery
regressions. Native mocks use only synthetic homes and local fake endpoints and
must prove exact bytes forwarded and zero upstream requests on any invalid case.

Estimated effort after approval: 2-3 implementation/QA days including native
failure/recovery coverage and independent security review, excluding owner-only
history diagnostics and real-connection scheduling. If native producer/path
assumptions fail, hold and report instead of broadening the rules.

## Approval requested after independent design review

Approve only this versioned trial input-binding change and its offline
implementation/tests/security review, with the final manifest SHA-256. Explicitly
acknowledge loss of advance equality for every generated byte, replaced by exact
static content plus authenticated, finite, fresh single-launch bindings and a
durable full-body hash. Existing-file at-rest encryption remains unguaranteed.
This approval grants no live call, auth/refresh/recovery, historical-record reset,
administrator action, service operation, main update or unattended Loop. Actual
live approval follows exact template/source/QA/history/profile and lifecycle
evidence; any unresolved prerequisite remains a stop condition.
