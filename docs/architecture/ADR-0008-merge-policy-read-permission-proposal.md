# ADR 0008 — Merge policy read permission proposal

Status: APPROVED FOR IMPLEMENTATION by the operator on 2026-10-31.
The operator explicitly approved Administration read for the repo-only Merge App.
This authorizes implementation and requesting that read permission, not activation.

## Concrete blocker

The broker must freshly inspect classic main protection before merging. GitHub's
[Get branch protection REST API](https://docs.github.com/en/rest/branches/branch-protection#get-branch-protection)
requires repository Administration read for installation tokens. Neither approved
App role grants it. An anonymous read of Locus's endpoint returned HTTP 401;
the owner's existing authenticated `gh` can read it, which does not establish
that a separately provisioned App service can.

## Approved permission delta

For the **Merge App installed on kanalia7355/Locus only**, change its requested
repository permissions from:

```json
{"contents":"write","pull_requests":"write"}
```

to:

```json
{"contents":"write","pull_requests":"write","administration":"read"}
```

The Review App stays Contents read, Checks/Pull requests write. Metadata read is
implicit. No Administration write, owner OAuth credential transfer, account-wide
repository selection, bypass of CI/review protection or native future-head merge
authorization is proposed.

The trusted, pinned broker would use that read scope to inspect the current main
protection and compare the approved policy while holding the global mutex. Its
policy reader must use fixed repository/endpoints and validate raw evidence;
untrusted worker booleans cannot establish policy compliance.

The Review service also needs trustworthy current policy facts. Its own App
scope remains unchanged: it would require a fresh, authenticated broker policy
snapshot bound to head/base/policy/source identity, with replay-resistant service
communication and independent source/QA inspection. That channel and its binding
must be implemented, reviewed and tested before publishing trusted reviews;
neither a worker's pass flag nor an unauthenticated snapshot is sufficient. This
proposal does not claim that the channel already exists.

## Security impact and limits

Administration read exposes repository administration metadata beyond branch
protection, such as collaborator/deploy-key metadata where the API permits it.
It does not grant administration changes or private deploy keys. See the
[deploy-key API permission/response contract](https://docs.github.com/en/rest/deploy-keys/deploy-keys#list-deploy-keys).
The extra scope
is broader than a single-endpoint permission because GitHub does not offer that
granularity. Repo-only installation and credential handling still require live
validation, rotation/revocation and isolation evidence. No key/token goes into
source, prompts, files or CI.

This is a security-scope decision under AGENTS.md: "If a decision materially
affects confidentiality, security or scope, ask first." Approval would authorize
implementation and the App's read-permission request, not unverified activation.
Existing keys need no rekey solely for a permission update; the owner must accept
the installation's requested permission change. Exact returned scopes must then
be validated rather than accepted opportunistically.

## Alternative if the additional scope is declined

Keep both App roles unchanged and design a separately authenticated, pinned
read-only policy inspector using the existing owner authorization, or an
equivalently enforced/readable ruleset policy. Its trust boundary, freshness,
revocation and complete protection equivalence require a separate concrete
design/review. Do not silently copy a broad owner credential into the broker,
replace protection with weaker rules, or claim that this alternative exists.

Neither approach has been activated. All ADR0007 live proofs, independent final
review, Goal/attempt-preserving migration and explicit activation remain required.
