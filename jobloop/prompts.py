"""Build the briefs the implementer and reviewer receive.

A brief carries the job, its boundary and the evidence it owes — not permission.
Both briefs name the repository skills that raise quality, because a free model
with a checklist outperforms the same model without one.
"""

from __future__ import annotations

from jobloop.tasks import ATTEMPT_LIMIT, Task

# Guidance a worker in a job workspace can actually act on. The operator-facing
# skills (`job-isolation`, `requirement-triage`, `progress-records`) are not
# listed here: a worker neither places workspaces, picks jobs, nor writes records.
SKILLS = (
    ".agents/skills/systematic-debugging/SKILL.md",
    ".agents/skills/verification-before-completion/SKILL.md",
    ".agents/skills/local-ci-parity/SKILL.md",
)
REVIEW_SKILLS = (
    ".agents/skills/quality-review/SKILL.md",
    ".agents/skills/security-audit/SKILL.md",
    ".agents/skills/verification-before-completion/SKILL.md",
)

BOUNDARY = """Hard boundary, enforced by the controller after you stop:
- Work only inside the directory named above. It is your own clone of the
  repository. Other checkouts of the same repository may exist elsewhere on this
  machine; writing to one of them is a containment failure, your work is
  discarded, and the job goes to the owner. Use relative paths.
- Change only the paths listed under `allowed_paths`. Every other path, and in
  particular `.pi/`, `.loop/`, `loop_engine/`, `docs/plans/`, `docs/planning/`,
  `docs/governance/`, `docs/agent/`, `.github/` and `pyproject.toml`, is rejected
  and the job is handed to the owner instead of being committed.
- Never delete, skip, relax or rewrite an existing test, assertion or acceptance
  criterion to make a check pass. The controller re-runs the checks itself.
- Never write a credential, token or password literal into any file.
- Do not commit, push, merge, rebase or touch another branch. The controller
  commits once your work passes its gates.
- Do not install packages, fetch remote scripts or call a network service.
- If the job cannot be done inside this boundary, or the specification is
  ambiguous, stop and say exactly what decision is needed. A stop with a clear
  question is a good outcome; a guess is not."""


def implementer_brief(task: Task, *, attempt: int, repository: str) -> str:
    """`repository` must be the job's own workspace, never the main checkout."""
    return f"""You are the single implementation worker for one Locus job.
Your working copy is {repository} and nothing outside it is yours to change.
This is attempt {attempt} of {ATTEMPT_LIMIT}.

Read these first, in this order:
1. `AGENTS.md` and the governance files it points to.
2. The job text reproduced at the end of this brief. It is the authoritative
   copy — the file in your worktree may be an older revision, so where they
   differ, this brief wins.
3. The existing code the job touches, before you change any of it.
4. These skills, and actually follow them: {", ".join(SKILLS)}.

Job: {task.id} (weight {task.weight or "unspecified"})
allowed_paths: {", ".join(task.allowed_paths)}
Verification command the controller will run: {task.test_command}

Method:
- Reproduce or express the requirement as a failing check first, then make it pass.
- Match the conventions of the surrounding code: its naming, its comment density,
  its error handling. Where documentation and code disagree, follow the code and
  say so in your report.
- Keep the change as small as the acceptance criteria allow.
- Run the verification command yourself before you finish.

When you are done, reply with exactly these sections and nothing else:

REPORT
- what you changed and why, file by file
- any inconsistency you found between the documentation and the code
- any risk you are leaving behind

TEST
- the commands you ran, with their real results (including failures)

STATUS
- exactly one line, and nothing else on it. Either the literal text
  `ready-for-review`, or `needs-owner-decision:` followed by the real question you
  need answered, written out in full. Never copy this instruction's wording as
  your question, and never report a question you have not actually got.

{BOUNDARY}

--- job text ({task.path.name}, authoritative) ---
{task.body.strip()[:12000]}
--- end of job text ---"""


def reviewer_brief(task: Task, *, diff: str, evidence: str, repository: str) -> str:
    """`repository` must be the job's own workspace, never the main checkout."""
    return f"""You are an independent read-only reviewer for one Locus job.
The working copy under review is {repository}; nothing outside it is in scope.
A different model wrote this change. You did not write it, and you may not fix it.

Hard rules: do not create, modify or delete any file; do not run git commands
that change state; do not commit, push or merge; do not spawn other workers. The
controller verifies the worktree is byte-identical after you finish and discards
your review if it is not.

Job: {task.id}
Acceptance criteria are in `{task.path.as_posix()}` under TASK DEFINITION.
allowed_paths: {", ".join(task.allowed_paths)}

Controller evidence (already verified deterministically, do not re-run):
{evidence}

The change under review:
```diff
{diff}
```

Review in this order and use these skills: {", ".join(REVIEW_SKILLS)}.
1. Security and boundaries: does the change weaken a permission check, an access
   rule, an audit record, a resource bound or the local-only rule?
2. Correctness: give a concrete failing input or sequence, not a style opinion.
3. Acceptance: is every criterion actually met, and actually asserted by a test?
4. Test honesty: would the new tests fail if the implementation regressed? Was
   any existing test weakened or removed?

Reply with exactly these sections and nothing else:

VERDICT
- one line: `APPROVED` or `CHANGES_REQUIRED`

FINDINGS
- one bullet per finding: severity (High/Medium/Low), file:line, what is wrong,
  the concrete failure scenario, and the smallest fix you would recommend.
- write `none` if you found nothing material. Do not pad with praise.

UNVERIFIED
- anything you could not check, and why."""
