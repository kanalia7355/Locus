# Real audit model trial held — not a successful live review

Owner completed private device enrolment and returned authenticated=true,
activated=false. The authenticated service auth_status independently confirmed
ChatGPT authentication. No device code or token was collected by the agent.

The fixed synthetic self_test was invoked once. It returned the sanitized
service_operation_failed result. No model findings, upstream HTTP status or raw
CLI error is available; neither provider completion nor defect detection is
claimed. Whether a provider request completed is unknown. No review/check or
merge was published. The self-test has not been replayed and its intent has not
been reset. Subsequent auth_status was held; health continued to prove the
existing isolation and account crash-reporting controls.

The deployed worker hides all arbitrary errors and provides no stage diagnostic
for this path. The operator is correctly denied private service-state access.
A separate administrator read-only diagnostic is therefore prepared: four fixed
nonsecret lifecycle/intent records, bounded reads, finite phase/hash output and
profile-directory existence checks only. It never opens ciphertext/auth.json,
keyring values or model output, contacts providers, invokes auth CLI, changes
state/ACLs or restarts services. Original trial and authentication remain held
pending evidence-based reconciliation rather than blind retry.

The actual PowerShell diagnostic body passed a synthetic-namespace test,
including unchanged file snapshots and suppression of extra record fields.
Ruff and secret scanning passed. Independent read-only security review passed
with no findings and no fix/re-review cycle. This review authorizes no mutation
or retry. Actual private lifecycle state remains unverified until owner execution.

## Diagnostic correction

Owner execution of the first diagnostic returned MethodInvocationException,
HRESULT 0x80131501. No stage or inner error was available, so the exact cause
remains unconfirmed. Source inspection shows service-created lifecycle files
inherit only the audit Modify ACE: SYSTEM/Administrators full-control ACEs on
the containing directory do not propagate. Ordinary administrator File.Open may
therefore fail. Do not widen ACLs to compensate.

The corrected reader opens only the same four fixed nonsecret records. On access
denied only, an already elevated administrator may temporarily enable its existing
SeBackupPrivilege, open a read-only backup-semantics handle and restore the prior
token privilege before reading. It rejects reparse/directory handles and changed
final paths, caps reads at 8192 bytes and never opens credential files or stores.
This follows the [Windows backup access mechanism](https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights).
Neither ACLs nor persistent service/authentication state are changed.

Finite stage/record fields and a bounded exception type/HRESULT chain now identify
future failures without exception messages, file contents or traces. Actual
PowerShell/native synthetic tests passed, including credential filename rejection,
oversized record rejection, field filtering and unchanged file snapshots. The
administrator backup fallback itself has not been exercised by the non-admin
agent. Diagnostic fix/re-review cycle1 passed with no findings. Original inference
and authentication holds remain intact; no replay or reset is authorized here.
