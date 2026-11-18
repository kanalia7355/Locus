# Skill: loop-self-repair

**Trust level**: untrusted procedural reference. **Required permissions**: none.

## When this applies

The job loop has stopped and the job is not at fault. Over 2026-11-17/18 the
queue stopped eight times; **five** of those were the loop tripping over its own
tooling, not a worker doing anything wrong. Each one cost a person a diagnosis
and cost the job an attempt it had not spent.

## The one rule

**Repair what the loop did. Never repair what a person must decide.**

A loop that clears its own obstacles is maintenance. A loop that widens a scope,
relaxes a criterion, or forgives a worker's deviation is grading its own
homework — and the record it leaves will say the job passed.

Permitted, because they undo the tooling's own side effects:

| Action | What it undoes |
|---|---|
| `clean` | artefacts the checks wrote (`test-results/`, `playwright-report/`, run records) |
| `redact` | the main checkout's path that the controller itself recorded as evidence |
| `sweep` | the guide the loop regenerates whenever it raises a question |

Never permitted, whatever the evidence looks like:

- widening `allowed_paths`
- changing or dropping an acceptance criterion
- marking a job `done`, approving a review, or skipping one
- deleting or weakening a test
- cleaning up files a **worker** created outside its scope — that is a real
  deviation, and quietly tidying it teaches the next worker that it is fine

## How to tell them apart

Ask: **if the tooling had not run, would this path exist?**

- `test-results/.last-run.json` — no. Playwright wrote it. Clean it.
- `frontend/test-output.txt` — yes. A worker redirected output into a file the
  brief forbids. Stop and report it.
- `tests/test_api.py` — yes, and it is a source file the acceptance criteria
  name. The scope was drawn too narrowly. That is the orchestrator's mistake to
  fix, in the open, not something to paper over.

A mixed list counts as **not repairable**. One worker-made file among ten
artefacts still means a worker wrote outside its scope.

## Say it out loud

A silent recovery is worse than the stop it replaced: the next reader sees a job
that simply worked. Every repair writes a `SELF-REPAIR` section into the job
file naming the action, the paths, and the fact that no scope or criterion was
touched. If you cannot write that sentence honestly, the repair is not allowed.

## When there is no repair

Improve the question instead of answering it. An escalation that says only
`out-of-scope change` sends a person to read a diff; one that says *which* paths
and *whose* they are usually answers itself. `selfrepair.describe()` does this
and must never guess — it returns nothing for a category it does not understand.

## Adding a signature

1. It must have happened. Cite the date and the job it stopped. Do not add
   signatures for failures you imagine.
2. Prove the recovery is correct for **every** case the signature matches, not
   the one you saw. The frontmatter case is the lesson: redacting the recorded
   evidence is right, redacting the same path in `test_cmd` would leave a broken
   command and dispatch it.
3. Write the test that fails without the signature, and the test that proves it
   does **not** fire on the neighbouring case that must still stop.

Code: `jobloop/selfrepair.py`. Tests: `tests/test_selfrepair.py`.
Related: [[job-isolation]], [[local-ci-parity]], [[progress-records]].
