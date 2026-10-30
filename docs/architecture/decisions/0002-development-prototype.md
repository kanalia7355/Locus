# ADR 0002 — Local synthetic-data development prototype

Date: 2026-10-31. Status: accepted for development only by user instruction in this session.

The user authorized bootstrap and phased implementation, then explicitly approved local development only, no external AI, no real research data, with production recovery, delegation, retention and LAN exposure disabled pending decisions. This does not settle ADR 0001 for production.

## Boundaries

- FastAPI, React/TypeScript/Vite. Python 3.13 is available locally. No remote repository, push, merge, automatic issue intake, model download or cloud connection is authorized.
- SQLite is an isolated, replaceable prototype repository using parameterized SQL and foreign keys, not the approved production database. No vector engine or model is selected. Local lexical retrieval returns verbatim excerpts with document/page/chunk provenance; it must never claim LLM generation.
- Bind loopback only. Reject unexpected Host/Origin and cross-origin mutations. No CORS wildcard, no external fonts/scripts, no service analytics. Production launch fails closed. Deployment-layer outbound restrictions remain a production prerequisite, not an application guarantee.
- Admin provisioning is a local interactive CLI, without default accounts or committed passwords. Argon2id password hashing, expiring one-time temporary password, mandatory first-login change. Random opaque sessions are stored as digests; HTTP-only SameSite=Strict cookies are loopback-development only. Rotation revokes existing sessions. Generic login errors, bounded rate limiting, logout/revocation, and no self-escalation.
- No recovery/MFA workflow or live delegation; those operations return an explicit unavailable response. Existing role templates are backend-defined. Admin-created custom role permissions must be a subset of the actor's delegable permissions and scope. No arbitrary backend privileges.
- Tenants and projects are explicit. Every document/chunk/citation/history/graph operation rechecks live authorization. Administrators receive no automatic access to personal documents or conversations. Owner-private attachments are bound to a single conversation and never automatically published. No cross-user cache.
- Upload prototype supports bounded UTF-8 text/Markdown/CSV only, with size/name/type/encoding checks and no active-content rendering. A scanner interface is mandatory; the default scanner fails closed and leaves uploads quarantined when unavailable. Only tests and an explicitly synthetic sample-seeding CLI use a fixture scanner. No executable parser, OCR, remote connector or model processing.
- Bounded background ingestion queue, visible state and cancellation. Deletion removes derived chunks; authorization is rechecked at job execution and history/citation read. Queue capacity is a safety bound, not a performance claim.
- Stored history consists of user text and citation IDs; retrieved excerpts are rebuilt from currently authorized sources on read, avoiding stale source text after permission changes. Conversations are owner-only; reference scope is explicit.
- Audit events contain operation, actor ID, target ID and outcome, never credentials, document text or chat text. Retention and production backup policies remain pending.

## Acceptance and sequencing

Phase 0: pinned installs, reproducible lint/type/unit/integration/E2E checks, audit/secret scan, CI, measured limitations and bootstrap evidence.
Phase 1: temporary expiry, forced rotation, hash/session protections, failed-login limits, logout and invalid session tests.
Phase 2: cross-tenant/project isolation, private data isolation, server-side admin restrictions, role subset checks and denied-by-default regressions.
Phase 3: quarantine without scanner, synthetic successful ingestion, queue bounds/cancel, citation accuracy, deletion and revocation tests. Production scanner and actual local LLM remain pending.
Phase 4: approved chat layout, accessible persistent sidebar controls, IME-safe submission, shared file/drop path, attachment states/removal, source view, own history, responsive browser checks.
Phase 5: role/scope/operation preview, backend subset validation, metadata-only audit. Live delegation remains disabled.
Optional Phase 6 / roadmap Phase 5: ACL-filtered provenance relationships may be implemented; cloud adapter, model execution, plots and capacity claims remain pending concrete requirements and approvals.

## Review controls

Initial independent design audit found no critical/high issue within this scope. Medium clarifications adopted before implementation: exact Host/Origin allowlists and missing/null-Origin mutation rejection; rotation-only sessions with 30-minute idle/8-hour absolute expiry, 24-hour temporary-password expiry and single-use temporary login; transactional source/permission/cancellation checks before ingestion publication; fixture scanner cannot be selected through HTTP or environment; only system administrators provision identities and assign built-in project roles, while project role editors can create non-administrative permission subsets in their current project. Administrative delegation is always disabled.

Only the main agent implements. One fresh-context read-only reviewer is permitted for architecture/security audit. Reviewer must not edit files, spawn agents, access secrets or network. At most two fix/re-review cycles. The current collaboration interface does not expose a per-reviewer filesystem sandbox or enforceable token/time cap: these restrictions are procedural, not technically guaranteed. A local guard module and tests can constrain project-owned automation, not the hosting agent tool system. No protected-branch merge is permitted without trusted review checks.
