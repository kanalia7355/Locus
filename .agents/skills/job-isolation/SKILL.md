---
name: job-isolation
description: Use before giving a model-driven worker a working directory, or when a worker's changes appear somewhere other than where it was told to work.
---

# Isolating a model-driven worker

## Purpose and authority

Make a worker's blast radius match what it was told to touch. This Skill is
procedural knowledge only: it grants no permission, authorizes no command, and
does not replace the controller's gates, the review requirement, or any Owner
decision. A worker that escapes its directory is a containment failure, not a
style problem — treat its output as unreviewed and discard it.

## The failure this prevents

Observed five times on 2026-11-15 in this repository: a worker was started with
its working directory set to a git **worktree** under `<repo>/.jobloop/worktrees/<id>`,
reported that it had implemented the job, and left the worktree byte-identical —
because the edits landed in the **main checkout**. The controller's own gate
(`the worker changed nothing`) was the only reason it was caught.

Three distinct causes, all load-bearing:

1. **A linked git worktree is not isolation.** Its `.git` is a *file* containing
   `gitdir: <main repo>/.git/worktrees/<id>`. A tool that resolves "the project
   root" by following that link lands on the main checkout, whatever the process
   working directory says.
2. **A shared background service ignores your working directory.** `opencode`
   reuses a background server rooted wherever it was first started unless
   `--standalone` is passed.
3. **Any path to another checkout, anywhere in the brief, is an instruction.**
   A prompt that says "you are working in `C:/Users/you/Repo`" is obvious; the
   subtle version is a path the *job text* carries — a recorded `test_cmd` naming
   the interpreter in the main checkout. A worker with file tools reads either as
   "the project is over there" and edits it. Rewrite every such path to the
   workspace before the brief is sent, name the workspace explicitly, say that
   nothing outside it is theirs to change, and ask for relative paths.

## Procedure

1. Give each job a **separate local clone**, not a worktree:
   `git clone --local --single-branch --branch <integration> <repo> <dir>` then
   `git checkout -B <job-branch>`. A clone has its own `.git` and no link back.
   `--local` hardlinks the object store, so this is cheap (31 MB here).
2. Place it **outside the repository tree** (`../.jobloop-<repo>/workspaces/<id>`).
   A nested directory invites the same root-resolution mistake.
3. Start the session with the flags that bind it to that directory
   (`opencode run --standalone`), and pass `cwd` explicitly.
4. Re-link whatever the clone needs but git ignores — here `frontend/node_modules`
   via a symlink or junction — or gates fail for reasons unrelated to the job.
5. **Verify containment after every run**, do not assume it: fingerprint the
   main checkout before and after the dispatch and escalate on any difference,
   and keep the "the worker changed nothing" gate. An unverifiable fingerprint
   (the path is not a repository) is "unverified", never "unchanged".
6. Deliver by `git fetch <workspace> <branch>` then merge. A clone is a separate
   repository; its branch is not visible to the parent until fetched.

## Related traps in the same path

- **Long prompts**: a brief that carries a whole job text exceeds the Windows
  command-line limit. Pipe it on stdin instead of passing it as an argument.
- **`git status --porcelain` is column-oriented**: the first two characters are
  status codes. Stripping a line before reading it shifts every path by one
  character and turns records into "foreign" paths.
- **Console encoding**: a cp932 console cannot print an em dash or Japanese text
  from a plain `print`. Reconfigure stdout to UTF-8 with `errors="replace"`, or
  keep operator output ASCII.
- **Fixed commands built by the controller** should run without a shell
  (argument vector), so a Windows interpreter path never needs quoting.

## Boundaries

- Containment is not authorization: an isolated worker still may not commit,
  push, merge, reach `main`, or touch protected paths.
- Never "fix" an escape by widening what the worker may write. Restore the
  checkout, quarantine the output, repair the isolation, and re-run the job.
- An attempt lost to a controller defect is not the job's attempt: reset it and
  record why (`PROTOCOL.md` §5.4 treats only model failures as attempts).
