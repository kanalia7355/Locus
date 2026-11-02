# Existing auth-file exception: offline implementation

2026-11-03 (Asia/Tokyo). Approved Option A document SHA-256 was verified before
implementation: bf57596881e4fc50eea52ce109e2f80197d9ad684febca1220f2f220d5dab5b4.
The frozen decision document remains unchanged; its decision-required wording
describes the earlier proposal, superseded by the owner's explicit Option A reply.

## Implemented scope

The existing profile validator accepts an explicitly registered existing-file
binding. No actual profile registration was performed. The same CODEX_HOME,
operator SID, configuration digest, file identity and protection metadata must
match. Unset store (the pinned CLI's file default) and explicit file are accepted;
auto/keyring/ephemeral do not enter this exception. Existing secure backend
restrictions remain in place.

The helper opens the credential path with READ_CONTROL|FILE_READ_ATTRIBUTES only
(0x20080), never FILE_READ_DATA/GENERIC_READ. It checks local fixed drive,
canonical handle path, reparse ancestors, regular-file attributes, bounded size,
one hard link, owner, DACL and stable identity before/after protection inspection.
Unknown grants, other-principal access and unsafe ancestor modification rights
hold. Home/config filesystem security queries now explicitly use SE_FILE_OBJECT.
No ACL repair, credential contents hash/read/copy, authentication, migration or
configuration write is provided. Only a separately permitted official CLI may
later consume the existing file. Changed metadata after official use holds for
reconciliation; this work grants no refresh permission.

There is **no at-rest-encryption guarantee** for this exception. Local administrator,
SYSTEM or an attacker controlling the operator can still access that operator's
credentials. Metadata validation does not prove credential validity or account
identity and cannot eliminate a malicious same-principal replacement race between
validation and a later CLI open. The explicit existing-file exception does not
become general agent permission to read credentials.

## Evidence and independent review

- Synthetic auth/adjacent dotenv tests: 37 passed. Includes real Win32 synthetic
  metadata-only access with ReadFile tripwire, filesystem ACL query, native failure
  cases with handle-close assertions, changed identities, weak ACLs, reparse and
  unsafe ancestors. No actual auth.json contents were opened.
- Stable-source full engine verifier with --audit: 692 passed, 7 skipped in
  404.44s; lint/format, both type checks, secret scan, dependency consistency and
  advisory audit succeeded. Skips: one unavailable symlink privilege and six
  explicit Docker opt-in tests. This run is not live-model or Docker evidence.
- Independent read-only security reviewer: initial two medium findings (native
  negative coverage; filesystem object type), both resolved at fix/re-review
  cycle 1; final no findings. Reviewer inspected source/tests, did not independently
  execute tests, access credentials, use network or operate services.
- Separate dotenv hardening denies an unassessed startup .env before any auth
  operation/content read; its initial independent audit found no findings.

No actual authentication/profile registration, credential migration, model
inference, audit-service operation, unattended Loop, PR, merge or main update
was performed. GitHub Push/CI evidence is recorded separately after delivery.

## Remaining startup holds

The one-shot trial still fingerprints the entire input array. Two bounded local
mock-only CLI launches showed fresh message IDs, turn metadata/times and a random
owned arg0 helper directory in environment context. Consequently a complete future
packet cannot yet be preapproved using the current whole-array hash. No runtime
normalization or wildcard was installed. A separately reviewed, explicit input
binding proposal and approval are required before changing this condition.

Current live receipt, protected historical-attempt reconciliation, future
per-workspace permits and the conservative Git-attributes guard also remain
unresolved. This offline exception does not establish readiness for a live call
or a 30-minute Loop. Previously green CI at 6c006e3 is historical evidence and
does not substitute for checks on the next commit.
