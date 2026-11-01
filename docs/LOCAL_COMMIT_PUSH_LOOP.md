# Local commit and Push delivery

The operator's 2026-11-02 instruction authorizes task commits and Push to a
dedicated development branch. It does not authorize direct main Push, new PRs,
App activation or automatic merges. Existing Controller, task worktrees,
verification, independent reviewer, Development Loop and runtime limits remain.

## Policy

Set `github.delivery: local_commit_push`, `github.enabled: true`,
`github.base: loop/local-development`, `github.auto_merge: off`, and retain the
approved repository and origin. The branch must already exist locally at the
approved starting commit. No branch is silently selected or created by runtime.
Legacy `local` still means verification-only and does not create commits.

For a frozen project, propose a complete source snapshot using `migration-plan
--file <snapshot.json>`, inspect its exact diff, resolve its scope decision and
run `migration-apply <id>`. Acceptance, attempts, budgets, pending decisions,
execution boundaries, QA and independent review are preserved. Do not hand-edit
frozen `.loop` files, manufacture approvals or reset attempted tasks. The
existing PR-oriented Goal wording must be migrated explicitly too; product
acceptance must stay unchanged.

## Execution and recovery

Use `.venv/Scripts/python.exe -m loop_engine.cli launch 2h`, or
`launch --resume 2h` for another bounded window. Both require a current successful
execution-boundary receipt. This delivery feature does not establish that proof.
Review/merge/audit Windows services and ADR-0011 are unnecessary for this path;
they are neither activated nor authenticated by this change.

Each verified and reviewed task records a commit intent, stages only verified
paths and creates `feat: implement TASK-NNN`. The expected parent, tree, source
binding and subject identify a recovered commit. Empty changes are held rather
than producing an empty success commit. A committed task is fast-forwarded into
the configured branch; a clean primary checkout may be fast-forwarded, but an
occupied other worktree is held. Main and unrelated branches are untouched.

Delivery records expected local and remote OIDs before mutation, uses an ordinary
non-forcing single-ref Push and confirms the remote OID afterwards. A failed or
uncertain delivery stops the run and retains the idle task checkpoint. Resume
observes Git state before continuing. Push confirmation is required before task
completion or another task; dependency worktrees start at integrated local HEAD.
Unexpected changes or branch deletion are held, never force-pushed or rewritten.
As with ordinary Git Push, a remote change after the final read is subject to
server fast-forward protection; this is not a distributed compare-and-swap lease.

## GitHub Actions

Existing `quality.yml` and `loop-ci.yml` already run on non-main Push. They are
unchanged. Recent inspected runs took about 1–2 minutes for product verification
and 4 minutes for the engine matrix; an engine run had failed. Actions success
is **additional evidence**, not a prerequisite for this delivery mode. No failed
Action is reported as passing. Local required checks and independent review
remain mandatory. Investigate remote failures without weakening CI or tests.
This avoids introducing PR-only title checks or App checks into Push completion.
The inspected failed Windows run ended around the old aggregate test command's
180-second limit. Real Git recovery coverage also adds runtime, so the aggregate
test-command limit is now 600 seconds. No test/check is removed, no assertion is
weakened, and Controller/task/attempt limits and workflow job limits are unchanged.

## Proof boundaries

New integration tests use real Git, worktrees, commits and a local bare remote;
only GitHub destination identity is substituted. Model/reviewer fixtures do not
prove live model isolation, and bare transport does not prove live GitHub Push.
Existing App/Broker/service tests remain regression coverage for optional legacy
paths. Goal completion still requires all acceptance, current-head verification,
independent project review and no major unresolved findings.
