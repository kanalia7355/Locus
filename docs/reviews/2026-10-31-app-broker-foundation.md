# App/Broker foundation review — 2026-10-31

Scope: approved ADR0007 implementation foundation only. No production service,
trusted review publication, remote merge gate, Controller activation or state
migration is claimed. Existing `atomic_base_binding=false` remains unchanged.

## Independent source review

One fresh read-only security/architecture reviewer inspected the six new modules,
App registration CLI, pinned cryptography dependency, associated tests and setup
documentation. It accessed no credentials/network, ran no tests, modified no
files and spawned no agents. Only the main agent implemented changes.

Initial disposition: accept the **inactive foundation** with two medium hardening
findings and one low wording issue. Fix/re-review cycle 1 accepted with no scoped
blocking findings. A final key-parser hardening change was accepted in cycle 2;
the maximum two fix/re-review cycles were used.

- Journal confinement: now uses existing Windows-aware reparse detection for all
  ancestors and SQLite sidecars before directory creation and each open. Tests
  simulate unsafe ancestors/sidecars. This is not live junction/replacement-race
  proof; a service-owned directory and ACL boundary remain activation gates.
- Absolute receiver lifetime: a byte-wise socket reader enforces monotonic
  deadline and 16 KiB total header limit. Actual socketpair regressions exercise
  trickled and oversized headers; inactivity timeouts alone are not relied on.
- Token wording: in-memory handling is distinguished from remote expiry/revocation
  and guaranteed memory erasure. Those lifecycle proofs remain outstanding.
- Setup documentation now invokes the actual `loop_engine.cli` module.
- Registration parses the returned PEM and requires an RSA private key of at
  least 2048 bits before vault storage; it does not rely on a header prefix.
  Malformed/unsupported/encrypted/non-ASCII keys fail with a static error. This
  also avoids an artificial secret-header literal in source snapshots; existing
  secret-scanner controls are unchanged.

The review confirms writer-only ruleset proposals do not replace CI/review
protection, mutation intents precede remote writes, and uncertain operations do
not trigger lock stealing or blind replay. This does not prove live GitHub rules.

## Executed local evidence

- `scripts/verify_loop.py --audit` after final hardening: 156 passed, 6 explicitly skipped Docker-live
  tests; lint/format, mypy native and Python3.11/Linux, secret scan, dependency
  consistency and advisory audit passed. No known third-party advisories;
  unpublished `locus-loop-engine` is explicitly outside PyPI advisory coverage.
- App/Broker-specific tests after final hardening: 33 passed. Remote lock, mutation uncertainty, crash
  restart and ownership cases are simulated. JWT signatures use generated
  ephemeral in-memory RSA keys. No real App key/token is used.
- Actual Windows Credential Manager: one newly allocated, nonsecret synthetic
  credential completed write/read verification; only that owned item was removed
  and absence confirmed. Existing credential entries were not enumerated/read.
  This proves the storage API binding, not signer isolation or GitHub App auth.

- `scripts/verify.py --e2e --audit` before the final registration-parser hardening:
  all 12 checks passed; 176 Python tests, 11 frontend unit tests and 5 Chromium
  E2E tests passed, application backend coverage 88%, package advisories zero.
  The subsequent change affects registration validation only and is covered by
  the complete final engine suite above; application behavior was unchanged.
- The six new modules pass the unchanged source-context secret guard. The frozen
  runtime database still records TASK-001 completed with 3 attempts and stopped
  control. No Goal, approval, task counter or frozen config was reset.

Rebuilt QA image and remote CI outcomes are recorded below when observed.
No skipped or mocked check is classified as live proof.

## Deliberately unfulfilled gates

[BROKER_SETUP.md](../BROKER_SETUP.md) lists service identity/source pinning,
fresh reviewer/check publication, actual App installation, remote gate reader,
exclusive main/lock writers, denial of other update paths, cross-host recovery,
rotation/revocation, versioned policy migration, final audit and operator
activation. No frozen Goal/config/database, attempts or approvals were reset.
