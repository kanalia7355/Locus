# Held audit authentication — bounded recovery task

Owner's corrected read-only diagnostic confirmed real-home lifecycle active_use,
original synthetic trial started, completed keyring probe and cleared probe login.
Both profile ciphertext files exist; plaintext auth files and unexpected secret
artifacts are absent. The diagnostic's provider_request_sent=false describes that
diagnostic only. It does not establish whether the original inference reached or
completed at the provider. Original failure cause remains unknown.

This task does not replay or reset the old trial. A SYSTEM-sealed owner permit
binds its exact record hash, the exact active authentication record hash and the
old/new audit artifacts. The dedicated audit identity checks existing key-header
metadata, ciphertext envelope, lifecycle and unchanged protected model profile.
It records an exclusive status intent containing the prior nonsecret record before
calling only a bounded fresh CLI login status. Only ChatGPT success plus matching
post-call records/key metadata permits changing active_use to enrolled. Unknown
state, failed status or an existing intent stops without retry. No key, ciphertext,
password or original trial is deleted/replaced. The original record is preserved
inside the append-only reconciliation intent before its lifecycle phase changes.

A separately permitted diagnostic validation task has its own single persistent
intent, which cannot be replayed across artifact updates. It uses only the fixed
synthetic authorization fixture. Failure emits/stores a closed stage/reason/HTTP
status triple; no exception message, token, provider body or raw CLI output is
exposed. Success is labelled diagnostic_only and cannot complete the original
uncertain trial or publish a review/check. Controller budgets are unchanged.

The audit-only upgrade adds a sealed new runtime and backs up old settings. It
preserves the existing account, SCM credential, encrypted-login location, keyring,
profile config, old catalog/log policy, old runtime, private state and all App
services. New source inventory is independently leased/verified. Prior profile
manifest and identical CLI/model/reasoning/tool policy are required. SCM changes
only the audit binary path: null account/password parameters preserve existing
credentials as documented by [ChangeServiceConfigW](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/nf-winsvc-changeserviceconfigw).
There is no account creation, password rotation, auth cleanup or automatic replay.

Independent read-only security/architecture review: TASK-000, pass, no findings,
initial review, no fix/re-review cycle. Reviewer inspected source/diff and supplied
test evidence, without modifying files, accessing deployed state/credentials,
network or privileged operations. This is a new bounded failure-recovery task;
prior deployment review budgets and trial histories are not reset. Review does
not certify live reconciliation, provider behavior, deployment or activation.

Related synthetic tests: 12 passed, covering exact hash/identity/key guards,
failed-status hold/no retry, separate diagnostic once-only behavior/original trial
preservation, sanitized upstream403/timeout handling, credential-preserving SCM
arguments and generated PowerShell/native compilation without privileged execution.
Full verification and concrete administrator package validation are recorded
separately. No new runtime or reconciliation has been deployed/executed yet.

Full local `scripts/verify_loop.py --audit` subsequently passed: lint/format,
native and Python3.11 Linux types, 420 tests, secret scan, dependency consistency
and dependency advisory checks. Seven tests skipped for the existing Windows
symlink privilege and opt-in live Docker conditions. The unpublished project
itself has no PyPI advisory record. These tests do not certify live deployment.
