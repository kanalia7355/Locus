# Product acceptance is unchanged

# Product specification (proposed)
## Purpose
On-premise or private-network research data management and AI-assisted analysis for laboratories, organizations and individuals. Confidentiality is a first-class requirement. Existing lab book and GraphRAG systems motivate this work, but no existing code is assumed.
## Core capabilities
- Browser UI available to authorized clients on a LAN; optional VPN/reverse proxy with explicit administrator configuration. LAN membership alone never grants authorization.
- Organization/project/user separation, private chat histories, document-level ACLs and permission-filtered retrieval including vector and graph traversals.
- RAG answers with traceable document/page/chunk citations; GraphRAG provenance visualization, not unsupported confidence claims.
- New uploads parsed, scanned, indexed and linked to existing material asynchronously; this is retrieval index updating, not LLM training.
- Chat with attachments, data exploration, plots, research discussion and hypothesis support. Mark AI-generated analysis as suggestions, not verified findings.
- Local LLM mode for strictly private workloads. Cloud APIs only for explicitly allowed data and administrator-authorized egress; no UI automation of consumer chat services.
- Administrator-issued unique user IDs and one-time temporary passwords; force password reset on first login. No plaintext password storage; hash with Argon2id. Secure recovery and session revocation.
- Built-in role templates: system admin, organization admin, assistant admin, project lead, researcher, research assistant, general user, viewer, guest, auditor. Administrators can clone/name/configure roles within their own delegable permissions; cannot invent new backend privileges.
- Delegated administration constrained by permission subset, scope and expiration, with audit logs and no privilege escalation or self-escalation.
- UI settings: role presets, permission chips, scope selectors, advanced overrides and effective-access preview. No credits/billing.
## Out of scope for first prototype
Full autonomous research, fine-tuning, unrestricted cloud connectivity, automatic privileged delegation, multi-organization federation, billing, and production-grade high availability.
## MVP vertical slices
1. Auth + forced password rotation + sessions.
2. Organization/project/role ACL with denied-by-default tests.
3. File ingestion + provenance-aware local RAG.
4. Chat UI + source citations + per-user history.
5. Admin role editor + delegation and audit trail.
6. Optional GraphRAG visualization, plots and approved cloud adapter.
## Acceptance criteria
Every retrieval path enforces ACL; users cannot see other users' histories; local-only mode has no external egress; unauthorized API access is denied server-side; source citations link to actual indexed content; first-login password change is enforced.

## Product and UI refinement — 2026-10-29
See `../planning/research-app-concept.md`, `../planning/UI_IMPLEMENTATION_BASELINE.md`, and `../planning/ui-and-multiuser-design.md` for the latest folder ingestion, personal documents, drag-and-drop chat attachments, role-and-scope publication, and multi-user design. The UI baseline records the user-selected final demo. Provider, capacity and retention decisions remain open.


## Completion evidence

All Goal acceptance must have current-head required checks, independent project review and no major unresolved issue. One task PR is not Goal completion. Unapproved or unimplemented subsystems remain incomplete; never weaken criteria or auto-confirm architecture/provider/security decisions.
