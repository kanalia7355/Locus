# C-min ACL/auth preparation: assessment and proposed authorization boundaries

2026-11-04 Asia/Tokyo. Investigation/proposal only. No ACL, membership, auth,
service, runtime permit or model execution change is authorized or performed.
Reuse Controller/Development Loop/local_commit_push and existing validators,
diagnostic, trial journal and synthetic fixture mechanism. No new execution stack.

## 1. Evidence and conservative historical accounting

Owner supplied the output of the reviewed combined diagnostic. See
`../reviews/C_MIN_TRIAL_HISTORY_RECONCILIATION.md` for the derived, non-operational
ledger. The original record is started with SHA-256
`a23610b70b8f12257bc31261ed335498e41a66d1878855fa2327b9a599eba2c9`.
It exactly matches the original-trial hash in the owner-approved runtime-upgrade
manifest (manifest SHA-256 ff4053a18ef4ccfadaa3d859564eddaed1af959821489c8ffda316b872068d33).
That upgrade and completion preserved it and allowed one separate diagnostic
inference against payload cee51f97a79bcdfdd2009f4e9fb889d999baf1b9d3e866e40f934cb18ffc0877.
Completion pinned the reconciliation permit hash
c64fc846dca7dd928475e2f7f9e511b640ec0ebe67c09d00eb15fca24db70a3a.

The diagnostic record is started with SHA-256
`df7281d09810616989c957a620cec473fe31592121b57c1f8564a928b0a39e25`.
This is its first owner-reported hash anchor; no earlier diagnostic-record hash
is available for an equality claim. Repo history documents one diagnostic blocked
at upstream_response/policy/HTTP200; it does not establish provider completion.
Both reservations remain held/unknown and non-replayable. Accounted historical
reservations: 2; refunds: 0; new trial grants: 0; completed inference count and
remaining subscription quota: unknown. The diagnostic's provider_request_sent=false
refers to that read-only operation, not the historical model trials.

This is PASS for conservative reservation accounting, not a live authorization
or a claim of exactly two successful provider invocations. No StateStore metadata,
intent, task attempt or Controller time budget was rewritten. Actual trial history,
profile and permit remain absent in the root StateStore. A future live permit must
bind fresh reconciliation evidence and explicitly add at most one new trial slot;
it cannot reuse either historical reservation. Reported owner JSON is not signed
machine attestation; verify hashes again at the permitted execution boundary.

## 2. Group purpose, membership and affected ACLs

Read-only local SAM queries identify CodexSandboxUsers as SID
S-1-5-21-3443020525-2208561192-1245966680-1003, containing exactly the two observed
local users CodexSandboxOffline (...-1004) and CodexSandboxOnline (...-1005).
No user/group was created, removed, disabled or modified. Pinned public CLI source
uses this group for dedicated low-privilege command accounts and filesystem read
roots. This does not independently verify current firewall effectiveness or the
implementation selected by every installed Codex app version.

Owner diagnostic: operator/SYSTEM/Administrators have full control; auth.json,
config.toml and home owners match the operator. The group has ReadAndExecute
0x001200a9: explicit inheritable OI|CI on home, inherited on auth/config files.
The existing private_acl validator rejects this principal, including on home.
The owner-profile ancestor is SYSTEM-owned, which the ancestor policy permits;
its unapproved capability SID has traverse/synchronize only, not the dangerous
ancestor modification mask. It is not a reason to rewrite ancestor ownership.

Known runtime metadata, read without directory contents/secret stores:
- .sandbox: explicit group Modify plus inherited ReadAndExecute.
- .sandbox-bin: explicit group ReadAndExecute plus inherited ReadAndExecute.
- tmp, tmp/arg0-windows, skills: group ReadAndExecute inherited from home.
- .sandbox-secrets: metadata unavailable; no access workaround or content read.

Removing the group or its members is inappropriate. A recursive /reset, /grant,
/takeown or /T repair of CODEX_HOME is inappropriate. Removing the root inheritable
ACE can propagate to descendants even without /T and can break helpers/skills.
The official legacy setup read-root logic includes profile entries unless
excluded; .codex is not in its hardcoded profile exclusion list. The read-ACL helper
can add inheritable group RX again during a later setup/refresh. This is source-level
evidence of regrant risk, not a claim that the current UI has executed that path.

## 3. Smallest current-policy repair candidate (NOT execution-ready)

Keep the exact existing trust policy. Candidate protected objects are only:
C:/Users/hirot/.codex/auth.json, config.toml and the .codex home directory.
Keep the existing owner and operator/SYSTEM/Administrators permissions; preserve
credential bytes and file identity. Protect the auth/config DACLs from inheritance
and remove only the CodexSandboxUsers allowance from their copied descriptors.
Remove that group's home allowance only after a metadata-only descendant-impact
inventory and compatibility rehearsal has fixed the exact affected-object set.
Do not remove group membership, add blanket deny ACEs, modify parent profile/drive
ACLs or grant a new broad read path. Blanket deny ACEs also conflict with the
current validator's supported security-descriptor contract.

This three-object description is NOT a claim of only three filesystem effects:
Windows inheritance propagation is material. Preserve already-authorized read
access needed by nonsecret sandbox runtime helpers/skills using an explicit,
reviewed affected-path manifest only after the inventory/rehearsal; do not guess
runtime paths or grant new access to secret stores. If additional targets are
necessary, enumerate them and obtain approval before implementation. Access to
.sandbox-secrets must not be widened to make the inventory pass.

Compatibility is BLOCKED: no zero-impact claim and no actual ACL repair command
is provided. A files-only repair leaves home admission failing; a home-only
repair can remove required inherited rights and can later be undone by official
setup. Silently allowing this group in private_acl is a security-policy exception,
not the current-policy repair. No such exception is approved or recommended here.

The next proposed approval is limited to OFFLINE rehearsal in newly created
synthetic directories under newly created .loop/runtime/probes/acl-compat-<nonce>
using existing tests/diagnostic, with at most three total attempts and two
fix/re-review cycles. It may set/restore only synthetic DACLs, exercise inheritance
and exact rollback, and simulate the official
read-root regrant. It must not touch actual CODEX_HOME, accounts/groups, credentials,
services or network; must not run the real auth CLI, model or Loop. Afterwards,
freeze an exact real-target manifest and obtain a separate owner/admin repair
approval. Read-only metadata inventory is within this investigation authorization;
actual protected objects remain untouched. This is not a new execution framework.

### Future owner repair and recovery requirements

Before any separately approved real repair, collect exact security-descriptor-only
snapshots (owner/group/DACL/protection) and file identities for every affected
object. Keep their hashes and protected metadata backup; never back up auth contents.
Reject unexpected SID, owner, ACE, reparse/hard-link identity or concurrent change.
Apply only the frozen reviewed delta. Stop on partial failure. Validate actual
profile metadata with the existing helper and verify sandbox runtime access with
nonsecret synthetic resources, without authentication or inference. No protected
credential file should be opened under a sandbox account to test readability;
security-descriptor access analysis/metadata-only checks must be used there.

Rollback restores only saved descriptors on the SAME identities and only when the
current descriptor matches the repair's expected after-state. Unexpected changes
hold for owner investigation instead of overwriting them. It must not restore
credential bytes, reset memberships, reauthenticate or replay a trial. Restoring
the original group access intentionally returns to a BLOCKED security posture;
keep all live operations disabled. New official setup/app updates can reintroduce
rights, so revalidate admission on every attempt and after official use. The
current validator already fails closed on descriptor or file-identity changes.

## 4. Official CLI auth lifecycle: source-confirmed, not exercised

Pinned executable 0.166.0 SHA-256 matches the existing binary pin. Public auth
manager at tree 6ff1e1ca3b30fc8b914720681fcf5fe62e95f856 matches the auth manager blob
from official tag rust-v0.166.0. Cached public storage.rs blob matches that tree
(60adea09ca81eb9b1d71511984db8041f42c2ba2). This verifies inspected public source
provenance, not a reproducible-build proof of every binary instruction.

The official client loads existing auth.json itself. It can refresh proactively
near expiry (five-minute window), fall back to an eight-day refresh age when no
JWT expiry is available, and has unauthorized-response recovery paths. File-backed
persistence takes auth.lock (read/write/create and file lock), reloads existing
auth, checks login continuity, updates tokens/last_refresh, then truncates/writes
and flushes auth.json. The normal operator therefore needs existing file read/write
and parent create/traverse for auth.lock, not new rights for sandbox users.
Inspected operator full control supports the source-level requirement on the
existing auth file and creation of a new lock in the home. A separate metadata-only
check found auth.lock absent at inspection time; its contents were not read. This
is not a proof of future exclusive-lock availability, concurrent file identity or
permissions on a subsequently created lock. Those must be checked at preparation;
no lock acquisition or auth operation was probed.
No token expiration, validity, account identity or actual refresh need was inspected.

Default refresh destination is https://auth.openai.com/oauth/token, distinct from
inference at https://chatgpt.com/backend-api/codex/responses. Source also supports
an environment override and credential-record OAuth issuer provenance. Existing
safe_environment(model=True) omits the override and API credential variables, but
the agent cannot prove the record's issuer without reading forbidden credential
content. The inference relay does not govern all official client auth traffic.
Do not call a source default a proven complete network-egress guarantee.

Lifecycle permission remains BLOCKED. The current permit literal
'official-existing-secure-backend-only' does not clearly express permission for
plaintext existing-file refresh. The offline existing-file exception granted
metadata validation only, not actual credential use/update. Any new permission
must explicitly identify official CLI-only use of existing auth.json/auth.lock,
normal auth network traffic, no login/logout/enrolment/recovery/migration/export,
no extra API billing and no agent access to credential values. A blanket permission
for any issuer/refresh endpoint is not proposed. If a fixed-auth-destination guarantee
is mandatory, its enforcement is an unresolved design issue, not an approved bypass.

File-backed save truncates before writing and is not an atomic file replacement
in the inspected source. A crash can leave incomplete auth data. No credential
backup or agent-led token restoration is allowed; official owner recovery would
need separate permission. This is a residual risk of the existing-file mode.

Auth refresh changes size/mtime identity and the existing post-use profile check
must HOLD rather than adopting the new metadata automatically. A successful model
response with changed auth metadata is not a passed trial. Reconciliation needs
separate permission; do not weaken the check or retry. CLI 401 recovery must not
create a second upstream inference POST; existing durable single-send reservation
remains authoritative. All live behavior and failure paths still need separate
owner permission; this investigation performs none of them.

## 5. Completion and owner decision sequence

PASS: owner evidence ingestion, conservative two-reservation accounting, original
hash comparison, group identity/membership/purpose, identification of required
CLI filesystem writes and source-level refresh behavior.
BLOCKED: exact remaining subscription/provider consumption (not available from
started intents), actual ACL compatibility/remediation, complete profile admission,
plaintext-file lifecycle permission, fixed refresh-egress guarantee if required,
operational history/profile registration, frozen one-shot live approval packet.

Additional existing CI blocker discovered during evidence checking: commit
c6da9cf8d2e220359a130f5593d90b4057d3235c, engine run 41782179152, Windows 3.13
failed the new synthetic connection-preparation test at its unchanged 20-second
process timeout (no stdout/stderr). Windows 3.11 was cancelled by matrix fail-fast;
both Linux jobs, product CI and convention CI passed. No definitive timeout cause
is established by that log. Owner diagnostic execution succeeded, but it does not
replace CI. No test, timeout, skip or CI configuration was changed in this
investigation; a bounded repair and fresh verification remain required.

Recommended sequence: approve bounded synthetic ACL compatibility/rollback
rehearsal -> fix and freeze the exact affected-object repair plan -> separate
owner/admin ACL authorization -> verify profile -> settle lifecycle policy and
post-refresh hold behavior -> bind historical reservations and at most one fresh
trial slot -> request one live connection approval. No existing acceptance check,
QA gate, v3 input binding, single-send rule or normal Loop gate is relaxed.

## Primary references and code/document discrepancies

Official OpenAI documentation (read, not just search snippets):
- https://learn.chatgpt.com/docs/windows/windows-sandbox
- https://learn.chatgpt.com/docs/auth

Pinned public source:
- https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/login/src/auth/manager.rs
- https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/login/src/auth/storage.rs
- https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/windows-sandbox-rs/src/setup.rs
- https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/windows-sandbox-rs/src/setup_provisioning.rs
- https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/windows-sandbox-rs/src/setup_provisioning/sandbox_users.rs

The frozen original single-connection preparation document still says its command
is unimplemented and fingerprints the whole static input. That is historical:
the adapter and explicit v3 runtime input binding are implemented. The document's
secure-backend refresh wording is also not sufficient for the approved offline
existing-file storage exception. Preserve frozen bytes; this report documents the
current mismatch. No runtime schema, policy or frozen ADR was changed here.

Security review: initial independent read-only review was nonblocking with one
low finding about distinguishing new auth.lock creation from existing-lock access.
The wording is corrected, absence of the lock was checked using metadata only,
and lock availability remains unverified. Fix/re-review cycle 1 completed with no
findings and no blocking issue. The reviewer
independently verified owner evidence/manifest/hash/ledger consistency without
actual credential, protected-state, SAM, service or network access. Review elapsed
time and token usage were not instrumented. Final consistency re-review cycle 2
also returned no findings; MD/local-JSON evidence projection and the unresolved
CI status were checked. Both fix/re-review cycles for this proposal scope are used.
