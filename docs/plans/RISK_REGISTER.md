# Development risk register

| Risk | Current mitigation | Remaining gate |
|---|---|---|
| Real research data in a prototype | Visible synthetic-data-only labels; no imports from actual storage; loopback guards | Explicit production security/data handling design |
| Malware or unsafe parsers | Bounded plain UTF-8 inputs, no active rendering, scanner default quarantine | Approved scanner, parser isolation and supported-format validation |
| Cross-project or private-history leakage | Shared live policy checks, per-owner history/attachments, regression tests | Independent audit and actual deployment threat tests |
| Stale authorization during ingestion | Final transaction rechecks owner, membership, cancellation/source state | Production distributed transaction/job design |
| External disclosure | No model/cloud connector; explicit startup rejection of cloud settings; covered-path socket test | Deployment outbound firewall verification |
| Reviewer permissions not technically enforced | Fresh context, explicit read-only/no-spawn/no-network scope, recorded findings, two-cycle limit | Hosting runtime permission controls and trusted CI review integration |
| Development SQLite confidentiality and retention | Only synthetic data; Git exclusions; explicit delete endpoints | Production storage, encryption, backups, retention and secure erasure ADRs |
| Capacity assumptions | Bounded ingestion backlog, per-user and document/message quotas | Measured representative hardware/material workload |
| Supply-chain/licensing | Exact resolved versions, integrity-bearing npm lock, advisory checks, license inventory | Production dependency policy, notices and redistribution review |
| GitHub governance unavailable | Local feature branch only; prepared CI and Conventional Commits title workflow | Authorized remote, PR, trusted review status and protection verification |

Open items are deliberately not converted into a claim of production readiness. See ADR 0001 and ADR 0002.
