# App delivery / migration source reviews

These are independent read-only source reviews of inactive service components,
not deployed-system or GitHub merge proofs. Reviewers did not run tests, read
credentials/vault/runtime contents, contact services, write files or delegate.
Five review invocations were used: two for delivery/readiness and three for
migration. Per-invocation token usage and elapsed metrics were not supplied.

## Review publication / remote transport / readiness

Initial review found a high replay issue: binding identity included fresh review
wording, so an uncertain publication could be retried with a different passing
review. A low issue identified schema initialization in a read-only observation.

Fix/re-review cycle1 passed with no remaining findings. A stable PR/head/base
reservation is now persisted before fresh review and survives different review
wording, changed QA timings and policy hashes. No repeat publication is sent
without explicit reconciliation. Readiness opens SQLite read-only before the
normal CLI state initialization path. New tests exercise lost check/approval
responses, changed review and QA, absent DB and byte-preserved legacy DB.

Review service accepts only a fixed authenticated policy-observer interface;
it is not given the Merge App client. Default transport authority refuses remote
lock acquisition. No publication or merge command is exposed to a model or
wired into the Controller. Real protected-DB authority, authenticated channel,
isolated service packaging and explicit recovery remain deployment prerequisites.

## Versioned policy migration

Initial scoped review found a high concurrent-edit overwrite race, a medium
legacy-config normalization mismatch and a backup interruption recovery gap.
Cycle1 confirmed those fixes and found one remaining medium staging-write
recovery limitation. Cycle2, the final allowed cycle, passed without findings.

The exact source being replaced is now captured and retained before no-replace
installation. Unknown edits are restored where the target is absent and then
held for reconciliation; recreated targets are never overwritten. Old backups
and new staged content are published only after complete flushed temporary
files exist. Interrupted temporary artifacts are retained. Configuration uses
the same normalization for live and backup comparisons. Goal acceptance, QA,
hard limits, repository/check identity, task attempts, budget, decisions and
evidence are not reset. The real project was not migrated or approved.

Hostile concurrent ancestor-directory replacement remains outside demonstrated
protection. Production deployment requires the isolated ACL/service boundary;
source review alone does not prove that boundary.

## Verification

Final local engine verification:221 passed,7 skipped; native and Python3.11/Linux
strict typing, Ruff lint/format, secret scanning and dependency audit passed.
Six skips are opt-in Docker containment cases, run separately. One synthetic
symlink test is explicitly skipped because this Windows account cannot create
that link; Linux CI must exercise it. No CI, assertion, timeout, retry cap or
acceptance criterion was weakened. Current installation bot identities and the
fixed read-only GraphQL PR query were separately verified live, with no remote
review/check/merge publication. PR6's native queued auto-merge was disabled.

The separate six-case real Docker run passed. The refreshed zero-tool client,
source-only QA and timeout probes also passed for runtime identity
`6914eccb4d12b8c252e4618bf1df89f6697df354c3a76b8362e4120f51c10cfd`.
The receipt still explicitly reports `merge_authorized=false`.

See [the full requirement/status inventory](../UNATTENDED_READINESS.md). Neither
these source reviews nor passing mock tests authorize production activation.
