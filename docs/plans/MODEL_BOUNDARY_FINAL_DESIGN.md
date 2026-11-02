# Model execution boundary: final A investigation and C implementation proposal

Status: INVESTIGATION / PROPOSED; 2026-11-02. This is not ADR0011 adoption,
implementation authorization, an activation receipt or permission for inference.
Base: ADR0006, ADR0009/0010, proposed ADR0011, existing local_commit_push.
Proposed normative adoption scope and the exact departures from the historical
ADR text are in [the owner approval proposal](MODEL_BOUNDARY_APPROVAL_PROPOSAL.md).
Neither document changes an accepted ADR or runtime policy before owner approval.

## Decision

A can suppress outgoing declarations locally through existing catalog/config
mechanisms. It has NOT established the complete approved execution boundary for
the ordinary ChatGPT-authenticated runtime. Therefore the existing startup hold
remains and phase 2 is specified below. C is the proposed way to enforce the
remaining request/response boundary, not proof that every possible A configuration
is impossible. The newly found A configuration should reduce C's attack surface;
do not discard it or build a new executor/orchestrator.

No paid API integration, credential export, real inference, auth commands,
service restart, autonomous Loop, production config/receipt change or delivery
operation occurred. An independent read-only reviewer was the only agent used.
Diagnostic scripts and synthetic evidence live under ignored `.loop/runtime`.

## Phase 1 scope, evidence and limits

Investigation began 2026-11-02 09:54 UTC. A investigation ended 10:05 UTC,
within the four-hour maximum; no additional compatibility search follows this
decision. This is an elapsed investigation bound, not a four-hour test run.

Pinned native client: `codex-cli 0.166.0`, binary SHA256
`9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42`.
Model: `gpt-6.1-sol`; provider ID: built-in `openai`; Lite remains enabled.
No real API key was used. A synthetic, nonfunctional marker existed only in
the child environment to exercise serialization without accessing the login.
There was no login/logout/status, token copy, keyring provisioning or refresh.

The local server never forwards requests. Declaration runs return HTTP400;
response tests return one synthetic SSE stream and then reject further requests.
CLI sessions use isolated homes, ephemeral execution, disabled exports/history,
ACL-denied log directories and the existing Development Worker read-only native
settings/owned-process lifetime containment. This is NOT the deployed audit
identity, audit service, complete Controller invocation or a secure relay proof.

| Local diagnostic | Observed result |
| --- | --- |
| Original catalog, feature switches disabled | 10 declaration nodes remain, including namespaces |
| Additionally disable native V2 collaboration | 3 nodes remain: functions namespace, exec and wait |
| Diagnostic catalog with tool_mode=direct | 4 nodes remain: clock/curr_time and functions/apply_patch |
| Direct + experimental_supported_tools=[] + apply_patch_tool_type=null + shell_type=disabled + multi_agent_version=null, with native V2 collaboration disabled | 0 declaration nodes; no additional_tools item |
| Same zero-capability catalog, synthetic JSON response | One local request, exit0, turn.completed and schema-equivalent JSON observed |
| Zero-capability catalog, synthetic function/custom call | A second request contains call/call_output history; server rejects it and CLI fails |

Counts include namespace containers; they are not OS privileges or counts of
executed tools. The negative streams show automatic continuation, NOT proof of
shell execution, file modification or a credential leak. The diagnostic does not
persist request/response bodies; designated CLI log directories contain no files.
This is not an audit of every CLI-created artifact. The successful JSON response still contains CLI error events;
the current runner rejects such events. It is not an end-to-end successful task.

Evidence paths, relative to repository root:

- `.loop/runtime/phase1-zero-tools/09a9db6b142b4f9584637f1c9090f1e9/evidence.json`
  records the four declaration variants.
- `.loop/runtime/phase1-zero-tools/0783ec04e0374166baf2473017843d83/evidence.json`
  records structured positive completion and the remaining error events.
- `.loop/runtime/phase1-zero-tools/d787efcdcdd341ba8256ec9e281d844b/evidence.json`
  records the function-call continuation.
- `.loop/runtime/phase1-zero-tools/32ab35a73d1346d7845e6678358daaac/evidence.json`
  records the custom-call continuation.

Early attempts incorrectly added the audit-only one-process limit to the
Development Worker diagnostic: instruction loading failed with Windows1816.
They are failed harness attempts, not evidence that catalog suppression failed.
The corrected diagnostic uses the existing Development Worker containment;
no deployed service/process policy was modified or relaxed.

The ambient public cache changed between runs. Do not combine different cache
hashes into one exact-artifact proof. Final positive/custom runs read a preserved
baseline file, report source_catalog_unchanged=true, and share effective catalog
SHA256 `40523a08e04fb82ab0a16ee7f257937daaf9ad343f04d8e9e8a9c51159c479a0`.
Their configs have separate hashes because absolute homes/ports differ.
The original selected model entry has canonical diagnostic SHA256
`1bf7b9261a3e33b02b71c9c83992b994e547c85d5d27d078d3dd36958767d436`.
This does not establish equivalence to today's ambient cache or operator profile.
The zero-capability case changes FIVE catalog fields (including nullable
multi_agent_version), plus configuration switches. Earlier progress wording saying
four fields omitted this fifth field; no isolated four-field proof is claimed.

Findings correcting previous assumptions:

1. Top-level `openai_base_url` routes the built-in provider to loopback. The
   ignored `[model_providers.openai].base_url` override is a different setting.
   The older alias-only probe did not establish that the top-level override fails.
2. Catalog metadata matters: false feature switches do not by themselves override
   model-selected Code Mode, clock, apply_patch or native V2 collaboration.
3. Actual built-in Lite items include id, role, provenance metadata and a
   configuration_update item. The existing tool_surface rejects these shapes;
   declared_tools=0 must not be relabelled no_tools=true or promoted to a receipt.
4. Request metadata shapes were inspected in memory, including the JSON encoded
   x-codex-turn-metadata. The observed zero case has no tool inventory there.
   This diagnostic is not a closed-schema proof of every metadata interpretation.
5. Synthetic API-key serialization does not establish ordinary ChatGPT auth
   equivalence, live provider behavior, hidden native-handler absence, every
   Worker/Reviewer/GoalEvaluator role or production hook/config equivalence.

## C minimum design, based on ADR0011

### Composition and reuse

Keep Controller -> CodexRunner -> official pinned CLI. Each model invocation owns
one ephemeral local instance of the existing AuditRelay, extended into a protocol
gate. The same adapter is used by Worker, Reviewer and GoalEvaluator; role/source
permissions, fresh review contexts and authoritative local schemas remain distinct.
No new scheduler, generic executor, account, service or GitHub App is introduced.
The stopped audit service and preserved trials remain untouched.

Use the discovered zero-capability catalog as defense in depth. The minimum gate
REQUIRES a zero incoming declaration inventory and rejects nonempty definitions;
it does not silently rewrite source/instructions to make a request pass. This is
a deliberately narrower ADR0011 implementation than stripping arbitrary populated
tool sets. If stripping is later required, it is a separate, reviewed transform
with an exact pointer allowlist and preservation tests; it is not implicit scope.
All model-facing requests must have zero tools regardless of catalog behavior.

Initially support only pinned Windows CLI0.166.0 + gpt-6.1-sol + Lite + fresh HTTP
SSE. No WebSocket, continuation, standard-protocol fallback, compression, other
model, alternate provider, voice, MCP, Apps or agent delegation. Unknown variants
stop. Supporting standard Responses or a newer client requires a new contract,
negative tests, review and receipt; no compatibility auto-detection/fallback.

### Launch, identity and routing

- Pin binary, effective catalog/config, schema, source/Goal/QA binding, hook and
  skill identities before/after the invocation. Existing hook holds remain.
- Bind the loopback listener exclusively before starting the CLI. Use the built-in
  provider with the verified top-level endpoint setting, preserving its identity.
- Authorize the connected peer using kernel TCP ownership, expected CLI PID,
  retained process handle/creation identity, owned-job membership and SID. The
  current SID-only helper is reusable groundwork but insufficient for this scope.
  Expose a bounded pre-resume child-binding hook in ProcessRunner if necessary;
  do not change its ordinary lifetime/termination behavior.
- One accepted request per invocation. Reject catalog, auth, unknown endpoints,
  GET/CONNECT, duplicate requests, proxy-style absolute URLs and other peers.
- Upstream is only POST https://chatgpt.com/backend-api/codex/responses with TLS
  certificate verification, no redirects, proxy inheritance or caller-chosen URL.
  The gate cannot be used as a general credential-forwarding proxy.
- CLI obtains its own existing ChatGPT login through its approved storage. The
  gate never reads credential stores, exports tokens, calls login/refresh APIs,
  creates credentials or substitutes API-key authentication. Auth unavailability
  holds the invocation; recovery/enrolment is separately authorized work.

The new gated normal path removes CodexRunner.invoke's unconditional `login
status` preflight. A status command is not a harmless readiness substitute:
authentication backends can mutate state during load. Do not add login/logout,
synthetic provisioning, automatic cleanup or a status fallback. Before spawning
the real CLI, validate nonsecret approved profile/storage identity, artifact
existence/owner/reparse conditions and any applicable lifecycle evidence; an
unknown/missing/inconsistent binding holds before invocation. Such metadata
does not assert token validity or entitlement. No new authentication-success
record may be manufactured from file presence or a successful mock.

Keep the operator's existing CODEX_HOME and approved storage backend; no auth
cache copy, migration, new key or exception permitting new token files. ADR0010
and AuthState govern the dedicated audit identity: do not clone its lifecycle
into the operator profile or silently extend its encrypted-file exception.
Reuse applicable nonsecret-check primitives only after assessing that backend.
If its approved state cannot be established noninvasively, stop for a separately
scoped reconciliation decision; do not invent an enrolment ceremony.

The inference relay does not control every CLI network path. In particular, its
fixed POST route does not prove that the official client cannot perform its own
token refresh outside that route. No real CLI invocation/auth load is authorized
by this design approval. A later real-connection permit must explicitly cover
the ordinary official-client lifecycle required for that attempt, or live testing
stays held. No custom refresh, recovery, re-enrolment or changed endpoint follows.

The local gate necessarily sees the CLI's outgoing Authorization/account header
in transient memory and forwards it unchanged only to the same official model
endpoint. This is same-purpose transit, not credential extraction for a different
client or destination. It enlarges the trusted process boundary and needs explicit
acceptance. If the constraint means credentials may never leave CLI memory even
for this local relay, C cannot satisfy it; do not work around that constraint.

### Closed request contract

Parse strict UTF-8 JSON with duplicate-key/nonfinite-number rejection and bounded
depth before forwarding. Freeze the complete typed contract from same-version
source and native captures; accept only the following field families:

| Location | Required rule |
| --- | --- |
| model, stream, store | Exact approved model, stream=true, store=false |
| input | Fresh typed message items plus the precisely defined configuration_update; no assistant/tool history, response IDs or conversations |
| message | Exact role/content/id/provenance schema; preserve every source/spec/QA/instruction string |
| tools/additional_tools | Absent or explicitly empty in recognized shapes; nonempty means hold before provider |
| tool_choice/parallel_tool_calls | Exact pinned zero-tool Lite contract; values do not authorize a tool |
| reasoning/text/include | Approved effort and transport schema; full existing local schema still mandatory |
| client_metadata | Closed per-key types; decode authoritative JSON metadata, including x-codex-turn-metadata, with its own closed schema |
| prompt_cache_key and other observed operational fields | Bound type/length and exact permitted semantics; no routing or capability extension |

Unknown fields at every structural level are rejected. User source text remains
text: do not delete text merely because it contains words such as tools. Unknown
metadata must not be accepted as an opaque capability container. Dynamic workspace
maps are restricted to approved roots and have a closed value schema. Reject any
embedded authoritative inventory or past call history. Preserve valid request
semantics exactly; any necessary metadata normalization needs explicit contract
and preservation tests. Never use a string search alone as proof of tool absence.

Forward only pinned safe headers, the unchanged auth/account headers, and the
exact Lite marker. Reject duplicates, controls, unexpected content encodings and
unsupported framing. No body/header echo in errors. HTTP401/403 and quota errors
are recorded as finite status classes; they never trigger gate retries or a
fabricated success. Ensure CLI cannot autonomously repeat upstream inference or
turn failure into authentication recovery through this transport.

### Closed response contract

Before any provider body bytes reach CLI, assemble a complete bounded SSE frame,
strictly parse it and validate a closed event/envelope/item schema and state
transition. Allow only the pinned text/message and necessary reasoning families.
Candidate families include response.created/in_progress, output_item/content_part
added/done, output_text delta/done, approved reasoning events and completed. This
is not a prefix allowlist: every exact event and every nested field needs a
same-version typed definition and fixture before it can be enabled. Unsupported
reasoning envelopes are held rather than silently passed. No raw reasoning log.

Reject function/custom/MCP/browser/computer/code/search/agent calls at first item,
delta or argument fragment, including nested calls in terminal response objects.
Reject unknown events/items, contradictory event/data types, duplicate IDs/indexes,
invalid ordering, malformed UTF-8/JSON, incomplete frames, mismatched response
identity, multiple terminal outcomes and events after completion. Validate
terminal output against the accumulated items/text. Ordinary text containing a
tool name is not a tool invocation; preserve it as text for the existing schema
validator. Known upstream failure events fail the invocation, never become findings.

Incremental forwarding is limited to complete validated safe frames. Earlier safe
text may have reached CLI before a later rejection; it is never accepted/applied
as a task result. On rejection the gate closes transport, cancels the owned CLI,
marks failure and waits for bounded cleanup. No offending frame reaches dispatch.
Successful task result requires gate completion AND clean CLI completion AND
existing authoritative schema/binding checks. CLI error events remain fatal;
the error events seen in phase 1 need classification/remediation, not suppression.

### Bounds, persistence and recovery

Preserve the earlier of Controller deadline and current per-invocation deadline,
including connect/read/parse/teardown. Initial ceilings: request4MiB,
response16MiB (existing relay limits), header block64KiB, each SSE frame1MiB,
JSON depth64 and at most10,000 frames; lower role-specific limits still win.
These are compatibility ceilings requiring tests, not permission to increase
existing source/schema limits. Bound fragmented lines before allocating/parsing.
Cancellation closes sockets and terminates the owned job. Unknown teardown holds.

Gate states: prepared -> launch_reserved -> peer_bound -> request_validated -> upstream_reserved ->
streaming -> terminal_validated -> cli_validated -> completed. Any uncertain
post-reservation result is held. Persist only call/role/task identity, artifact
hashes, state, finite error/status category and counters in existing invocation
evidence. No input/request hashes of potentially sensitive payloads, raw headers,
body, model reasoning, exception text, packet dumps or subprocess stderr logs.
Contracts/code/config hashes are allowed. Required final edits/findings continue
through existing authorized task artifacts; they are not duplicated as raw model
transcripts. Authentication stays transient and never becomes an evidence field.

CodexRunner's existing sanitized stderr/error persistence is not sufficient for
this rule: sanitization recognizes some secrets but does not prove absence of
prompts/outputs. Replace ONLY model-transport diagnostics with finite categories
and pinned non-content metadata. Preserve QA logs and all QA requirements.
Verify actual CLI history/log/export/temp behavior too; flags alone are not proof.

No automatic resend after an uncertain provider outcome or on resume. Controller
remains the retry authority within its existing budget. Disallow a second upstream
POST even if CLI attempts a tool loop. Never reset previous audit permits/nonces,
real-model attempt counts or held authentication/trial records.

### Durable invocation ownership and crash reconciliation

Use the existing StateStore database, lock and transaction/evidence conventions;
add one narrowly scoped model_invocations journal table, not another Controller
or task/delivery state machine. AuditRelay.used remains an in-process guard and
is not durable evidence. Trusted caller wiring supplies the following stable
semantic owner; caller-generated model text cannot choose it:

- Worker: existing execution ID, task ID, implementation attempt, role/schema,
  frozen specification identity and current source binding.
- Reviewer: that execution/task/attempt, existing exact review binding (including
  head/base and mandatory QA), role/schema. Existing review/fix limits apply.
- GoalEvaluator: existing persisted Development run/cycle owner, Goal/spec and
  evaluation HEAD/binding, role/schema. Persist its cycle slot before invocation.

Other schemas/roles without a bounded trusted owner fail before launch. Random
call IDs identify records but do not replace the semantic unique key. Artifact
updates, a changed nonce, a new run window or process restart cannot bypass an
unsettled owner. A global unsettled-process/cleanup guard also blocks newly
minted owners until reconciliation; time/attempt counters never reset here.

The trusted invocation adapter owns all journal writes. Under existing project
serialization, BEGIN IMMEDIATE + a UNIQUE semantic-owner constraint claims the
record and appends a content-free event. Store owner IDs/binding references,
call ID, protocol/artifact version, phase, deadline and finite failure category;
never the prompt, raw response, token or hashes newly derived from those payloads.
Use and verify SQLite's durable commit settings (FULL synchronization); a failed
commit prevents the next action. Do not treat an unflushed JSON file as a lease.

Commit launch_reserved BEFORE resuming a CLI process that could load auth or
initiate traffic. Bind its retained process identity before resume. Commit the
single transition request_validated -> upstream_reserved BEFORE establishing the
upstream connection or sending any provider bytes. Only that successful transition
grants this invocation one upstream POST; a duplicate callback/request cannot send.
Final task/evaluation result persistence still belongs to the existing caller.
The adapter's validated transport completion never marks a task/delivery complete.

| Observed durable state after interruption | Permitted recovery |
| --- | --- |
| prepared, no launch reservation | Revalidate exact owner/artifacts/budget before an atomic launch claim; never infer auth readiness |
| launch_reserved through upstream_reserved/streaming | Hold until process/socket lifetime and outcome are reconciled; absence of a response is not proof of non-send |
| terminal_validated/cli_validated, caller result absent | Hold; do not infer task success, invent a result or repeat inference |
| completed plus matching authoritative caller result | Reconcile the existing task/evaluation checkpoint; no inference replay |
| completed but caller result missing/mismatched | Hold for explicit reconciliation; no automatic new owner or model resend |
| known pre-launch rejection with proven cleanup | Return a finite failure under existing budgets; only the Controller may schedule another authorized attempt |

A normal return completes the transport record only after clean gate/CLI/schema
checks. Link it to the caller's existing result/checkpoint when that result is
durably observed; a crash between these steps conservatively holds. No raw-model
result cache is added. Minimal caller plumbing may pass owner IDs and acknowledge
the already existing result commit, but does not change scheduling, task states,
QA, Git delivery or their recovery algorithms. Fault-inject before/after each
reservation/commit/send/result boundary, including caller and gate crashes.

### Implementation scope after approval

| Existing module | Scoped work |
| --- | --- |
| audit_transport.py | Extend existing relay with closed request/response contracts, frame state machine, bounded teardown and one-upstream-request enforcement |
| toolless_boundary.py | Correct native built-in diagnostic shape coverage and bind the new gate evidence; no success override |
| codex_runner.py | Route the three bounded normal roles through the gate, remove unconditional login status, enforce nonsecret preflight and use content-free transport failures; keep proposals and local schema checks |
| native_boundary.py / audit_profile.py | Pinned zero-capability profile/catalog and built-in routing where used; preserve OS controls and auth storage |
| process.py / windows_tcp_peer.py | Scoped owned-child peer binding and coordinated cancellation; no replacement supervisor |
| runtime_diagnostics.py / cli.py | New versioned boundary receipt and composition; no reuse of old zero-tool receipts |
| state_store.py and existing caller wiring | Durable unique invocation reservation/reconciliation and trusted owner/result references only; no replacement scheduler or task/delivery transition changes |
| tests and deployment manifests | Native offline conformance, negative transport/privacy tests and exact artifact identity |

Controller and Development Loop retain their algorithms with only the invocation
owner/result plumbing specified above. Proposal application, mandatory QA, Conventional
Commits, local integration, Push and their recovery/state transitions remain
unchanged. No Review App/Merge Broker prerequisite is restored. No main Push.
Existing tests remain regressions; their old count is not a gate proof. Add
targeted inference transport coverage rather than weakening existing tests/CI.

### Required verification and approval gates

1. Same pinned client/catalog/config and all three normal roles: zero definitions
   before forwarding, native positive JSON roundtrip, clean CLI events and closed
   standard/Lite separation. Exclude the observed startup-error cases from success.
2. Malicious synthetic streams for every call family, partial frames, terminal
   smuggling, metadata inventories, duplicate fields, invalid order, oversized and
   truncated input. Verify rejected frames never reach CLI, no tool effects/child
   delegation occur and no second upstream request is sent.
3. Wrong PID/SID/job, PID reuse, listener races, replay, crash, cancellation,
   expiry, unknown cleanup and resume. Existing task/delivery budgets unchanged.
4. Synthetic canaries for auth, input and reasoning absent from every application
   log/temp/failure artifact; TLS/redirect/proxy/endpoint bypass negatives.
5. Independently review code and exact deployed artifact. Fresh hash-bound receipt
   only after tests. Policy migration/ADR wording explicitly approved; no Fixture
   boundary, bypass, weakened CI, conditional passed flag or native fallback.
6. Only with a separate concrete permit: real ChatGPT-path validation within
   approved source-only scope and cumulative existing model-attempt limits. No
   new trial/nonce resets, auth recovery or audit-service restart inferred from
   design approval. Synthetic success never certifies entitlement/live protocol.

## Support, authentication and usage conditions

Official documentation describes custom providers and forwarding ChatGPT
Authorization/account headers unchanged to the Codex backend for user-attributed
inference. This supports the general gateway pattern, not a guarantee for this
personal account, fixed old client, internal Lite protocol or modified zero-tool
semantics. A gateway cannot increase entitlement or bypass rate limits. API keys,
auth helpers extracting login data and alternate upstream credentials are excluded.

Official general gateway compatibility includes tool execution and continuation;
this restricted gate intentionally rejects both and must not be advertised as a
fully compatible general gateway. Public documentation does not establish a
stable support commitment for the internal Lite marker/shape or approve this exact
personal deployment's terms. Unsupported changes fail closed; unresolved applicable
usage/support conditions block live activation, not justify token reuse or API
billing. No provider-side acceptance was tested in this investigation.

Sources read using OpenAI Docs:

- https://learn.chatgpt.com/docs/config-file/config-advanced#custom-model-providers
- https://learn.chatgpt.com/docs/enterprise/connect-to-a-gateway#handle-credentials-at-the-gateway
- https://learn.chatgpt.com/docs/enterprise/gateway-compatibility
- Locally cached same-version spec-plan.rs, openai-models.rs, client.rs,
  model-provider-info source and responses-lite tests under
  `.loop/runtime/audit-client-source`; these are source evidence, not execution proof.

## Changed guarantees, estimate and owner decisions

Existing absent-tools safety objective remains. Native registry emptiness is NOT
an established guarantee here: C replaces reliance on it with a mandatory
model-facing zero inventory plus rejection before native dispatch. New trusted
components are the request/event parser, transient credential transit and peer
binding. Same-SID compromise is not solved by a loopback listener or credential
manager; the operator host/trusted code assumption remains explicit. Catalog-zero
is defense in depth, not a reason to omit negative response validation.

Conditional implementation estimate: 5-8 person-days for this fixed Lite-only
scope: contracts/composition1-2, state machine/peer/lifetime2-3, negative/privacy/
regression tests and independent review2-3. This is an engineering estimate, not
measured completion time. Account/support clarifications, approvals, OS deployment
and live verification waiting time are excluded. Protocol incompatibility may
block rather than silently expand the scope.

Owner decisions before implementation: adopt this restricted C refinement of
ADR0011; accept the precise native-vs-model-facing guarantee; allow same-purpose
credential transit in the local trusted gate; approve exact catalog/profile and
versioned boundary contract changes. Live validation/activation is a later,
separately bounded approval. No approval is requested for additional API billing,
a new account/service, external credential export or weakening QA/delivery.

Residual risks: internal protocol drift, unproven ordinary ChatGPT equivalence,
CLI error events, hidden native capability, parser defects, local same-user
tampering and uncertain provider completion. Every unresolved blocking condition
keeps startup held. This proposal does not claim Locus development is ready.

## Independent review history

Initial isolated read-only architecture review returned needs_decision. It
identified incomplete ChatGPT/native evidence, the first literal-text completion
detector and different baseline catalog hashes. The positive detector was changed
only in the ignored diagnostic to parse JSON events in memory, and subsequent
positive/custom evidence is bound to a preserved baseline and effective catalog.
Unproven operational guarantees remain explicitly blocking above.

The earlier first re-review invocation could not run because the review agent reported
its usage limit. No model/account substitution or extra agent was used to bypass
that limit. Review usage counters were unavailable. The subsequent owner-requested
review found three Medium design-scope issues: historical ADR precedence, durable
invocation reservation/recovery and unconditional login status. Their resolution
is specified above and in the exact proposed adoption supplement. The current
review disposition and reviewed file hashes are authoritative only in
[the separate review record](../reviews/MODEL_BOUNDARY_DESIGN_REVIEW.md).
Missing or non-passing re-review remains a blocker. Design review is never runtime
verification or permission to adopt/implement/deploy without the owner decision.
