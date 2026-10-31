# ADR 0004 — Bootstrap launch and current-head CI repair

Status: implemented adapters; live executor and merge activation blocked.

The Bootstrap integration extends the existing serial Controller and SQLite
ledger. It does not replace the previous specifications or start product work.
`$loop` calls `loop launch`, which checks Goal/plan, doctor and the OS lock before
requesting a background resume. The Controller lock remains authoritative under
concurrent launch requests. Detached diagnostics rotate at 256 KB, three backups;
validated results remain in SQLite. No raw model transcript is logged.

GitHub observations distinguish missing, pending, failed, stale and unsuccessful
checks. The PR HEAD is read before and after collecting checks and run IDs.
Required check names must exist exactly once. Failure logs are bounded, masked
and classified; authentication, permissions, billing, infrastructure and unknown
failures never enter automatic code repair. Logs are untrusted task context.
Repairs invalidate verified source/commit evidence, consume the original task's
three-attempt budget and repeat local QA and independent read-only QA. Ordinary
fast-forward pushes update an existing PR only from the previously owned HEAD.
Uncertain mutations still require recovery rather than blind replay.

The source-only executor is **not enabled** by this ADR. A synthetic native
Codex sandbox probe proves Python startup and a single control-file read denial,
not complete credential, MCP, tool, network or writable QA containment. Keep
UnprovenBoundary until the full negative capability suite and isolated review
support a replacement. Do not treat a user setting as isolation evidence.

`gh pr merge --auto` exists in gh 2.95.0, but its permission to merge a future
HEAD and lack of atomic base-policy binding cannot satisfy the existing merge
contract alone. No `--admin`, protection relaxation or native auto-merge is
enabled. Private repository Rulesets API returned HTTP 403 requiring GitHub Pro
or a public repository; changing visibility/plan/protection is a human decision.

Configuration migration is additive and in memory: legacy `base` and
`allow_unrestricted_execution` remain canonical; supplied `base_branch` and
`allow_unrestricted_codex_execution` aliases must agree. QA gates cannot be
disabled. Existing write/merge permissions remain off. Detected QA profiles
are proposals until explicitly configured; `{python}` resolves to the running
Controller interpreter to avoid a different system Python on Windows.
