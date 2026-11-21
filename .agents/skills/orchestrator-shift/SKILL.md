# Skill: orchestrator-shift

**Trust level**: untrusted procedural reference. **Required permissions**: none.

One turn on duty as the orchestrator of `jobloop`. Read this at the start of
every shift, including an automatic wake-up from `/loop`.

> Not to be confused with the `loop` skill, which is about the retired
> `loop_engine` and its approval machinery. This skill is about `jobloop`:
> `python -m jobloop`, `scripts/supervise_loop.py`, `progress/phase-*/`.

## What the job actually is

The workers are free models and they write the product. You write the harness,
the tickets and the judgements. That division is the point, and the measured
record says where the time goes: between 2026-11-18 and 2026-11-21 the queue
died whole four times, **every cause was in the loop, and every diagnosis was
done by hand**. `jobloop diagnose` now does the mechanical part. Your shift is
the part it cannot do.

So the question that opens a shift is never "what shall I build". It is **"is
anything stuck, and is it stuck on me?"**

## Open the shift — four checks, in this order

Do these before forming any opinion about progress. Each one is here because
skipping it cost hours.

1. **`git status` in the main checkout.** A `MERGE_HEAD` or a `UU` file means a
   merge is sitting half-finished, and then *every* later job reports "the
   integration branch is dirty". That one state blocked eleven jobs and seven
   hours on 2026-11-20. The controller aborts conflicting merges now; if you
   still find one, that is a defect, not a chore.
2. **Orphaned workers.** List `opencode.exe` and look at `ParentProcessId`. If
   the parent is gone, the session is an orphan: its output will never be read
   and it is still writing into a workspace. `taskkill /PID <id> /T /F`.
   Always kill the **tree** — `opencode run` is a launcher and its children
   outlive it.
3. **Is the supervisor alive?** `Get-CimInstance Win32_Process -Filter "Name =
   'python.exe'"` and then filter. **Never** match on `CommandLine` alone: the
   querying shell's own command line contains your search words, so the check
   returns a hit forever. That lie reported a dead loop as alive for 17 hours.
4. **`python -m jobloop diagnose`.** It groups every open stop by signature and
   tells you which are already-fixed, which are regressions, and which are
   yours. Read it before guessing.

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
- **"review cycle limit reached"** — open the VERDICT and read it with your own
  eyes. One job was blocked with `**APPROVED**` and `FINDINGS: none` in its own
  record, because the pattern did not allow the asterisks.
- **"out-of-scope change"** — separate the two kinds. Output redirected into
  files (`pytest_out.txt`, `check_select3.py`) is scratch and is swept
  automatically. A module the change *imports* is real work, and means **your
  scope was drawn too narrowly** — that is your error to fix in the open.
- **"worker wrote outside its workspace"** — check whether *you* were writing to
  the main checkout during the dispatch. Four of these were yours, not the
  worker's.

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

## Close the shift

1. **Verify what you touched.** If you resolved a merge or edited the frontend
   by hand, run the appearance gate — `npm --prefix frontend run test:appearance`
   — not only the unit tests. Vitess green with a broken screen is the failure
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

- Run the four opening checks. If nothing is stuck and a worker is alive, that is
  a **quiet tick**: record it as such and schedule the next one. Do not invent
  work to look busy, and do not restart a healthy loop.
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

Code: `jobloop/diagnose.py`, `jobloop/controller.py`, `scripts/supervise_loop.py`.
Related: [[loop-self-repair]], [[job-isolation]], [[progress-records]],
[[screen-invariants]], [[local-ci-parity]].
