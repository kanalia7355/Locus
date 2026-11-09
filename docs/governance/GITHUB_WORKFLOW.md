# GitHub PR / Merge Governance

## Objective

### Dedicated development branch exception (operator authorized 2026-11-02)

The normal autonomous path may use `local_commit_push` as documented in
`../LOCAL_COMMIT_PUSH_LOOP.md`: task-local implementation, mandatory local QA
and independent review, Conventional Commit, fast-forward local integration,
then ordinary Push to the matching dedicated `loop/*` branch. A PR, Review App,
Merge Broker and automatic merge are not prerequisites on this path. Existing
Actions remain additional Push verification. Main Push is not authorized.
Protected-branch merging continues to use every gate below. No force Push,
history rewriting, secret storage, execution-boundary weakening or implicit
approval is permitted. Frozen policy changes use versioned migration.
Every implementation change goes through a short-lived branch and pull request. The default integration strategy is **squash merge** with a Conventional Commits subject. Do not push directly to `main`.

## Commit and merge subjects
Use `<type>(<optional-scope>)!: <imperative summary>` (or omit scope / !). Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`. Breaking changes require `!` and a `BREAKING CHANGE:` footer when appropriate. UI feature changes are not automatically `style`.
PR titles MUST follow this pattern; configure GitHub's squash commit default to **pull request title**, then validate the resulting merge subject. Individual commits should also follow the convention. Examples: `feat(auth): require password rotation on first login`; `fix(rag): enforce document-level access filters`.

## Workflow
1. Confirm approved task and acceptance criteria. Critically review user request and security implications.
2. Create `feat/<slug>`, `fix/<slug>`, etc. from updated default branch. Never rewrite another person's branch.
3. Implement small changes, run tests, linters, security checks; record evidence.
4. Push branch and open PR with Conventional Commits title, problem, solution, test evidence, risks, and review requirements.
5. Run PR title CI and quality checks. Significant architecture/data model changes, security changes, and ALL merges into protected branches require independent read-only adversarial review. Overlapping triggers count as one initial review.
6. Review agent receives specs, diff and test results in fresh context; no write permissions, secrets, or further delegation. Reviewer reports severity, file/line, evidence, and remediation. Main agent owns fixes. Maximum TWO fix/re-review cycles.
7. Merge only when required CI and independent-review status checks pass, all review conversations are resolved, branch protection permits, and no high/critical unresolved findings exist. Enable GitHub native auto-merge only after explicit authorization and repository configuration. Never bypass branch protection or auto-approve own PR.
8. After squash merge, confirm merge commit subject matches the PR title and convention; close linked issue and summarize. If verification fails, report and halt automation.

## Guardrails
- A GitHub Actions workflow alone cannot establish that a separate review happened. An authenticated review runner or trusted human must publish the dedicated required check; an implementer cannot mark its own review passed.
- Secrets use GitHub Actions secrets or a dedicated credential manager; never store in source, prompts, logs, or reviewer context.
- Set least-privilege GitHub App / token permissions; PR creation and auto-merge should be separate permissions where practical.
- Do not start autonomous issue intake, remote PR creation, or auto-merge before the user approves repository, branch rules, and execution scope.
- If repository plan/rules do not support required branch protection or auto-merge, report limitation; do not silently weaken checks.
- CI workflows from untrusted PR branches must not receive write credentials. Avoid `pull_request_target` with checkout of untrusted code.
