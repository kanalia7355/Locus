# Decision M — PR-free main delivery activation (NOT approved)

Independent from Decision L and any unattended Loop trial. Offline design approved:
MAIN_FF_INTEGRATION_DESIGN.md SHA256
34cdd903506410ed45d63d041517776f7a2b0134c08d2166d55c8ad57e5cfb8f.
Code/review evidence: ../reviews/MAIN_TRIAL_OFFLINE_IMPLEMENTATION.md.

## Present state

Existing local_commit_push still publishes loop/local-development only. Optional
MainIntegration has an offline-only injected backend; no production transport,
runtime mode selector or real mutation permission is installed. The pure payload
and bare-repository transaction are not evidence of GitHub API compatibility.

Read-only inspection found current main protection requires one approving PR
review, last-pusher separation, administrators enforced and strict six required
Actions checks. Ruleset26268631 is disabled but that does not disable branch
protection. Current gh identity has admin/push rights; those rights do not permit
us to bypass the rules or infer write permission from metadata. Protection was
not edited or probed by mutation. Under these rules PR-free activation MUST HOLD.

## Separate design/protection decision needed first

The requested PR-free flow and current server-enforced PR approval conflict.
Removing that approval would lose the server's PR-review/last-pusher guarantee.
Independent local QA/review/range receipts, exact-SHA trusted Actions checks,
strict fast-forward/CAS and model/control-plane isolation are proposed replacement
controls; they are not identical guarantees and do not remove the trusted-host
assumption. A specific future protection policy and review-authority mechanism
must receive owner approval before any change. No blanket bypass, admin exemption,
new App/Broker, weakened CI or force Push is proposed as an automatic solution.

## Requirements before a future activation permit

- Implement/review the production backend only after an additional scoped approval.
  Reuse existing gh auth; never retrieve/store a token. Read complete/paginated
  exact-repository/commit push workflow runs and latest attempts, trusted publisher,
  workflow source digests and every required job. Keep all six required checks.
- Demonstrate the paired GraphQL updateRefs source no-op guard and main beforeOid
  guard with force=false in an expressly approved disposable GitHub validation
  repository/branch; offline tests do not establish hosted semantics. Unknown or
  unsupported no-op/CAS must HOLD without a fallback. No Locus main probe.
- Preserve current protection until the separately approved replacement is applied
  by an authorized owner procedure and read back. Permission/protection rejection
  remains terminal for that reserved attempt. No test-driven privilege expansion.
- Independently review the WHOLE accumulated main..target range at first promotion;
  current task reviews alone do not certify historical development commits.
- Pin reviewed source/runtime, repo node identity, both refs, QA/review/spec policy,
  workflow digests/publisher and exact target SHA. Re-read refs/CI before atomic
  mutation; no unrelated changes or unreviewed integration commit.
- Use existing PolicyMigration to select the post-Push mode only after explicit
  exact config/spec approval. Current frozen documents exclude main and therefore
  cannot be silently edited. Migration must remain impossible while a main intent
  is unsettled. Never reset task attempts or bypass pending security decisions.
- Retain separate development/main durable receipts. Require recorded main_head
  before Controller completes the task or starts the next task in that mode.
  Lost reply/state failure reconciles only the original exact intent and fresh
  refs/CI; no second mutation after uncertainty. Cancellation allows observation
  only and cannot start the next task.

## Future requested permit, not requested for execution now

After all preconditions: grant a bounded main-integration run tied to exact
repository/source/target/Goal/scope/policy and reviewed SHA range, deadline and
stop conditions, with read-back confirmation of main and durable journal. No PR,
force/history rewrite, protection bypass, unapproved data/model/auth/service or
Loop activity. Existing development成果 remain preserved if main delivery fails;
that failure never counts as overall Loop success.

Current deliverable is safe offline implementation and a concrete list of missing
activation evidence. It is NOT an already operational production-main backend.
Do not interpret approval of the offline design as granting any item above.
