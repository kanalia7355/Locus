# ADR 0006 — Text proposals and isolated QA

Scope: the operator-authorized, source-only development runtime. Product data,
production deployment and external research-model connections remain excluded.
See [operator authorization](../governance/UNATTENDED_AUTHORIZATION.md).

The native Windows sandbox diagnostic did not establish the complete boundary:
loopback and a policy-path write were possible. Its result is never accepted as
production proof. The default unavailable executor still fails closed.

The `proposal-docker` executor uses two separate capabilities:

1. An authenticated, project-local Codex 0.166.0 client returns JSON text only.
   Model tools, plugins, apps, browser/search and shell snapshots are unavailable.
   A local rejecting inference endpoint observes the actual request advertising
   zero tools and no prior response. It never forwards requests or records auth
   headers/input. The catalog is pinned; client/config/catalog/AGENTS/skill and
   hook identities are checked before and after inference. Installed lifecycle
   hooks cause a hold for assessment; they are not disabled or bypassed.
2. The Controller validates bounded exact replacements before applying them in
   the task worktree. No fuzzy patches, deletions, existing-file creation,
   symlinks, path escapes, nested Git/config/agent controls or dependency/QA
   configuration edits are allowed. Credentials are rejected. A reviewer receives
   explicit current and baseline source; hashes alone are insufficient.

QA runs in an immutable Docker image without network, host credentials, Docker
socket or shared Git/state mounts. The host first stages only Git-visible,
non-sensitive regular source files. The container mounts that staging read-only
and copies it to private tmpfs. Tests run as UID1000; QA writes never reach the
host worktree. Root supervisor setup uses only the listed capabilities and drops
identity before starting the workload. Per-call leases, a hard deadline, closed
markers and owner/call-bound container reconciliation handle cancellation,
timeout, excessive output and descendant processes. Uncertain cleanup blocks
further calls. No other user's container is stopped.

Online pip/npm advisory checks run during the trusted image build. A required
`{image-audit}` check binds that successful build to the exact immutable image,
current manifests/supervisor and a 24-hour freshness window. Changed manifests
or stale receipts fail; runtime QA cannot silently use unaudited dependencies.
CI retains its existing online advisory checks and all other required checks.

The service rejects `uniqueItems` in its output schema. Only the transport copy
omits that unsupported keyword; full local validation still rejects duplicates.
Local schemas, task identities, attempt limits and acceptance are unchanged.

PR-only delivery requires local QA/review, observed successful current-head CI
and exact repository/head/base identity. Merge-only protection/publisher APIs
are not prerequisites for merely delivering a PR. Every merge remains held by
the operator; no protection, trusted-review or atomic-base gate is relaxed.

The repository has no `main`. The outer latest-main Development Loop remains
held while merges are held; it is not redirected to another integration branch.
Existing independent task PRs may target the configured existing bootstrap
branch. This is delivery, never proof of main integration or Goal completion.

Limitations: Windows client setup and Docker Desktop are required for this
tested mode; arbitrary model tool use is unsupported. Source bundles have
finite size limits and intentionally conservative credential detection. A false
positive holds the task rather than exposing data. Fresh runtime proof is
required after runtime/image changes. Exact CLI/QA/review evidence and unresolved
gates are recorded in the runtime review ledger.

References: [Codex permissions](https://learn.chatgpt.com/docs/permissions),
[Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox),
[hook configuration](https://learn.chatgpt.com/docs/config-file/config-advanced#hooks).
