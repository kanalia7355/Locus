---
name: requirement-triage
description: Use when choosing what to build next, filling a phase queue, or deciding whether a remaining requirement is implementable now or needs an Owner decision.
---

# Turning requirements into a job queue

## Purpose and authority

Pick the next work from the frozen requirement states instead of from intuition,
and separate "we can build this" from "someone must decide this". This Skill is
procedural knowledge only: it cannot approve a requirement, change a gap state,
widen scope, or start deferred work.

## Where the truth is

- `docs/plans/REQUIREMENTS_TRACEABILITY_MATRIX.md` — 92 requirement IDs, each
  with a **frozen gap state** and a "remaining work" column. Read the state, do
  not infer it from the code.
- `docs/plans/PHASE_STATUS.md` — what each phase has delivered and what it has
  explicitly **not** declared complete.
- `docs/planning/*` — the product intent. The concept note also marks which
  capabilities are deliberately *later* extensions; that ordering is a
  requirement, not a suggestion.
- `docs/plans/FINAL_ACCEPTANCE_CRITERIA.md` — the bar for the end, not for a job.

These are Owner-owned. Triage reads them and writes jobs under `progress/`.

## Procedure

1. Group the IDs by gap state and count them, so the queue is chosen against the
   whole picture rather than the first interesting row.
2. For each candidate, read its "remaining work" sentence literally. If it names
   a selection, an approval, a deployment, a provider, a retention period or a
   format decision, it is **not** implementable now — it is an Owner decision.
3. Keep a candidate only if all of these hold:
   - every value it needs already exists in the repository or the requirement;
   - it can be verified by a command that exists;
   - it fits inside a set of paths you can name in advance;
   - it does not require touching a specification or a protected path.
4. Write each kept candidate as one job: requirement ID, background with the real
   file and symbol names, implementation steps that start with *read this code
   first*, acceptance criteria that a test can decide, `allowed_paths`, and a
   runnable `test_cmd`.
5. Write the rejected candidates into the phase summary **with the reason and the
   requirement ID**, so "not now" is a recorded decision rather than an omission.
6. State the limits you are not allowed to invent. Where a requirement says
   "measure before claiming", the job measures and reports; it never sets a
   target.

## Shapes that make a good job

- **Prove the current behaviour**: enumerate the real paths, then add a negative
  test per path (permission revoked, resource deleted, state changed). Fix only
  what the tests actually catch, and say which path leaked.
- **Make an existing rule visible**: surface a configured bound and an observed
  value through an existing read-only endpoint, changing no bound.
- **Report instead of hide**: itemise outcomes with explicit reasons, reusing the
  exact rules the write path already enforces, so the report cannot drift from
  the behaviour.

## Shapes that are not a job yet

- Anything whose first step is "choose a provider / format / period / platform".
- Anything that needs a sandbox, an isolation boundary or an approval ADR that
  does not exist.
- A capability the plan places in a later phase, however easy it looks.

## Boundaries

- A job queue is not an authorization: deferred items stay deferred until the
  Owner decides, and a convenient implementation is not a decision.
- Do not restate a frozen gap state as "done" because the code looks right;
  completion needs the evidence its row demands.
