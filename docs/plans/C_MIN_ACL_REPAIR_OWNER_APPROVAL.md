# C-min ACL rehearsal: compatible shape and required boundary approval

2026-11-04 Asia/Tokyo. NOT permission to apply. Real ACLs, credentials, auth lifecycle, services, inference, Controller state and main remain unchanged.

## Five-object candidate: DO NOT APPLY

The earlier three-object candidate is superseded by this five-object scope. Existing Arg0Guard also checks tmp and tmp/arg0-windows; keeping their group access would fail the unchanged guard. No validator exception is introduced.

| Object | Before-security fingerprint | Proposed DACL |
|---|---|---|
| C:/Users/hirot/.codex/auth.json | `67b0a787eeea2222a6f403c969ffb2f6553ae43266ab8bdc328c27b1fec3ad8c` | three trusted FullControl ACEs, no inheritance flags, protected |
| C:/Users/hirot/.codex/config.toml | `67b0a787eeea2222a6f403c969ffb2f6553ae43266ab8bdc328c27b1fec3ad8c` | three trusted FullControl ACEs, no inheritance flags, protected |
| C:/Users/hirot/.codex/tmp/arg0-windows | `f30bba8b851814d95c2bb089bcc6671d074106725911f5b5da91fde789a3b730` | three trusted FullControl ACEs, OI/CI, protected |
| C:/Users/hirot/.codex/tmp | `f30bba8b851814d95c2bb089bcc6671d074106725911f5b5da91fde789a3b730` | three trusted FullControl ACEs, OI/CI, protected |
| C:/Users/hirot/.codex | `ea9436f283b06379827ccc29a2725995e6cd48a14ef83df89eebe7106854035f` | three trusted FullControl ACEs, OI/CI, protected |

Trusted principals are ONLY the unchanged operator SID (...-1001), SYSTEM and Administrators. The observed trusted principals already have FullControl; no new principal or effective right is added. Remove CodexSandboxUsers (...-1003) from these five objects only. Keep owners, object data, local group membership and account state unchanged. Convert trusted inherited ACEs into explicit entries and protect the target DACLs. Do not change SACL/integrity labels, keys, config values or credential bytes.

Metadata snapshot (no file data): `C:/Users/hirot/Locus/.loop/runtime/acl-rehearsal-approval/95bc95913ed645f4b6ece4bf6233ec3c/metadata.json`
Snapshot SHA-256: `4640e48783588e822e3121aba1624d2b8558677f03d0a7355c06bc5f96546613`

Snapshot includes before descriptors and stable object identities; it is evidence, not a permit. File content hashes are deliberately absent. File size/write time observations are not authorization to read or modify contents. Before apply, require the exact approved before-security fingerprints, stable volume/file IDs/creation identity, expected owner, local fixed drive, one hard link for files and no reparse ancestor. If identity or ACL differs, stop; do not widen the scope or silently refresh this plan.

## Mechanism and bounded impact

Use the documented non-propagating SetSecurityInfo operation on directory handles opened with MAXIMUM_ALLOWED. Those short-lived DIRECTORY handles are broader than minimum metadata rights; the implementation must expose no handle and call only the fixed descriptor/query operations for these three directories. They must never be used for enumeration, object deletion, content access or unrelated writes. On auth/config FILE handles request only READ_CONTROL | WRITE_DAC | FILE_READ_ATTRIBUTES, without FILE_READ_DATA or WRITE_DATA. No owner change or extra privilege is needed for the observed owner permissions.

Microsoft documents that MAXIMUM_ALLOWED directory handles prevent SetSecurityInfo propagating ACEs to children. The synthetic NTFS tests verify that ordinary propagating writes break inherited helper rights, while this mode leaves every non-target descriptor unchanged. [SetSecurityInfo reference](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo).

Order: lock/validate all five -> durable metadata-only before/expected-after/operation-intent record -> protect auth/config -> protect arg0-windows -> protect tmp -> protect home -> verify all five and unchanged non-target canaries -> record completion. No wildcard, /T, /reset, takeown, group/account change, parent-profile ACL change or arbitrary target is permitted. Target directories must already exist; missing or unexpected paths HOLD. Do not call sandbox setup or run the client to repair ACLs.

The non-propagating choice deliberately retains existing access on other descendants, including legacy helper files and skills/plugins. New files inside those unchanged runtime directories retain their existing group inheritance. New arg0 invocations inherit private parent ACLs and pass the existing Arg0Guard. This does not claim that every other CODEX_HOME file is confidential. Protected secrets subtrees are neither enumerated nor modified.

A later official sandbox setup can regrant home access; protected auth/config prevent an inherited regrant exposing those two files, but admission must HOLD when the home descriptor changes. No automatic cleanup, exception or reauthorization is allowed. The synthetic test deliberately reproduces and rejects this case.

## Compatibility scope

PASS requires real Windows-kernel access checks using a process-local restricted token and an unprovisioned synthetic SID on fresh managed fixtures only: original synthetic auth readability, post-repair auth denial, unchanged read access to existing helpers/skills/plugins/legacy shims, new skill readability, operator access, private fresh arg0, and exact rollback. No LogonUser, real sandbox-user password, SAM mutation or actual profile read under impersonation is used.

The existing native mock-only CLI conformance test separately exercises the pinned official CLI under a private synthetic home and frozen v3 input contract, including two validating launches. This proves the tested synthetic combination, not all installed desktop-app versions or every real-account sandbox command. No real ChatGPT authentication or provider inference is permitted for compatibility testing.

## Failure and recovery contract

Persist metadata-only snapshots and expected descriptor hashes before the first write. Acquire exact-identity handles without delete sharing; prevent concurrent file-data writers during the real operation, or stop before writing. Preserve all five identities. If any write fails or state becomes uncertain, stop; do not blindly rerun apply.

Before rollback, validate ALL five target identities and the complete recorded state before the first restoration. Applied targets must match their recorded after-state; untouched targets must match before-state. Missing acknowledgement, unexpected descriptor, replacement, link or partial journal means HOLD for owner reconciliation, not a guessed rollback. Restore only positively recorded applied targets, parent-first, via the same non-propagating mechanism. Verify exact original descriptors and unchanged non-target descriptors. Never restore credential contents or delete new files.

Rollback returns to the original insecure admission state and must leave model execution blocked. The synthetic rehearsal tests normal rollback, known partial failure, uncertain partial failure, descriptor drift, object replacement and out-of-fixture rejection. OS process crash persistence of a future REAL repair tool is not claimed by in-memory fixture tests; its offline implementation must validate the durable intent contract before owner execution.

## Owner operation for five-object candidate: WITHHELD

This document fixes the five-target delta and required recovery conditions. No real repair package or apply command is authorized by the synthetic-test approval. Do not request authorization to apply this delta: normal fresh PATH-shim compatibility is blocked as described below. The following conditions are the rejected candidate's safeguards, not permission to implement/apply it. A normal owner terminal should have sufficient existing rights; do not request elevation or alter ACLs when checks fail. If owner prefers manual execution, supply a pinned one-operation block after its offline implementation/review; do not ask the owner to run raw recursive icacls commands.

After an authorized application, run only metadata admission/identity checks and nonsecret compatibility probes. Do not run login/status/logout, refresh credentials, model calls, services or Loop. The real auth profile and single-shot permit remain unregistered; changing ACLs grants neither. Auth lifecycle and one fresh non-replayable trial slot require their own explicit approval.

## Evidence

Local related tests and exact-SHA Windows CI results are recorded in the companion rehearsal report. Initial independent review found the fresh PATH-shim gap; cycle 1 identified credential recreation risk in the alternative. The current three-object shape and offline adoption gates resolve both paper-design findings. Final fix/re-review cycle 2 returned no findings; independent synthetic tests: 11 passed in 11.90 seconds. Actual boundary adoption and real ACL operation remain BLOCKED. Review elapsed time/token usage were not instrumented. Both fix/re-review cycles for this scope are used. No real ACL operation has run.

## Confirmed compatibility conflict

Pinned official source at tree 6ff1e1ca3b30fc8b914720681fcf5fe62e95f856:
arg0/src/lib.rs lines 319-352 fixes the alias root under CODEX_HOME/tmp/arg0-windows;
lines 394-409 creates apply_patch.bat and prepends its directory to PATH.
windows-sandbox-rs/src/env.rs lines 34-45 inherits PATH, and elevated_impl.rs
lines 133-147 passes that environment to the normal sandbox path. The separate
.sandbox-bin helper directory is not a substitute for every caller of the fresh
PATH batch shim. Native apply_patch interception does not establish compatibility
for arbitrary scripts that invoke the PATH alias.

The new offline test creates a valid harmless fresh apply_patch.bat. It returns
37 for the normal owner via system cmd.exe, but the kernel rejects reads under
the synthetic sandbox restriction after the five-object repair. Old helpers
remain readable. Therefore NTFS inheritance/recovery correctness is PASS while
broad normal-Codex-sandbox compatibility of this repair is BLOCKED. A negative
regression test passing is not a compatibility success. No gate is weakened to
turn this into PASS.

The pinned production helper seam fixes the arg0 path to CODEX_HOME; no separate
arg0-root setting is established by this source. Moving/copying auth or introducing
a second execution stack is not proposed. No actual real-account sandbox or auth
operations were used to establish this access conflict.

Public source links:
- https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/arg0/src/lib.rs
- https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/windows-sandbox-rs/src/env.rs
- https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/windows-sandbox-rs/src/elevated_impl.rs

## Next approval proposal: three-object shape and limited boundary design/offline work ONLY

The initial two-file-only alternative was insufficient: deleting a protected file
and recreating it below inheritable Group RX can expose the replacement. This is
now covered by a positive synthetic alternative and an explicit adoption gate.

The smallest demonstrated ACL shape uses exactly three objects:

| Object | Proposed change |
|---|---|
| C:/Users/hirot/.codex/auth.json | Protected DACL, only unchanged operator/SYSTEM/Administrators FullControl |
| C:/Users/hirot/.codex/config.toml | Same private file DACL |
| C:/Users/hirot/.codex | Protected trusted OI/CI ACEs; retain exact CodexSandboxUsers RX but with NO inheritance flags |

Use non-propagating directory update for home, retaining existing assessed runtime
child descriptors and inherited group RX on tmp/arg0-windows, skills/plugins and
existing helpers. No actual tmp/arg0 ACL update is proposed for this alternative.
The before fingerprints of these three objects are the corresponding entries in
the metadata snapshot above. That snapshot is evidence only, not authorization.

The synthetic kernel probe proves: fresh PATH batch shim remains group-readable;
existing auth/config are group-unreadable; after synthetic rename/recreation both
new auth/config objects inherit only trusted entries and remain group-unreadable;
other descriptors are unchanged; normal rollback is exact and changed identity
blocks rollback without writes. Existing production private_acl/Arg0Guard reject
this candidate, as explicitly tested. Thus ACL-shape compatibility/recreation tests
can PASS while model-boundary adoption and actual repair remain BLOCKED.

Pinned setup_provisioning.rs apply_read_acls checks existing effective RX mask and
skips adding an ACE when the group already has that mask. Non-inheriting root RX
satisfies the tested mask without authorizing propagation. This is a source-level
compatibility argument; the entire real-account setup and every future CLI/app
version were not executed. Unexpected root ACE inheritance or new setup behavior
must HOLD, not be accepted. No global CODEX_HOME confidentiality claim is made.

Proposed offline implementation scope, if the owner approves:
- Keep auth/config strict private_acl unchanged: only operator/SYSTEM/Administrators,
  never group credential/config data access.
- Add separate read-only runtime admission using existing helpers/Arg0Guard, only
  for the fixed CODEX_HOME, tmp, tmp/arg0-windows, fresh owned invocation directory
  and its three assessed files. Permit only the registered Group SID (...-1003)
  and rights no greater than ReadAndExecute (0x001200a9), no write/delete/WRITE_DAC/
  WRITE_OWNER. Home Group ACE must be explicitly NON-inheriting; unknown flags,
  other SIDs/paths/files, links, owner changes and stronger grants fail closed.
- Retain exact-identity metadata-only no-delete-sharing auth/config handles for
  the ENTIRE CLI lifetime including cancellation/cleanup, using the existing
  retained-handle mechanism. _metadata currently opens with share=7 then closes;
  it does NOT provide this guarantee. Validate official in-place-write compatibility
  only on synthetic data. No real auth update permission is granted. Root inheritance
  protection is still mandatory: a lease alone cannot protect recreation after exit.
- Preserve owner/process/freshness/attributes/retained handles, source and before/after
  descriptor binding, all v1/v2/v3 exact input contracts, generated-ID reuse rejection,
  durable single-send/no-replay and zero-tool request/response gates. Changed auth
  metadata remains HOLD, never automatic adoption or retry.
- Use only existing validator/Arg0Guard/diagnostic/tests, no new orchestrator,
  executor/account/auth provider, API billing, token export or real-account logon.

Guarantee lost if later adopted: assessed nonsecret runtime directories/shims
would no longer be readable exclusively by operator/SYSTEM/Administrators.
Substitute guarantees to demonstrate: auth/config and replacement inheritance
stay private, group cannot mutate input/shims/security, exact identity and zero-tool/
replay checks remain enforced. Other descendants retain current access and are not
certified globally private. Real CLI auth refresh, issuer routing, credential
recovery/replacement and post-refresh reconciliation remain separately BLOCKED.

Mandatory offline adoption gates: positive fresh-shim group readability, denied
auth/config reads before and after recreation, no-delete lease across the full
launch/failure lifetime, negative group-write/SID/flag/path/identity/unknown-file
cases, future-root-regrant HOLD, unchanged tool/replay rejection, partial/uncertain
recovery, native mock-only v3 conformance, mandatory QA/CI and independent security
review. If required official behavior conflicts, stop for owner decision; do not
release the handles early or silently expand access. This new validation policy is
NOT implemented, adopted or authorized by the current synthetic-testing approval.

Requested NEXT approval is only this bounded design and OFFLINE implementation/
verification. It excludes ALL real ACL writes, credential use/update, real inference,
services, main and Loop. A final three-object real-ACL manifest and owner operation
must be frozen and independently reviewed after the boundary change is approved
and demonstrated. The current owner operation is STOP: do not apply the rejected
five-object repair, the old three-object-private-root candidate or this unadopted
read-only-runtime alternative. No executable real repair command is issued.
