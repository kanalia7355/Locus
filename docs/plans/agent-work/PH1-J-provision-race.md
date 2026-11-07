# PH1-J — Fix the stale-Principal race in web provisioning

Agent: append your progress under "## Progress" below every time you complete a
step. Do not edit other agents' files.

## Task brief

Context: PH1-G consolidation found one cross-slice semantic issue (recorded in
`docs/plans/agent-work/PH1-G-consolidation.md` at the integrated HEAD of
`loop/local-development`, a55d856 or later):

> The API obtains an admin `Principal` in `backend/app/main.py`'s `Actor`
> dependency before `POST /api/admin/users` calls `Service.provision_web_user`.
> That service checks the cached `system_admin` flag but does not revalidate the
> session in its creation transaction. Reproduction: capture admin A's
> principal, disable A via admin B (A's token then 401), call
> `provision_web_user` with the captured principal — the user is nevertheless
> created. Impact: a delayed in-flight admin provisioning request can mutate
> state after disable/session revocation.

Goal: revalidate the live session inside the provisioning mutation transaction
(follow the pattern PH1-B used for `set_user_enabled`/`rotate`: bind
authorization to the live session inside the serialized transaction) and add a
race regression test (disabled/purged admin principal cannot create a user;
enabled admin can). Check whether the same Principal-before-transaction pattern
affects other newer admin endpoints added by the integrated slices
(`set_user_enabled` already revalidates; verify recovery redemption needs none)
and align them, recording any judgement.

Setup: create your own worktree: `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH1-J-provision-race -b loop/PH1-J-provision-race origin/loop/local-development` (reuse if it exists). Work ONLY inside it. Read `AGENTS.md`, governance docs, `backend/app/service.py` (provision_web_user, set_user_enabled, _authenticate), `backend/app/main.py`, and `tests/test_account_toggle.py` (revalidation test pattern) first.

QA (repeat until ALL green): pytest tests -q --ignore=tests/e2e (full suite), ruff check + format --check, mypy backend/app, secret scan; frontend lint/test/build only if you touch frontend (you should not). Adversarial self-review the fix (auth path: check enumeration, timing, audit accuracy).

Conventional Commit (`fix(admin): revalidate the live session inside web provisioning`). Push `loop/PH1-J-provision-race`. Wait for branch CI; fix failures and re-push until ALL checks green (bounded; record if blocked). Append progress + SHA + CI evidence here.

Boundaries: never push to `main` or `loop/local-development`; scope is the race fix + regression only (no other features); do not weaken tests; do not spawn subagents.
