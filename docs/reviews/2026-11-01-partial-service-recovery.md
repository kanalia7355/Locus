# Partial service installation recovery audit

Scope: new explicit recovery of the accounts-stage partial preparation, exact
old-manifest/Review-SID binding, never-used-account adoption, password rotation,
durable no-replay intent and preservation of old deployment bytes and ACLs.
The original preparation source review exhausted its two re-review cycles and
was not reopened. This is not a final deployed-system audit or activation approval.

Owner-provided administrator diagnostic confirms all three approved logon rights
on Review, no profile registration and no Merge account. Non-admin observations
found no dedicated services, no Review profile and no local group membership.
The original CreateProfile HRESULT was lost; the precise underlying OS error is
not asserted. SCM profile loading replaces the unnecessary manual profile call,
following [Microsoft's service account specification](https://learn.microsoft.com/en-us/windows/win32/services/service-user-accounts).

The fresh read-only `partial_service_recovery_audit` reviewer initially identified:

- Medium: profile/service/group facts were not re-read at the rotation boundary.
  A shared guard now re-reads them immediately before rotation. Exclusive
  administrator maintenance is an explicit prerequisite; no transaction against
  a concurrent administrator is claimed.
- Low: extra empty directories were not rejected. Exact directory inventory is
  now derived from the old manifest's paths and compared with actual contents.
- Test limitation: initial predicate tests did not exercise complete preflight.
  Added synthetic inventory scenarios use real file hashing and expected failure
  reasons, including prior intent, unknown contents, used identity and changed pins.

Fix/re-review cycle 1 accepted both corrections with no new blocking findings.
One of the two allowed recovery fix cycles was used. Reviewer inspected source,
tests and docs only; no execution, network, services, keys, state changes or
implementation delegation. Agent usage/elapsed telemetry and a technical read-only
sandbox are unavailable. Test evidence below was executed by the implementer.

Focused preparation/recovery suite: 48 passed. This includes actual PowerShell
syntax/C# compilation and pure guard execution, user-owned ACL rejection, plus
full preflight against synthetic files with OS account/ACL/registry/CIM queries
mocked. A separate non-admin read-only lookup verified that a missing Merge
account is handled by the native LocalAccounts error contract.

Final `scripts/verify_loop.py --audit` passed: Ruff lint/format, native strict
types, Python3.11/Linux strict types, 283 tests passed and 7 explicit skips
(six opt-in Docker tests and one Windows symlink privilege case), offline
secret scan zero findings, dependency consistency and no known third-party
advisory findings. The unpublished local package is outside PyPI advisory
lookup and is not certified. The refreshed source-bound zero-tool/container-QA/
timeout probe passed; its merge_authorized remains false.

These tests do not execute password reset, account creation, protected intent
creation/crash recovery, actual SCM startup, profile creation or vault persistence.
The prepared recovery has not yet been executed by the owner. All live deployment,
Controller, migration, merge proofs and final activation gates remain held.

## Services-stage completion — final recovery cycle 2

The owner ran the earlier partial recovery. It reached services after creating
both accounts and the sealed runtime/settings/state. No dedicated service was
present on read-only inspection; both LastLogon values remained null.

The credential bug was reproduced in actual Windows PowerShell with a synthetic
SecureString: the previous New-Object expression returns PSCredential type but
UserName is null. The earlier type-only test was insufficient. Explicit
PSCredential::new now preserves the username, tested for both roles and both
installation paths without real credentials or service creation.

The helper-only completion bundle uses immutable same-commit shared functions,
native definitions and a completion template. Its new manifest pins the existing
active artifact and both SIDs. The helper validates existing ACL policies,
inventories, exact roles, canary-only state and prior intent before exclusively
creating a new durable completion intent. It rechecks each unused identity before
SID-only rotation and registers services using the existing artifact. It changes
no prior runtime, settings, state or intent bytes/ACLs. The existing runtime source
commit is not relabelled as the new helper source commit.

Final source-only re-review cycle 2 accepted the correction and completion path
with no blocking findings. Both recovery fix/re-review cycles are now exhausted.
The reviewer did not execute tests, inspect deployed state or access credentials.
The original preparation review remains closed; no activation is approved.

Implementer verification: 54 focused tests passed, including 17 completion
preflight scenarios batched in a synthetic fixture run with exact failure reasons
and per-path ACL policies. Generated-helper parsing and sanitized diagnostics
exclude an opaque exception-message sentinel and retain native code5. Final
engine verifier/audit passed 289 tests with the same seven explicit skips,
Ruff, native/Python3.11 typing, zero secret findings, dependency consistency and
no known advisory findings (unpublished local engine is not in PyPI lookup).

A non-admin read-only probe on the real active deployment validated its public
sealed files/ACLs and identity predicates, then stopped at the expected protected
old intent boundary. No rotation, service creation/start or key transfer occurred
in that probe. Actual administrator completion, SCM/profile and vault persistence
remain unverified. Windows QA image audit freshness expired during this work;
the trusted manifest-only image build was re-run successfully for the new UTC day,
without changing dependencies or substituting a timestamp-only receipt refresh.
