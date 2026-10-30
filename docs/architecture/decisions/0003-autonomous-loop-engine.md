# ADR 0003 — Autonomous loop controller, isolated from the research application

Date: 2026-10-31. Status: implementation design for the user's supplied Autonomous Loop Engineering specification.

## Authority and scope

The supplied specification authorizes adding a language-independent Python CLI/controller in this repository, preserving the existing research application. It does not authorize connecting an unspecified GitHub repository, publishing, charging API usage, relaxing permissions, altering protected branches, or overwriting existing AGENTS/Skills. The existing repository has no commits or remote: real worktree execution therefore cannot run here until a human establishes an approved committed baseline. Tests use isolated temporary Git repositories.

Existing AGENTS guidance remains intact; loop-specific startup and result rules will be appended. New seven skills live in `.agents/skills/`. Python project/dependency metadata is added to existing pyproject.toml without removing existing checks. The existing scripts/verify.py remains the application's verifier; a separate engine verifier and CI job cover this subsystem.

## Trust boundary

The deterministic controller owns SQLite state, immutable task/spec hashes, execution counts, approvals, verification and merge decisions. Worker/planner/reviewer JSON is untrusted input validated against strict JSON Schema. No worker self-report completes a task. SQLite transactions, compare-and-set transitions and an OS-released project file lock prevent duplicate execution. Pause/stop are persisted control requests; only the live owning process terminates its own subprocess tree. Recovery never kills an arbitrary persisted PID or silently retries an uncertain operation.

Trusted configuration and acceptance commands are snapshotted before a task runs and kept outside its worktree. The worker cannot change the control-root policy by editing its worktree. Changes to verification scripts, tests, acceptance, policy, workflows, Skills or dependency manifests require separate review/approval. Snapshot mismatch blocks execution; old approvals cannot authorize changed content. No force-push/reset/clean, hook bypass, direct-main commits or administrative merge override is implemented.

All model runs are separate serial contexts; worker child-agent tools are disabled with the documented multi_agent feature switch. Independent reviewers use a fresh read-only Codex execution, never implementation session resume. Sandboxed source context is still model-visible: real data/credentials/ignored files must never enter the worktree. Block sensitive paths, symlinks and credential-bearing remote URLs. Repository policy is not a security sandbox; actual CLI sandbox availability is checked and errors block execution. Existing managed/user controls and rules must not be ignored or bypassed.

Verification runs project commands as code and must use a configured sandbox executor. The controller must not silently fall back to unrestricted host execution when the sandbox is unavailable. Captured model/tool output is bounded and kept in memory; only schema-validated, secret-checked summaries and metadata are persisted. Raw prompts, command output, stderr, authentication tokens and session transcripts are not logged. Redaction detects credential patterns, not arbitrary semantic confidentiality; only approved non-confidential source/Goals may be used.

## State and completion

SQLite tables: goals, tasks, task_dependencies, executions, verification_results, reviews, decisions, pull_requests, checkpoints, events, metadata. Events are append-only through the store API. Task states and transitions are explicit. Dependency cycles and unknown dependencies are rejected atomically. Task attempts are consumed before launching a worker; at most3 total including review fixes. At most2 review-fix cycles, concurrency1, run/task/time limits enforced independently of model usage. Spawn failures, timeouts, invalid JSON, verification unavailable, failing verification, review failure and external-operation uncertainty remain distinct outcomes.

Local implementation status, verification, independent review, approvals, CI, publication and merge are distinct. A verified local implementation can be recorded while GitHub publication is disabled; a PR alone never means completed. A task reaches completed only after the configured delivery requirements (including CI/merge if requested) are evidenced. Dependent tasks require completed prerequisites. No checks means unavailable/skipped, never pass.

Approvals are human CLI decisions tied to exact task+policy+diff hashes and recorded actor/reason/time. Workers can request decisions but cannot resolve them. Deferred-review work may proceed locally while publication/merge waits. Mandatory-preapproval work never launches without a matching approved decision. High-risk work is preapproval-gated even if a planner marks requires_approval=false. Independent ready tasks continue around blocked/awaiting tasks.

## Git/GitHub

One deterministic task branch `loop/TASK-ID-slug` and managed worktree per task. Use local committed base identity, record immutable SHAs and inspect actual diff/path changes rather than trusting files_changed. Checkpoints reconcile Git/DB before repeating commits or PR creation. Remote writes are disabled until an exact repository/base/scope is explicitly configured and approved. PR lookup by repository/head/base plus durable intent avoids duplicate creates. Unknown network outcomes are reconciled before retry. GitHub CLI uses existing credentials through its normal store; tokens are never obtained or printed by this engine.

Safe auto-merge is disabled by default. Enabling the safe mode alone is not human authorization. A current exact authorization, low risk, approved path allowlist, no pending approvals, current base/head verification, successful independent review, all configured required CI checks present/successful for the exact head, verified branch-protection capability, and mergeability are required. Use GitHub native squash merge with head-SHA matching and never admin/bypass flags. Unsupported/ambiguous protection or merge-queue state blocks automatic merging.

## Planning and recovery

`loop plan` either invokes a read-only planner for a strict plan schema or imports a human-provided plan with `--file`; no fake Goal parsing. Preserve the immutable source Goal/requirements/acceptance, and save generated proposals separately. No specification relaxation. Unknown/conflicting decisions enter the approval queue. Stop/pause/resume survives IDE exit because state and control signals are external to the IDE process. Explicit background start is optional; no background process starts during init/import.

Recovery reconciles claimed execution/worktree/head/checkpoint state. Interrupted or ambiguous tasks become blocked for explicit human assessment, preserving attempts. Worktree reuse requires exact identity and clean/expected state. PR and commit state are checked before external mutation; unknown outcomes never cause blind replay. Markdown reports are generated from DB state and atomically replaced only for engine-owned files.

## Validation and known environment constraints

### Initial independent design audit — adopted execution gates

Live planner/worker/reviewer/verifier execution requires negative capability probes proving: no access to control-root/SQLite/approval CLI credentials, no writes to shared Git administrative paths, no network/tool connector mutations, and process lifetime containment. Filesystem read-only alone is insufficient for reviewer isolation. Reject symlinks and Windows reparse points/junctions. Managed/user hooks and rules remain in force; do not bypass them with alternate Git settings or flags. If trusted safe Git execution cannot be established, Git mutation is blocked rather than disabling hooks/filters behind the user's back.

Execution remains unavailable when these capabilities cannot be proven. Mocks test controller decisions but do not certify the installed sandbox. Initial Windows diagnostics already failed; this is an explicit unresolved environment gate, not a successful live integration.

Separate preexecution scope approval (task+base+policy+operations) from exact-diff delivery approval. Approval hashes are not interchangeable. A trusted external review publisher identity, reviewed head/base/policy binding, resolved conversations and server-enforced up-to-date/strict branch checks are required for merge; same-name CI or self-generated review records cannot satisfy that trust. Unknown base races or protection rules block auto-merge.

Orphan subprocess risk blocks every new task until lifetime containment/recovery evidence establishes no remaining executor. Persist run budget/deadline across pause/resume and crashes. Test schema size/nesting, unknown keys, attempts<=3, review cycles<=2, concurrency1, process/output/review deadlines, and unavailable usage/cost telemetry. User-specified `loop/TASK-ID-slug` is an explicit branch-prefix exception to the older governance examples; Conventional Commits subjects remain required.

Six phases are verified separately with schema/unit/integration/mock external E2E tests and independent read-only review. Live integration tests are opt-in and not counted as passed when skipped. Codex0.144.5 and gh2.95.0 are present. `codex exec --help` confirms output-schema/json/ephemeral/sandbox flags. A Windows sandbox diagnostic failed (`CreateProcessWithLogonW` error267); this is a blocker to live sandbox execution until doctor proves a supported configured sandbox works. No unsafe fallback is permitted. No remote or default committed branch exists in the current directory.

Official sources consulted: [non-interactive execution](https://developers.openai.com/codex/noninteractive), [configuration reference](https://developers.openai.com/codex/config-reference), and installed CLI help. The generic `/codex/security` page now concerns the Codex Security product rather than sandbox settings; it is not evidence for sandbox behavior. Current docs and installed help differ on some flags, so capability detection uses the installed CLI and never invents an option.
