# Audit preparation installation recovery

Owner reported `stage=audit_account`, `installed=false`, `activated=false` for
the first audit package. Read-only operator observation found the new enabled
audit SID, no LastLogon and no audit SCM registration. Both existing App services
remain Running. Private deployment contents are inaccessible to the operator;
their exact partial state has not been assumed verified.

Deterministic source reproduction: the installed PowerShell validator
`^[a-z_]+$` rejects the approved `responses_websockets_v2` entry. This branch
runs after creating the new account and empty workspace, before any authentication
profile. Previous syntax/native compilation checks did not exercise it.

Fix: accept safe versioned names and validate the complete fixed list before
mutation. Execute the actual guard in PowerShell for all approved features and
unsafe-name rejection. Add granular stages and exception type/HRESULT only,
without raw exception messages, secrets or transcripts.

The completion helper preserves the original sealed runtime and manifest. Its
read-only guards require the exact private namespace, installed inventory/ACLs,
unused pinned SID, no registered/disk profile, no service/group use, exact three
expected LSA rights and state containing only an empty workspace. Missing or
different state stops before mutation. It writes a new exclusive completion
intent before regenerating only the lost service password of that unused audit
account. It then performs the missing profile/settings/service preparation.
It cannot delete/reset existing authentication, recreate the account, copy a new
runtime or replay an existing completion intent. Existing App services are checked
and preserved. Actual administrator completion remains required and unverified.

Independent read-only implementation review: correction/re-review cycle1 passed
without findings. Final cycle2 passed without findings, including the additional
per-artifact private ACL validation before packaging. This is the same deployment review scope; review
budgets are not reset. A local audit report does not publish a GitHub approval.

Local verification: 407 tests passed, 7 skipped for the existing Windows symlink
privilege / opt-in live Docker conditions. Lint, formatting, native and Python3.11
Linux type checks, secret scanning and dependency consistency passed. These do
not prove the still-private installed partial state or administrator completion.
