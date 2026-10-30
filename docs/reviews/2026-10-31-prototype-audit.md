# Independent architecture/security audit record

Scope: local synthetic-data-only prototype; no live research data, production deployment, cloud connection or remote merge. Main implementer alone changed files.

## Design audit (initial)

Fresh-context read-only agent `security_audit` reviewed governance, specifications, threat model and ADR 0002 before security implementation. No critical/high finding within the approved scope. Medium clarifications: missing/null Origin rejection; rotation-only/single-use temporary login and concrete expiry; final transactional ingestion checks; fixture scanner unavailable through runtime configuration; explicit role/assignment ceilings. Adopted in ADR and implementation.

## Implementation audit (initial)

Fresh-context read-only agent `implementation_audit` inspected backend, frontend, boundaries, tests, scripts and recorded verification evidence. Did not edit files, run network calls or read credentials/storage. Disposition: FAIL pending two medium findings; no critical/high finding.

1. Owner publishing to a recipient role excluding the owner's role lost the ability to stop publication or delete. Added an owner-management path with current project/upload permission checks; empty grants return the document to personal scope. Content retrieval still follows recipient grants. Added publish-to-other-role → stop/delete regressions.
2. SQLite connection contexts did not explicitly begin until DML, leaving final authorization SELECTs outside the publication transaction. Added explicit BEGIN IMMEDIATE/commit/rollback around complete service database units. Added a two-connection concurrent revocation regression. Also moved interrupted-job recovery out of connection construction into worker startup, so CLI connections do not reset running jobs.

Both regression tests were executed before the fixes and failed for the reported reasons; after fixes, the full Python suite passed. Follow-up verification and first implementation re-review results are recorded below when returned.

### Implementation re-review — fix cycle 1

The independent reviewer returned PASS for the reviewed prototype fixes, pending final automated verification. It confirmed the owner-management boundary, explicit transaction around authorization and indexing, independent-connection regression, and worker-startup-only recovery. No new concrete critical/high/medium finding was identified in the changed paths. The reviewer inspected source and tests without claiming independent execution. A second fix/re-review cycle was not needed.

Final automated verification after those fixes completed successfully: all12 verifier checks exit0; Python22 tests, UI4 tests, Chromium5 end-to-end tests, offline secret scan0 findings, pip/npm advisories0. Evidence is recorded in `.bootstrap/verification.json` and summarized in `.bootstrap/complete.json`. This final execution was performed by the implementer, not misattributed to the reviewer.

## Invocation governance

Only audit agents were used; no implementation delegation. Initial design audit and initial implementation audit were separate fresh contexts. Implementation fixes/re-review are limited to two cycles. Runtime tools expose no per-agent read-only sandbox or enforceable usage/time limit; boundaries are procedural and this limitation remains open. Reviewers were instructed not to edit, spawn, access secrets or use external services. Their reports did not claim independent test execution. Exact reviewer token usage/elapsed telemetry is unavailable in the collaboration API.
