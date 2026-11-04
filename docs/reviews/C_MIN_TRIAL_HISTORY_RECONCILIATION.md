# C-min trial history: conservative reconciliation

Investigation evidence only. Operational permission: **false**. Production history registration: **false**.

Owner evidence inspected at: 2026-11-04T06:16:31.293023+00:00
Owner-supplied diagnostic SHA-256: `05e565177326f9876ce60e675a28976c0904c6dd94788569f6268fb3b8889914`

| Record | Owner-reported phase | SHA-256 | Disposition |
|---|---|---|---|
| synthetic-model-proof.json | started | `a23610b70b8f12257bc31261ed335498e41a66d1878855fa2327b9a599eba2c9` | held / unknown / no replay; reservation not released |
| transport-model-proof.json | started | `df7281d09810616989c957a620cec473fe31592121b57c1f8564a928b0a39e25` | held / unknown / no replay; reservation not released |

Original trial hash matches the owner-approved upgrade manifest exactly.
Approved upgrade manifest SHA-256: `ff4053a18ef4ccfadaa3d859564eddaed1af959821489c8ffda316b872068d33`
Diagnostic active payload: `cee51f97a79bcdfdd2009f4e9fb889d999baf1b9d3e866e40f934cb18ffc0877`
Completion reconciliation-permit hash: `c64fc846dca7dd928475e2f7f9e511b640ec0ebe67c09d00eb15fca24db70a3a`

The diagnostic-record hash has no earlier observed baseline. It is a new owner-reported anchor, not a claim of historical hash equality.

Accounted historical reservations: **2**. Refunds: **0**. New grants: **0**.
Actual provider completions and remaining subscription quota: **unknown**.
No Controller time budget, task attempt, intent, production metadata or permission was reset.

The diagnostic provider_request_sent=false describes that diagnostic operation, not historical sends.
Started is neither a completion receipt nor evidence that nothing was sent.
New source/workspace identities cannot refund reservations.
Owner JSON is not signed machine attestation; hashes must be rechecked before a future permitted live attempt.

The equivalent machine-readable analysis is retained locally under .loop/runtime/c-min-trial-history-analysis.json; it is not an executable permit.
