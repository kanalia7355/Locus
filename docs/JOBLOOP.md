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

## What it deliberately cannot do

Approve its own escalation, push or merge `main`, open or merge a pull request,
modify specifications, relax a gate, install packages, or reach a network service
other than the model CLI the owner authorised.
