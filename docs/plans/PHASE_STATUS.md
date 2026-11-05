# Phase status — local synthetic-data prototype

Date: 2026-10-31. This tracks implementation progress, not production approval. Roadmap phase numbers are used below; PRODUCT_SPEC's MVP slice numbers differ.

| Phase | Implemented development slice | Remaining product work |
|---|---|---|
| 0 Bootstrap | Python/FastAPI and React/TS/Vite/Tailwind, locked dependencies, lint/types/unit/integration/browser checks, offline secret scan, package audits, CI files, local scripts, ADR/risk/usage records | Remote CI/branch protection/trusted review integration; host-enforced reviewer restrictions unavailable |
| 1 Authentication | Interactive local provisioning, unique IDs, Argon2id, expiring single-use temporary credentials, enforced first-login rotation, opaque digested sessions, idle/absolute expiry, revocation on change/logout, rate limits | Production recovery/MFA/TLS/session deployment policy approval |
| 2 Scoped authorization | Project and organization identity, backend permission templates, per-project membership, private documents/history/attachments, live document-role grants, deny-by-default API tests | Production data model and delegation semantics; live delegation remains disabled |
| 3 Ingestion and retrieval | Bounded text ingestion, source/page/chunk metadata, queue/cancel, scanner default quarantine, synthetic-only successful seed path, lexical search, live permission checks, derived-data deletion | Approved scanner/parser sandbox, PDF/OCR, storage connectors, approved DB/vector/model adapters, resumable distributed jobs |
| 4 Researcher/admin UI | Approved sidebar/chat/composer/icon baseline, accessible navigation, IME handling, file/drop shared path, status/removal, project/reference scope, actual source viewer, owner history, mobile checks | Actual local LLM streaming, representative-user usability and accessibility audit beyond current checks |
| 5 Roles/audit and optional extensions | Project role template cloning with permission ceiling, chips and scope preview, document publication preview, metadata-only audit, user listing | Live delegation explicitly disabled; GraphRAG, plots and cloud adapter deferred until their data/model/provider requirements are approved |

## Acceptance interpretation

2026-11-06: the optional local provenance slice exposes
`GET /api/documents/{id}/related` (optional `conversation_id`). It returns up to ten
currently readable/retrievable same-project documents, ranked by shared lexical
terms, with up to ten actual source/target chunk IDs and page references per link.
Japanese character bigrams support non-whitespace-delimited text. This is an
explainable lexical relationship, not a semantic graph or model-generated finding.
Private documents and conversation-bound attachments retain their live ACLs.
Requests are rate-limited; authorized chunks are still scanned under the prototype
transaction lock, so this is not a production capacity claim. The existing source
dialog can load these relationships on demand, show common terms and page
references, and open the related original through a fresh authorized chunk read.
Pending retrieval is cancelled when its view is discarded. A persistent graph
index, semantic GraphRAG and graph visualization remain unimplemented.

Publication UI now explicitly chooses read-only (the default) or read plus
retrieval, previews that choice with the role and project scope, and warns that
saving replaces existing grants. Failed saves retain the input. Browser tests
use a second user to verify that read-only grants allow source reads but not
chat retrieval or related-document exploration; backend policy is unchanged.

Isolation and citation tests verify the implemented local paths. They do not prove every path of an unimplemented vector/graph/model subsystem. The application emits quoted source excerpts, not generated research findings. Quarantined uploads are not called indexed/read. Queue limits are development safety limits, not tested user capacity.

The remaining production decisions are not silently resolved. No production/LAN deployment, GitHub operation or external AI call is part of this delivery.
