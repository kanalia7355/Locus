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

## Settings switch completion

Owner's first upgrade execution stopped at settings_and_binary. Read-only public
metadata showed old settings and SCM path unchanged, the new sealed runtime,
staged settings, backup and reconciliation permit already present, and Audit
stopped. The operator started the matching old service using its existing SCM
rights; all three services are Running again. No authentication/model operation
was retried and private state was not changed.

Windows PowerShell5.1 synthetic reproduction established that File.Replace's
third string argument receives an empty path when passed ordinary PowerShell
`$null`, causing ArgumentException. The actual upgrade statement now passes
`[System.Management.Automation.Language.NullString]::Value`; real synthetic file
replacement passed. Syntax/native compilation alone had not exercised this call.

A completion-only helper binds old/new settings hashes, existing backup/permit,
original upgrade intent, exact audit identity/SCM registration and every already
installed new runtime file plus protected ACLs. It records its own exclusive
intent, stops Audit, replaces settings with the corrected statement, switches only
the Audit binary path and restarts. It cannot recopy code, recreate accounts,
rotate passwords, modify authentication or replay either intent. Existing App
services and credentials remain preserved. Failure includes bounded inner
exception type/HRESULT diagnostics rather than arbitrary messages.

Fix/re-review cycle1 in the same task scope passed with no findings. Three
additional tests passed: completion boundary, actual Windows PowerShell5.1 .NET
replacement and generated completion PowerShell/native compilation without
privileged execution. Actual completion and live reconciliation remain pending.

After this correction, full `scripts/verify_loop.py --audit` passed 423 tests
with the same 7 skips, lint/format, both type checks, secret scanning, dependency
consistency and advisory checks. The local package remains outside PyPI lookup.
