# Implementation log

2026-10-31: user authorized bootstrap and phased development. Explicit clarification approved a local development prototype using synthetic data only; production recovery, delegation, retention and LAN exposure remain disabled pending approval. Single implementer; audit-only subagents.

Initial inspection: documentation/reference-only directory, no Git repository or package manifests; Python 3.13 and Node 22.16 available; Docker daemon unavailable. Existing user documents preserved. See ADR 0002 for scope and acceptance criteria. Implementation and actual verification results will be appended as work progresses.

## Implemented and verified

- Created local branch `chore/bootstrap-prototype`; no commits, remote configuration, pushes, PRs or merges.
- Added the local-only FastAPI service, Argon2id/temporary credential/session flow, scoped role and document authorization, owner-private conversations/attachments, default-quarantined ingestion, fixed synthetic seed path, live citation reconstruction and audit metadata.
- Added the React/TypeScript/Vite/Tailwind UI using Lucide SVG controls and the approved chat layout. Screenshots at320/375/414/768/1024px were inspected; mobile capture now waits for sidebar/grid transition completion rather than capturing an intermediate state.
- New tests were run before core service implementation (missing module failure), then passed after implementation. Both audit regressions were demonstrated failing before fixes. The credential-error UI regression likewise failed before correction.
- Final `scripts/verify.py --e2e --audit`: all12 checks exit0. Python22 tests, UI4 tests, actual API Chromium5 E2E tests; Python coverage88%. Ruff, mypy, ESLint, TypeScript/Vite build, pip check, offline secret scan and both advisory audits passed. Secret findings0; known advisory findings0. These results apply to the tested local development paths.
- Initial venv pip24.3.1 advisory findings were corrected by upgrading to26.2.2 and recording the exact version in the Python lock. Dependency license inventories contain63 Python and297 npm metadata entries with no missing license field. Production distribution review remains open.
- Independent design audit followed by fresh-context implementation audit. The implementation audit found two medium issues; fixes and regressions passed first re-review. No second fix cycle needed. See `docs/reviews/2026-10-31-prototype-audit.md`.

## Documentation versus implementation

These are explicit development exceptions, not silent product decisions: SQLite instead of the proposed PostgreSQL/pgvector stack; lexical quoted-source retrieval instead of a local LLM/vector/GraphRAG pipeline; loopback development instead of LAN deployment; scanner-unavailable quarantine instead of production parsing; production recovery/delegation/retention and cloud disabled. Original placeholder READMEs were retained and annotated as historical where implementation was added. The approved reference HTML remains reference material, not executable product code.

Full product acceptance, performance capacity, production security and remote CI/branch enforcement are not claimed. Remaining work is tracked in PHASE_STATUS.md and RISK_REGISTER.md. Host-level reviewer restrictions could not be technically enforced through the available Codex API and are explicitly recorded as unenforced.
