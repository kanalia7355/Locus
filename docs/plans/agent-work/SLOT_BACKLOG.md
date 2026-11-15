# Slot Backlog (max-utilization policy, owner 2026-11-11)

Owner policy: as soon as a slot finishes, refill it with the next queued task — keep slots maximally utilized up to the 10-slot cap. Active slots integrate in FIFO order; blocked/queued items below are dispatched the moment their dependency clears.

| # | Task | Slot/model | Dependency | Brief |
|---|---|---|---|---|
| 1 | Skills actual-usage integration (owner directive §3-§9) | Z / GLM | U integrates (skill-file conflict avoidance) | Z-SKILLS-USAGE.md |
| 2 | Receipt 2b independent review | next / per alternation | Q integrates | (to write) |
| 3 | Skills P0 deliverable review (may fold into Z's audit) | — | U integrates | — |
| 4 | UI refactor independent review | next / per alternation | W integrates | (to write) |
| 5 | Runner trust foundation implementation (post-review) | next / per alternation | trust design review passes (Y) | (to write) |
| 6 | Runner comm/isolation implementation planning | next / per alternation | comm design review passes (Y) | (to write) |
| 7 | Agent adapter verification test plan execution (mock/stub only) | next / per alternation | adapter review passes (Y) | (to write) |
| 8 | P1 skills (eval-skill/retro/improve-skill) design | deferred | owner go-ahead + no duplication with existing | — |

Active at last update: Q (P1-RECEIPT), U (SKILLS-P0), W (UI refactor), X (doc reconcile), Y (design review).
Alternation ledger: P=GLM→Q=Luna→R=GLM→S=Luna→T=GLM→U=Luna→V=GLM→W=Luna→X=GLM→Y=Luna→Z=GLM.
