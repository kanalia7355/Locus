# Credential metadata lease sharing class: approval addendum

2026-11-04. Proposed only. No actual credential/profile ACL or handle change,
authentication, inference, service operation, main update or Loop is authorized.

The approved proposal e100391c12ca9bb434fb817a5a3999ea5e7e489316d12df6382c5f1f107ea000
specified READ_CONTROL|FILE_READ_ATTRIBUTES (0x20080) retained handles with share=3.
Real Windows synthetic-file tests showed that these metadata-only access bits do
not prevent rename despite omitting FILE_SHARE_DELETE. Adding SYNCHRONIZE or
FILE_READ_EA did not prevent it either. The current offline prototype remains
BLOCKED for the required fixed-file-ID guarantee; failed tests are not waived.

The smallest demonstrated sharing-class alternative adds FILE_EXECUTE (0x20),
making the auth/config FILE handle access 0x200a0, still share=3. Synthetic rename
then fails. A real ReadFile call on that synthetic handle fails with access denied;
FILE_READ_DATA and GENERIC_READ are absent. No write/delete/WRITE_DAC/WRITE_OWNER
access is requested. A directory probe also allowed rename with 0x20080 and
blocked it with 0x200a0. On directories bit 0x20 is FILE_TRAVERSE, not listing/data
access. Scope is exactly the five CredentialLease handles: auth.json, config.toml,
home, tmp and tmp/arg0-windows. No arbitrary path or additional handle is included.

This changes the literal metadata-only-rights guarantee: the internal retained
file handle would also possess FILE_EXECUTE (directories FILE_TRAVERSE). It does not grant a new principal
access or alter the file ACL, but this extra capability was not listed in the
approved mask. Code must never execute, map, return or transfer that handle;
only existing metadata/security queries and bounded close/quarantine are allowed.
No credential contents are read, hashed, copied or logged.

Proposed next approval is limited to this access-mask addition for the existing
five fixed credential/runtime lifetime handles listed above, OFFLINE implementation and
synthetic validation only. Keep strict private_acl, runtime group limits,
whole-lifetime identity/ACL checks, no-delete behavior, job settlement, durable
single-send/no-replay and all existing deadlines. Failure or unknown state holds.
Test actual ReadFile/write rejection, rename/replacement denial, ACL/identity
drift, cancellation/crash cleanup and unchanged CLI in-place-write compatibility
on synthetic data. Unknown behavior or broader access needs new approval.

Actual existing-file use, ACL repair, auth refresh, real inference, services,
main and Loop remain excluded. This document is not a live permit or an adopted
mask. Independent read-only security review precedes requesting owner approval.

The implementation must require a separately registered lease-approval digest
in the exact profile/permit binding before using 0x200a0. Do not enable this
access automatically for an old existing-file profile or from CLI/model input.
