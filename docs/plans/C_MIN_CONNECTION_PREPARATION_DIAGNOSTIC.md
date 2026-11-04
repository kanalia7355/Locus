# Single-connection preparation: read-only owner diagnostic

2026-11-04 Asia/Tokyo. No authentication, provider inference, ACL repair,
service operation, main update or Loop launch is authorized by this diagnostic.

## Current result

Read-only inspection using the existing metadata-only native helpers identified
an extra principal on the normal operator profile. Its SID is
`S-1-5-21-3443020525-2208561192-1245966680-1003`, resolved through the local SAM as
the local group `CodexSandboxUsers` (not an unknown local user).
The group has ReadAndExecute mask `0x001200a9`: explicit inheritable ACE flags 3
on the home, inherited ACE flags 16 on auth.json and config.toml. The owner
matches the operator on all three. No credential/config content was read in
this inspection; no permissions were changed.

The existing validator trusts only the operator, SYSTEM and Administrators.
This group is outside that set. Maintaining the current policy requires
reviewing/removing its access to these protected profile paths; adding the group
to the validator would expand the credential-access boundary and is not a repair
within this authorization. Group membership and other uses must be checked before
an owner separately authorizes a narrow ACL change. This document provides no
ACL mutation command. Ancestor validation and complete profile validation must
be repeated after any authorized repair.

Both protected historical intent records remain unreadable by the ordinary
agent. Their phases and current hashes must be obtained before reconciliation.
The root controller remains stopped, with no registered trial history, auth
profile, trial permit, offline trial review or input contract. There is no new
trial slot implicitly available. Controller elapsed seconds are not subscription
quota; provider/account remaining quota cannot be inferred from these files.

## Existing mechanism reused

`scripts/Inspect-LocusLoopAuditState.ps1 -ConnectionPreparation` uses the existing
fixed Win32 nonsecret-record reader and administrator backup-read fallback.
Only synthetic-model-proof.json and transport-model-proof.json are read in this
mode, bounded to 8192 bytes each. It returns their presence, allowlisted phase
and SHA-256, never arbitrary JSON fields or model input/output.
Existing privilege state is restored before the protected handle is read; ACLs,
owners, service state and authentication state are unchanged.

The same process obtains ACL metadata for the manifest-bound normal profile's
home, auth.json, config.toml and bounded operator-profile ancestors. Get-Acl
queries security descriptors only. It returns SID, access mask, allow/deny,
inheritance and owner metadata without resolving names through remote services.
It does not read or hash credential data, enumerate credential stores, call
login/status/logout, repair ACLs or grant an exception. Remaining trial budget
is explicitly unverified; reading or completing a historical record grants no retry.

## Owner procedure

Use the same Windows owner account in a NEW elevated 64-bit Windows PowerShell.
Open this exact newly generated file and copy its complete block into that shell:

`C:\Users\hirot\Locus\.loop\runtime\audit-diagnostics\34e68426e75c4ed09badc46e18fe8da5\admin-command.txt`

Do not reuse earlier diagnostic, installation, completion or upgrade commands.
The wrapper checks both hashes and rejects reparse paths, copies only the verified
code to a new Windows Temp file, holds a read lock, rechecks its hash and launches
the existing diagnostic. That new temporary code file is the only deployment-side
file created; protected state, auth/config files, ACLs and services are read-only.
No credential input is needed. Return only the final JSON, not credentials,
raw record contents or unrelated logs. On error return the bounded failure JSON;
do not change permissions or retry authentication to make the diagnostic work.

Manifest SHA-256:
`743745cd834d3e4a88114fb7b354b1053f7eb6a9ce1515515a37ace481444852`

Script SHA-256:
`9e90cd1cc1f33bec47bbb9f2a5ada852bef6e7a3f0ee35cc94cd265f4336b8b1`

## Validation and limitations

The actual PowerShell/native reader ran on synthetic namespaces only: 2 tests
passed in 13.33 seconds. Coverage includes the legacy diagnostic, both new record
hashes, an orphan SID ACE, canary non-disclosure, unchanged file contents, changed
manifest hash, correctly hashed outside-profile target, and oversized manifest
rejection. Native code compiled during those tests. Both diagnostic and wrapper
passed PowerShell parsing; Ruff/format and offline secret scan passed.
The synthetic fixture alone sets its own test ACL to create a negative case;
the production diagnostic contains no ACL write.

Independent security review completed before presenting this procedure. Initial
review identified a medium bounded-manifest-read issue;
its fix uses a read-only/share-read stream with length checked before allocation
and an exact bounded loop. Fix/re-review cycle 1 returned no findings. The reviewer
independently ran the synthetic tests (2 passed in 11.87 seconds) and verified both
source/bundled script hash and manifest hash. Initial plus one re-review were used;
review elapsed time and token usage were not exposed. The owner wrapper was read,
not executed, by the reviewer. These tests
and review do not establish current protected-record outcomes or actual remaining
budget. Owner output must be reconciled against original grants; unknown or
consumed reservations stay consumed/held without an explicit new grant.

Next: owner diagnostic -> reconcile both immutable records and cumulative budget
-> obtain narrow ACL-repair authorization if needed -> repeat metadata validation
-> settle official CLI auth lifecycle -> freeze the single-connection approval
packet -> request separate live permission. No step authorizes inference by itself.
