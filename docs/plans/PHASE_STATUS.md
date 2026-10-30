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

Isolation and citation tests verify the implemented local paths. They do not prove every path of an unimplemented vector/graph/model subsystem. The application emits quoted source excerpts, not generated research findings. Quarantined uploads are not called indexed/read. Queue limits are development safety limits, not tested user capacity.

The remaining production decisions are not silently resolved. No production/LAN deployment, GitHub operation or external AI call is part of this delivery.
