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

## Hosted follow-up and next bounded diagnostic

Run41405792339 at c85c552 still failed the same three tests on Windows3.13;
Windows3.11 was cancelled. PowerShell preflight itself passed: cold2.367s,
warm0.230s. The failing results had empty stdout/stderr and elapsed20.02–20.037s.
This disproves simple interpreter cold startup as a sufficient explanation;
the setup change alone is not reported as a fix.

The next small diagnostic preserves the same PowerShell5.1 executable, actual
generated script files, assertions and20s deadline. It invokes each file with
the call operator through `-Command` instead of the ConsoleHost `-File` entry,
quotes every file/argument as a PowerShell literal, and emits fixed synthetic
stderr markers on host entry and script entry. These markers distinguish process
startup, file dispatch and script-body stalls without displaying protected state.
The three related test modules passed locally (seven cases,8.71s). Hosted results
are still required; no failure is retried into success or silently ignored.

Run41407174718 at b55692f again failed the three Windows3.13 cases. Both host
and script-entry markers appeared before each20s timeout. Thus startup and file
dispatch completed; changing the entry did not fix the failure. Windows3.11 was
cancelled by fail-fast again. The three script bodies first use standard Utility
or Management cmdlets, while the startup probe uses only .NET Console methods.

The next bounded check loads Utility/Management explicitly from the running
Windows PowerShell's `$PSHOME\Modules` and confines `PSModulePath` to that system
directory **inside each synthetic test process only**. Import-start/import-ready
markers separate module resolution from script execution. This pins the required
5.1 module implementation instead of relying on mixed installed-version/user
module discovery. It does not change ProcessRunner's environment whitelist,
machine/user environment, execution policy, production scripts, test deadlines
or existing assertions. An additional assertion requires the import-ready marker.
All seven related cases passed locally in8.91s; hosted validation is pending.

Run41408474025 at ac39bc7 passed those three initialized invocations. Its sole
Windows3.11 failure was the oversized-record negative case later in the diagnostic
test, which still used the original uninitialized `-File` invocation. It timed out
after script entry; 480 other cases passed and six were skipped. This separates
the synthetic test's module environment from interpreter startup/file dispatch.

The diagnostic test now reuses its initialized command for both positive and
oversized-record cases. The wrapper explicitly propagates the script's native
exit code; parent error handling remains terminating. The negative case still
requires exit2, bounded nonsecret diagnostics and byte-for-byte unchanged fixture
files, and now additionally requires a normal process exit and the module-ready
marker. Its20s deadline is unchanged. Local regression passed in3.14s; final
hosted results must be observed separately before claiming all CI green.
