# Unattended runtime verification — 2026-10-31

Operator decision: automate through PR creation; hold every merge. Existing
GitHub CLI keyring authentication remains `kanalia7355`. No token was copied
into source, configuration or runtime artifacts. Global Codex installation and
configuration were preserved; the client is installed under ignored runtime.

Independent auditor: `/root/unattended_boundary_audit`, read-only fresh context.
Initial review found container-lifetime and unproven tool-surface problems.
Fix/re-review 1 confirmed no High/Critical blocking a harmless schema-only sample;
it required stronger configuration binding before production. Final cycle2/2
returned `pass`, no unresolved High/Critical for source-only serial PR delivery.
The auditor performed static inspection only, not tests or external operations;
exact elapsed time and token/cost usage were not supplied. No merge or complete
Goal was approved. After that report, the existing container-only cache policy
was extended to Vitest's cache directory; latest full QA and containment checks
below cover this environment fix. No further review cycle was invoked.

Actual evidence so far:

- Authenticated schema-only Codex response: passed; not implementation approval.
- Zero-tool inference request capture with pinned catalog: passed.
- Docker negative/lifetime tests: 6 passed, including UID, network, daemon socket,
  immutable lease, no host writes, timeout/setsid, cancellation, output limit and
  sensitive-source rejection. CI skips these unless explicitly enabled; a skip
  is not live evidence.
- Latest immutable QA image: all4 configured required checks passed: current
  image advisory evidence, engine verification, wheel build and full application
  verification including browser E2E. Latest6 containment tests passed again;
  doctor generated a matching live receipt with zero tools, QA and timeout pass.
- Host engine verifier: 98 passed,6 explicitly skipped live tests; lint, format,
  Python3.13/3.11 types, secret scan, dependency consistency and advisories passed.
  Separate host application validation passed all12 checks (119 Python before the
  final hook regression was added,4 UI tests and5 Chromium E2E tests).
- Actual model implementation applied to a synthetic local Git fixture, then
  real container pytest: 2 passed. Three worker attempts were used: initial
  probe unavailable, unsupported schema, then successful implementation.
- First independent model review timed out at its 180-second bound. One separate
  bounded review retry returned `pass` with no findings. No worker was rerun;
  total worker attempts remain three and review invocations two.
- The full mocked Development Loop continues to cover PR/CI repair/eligible
  merge/next-gap generation. Real GitHub merge is intentionally untested/held.

Ignored receipts: `live-runtime.json`, `real-proposal-sample.json`, `qa-image.json`
and verification records under `.loop/runtime`. Receipt hashes invalidate when
the bound runtime changes. No `.loop/complete.json` is written by these samples.

Documentation reconciliation: older Bootstrap/ADR/phase entries describe the
earlier unavailable executor and initial Git state. ADR0006 and this ledger
supersede those transport/environment statements, not their immutable Goal,
acceptance, production-data restrictions or outstanding merge guarantees.

Initial product task: HeadersInit normalization, with an offline synthetic fetch
reproduction (`Headers` input lost `X-Request-ID`). The original README/product
scope is restored before any plan import; previous temporary engineering Goal
files are retained verbatim under `docs/plans/bootstrap-goal-history`. No frozen
plan was replaced and the old engineering acceptance remains incomplete. No
product code was changed during the runtime build or synthetic sample.
