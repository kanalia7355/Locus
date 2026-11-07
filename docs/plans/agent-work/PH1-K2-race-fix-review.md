# PH1-K2 — Re-review of the integrated provisioning race fix (PH1-J)

Agent: append your progress under "## Progress" below. You are a REVIEWER: do
not modify any file other than this one (your progress notes), do not spawn
agents, do not push, do not create a persistent worktree. Work in the main
checkout read-only.

## Task brief

The PH1-K aggregate review (verdict: accept after minor fixes) conditioned
acceptance on: (1) the provisioning race fix, (2) a re-review of the integrated
fix, (3) all-CI-green at the exact final HEAD. Condition (1) is now integrated:
commit `0365a6a` on `loop/local-development` — `fix(admin): revalidate the live
session inside web provisioning` (branch CI green at a196e5e; full local pytest
1114 passed/18 skipped).

Review the integrated fix commit `0365a6a` (diff vs its parent):
1. Does `provision_web_user` now bind authorization to the live session INSIDE
   the serialized creation transaction (re-authenticate cookie, principal-id
   match, current system_admin check, rate limit, user insert + audit in the
   same transaction)? Any residual window?
2. Is the race regression test valid and does it assert no user/audit creation
   on the stale path and success on the live path?
3. Does the fix weaken anything (authz, audit accuracy, existing tests)?
4. Delivery note: the agent stalled and the orchestrator completed delivery,
   hardening the test (allowlisted password literals, first-login rotation +
   re-login). Verify the test changes are sound and secret-scan-safe.

Verdict: accept / accept after minor fixes / needs major rework — this closes
the PH1-K condition if accepted. Findings with severity/location/evidence/fix.
Do not edit anything except this file.

## Progress

- (reviewer appends here)
