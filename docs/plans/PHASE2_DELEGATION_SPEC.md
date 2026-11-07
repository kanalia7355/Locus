# Phase 2 delegation specification (draft)

Status: design draft for owner decisions; **not approved**. This document specifies
fail-closed authorization semantics for the later PH2-D implementation. The
【要決定】 items below are blockers for any behavior that depends on them; this
draft does not silently select their values.

## Grounding and security invariants

The product requires delegated administration bounded by permission subset,
scope, and expiration, with audit and no privilege/self-escalation. The Phase-2
reconciliation row says time-limited delegation currently returns 409 and the
expiry/cancellation semantics are unresolved; the endpoint in `backend/app/main.py`
currently always returns that 409. Keep the endpoint disabled (409) until the
spec is approved and PH2-D is implemented and verified. Nothing here authorizes
bypassing that guard early.

Current `service.py` resolves a single project membership to a built-in or
project-local custom role; `_permissions` and `require` are the live permission
path. Custom role create/update is limited to the actor's effective permissions
intersected with `NON_ADMIN`; publication is restricted to same-project role
IDs and `read`/`retrieve`, and read/retrieval authorization is rechecked against
current membership, role, and publication data. Administrative writes use
`BEGIN IMMEDIATE` transactions and `_audit` metadata rows in the same
transaction. The existing data model does not implement organization-scoped
memberships or active delegations. In particular, organization scope and
project-level role membership must not be conflated.

Mandatory invariants for any future implementation:

- Deny by default. A grant is an additional, explicit, time-bounded authorization
  input; it does not bypass authentication, resource ownership, project
  membership, publication ACLs, or any other existing check.
- Recompute authorization from current persisted state at every authorization
  point. Do not rely on session-start snapshots or long-lived authorization
  caches. An expired or revoked grant denies immediately at the next check.
- A grant can never create a permission, scope, recipient privilege, or
  administrative capability that its grantor cannot currently exercise and
  delegate in that same scope. No self-grant or indirect self-escalation.
- Existing roles and publication grants remain in force as independent gates;
  delegated permissions never expand a document's publication operations or
  alter its allowed role audience.
- Existing denials remain effective. PH2-B explicit deny overrides allows as
  specified there; this document does not redefine its precedence.

## 1. Grant model and storage/audit proposal

A delegation is an explicit grant from one authenticated grantor (actor) to a
*different* recipient for a finite permission set, an explicitly bounded
organization or project scope, and a finite expiry. The grantor must pass a live
authorization check for the management action and each delegated permission in
each scope unit. The service must bind the actor to the current session and
perform checks and writes in one serialized transaction, following the live
session-binding pattern used by user administration and the transaction pattern
used by role changes.

Proposed logical grant fields (storage representation is subject to review):

- stable grant-family ID and immutable version ID/number;
- grantor user ID and recipient user ID (not usernames);
- exactly identified scope kind and scope ID, with no wildcard or implicit
  cross-organization scope;
- canonical, deduplicated permission identifiers;
- server-generated creation time and absolute expiry time (derive expiry from
  the authoritative current time plus a requested TTL after applying the
  approved bound; never trust a client-supplied past/future absolute timestamp);
- lineage/parent grant reference if re-delegation is later authorized;
- lifecycle events for revocation/cancellation, rather than silently replacing
  grant contents.

Prefer append-only versioned grant facts: a changed grant is a new version and
must not rewrite historical grant parameters. Revocation should be represented
as an append-only lifecycle fact or equivalent versioned state that can be
queried efficiently for live authorization. The implementation must define a
single unambiguous current-version/current-state query and enforce it
transactionally; no stale version may become effective again. This follows the
Phase-2 versioned-row design direction without asserting that the current
`roles` or document `grants` storage is already immutable (it is not: role rows
are updated in place and publication grants are replaced in place).

Grant creation/renewal/revocation and their `_audit`-style events must commit or
roll back together. Audit is metadata-only: actor ID, operation, target grant ID
(or version ID), outcome, timestamp. Do not record permission payloads, user
content, secrets, or sensitive names. Failed authorization/mutation must not
leave a successful grant or success audit record. Follow current SQLite epoch
seconds (`time.time()` stored as REAL) for timestamps; represent instants
consistently in UTC epoch seconds, compare expiry with `now >= expires_at`, and
obtain `now` at each live check. Use the authoritative service/database clock;
clock-source behavior and permitted skew for production adapters remain
【要決定】. If the database clock changes or an expiry cannot be validated,
fail closed.

### Interaction with existing roles and document publication

A grant is not a role assignment and cannot edit or supersede one. For each
request, effective authorization is computed from the applicable current role
holdings plus applicable active delegation grants, subject to all existing
resource checks and PH2-B's explicit-deny semantics. The delegated contribution
is bounded by its exact grant scope and permission subset. This union is not a
way to mint a role, raise the grantor's ceiling, or bypass role-editor ceilings.
Role creation/update must continue to enforce the existing non-administrative
allowlist and current actor ceiling. A delegation containing a permission does
not itself make that permission delegable; the grantor must independently have
the permission and delegated-administration authority.

Publication remains a separate document-level allowlist: recipient access to a
shared document requires the existing project membership and publication role
match and operation grant, as well as current `read`/`retrieve` authorization.
A delegation cannot add publication entries, widen `operations`, make
`retrieve` imply `read`, expose private/attachment documents, or revive a
removed publication. An expired/revoked permission must also be filtered from
historical citations and generated answers at read time, following the current
live citation and answer-visibility checks.

## 2. Expiry, renewal, and live rechecks

A grant is valid only while all of these are true at the authorization point:
its current version is active, it has not been revoked/cancelled, the current
instant is before its expiry, its grantor/recipient accounts remain enabled,
its scope and permission match the request, required current membership and
resource checks pass, and the grantor's authority/lineage remains valid under
the approved policy. Expiry is an immediate deny at `now >= expires_at`; there
is no grace period. No background cleanup job is required for safety, and
cleanup must never be the enforcement mechanism.

Check live grant state at every API/data authorization point, including project
listing/effective-access preview; role and membership management; document
listing, metadata, body, chunks, related items, exports; chat creation/history;
retrieval, citations, generated-answer visibility; attachment paths; and
background/queued work before processing, before any sensitive side effect or
content release, and at the final transaction that persists results. Recheck
again after external or otherwise long-running work before returning or
committing derived output. Do not copy delegated authority into a session, queue
job, model prompt, or long-lived cache. A queued job must not preserve authority
beyond the grant's live validity.

The current code uses floating-point Unix epoch seconds and `time.time()` for
session, temporary credential, recovery, and job expiry. Follow that convention
in this SQLite implementation, use a consistent UTC instant, and avoid
comparing formatted local-time strings. Production database clock and
cross-host skew policy require an owner decision; until a trusted clock policy
exists, uncertain expiry is deny. Boundary tests must make the exact-expiry
condition explicit (`now == expires_at` denies).

Renewal is a new authorization decision, not an extension that resurrects an
expired/revoked row. Require a live authenticated actor, recompute current
scope/permission ceiling and grant authority, apply the approved maximum TTL,
and create a new immutable version with fresh created/expiry times in a
transaction with metadata audit. It cannot enlarge scope or permissions as a
side effect; any enlargement is a new grant request fully revalidated against
the grantor's current ceiling. The prior version and its expiry/revocation
history remain auditable. 【要決定】 whether renewal keeps the same grant-family
ID or creates a new one, and how the default maximum TTL is configured.

No specific minimum/maximum TTL or default duration is selected here.
**【要決定】 default and maximum expiry/TTL, minimum TTL, whether clients may
request arbitrary expiry within the bound, and who may change the configured
bound.** Until answered, PH2-D must not invent a duration; delegation remains
unavailable for production use.

## 3. Revocation/cancellation and in-flight work

An authorized grantor or other owner-designated revoker may revoke/cancel only
within explicitly authorized scope. The change takes effect transactionally
and immediately at the next live authorization check, without requiring
logout, session replacement, worker restart, or cache invalidation. This mirrors
the Phase-1 disable/revoke behavior: current credentials remain subject to
live checks, and ongoing ingestion checks its actor and permissions again
before scanning/finalizing. The analogous grant tests must prove revoked
permission is not used by a live session or queued/background operation.

Revocation must not wait for expiry. It must be monotonic: revoked grants and
versions cannot be reactivated; a later grant requires a new authorization
transaction and auditable version/fact. Account disable, membership removal,
role permission reduction, grantor authority loss, ancestor-grant expiry or
revocation, and applicable explicit deny must all cause the relevant delegation
not to authorize further work. Do not cascade a broad account or unrelated
project change beyond its defined scope.

For in-flight operations, authorization checks are linearization points. If
revocation/expiry is observed before a protected read/release, mutation, scanner
call, model dispatch, external side effect, or final result commit, stop that
operation and do not release or persist protected data. For streaming or
multi-step work, recheck before each protected release/side effect; stop future
output when denied. Work already lawfully disclosed before revocation cannot be
recalled, but no later fetch of old conversation citations or generated answers
may expose content that no longer passes live checks. Use a final serialized
transaction for state changes where applicable, as current ingestion and
administrative paths do. Define cancellation outcome and cleanup for partial
work without weakening existing data isolation.

Record metadata-only grant revoke/cancel audit in the same transaction. Failed
revocation must not falsely record success; idempotency/response semantics and
whether a recipient can request cancellation are **【要決定】**. Do not permit
recipient self-service cancellation to mutate grant authority until that
policy is decided.

## 4. Self-privilege-escalation denial

Deny grant creation if the actor is the recipient, if grantor and recipient
resolve to the same user ID, if any requested permission is unknown, if the
permission is not currently effective for the actor in the complete target
scope, if the actor lacks the separately required authority to administer
that delegation, or if scope/expiry exceeds the actor's authority. Never trust
client-supplied role, effective-permission, organization, or ceiling values;
resolve them from current database state within the transaction.

For each grant, prove the requested permission set is a subset of the grantor's
current delegable effective permission ceiling at the target scope. A grantor
cannot obtain a new permission by issuing it to a second account, by creating
or editing a custom role, by publishing a document, by selecting an organization
scope over projects where they lack authority, or through a grant chain. Do not
allow a grant to the actor's own alternate identity if an identity-equivalence
or account-link mechanism exists. Detect/reject cycles and stale parent grants
if re-delegation is ever approved. Explicitly deny self-grant even when the
caller has system-admin status; system-admin exceptions and grant authority
remain unresolved rather than implicit.

The recipient's other roles do not validate an over-broad grant: every
requested grant is checked against the grantor's ceiling independently. Union
with the recipient's permissions cannot feed back into the grantor ceiling.
A permission that is denied by PH2-B remains denied even when any grant or role
allows it. Invalid attempts produce no grant state or successful audit record.

## 5. Subset and scope narrowing

- **Permission:** use only known backend permission identifiers. Requested
  permissions must be a strict or equal subset (never a superset) of the
  grantor's current effective and explicitly delegable permissions, evaluated
  per scope. Keep permission dependencies such as `retrieve` requiring `read`.
  No new backend capability can be created through a grant. Preserve the
  current `NON_ADMIN` restriction for custom role creation/update; do not infer
  that a grant can lift it.
- **Project scope:** a project-scoped grant names exactly one existing project
  and cannot be used in another project, even in the same organization.
  Project deletion/reassignment and organization changes must invalidate or
  re-evaluate scope; never silently retarget a grant.
- **Organization scope:** an organization-scoped grant is bounded to that
  organization and never crosses organization boundaries. It does not imply
  system-wide access or silently become a grant over future projects. Each
  concrete project/data operation must still resolve to the same organization
  and satisfy the existing project membership, ownership, publication, and
  permission checks. The current service has project-level membership and no
  organization-role authorization path, so PH2-D must not invent an
  organization-admin capability; the owner must decide whether org-wide grant
  support is in scope now or whether only project grants are enabled initially.
  This limitation is **【要決定】**.
- **Resource ceiling:** a project/org grant cannot widen document publication
  grants, private-history ownership, attachment/conversation binding, or any
  other independent ACL. Scope is an upper bound, not a replacement for those
  checks.
- **Union:** under PH2-B's concurrent-role design, applicable allowed roles and
  delegation permissions may be combined only under its union semantics; a
  grant contribution stays within its own scope and the grantor ceiling.
  Explicit deny overrides the union. Do not implement an alternate union or
  deny algorithm here; PH2-B owns those semantics.
- **Re-delegation:** a recipient cannot issue onward grants by implication.
  **【要決定】** whether re-delegation will ever be supported. Until expressly
  approved and specified, the safe behavior is no re-delegation; do not create
  a grant lineage feature that assumes it is allowed.

## 6. Concurrent roles and explicit deny (PH2-B interface)

PH2-B owns concurrent role holdings and explicit-deny model and precedence.
PH2-D must integrate with that approved implementation instead of duplicating
or contradicting it. Authorization must take the current PH2-B effective
permission result, add only current grants applicable to the exact actor,
permission, and scope, and then apply PH2-B's deny behavior exactly as defined
there. A grant may not suppress an explicit deny. Role/membership changes
invalidate no-longer-authorized delegations immediately through live
recomputation; no cached union or grant-derived role assignment is permitted.

If the PH2-B contract or data model is not available when implementation starts,
block the dependent integration rather than guessing. Cross-task questions
about whether a grant adds a holding, a permission source, or scope-specific
allow must be resolved consistently by PH2-B and the owner before PH2-D is
considered ready; this spec does not decide PH2-B's internal model.

## 7. Regression-test plan: reconciliation verification column

Retain and run all existing tests, especially `tests/test_custom_role_publication.py`,
`tests/test_role_updates.py`, `tests/test_administration_audit.py`,
`tests/test_security.py`, and the complete backend suite. Add focused service/API
regressions with independent principals, projects, and organizations; assertions
must prove both allowed behavior and denied behavior without weakening existing
security tests or the disabled endpoint before implementation is approved.

### Actor, organization, and scope matrix

- Two users in one project; same organization but different project; different
  organizations; non-member; disabled account; role with lower permission;
  project/organization mismatch. Confirm no cross-user, cross-project, or
  cross-organization disclosure or administration.
- Project grant permits only its exact project. Organization grant (if approved)
  is limited to its organization; membership, ownership, and publication remain
  required. Unknown, deleted, moved, or mismatched scopes deny.
- Grantor without the requested permission, without delegation-management
  authority, or without authority in one child project cannot issue a wider
  grant. Recipient's preexisting higher role does not permit the grantor to
  exceed their ceiling.
- Test valid subset, equal subset, strict subset, duplicate permission
  canonicalization, empty/unknown permission sets, invalid permission
  dependency, and attempted superset. Assert failed requests create neither a
  live grant nor a success audit event.
- Self-grant, same-user ID, alternate/self-linked identity if supported,
  indirect/circular grant attempt, custom-role escalation, publication-based
  escalation, and system-admin self-target attempts deny explicitly.

### Expiry and version lifecycle

- Valid before expiry; denial at exact expiry and after; expired permission
  immediately absent from a live authenticated session; no grace period or
  cleanup-worker dependency.
- Renewal recomputes current ceiling and creates auditable fresh state; expired
  and revoked versions cannot be revived; renewal after role/membership loss,
  account disable, ancestor invalidation, or expired parent denies.
- Exercise clock boundaries with a controlled clock. Validate epoch-second
  precision/conversion and fail-closed behavior for invalid or unavailable time.
- Verify all active-version queries select exactly one current version under
  concurrent create/renew/revoke requests and that transaction/audit failure
  rolls back the change.

### Revocation, races, and all protected data paths

- Revoke while the recipient remains logged in. Next request denies without
  logout. Cover project list/effective-access output, role/membership admin,
  document list/metadata/body/chunks/related, conversation create/list/history,
  citations/generated-answer visibility, attachments, and every implemented
  search/retrieval/export path.
- Match the Phase-1 `test_security.py` callback/race style: change grant or
  grantor/recipient membership, role permissions, account enabled state, or
  explicit deny while scanning/processing/long work is in progress; assert no
  stale content reaches scanner/model/output and no protected result is
  committed or returned after the final check.
- Queue work while a grant is active, then expire/revoke before dispatch and
  before finalization. Confirm queued jobs do not retain authority, stop safely,
  and produce no protected output. Test revocation at each defined
  in-flight/streaming authorization point; already released output is not
  represented as retractable.
- Revoke/expire a `read` or `retrieve` source permission after a generated
  answer exists. Confirm current citation filtering and whole-answer hiding
  continue to prevent partial stale disclosure.
- Ensure publication removal, changed custom role permissions, and document
  ownership/attachment rules still deny despite an active delegation. Ensure
  granting access elsewhere does not change the publication allowlist.

### Audit and non-regression

- Create/renew/revoke records contain IDs, operation, outcome and timestamp
  only; assert no permission payload, document/message content, secrets, or
  sensitive names appear.
- Inject audit failure for each transactional mutation and assert full rollback;
  assert denied/failed operations do not write success events. Test the
  documented behavior for idempotent revoke after owner decision.
- Verify PH2-B explicit deny overrides grants and union does not escape scope.
  Existing role updates keep the same ceiling and immediately affect
  publication/data access.
- While PH2-A is a draft and until PH2-D is authorized, retain a regression
  proving `POST /api/admin/delegations` returns 409. Only an approved PH2-D
  implementation may replace that test with enabled-path cases; no unrelated
  security test may be removed or weakened.

This matrix is the proposed evidence for the Phase-2 verification column:
**異なる利用者/組織/権限変更中の全データ経路、委任subset/scope/expiry、自己昇格拒否**.

## 8. 【要決定】 owner decision inventory (not decided here)

1. Default and maximum grant TTL, minimum TTL, expiry input rules, and policy
   owner/configuration path.
2. Whether re-delegation is allowed; if yes, lineage, parent invalidation,
   ceiling, depth/cycle limits, and audit details.
3. Who may grant and revoke: project owner, organization administrator,
   system administrator, or another role; whether grant authority itself is
   separately permissioned and delegable. Current code does not define
   organization-level membership/administrator enforcement.
4. Whether organization-wide grants are in PH2-D or only project-scoped grants
   are initially supported; how future projects and org/project moves behave.
5. Whether a grantor's continuing authority is a live dependency, and exact
   behavior on grantor role reduction/removal, account disable, or parent
   grant expiry/revocation. This draft recommends live invalidation, fail
   closed, but owner must confirm this security-impacting policy.
6. Whether the recipient may cancel/request revocation; who can revoke an
   issued grant; idempotent revoke response and audit policy.
7. Re-grant/renewal identity and version semantics (same family/new family),
   whether scope/permissions may change on renewal, and whether overlapping
   grants are allowed or deduplicated.
8. Timestamp authority and allowable clock skew across production hosts;
   SQLite currently uses `time.time()` epoch seconds, but production DB/clock
   is not selected.
9. Whether `manage_roles`/`manage_members` or other administrative permissions
   are grantable at all, and what delegable-permission catalog applies. Current
   role editor only permits `NON_ADMIN` custom-role permissions.
10. Whether grants can confer project access without an existing membership.
    This draft says no; membership remains an independent gate.
11. Data retention for expired/revoked grant versions and audit entries, and
    any administrative listing/redaction requirements.
12. Concurrency/user-visible response semantics when revocation races a
    request, including any future streaming path. Security behavior must still
    deny at the next authorization point.

## Source-code observations and boundaries

Verified files: `backend/app/service.py`, `backend/app/main.py`,
`tests/test_custom_role_publication.py`, `tests/test_role_updates.py`,
`tests/test_administration_audit.py`, and `tests/test_security.py`, plus the
Phase-2 breakdown, reconciliation Phase-2 row, product spec, and architecture.

The reconciliation and job-breakdown documents call the delegation path disabled
with 409, but the actual source endpoint is specifically
`POST /api/admin/delegations`, and the job breakdown describes the disabled path
as existing. The code contains no delegation storage or active grant logic at
all: it is only a disabled placeholder. This difference in wording does not
change the fail-closed behavior or authorize enabling the endpoint. Also, the
reconciliation describes live publication grants and role subset checks, which
are present, but role rows and document grant JSON are mutable in place; this
spec's append-only/versioned delegation proposal is a new design direction, not
an existing convention already implemented for those records.
