# Read-only runtime ACL and fixed credential lifetime: offline result

2026-11-04. Scope: existing Controller, Arg0Guard and C-min adapter only.
No actual profile ACL, authentication, inference, service, main or Loop operation.

## Approval and implementation

The three-object runtime alternative is the frozen proposal
`e100391c12ca9bb434fb817a5a3999ea5e7e489316d12df6382c5f1f107ea000`.
The owner separately approved the no-delete sharing-class addendum
`4adfaee16009ab0c9112ef0e974d3243b338013e8a910d4eba16cf1f3e0307c4`.
Its file hash was checked before adoption.

`private_acl` remains unchanged. `runtime_acl.py` admits only the registered local
CodexSandboxUsers alias, read-only runtime masks, assessed paths and a protected,
non-inheriting home RX grant. Credential/config files never use this exception.

CredentialLease uses exactly the existing home/auth/config/tmp/arg0-base handles,
access 0x200a0, share 3. The explicit `lease_approval` digest is required before
opening; old profiles cannot acquire this capability implicitly. The complete
profile remains bound by the existing permit fingerprint. No real registration
or permit has been added by this work.

Handles expose neither FILE_READ_DATA nor writing/deletion/ACL mutation rights.
The additional bit is FILE_EXECUTE for files and FILE_TRAVERSE for directories;
code never executes, maps or transfers these handles. Query failures, identity,
ACL, path or content-metadata changes permanently invalidate the lease.

The existing ProcessRunner optionally proves the contained Windows job is empty
before release, terminating descendants and bounding cleanup. Unknown settlement
quarantines retained handles and prevents another lease in this process. Durable
invocation holding and existing single-send/no-replay remain authoritative across
restart. No new executor or general retry/reset path is introduced.

## Verification evidence

- Native runtime/lease suite: 44 passed, including explicit nonzero process exit
  and timeout cleanup. Actual Win32 ReadFile/WriteFile fail with
  access denied on all five retained handles; rename fails on all five paths.
- Adapter suite: 48 passed. Existing input contracts remain covered; added leased
  v3 success, malformed input, disconnect, response/source changes, lifetime drift,
  unknown settlement and re-entry cases do not permit a second launch/send.
- Independent final security re-review: the reviewer separately ran both suites,
  90 passed in 11.75 seconds; no unresolved critical/high finding. The initial
  sharing-mask, spawn-error settlement and adapter-coverage findings are resolved.
  Review history: initial review and two bounded re-review cycles; no further
  silent fix/review cycle is authorized by this report.
- `python scripts/verify_loop.py --audit`: passed, including lint/format, both
  type-check configurations, 875 passed / 7 skipped in 434.97 seconds, secret
  scan, dependency consistency and advisory audit. The seven skips remain
  unverified capabilities. This full run collected before four additional native
  test cases were added; the final 44-case native suite passed separately. Counts
  overlap and must not be summed. The local package is not on PyPI and cannot be
  audited there; installed third-party dependency audit reported no known issue.
- Existing official pinned CLI mock-only conformance: 6 passed in 33.92 seconds,
  including two validating launches against the same prefrozen input contract.
- Exact-commit GitHub CI is still a separate publication gate; local success
  does not establish hosted Windows CI or live readiness.

Fresh synthetic PATH batch shims remain readable through a restricted synthetic
group token while auth/config are unreadable. Recreated credentials inherit only
trusted grants; old registered IDs remain rejected even after restoring the exact
approved ACL. Invalid rights, inheritance, SID, path and owner changes fail closed.

The cached pinned official FileAuthStorage source uses create/write/truncate and
flush on the same auth.json. A synthetic in-place write succeeds with the lease
held, preserves ID/private ACL, and then invalidates admission because metadata
changed. This is source-level storage compatibility plus a kernel test, not an
actual ChatGPT refresh or a claim that every official CLI auth lifecycle ran.
Existing native mock-only CLI conformance remains a separate test prerequisite.

## Actual application: still requires owner approval

Only three actual objects may be proposed: existing auth.json and config.toml
receive protected trusted-only DACLs; .codex retains the exact Sandbox RX grant
with no inheritance. Do not change tmp/arg0 or other child descriptors, owner,
contents, accounts or credentials. The five-handle approval is not approval to
modify five ACLs.

Before any future actual application, recheck current nonsecret descriptors,
owner, file IDs, links/reparse/fixed-drive conditions against a fresh owner-approved
snapshot. Record metadata-only before/after evidence and use the already reviewed
non-propagating directory procedure. If snapshots drift, fail before writing.
On partial failure preserve state; restore only matching identities/descriptors
from the exact snapshot. Never blindly rerun or restore onto replacements.

The owner must separately approve that concrete actual three-object change and
its recovery conditions. Actual profile registration, auth lifecycle/refresh,
new single-shot permit, real inference and Loop startup remain separate gates.

## Residual risks and documentation reconciliation

The old metadata-only wording and five-object private-directory repair in the
frozen original proposal are historical alternatives. The subsequently approved
three-object alternative and sharing-mask addendum supersede those parts only;
the frozen source documents were not rewritten.

The disclosed execute/traverse bit is a retained internal capability. Metadata
polling does not protect against a malicious same-user process or administrator
making transient ACL/content changes between observations. The trusted pinned
CLI/process assumption remains. Other existing .codex runtime children can remain
group-readable; this is not a claim that all of .codex is confidential.

In-place auth refresh changes metadata and must HOLD; it is never silently
adopted or retried. Truncate-before-write can leave incomplete data after a crash;
no agent credential backup/restore or real recovery is authorized. Offline
capability approval cannot satisfy real-account network/lifecycle authorization.
