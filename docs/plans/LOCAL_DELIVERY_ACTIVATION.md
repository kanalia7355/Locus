# Local delivery activation proposal

Prepared from the frozen project, without replacing it. Complete exact proposal:
[`local-delivery-snapshot.json`](local-delivery-snapshot.json).

- Migration: `6b58f01906ec4239a5d13012eac965c7`
- Decision: `DEC-6f80a4a73aac428a`
- Target: `f6b99a048bbe2a31acdb3dd66796fe564a079f5983963f7b498623d44290f44a`
- Development branch: `loop/local-development`, corresponding origin branch.
- Changes: delivery `local_commit_push`, enable existing Development Loop,
  bound its planning scope to backend/frontend/tests, replace historical PR/main
  assumptions in Goal/requirements/architecture with the authorized delivery.
- Unchanged: all product acceptance, local mandatory QA, independent review,
  security policy, execution boundary, repository/origin, stored required CI list,
  attempt/review/time limits, every existing task and pending decision.

`PolicyMigration._apply` requires exact operator approval; code implementation
does not manufacture that decision. After reviewing the proposal, an operator
can approve and apply using the existing CLI:

```powershell
.venv\Scripts\python.exe -m loop_engine.cli approve DEC-6f80a4a73aac428a --target-hash f6b99a048bbe2a31acdb3dd66796fe564a079f5983963f7b498623d44290f44a --reason 'Reviewed local commit and development branch Push migration'
.venv\Scripts\python.exe -m loop_engine.cli migration-apply 6b58f01906ec4239a5d13012eac965c7
```

This does not establish runtime readiness. The current model-boundary receipt
does not match current code and live execution remains blocked. The existing
tool-surface probe also needs explicit validation against the installed client
request shape before any new readiness proof can be trusted. Do not regenerate
or waive a receipt merely to launch. No ADR-0011 design is approved here.
Old App/audit services need no activation for this workflow.

Pending decisions and the exhausted historical TASK-001 are not approved/reset
by migration. Independent new tasks can be planned by the existing planner;
their actual scope and dependencies remain subject to the original gates.
