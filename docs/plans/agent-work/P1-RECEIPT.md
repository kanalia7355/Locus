# P1-RECEIPT — Receipt 2b implementation (TTL + approval flow + contract finalization)

Agent: append your progress under "## Progress" below every time you complete a step.
Work ONLY in your own worktree/branch. You MAY modify backend code and tests.
Never push to `main` or `loop/local-development`; no subagents. Use `.loop/runtime/qa-venv`.

## Task

Implement the Receipt 2b contract with the owner-approved parameters (Entry 1-2 from
`docs/plans/OWNER_DECISIONS_2026-11-10-ENTRIES.md`).

**TTL values (owner-approved Entry 1):**
- Default TTL: 24 hours (86400 seconds)
- Maximum TTL: 7 days (604800 seconds)
- Expiry: Control Plane authoritative absolute epoch-seconds
- No grace period
- Expired receipt reuse is prohibited
- Auto-reissue: in-scope jobs get a NEW receipt (not an extension) after current
  permission/policy re-verification
- Auto-reissue is PROHIBITED on permission loss, policy change, or out-of-scope operation
- Receipt TTL and delegation grant TTL are SEPARATE concepts

**Approval flow (owner-approved Entry 2):**
- No new `approve_jobs` permission — derive approval authority from existing Owner/Grantor/Admin roles
- Personal workspace: owner self-approval within Q2-approved scope
- Shared/organization workspace: existing admin controls and approver authority ceilings
- Never bypass upper policy, explicit deny, membership conditions, or delegation limits
- Maintain approval-subject / execution-subject separation where required

**Implementation scope:**
- backend/app/service.py — receipt creation, TTL validation, auto-reissue logic
- backend/app/agents/registry.py — receipt/envelope integration
- tests — TTL boundary tests (default, max, expired, reissue, auto-reissue prohibition)
- Update `docs/plans/HYBRID_STEP2_RECEIPT_CONTRACT.md` §7 to reflect confirmed TTL values
  and approval authority (replacing 【要決定】 markers on DP-010/011/021)

**Safety boundaries (MUST NOT change):**
- ADR-0011 Plane-M zero-tool, ADR-0012 dual-plane, B6 dispatch rejection
- E1 recheck before enqueue, E2 recheck before execution
- Fail-closed on denial, stale policy, mismatch, revocation, unavailable authority
- No credential bytes in receipts/audit
- No dispatch/enqueue/execution activation

## Process

Read AGENTS.md + DEVELOPMENT_POLICY.md + owner decisions + HYBRID_STEP2_RECEIPT_CONTRACT.md.
Implement; run FULL QA (ruff, mypy, pytest --ignore=tests/e2e, frontend tests if UI changed);
Conventional Commit; push origin loop/p1-receipt-2b; repeat until all checks pass.
Conventional Commit subject: `feat(receipt): implement the receipt 2b contract with owner-approved TTL and approval flow`
