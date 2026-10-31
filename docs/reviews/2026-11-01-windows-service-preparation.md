# Windows service preparation review

Scope: isolated prepare-only service runtime, Windows pipe authentication,
credential import, fixed policy observation, pinned bundle and administrator
installer, CLI and deployment documentation. No product implementation.

The fresh read-only `windows_services_preparation_audit` reviewer found no
confirmed source blocker in the initial security/architecture review. One
re-review confirmed the added Native attribute type declarations and eleven
line-specific public artifact hash scanner annotations, with no scanner-wide
exclusion. Documentation distinguishes preparation, deployment proof and
activation. Findings: none. One of two allowed fix/re-review cycles used.
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

This is source/preparation evidence only. No administrator installer was run,
no accounts/services were created, no keys transferred and no remote policy,
review or merge was changed by this preparation work. Cross-SID communication,
SCM execution/stop, deployed filesystem denial and vault persistence still need
real deployment. Production authority, Controller delivery wiring, migration,
live race/recovery proofs and final approval remain separate gates.
