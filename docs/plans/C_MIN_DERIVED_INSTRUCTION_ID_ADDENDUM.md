# Derived initial instruction ID: proposed final native binding addition

2026-11-03 Asia/Tokyo. Design only, NOT approved or implemented. Current v2
extension was separately approved by SHA-256
6f84090f99d0cd5fc6d921ea935d05b8c45a36049184a3832ef38429820bf605.
Its normal-CLI two-launch acceptance test is currently FAILED, not waived.

## Exact remaining mismatch and source

Native local mock conformance used only synthetic homes, fixed official CLI,
the real single-trial PROMPT/SCHEMA, same workspace, mock responses and a
nonfunctional local test marker. No operator credentials, authentication,
provider calls, trial reservations or normal live grants were used. All request
and response contents remain in test process memory, never logs/files.

After v2's explicit known ID/time/window/path projection, only
body.input[0].id differed between the two launches. Its value is msg_ plus UUIDv5.
All v2 window/header/context checks passed before the remaining static-comparison
failure. The fixed first ID must NOT be ignored or admitted as a generic UUID.

The earlier v1 Message-ID rule assumed generated message IDs were UUIDv7. That
source assessment missed the special rebuilt base-instruction prefix. The
[fixed client source](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/core/src/client.rs)
constructs it at lines1052-1079:

    prefix_namespace = UUIDv5(NAMESPACE_OID, canonical_thread_uuid_utf8)
    instruction_uuid = UUIDv5(prefix_namespace, base_instruction_text_utf8)
    instruction_id = "msg_" + canonical_lowercase(instruction_uuid)

The cached client.rs was independently checked by the implementer against the
Git blob SHA in the pinned6ff1e1... tree; its bytes match after the cached text's
normal LF representation. This is source evidence, not live compatibility or
authentication evidence. The public source also has a tools-prefix UUIDv5 path;
that path is EXCLUDED here because the existing zero-tool gate must remain.

## Proposed narrowly derived descriptor

Add a separately versioned c-min-trial-input-contract-v3 with a new exact design
approval digest. v0/v1/v2 keep their own admission and do not auto-upgrade. C-min
wire protocol remains c-min-lite-v3; input version3 is a different version axis.
Reuse the existing validator, relay, owned process, journal and source/QA gates.

The only new generated selector is exactly [body,input,0,id], with descriptor
kind=base_instruction_id and one explicit thread_group reference. No other
location, UUIDv5 namespace, arbitrary prefix, additional_tools item, tool/history
item, instruction rewrite or schema/permission exception is permitted.

Require the exact static template at input[0]: type=message, role=developer,
one input_text content element with the exact pre-reviewed public base instruction
text, and exact pinned harness/non-hook provenance/content-item kinds. No dynamic
text or additional content/metadata holes may exist in that first message.
The future native manifest must pin the base-instruction UTF-8 SHA256 and retain
the exact text in the static comparison; capture does not constitute approval.

After validating every existing v2 fixed field/slot, resolve the descriptor's
thread_group to the SAME single canonical fresh thread UUIDv7 already required
by prompt_cache_key/body/header/session/window relations and owned CLI identity.
Recompute the two-stage UUIDv5 formula above from that validated thread and the
approved literal text. Require exact full msg_ value, canonical form and UUID
version/variant. Do not accept a UUIDv5 merely because it has the right shape.

Freshness is inherited from the independently validated current thread UUIDv7,
its time interval and owned CLI launch, not claimed from UUIDv5's nonexistent
embedded time. A prior-run instruction ID with another thread or text fails the
recomputation; same-thread replay fails the existing persistent aliases, one-use
invocation, lifetime trial slot and no-resend controls. Preserve stable replay
fingerprint domains across contract versions; reserve the derived ID atomically
with the original full-body hash and existing aliases before upstream reservation.

UUIDv5 uses the official CLI's SHA1-based identity construction. It is NOT an
authorization MAC, encryption or the security hash for request integrity. Exact
static text, owned fresh thread/process, explicit permit, SHA256 body/template/
source bindings and all prior safety controls remain the authorization boundary.
No claim of SHA1 collision resistance replaces those controls.

## Required offline evidence and approval boundary

Before any real grant: independently assess the literal native template as public/
synthetic, freeze it before the validating launch, then two distinct owned CLI
launches must pass that SAME static template while full raw-body hashes differ.
The offline fixture capture remains separate from production validation and may
not register/approve operator metadata or auto-learn an unknown first packet.

Test exact recomputation, wrong prefix/UUID/namespace/thread/text/provenance,
unknown descriptor or index, extra content, tool-prefix attempts, old/reused ID,
counter/window/header/body mismatch, expiry/wrong process, duplicate/crash/commit
failures, unchanged v1/v2 denial and original bytes/zero tools/upstream allowlist.
Retain the currently failing native acceptance until it actually passes this
separately approved implementation; do not skip it or claim completion meanwhile.
Repeat relevant QA, whole verification and independent security review.

Changed guarantee: one previously fixed or UUIDv7-only message ID may instead be
a deterministic UUIDv5 computed by one pinned formula, at one fixed position,
from already approved text and one authenticated fresh thread. All remaining
v2 fields,64-slot cap, exact input/model/provider/destination/permissions,
same-process clocks/path ownership, persistent reservation/replay and no retry
remain. No new orchestrator, executor, auth client or infrastructure is introduced.
Expected additional implementation/QA:0.5 day, excluding owner-only history work.

Owner approval of this file's final SHA-256 is required BEFORE implementing this
exception. Scope would be offline code, synthetic native/mock/adversarial QA and
independent review only. Real auth/model/credential lifecycle, profile or live
permit registration, protected-history/admin/service operations, new real budget,
main update and unattended Loop remain excluded. Historical records remain
unreconciled; normal v3 receipt/workspace/run grants remain separate startup holds.
