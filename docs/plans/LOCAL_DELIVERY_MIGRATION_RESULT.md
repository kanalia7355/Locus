# Local commit / Push policy migration result

## Applied scope

The operator explicitly approved only target
`f6b99a048bbe2a31acdb3dd66796fe564a079f5983963f7b498623d44290f44a`.
Existing CLI `approve` recorded that decision, and `PolicyMigration` applied
`6b58f01906ec4239a5d13012eac965c7`. Active specification hash:
`78eb0872fb0b0fb2778ffece140573f64b01751482e8ca0fce95fb08fb76cb71`.

Delivery is `local_commit_push`, integration/Push branch is
`loop/local-development`, and the existing Development Loop is enabled for
`backend`, `frontend`, `tests`. These are configuration changes, not a running
loop. Original source files are preserved by the migration's existing capture
and backup mechanism. The approved proposal itself is unchanged.

## Verified invariants

- Live source equals the exact approved proposal and its frozen metadata hash.
- Reapplying the same migration returns the same hash without another migration.
- All ten captured operational history tables have identical before/after
  digests, including task/checkpoint/execution/verification/review history.
- TASK-001 remains completed with three consumed attempts. Run budget and
  dependency history are unchanged. No tasks are reset or imported.
- Only the explicitly approved migration decision changed; all other decisions
  retain their exact rows. Metadata changes are limited to specification
  snapshot/hash and migration intent.
- Product acceptance bytes and loop/security/verification/QA/approval policy
  sections are unchanged. No runtime, retry, independent-review or protected-file
  approval condition is relaxed. Original file backups match pre-migration bytes.
- Controller remains stopped, audit service remains stopped, Review/Merge
  preparation services retain their prior Running states. No service command,
  authentication operation, model call, loop launch, PR or merge is performed.
- The current runtime receipt is rejected, as expected; no readiness proof is
  regenerated or waived.

Actual migration regression command: `python -m pytest
tests/unit/test_loop_policy_migration.py -q` — 12 passed, one existing Windows
symlink-privilege skip. Before/after evidence is retained under ignored runtime
`migrations/6b58f01906ec4239a5d13012eac965c7/operator-verification-*.json`.

## Observed GitHub Actions for implementation commit 254dd46

- [Prototype quality](https://github.com/kanalia7355/Locus/actions/runs/41344254310): success.
- [Loop engine checks](https://github.com/kanalia7355/Locus/actions/runs/41344254345): failure.
  Ubuntu Python3.11 and Python3.13 succeeded. Windows Python3.13 had three
  failures; Windows Python3.11 was cancelled by the matrix failure.
- Failed tests: `test_actual_installer_feature_guard_accepts_fixed_versioned_features`,
  `test_read_only_diagnostic_filters_nonsecret_record_fields`,
  `test_actual_upgrade_replace_statement_handles_null_backup`.
  Each involves legacy audit-service PowerShell fixtures timing out at its
  20-second subprocess boundary. The run reports 448 passed, three failed and
  six skipped. The underlying cause is not established by these logs alone.

No tests, timeouts or workflows are changed as part of settings migration.
These failures remain visible follow-up work; the run is not reported as green.
Actions remain additional evidence for this mode, not a replacement for local QA.
Subsequent migration-commit runs must be distinguished from this completed run.

## Remaining work before unattended Locus development

1. Diagnose and fix the three Windows failures with the existing local QA and
   actual CI evidence; preserve assertions and bounded subprocess execution.
   A simple unexamined timeout increase is not proof of correctness.
2. Correct and validate the existing model boundary's tool-surface proof. The
   pinned client receipt is 0.166.0. Existing project findings in proposed
   ADR-0011 document tool declarations inside Responses Lite `input.additional_tools`;
   `ToollessBoundary.probe` currently inspects only top-level `tools`. Therefore
   neither the old zero-tool claim nor simply refreshing the stale receipt is
   sufficient. This affects the implementation runner as well as former audit
   infrastructure. No ADR-0011 architecture is adopted by this migration.
3. Reuse the current executor/interfaces, prove actual permitted request/tool
   behavior and fail-closed handling with synthetic inputs, then independently
   audit any security-relevant change. If current client/model cannot satisfy
   the approved boundary, report that limitation before selecting an alternative;
   do not silently introduce another executor, protocol gate or authentication.
4. After separately permitted live capability validation, bind a new runtime
   receipt to the exact code/client/image and verify local QA isolation,
   cancellation/deadlines and no credential/control-plane access. Product/model
   privacy and research-data restrictions remain unchanged.
5. Obtain a separate instruction to launch unattended execution, then let the
   existing planner select grounded low-risk synthetic-prototype gaps using the
   approved Goal, product acceptance, UI baseline and preserved task history.

PR creation, Review App, Merge Broker, automatic merge, new App enrollment and
audit-service restart are not prerequisites for this delivery path. Manual
single-agent product work is separate from unattended runtime readiness; no
product code is changed by this settings-only operation.

## Documentation reconciliation

Frozen Goal/requirements/architecture now describe local integration and Push;
the obsolete assertion that main does not exist is removed by the approved
proposal. Earlier PR/main/App operational documents remain historical for legacy
delivery and are not normal-mode activation requirements. Product architecture
still uses the documented development SQLite/lexical adapters; proposed
production PostgreSQL/vector/model choices remain unconfirmed.
