# Local loop startup repair — 2026-11-02

This is startup repair of the existing Controller/Development Loop, not a new
orchestrator or permission to launch. ADR-0011 is not adopted. The audit service
stays stopped. Product acceptance, frozen policy and task budgets are unchanged.

## Roles and actual controls

| Role | Output and authority | Approved boundary |
| --- | --- | --- |
| Development Worker | Source-only JSON edit proposals. Controller validates scope and applies edits, then owns QA, commit, integration and Push. The model does not own Git or publication credentials. | ADR0006 requires no executable model tools; Worker uses ToollessBoundary with read-only native settings even when proposing edits. |
| Local task Reviewer / Goal evaluator | Fresh read-only source/diff/verification assessment; no edits, approval substitution, commit or Push. | Same existing CodexRunner/ToollessBoundary. Independent reviews and completion checks remain required. |
| Optional dedicated audit Worker | Separate Windows identity, sealed packets, own approved authentication and no App signing keys. | Additional account/process/storage/peer restrictions. This legacy service is not a prerequisite for local_commit_push and is not restarted here. |

ToollessBoundary binds the pinned executable, configuration, catalog, instructions
and skills; rejects unassessed hooks; configures read-only/network/MCP/tool options;
and checks a local rejected request before admitting inference. It is not itself
an OS sandbox or evidence that every native tool was removed. Actual source
application is separately restricted by Controller proposal validation. QA runs
in the existing source-only Docker boundary.

Official CLI [reference](https://learn.chatgpt.com/docs/cli/reference) describes
sandbox selection as shell-command permissions. This does not establish absence
of model tool declarations; that remains the stronger project-specific contract.

## Corrected false-positive paths

The old request inspection checked only top-level `tools`. The current guard
also inspects Responses Lite `input.additional_tools`, counts nested declarations
even if the surrounding request shape is unsupported, and rejects unknown input
shapes, tool history, duplicate JSON keys and non-JSON constants. Only finite
diagnostic values are retained; prompts and headers are not recorded. The local
endpoint rejects every request and never forwards inference.

The old `openai_base_url` probe override was not a reliable local route for the
pinned client. Diagnostic requests now reuse the existing fixed-loopback alias
helper. This is **diagnosis only**: the alias/provider tool-surface equivalence
is unproven. `probe.passed` therefore deliberately remains false. Neither a
captured request nor a successful text schema can become runtime authorization.
Native CLI features/catalog changes are not adopted from diagnostic experiments.

The old successful receipt cannot be reused: its source/image identity differs,
and the current loader additionally requires the v2 tool-surface evidence.
Malformed or old proof is rejected. HTTP listener cleanup remains bounded even
when command construction or subprocess execution fails.

## Current evidence and remaining model blocker

Existing QA-image construction reran dependency audits successfully and recorded
immutable image `sha256:813ab482ac2e0aece7527eeb0186e8dc4c4efb8076afab77b0f282a8403cae9d`.
The previous image/runtime receipts are preserved under ignored readiness-repair
evidence. Current-code diagnostics revalidate source-only QA, UID/network/control
denial, canary preservation and cancellation without starting a Controller run.
Their overall readiness result remains **false**.

A diagnostic-only copy of the selected model catalog removed clock/apply-patch
metadata, selected direct tool mode and disabled additional native features.
The actual rejected local request still contained tool declarations (diagnostic
count four, including nested entries); the request shape was also unsupported.
This copy was not adopted. An initial experiment used a directory outside the
approved QA probe namespace and was rejected before CLI startup; the corrected
experiment used the existing managed probe namespace.

To preserve the approved boundary, actual native declarations must be absent
under the normal provider, not merely hidden by a parser. A compatible fixed
CLI/configuration must be demonstrated with current source and independent
negative-capability review before this hold can be lifted. If that cannot be
established, stop for an owner decision. A tool-filtering protocol gate would
change the safety boundary and needs a separate concrete proposal/approval;
it is not implemented by this repair and ADR-0011 remains PROPOSED.

## Verification

- Full engine regression before the final narrow diagnostic/cleanup additions:
  478 passed, seven existing skips; lint/format/current+Linux3.11 mypy, secret
  scan, dependency consistency and advisory checks passed.
- Final tool-surface/HTTP cleanup regression: 30 passed. This includes two
  follow-up cases beyond the earlier full collection.
- QA receipt correction additionally requires `outcome == exit` as well as
  exit code zero: a timed-out/cancelled Windows Job can return zero. Three
  synthetic normal/timeout/cancel regressions passed (33 together with the
  tool-surface tests). This subsequent monotonic success-predicate correction
  was tested separately from the capability/routing security review.
- Related real Windows PowerShell/process-lifetime regression: 36 passed before
  those final additions. No installer or deployed service operation is executed
  by these synthetic tests.
- Independent read-only security review and two bounded re-reviews found no unresolved
  Critical/High finding. Reviewer did not run services, network, authentication,
  model inference or tests. Time/token usage was not supplied by the review tool.

## Conditional 30-minute trial command — not executed

Only after a truthful current-code model boundary proof, current audited QA
image, required verification/CI success and a separate operator launch instruction:

```powershell
Set-Location C:\Users\hirot\Locus
.venv\Scripts\python.exe -m loop_engine.cli doctor
.venv\Scripts\python.exe -m loop_engine.cli status
.venv\Scripts\python.exe -m loop_engine.cli decisions
# Require ready_for_live_execution=true and no relevant unsettled executor,
# delivery or task-scope decision. Then, only with launch authorization:
.venv\Scripts\python.exe -m loop_engine.cli launch 30m
```

Inspect `status`, `report` and `.loop/runtime/logs/controller.log`; use
`python -m loop_engine.cli pause` / `stop` for cooperative control. Do not reset
attempts or assume an unknown process terminated. Resume, if separately desired,
uses `launch --resume 30m` and retains consumed task/cycle/attempt counters.
The present diagnostic hold means this command is **not ready to run**.

Residual risks: unsupported CLI request shapes, configuration/hook changes, stale
daily advisory evidence, intermittent hosted Windows startup delays, remote branch
concurrency/Push outages and bounded retry exhaustion. Existing failure gates
remain active. No PR, main Push, App activation or automatic merge is authorized.
