# Autonomous loop engine — usage and current limits

The user specification is preserved verbatim in [AUTONOMOUS_LOOP_SPEC.md](requirements/AUTONOMOUS_LOOP_SPEC.md). The engine is additive: the research UI/API remains in frontend/backend. Python3.11+ CLI code has no FastAPI/React dependency. State is in `.loop/runtime/state.sqlite3`, excluded from Git.

**This is not a completed live autonomous runtime.** Local state, planning import, controller logic, approvals, Git worktrees and mocked external integration are implemented/tested. The default CLI execution transport is `UnprovenBoundary`: start/model planning cannot launch real tasks until a complete isolated executor is implemented and verified. Human approval cannot turn missing isolation into proof. Real auto-merge is also blocked because gh's head guard cannot atomically bind a PR base ref. These are unfulfilled acceptance gates, not successful substitutes.

The additive [Development Loop](architecture/ADR-0005-development-loop.md)
assesses latest main before scheduling and after observed merges, plans grounded
improvements without replacing Goal criteria, detects stalled quality and applies
a deterministic completion gate. See [Bootstrap status](LOOP_BOOTSTRAP_STATUS.md)
for actual versus synthetic validation. `loop launch 2h` requests a new bounded
run; `loop launch --resume 2h` resumes the same run in a new time window. Neither
activates an unavailable executor or authorizes product development.

## Install and inspect

```powershell
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
./.venv/Scripts/python.exe -m loop_engine.cli --version
./.venv/Scripts/python.exe -m loop_engine.cli doctor --check-sandbox
./.venv/Scripts/python.exe scripts/verify_loop.py --audit
```

The installed console entrypoint also supports `loop ...`. Doctor reports versions and authentication booleans without credential values. The optional sandbox probe runs only synthetic local Python code through the installed CLI, never an LLM; failure does not cause an unrestricted retry. A successful basic command alone would still not prove credential/control-plane/MCP/network isolation. Authentication availability is distinct from source-sending authorization and API billing limits; monetary caps are not guaranteed.

## Goal and planning

```powershell
loop --project C:/path/to/project init --goal-file C:/path/to/nonconfidential-goal.md
loop --project C:/path/to/project plan --file C:/path/to/reviewed-plan.json
loop --project C:/path/to/project status
loop --project C:/path/to/project decisions
```

Init exclusively creates missing files and leaves existing AGENTS/Skills/specifications intact. Source Goal, requirements, architecture, acceptance and config are frozen on import. Tasks must use the exported task schema, zero attempts/version and initial planned/ready states; plan-schema tasks form an acyclic graph. Re-import into an existing immutable plan is refused rather than replacing acceptance. Generated requirements/design proposals are separate files.

`plan` without `--file` uses the actual read-only Codex adapter when a proven boundary is available; currently it blocks. It does not fabricate a deterministic task list and call that AI Goal analysis. All exported schemas live in `.loop/schemas/`.

## Human decisions

```powershell
loop decisions
loop approve DEC-... --target-hash EXACT_HASH --reason "Reviewed this scope"
loop reject DEC-... --target-hash EXACT_HASH --reason "Outside approved scope"
loop revise DEC-... --target-hash EXACT_HASH --reason "Revise the proposal"
```

Multiple decision IDs can be supplied when they share the exact supplied target hash; the batch validates fully before any update. Actor, reason, timestamp and immutable target hash are persisted. Preexecution scope approval binds task/spec/base/policy, while final delivery approvals bind the exact verified change. Changed hashes never inherit old approvals. Rejected/revise work stays held; changing immutable scope requires a new reviewed plan rather than resetting attempts.

Medium design/dependency changes can be recorded for deferred review. Production/publication, confidential-access expansion, destructive operations, security policy relaxation or billing are not silently authorized. Model results can request decisions only. Source/backend boundary enforcement is required to prevent a worker invoking the human CLI or editing DB; a prompt instruction alone is insufficient.

## Run controls

```powershell
loop start
loop start --background
loop pause
loop resume
loop stop
loop report
```

Only an explicit start can request a background controller. Init/import does not spawn one. Current start blocks at the unavailable isolation/authorization gate, so these commands are not a claim that the supplied machine is ready for unattended operation. Tests replace the transport/controller factory in code; no mock/unsafe selector is exposed by CLI or environment.

One task at a time, maximum3 worker attempts total including review repairs, maximum2 review-fix cycles. Time/task/run counters persist across pause/resume. Repeated explicit new start can begin a new run budget, but cannot reset a task's implementation attempts. Missing profiles, required skipped checks, malformed output, authentication failure, uncertain state and unavailable review never become success. Task, verification, review, approval, PR, CI and merge state remain distinct.

Process output is bounded in memory; raw model prompts/tool output/authentication details are not saved. Only validated, credential-pattern-checked structured results and metadata are persisted. Pattern checks cannot recognize every kind of semantic confidential content: use approved nonconfidential source and Goals only.

## Git and delivery

An approved committed base is required. Locus now has a committed baseline and the private `kanalia7355/Locus` origin. Its initial default branch is `feat/autonomous-loop-engine`; `main` has not been created. The configured `main` base therefore cannot run real task worktrees yet. Bootstrap validation uses a separate validation base and never silently creates main. Task worktrees use `loop/TASK-ID-slug`. Local delivery does not integrate changes into main. A dependent real-worktree task needs prerequisite merge evidence in its approved base; local completion alone cannot make prerequisite code appear in another checkout.

All worker-produced staged/index changes are refused before verification; the controller validates its own prospective staged tree before commit. No reset/clean/force-push, hook bypass or default-branch direct commit exists. Installed executable Git hooks/filters/custom configuration require separate assessment; the engine blocks instead of disabling them. Tests use isolated known fixtures and label their fixture-specific configuration treatment.

Remote writes are disabled until exact repository/base/change publication approval. Effective fetch and all push destinations must match that authorization. PR create intent and lookup prevent blind duplicate replay; uncertain creation/commit outcomes require recovery assessment. PR creation alone never completes a task; exact head/base and required CI/trusted review identity must be evidenced for PR delivery.

Auto-merge defaults off. Same-name Actions checks cannot establish independent review. A separately authenticated publisher must match branch-protection app identity and publish the exact head/base/policy binding. Strict current-base protection, resolved conversations, complete required checks, low risk, allowlisted paths and exact human authorization are necessary. The current gh API cannot atomically constrain the base ref at merge time, so the real adapter reports `atomic_base_binding=false` and does not merge—even if all other predicates pass. This limitation remains engineering work; no repository rule is weakened to hide it.

## Recovery and reports

State changes and execution claims are transactional, generation-checked and lock-protected. Unknown executors block every new task. Recovery examines active stages, unsettled executions, worktree identity, commit intent and PR uncertainty; it never kills a stored PID or blindly repeats a remote mutation. A human approval by itself does not prove an orphan is gone.

Windows subprocesses are created suspended, assigned to a kill-on-close Job, then resumed. Tests confirm child death after a successfully assigned owner dies. A controller crash between process creation and assignment can leave a suspended orphan; recovery therefore retains an uncertainty gate rather than claiming every creation-stage crash is contained. POSIX parent-death containment is unproven and Windows-specific tests are skipped there.

Markdown is derived from DB. Preexisting/user-edited reports are preserved when ownership receipts do not match. A concurrent editor changing an engine-owned file between receipt check and replacement can still race: do not edit generated report files while the controller writes them; use separate notes. Report receipts are not an OS-enforced coordinated editor protocol.

## Verification status

Local unit/integration/mocked CLI E2E, real temporary Git operations, process timeouts/output bounds and Windows lifetime tests are run by scripts/verify_loop.py. The research app retains scripts/verify.py and its browser E2E. New CI defines Windows/Linux and Python3.11/3.13 checks, but remote CI is not executed/verified here. Skipped platform/live checks are not claimed passed. See [phase ledger](plans/LOOP_IMPLEMENTATION.md) and [audit record](reviews/2026-10-31-loop-audits.md) for evidence and unresolved gates.

The final advisory command found no known vulnerabilities in installed third-party dependencies. pip-audit explicitly skipped this unpublished local engine package because it is not in PyPI's advisory inventory; that is not a security clearance of the engine itself. Source audits, tests and the unfulfilled live boundaries remain separate evidence.
