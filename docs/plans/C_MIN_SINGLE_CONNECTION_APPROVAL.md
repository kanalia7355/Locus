# C-min single ChatGPT connection — preparation, not permission

2026-11-03. No live command has run; no auth store/profile was opened. This
proposal is separate from MAIN_FF_INTEGRATION_DESIGN.md and its activation.

## Fixed finite test

Pinned Windows official Codex CLI0.166.0 executable SHA256:
9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42.
Model gpt-6.1-sol, built-in openai provider, fixed verified HTTPS destination
https://chatgpt.com/backend-api/codex/responses. No API key or API billing.
Existing ToollessBoundary catalog/privacy restrictions and OwnedCliPeer apply.
The relay's ephemeral localhost address is routing only, not another provider.

Only approved synthetic input:

    This is a synthetic transport verification. Do not use tools. Return exactly
    the JSON object {"ok":true,"proof":"C_MIN_SYNTHETIC_OK"}.

JSON schema: object, additionalProperties=false, required=[ok,proof]; ok is
boolean const=true, proof is string const=C_MIN_SYNTHETIC_OK. No project files,
diffs, tasks, research data, conversation history or private source in the packet.
An empty controlled workspace contains only a public synthetic marker. Verify
all ancestor instructions, hooks, skills and global settings before launch;
unassessed hooks are a HOLD, not permission to disable them. Gate must compare
the complete semantic message/instruction input against the reviewed synthetic
allowlist before reserving upstream, not merely check the caller's prompt. Any
automatic CLI context outside that allowlist rejects before provider bytes.

Shared wall deadline180s, process/output limits from existing gate remain; maximum
ONE CLI launch and ONE upstream POST. No retry after 401/429/5xx, malformed output,
EOF, timeout, process crash, missing reply, journal error, changed artifacts or
unknown completion. A rejected local WebSocket upgrade is not a model invocation;
the existing one HTTP fallback is allowed, but another POST is never allowed.
Reserve the trial slot durably before launch; a fresh nonce or run cannot reset it.

## Present durable evidence (read-only inspection)

StateStore opened SQLite mode=ro, not via its schema-writing constructor:
control=stopped; prior run eafbe75fe98343dcbb07069f77e469e3 expired, consumed_seconds
314.31721839999955; TASK-001 completed with attempts=3/3; worker records one failed
and two returned. No c_min_live_permit, registered normal auth profile, or
model_invocations table is present. Do not modify existing task/attempt/run rows.
Pending dependency/merge/publication/scope/security decisions remain pending.

live-runtime.json has passed=false, surface_version=2, no C-min protocol or
response/auth/live verification flags. It is INVALID for v3 and must be retained,
not upgraded by editing flags. Current source identity must be recalculated after
final reviewed commits; future implementation changes invalidate that identity.

Historical isolated-audit evidence documents TWO consumed/reserved real trial
intents: original result unknown; separate diagnostic blocked at upstream_response,
policy, HTTP200. See reviews/2026-11-01-audit-model-trial-held.md and
reviews/2026-11-02-responses-lite-boundary.md. Their protected current records were
NOT read and their current cumulative authorization cannot be inferred from docs.
No third attempt is implicitly available. Before live approval, reconcile only
existing nonsecret record phases/hashes using an expressly approved read-only
method, without service operations, auth CLI, credential reads or resetting intents.
Explicit future permission must add at most one cumulative trial slot and identify
all previous consumed/unknown reservations. Failure to reconcile remains a HOLD.

## Auth scope to be approved separately

The official CLI alone may access its existing ordinary ChatGPT login. Relay may
transiently forward the CLI's Authorization/account headers in same-PC trusted
memory only to the same fixed official inference destination. No investigator or
trial code may retrieve/display credential values, read token files, copy stores,
write plaintext/encrypted token exports, create API keys or implement OAuth.
Existing secure backend/profile/owner/ACL/reparse/ciphertext identity must match
nonsecret registered evidence before launch and afterwards. Missing or changed
storage means STOP, not login/status/logout/enrolment/recovery or migration.

IMPORTANT: native tool sandbox settings do not prove that the CLI's own auth
refresh traffic is blocked. The inference relay does not intercept all CLI network
traffic. The present code cannot promise a credential-read-only real launch or
prevent an ordinary official refresh before it happens. If the owner forbids all
standard secure-store refresh writes as well as export, live execution remains
blocked until that guarantee is proven. No new egress/auth restriction will be
silently installed. A future live permit must explicitly resolve whether ordinary
official-client refresh in its existing secure backend is allowed; it must NOT
authorize custom refresh, auth recovery, new storage or unrelated connections.

## Exact command and missing activation implementation

Proposed command, NOT YET IMPLEMENTED OR AUTHORIZED (do not run):

    .venv\Scripts\python.exe -m loop_engine.cli c-min-trial --plan docs/plans/C_MIN_SINGLE_CONNECTION_APPROVAL.md --approval <exact-approved-trial-record-id>

Do not substitute loop start/launch/resume, doctor --check-sandbox, audit service
self_test or a raw codex exec. None is an approved one-shot C-min v3 validator.

Normal c_min_runtime.preflight requires an existing live v3 receipt and a
normal-development permit BEFORE launch. It cannot bootstrap the first live
receipt. A minimal validation-only branch of the SAME adapter/journal is needed;
not a new executor. Its purpose-specific permit replaces ONLY that circular
prerequisite with reviewed offline proof, exact synthetic packet/runtime/profile
binding, cumulative single-slot budget and deadline. Normal preflight is unchanged.
Do not forge a task/execution or classify a trial as normal Worker activity.
Independent review and owner approval are required before this safety-related
implementation; live execution is a subsequent, separate permission.

## Receipt, output and stop conditions

Record only IDs, hashes, static outcome/stage, timestamps, request count<=1,
verified tool-count=0, fixed protocol version, peer/source/runtime bindings,
schema-validation boolean and post-cleanup/profile checks. No auth values,
request/response bodies, model reasoning, raw stderr/exception or conversation log.
Validate output in memory against the fixed schema and discard content afterwards.

Issue a NEW trial-scoped v3 proof only after all actual tests pass: completed
closed request/SSE gate; zero definitions; no call forwarded; exact peer/process;
normal ChatGPT auth path; synthetic packet binding; clean CLI completion; privacy,
storage/source/QA checks. Name the proof c-min-single-validation; do not write a
normal-development-ready receipt or infer multiworkspace/Loop approval from it.
Finite failed/unknown evidence never becomes passed. Source identity, CLI/catalog,
settings/hooks, QA image/audit freshness and trial purpose are included in hashes.

## Multiple workspaces and launch blockers

Current permit.artifact equals ToollessBoundary._binding(workspace), which contains
the absolute workspace path and settings. One permit therefore does not cover
GoalEvaluator and Worker/Reviewer task workspaces. A future explicitly approved
run policy must bind immutable run/spec/scope/deadline plus each call's concrete
task/execution/attempt/source/workspace/role; generated workspaces are not an
unbounded wildcard. Preserve unsettled invocation exclusion and original deadlines
across restart; no new run/nonce bypass. This policy is NOT implemented/activated
by preparing a single trial. Worker attempt3/3 is not reset for CI repair.

Development publication and main integration must have separate durable receipts;
the proposed main journal must block task completion and policy migration while
unsettled, without erasing published development commits. Resume rechecks exact
SHA/CI/refs; missing or changed evidence holds. QA image audits must be current at
the actual trial; local/native mocks and hosted skips do not establish live readiness.

## Separate decisions still required

1. Offline implementation approval for the minimal one-shot adapter purpose,
   exact-message allowlist, trial journal owner/acknowledgement and scope-specific
   proof. No normal-preflight relaxation, real auth or model call is included.
2. After implementation/offline QA/independent review: exact source/packet/command
   hashes, nonsecret historical/profile reconciliation, refresh disposition,
   cumulative ONE new trial slot,180s shared deadline and result-unknown stop.
3. Main production activation has its own design/policy/protection decision and
   does not follow from either item above. Unattended Loop needs another approval.
