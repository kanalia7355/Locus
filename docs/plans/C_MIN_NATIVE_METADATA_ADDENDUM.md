# Native metadata addendum: approval required before extension

2026-11-03 Asia/Tokyo. NOT adopted or implemented. Complements the already approved
input-binding design manifest43bd4b6b8159ec2c7fadef9c9e2f5e305f8d93d019a044af8297c20960c452a0;
it does not replace/modify that frozen document or grant a live trial.

## New evidence and current safe stop

Bounded native mock investigations used only isolated synthetic homes, the pinned
CLI/model, a local fake endpoint and a nonfunctional test marker. They used no
operator login/auth file, real provider or actual trial reservation. Only input
shapes, equality relations and public client-header literals were reported;
request/input/auth/response contents were not retained. This is not ChatGPT-path
compatibility or an approved native full-packet manifest.

The prior design explicitly required window identifiers to remain exact fixed
profile values. Actual two-launch comparisons contradict that assumption:

- client_metadata.x-codex-window-id changes.
- Its decoded x-codex-turn-metadata.window_id also changes.
- Decoded x-codex-turn-metadata.context_window_id changes and is UUIDv7.
- Existing session_id/thread_id/prompt_cache_key share the current thread; the
  turn_id/root_turn_id group is a separate current-turn identity.

Native request header names also include session-id, thread-id, version,
x-codex-beta-features and x-codex-window-id. These are outside the current v1
trial header inventory. The pinned local samples' public literals are
version=0.166.0 and x-codex-beta-features=remote_compaction_v2.

Current code keeps these unknown dynamic slots/headers denied. Regression tests
prove they cannot be added under the session_id generic descriptor. No wildcard,
dynamic-window exemption, new forwarded header or silent contract upgrade was
implemented. The approved v1 offline subset does not yet admit the native packet.

## Pinned producer evidence

Revision6ff1e1ca3b30fc8b914720681fcf5fe62e95f856:

- [current_window_from_state](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/core/src/session/mod.rs)
  constructs window_id as format!("{thread_id}:{window_number}") and returns the
  separate auto-compaction context_window_id. This is not an arbitrary string.
- [AutoCompactWindowIds / AutoCompactWindow](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/core/src/state/auto_compact_window.rs)
  initializes context ID with Uuid::now_v7(), window_number=0 and no previous
  window; advancing changes both number and context ID.
- [Responses metadata](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/core/src/responses_metadata.rs)
  emits body window metadata and the compatibility x-codex-window-id header.

The native mock shows field existence/change; source establishes the intended
producer relation. Neither alone establishes the actual operator profile or
same-user adversarial filesystem provenance.

## Smallest proposed extension

Add a separately versioned input contract v2, with its own approved design hash
and exact future permit input_version/input_hash. Do not broaden v1 or upgrade
existing permits; legacy v0 and v1 retain their existing comparator/admission.
The C-min response protocol remains c-min-lite-v3; input-contract v2 is not a
normal live receipt and does not authorize another trial slot.

Permit only these finite additional positions, with exact presence/counts in the
later reviewed full native template:

| Position | Exact rule |
| --- | --- |
| body.client_metadata.x-codex-window-id | Exactly current thread UUIDv7 + literal :0 |
| decoded body.client_metadata.x-codex-turn-metadata.window_id | Same exact derived :0 value |
| decoded compatibility header x-codex-turn-metadata.window_id | Same exact derived :0 value, if present in the exact inventory |
| incoming x-codex-window-id header | Same exact derived :0 value |
| decoded body/header x-codex-turn-metadata.context_window_id | One canonical fresh UUIDv7 with identical body/header values, distinct from message/thread/turn identities; same process/window/time and durable replay binding |
| decoded body/header x-codex-turn-metadata.window_number | Fixed integer0, never a generated wildcard |
| incoming session-id / thread-id headers | Exactly the same current thread UUIDv7 as body session_id/thread_id and prompt_cache_key |
| incoming version header | Exact pinned literal0.166.0 |
| incoming x-codex-beta-features header | Exact pinned literal remote_compaction_v2 |

Use a dedicated derived-window descriptor, not session_id-with-arbitrary-prefix.
Require an explicit declared thread equality group and context-window group in
the closed manifest. For :0 validate the UUIDv7 thread member and the relation,
not just UUID/string shape. Context-window IDs have their own durable fingerprint
and must not be reused under another contract version or invocation. Require
message, thread, turn and context-window identity groups to be distinct except
where the manifest explicitly requires the known aliases above.

The static body, provenance/instructions, model, schema, permissions, provider,
destination, clock/process/path ownership and remaining budget/history checks
stay exact. The64-slot maximum remains; no allowances for advance/compaction,
new_context_window, resume, additional turn, incremented counter or another call.
An unexpected :1, changed context ID mid-invocation or an extra request HOLD.

New incoming headers are validated locally ONLY; the existing relay upstream
header allowlist remains unchanged. In particular, do not forward/enable
x-codex-beta-features, version, session-id, thread-id or x-codex-window-id as part
of this extension. The flag is treated as a fixed observed client attribute, not
permission for remote compaction. Existing endpoint/single-send guards reject
any compaction/extra request. A future need to forward additional provider headers
or support other literals/protocols must stop for a separate review/approval.

## Implementation and verification after separate approval

Extend the existing pure binding validator, versioned authorization and trial
incoming-header hook only. Preserve the same journal, original bytes, atomic
aliases/request hash, process/path checks, no-retry slot and result proof.
Do not introduce another runner, auth client, service or controller.

Required offline evidence: exact native synthetic template prepared before the
validating launch (not runtime first-request learning); two distinct owned CLI
launches pass the same approved static contract while each full-body hash differs;
all new equality/count/type/version/time/uniqueness rules; unknown header/literal,
installation-ID change, :1, older/reused context UUID, mismatched body/header/
thread/window, changed permission/tool declaration and additional request reject
before any simulated upstream bytes. Show all new incoming headers remain absent
from the outgoing header map. Native mocks use synthetic homes only and must
never register a real permit or read/copy operator auth content. Repeat relevant
regression QA and independent security review. Estimated additional effort:
0.5-1 implementation/QA day, excluding owner history diagnostics/live approval.

Changed guarantee: the previously fixed window fields become explicitly typed,
derived, fresh per-launch values at only the listed locations. No broader
metadata exemption or additional egress capability is granted. The trusted
pinned-CLI/control-plane assumption and lack of at-rest encryption for the
existing auth-file exception remain unchanged.

Owner approval of this addendum's final exact SHA-256 is required BEFORE these
v2 edits. Approval would cover only offline implementation, synthetic tests and
independent review. It would not authorize real auth/refresh/inference, attempts
reset/additional real budget, protected-history/admin/service operations, profile
registration, main update or Loop startup. Previous historical records remain
Access Denied/unreconciled, and normal v3/workspace/live grants remain absent.
