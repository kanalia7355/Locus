---
name: progress-records
description: Use when reading or writing `progress/<phase>/PROGRESS.md` or a task file, or when a record and the repository disagree about what was verified.
---

# Keeping the progress records true

## Purpose and authority

The files under `progress/` are how agents hand work to each other
(`docs/agent/PROTOCOL.md`). They are evidence, not narration: a reader must be
able to tell what ran, on which head, and what did not run. This Skill is
procedural knowledge only — it grants no permission and cannot transition a task
or Phase.

## Format rules that break silently

- The frontmatter is parsed line-by-line as **single-line scalars** between a
  leading `---` and the next `---`. No nesting, no lists, no leading blank line.
  A nested value is not "ignored", it breaks the parse for every reader.
- `status` is exactly one of `todo` / `doing` / `review` / `qa` / `done` /
  `blocked`. Anything else is a broken file, not a new state.
- `updated` must be rewritten on every edit: pollers detect work by `status` or
  `updated` changing, so an edit without it is invisible.
- `attempts` is an integer with a limit of 3. A model's **usage exhaustion is not
  an attempt** (`PROTOCOL.md` §5.4), and neither is a controller or harness
  defect. Reset a wrongly-charged attempt and say why in the file.
- Read and write these files as **bytes**. `Path.read_text` translates CRLF to
  LF, so a tool that reads text and writes back rewrites every line ending in the
  file and buries the real change in the diff.
- Edit only the field or section you mean to change; never regenerate a file a
  worker or reviewer wrote.

## What a record must contain

1. **Commands actually run**, with their real results — including failures,
   skips and timeouts. "Tests pass" without the command and the counts is not
   evidence.
2. **The head the evidence belongs to.** Evidence from another commit is stale.
3. **A negative control for any new test**: show that it fails without the fix.
   A test that cannot fail proves nothing, and saying so is cheap.
4. **Known deviations, named as deviations** — for example an independent review
   that could not be performed, with the rule it deviates from.
5. **Who decided what.** An orchestrator ruling that widens `allowed_paths` or
   permits an additive test change belongs in the file, with its reason, before
   the work resumes. Keep the frontmatter in sync with the ruling; prose alone
   leaves the enforcement mechanism lying.

## Things that are not true and must not be written

- "CI is green" when the pipeline stopped at an earlier check: the later checks
  **did not run**. Check which checks actually executed before claiming any.
- "Pre-existing failure" without re-running the same check on the unmodified
  head.
- A capacity, performance or readiness claim derived from arithmetic rather than
  measurement — separate "measured" from "derived" explicitly.

## Boundaries

- A record does not grant authority: completion, merge and Phase transitions keep
  their existing gates.
- Never write a credential, token or secret body into a record or log.
- Specifications under `docs/plans/` and `docs/planning/` are Owner-owned; record
  the gap in `progress/`, do not edit the specification to match the code.
