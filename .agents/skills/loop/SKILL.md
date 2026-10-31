---
name: loop
description: Start or resume autonomous implementation, QA, PR and safe merge workflows for the current repository.
---

Read AGENTS.md and its required governance documents, then `.loop/goal.md`,
`.loop/requirements.md`, `.loop/architecture.md`, `.loop/acceptance.md` and the
current `loop status` / `loop decisions`. SQLite is authoritative; do not infer
unfinished work from a stale Markdown report or invent approval.

Use the repository's Python environment (`.venv/Scripts/python.exe` on Windows,
`.venv/bin/python` on POSIX). From the repository root actually execute:

```text
python -m loop_engine.cli doctor
python -m loop_engine.cli launch
```

For `$loop 2h`, execute `python -m loop_engine.cli launch 2h` (a new bounded run).
For `$loop resume 2h`, execute `python -m loop_engine.cli launch --resume 2h`
(a new time window for the same run, retaining its task/cycle caps).
Both retain persisted task attempts, dependencies, approvals and evaluation
history. Without a duration, resume retains the existing deadline. Never
increase the configured six-hour ceiling.
Interpret this invocation only within the user's current scope: a Bootstrap
request is not permission to start product development.

The Development Loop evaluates immutable Goal criteria against the latest
approved repository `main`, before selecting work and after each observed
merge. New gaps need file evidence, reproduction, expected effect and
acceptance. SQLite deduplicates findings; attempted task scopes and counters
cannot be reset. Completion requires current-head mandatory verification,
independent project review and no unresolved tasks/gaps/decisions. A stalled
loop is held for human review. Model claims or PR creation alone never mean
the Goal is complete. If main does not exist, report the blocker; do not create
or choose another integration branch on your own.

`launch` checks the OS controller lock, Goal and imported task plan, then calls
the persistent Controller in the background. It preserves attempt counters and
resume budget. A missing Goal/plan, recovery uncertainty or failed execution
boundary is a blocking diagnostic, not successful startup. Report that reason;
do not bypass controls, change permissions, approve decisions, replace Goal
files, or substitute an unbounded chat loop. If no Goal is set, ask for its
outcome, allowed paths and acceptance criteria; planning does not authorize
implementation. If a Goal exists without a plan, explain `loop plan --file` and
the source-only planning boundary rather than starting unrelated product work.

Report the actual launch result, `.loop/runtime/logs/controller.log`, and
`loop status`, `loop decisions`, `loop pause`, `loop resume`, `loop stop`,
`loop report`. Use `python -m loop_engine.cli` if `loop` is not on PATH.
Pending approval must not be treated as permission. Local QA and independent
read-only QA are separate requirements; neither authorizes publishing a review
check as another actor. CI repair shares the task's three-attempt limit and
must preserve tests, CI configuration and acceptance criteria.
