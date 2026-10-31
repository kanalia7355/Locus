# ADR 0007 — Proposed exact-base automatic merge architecture

Status: PROPOSED, requires operator approval before implementation/activation.
No existing Goal criterion, retry cap or safety gate is relaxed.

## Observed problem

Public visibility now permits branch protection and GitHub auto-merge, but the
current personal repository cannot use GitHub's organization merge queue.
`github_manager.py` consequently continues to return atomic_base_binding=false.
Expected-head matching alone cannot close a base-change race. An independent
authenticated review publisher is also missing.

## Proposed personal-repository design

- A dedicated review service uses a repo-only Review App: Contents read, Checks
  write, Pull requests write. It invokes the fresh read-only reviewer, verifies
  current head/base/policy and test binding, and publishes the bound check plus
  the actual approving review. Model text alone is not signing authority.
- A separate Merge App has only repo Contents/Pull requests write. A trusted
  serialized broker is its only credential consumer and only merge entrypoint.
  It rechecks source, trusted review, CI, current base, conversations, risk,
  allowlists and approvals, then performs an immediate expected-head squash
  merge under its lock, retaining the lock through result reconciliation.
- A separate main-update restriction admits only that Merge App. The existing
  CI/review protection remains independent, without bypasses. Exemption from the
  writer restriction must never exempt the App from required checks/reviews.
  This API capability and denial behavior must be live-tested before relying
  on exclusive-writer serialization.
- Native future-head auto-merge requests are not used by this broker. All main
  writes, including operator-requested manual merges, go through the broker;
  otherwise the exclusive-writer guarantee does not hold. Administrative policy
  changes invalidate its attestation and stop it.
- App keys/tokens stay in the credential manager and trusted broker, outside
  model tools, source, CI jobs, prompts and logs. Initial service binaries/source
  hashes need independent review and explicit operator activation; they must
  not execute signer code supplied by an untrusted PR.

This changes the operator's manual-merge path and introduces privileged service
identities, so general permission to try auto-merge is not treated as automatic
approval of this material architecture change. App creation/installation needs
one-time operator account authorization; no credential is requested in chat.

## Required validation

Prove that other actors cannot update main; concurrent requests serialize;
head/base/policy changes fail closed; failed/missing/cancelled CI cannot merge;
untrusted code cannot publish trusted review or reach App credentials; crashes
reconcile without duplicate writes; and limits/Goal/previous attempts survive
the main/policy state migration. A synthetic pass is not live proof.

Until approved and proven, use PR delivery with protected manual review. Moving
to an organization-backed merge queue would be a different owner/scope decision
and is not performed automatically.
