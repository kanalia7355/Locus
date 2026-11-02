# Trial input binding v1: offline implementation and held native extension

2026-11-03 Asia/Tokyo. Owner approved exact manifest
43bd4b6b8159ec2c7fadef9c9e2f5e305f8d93d019a044af8297c20960c452a0.
Before implementation its digest and all11 listed file hashes matched. The frozen
manifest's proposed-not-approved status is historical; the owner's separate exact
approval authorized offline implementation/tests/review only. It is preserved.

## Implemented and reviewed scope

The existing trial permit can explicitly select c-min-trial-input-contract-v1.
Its input_hash binds the exact closed template/slot/launch/header contract stored
as nonsecret metadata. No actual operator contract/profile/permit was registered.
Legacy permits keep their original whole-input comparison; no downgrade/fallback
or normal Worker/Reviewer/GoalEvaluator permission is added.

trial_input_binding checks finite exact selectors, static types/values via
deterministic fingerprints, UUID prefix/version/time, declared equality groups,
strict embedded metadata JSON, bounded clocks, the retained CLI process identity
and one exact arg0 text span. It neither changes the original request bytes nor
logs model/auth contents. trial_arg0 uses metadata-only retained Windows handles,
owner/private ACL/local path/identity/freshness checks and bounded namespace/child
inventory; no credential file is opened, copied, parsed, hashed or repaired.

InvocationJournal atomically persists original-body SHA256, contract and launch
identity, generated-value fingerprints and UNIQUE replay aliases with the
request_validated transition. Existing one-shot reservation, upstream reservation,
held uncertainty, no-retry and atomic acknowledgement remain. The relay's v1
header hook receives no authentication values. It rejects unknown incoming
headers and checks non-auth metadata before upstream reservation. Immediately
before reservation the adapter rechecks authorization/history/profile/source/QA,
peer/path/body and the durable binding. Trial results bind the input contract,
full body hash and journal evidence; they cannot satisfy the normal live receipt.

## Verification and review

Targeted final selection:83 passed in6.78s. Ruff lint/format passed. Native and
Python3.11/Linux mypy passed at full-verifier startup. Tests cover static tampering,
typed/fresh values, skew/expiry, strict metadata/equality, SQL concurrent claim,
alias collision and transaction rollback, reopen/duplicate denial, native Windows
metadata access/retention and namespace failures. Shared-adapter fake-process
cases prove unknown headers and changed permit/history/contract/path/peer/durable
binding stop before fake upstream creation; original body bytes are preserved.
Response tools/unknown events, lost reply, final source changes and no-replay are
retained for both old and versioned test permits. Synthetic fixtures are not real
approval, live transport or account/entitlement evidence.

Independent read-only security audit runtime_input_binding_implementation_audit:
initial no findings; supplemental review identified one low test-isolation issue
(unsupported-window descriptor also had an invalid template placeholder). Fix/
re-review cycle1 resolved it; final findings empty. One further cycle remains.
Reviewer inspected source/test evidence, did not run tests, edit, use network,
access credentials/state/services or run models. Separate usage/time unavailable.

Whole engine verifier --audit:760 passed,7 skipped in430.80s; lint/format, native
and Python3.11/Linux types, secret scan, dependency consistency and advisories
passed. Skips are one unavailable Windows symlink privilege and six opt-in Docker
cases, not passed containment checks. The final test-only placeholder correction
was made while this run was active; the complete affected selection was then
rerun (83 passed), and lint/format passed. Runtime source was unchanged throughout
that full run. This combination is recorded explicitly, not claimed as a fresh
whole-suite run of the subsequently strengthened test file. Pushed-commit CI must
be checked separately; local success is not remote/native live compatibility.

## Native investigation found a new explicit approval boundary

Bounded native mock probes, isolated synthetic homes and local fake responses:
zero real provider calls, no operator auth access. Only shapes/equality relations,
hashes and known public header literals were reported. These probes reused the
existing native fixture in memory; they did not run the v1 trial authorization
path, create a root trial or prove full native-v1 compatibility.

The approved design treated window identifiers as fixed profile values. Actual
native body window_id/x-codex-window-id/context_window_id change per launch, and
the incoming native header inventory contains five additional compatibility
headers. Thus a real native packet remains blocked under v1. Negative regression
tests explicitly deny new window selectors rather than adding a generic UUID
exception. Do not describe this subset as real-connection ready.

C_MIN_NATIVE_METADATA_ADDENDUM.md proposes a separately approved v2 contract for
exact threadUUID:0 windows, fresh distinct context UUIDv7, integer0, and local-only
validation of five incoming headers. The existing upstream header allowlist would
stay unchanged. Independent addendum review: needs_decision, no blocking design
findings. No v2 code or exception was implemented. The earlier fixed-window
assumption in the frozen approved design is now contradicted by native evidence;
the frozen document stays intact and the code preserves its strict stop.

## Live and normal development remain held

Protected historical trial records remain unreconciled/Access Denied; this does
not establish a remaining real allowance. Old expired budget and TASK-0013/3
remain preserved. No auth/profile/contract/live/trial grant was installed, no
receipt flags rewritten and no attempt reset. Existing-file at-rest encryption
is still unguaranteed, and filesystem metadata is not kernel creator attestation.

After a separately approved native extension: exact offline native template/header
and source conformance, current QA, owner-assisted read-only historical phase/hash
reconciliation and an explicit cumulative one-call permission plus official CLI
arg0/auth lifecycle permission still precede a real test. Normal v3 receipt,
per-role/task/workspace/run grants, Git-attributes assessment and explicit Loop
permission remain separate. No real authentication/inference, audit service,
credential lifecycle, main update, protection change, PR/merge or Loop was run.
