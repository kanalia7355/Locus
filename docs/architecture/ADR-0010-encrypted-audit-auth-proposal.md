# ADR 0010 — Restricted encrypted audit authentication cache

Status: ACCEPTED for implementation by owner reply on 2026-11-01. Deployment and
real enrolment still require audited implementation and isolation validation.
Automatic merge permission has already been granted; this is a
separate exception to the owner's prohibition on token files.

## Observed incompatibility

ADR0009 selected a dedicated keyless audit identity with Codex authentication
stored directly in Windows Credential Manager. Installed Codex 0.166.0 serializes
the complete authentication record into one keyring password. Its Windows backend
rejects large records. Synthetic invalid strings of 1,536, 3,072 and 6,144 characters
failed; a short synthetic string succeeded. The CLI reported the platform password
encoding size limit. These tests used new isolated diagnostic homes, never existing
operator credentials. No real OAuth record was inspected or measured. Therefore
small-key success does not establish OAuth enrolment readiness.

The same-version public source implements a standard encrypted backend when
`cli_auth_credentials_store="keyring"` and `features.secret_auth_storage=true`.
It generates a random 32-byte passphrase, stores its base64 encoding in the OS
keyring, encrypts the serialized record with age before writing, and writes only
ciphertext to temporary/replacement files. Keyring write failure returns an error.
Windows replacement can remove the old ciphertext before rename; interrupted
replacement must hold for reconciliation rather than assert authentication success.

An isolated synthetic-only test of this backend saved a 6,144-character invalid
value, loaded it from a fresh CLI process and logged out successfully. The file
had an age header, no `auth.json` existed, and generated files did not contain the
synthetic plaintext. This is compatibility evidence under the operator's isolated
diagnostic profile, not audit-account deployment, real login or cryptographic audit.

Source: [Codex authentication storage](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/login/src/auth/storage.rs)
and [local secrets backend](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/secrets/src/local.rs).

## Proposed narrow exception

Permit only the dedicated audit account's pinned Codex CLI to persist its own
model authentication in `C:\ProgramData\LocusLoopAuditV1\state\home\secrets\codex_auth.age`.
Its sibling temporary files may contain ciphertext only. The OS keyring stores the
encryption passphrase. Do not export it or copy the operator's existing login.
Plaintext `auth.json`, token logs, environment/command-line tokens, Git/CI token
files and API-key fallback remain prohibited. GitHub App keys retain their existing
separate OS-only storage; this exception does not apply to them.

The secrets directory must inherit the protected private state ACL: SYSTEM and
Administrators full control, audit identity required file mutation rights, no
operator/Review/Merge access. Authentication does not defend against compromised
audit-identity code or an administrator; executable integrity and zero-tool model
execution remain mandatory. The model workspace, configuration and logging
directories remain read-only. Only the secrets directory and pre-existing nonsecret
lock/installation files get narrowly required writes. Do not make the whole home
writable. Do not add a custom cipher, OAuth client or token refresh implementation.

Before real enrolment: verify directory owner/ACL/reparse denial, ciphertext-only
temporary files, oversized synthetic save/load/logout under the actual audit SID,
plaintext-file absence, crash/telemetry controls, cross-role denial and restart
reconciliation. Pin backend selection for login, status, logout and inference;
never fall back to direct/file storage. Unknown backend, leftover plaintext, failed
cleanup or missing key/ciphertext holds activation. Never delete uncertain existing
authentication automatically. Revalidate after enrolment without displaying tokens.

Before invoking any authentication CLI operation (including status), use a protected
nonsecret lifecycle record and nonsecret existence/identity checks to distinguish
pristine, synthetic-probe, enrolling and previously enrolled profiles. The backend
can create a missing key during load; CLI save/logout can delete old authentication.
Therefore unexpected plaintext, orphan ciphertext temporary files, missing or
mismatched key/ciphertext, or interrupted lifecycle must stop before CLI invocation.
Do not regenerate keys, replace authentication, delete uncertain files or run
cleanup/logout against an uncertain profile. Even an empty profile is not pristine
when its lifecycle record says enrolled. Key presence checks must not export its
value. Require fault-injection tests of these states before real enrolment, with
explicit reconciliation rather than automatic retry. Synthetic cleanup is allowed
only for the exact known probe identity whose successful write is established.

## Alternatives and decision boundary

Keep the no-token-file rule: design a separate bounded/chunked OS credential
adapter compatible with the pinned CLI. This is additional security architecture,
not an existing supported configuration; its implementation and recovery semantics
need their own approval and audit. Do not silently implement custom OAuth instead.

Recommended: approve the narrow encrypted-cache exception above. Approval permits
implementation and isolated deployment validation, not bypass of App-bound review,
branch policy, exact-head merge, independent audit or required CI. Existing merge
authorization remains conditional on those gates.

AGENTS.md says: "If a decision materially affects confidentiality, security or
scope, ask first." The owner's instruction forbids storing authentication tokens
in files. Encryption is still file persistence, so explicit owner approval is
required before adopting this proposal for real authentication.
