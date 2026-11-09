# Bounded run and notify suppression: offline implementation

2026-11-05. Offline evidence only; no live authorization.

## Approved scope

The two frozen approval documents were rehashed without modification:

- LOOP_30M_ACTIVATION_REMAINDER.md: `f52797bbc096c7c00d2ffd8c5d6d07e0da4928511c6b7758c44602a3e80b0f04`
- C_MIN_NOTIFY_SUPPRESSION_APPROVAL.md: `6b24d365fe1bfb04c43d7083ccdbac8a7d17385bf7bdbeb7f3437e45642a5a01`

## Implementation

The existing Controller prepares a durable thirty-minute scope and requests exact
owner authorization. Adoption uses that same ID and deadline; resume cannot extend
it. Current normal receipts remain mandatory at adoption and model preflight.
Profile, configuration, Goal/specification, control source, repository identity and
current QA audit are revalidated. Each call binds its managed workspace, integrated
HEAD, exact source, owner execution/attempt/role/schema, artifact and deadlines.
Bindings are persisted in the existing StateStore before process launch and checked
before child resume, upstream reservation and proof acceptance. Uncertain sends
remain held; retries cannot extend the authoritative invocation deadline.

Optional notification suppression requires an exact registered profile policy and
original configuration fingerprint. Only the root notify entry is assessed as
suppressed, using the final literal `-c notify=[]`; other hooks remain denied. The
actual configuration is unchanged. Older profiles cannot enable this implicitly.
Doctor cannot probe authentication on normal receipt evidence alone: separate
current live authorization is required. Agent-owned prepare-run guidance is in the
existing loop Skill; the owner entry point remains `$loop`.

## Verification and independent review

Focused regression tests: 90 passed (47.86 seconds). Pinned official Windows CLI
against a synthetic home and loopback mock: notification suppression success,
tool-response rejection and cancellation all passed (3 cases). These are not real
ChatGPT connections. Ruff and mypy passed, including 92 engine source files.

An isolated read-only security reviewer inspected all new source/tests and the
complete diff, including QA audit reuse: no blocking findings; 41 synthetic unit
tests passed. One low documentation finding (preparation versus launch receipt
requirements) was corrected. The initial interrupted quota attempt supplied no
review conclusion and was not counted as a pass. No review fix cycle involving
source changes was required. Full local QA passed: 933 tests passed and 7 opt-in real Docker tests skipped
in 472.79 seconds. Lint/format, both Python type targets, secret scan, dependency
consistency and dependency advisory audit passed. Exact-commit CI results are
recorded in the completion report; no pending run is evidence of success.

## Remaining activation gates

No production profile, live grant, ready receipt or execution permission was
registered by this work. Historical unknown reservations remain held, without
refund or replay. A current-source single-connection approval packet still needs
exact profile/config/suppression binding, history/budget reconciliation, current
QA evidence, command/full-input/workspace binding and an explicit decision on
standard official CLI credential use/refresh and auth-file persistence. The
existing profile file content must never be inspected by the agent.

A successful separately approved single trial is trial evidence only. Normal
C-min v3 capability evidence and a distinct finite normal-run authorization are
still required before the agent can execute `launch 30m`. If the existing proof
contract cannot establish those guarantees, stop and report the missing evidence;
never copy trial flags or broaden permissions. No actual auth, inference, ACL,
service, main update or Loop launch occurred in this offline implementation.

The frozen design documents retain their original proposal wording intentionally;
this implementation record distinguishes approved implementation from live use.

## CI repair after initial delivery

Initial delivery 18a2087 passed Linux 3.11/3.13, Windows 3.13, product QA and
convention CI. Windows 3.11 exposed a pre-existing observation deadline rounding
bug: a 120-second timeout became 120.00000000000006 and correctly failed the
existing cap assertion. Clamp the computed remainder to the original timeout;
retain the expiry guard and every assertion. An added synthetic clock reproduces
the overshoot. The isolated reviewer approved this first fix/re-review cycle and
independently passed all 18 observation tests. No service operation occurred.
Final full local QA: 934 passed, 7 opt-in Docker skips, 466.37 seconds; lint,
format, both type targets, secrets, dependency consistency/advisories all passed.
Exact repaired-commit remote CI remains separately verified in the final report.
