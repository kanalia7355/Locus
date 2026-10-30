# Development governance v1
## Objectives
Build a secure, maintainable, LAN-deployable research knowledge assistant. User intent matters, but instructions require critical technical evaluation.
## Agent topology
One main agent performs analysis, design, implementation, testing and fixes. No routine subagents or parallel delegation. Exception: independent read-only reviewer for significant architecture/data model changes, authentication/authorization/security/external communications, and before protected-branch merge. Consolidate overlapping triggers into one review.
Review must use a fresh context focused on specifications, diff and test evidence, not the implementer's reasoning. Reviewer cannot edit, spawn agents, access secrets, or use external services without approval. Reviewer implementation (Codex/new session/etc.) remains undecided. Do not assume policy prose enforces technical limits: install/test runtime guards where supported.
## Review loop
Initial independent review, then at most TWO fix + re-review cycles. Block merge for unresolved critical/high severity issues; escalate with evidence after limit. Reject unsupported review claims with documented reasons. Reviewer report: severity, location, reproducible evidence, impact, fix recommendation.
## Delivery loop
Requirement critique -> acceptance criteria -> design/ADR -> tests -> implementation -> automated verification -> risk-based independent review -> fixes -> evidence-based report. Do not claim tests passed unless run. Stop on unclear security decisions. Use small vertical slices and minimize scope.
## Resource governance
Record review invocations, elapsed time and usage if available. No unbounded retries. Runtime limits are mandatory where available; document unenforceable caps. Do not auto-merge or change protected branches without authorization.
## UI
Researcher UI emphasizes chat, file upload, source citations, analysis and plots. Admin UI emphasizes understandable role templates and drill-down configuration. No credits/billing UI. Prefer fast perceived response, streaming, reusable components and accessible patterns. Avoid checkbox grids for primary permissions UX.

## GitHub delivery
Follow `docs/governance/GITHUB_WORKFLOW.md` for all changes. PR titles and squash merge subjects must use Conventional Commits. Independent review and required CI gate protected-branch merges; never bypass them.
