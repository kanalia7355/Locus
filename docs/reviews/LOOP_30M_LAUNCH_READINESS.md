# Thirty-minute launch investigation, 2026-11-05

The real launch request was rejected as execution_boundary_unverified. Controller
remained stopped; no thirty-minute work or model inference completed. The existing
normal receipt is failed/stale and cannot be repaired by setting readiness flags.

## Implemented minimal fix

Doctor previously ran Codex login/status before rejecting an unverified execution
receipt. It now checks the existing receipt first. Missing/stale evidence reports
authentication unknown and explicitly records that the probe was not run. With
valid evidence, the original authentication check and every readiness condition
are retained. This strengthens the current failure path; it does not authorize
authentication when a valid receipt exists or implement a new run policy.

Focused tests: eight passed, including missing/stale receipt denial and unchanged
valid-receipt authentication requirements. An isolated reviewer independently ran
the same eight tests (0.90s), with no blocking findings. Full engine QA with audit
passed: lint/format, both type configurations, 883 passed / 7 skipped in434.06s,
secret scan, dependency consistency and third-party advisory audit. Skips remain
unverified; the local package is unavailable on PyPI for advisory lookup. Hosted
CI results remain separate evidence for the published commit.

The post-fix real launch diagnostic reports execution_boundary_unverified and
authentication_probe=not_run_execution_boundary_unverified. No model request or
background Controller was started. Do not repeatedly relaunch this unchanged
state as if it were making progress or reuse old task attempts.

## Additional preparation completed without activation

Existing verify_profile passed for an unregistered nonsecret existing-file
profile candidate, including exact current configuration fingerprint, strict
auth/config protections, runtime policy and approved credential lease digest.
Only configuration and metadata were examined; auth.json contents were not read.
The current synthetic-trial workspace artifact was calculated with existing
ToollessBoundary._binding; no authentication or model subprocess was involved.
Candidates and private preparation evidence remain in ignored runtime storage,
not in this public report or root permission registrations.

The existing mock fixture separately captured a v3 contract and validated two
distinct CLI launches after freezing it. It remains a synthetic fixture, not an
exact current-live-workspace contract or authorization. Historical two started
service reservations remain held/unknown, with no refund, reset or new live grant.

## Actual remaining causes

1. Profile/history/input/review/permit registration and exact live trial bindings
   are incomplete. Official-client normal automatic refresh is not authorized;
   its traffic is outside the inference gate, and read-only credential startup
   cannot be promised by the current CLI. Explicit owner disposition is required.
2. Trial success intentionally stays trial-only; it cannot satisfy normal receipt
   requirements by copying result flags. Current normal capability evidence and
   a separately authorized thirty-minute run remain necessary.
3. Normal preflight binds one absolute workspace artifact and run ID. Controller
   creates a new run identity internally, and evaluation/task workspaces vary.
   This activation composition gap needs the bounded, separately approved change
   described in ../plans/LOOP_30M_ACTIVATION_REMAINDER.md. No wildcard, new executor
   or implicit delegation is implemented by the doctor fix.

The independent reviewer confirmed these causes and reviewed the minimal offline
proposal through the two permitted clarification/re-review cycles, without
blocking findings. That review grants no permission to implement the delegation
or execute credentials/inference. Owner approval is still required.

## Documentation reconciliation

The frozen single-connection preparation document labels its internal CLI
unimplemented, whereas current c_min_trial.py implements it with closed gates.
Follow current source for command availability; preserve the original frozen
approval document and its historical wording. Availability is not activation.
The loop skill requires doctor/launch, but the operator's narrow authorization
still governs authentication and inference; the new failure path avoids the
unverified receipt causing an automatic Codex authentication-state probe.

Agent ownership is unchanged: after explicit approval the agent runs internal
commands and monitors state. The owner uses $loop30m; owner-terminal Python is
not a prerequisite. No main write, protected-service operation, permission change,
credential recovery or actual inference is part of this fix.
