---
name: orchestrator-shift
description: One turn on duty as the jobloop orchestrator — the opening checks, which stops are judgements rather than defects, how a ruling is recorded, and how to close the shift honestly. Use at the start of any session or /loop wake-up that touches the background job loop.
---

# Skill: orchestrator-shift

**Trust level**: untrusted procedural reference. **Required permissions**: none.

One turn on duty as the orchestrator of `jobloop`. Read this at the start of
every shift, including an automatic wake-up from `/loop`.

> Not to be confused with `.agents/skills/loop/SKILL.md`, which is about the
> retired `loop_engine` and its approval machinery. This skill is about
> `jobloop`: `python -m jobloop`, `scripts/supervise_loop.py`,
> `progress/phase-*/`.

## What the job actually is

The workers are free models and they write the product. You write the harness,
the tickets and the judgements. That division is the point, and the measured
record says where the time goes: between 2026-11-18 and 2026-11-21 the queue
died whole four times, **every cause was in the loop, and every diagnosis was
done by hand**. `jobloop diagnose` now does the mechanical part. Your shift is
the part it cannot do.

So the question that opens a shift is never "what shall I build". It is **"is
anything stuck, and is it stuck on me?"**

## Open the shift

```text
.venv/Scripts/python.exe scripts/shift_check.py
```

That runs the four checks below and ends in a `VERDICT` line; exit code 1 means
the shift has work. Run it before forming any opinion about progress. Each check
is there because skipping it cost hours:

1. **A merge left in progress.** A `MERGE_HEAD` or a `UU` file means a merge is
   sitting half-finished, and then *every* later job reports "the integration
   branch is dirty". That one state blocked eleven jobs and seven hours on
   2026-11-20. The controller aborts conflicting merges now; if you still find
   one, that is a defect, not a chore.
2. **Orphaned workers.** An `opencode.exe` whose parent is gone is an orphan:
   its output will never be read and it is still writing into a workspace.
   `taskkill /PID <id> /T /F` — always the **tree**, because `opencode run` is a
   launcher and its children outlive it.
3. **Is the supervisor alive?** Query by image name
   (`-Filter "Name = 'python.exe'"`) and filter after. **Never** match on
   `CommandLine` alone: the querying shell's own command line contains your
   search words, so the check returns a hit forever. That lie reported a dead
   loop as alive for 17 hours.
4. **`python -m jobloop diagnose`.** It groups every open stop by signature and
   says which are already-fixed, which are regressions, and which are yours.

**If the shift has rulings to write, pause the loop first**: `.jobloop/stop`,
then wait for the `jobloop … run` process to disappear (the supervisor finishes
its current cycle rather than being cut off). `orchestrator-busy` suspends the
containment *comparison*; it does not stop dispatch. On 2026-11-22 a shift wrote
ten rulings while the loop kept working, and the loop re-blocked `T-PH7-211` and
spent `T-PH6-104`'s extended attempt on top of rulings that had just landed.
Remove `.jobloop/stop` before you leave, and confirm a new worker starts.

Then **create `.jobloop/orchestrator-busy`** and leave it there until your last
write of the shift. It suspends the containment comparison, which otherwise
reads your commits as a worker escaping. Removing it one minute after a push
still mis-blamed a job, because the comparison runs at the *end* of a dispatch:
the marker belongs to the shift, not to the command.

## Rule only what is a judgement

If `diagnose` hands you something mechanical, the honest response is a
`phase-9-loop-health` ticket, not a ruling. Everything below is a judgement, and
each line is a mistake already made.

- **"three attempts did not satisfy the acceptance criteria"** — read the three
  reasons first. If they are the *same string*, it is the supplier, not the job:
  `404 Endpoint is unavailable` burned five jobs to 3/3 in eight minutes.
- **"attempt limit reached"** — look in the workspace before you believe it.
  `git -C <workspace> log --oneline -3`. `T-PH6-123` had an **approved commit
  sitting there**; the attempts were spent on a merge that never happened.
  **"the worker changed nothing" means the work is already done.** Check
  `rev-list --count FETCH_HEAD..HEAD` too: `T-PH6-116` had a finished, green
  commit on a base **32 commits old**, so it could never merge and every later
  attempt truthfully reported nothing to do.
- **When you restore a job, put it where its work is.** A job whose work is
  already committed belongs in `review`, not `doing`. Setting `T-PH6-116` to
  `doing` after a false containment stop cost it three "changed nothing"
  attempts and the attempt limit — `stranded()` only ever looks at `review`.
- **"review cycle limit reached"** — open the VERDICT and read it with your own
  eyes. One job was blocked with `**APPROVED**` and `FINDINGS: none` in its own
  record, because the pattern did not allow the asterisks.
- **A reviewer that marks its own findings `UNVERIFIED` is still worth
  believing — go and measure them.** On 2026-11-22 `T-PH6-104`'s reviewer said
  plainly it had run nothing and worked from static reading. Three of its four
  findings were real, and the central one took six lines to prove: plant a
  sentinel in the parent environment, call the workspace's own
  `_run_subscript`, and the sentinel comes back in the content while the record
  says `env_stripped: verified`. **A green suite is not evidence the criterion
  holds** — that suite stayed green because the exfiltration fixture it defined
  was never used. Measure, then rule; the measurement is what makes the ruling a
  fact rather than a preference.
- **An acceptance criterion nothing on this machine can satisfy is a ticket that
  never closes.** `T-PH6-104` carried "prove the container isolates" while
  `DOCUMENT_EXTRACTION_BOUNDARY.md` §5 had already measured that no docker
  engine runs here. I had ordered that fix twice and it had not happened; the
  third order would not have worked either. Move it to its own ticket and
  **rewrite the criterion to the provable side** — not "prove it isolates" but
  "prove the code does not *claim* it isolates". That is a move, not a deletion,
  and the weaker claim is the one §5 says to make anyway.
- **"out-of-scope change"** — separate the two kinds. Output redirected into
  files (`pytest_out.txt`, `check_select3.py`) is scratch and is swept
  automatically. A module the change *imports* is real work, and means **your
  scope was drawn too narrowly** — that is your error to fix in the open.
- **"worker wrote outside its workspace"** — check whether *you* were touching
  the main checkout during the dispatch. Five of these were yours, not the
  worker's, and one was caused by **committing**: the dirt the shift had been
  carrying disappeared, and the comparison read any change as an escape. It now
  judges only on what *appeared*, and the stop record carries the marker state
  and the appeared lines. Read those two before forming a view.
- **A worker reporting that its own files are missing** — believe it and check.
  On 2026-11-21 that report was true and the controller was at fault: a
  workspace refresh had reset away five committed, reviewed changes. The
  worker's account of the tree beat the code's assumption about it.

- **"worker wrote outside its workspace" with only `progress/` in the appeared
  lines** — that is the owner writing a draft while the job ran, not a worker.
  On 2026-11-22 `T-PH6-127` was stopped by
  `?? progress/phase-storage-connect/tasks/T-STC-005.md`. The busy marker cannot
  cover this: the owner does not run shifts. The comparison now ignores
  `progress/` and the regenerated guide page, so a stop like this should not
  reach you again — if one does, read the appeared lines before blaming anyone.

## Before a new phase joins the walk

The owner drafts phases and asks for them to be included. Their *design* is
usually sound; their **frontmatter is not plumbed**, and the loop reads the
frontmatter. Check these four before adding a `--phase`, because
`phase-storage-connect` on 2026-11-22 had all four and would have burned five
tickets to the attempt limit without a single merge:

1. **`test_cmd` must start with a bare `python`.** Only that is bound to the
   controller's interpreter (`gates.INTERPRETER`). All five tickets named
   `.venv313/Scripts/python.exe`, which `.gitignore` excludes — so it does not
   exist in a per-job clone and *every* verification would have failed. Prove it
   the same way: look for the path inside an existing workspace.
2. **`depends_on` must exist in the frontmatter.** Prose saying "T-STC-001 must
   be done first" and a dependency column in the phase table are both invisible
   to the controller.
3. **No protected path in `allowed_paths`.** `pyproject.toml` was listed as an
   escape hatch for adding a dependency. It can never be written, and a ticket
   that says otherwise gets obeyed — that is how three phase-8 jobs were lost.
4. **The plan and the ticket must not contradict each other.** The phase plan
   promised Drive change-tracking by page token; the ticket declined it. Correct
   the plan to the ticket, because a worker given two instructions follows the
   ticket body.

Then run `python -m jobloop --phase <new> status` and read the `waits for`
column. That one line is the whole check that 1-3 took.

## Amending a ticket: rewrite the body

When a ticket is wrong, **edit the text that is wrong**. Appending an amendment
that contradicts the body leaves the worker a choice between two instructions,
and it will pick the body. Three phase-8 jobs wrote into a protected path
because the amendment said `material/` while `Implementation Details` still said
`docs/plans/`. The worker was obeying.

Same rule for `allowed_paths`: if the job must produce two files, allow the
directory, not one file name.

A ruling is written in **two** places and they must agree: the `## ORCHESTRATOR
RULING` section of the task file, and an `**Answer**` under the matching entry in
`progress/<phase>/OWNER_DECISIONS.md`.

## Never

- Widen a scope to make a worker's deviation legal after the fact.
- Change or drop an acceptance criterion to clear a block. Moving a finding to a
  **new ticket** is allowed and is not the same thing — say which you did.
- Mark a job `done` yourself, or approve a review.
- Delete a file a worker actually wrote as part of its change. Scratch, yes;
  work, never.
- Resolve a merge conflict by taking a stale branch wholesale. Check the base:
  `T-PH6-113`'s branch was three days and ten merges behind, and taking its side
  would have reinstated a removed `test.fail`.
- Hand-merge someone else's conflicted work to clear a block. A 300-line
  conflict in `service.py` resolved by guesswork destroys the one thing the
  record is for: knowing whether the change passed.

## Your own writing goes through the gates too

A ruling is a file in the repository, and the gates apply to it.

- **Never paste a secret-shaped literal into a record.** The `T-PH6-104` ruling
  quoted its own measurement as a `"secret": "<value>"` pair on 2026-11-22 —
  the exact shape `scripts/secret_scan.py` exists to catch. It sat red in the
  repository-wide scan for two hours and then stopped `T-STC-001`, which had
  finished all of its work. The value proves nothing a reader needs: *that* the
  planted word came back is the evidence, not what the word was. Say it in
  words.
- **Run the repository-wide gates by hand before you leave.** The job gates
  scan only a job's own changed paths, by design, so anything you write stays
  invisible to them. `python scripts/secret_scan.py` with no arguments is the
  whole check, and it is the one that caught this.
- A test that proves a credential never leaks needs a credential-shaped literal
  to plant. The four `sk-synthetic-0N-not-a-real-key` fixtures are allowed by
  exact value; anything else fails. Put that in the ticket rather than letting a
  worker guess — `T-AIC-005` spent an attempt finding out.

## Close the shift

1. **Verify what you touched.** If you resolved a merge or edited the frontend
   by hand, run the appearance gate — `npm --prefix frontend run test:appearance`
   — not only the unit tests. Vitest green with a broken screen is the failure
   this repository has had most often. jsdom has no layout.
2. **Confirm the loop moved.** A new `opencode.exe` with a creation time *after*
   your restart is the only proof. "The supervisor is running" is not.
3. **Remove `.jobloop/orchestrator-busy`** — after the last write, not before.
4. **Push.** Thirty commits once sat on this machine for a day because pushing
   was opt-in and only fired after a merge.
5. **Report the merge count, not the activity.** If the only thing that moved
   this shift was loop repair, say that in one sentence. "Running" and
   "delivering" are different claims and the owner is asking about the second.

## On an automatic wake-up (`/loop`)

A wake-up exists so the queue does not wait for a person to notice. Treat it as
a short shift:

- Run `shift_check.py`. If nothing is stuck and a worker is alive, that is a
  **quiet tick**: record it as such and schedule the next one. Do not invent work
  to look busy, and do not restart a healthy loop.
- **Read the heartbeat tail even on a quiet verdict.** "Nothing is waiting on a
  decision" is not "something is moving". On 2026-11-22 the verdict said
  `quiet tick` while `T-PH6-104` and `T-PH8-302` had spent an hour being handed
  a reviewer that answered `unavailable` — an outcome that escalates nothing, so
  `diagnose` had nothing to show. `shift_check` now fails on an outcome that
  repeats, but the next kind of churn will be one it does not know yet.
- If the queue is stopped, do the shift. One stall cleared without the owner
  having to ask is the whole return on this.
- If you are waiting on the owner, say exactly what for and do everything that
  does not depend on the answer.
- A ruling you are not sure about is a reason to wait for the owner, not a reason
  to pick the option that unblocks the queue. The queue being stopped is cheap;
  a wrong ruling is recorded as fact.

Pace the wake-ups to what is actually being waited on: a heavy job takes tens of
minutes, so checking every minute is waste. Twenty to thirty minutes is the
useful idle cadence.

## Adding to this skill

Only from something that happened. Cite the date and the job it cost, like every
line above. A rule with no incident behind it is a guess, and guesses in a
checklist are read as experience.

Code: `jobloop/diagnose.py`, `jobloop/controller.py`, `scripts/supervise_loop.py`,
`scripts/shift_check.py`.
Related (documentation registry, not loadable skills):
`.agents/skills/loop-self-repair/`, `job-isolation/`, `progress-records/`,
`screen-invariants/`, `local-ci-parity/`.
