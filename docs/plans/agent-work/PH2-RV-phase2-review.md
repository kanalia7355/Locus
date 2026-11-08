# PH2-RV — Independent read-only review of the Phase-2 aggregate

Agent: append your progress under "## Progress" below. You are a REVIEWER: do
not modify any file other than this one (your progress notes), do not spawn
agents, do not push, do not create a persistent worktree. Work in the main
checkout read-only.

## Task brief

This is the FINAL GATE before the Phase-2 main integration (owner mechanism B-2:
implementation/review/QA complete → completion conditions + final audit →
all-CI-green → automatic main integration → version bump → next phase).

Review the Phase-2 aggregate at `loop/local-development` HEAD (the integration
of: PH2-B concurrent role holdings + explicit deny `10ee9c4`; PH2-E
combined-roles/deny UI `9738ca2`; PH2-D time-limited delegation `3150f6b`;
PH2-C storage-ACL research `0e06107`; the PH2-CA completion audit docs). Read
also: `docs/plans/PHASE2_DELEGATION_SPEC.md` §8 (binding owner conditions),
`OWNER_DECISION_REGISTER.md` (RESOLVED 2026-11-09), the task files
(PH2-D-delegation.md, PH2-B-roles.md, PH2-E-web-mgmt.md), the Phase-2
reconciliation row and PHASE_STATUS declaration.

Review criteria:
1. **Security adversarial pass over the whole authorization surface**: the
   delegation model (grant/revoke/cancel/expire endpoints), concurrent-role
   union + deny precedence, the interaction of delegation with roles/deny/
   publication grants/membership — hunt for ANY path where effective permissions
   exceed the union of legitimately held rights, where an expired/revoked grant
   still authorizes, where grantor authority loss leaves a live grant, or where
   the audit misses a mutation. Verify the live-revalidation claims against the
   actual authorization code paths (document read/retrieve, chat dispatch,
   attachments) — not just tests' existence.
2. Spec conformance: every binding owner condition (TTL 24h/7d/15m, grantor
   definitions, family/version no-revival/no-coexistence, NON_ADMIN ceiling,
   membership gate, epoch seconds, retention) verifiably implemented.
3. The PH2-CA completion declaration: is its scope accurate (delegation UI
   absent — recorded; org-wide deferred; storage-ACL planning open; production
   items deferred)? Any silent resolution?
4. Spot-check ≥10 code paths and the recorded QA counts (PH2-D 1156/18;
   PH2-E 1146/18+64+12; integrated 1155/9) against reality.
5. The local load-flake observation (native-launch tests) is recorded, not
   claimed as pass/fail.

Verdict: accept / accept after minor fixes / needs major rework. Findings with
severity, location, evidence, fix recommendation. Do not edit anything except
this file.

## Progress

- (reviewer appends here)
