# Windows service preparation review

Scope: isolated prepare-only service runtime, Windows pipe authentication,
credential import, fixed policy observation, pinned bundle and administrator
installer, CLI and deployment documentation. No product implementation.

The fresh read-only `windows_services_preparation_audit` reviewer found no
confirmed source blocker in the initial security/architecture review. One
re-review confirmed the added Native attribute type declarations and eleven
line-specific public artifact hash scanner annotations, with no scanner-wide
exclusion. Documentation distinguishes preparation, deployment proof and
activation. A second cycle accepted the subsequent POSIX path conversion fix
and parametrized fixed-path/denial regression with no findings. No further fix/re-review cycles
are available for this scope.
No implementation agent was delegated. Reviewer did not execute tests, services,
installer, network requests or access credentials. Per-agent usage/elapsed
telemetry is unavailable; no technical read-only sandbox is asserted.

Implementer verification:

- `scripts/verify_loop.py --audit`: passed lint/format, native and Python3.11/Linux
  type analysis; 255 tests passed, 7 skipped. Skips: six opt-in Docker cases and
  one Windows account symlink privilege case. Offline secret scan: zero findings.
  Dependency consistency passed; no known advisory findings. The unpublished
  local engine package is outside PyPI lookup and is not certified by that audit.
- Actual same-user Windows kernel tests exercised pipe owner, full ACL,
  authenticated peer, roundtrip, denial, timeout and cancellation.
- Official SHA-pinned embedded Python 3.14.10 executed isolated imports and a
  synthetic in-memory RSA/JWT plus same-user kernel pipe roundtrip. No real key
  or token was used in that smoke probe.
- PowerShell syntax parsing and C# compilation tests passed without invoking
  account, profile, ACL or service installation methods.

Initial verification exposed missing Linux/Python3.11 inferred ctypes attribute
types, then scanner false positives on public artifact digests. Explicit types
and narrowly scoped public-digest annotations fixed them. CI/test assertions,
scanner inventory and dependency controls were preserved.

Remote Ubuntu CI then exposed `PureWindowsPath(Path(...))` interpreting POSIX
parts as drive-relative. Converting the fixed path to its string first preserves
Windows absolute semantics on both hosts. All original allow/deny assertions now
also run with a synthetic PurePosixPath inventory. The focused suite passed
21 cases after this correction. Earlier bundles are superseded and must not be
deployed; generate the bundle from the corrected clean commit.

## First administrator deployment feedback

The owner attempted the corrected bundle; it stopped at package_validation.
Read-only reproduction identified the built-in LocalAccounts manifest under
the fixed `1.0.0.0` subdirectory. The helper now uses that explicit System32
module path. A non-admin probe of all package validation steps passed after
the correction; the fixed built-in module import has an actual Windows test.
The deployment root was absent when inspected after the failure. No installer
state was deleted and no key was read during diagnosis.

This compatibility correction occurred after the two source re-review cycles.
It is not represented as independently re-reviewed. No third cycle was requested;
the final deployed-system audit and all activation/merge gates remain required.

At the initial source review this was preparation evidence only. No administrator installer was run,
no accounts/services were created, no keys transferred and no remote policy,
review or merge was changed by this preparation work. Cross-SID communication,
SCM execution/stop, deployed filesystem denial and vault persistence still need
real deployment. Production authority, Controller delivery wiring, migration,
live race/recovery proofs and final approval remain separate gates.

## Subsequent accounts-stage failure

The owner ran the replacement bundle and reported accounts/setup_failed.
Non-admin inspection found the deployment root and Review account, but no Merge
account, either service or Review profile registration. The original installer
was not re-run, no partial state was deleted, no password reset was attempted
and no key was accessed. Public-only C# entry-point resolution and PowerShell
SID/credential-construction probes succeeded without invoking identity changes.
Non-admin LSA rights enumeration returned access denied; the exact failed
identity setup API is still undetermined. A separate read-only account diagnostic
was added; it does not constitute a third source re-review or activation proof.
