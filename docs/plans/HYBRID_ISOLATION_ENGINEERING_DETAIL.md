# Hybrid isolation — engineering-detail design package

**Status: design documentation only.** This package covers only the isolation-related rows classified `ENGINEERING_DETAIL` in [OWNER_QUEUE_CLASSIFICATION_2026-11-09.md](OWNER_QUEUE_CLASSIFICATION_2026-11-09.md): **DP-033, DP-042, DP-044–049, DP-051, DP-052 and DP-053a**. It specifies comparison criteria, future test-inventory requirements, evidence binding and candidate-profile conformance checks. It does not select or certify a profile, authorize execution, or implement a transport, verifier, admission controller or artifact path. Every profile remains **INACTIVE / UNVERIFIED**.

Authority and constraints: owner decisions [Q1–Q7](OWNER_DECISIONS_2026-11-09-EVENING.md), especially Q3 (per-environment independent verification; no universal VM; no run absent proof) and Q4 (official CLI preference is an adapter constraint, not credential authorization); [ADR-0012](../architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md), [HYBRID_ISOLATION_PROFILES.md](HYBRID_ISOLATION_PROFILES.md), [HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md](HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md), and the classification record. Where this package is more specific, it is a bounded engineering proposal, not a change to those sources.

## 1. Scope and classification boundary

| In-scope row | Classification basis | Engineering detail covered here |
|---|---|---|
| DP-033 | `ENGINEERING_DETAIL` | Compare minimal, verifiable, bounded input/output transfer patterns. No unrestricted host access; do not introduce a bespoke broker without threat evidence. |
| DP-042 | `ENGINEERING_DETAIL` | Online revocation status from the same authority; fail closed on uncertainty. No invented service-level, cache or propagation-time number. |
| DP-044 | `ENGINEERING_DETAIL` | Opaque one-use reference over authenticated transport to a closed, versioned contract; no second job-envelope signature by default. |
| DP-045 | `ENGINEERING_DETAIL` | Reuse vetted authenticated transport and a closed schema; no second signature family. |
| DP-046 | `ENGINEERING_DETAIL` | Control-Plane-authoritative online freshness; no second envelope TTL or clock-skew grace. Receipt TTL numbers remain unresolved. |
| DP-047 | `ENGINEERING_DETAIL` | Durable Control-Plane job identity consumed atomically online; no separate nonce ledger by default. |
| DP-048 | `ENGINEERING_DETAIL` | One Control-Plane authority checks the required bindings, including the exact enrolled Runner; define the closed contract, not the enrollment mechanism. |
| DP-049 | `ENGINEERING_DETAIL` | Bind result digest to job and instance; live revalidate before release. Add an artifact signature only if a later channel change justifies it. |
| DP-051 | `ENGINEERING_DETAIL` | Measurement and test criteria for admission/deadline/cancellation behavior; preserve ADR-0012 semantics and invent no quota or numeric bound. |
| DP-052 | `ENGINEERING_DETAIL` | Per-profile positive/negative test inventory and qualitative pass/fail criteria; synthetic fixtures and independent review. Tests do not activate a profile. |
| DP-053a | `ENGINEERING_DETAIL` | Bind evidence to exact build, configuration and tests; invalidate on material change and require independent review. |

**Not expanded or reopened:** DP-024–030 are owner-resolved Q3 policy (appropriate verified isolation per environment, no universal VM, no downgrade); DP-031/032 (communication path/endpoints), DP-034b (credential supply), DP-035–041 and DP-043b (Runner trust, enrollment, key custody and recovery) are `OWNER_DECISION_REQUIRED`; DP-034a is Q4 policy; DP-043a is an existing cancellation/hold decision; DP-050 is deferred; DP-053b is an existing separate activation-authority rule. Those items constrain this design but are not solutions to be filled in here.

### 1.1 Non-negotiable safety invariants

1. A profile is unavailable until independent evidence proves the **exact** environment and a separate activation authority has acted. Documentation, a test plan, a passing unit test, a container/VM label, or another profile's proof is not activation evidence.
2. Unverified or unverifiable profiles fail closed. There is **no host fallback**, implicit downgrade, permissive retry, or execution on verifier, setup, teardown, authority or cleanup uncertainty.
3. No dispatch before the authoritative receipt and every applicable ADR-0012 gate, including B6, E1/E2 and verified isolation. A valid receipt cannot substitute for isolation evidence; isolation evidence cannot substitute for authorization.
4. This design authorizes **no network path, egress, provider authentication or credentials**. It does not name or allow a Control-Plane endpoint. Q4 constrains future adapter verification only.
5. Future evaluation, if separately authorized, uses an isolated disposable environment and synthetic data only. No live provider, host credentials, research data or real endpoint is used. A test listener or capture sink is a harness component, not a permitted product destination.
6. Plane M's ADR-0011 zero-tool gate and ADR-0012 dual-plane separation remain unchanged. This design creates no dispatch-capable behavior.

## 2. Engineering comparisons

The following comparisons are for resolving the stated engineering rows within the already-approved safety envelope. They do not settle owner-gated policy, trust or deployment choices. The “proposed baseline” column is a design recommendation only; each exact-profile claim still requires proof and separate authorization.

### 2.1 DP-033 — bounded transfer across the isolation boundary

| Pattern | Isolation/evidence characteristics | Limitations and failure cases | Assessment within this scope |
|---|---|---|---|
| Broad host bind/shared writable folder | Simple and fast; host sees the same live path. | Exposes a mutable host surface; path aliases, mount replacement, concurrent modification and cleanup ambiguity enlarge the boundary. A mount is not proof of least privilege. | Reject as the default design for untrusted job access; any exceptional use would need an explicit, profile-specific threat justification and approval. |
| Direct Runner access to host paths or control/runtime sockets | Avoids a copy step. | Gives the job reach into unrelated host data or privileged control interfaces; difficult to prove the complete reachable surface. | Not acceptable as a transfer mechanism. No user profile, credentials, runtime socket, policy/receipt store or broad host path is exposed. |
| Supervisor-staged, bounded input/output bundles | Supervisor stages a declared immutable input bundle before job start; only a job-scoped output bundle is collected after containment and termination checks. A manifest can bind names, sizes, digests and job identity; the verifier can inspect the exact transfer. No shared writable host mount is required. | Requires safe staging, path canonicalization, integrity checks, size/resource bounds, atomic publication and clear failure cleanup. It does not itself authorize a result or prove the OS boundary. Numeric limits are not set here. | **Recommended engineering baseline for evaluation**, if a future approved implementation needs transfer: minimize the crossing, make it explicit and one-way at each phase, and fail closed on any manifest or cleanup uncertainty. This is not a host-access permission or activation. |
| Narrow mediated file-transfer interface | Can enforce a small schema and per-job object scope without exposing general filesystem access. | Adds trusted code and a new security-sensitive boundary; an unnecessary general-purpose broker increases attack surface. | Consider only if measured threat or platform constraints show staged bundles insufficient. DP-033 does not require a bespoke broker absent such evidence. |
| Shared clipboard/device/guest integration | Convenient for interactive workflows. | May create unobservable alternate paths and expose host state; semantics vary across guest/runtime versions. | Disabled in the candidate profiles unless a specific feature is separately justified, constrained and independently proven. No such use is authorized here. |

**Transfer contract proposal:** before launch, the trusted supervisor associates an immutable input manifest with the exact job/profile/configuration; job content stays synthetic in future verification. The guest sees only the explicitly staged job input and its isolated scratch/workspace. After execution is confirmed stopped and cleanup state is known, the supervisor accepts only declared output objects into a quarantine/staging area, verifies their manifest and digests, then leaves authorization, classification, ACL, source-liveness and release checks to their independent Control-Plane gates. A digest proves byte identity relative to a manifest, not safe content, provenance, authorization or permission to release. Missing, duplicate, altered or ambiguous objects deny transfer. All transfer channels remain unconfigured and inactive in this document.

### 2.2 DP-042, DP-044–048 — authorization-status and job-reference contract

| Design concern | Compared alternatives | Recommended engineering behavior | Owner-gated dependency / boundary |
|---|---|---|---|
| Revocation status (DP-042) | Trust a prior enqueue result or cache; ask the same authoritative Control Plane live; query a second authority. | At every required enforcement point, resolve current status from the **same** authority used for authorization. On unavailable, stale, contradictory or indeterminate status, deny. No positive cache or invented staleness allowance in the baseline. | This is a behavioral contract, not a choice of transport, endpoint, trust anchor, enrollment, or revocation authority. Any Runner↔Control-Plane reachability and credentials for it remain gated by DP-031/032 and DP-035–041. No endpoint is specified or enabled. |
| Job reference (DP-044) | Carry mutable authorization claims in a client-provided envelope; resolve a bearer-like reusable token; use an opaque one-use reference and resolve the closed contract online. | Prefer an opaque, one-use reference to a durable Control-Plane job/receipt record. Treat the reference only as a lookup handle, never as proof of authorization. Resolve all authoritative fields and current state online. | The reference's delivery is only meaningful over whatever authenticated transport is separately approved; this package authorizes none. Do not embed credentials or treat possession as approval. |
| Message integrity/schema (DP-045) | Add a second bespoke signature family to the job payload; rely on unauthenticated serialized fields; use authenticated transport plus a strict versioned schema. | Use the already-required authenticated, vetted transport and a closed, versioned schema. Reject unknown fields, unsupported versions, duplicate/ambiguous encodings and malformed values. Do not add a second job-envelope signature family by default. | “Vetted transport” does not choose a trust root, crypto profile, certificate/key custody or endpoint. Those remain unresolved. If future channel properties materially differ, revisit signature needs as a separately reviewed design change, not an implicit addition. |
| Freshness (DP-046) | Separate envelope expiry/skew grace; rely on a cached status; resolve the Control-Plane-authoritative record at enforcement time. | Use the Control Plane as the authority for freshness and expiry. No second envelope TTL, no invented skew grace, and no allow on time/authority uncertainty. Receipt TTL numeric values remain DP-010/011 `OWNER_DECISION_REQUIRED`; they are not set here. | Requires the separately authorized online authority path. No duration, time source beyond existing design references, cache interval or network permission is created here. |
| Replay/consumption (DP-047) | Add an independent nonce ledger; rely on an in-memory “seen” set; consume a durable Control-Plane job ID atomically. | Make the authoritative job state durable and atomically transition an eligible, unconsumed job to consumed before any execution side effect. Enforce a uniqueness/one-consumption invariant under concurrency and after restart. Do not create a second nonce ledger by default. | The transition does not lift B6 or permit dispatch. Failure/uncertainty in the authoritative transaction denies. Persistence technology remains on the Q7 track. |
| Binding authority (DP-048) | Let the Runner/client supply binding values as assertions; let different services make independent partial decisions; one authoritative Control-Plane resolution of the closed binding set. | A single Control-Plane authority resolves and checks the full required binding set against current authoritative records; the Runner must still perform the required independent E2 check. A partial check or claim from the caller is insufficient. | Bindings derive from ADR-0012; this does not change them or define how a Runner is enrolled. Exact Runner identity remains a required predicate, while its trust/enrollment/key mechanism is DP-035–041 `OWNER_DECISION_REQUIRED`. |

**Binding set to check (not a new permission set):** job ID; authenticated actor and current authority; workspace; exact immutable policy ID/version; adapter and pinned identity; execution destination and operation; exact enrolled Runner instance/workspace binding; receipt approval, expiry and live revocation; and the required input/result references. Reject missing, inconsistent, stale, unknown or extra authorization-bearing fields. All the bindings required by ADR-0012 remain mandatory at their prescribed enforcement points; this list is not permission to omit any gate or to treat an adapter/profile label as an identity.

### 2.3 DP-049 — result/artifact integrity and release

| Option | Benefit | Limitation | Assessment |
|---|---|---|---|
| Trust output bytes without a binding | Minimal machinery. | Cannot distinguish job/instance substitution, accidental corruption or stale output. | Insufficient for the required evidence binding. |
| Bind a cryptographic digest to the originating job and Runner instance in a closed manifest | Detects byte changes and binds the result reference to the claimed job/instance; can be checked before accepting the object. | A digest is not a signature, trusted identity, safe-content verdict, ACL, source permission or release authorization. The manifest's integrity depends on its channel and authoritative record. | Required minimum design: bind result digest to job and instance, with workspace and exact policy/version and output-manifest identity as applicable. Use the already-approved channel/contract; do not imply new key custody. |
| Add a separate artifact signature/key family | May be useful if a future storage/transfer channel breaks the authenticated binding or requires independently verifiable origin. | Introduces key custody, rotation, identity, replay and recovery policy; may duplicate the transport/authority contract. | Not the default. Add only if a documented channel change establishes need, and then return for review and any required owner decision. |

**Release rule:** after integrity/binding validation, re-check current receipt/authorization and the applicable workspace policy, source ACLs, classification, source existence/revocation and artifact gates immediately before persistence, reuse, export or release as required by ADR-0012. Any failed or unavailable check holds/denies the result. A result digest never makes the artifact trustworthy by itself. Physical retention/deletion choices remain in their existing Q7/deferred tracks.

### 2.4 DP-051 — admission, deadline and cancellation measurement

Compare fixed arbitrary quotas, unbounded admission, and measured limits. The engineering direction is to measure bounded admission and execution behavior for each future profile/workload and propose values through the applicable approval process; this package sets **no numbers** for queue size, concurrency, CPU, memory, process count, disk, output, wall-clock deadline, cancellation wait, or evidence lifetime. An absent or unsupported resource-control mechanism is a profile failure, not a reason to widen the host boundary.

Any future implementation must preserve ADR-0012 cancellation safety, not redefine it: queued cancellation prevents dispatch; cancellation of running work is not terminal until termination is confirmed; uncertain or missing acknowledgement keeps the work fenced/held and does not release resources or outputs for reuse; dispatch/cancel races are serialized; repeated cancellation is idempotent. Tests must verify those state transitions with synthetic work. The mechanisms, actors, recovery details and numerical bounds that require owner decisions remain gated. Measurement is not authorization to activate.

## 3. Reproducible test-inventory criteria (DP-052)

**Execution status:** no tests in this inventory were run for this docs-only task. These are future acceptance criteria. Run only after a separately authorized evaluation plan exists, on an isolated disposable target with synthetic fixtures and no external route. Nothing in this section authorizes attack testing against a host, endpoint or service. Use benign boundary probes and independently observed enforcement results; do not use a live service, provider, credential or research data.

### 3.1 Test record and procedure

Each future test case must have a stable ID and record: profile ID; exact target and environment fingerprint; test/harness and fixture identities; prerequisite gates; positive control; negative/control case; expected result; independent observation source; actual outcome (`PASS`, `FAIL`, `BLOCKED`, `SKIPPED`); and evidence artifact references. Record non-sensitive diagnostics only. A skipped, unobserved or ambiguous case is never a pass.

For every profile-specific run:

1. Verify the test target matches the predeclared profile manifest and is disposable, isolated and synthetic-only. If identity/configuration differs or any route to a real endpoint exists, stop and mark blocked.
2. Validate that the harness and independent observation channel work using a harmless positive control limited to the designated workspace or offline harness. A failed positive control makes corresponding negative results inconclusive.
3. Execute the declared denial cases, observing both from within the boundary and at an appropriate host/OS enforcement point. Do not count the job's own report as independent proof.
4. Exercise setup, cancellation and cleanup failure states in the disposable harness. Confirm no job starts before prerequisites; no output is released while authorization or cleanup is uncertain.
5. Reconcile every planned test ID against results; explicitly classify skips/blocks/failures. Package the run manifest and evidence digests, then obtain independent review of the exact claimed target and results.

### 3.2 Cross-profile test inventory

| Test family / ID prefix | Positive control | Required negative/fault cases | Required observation and qualitative acceptance |
|---|---|---|---|
| `CFG` — exact configuration and provenance | Independently read the target's declared OS/runtime/image/config identities. | Mismatched or unknown build, changed security policy, unexpected mount/device/integration, unpinned artifact or missing required feature. | Inventory agrees with the declared exact profile. Unknown, changed or unsupported inputs cause **no execution** and invalidate the profile claim. |
| `FS` — filesystem and transfer | Read/write only the dedicated synthetic workspace; verify a declared test output reaches an isolated harness collector. | Attempt access to sibling/other-workspace, host/profile/system/service/policy/control and credential locations; exercise representative path-alias, link, mount-change and concurrent-update conditions without using sensitive files. Alter, omit, duplicate or substitute staged objects/manifests. | OS-observed denial outside the boundary; only declared staged objects cross; digest/manifest mismatch denies; no unexpected host mutation or exposure. Any ambiguous access or transfer fails the profile. |
| `PROC` — identity, process and lifecycle | Confirm expected isolated principal and a contained benign child process. | Attempt inspection or control of unrelated host/job processes; unexpected identity/privilege; detached descendant; supervisor loss or termination uncertainty. | Independent host/supervisor observations match the expected principal and process boundary. All descendants are accounted for before cleanup/reuse; uncertainty holds/quarantines and blocks admission. |
| `NET` — deny-by-default network | Offline harness confirms monitoring detects a deliberately attempted synthetic test flow without forwarding it. | Attempt representative outbound, local-host, private/LAN, name-resolution and alternate-stack paths only in a no-route disposable harness. Include unset/invalid policy and monitor loss. | No packet reaches an external or host/intranet destination; independent host enforcement/capture confirms denial. The harness sink is not allowlisted product egress. Any observed or unaccounted path fails. No Control-Plane endpoint test is authorized. |
| `RES` — resource enforcement | Bounded benign workload stays within the test harness's declared limits. | Synthetic resource pressure, child multiplication and output growth; limit mechanism unavailable or policy changed. | OS-enforced limits and supervisor response are observed; host impact remains bounded by the separately reviewed test setup. Numerical thresholds are supplied only by a future approved profile/workload plan, not this document. |
| `XFER` — DP-033 transfer lifecycle | Stage an immutable synthetic input and collect one declared output after normal, confirmed termination. | Missing/modified/duplicate manifest entry; traversal/alias; partial staging; crash during copy; cancellation before termination; attempt to use stale workspace/output. | No broad mount or alternate path; exact object identity and job association verify; incomplete/uncertain transfer is rejected/quarantined and cannot be released or reused. |
| `AUTH` — DP-042/044–048 status, freshness and bindings | In a future authorized, isolated synthetic authority fixture, a current matching record is resolved at the required checkpoints. | Authority unavailable/stale/contradictory; receipt denied/revoked/expired; wrong job, actor, workspace, policy version, adapter, operation, destination or Runner; unknown schema field/version; replay/concurrent consume; clock/status uncertainty. | Control Plane and Runner independently deny where required; there is no cached-positive allowance; durable job ID is consumed at most once even under concurrency/restart. No dispatch occurs while B6 or any gate is active. |
| `OUT` — DP-049 result binding/release | Verify a synthetic output manifest and digest against its originating job/instance record. | Alter output/digest/identity/policy binding; substitute another job/instance/workspace; revoke source/ACL or change current policy before release; make authority unavailable. | Mismatch or loss of live authority denies/holds before persistence, reuse, export or release. Digest validity does not bypass ACL/classification/source checks. |
| `CXL` — DP-051 admission/cancellation | Queue and complete synthetic work under the future test configuration. | Cancel before dispatch; cancel while running; race dispatch with cancel; repeat cancel; lose termination acknowledgement; supervisor/Runner failure; retry with uncertain old job. | State transitions satisfy ADR-0012; no post-cancel start, no early terminal status/resource release/output release, no duplicate execution and no reuse until termination is confirmed. |
| `CLEAN` — cleanup and recovery | Verify ordinary completion cleans the synthetic workspace before a later isolated case. | Timeout, forced stop, partial setup/teardown, host/guest restart, monitor loss and cleanup uncertainty. | All relevant processes, mounts/volumes, temporary work and network attachments are accounted for. Unknown residue blocks reuse and keeps the instance/profile unavailable; no fallback. |
| `B6` — dispatch and activation gate | Exercise a non-dispatching test harness path that confirms the explicit gate is present. | Valid-looking synthetic receipt with Runner absent and with a test-double Runner present; evidence pass without separate activation; any isolation failure. | Explicit rejection remains active until receipt and ADR-0012 gates and separate activation decision are satisfied. Absence of a Runner alone is not a passing rejection test. Test never dispatches. |
| `EVID` — evidence integrity/change invalidation | Independently replay the manifest against exact artifact/config/test identities. | Tamper with manifest/result, omit failed or skipped case, substitute a different profile's evidence, or materially change an input after proof. | Any mismatch, omission, non-reproducible result or material change makes evidence invalid/stale and the profile unavailable until re-evaluated. |

### 3.3 Qualitative pass/fail rules

- **PASS** means every mandatory case for the exact scope completed with functioning controls and independent observations, no unexplained result, and reviewer acceptance of the bound evidence. It is still not profile activation.
- **FAIL** means any forbidden access/flow/side effect occurred; any mandatory positive control failed; any binding, policy or observation contradicted the claim; or any cleanup, cancellation or authority uncertainty was treated as allow.
- **BLOCKED** means a prerequisite, authorized target, independent observer, evidence input or required decision was absent. Blocked is not pass or evidence of safety.
- **SKIPPED** means a case was not run. Skips remain visible and cannot be counted as passes or silently excluded from the inventory.
- Numerical workload thresholds and time budgets belong to measured and separately approved profile/workload decisions. No value is inferred from a CI runner, local development environment, earlier proposal or this test plan.

## 4. Evidence-binding contract (DP-053a)

### 4.1 Minimum evidence manifest

A future evidence packet must be a closed, versioned, integrity-protected record with at least these non-secret fields. The concrete serialization/signing mechanism must not introduce Runner key custody; if the existing authenticated channel is insufficient, that is a separate design and approval question.

| Evidence field | Binding requirement |
|---|---|
| `evidence_contract_version`, `profile_id` | Identifies the reviewed schema and one candidate profile; unknown versions/fields fail closed. A profile ID is not proof by itself. |
| Target fingerprint | Exact OS edition/distribution, build/kernel, architecture, patch/security-feature state; local/server class; and relevant host/hypervisor/runtime identity where present. Values must be observed on the target, not copied from a generic profile label. |
| Runner and artifact identities | Runner/supervisor/verifier build identities and digests; adapter identity only where relevant to the claimed boundary; guest/base image provenance and digest where used. No credential or provider-auth material. |
| Effective configuration | Digests and non-secret values needed to reproduce effective isolation: identities/privileges, mounts, network policy, runtime/hypervisor settings, resource controls, transfer policy and relevant OS security configuration. Avoid recording sensitive paths or secret-bearing configuration. |
| Test inventory and run | Complete planned case IDs, test/harness and synthetic-fixture identities, execution environment, run time, outcomes and explicit skip/block/failure reasons. Each test result is bound to the same target/config/artifact identities. |
| Independent observations | Non-sensitive host/OS enforcement observations and monitoring-health evidence sufficient to corroborate the in-boundary probes. Identify the source and its relationship to the implementation under test. |
| Results and change record | Digests of raw non-sensitive result artifacts, summary, deviations, known limitations and changes since prior evidence. Preserve failed/blocked/skipped records; do not replace history with a passing summary. |
| Review | Review outcome and finding references for an independent reviewer who did not implement or configure the evaluated boundary. This document does not appoint a reviewer or decide reviewer qualification/authority. |

No raw credentials, tokens, provider login state, private keys, user content, real research data or unnecessary host-sensitive payloads belong in the packet. If an evidence item cannot be collected without those, it is omitted and the resulting claim is narrower or blocked; evidence requirements do not authorize secret access.

### 4.2 Binding and invalidation rules

1. Every result refers to one exact tuple: profile ID + target fingerprint + Runner/supervisor/verifier artifacts + effective configuration digest + test/harness/fixture version. Evidence from different tuples cannot be combined to fill missing cases unless the reviewer documents and justifies that exact composition without weakening the claim.
2. The independent reviewer checks manifest/result integrity, planned-versus-executed test completeness, all non-pass outcomes, observation provenance, scope of the claim and residual assumptions. Reviewer identity/qualification and appointment remain subject to applicable authority; this package claims no review has occurred.
3. A material change to OS/kernel/build/security feature, hypervisor/runtime, guest image, Runner/supervisor/verifier, adapter boundary, identity, mounts, network or resource policy, transfer mechanism, test harness/monitoring, or any relied-on trust configuration invalidates affected evidence. The profile returns to **INACTIVE / UNVERIFIED** until affected proof is repeated and independently reviewed.
4. No general evidence expiry duration is assigned here. The acceptable freshness/expiry policy and any verifier appointment that requires owner authority remain **【要決定】** where applicable. Known material change invalidates immediately; absence of a known change does not itself prove evidence remains current.
5. A successful packet supports only the specifically tested environment, workload assumptions and stated residual-risk boundaries. It does not certify another build, OS family, deployment class, profile, adapter, network path or credential flow.

### 4.3 Permitted evidence claim form

A future report may state only that a named profile was evaluated on the listed exact target/artifact/configuration identities, that enumerated cases had their recorded outcomes, that the evidence received the recorded independent review, and which limitations remain. It must state `INACTIVE / UNVERIFIED` unless a **separate** activation decision and all current gates are evidenced. Do not claim “secure”, “escape-proof”, “supported”, “verified profile” or “activated” from a plan, partial test, skipped case or design recommendation.

## 5. Candidate-profile conformance checklists

These checklists refine the candidate profiles in HYBRID_ISOLATION_PROFILES.md; they do not select a candidate, broaden support, certify any OS family, or define residual-risk acceptance. Check every item on the exact target. `N/A` needs a documented technical reason and reviewer acceptance; if an item is actually required for the claimed boundary, inability to test it means **BLOCKED**, not pass. All profiles also require §5.1 common checks and the DP-033/042/044–049/051/052/053a contracts above.

### 5.1 Common checklist — all candidates

- [ ] Profile ID, local/server deployment class and exact OS/build/architecture are declared; no generic family-level inference.
- [ ] OS-level process, filesystem and network enforcement is independently observed; application policy or adapter flags alone do not count.
- [ ] Job principal is distinct and least-privileged; interactive user/session, other workspaces/tenants, credentials, policy/receipt state and runtime/control interfaces are not exposed.
- [ ] Only declared job-scoped synthetic input and output cross the boundary through the evaluated DP-033 transfer path; no alternate mount/device/IPC path is unaccounted for.
- [ ] Default-deny network enforcement is checked independently at the OS/host boundary for all relevant address families and paths. No destination is allowed by this package.
- [ ] Required resource controls are enforced, but their numeric values come only from separately measured/approved workload limits; feature absence fails closed.
- [ ] Setup verifies exact image/config/policy before job start. Failure or uncertainty starts no job and triggers no host fallback.
- [ ] Live authoritative status/binding checks, one-use consumption and output live-revalidation behavior are demonstrated only in an authorized synthetic test harness; there is no product dispatch in this task.
- [ ] Cancellation/termination/cleanup state is independently reconciled; uncertain state blocks reuse and output release.
- [ ] Evidence manifest binds exact target, artifacts, effective configuration, tests and observations; independent review and all limitations are recorded.
- [ ] Explicit statement: no profile activation, no egress, no provider authentication/credentials and no real data authorized.

### 5.2 Windows local desktop candidate (W-D)

- [ ] Exact Windows edition/build, architecture, patch/security features and (if used) Hyper-V/Sandbox/runtime versions are captured.
- [ ] Effective job token/principal and inherited handles are checked against the interactive-user boundary; no interactive session, user profile, credential store, clipboard/device or broad host folder is exposed.
- [ ] Filesystem ACL/reparse behavior, job workspace and staged transfer are observed through OS-level controls; representative alias/traversal and concurrent-update cases deny outside the job scope.
- [ ] Job Object/process containment is treated only as lifecycle/resource evidence, not as filesystem/network/kernel isolation. Every child and cleanup result is accounted for.
- [ ] Host firewall and guest/network policy observations show deny-by-default behavior; no loopback-to-host, LAN or external route is assumed safe from guest-only tests.
- [ ] If VM-backed, integration features, shared folders, guest services, devices, network and image/config identity are independently enumerated; any enabled path is explicitly tested or disabled.
- [ ] Known incomplete Windows sandbox diagnostics or development-loop containment are not reused as product proof.

### 5.3 Windows server candidate (W-S)

- [ ] Exact Windows Server edition/build, servicing state, isolation mode, runtime/hypervisor and immutable guest/image identity are recorded.
- [ ] Simultaneous synthetic principals/workspaces prove job-to-job and tenant-to-tenant separation; no service/admin identity, host process mode, broad host mount, runtime socket or management surface is exposed.
- [ ] Service restart, worker loss and host/guest restart scenarios reconcile processes, attachments, mounts and staged output; uncertainty quarantines the instance.
- [ ] OS-observed network controls deny host, peer tenant, LAN and external access; host/service-plane separation is evaluated independently of the guest's claims.
- [ ] Resource limits are enforced for concurrent synthetic jobs under a separately reviewed test envelope; this package assigns no concurrency or capacity number.
- [ ] Desktop evidence is not used to satisfy the server claim.

### 5.4 Linux local desktop candidate (L-D)

- [ ] Exact distribution, kernel/build/config, architecture, namespace/runtime, LSM/seccomp and cgroup feature state are recorded as applicable.
- [ ] Effective UID/GID mapping, user/mount/PID/network namespace composition, capabilities, mount propagation and descriptors are independently inspected; missing required feature or unexpected host namespace denies.
- [ ] Rootless OCI/namespaces are described accurately as sharing the host kernel; they are not represented as a VM or separate-kernel guarantee.
- [ ] No host PID/network, user home, credential path, runtime socket, broad bind, device or privileged mode is exposed; access denial is observed from host-side controls.
- [ ] IPv4/IPv6, loopback-to-host, local/private route and name-resolution denial are independently observed; missing filter support fails closed.
- [ ] Process descendants, session/namespace cleanup and job scratch state are reconciled after cancellation and supervisor/runtime failure.

### 5.5 Linux server candidate (L-S)

- [ ] Exact distribution/kernel, patch/config, LSM/seccomp, runtime/hypervisor, host policy and guest/image digests are captured.
- [ ] Concurrent synthetic tenants/jobs demonstrate isolation of PID, mount, identity, IPC, storage and network views; host namespaces, kernel interfaces, control sockets and cross-tenant volumes are denied.
- [ ] Host-level network observations show no unapproved host, tenant, intranet or external path; a container-local “no network” setting alone is insufficient evidence.
- [ ] Resource pressure, supervisor failure, restart and cleanup leave no unaccounted process, mount, namespace or network attachment; unknown residue fences the instance.
- [ ] If using layered VM + container, each boundary and the combined failure/teardown paths are tested; layers are not assumed to compose automatically.
- [ ] Local-desktop or generic Docker QA evidence is not used to satisfy the server claim.

## 6. Explicitly gated choices and non-claims

The following are outside this package and stay **【要決定】** or otherwise gated as recorded by the classification and owner decisions:

- Runner trust anchor, enrollment/identity proof, trust authority, keys, custody, attestation, rotation, recovery and verifier authority/qualification.
- Any Runner↔Control-Plane endpoint, network topology, firewall exception, destination, egress, DNS/proxy or external communication. DP-042/044–048 describe behavior conditional on an independently authorized channel; they do not authorize one.
- Provider credential supply, login/session reuse, broker, provider access or authentication testing. Q4's official CLI preference does not grant credential access.
- Exact Windows/Linux technology, build support matrix, threat tier, residual-risk acceptance, and any unverified profile's activation. Q3 fixes the direction, not the selections or risk acceptance.
- Receipt TTL values, grace/skew values, capacity/admission/deadline/cancellation numerical bounds, evidence lifetime/expiry values, and production time/storage decisions. No numerical bound is inferred here.
- Real-data use, production exposure, retention/deletion policy and any safety-boundary change.

This design does not report executed isolation tests, independent profile review, successful conformance, or activation. B6 continues to reject dispatch before any applicable receipt and ADR-0012 gates pass. No unverified profile may run, and there is no host fallback.

## 7. Adversarial self-review and source reconciliation

- **Classification scope:** each detailed proposal maps to an explicit `ENGINEERING_DETAIL` row above. Owner-decision, owner-policy-resolved, existing-decision and deferred rows are named only to preserve gates; no recommendation from older proposals overrides their current classification.
- **Trust/channel creep:** the online checks for DP-042/044–048 could be misconstrued as approval to connect a Runner. This package explicitly makes all such behavior conditional on a separately approved channel and chooses no endpoint, trust root or transport configuration.
- **Credential creep:** file transfer and CLI references could be mistaken for permission to access provider sessions. Only synthetic bundles are described; no credential or provider login is staged, read or tested.
- **Evidence overclaim:** positive/negative test inventories and checklists specify future criteria only. They do not prove or activate W-D, W-S, L-D or L-S. Missing/blocked/skipped evidence cannot be converted into a pass.
- **Risk acceptance creep:** comparing shared-kernel and VM candidates does not accept residual risk. Exact profile, support, threat-tier mapping and risk acceptance remain separately gated.
- **Numeric-bound creep:** the plan requires measured limits but supplies no values, tolerances, TTLs, timeouts, quotas or freshness interval. Receipt TTL stays DP-010/011; admission bounds are not selected.
- **Transfer creep:** the staged-bundle approach is a technical recommendation for evaluation, not permission for general host access, a new trusted broker, a mount, or artifact release. The digest is explicitly not authorization or a content-safety decision.
- **Source/code distinction:** proposal and profile documents describe candidate controls, while this package remains a design artifact. It does not treat code, prior QA, skipped live tests or development-loop containment as proof for a product Runner. Any source implementation/documentation disagreement discovered later must be recorded, not silently reconciled into a stronger claim.
- **Independent review:** task instructions prohibit subagent delegation. This is the implementer's adversarial self-review only, not the independent security review required for future profile evidence/activation.

## References

- [Owner formal decisions Q1–Q7](OWNER_DECISIONS_2026-11-09-EVENING.md)
- [Owner queue classification](OWNER_QUEUE_CLASSIFICATION_2026-11-09.md)
- [Hybrid isolation profile design](HYBRID_ISOLATION_PROFILES.md)
- [Hybrid step-3 isolation and trust proposals](HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md)
- [ADR-0012 — dual-plane model gate and Agent Runtime](../architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md)
- [Hybrid Agent Runtime threat model](../security/HYBRID_AGENT_THREAT_MODEL.md)
