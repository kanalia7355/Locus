# Job loop (`python -m jobloop`)

A deterministic controller that moves Locus development forward one job at a
time, using free OpenCode models as workers, and stops to ask the owner whenever
a judgement call appears. It drives the existing task protocol in
`progress/<phase>/tasks/*.md` (`docs/agent/PROTOCOL.md`) — it is not a second
source of truth, and it does not replace `loop_engine` or the `pi` harness; it
never writes `.pi/`, `.loop/`, `loop_engine/`, `docs/plans/` or `docs/planning/`.

## Commands

```text
python -m jobloop doctor      # can the loop run at all?
python -m jobloop status      # what the loop sees: jobs, attempts, models
python -m jobloop plan        # which job it would pick next
python -m jobloop run-one     # one job through one full cycle
python -m jobloop run --minutes 60 [--max-jobs 8] [--push]
```

Options: `--phase <slug>` (default `phase-4-closeout`), `--branch <integration>`
(default `loop/local-development`), `--python <interpreter>`.

## What one cycle does

1. **Select** the lightest actionable job: `status` is `todo`/`doing`,
   `attempts < 3`, and it declares both `allowed_paths` and `test_cmd`. A job
   with an undecided scope is never actionable — an unknown scope is not an open
   scope.
2. **Dispatch** one implementation worker in its own git worktree
   (`.jobloop/worktrees/<id>`, branch `loop/<id>-<slug>`) with a brief that
   carries the job, its boundary and the repository skills to follow.
3. **Verify deterministically** — the controller, not the model, checks:
   - every changed path is inside `allowed_paths` and outside the protected set;
   - the job's own `test_cmd` passes;
   - `ruff check` / `ruff format --check` when Python changed, and the offline
     secret scan whenever anything changed.
   A gate that could not run counts as failed, never as passed.
4. **Review independently**: a *different* free model reviews read-only
   (`CONSTRAINTS.md` §5-5). The controller fingerprints the worktree before and
   after; if the reviewer changed anything, its verdict is void and the job goes
   to the owner.
5. **Deliver** only on `APPROVED` plus green gates: one Conventional Commit in
   the worktree, then a `--no-ff` merge into the integration branch. `main` is
   never touched. `--push` pushes the integration branch.

## Isolation

Each job runs in **its own local clone** of the integration branch, placed
outside the repository (`../.jobloop-<repo>/workspaces/<id>`), and the worker
session is started with `opencode run --standalone`.

Both parts are load-bearing, and both were learned the hard way on 2026-11-15:

- A **linked git worktree is not isolation**. Its `.git` is a file pointing back
  into the main repository, so a session started inside one resolves its project
  root to the main checkout and edits *that* — three times, with the worktree
  left untouched. A local clone has its own `.git` and no link back.
- `--standalone` stops the CLI reusing a shared background service whose
  directory is wherever it was first started.

A fresh clone has no `node_modules`, so the installed tree is linked in before the
job starts; frontend gates would otherwise fail for a reason unrelated to the job.
The reviewed commit is `fetch`ed from the clone and then merged, because the clone
is a separate repository.

## Caps and rotation

- 3 attempts per job, 2 review cycles per job (`PROTOCOL.md` §5.4).
- Usage exhaustion is **not** a failed attempt: the model goes on a 6-hour
  cooldown in `.jobloop/roster.json` and the next eligible model takes over.
- Only free and local identifiers are eligible — `opencode/*-free` and
  `ollama/*`, intersected with what `opencode models` actually reports. A paid
  route can never enter the roster, so a loop cannot quietly spend money.

## What it escalates instead of deciding

Each of these stops the job, sets `status: blocked`, and appends a question to
`progress/<phase>/OWNER_DECISIONS.md`:

- the worker replied `needs-owner-decision: <question>`;
- the work needed paths outside `allowed_paths`, or touched a protected path;
- three attempts did not satisfy the acceptance criteria;
- the review cycle limit was reached with changes still required;
- no second model was available, so the review would have been a self-review;
- the reviewer modified the worktree;
- the integration branch was dirty when a reviewed commit was ready.

The run keeps going with other jobs, and prints the pending decisions at the end.

## Skills the loop depends on

Registered in `.agents/skills/SKILLS_REGISTRY.md`:

- `job-isolation` — how a worker is contained, and how an escape is detected.
  Read it before changing where a workspace is placed or how a session starts.
- `requirement-triage` — how a phase queue is chosen from the frozen requirement
  states, and what must become an Owner decision instead of a job.
- `progress-records` — how the task files and phase summaries stay true.
- `local-ci-parity` — why a local green is not a hosted green in this checkout.

The implementer brief hands workers `systematic-debugging`,
`verification-before-completion` and `local-ci-parity`; the reviewer brief hands
`quality-review`, `security-audit` and `verification-before-completion`.

## What it deliberately cannot do

Approve its own escalation, push or merge `main`, open or merge a pull request,
modify specifications, relax a gate, install packages, or reach a network service
other than the model CLI the owner authorised.
