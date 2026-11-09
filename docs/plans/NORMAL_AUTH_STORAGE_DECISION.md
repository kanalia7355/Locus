# Normal-profile storage compatibility — decision required before implementation

2026-11-03. This proposal permits no real authentication/model/service operation.
It does not amend the frozen C-min approval documents or silently change guards.

## Verified nonsecret mismatch

Read-only inspection of the operator config, file existence, owner and ACL metadata
found configured cli_auth_credentials_store unset, secret_auth_storage=false,
auth.json present and secrets/codex_auth.age absent. Home/config owners match the
operator. Config SHA2569413d71516311d878a3f26e66d977c211825d0bff31a7b53c46c91566f2a08c0.
No auth.json content, credential-store entry/blob, token, key or cookie was opened,
displayed, extracted or saved. No ACL/config/login state was changed. Presence
does not establish valid authentication, credential contents or account access.

Current c_min_runtime.verify_profile accepts only registered keyring/encrypted-keyring,
explicit keyring config and NO auth.json. Thus this profile cannot pass, even if
the official CLI itself is already logged in. No c_min_auth_profile or real trial
permit was registered, and root status confirmed trial phase=absent/passed=false.

Official OpenAI documentation describes file, keyring, auto/fallback and ephemeral
credential modes and warns that auth.json must be protected as a password:
https://learn.chatgpt.com/docs/auth#credential-storage
Current documentation is not proof of every pinned0.166.0 encrypted-store detail;
the fixed public source and offline tests remain necessary. No API-key route is
an alternative, and no ephemeral mode may be populated by extracting credentials.

## Option A — explicitly admit existing file storage, offline work only

Smallest compatibility change to the EXISTING profile validator, not a new auth
client/executor. Add a separately registered existing-file profile for the SAME
CODEX_HOME and official ChatGPT login. Agent/helper checks only canonical path,
reparse chain, operator owner, bounded stat identity and restrictive effective ACL;
it never opens/hashes/copies/parses the credential file's contents. Only the
official pinned CLI may consume it under a LATER explicit real-connection permit.
No new token file, credential export, store migration, custom refresh or recovery.

Changed guarantee: the validator no longer requires OS keyring/encrypted storage
for this explicitly selected profile. There is no new at-rest-encryption guarantee
for auth.json. This is an exception to the previously approved secure-backend-only
admission, not a claim that file storage is encrypted or newly acceptable by default.

Replacement guarantees: exact pre-existing file/profile/path/owner/ACL/stat binding,
no other-principal read/write grants, same official CLI/provider/destination, zero
model tools, source/QA/privacy/budget gates, and immediate hold on identity/change.
Unknown/weak ACLs HOLD; do not repair ACLs or delete/replace auth.json automatically.
Existing secure backend paths and normal/trial permit separation stay intact.

Ordinary official refresh may alter an existing file or use other official auth
destinations. Offline approval does NOT allow it. A later live approval must either
explicitly allow that standard lifecycle in the existing profile or the test stays
blocked. Changed metadata after use remains a reconciliation hold, not inferred
success/retry. Agent-written credential files remain forbidden.

Implementation/verification after owner choice: negative tests for unauthorized
backend/weak or changed ACL/owner/reparse/missing or replaced file, metadata-only
inspection with content-open tripwires, unchanged keyring restrictions, trial-only
permit binding, post-use changes, no auth operations and no new files; independent
security review. Tests use synthetic temporary files only. No actual profile
registration, authentication, inference, service or Loop operation in this phase.

## Option B — retain secure-backend-only admission

Do not add file support. Prepare a separate owner-operated official-client storage
setup/migration plan using the existing account/subscription and approved secure
mechanisms, without agent extraction/copy of credentials. Normal-user encrypted
storage would need its own explicit exception; ADR0010's audit-only exception is
not automatically generalized. Actual config/auth/storage operations require later
permission and interactive owner action. This likely adds owner steps but keeps
the current at-rest admission condition. The existing file must be preserved;
there is no permission to delete it or reset any authentication/trial history.

## Required decision and unchanged holds

Choose A (bounded offline profile compatibility implementation) or B (secure-store
setup design only). Neither choice authorizes a real connection, login/status/
logout, credential access by the agent, refresh, new token storage, main operation
or Loop startup. No default is assumed from elapsed time.

The existing protected audit-history reconciliation and complete synthetic/public
input-array verification are also still prerequisites. This storage choice does
not fabricate those records or loosen the single-call/expiry/no-replay conditions.
