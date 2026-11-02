# Windows CI startup investigation — 2026-11-02

Implementation run 41344254345 failed Windows3.13 in three legacy audit PowerShell
fixtures (20-second timeouts). Migration run 41402041723 failed Windows3.11 in
`test_actual_installer_feature_guard_accepts_fixed_versioned_features`, also at
20 seconds; 450 other cases passed and six were skipped. Product quality and
Ubuntu3.11/3.13 succeeded. Existing logs did not identify the point inside native
startup at which time was consumed, so a code-level cause is not proven.

The other Windows job was cancelled immediately after the failing matrix job.
The workflow has no `needs` dependency between matrix entries and leaves the
matrix's fail-fast behavior enabled. This is matrix cancellation, not a Python
version dependency. No matrix entry or required check is removed.

## Classification

| Test surface | local_commit_push runtime prerequisite? | Coverage retained |
| --- | --- | --- |
| Audit installer versioned feature guard | No; legacy dedicated-service setup | Protects valid feature allowlist/recovery behavior |
| Protected audit-state diagnostic field filtering | No; legacy service diagnostics | Protects nonsecret output and credential filename denial |
| Audit upgrade .NET File.Replace binding | No; legacy service upgrade | Prevents the earlier PowerShell null-backup binding regression |
| Core ProcessRunner Job containment, cancellation, output bounds | Yes; used by Git, native client and QA | Must remain mandatory for the normal path |

Legacy surfaces remain regression coverage while their implementation remains
in the repository. Optional runtime use is not permission to delete/skip tests.

## Minimal setup/diagnostic change

The hosted workflow uses `pwsh`, while these tests intentionally use Windows
PowerShell5.1 `powershell.exe`. Verification now initializes that existing runtime
once through the same ProcessRunner, records cold startup (maximum45s) and
requires a warm startup within the tests' existing20s allowance. Both checks
must exit successfully and print the exact synthetic readiness marker; failure
stops verification. This is bounded setup and added evidence, not a test retry.

Every existing20s script timeout, assertion, test and matrix/check/job limit is
unchanged. Failed-test messages now retain the synthetic ProcessResult so
elapsed/outcome information is visible. Local observed startup was0.892s cold
and0.802s warm; related PowerShell/process tests passed. Hosted evidence after
Push is required before claiming this setup resolves the observed failures.
If hosted failures persist after setup, investigate them rather than silently
increasing test deadlines or accepting a failure as success.

See [startup repair](LOCAL_LOOP_STARTUP_REPAIR.md) for independent model/QA gates.
