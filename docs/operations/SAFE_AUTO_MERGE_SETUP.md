# Safe automatic merge setup

Operator request, 2026-10-31: repository visibility was changed to public by the
operator, who now requests conditional automatic merging. This supersedes the
previous blanket merge hold only where every existing safety condition passes.
It does not authorize bypasses, self-approval, weaker CI or future-head blanket
authorization.

The reviewed `.github/main-protection.json` configures strict current-base CI,
all six existing required contexts pinned to the observed GitHub Actions App
ID15368, one approving review, stale-review dismissal, latest-push approval,
conversation resolution, administrator enforcement, linear history and no force
push/deletion. Repository settings allow auto-merge and squash commits with PR
titles; merge/rebase commits are disabled for future PRs. Existing history is
preserved. A token permission or public visibility alone does not provide these
controls.

These platform settings are prerequisites, not proof of completed unattended
merging. The current Controller still fails closed for:

1. A trusted independent-review publisher is not provisioned. It must publish
   `loop-independent-review` for the exact head/base/policy binding, with its
   authenticated App ID pinned in branch protection. Ordinary Actions jobs and
   the implementer's own approval cannot stand in for that review.
2. `atomic_base_binding` is deliberately false in `github_manager.py`: gh's
   expected-head guard does not atomically bind the base. Public personal
   repositories do not gain GitHub merge queues; those require an organization
   repository. A separately reviewed concurrency solution is still required.
3. Main migration of frozen configuration/state, merge allowlists and policy
   authorization must preserve Goal, existing attempts and prior evidence.
   Changing YAML alone invalidates the imported specification hash. The current
   `.loop/config.yaml` therefore remains PR-only until this migration and live
   safety evidence exist.

## Independent review identity: one-time operator setup

A suitable dedicated review App should be private, installed only on Locus,
with Checks write, Contents read and Pull requests write (for posting the actual
independent approving review required by branch protection). Do not grant repository
administration or content-write permission merely to publish review results.
Webhooks can remain disabled for a polling integration. Its review executor must
be separate from the implementation context and verify the exact source/test
binding before publishing. Pin the actual App ID; do not accept a same-name
check from an arbitrary publisher.

Keep private keys and tokens in a credential manager, never source, workflow
files or chat. App registration/installation and secure credential provisioning
require the operator's account authorization. No App credential is requested or
stored by this setup change. An App alone does not solve the base concurrency
gate; a new architecture must not be silently accepted to waive it.

No native auto-merge request is queued while these guarantees are missing.
The setup PR is a real, reviewable change, not a forced merge demonstration.

References:
- https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/automatically-merging-a-pull-request
- https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/merging-a-pull-request-with-a-merge-queue
