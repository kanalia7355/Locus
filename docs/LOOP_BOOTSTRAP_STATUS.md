# Bootstrap QA/PR integration — 2026-10-31

**Incomplete: live autonomous implementation is not enabled.** The full user
request is preserved in `requirements/LOOP_BOOTSTRAP_SPEC.md`. This report does
not replace `.bootstrap/complete.json`, which describes the older product
prototype bootstrap. No Locus product development loop has been started.

Implemented additions:

- `.agents/skills/loop/SKILL.md`: real `loop doctor` / `loop launch` entrypoint.
- `launcher.py`, CLI/background: Goal/plan/OS-lock checks, background resume,
  bounded rotating masked diagnostic logs. Resume preserves persisted budget.
- `checks.py`: current-head observations, required-check presence, distinct
  pending/failure/cancel/skip/missing states, failed-run log classification.
- Controller: prior local/review/CI failure evidence supplied to retries; CI
  repairs revoke old verification, repeat local QA/review and share three claims.
- GitHub adapter: fast-forward repair push to the existing owned PR; persist
  observed PR number, head, run IDs and CI evidence in SQLite.
- QA stack detection, portable `{python}` substitution and additive config
  aliases; QA gates cannot be disabled. Actual detected repository commands are
  configured, but still require a proven execution boundary.

The detector uses the existing verification scripts, which cover format, lint,
types, unit/integration/E2E tests, frontend build, offline secret scanning and
dependency audits. Wheel build is separate. Architecture/Goal alignment still
requires the independent reviewer; mechanical QA is not its substitute.

Verification evidence is recorded after commands run; see the scoped audit
record in `reviews/2026-10-31-bootstrap-qa.md`. Unit/integration tests use explicit
fixture transports. Those results do not prove a real Codex task was executed.

Remaining acceptance gates:

| Gate | State / reason |
| --- | --- |
| Skill structure validation | Passed with system quick_validate.py; VS Code discovery requires session refresh |
| Doctor and state/repair controller tests | Implemented; test evidence in audit record |
| Real Codex sample task | Not executed: complete model/tool/credential isolation unavailable |
| Live `loop start` | Safely blocked by UnprovenBoundary and execution authorization |
| Native synthetic sandbox probe | Python starts and adjacent synthetic control file read is denied; not full containment proof |
| GitHub write E2E | Dedicated validation PR only; no main merge permitted |
| Protected native auto-merge | Disabled; rulesets API HTTP 403 on current private repository plan |
| Trusted independent-review check | Not provisioned; local agent review cannot impersonate a GitHub check publisher |
| Atomic current-base merge binding | Unavailable in current gh adapter; never relaxed |
| Intended product Goal/task plan | No product plan imported; Bootstrap does not authorize one |

Configuration differences from the supplied example are intentional:
`base`/`allow_unrestricted_execution` are existing canonical names, with aliases
accepted and conflicting values rejected. Existing `enabled: false`,
`auto_merge: off`, `delivery: local` are retained until execution, publication
and merge gates can be verified. No permission, billing, public-visibility or
branch-protection setting is changed by this Bootstrap.

The initial GitHub CI failure was the Secret Scan interpreting deliberately
invalid test inputs as credentials. These inputs are now named local variables;
test values/assertions are unchanged, and no scanner/CI rule was disabled.
Private credentials, runtime DBs, generated logs and the original ZIP remain
ignored by Git. Existing gh keyring authentication is reused; no token file is
created.

Next invocation: `$loop` (after the skill is discovered). It inspects state and
reports missing plan/isolation instead of claiming a worker started. Manual
inspection: `./.venv/Scripts/python.exe -m loop_engine.cli doctor --check-sandbox`,
then `status` / `decisions` / `report`. Do not approve pending scope decisions
merely to suppress the isolation blocker.
