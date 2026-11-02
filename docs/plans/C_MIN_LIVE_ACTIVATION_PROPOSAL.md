# Decision L — one real C-min connection (NOT approved)

This decision is independent from main integration and Loop startup. The owner
has approved offline implementation only. Do not execute the command below now.
Approved baseline bytes: C_MIN_SINGLE_CONNECTION_APPROVAL.md SHA256
eca090f9d22f4347e16ae371cba9106d6600906d0806b6a5eb9852e864a01af7.
Implementation/review: ../reviews/MAIN_TRIAL_OFFLINE_IMPLEMENTATION.md.

## Concrete command and finite packet

From C:\Users\hirot\Locus, after every prerequisite and a separate exact permit:

    .venv\Scripts\python.exe -m loop_engine.cli c-min-trial --plan docs/plans/C_MIN_SINGLE_CONNECTION_APPROVAL.md --approval <approved-decision-id>

Read-only status, never replay:

    .venv\Scripts\python.exe -m loop_engine.cli c-min-trial --plan docs/plans/C_MIN_SINGLE_CONNECTION_APPROVAL.md --approval <approved-decision-id> --status

Fixed CLI0.166.0 SHA256
9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42;
gpt-6.1-sol; built-in openai; TLS-verified
https://chatgpt.com/backend-api/codex/responses. No API key, alternative provider,
additional metered API account or billing path is accepted.

Prompt is exactly:

    This is a synthetic transport verification. Do not use tools. Return exactly the JSON object {"ok":true,"proof":"C_MIN_SYNTHETIC_OK"}.

Schema requires exactly ok=true and proof=C_MIN_SYNTHETIC_OK. Schema fingerprint:
ca0510ef6eae3687ddc97f6d2b1eadb431ada755137689c268c51a83fae98a52.
Only that synthetic content and explicitly assessed public CLI instructions are
eligible. No private source or research material. The complete parsed input-array
digest must equal the permit input_hash, including automatic instructions,
configuration, provenance and empty tool definitions. Minimal prompt-only array
fingerprint is774c9bd99b0e41ee458f8e50284b390b2d7f404e69301ecc56b0bcb197a4090e;
this is NOT proof that the official CLI produces that array. Extra automatic
context rejects before provider bytes. Do not bless a captured unknown array by
hash alone; assess every semantic component as public/synthetic before approval.

The managed workspace .loop/runtime/probes/c-min-single-validation must contain
only synthetic.txt with the exact bytes C_MIN_SYNTHETIC_ONLY followed by LF.
The command does not create or overwrite it automatically. All hooks, global and
ancestor settings/instructions and public model catalog must be assessed/pinned.
Unknown context cannot be stripped or silently permitted to make the test pass.

## Authorization fields and budget

The exact future c_min_trial_permit contains ONLY purpose, runtime, artifact,
workspace, plan, input_hash, profile, history, expires, max_calls, refresh,
offline_review. Its fingerprint is the ApprovalQueue target; the explicit decision
ID must refer to that approved scope row. No pending/rejected/stale approval works.
The current runtime/source identity before later changes is
32ab2adafc9572cb4bc4784e0fdead887e2140e23e5d97e801827a17644fa6a1.
Recalculate and verify it against reviewed files when preparing the actual permit;
do not automatically trust a changed identity or extend permission to future code.

Maximum ONE reserved CLI launch and ONE upstream inference POST in a180s shared
absolute window. Permit wait/preparation consumes that window; no resetting expiry,
task attempts or previous history. No automatic retry, new nonce, duplicate command
or reset after any send/launch uncertainty. A recognized denied WebSocket upgrade
may select the one HTTP request; no WebSocket is established. Unknown HTTP/SSE/CLI
events, unauthorized input, tool call,401/429/5xx, timeout, interruption, changed
source/profile/audit, failed reservation/record/ack or lost reply holds the slot.

## Auth permission must be explicit

Official CLI access to the EXISTING ordinary ChatGPT login only; no operator/agent
credential extraction, display, export, copy, token file creation or alternate use.
Same-PC relay-memory forwarding is inference-purpose only. The current implementation
requires a nonsecret identity/profile and existing secure keyring/encrypted-keyring
evidence. Its registration is absent; storage correctness is NOT established.

The permit refresh value official-existing-secure-backend-only would explicitly
allow the OFFICIAL client's ordinary lifecycle in that already approved secure
backend, never custom refresh/recovery or a new store. This lifecycle may involve
the client's official auth destinations outside the inference relay. Their concrete
scope and compatibility must be established in the nonsecret lifecycle review
before this value can be approved. The relay is not full CLI egress isolation.
If allowing these secure-store writes conflicts with the owner's prohibition on
saving credentials, DO NOT RUN: this conflict must be resolved explicitly, not
interpreted as implicit permission. login/status/logout/enrolment/recovery and all
audit services remain excluded even if this single trial is later authorized.

## Preconditions still needing evidence, not waived by this proposal

1. Final exact-commit mandatory CI and offline QA/review, current QA image audit.
2. Nonsecret reconciliation of current historical protected audit intents and
   cumulative trial slots, using an explicitly authorized read-only procedure.
   Existing documents establish two historical intents (one unknown, one blocked),
   not their current protected state. Do not read credentials/ciphertext values,
   restart services, elevate ACLs or reset either intent to obtain this evidence.
3. Nonsecret normal-profile ownership/storage/config evidence without changing
   auth state; missing/unsupported storage is a separate blocker, not auto repair.
4. Reviewed full synthetic/public semantic packet and exact input_hash for the
   fixed invocation. The prompt-only hash above is only a candidate, not native
   conformance evidence for the operator profile.
5. Purpose-specific offline-review/history metadata with exact matching bindings,
   and a NEW explicit cumulative allowance for at most ONE trial. No such real
   grant or success receipt has been created by offline tests.

Until these are true, approval preparation is documented but LIVE READINESS IS
INCOMPLETE; there is no honest ready-to-execute permit to approve yet. Approval
cannot be made concrete by filling unknown hashes/record IDs with guesses.

## Requested future decision

When the above records and hashes are concrete: approve only this one official
ChatGPT-path synthetic validation and explicitly scoped ordinary auth lifecycle,
with exact permit fingerprint and deadline. Output consists only of finite stage,
IDs/hashes/timing/schema/peer/gate/privacy checks and a trial-purpose proof; no raw
input/auth/response/reasoning or transport stderr. Passed requires all current
gates plus atomic result acknowledgement. The proof cannot activate normal
development, main integration, services or a30-minute Loop. Those remain separate.
