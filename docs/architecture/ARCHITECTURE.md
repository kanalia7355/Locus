# Architecture baseline (subject to ADRs)
Browser SPA (React/TypeScript/Vite) -> FastAPI backend -> auth/authorization -> document and chat services -> ingestion queue -> relational metadata + vector/graph indexes -> LLM adapter (local default, optional cloud with policy gate).
Use shared policy enforcement in every data path, including retrieval, graph neighbors, exports, cached results, background jobs and model prompts. Deny by default, isolate tenants and scope tokens. Document uploads need type/size limits, malware scanning, safe parsing, storage isolation, indexing status and deletion propagation. Use audit logs without sensitive payloads.
Deployment: bind to private interface, firewall/allowlist, TLS where applicable, VPN for remote access; authentication is required even on trusted LAN. No claim that LAN-only access alone protects secrets. Restrict outbound traffic in local-only mode at deployment layer as well as application layer.
Initial stack proposal: React+Vite+TypeScript+Tailwind/shadcn UI, Python+FastAPI, PostgreSQL+pgvector, optional local graph engine, Ollama-compatible adapter, Playwright/pytest/Ruff. Evaluate actual needs, licensing and performance before freezing.

## Design refinement — 2026-10-29
See `../planning/ui-and-multiuser-design.md` for proposed model adapters, bounded dialogue and ingestion queues, shared resource limits, attachment handling, and role-plus-scope publication. See `../planning/UI_IMPLEMENTATION_BASELINE.md` for UI implementation acceptance checks. These proposals do not establish tested capacity or an approved provider.
