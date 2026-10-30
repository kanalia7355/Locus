# Bootstrap procedure
1. Inventory repository, environment, OS, runtimes, installed tools and existing files. Never destroy existing work.
2. Read all governance, product, architecture, security and ADR files. List unresolved design decisions and conflicts.
3. Present a short bootstrap plan and ask for approval for installs, network calls, external model usage, secret provisioning and irreversible actions.
4. Create missing directories and placeholder files only; preserve existing contents.
5. Set up frontend React+TypeScript+Vite, Tailwind/shadcn-compatible components; backend Python+FastAPI; PostgreSQL and pgvector are provisional until ADR approval. Keep adapters swappable.
6. Establish lint, type checks, unit/integration/E2E tests, secret scanning, dependency audits and CI. Pin dependencies and licenses after verification.
7. Inspect Superpowers skills and select only single-agent-compatible flows; no automatic remote execution. Install only with approval. Add reviewer guardrails and test them; if unavailable, report unenforced restrictions.
8. Create initial ADRs, implementation milestones and risk register. Do not implement the full product automatically.
9. Run verification, record commands and results in `.bootstrap/complete.json` only if genuinely successful. Otherwise write `.bootstrap/status.md` with blockers.
10. Summarize generated files, verified checks, decisions needing approval and next development slice.

11. Prepare GitHub PR title validation workflow; request authorization before connecting GitHub, pushing branches, enabling auto-merge or changing repository settings. Document branch protection and trusted independent-review status integration as pending until verified.
