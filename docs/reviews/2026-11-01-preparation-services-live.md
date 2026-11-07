# Preparation services: actual deployment evidence

2026-11-01. The owner executed the completion helper and returned installed=true,
mode=prepare, activated=false. This records actual preparation, not activation.

- Deployed artifact: `096969dfcf253cfc94620787bc5668e28c960dbc1a3a6f613388759d81413cb5`,
  runtime source commit `57d4b5c124d4628d89fd9d98b253eda88b57e552`.
- Completion helper manifest: `299c6acd4e5a4eece0343387fb6017850681d1fee1df017f2228bc9f454ab13a`,
  helper source commit `2e0676ced8cc3e9e327e55d66b76092228fc1611`.
- Both services are Running/Manual under distinct standard service accounts,
  with the exact sealed Python -I -B bootstrap/role/artifact command line.
- Read-only SCM inspection verified SYSTEM ownership and exact explicit Sys/Admin
  full-control plus operator query/start/stop/interrogate/read-control rights.
  Normal operator handles for change-config, delete, write-DACL and write-owner
  were separately denied; the probes did not invoke those mutations.
- Actual SID-authenticated health proved the other role's state unreadable,
  sealed source append denied and other-role credential target absent.
- Existing operator keys were transferred in memory/pipe to each service's own
  Windows Credential Manager. Both exact App installations authenticated with
  their approved permissions and Locus-only repository scope. No PEM or token
  was printed or written to a plaintext file.
- Each service was stopped and started using only the operator's limited SCM
  rights. Subsequent health showed both keys present, and verify authenticated
  both Apps without resending the key. Original import intents remain; they are
  not removed to enable replay.
- Merge service policy observation read actual main/protection/rulesets. Policy
  hash remained `e37a664d670cc41dad153a1019c53429079fdb6a9ea590bff12e711485744144`.
  Missing dedicated review/writer rules remain reported; merge authorization
  and atomic-base binding remain false. No remote mutation was performed.

Legacy operator vault and GitHub Secrets copies are retained, not represented as
retired. Review-service-to-Merge policy transport, protected evidence authority,
production publication/merge routes, Controller connection, approved migration,
live writer/crash/revocation/full-cycle proofs and final deployment audit remain.
The product loop and automatic merge have not started.

## Permanent read-only observation changes

ServiceClient now checks SCM registration before each pipe request, including
the exact owner/ACL/configuration and denied mutation-handle probes. The elapsed
inspection time is deducted from the original RPC window. A cancelled request
does not inspect or connect. These local SCM reads do not claim a transaction
against a concurrent administrator; administrative maintenance must be exclusive.
Initial source review identified synchronous SCM calls as non-interruptible by
the caller's deadline. Inspection now runs in an owned child process/job with a
maximum 15-second window, bounded by the caller's remaining time and cancellation.
Timeout/cancellation rejects even a partial successful-looking result and does
not proceed to IPC. Child arguments contain only fixed role/artifact identity;
no credentials or owner OAuth are passed.

activation-readiness --live uses only fixed health/verify/policy service methods
for App evidence; it no longer reads the operator App vault. Owner gh performs
only a fixed PR number/base/native-auto-merge read outside the services.
SQLite remains mode=ro. The new preparation gate does not enable production
signing, approval, migration, Controller startup or merge.

The original read-only readiness prose said no isolated service was connected.
That became stale after deployment; the implementation now distinguishes verified
prepare services from unavailable production signing authority. Frozen runtime
Goal/base/Development settings are still unchanged and require approved migration.

## Observation implementation audit and verification

Fresh read-only `service_observation_audit` initial review identified only the
non-interruptible SCM read limitation. Fix/re-review cycle1 accepted the owned-job
inspection change with no new blocking findings. One of two allowed cycles used
for this new observation scope. Earlier preparation/recovery scopes remain closed.
Reviewer inspected source/tests/docs only, without execution, network, credentials,
deployed-state access or edits. Reported live tests are implementer/owner evidence.
Per-agent usage/elapsed telemetry and technical reviewer sandbox are unavailable.

Final local `scripts/verify_loop.py --audit` passed307 tests with7 explicit skips
(six opt-in Docker tests, one Windows symlink privilege case), Ruff, native and
Python3.11/Linux strict types, zero offline secret findings, dependency consistency
and no known third-party advisory findings. The unpublished local package is not
in PyPI advisory lookup. Focused observation/readiness/preparation42 tests passed.
Tests cover per-field registration denial, cancellation before IO, reduced RPC
window, owned timeout/cancellation despite zero returncode, strict boolean response,
fixed owner gh read and no owner App-vault access. Preparation proof still cannot
approve production gates. Read-only live assessment showed preparation passed
while signing, Controller, migration, writer proofs and final activation remained
blocked. No review check, approval, branch protection, lock or merge was changed.
