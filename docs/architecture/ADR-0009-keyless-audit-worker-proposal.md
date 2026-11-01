# ADR 0009 — Keyless audit worker proposal

Status: ACCEPTED for design/implementation by owner reply on2026-11-01.
Authentication storage refinement: owner-approved [ADR0010](ADR-0010-encrypted-audit-auth-proposal.md)
replaces direct OS storage of the entire model login with a standard encrypted
audit-only cache and OS-stored encryption key, because the Windows direct-entry
capacity probe fails. GitHub App key storage and identity separation are unchanged.
Administrator deployment and authentication enrolment require the concrete,
audited package described below; production activation remains separately held.
This does not activate signing, automatic merge or product development.

## Problem established after preparation deployment

Both dedicated App services now run with separate Windows identities and working
Credential Manager keys. Restart/policy/denied-access proofs are recorded in
[the deployment evidence](../reviews/2026-11-01-preparation-services-live.md).
They expose preparation operations only. The production Review service still
needs a fresh independent model review before publishing any check or approval.

The existing Reviewer/CodexRunner runs under the operator's authenticated account.
No authenticated model executor has been provisioned for either service identity.
Sharing that operator's auth cache or executing model/QA processes as the App-key
holder would undermine the intended separation. Credentials in Windows Credential
Manager are available to processes of that same identity; storage alone does not
isolate a signer from a model executor. No service credential or model credential
has been copied as part of this proposal.

ADR0007 approved dedicated App signing/brokering. It did not select a model
execution identity or authorize a new principal holding model credentials.
AGENTS.md requires asking before material confidentiality/security/scope changes,
and the implementation specification forbids automatically finalizing major
architecture changes. The owner approved the dedicated audit account option.
That decision is not implementation evidence or production activation approval.

## Proposed addition

Add one standard Windows account `locus_loop_audit` and a pinned service
`LocusLoopAuditV1`, dedicated to independent read-only audits. No GitHub App is
added; no existing App permissions or repository scope change. PR author remains
the operator's existing gh account.

| Principal | Credential | Allowed work |
| --- | --- | --- |
| Existing operator Controller | Existing gh/Codex authentication | Single implementation, mandatory QA, PR creation, evidence scheduling |
| Review App service | Review App key only | Load protected evidence, request fresh audit, validate binding, publish review/check |
| Merge App service | Merge App key only | Fresh policy, exact-bound broker/lock/merge and reconciliation |
| New audit worker | Its own Codex login in OS credential store | Fresh read-only review of bounded source/evidence packets only |

The new worker must not inherit operator App/gh credentials, read either App vault
or state directory, access Docker's control endpoint, execute repository programs,
accept arbitrary shell/model commands, publish reviews/checks, or mutate GitHub.
It is not an implementation subagent. Its model invocations occur only for the
isolated audit exception already permitted by AGENTS.md, with fresh contexts.

A sealed copy of the verified CLI and policy runs with tools/MCP/apps/subagents
disabled under the existing zero-tool boundary. Code, dependencies, configuration
and service command line are SYSTEM-owned/pinned. Local SID-authenticated IPC
accepts review requests from the Review service; operator access is limited to
preparation health/auth enrolment and approved stop/start. Review service may gain
only SCM query/config-read/read-control metadata rights for the audit and Merge
services, never modification rights. Exact caller/owner/ACL/protocol checks apply.

Review service initiates a nonce-bound request from protected task evidence;
no endpoint accepts an implementer's review JSON or passed=true. Bind Goal/spec,
task/attempt, head, base, policy, mandatory QA, review scope and nonce. Re-read
binding after review before publication. The worker emits schema-validated findings
only and cannot sign success. Controller task/retry/deadline and two-fix-cycle
limits stay unchanged; duplicate/uncertain requests are held rather than replayed.
Transferred source is the approved public-code/synthetic-data scope only, not
research documents or any credential. Controller evidence authority and transport
still require implementation and testing; this proposal does not mark them ready.

### Runner adaptation and bounded packet lifecycle

Do not transplant Reviewer/CodexRunner unchanged. Current Reviewer runs Git to
assemble baseline source, and CodexRunner writes contracts/failure diagnostics
beneath its control root. Trusted Controller/Review-side code must assemble and
revalidate both baseline/current source against exact heads and mandatory QA.
The audit worker receives that canonical packet; it runs neither Git nor source
programs. Build schema contracts from the existing authoritative schemas into the
sealed artifact. Preserve all local schema constraints, including ones omitted
from the provider's transport schema; no writable contract directory in the model
workspace. Use an empty, controlled working directory and ephemeral model sessions.

Initial limits: packet2MiB total, metadata128KiB, at most256 files and128KiB/file;
structured findings256KiB; safe diagnostics8KiB/invocation. Keep existing65,536-byte
IPC frame limits: fixed ordered32KiB chunks, at most64, whole-packet hash and
exclusive nonce reservation; duplicate/out-of-order/truncated input is rejected.
No caller-selected paths, command arguments, models or provider endpoints.

Only trusted audit supervision writes its private spool; model tools have no file
write capability. Hold read handles and hash the same immutable bytes consumed.
At most8 pending packets/32MiB spool; reject new work when full. Settled packet
payloads may be removed within24h after the Review service acknowledges the exact
binding, only under the new worker's generated-artifact namespace and verified
ownership. Unknown outcomes remain held for reconciliation; do not age-delete
their payloads or consume the nonce again. Append-only journals, consumed nonces,
findings and binding metadata survive restart/rollback. Never delete user files or
discard journals to restore an older binary.

No raw CLI stdout/stderr, source packets or authentication transcripts enter
diagnostics. Persist only schema-validated findings and bounded static status/
timing/exit metadata. This project must not collect memory/crash dumps; detect
unsafe configured automatic dump/log collection before enrolment/activation and
hold if it cannot be excluded for the dedicated processes. Do not silently change
global Windows dump or logging policy. OS-managed encrypted Credential Manager
storage remains the approved secret store, not an application token-cache file.

Freeze provider/enrolment origins from reviewed configuration. Packets cannot
choose URLs/proxies or expand egress; remove inherited proxy/token overrides,
disable arbitrary redirects/custom endpoints and test fail-closed behavior.
Actual provider/proxy behavior and log handling must be proven before real login,
not inferred from the present operator's zero-tool receipt.

## Authentication and human work if approved

Use the currently authorized Codex account/login method and model policy; do not
switch to paid API keys or a new provider automatically. The new OS identity gets
its own login session, not a copy of the operator's cache. Force
`cli_auth_credentials_store="keyring"`; unavailable OS storage must fail rather
than fall back to auth.json. Official [OpenAI authentication documentation](https://learn.chatgpt.com/docs/auth#credential-storage)
describes that behavior. It also documents headless device-code login as beta,
requiring account/workspace support. The installed CLI's login help lists
--device-auth, but that does not prove eligibility or service-profile persistence.
Before starting real sign-in, verify effective policy actually selects keyring
and cannot be overridden by a file-store requirement. Do not change system-wide
authentication policy or the operator's existing login to make the test pass.

After code/tests/source audit, prepare one concrete administrator deployment that
adds the audit account and updates service code/permissions while preserving both
existing App accounts, vaults and passwords. It must not rerun the old installers
or rotate already-used App accounts. Existing bytes/configuration are preserved
for explicit rollback; uncertain upgrade phases stop for reconciliation.

The owner may then need one browser/device authorization for the new audit
identity. The local enrolment client shows the verification link/code directly to
the owner, not to a model/chat/log collector. Only an authenticated boolean/status
is returned to the assistant. No token/key values are requested in chat, files,
command arguments or environment handoff. Authentication logs must be inspected
for safe handling before enrolment is enabled; no undocumented secret-log guarantee
is assumed. If keyring/login is unavailable, remain PR-only; no file-cache copy or
silent authentication fallback. No subscription or billing change is authorized.

## Alternatives and tradeoffs

- Existing operator-hosted review relay: fewer setup steps, but shares an OS
  identity and gh credential capability with the implementation Controller.
  It would need additional anti-impersonation/provenance proof before being
  treated as signing authority. Not selected by this proposal.
- Model inside an App-key account: smaller deployment, but model-runtime compromise
  could reach that same user's signing credential. Rejected.
- Retain PR-only operation: no new model principal or login, but no fully
  unattended review/merge claim. Existing implementation/QA/PR work may continue
  within approved scope while merge remains held.

## Required evidence before activation

Prove model-worker denial of both App credentials/state, operator gh/auth stores
and Docker control; prove no credential-cache files/log leakage, actual keyring
authentication/restart persistence, empty tool surface under the new identity,
nonce/source/QA binding, cancellation/job containment, duplicate/failure recovery,
and rejection of fabricated review results. Re-test existing App authentication
without replacing their keys or passwords. Audit the complete deployed system.
Legacy operator App-vault/GitHub-Secrets copies must be reconciled before production
activation, not silently deleted now. Existing frozen Goal/main/Development
migration and all live writer/full-cycle proofs remain separate gates.

Approval means design/implementation of this addition only. It is not permission
to start an unbounded run, relax acceptance, modify Goal automatically, perform a
main trial merge, or enable automatic signing/merging before the final evidence.

## Independent design review

Fresh read-only architecture/security review found no critical/high contradiction.
Its initial Medium finding required adapting the existing Git/contract-writing
runner; the Low finding requested explicit packet/log/egress/rollback lifecycle.
The additions above resolved both in fix/re-review cycle1. A remaining stale
BROKER_SETUP opening was qualified as production deployment/wiring rather than
preparation. No new account, credential, service or authentication operation was
performed. Reviewer inspected source/docs only, without tests, network, credential
or deployed-state access. This is acceptance for owner consideration, not owner
approval, implementation evidence or activation. One of two design fix cycles used.
