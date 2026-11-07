# PH1-H — Independent read-only review of the hybrid step-2 design proposal

Agent: append your progress under "## Progress" below. You are a REVIEWER: do not
modify any file other than this one (your progress notes), do not spawn agents,
do not push, do not create a persistent worktree. Work in the main checkout
read-only (or a personal throwaway clone you delete afterwards).

## Task brief

Review `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` at the integrated HEAD
of `loop/local-development` (commit 36c0af4 or later). It is a DRAFT DESIGN
PROPOSAL for hybrid 実装順 2 (Agent Registry / common Agent Adapter / Workspace
Policy), produced by slot F (PH1-F), that must NOT weaken any approved boundary
(ADR-0011 / C-min zero-tool boundary, approval gates, synthetic-data-only rule,
existing tests).

Review criteria:
1. **Evidence validity**: spot-check at least 10 file-path citations against the
   real repository (e.g. `loop_engine/toolless_boundary.py`,
   `loop_engine/codex_runner.py`, `loop_engine/catalog_snapshot.py`,
   `loop_engine/app_credentials.py`, `loop_engine/docker_boundary.py`,
   `backend/app/service.py`, ADR files). Rate whether each supports the claim.
2. **Boundary preservation**: does any part of the proposal weaken or bypass the
   zero-tool boundary, approval gates, or existing tests? Check rules B1–B7
   against the actual C-min code paths. Flag ANY implicit weakening.
3. **Threat-model coverage**: are enforcement points E1–E8 actually mapped to the
   threat model's T-S1…T-E4 mitigations? Any material threat uncovered?
4. **Completeness**: registry/adapter lifecycle, credential presence-only model
   (要件5), workspace policy fields (要件2/3), slices 2a–2c acceptance criteria,
   regression plan — anything missing for an ADR draft?
5. **要決定 discipline**: are the 10 §6 items genuinely open decisions rather
   than silently made by the proposal? Is anything decided that should not be?
6. **Consistency** with `docs/security/HYBRID_AGENT_THREAT_MODEL.md` (accepted
   after minor fixes) and `docs/plans/PHASE_SPEC_RECONCILIATION.md`.

Report findings with severity (critical/high/medium/low), location (section),
evidence, and a fix recommendation. End with a verdict: accept / accept after
minor fixes / needs major rework. Do not edit the reviewed document.

## Progress

- 2026-11-07: Read the task brief and required governance/product/architecture/bootstrap docs. Confirmed main checkout is `loop/local-development` at `36c0af4124e2c4671c83c6790bfbc8736d7bdc15` (meets requested 36c0af4+); `.bootstrap/complete.json` exists. Existing untracked files include this assigned progress file and `docs/plans/MINIMAL_LOOP_POLICY_PROPOSAL.md`; neither was changed during setup. Reviewed the full proposal, accepted threat-model review history, and reconciliation document; now validating cited implementation evidence and boundary/test details.
- Evidence spot-check completed against 14 source/test paths: most citations support their stated limits; key correction is that `loop_engine/toolless_boundary.py` is the launcher/probe/configuration layer (its C-min probe is diagnostic-only), while the actual request/response contract enforcement is in `loop_engine/audit_transport.py`, `loop_engine/model_gate.py`, and `loop_engine/c_min_runtime.py`. Confirmed the named regression files exist and inspect relevant Lite/tool-call cases. Reviewing findings for classification defaults, dispatch approval/identity, artifacts, and §6 decision discipline.

## Final independent review report (read-only)

**Reviewed target:** `docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` at `loop/local-development` HEAD `36c0af4124e2c4671c83c6790bfbc8736d7bdc15`.

### Findings

1. **HIGH — §3.1 classification defaults; §3.2 E6; §5 Slice 2c. The stated fail-closed default is permissive for data classification.** `classification_ceiling` is defined as the highest classification the policy may touch, but defaults to `機密` (the highest/sensitive class). `local_only` and an empty egress allowlist constrain sending, not whether a runner may read/process sensitive local data. The note that egress above `公開` is “effectively deny” conflates classification authorization with destination authorization. Slice 2c acceptance only tests non-downgrade of derived answers/citations; it does not explicitly test unclassified input denial before context assembly, attachments, or every output path. **Fix:** default to no permitted classification/deny-all until an administrator explicitly selects a ceiling; define classification and egress as independent gates; add negative tests for unclassified inputs before prompt assembly and output/citation propagation.

2. **HIGH — §2.2, §3.2 E1/E2, §4 and §5.2b. Job-level approval is claimed but not part of dispatch/admission eligibility.** The proposal says the separate runtime has “its own approval gates,” but dispatchability is specified by adapter status, heartbeat, workspace binding and allowlist. E1/E2 recheck identity, expiry and policy version, not an authoritative human/user approval or permission decision bound to the job. §4 only says reusing `run_authorization.py` is future design input; those Loop gates are not wired into product agent jobs. B6 correctly blocks current execution, but it does not specify the future gate. **Fix:** define an authoritative approval/authorization receipt bound to actor, workspace, policy version, adapter/destination and operation; recheck before enqueue and runner execution, or explicitly make the separate approval ADR a hard prerequisite to any dispatch-capable code. Test denial, revocation and stale approval. Do not use “no runner exists” as the 2a dispatch test; assert the Control Plane rejects dispatch while B6 is active.

3. **HIGH — §3.2 E1/E6; §5 Slice 2c; threat T-I2/T-T3 and requirement 7. Runner outputs/artifacts lack a defined workspace/ACL/classification enforcement path.** E1 binds a job to a workspace, while E6 covers input classification and existing RAG citations. There is no enforcement point for validating a runner-produced artifact/log before storage, retrieval, export or reuse, nor acceptance coverage that a derived artifact cannot cross workspaces or downgrade classification. This leaves the accepted threat of leakage through derived data and the requirement to policy-check artifacts/logs materially under-specified. **Fix:** specify output artifact identity/binding to the originating workspace and policy version, ACL/classification inheritance and revalidation before persistence/use/export; add cross-workspace, revocation/deletion and downgrade regressions. T-T4 audit-log protection is explicitly open in §6.6; keep it an activation blocker rather than implying B7 solves it.

4. **HIGH — §2.1 B5/credential model; §2.4; §3.2 E8; §6.2/6.5. Runner identity and per-device credential scope are unresolved in a way that prevents the stated protections from being verified.** The proposed `adapter_health` and `adapter_credentials` rows are keyed only by `adapter_id`, and `workspaces` has a runner *type* but no explicit runner-instance/device binding. As written, health/credential presence cannot be unambiguously tied to a particular Desktop Runner, user or OS identity. Also, `windows_tcp_peer.py` is same-SID/PID peer-validation groundwork, not evidence of separation from the user session: its `OwnedCliPeer` records the current SID and requires the child peer to match it. A runner using that user identity may be able to use/access that user's CLI credential store; a distinct identity may not be able to use the official login. §6 leaves per-OS storage/enrollment open but does not resolve this trust/credential-access conflict. **Fix:** define a runner-instance identity and bind workspace, adapter health and credential-presence metadata to it; state precisely which identity can use the official CLI credential and how a compromised tool-executing runner is prevented from exporting it. Keep activation blocked until the selected OS mechanism is tested for both access and denial cases.

5. **MEDIUM — §6.1 versus accepted threat-model §4 finding 1 / §5 follow-up 2. The ADR gate is relaxed from before step 2 to before only slice 2b.** The threat model recommends the dual-plane ADR before implementation of hybrid 実装順 2 and lists it as feeding step 2. §6.1 instead leaves adoption before “any slice 2b code,” which permits slice 2a registry/policy implementation first. Although 2a is metadata-only, this is a timing change to the accepted review recommendation, not merely a detail. **Fix:** make dual-plane ADR adoption/approval precede all step-2 implementation, or surface the altered sequencing as a separate owner decision and do not treat it as already reconciled.

6. **MEDIUM — §6.7 versus §3.1/§3.2. Cloud-egress decision is only partly open.** §6.7 leaves open whether `allowlisted` mode may exist and its activation criteria, but §3.1 already puts `allowlisted` in the policy enum and E5 specifies its per-send audit/match behavior. That implicitly selects a future policy capability before the listed decision. **Fix:** mark `allowlisted` as a non-operative placeholder conditional on owner approval, prohibit producing an enabling policy/schema until that decision, and state which classifications could ever be eligible. Also add explicit cancellation semantics to the open admission-limit decision in §6.8: T-D1 calls out cancellation, but the proposed fields/acceptance enumerate deadlines and concurrency, not cancellation.

7. **MEDIUM — §1.1 / §1.5 source attribution. `loop_engine/toolless_boundary.py` is inaccurately identified as the model-facing protocol gate.** It assembles launch settings and contains the local tool-surface probe; for C-min its `probe()` deliberately returns `diagnostic_only: true` and `no_tools: false`. The actual strict request and response enforcement is in `loop_engine/audit_transport.py` and `loop_engine/model_gate.py`, wired by `loop_engine/c_min_runtime.py`. The other cited files (`c_min_runtime.py`, `catalog_snapshot.py`, `model_gate.py`, `model_invocations.py`) support the accepted offline composition, but naming the diagnostic file as the gate risks maintaining/reviewing the wrong boundary. **Fix:** correct the module map and identify `toolless_boundary.py` as launcher/configuration/probe only. Do not imply offline implementation is runtime activation; the draft otherwise correctly preserves that distinction.

8. **MEDIUM — §5 Slice 2b B1 acceptance is narrower than B1.** The proposed import test checks that `backend/app/service.py` and `local_model.py` do not import `runner/` or registry internals. It does not test the reverse `runner/` → `backend/app/` prohibition, the Control Plane/Runner transport-only boundary, or the constraint that `backend/app/agents/` must not import Plane-M model-path code. In current code, `backend/app/service.py` combines chat/retrieval, audit and role primitives, so “agents may import service-layer primitives” is not yet a clean module-level boundary. **Fix:** define separable importable primitives or an explicit dependency interface, and add a whole-package static import-graph test for all B1 directions and allowed imports.

### Evidence validity spot-check (14 paths)

- `loop_engine/toolless_boundary.py`: exists and checks/probes tool surface, but is not the strict C-min protocol gate (finding 7).
- `loop_engine/c_min_runtime.py`, `loop_engine/audit_transport.py`, `loop_engine/model_gate.py`: support the real C-min relay/request/response enforcement and invocation wiring; strict closed schemas and fail-closed behavior are present.
- `loop_engine/catalog_snapshot.py`: verifies exact snapshot bytes/hash and required selected-model restrictions; supports the pinned-catalog precedent, not generic runner enrollment.
- `loop_engine/codex_runner.py`: verifies a received binary-hash receipt and defaults to `UnprovenBoundary`, whose require/command fail; supports B6/pinning.
- `loop_engine/app_credentials.py`: is Windows Credential Manager-only with no file fallback, but is specifically the Review/Merge GitHub App vault, not a provider CLI credential implementation; it supports only a narrow precedent.
- `loop_engine/docker_boundary.py`: verifies an immutable development QA image and supervised leases; the proposal correctly disclaims it as Desktop Runner isolation evidence.
- `loop_engine/windows_tcp_peer.py`: binds an owned CLI PID/image/job and checks same-SID loopback ownership; it does not prove separate user/runner identities (finding 4).
- `loop_engine/schemas.py`: schema helper sets `additionalProperties: false`; supports closed-contract precedent.
- `backend/app/main.py`: verifies the stated development-only, cloud-egress-false, local-only startup holds; these are application guards, not an OS network filter.
- `backend/app/service.py`: verifies `_audit` is metadata-only, role updates enforce non-admin/subset ceilings, and citations/generated answers recheck live retrieval ACLs. No product classification or runner-artifact policy appears in the checked paths.
- `backend/app/local_model.py`: verifies one local Ollama request, no declared tools/retries, and rejection of tool calls in response; supports the cited narrow adapter behavior.
- `tests/unit/test_loop_tool_surface.py` and `tests/unit/test_loop_c_min.py`: exist and cover Lite `additional_tools`, malformed/unknown request shapes, tool-call families and response rejection.
- `tests/integration/test_loop_c_min_launch.py`, `tests/integration/test_c_min_public_reference_scan.py`, and `tests/integration/test_live_docker_boundary.py`: exist; Docker live coverage is opt-in and is not Desktop Runner proof, as the proposal states.
- The listed backend regression files (`test_api.py`, `test_security.py`, `test_chat_queue.py`, `test_administration_audit.py`, `test_role_updates.py`, `test_custom_role_publication.py`) all exist. No tests were run; this was a read-only design/source review.

### Coverage and decision-discipline summary

E1–E8 map several threats credibly (T-T1/T-R1, T-S1/T-T1, T-E1/T-S3, T-E3/T-E4/T-D1, T-I1/T-R2, T-I1/T-I4, T-E2, T-S2/T-S3), with clear fail-closed intent and explicit non-activation. Coverage is not complete: T-I2 artifact leakage has no direct enforcement point; T-T3 needs enforceable classification propagation across stored/derived outputs, not only a field/default and citation tests; T-S1 and T-I3 need the runner-instance/credential trust model above; and T-D1's cancellation requirement is absent from admission acceptance. T-T4 is explicitly unresolved, appropriately, but must stay a blocker.

Most §6 items are genuinely open. Exceptions/partial decisions: item 1 permits a later ADR gate than the threat model recommendation; item 7 already makes `allowlisted` a policy value and specifies behavior; item 2 constrains any possible health probe to a benign boolean command while leaving the method/open question. Item 8 omits cancellation. Items 3–6 and 9–10 are otherwise explicitly unresolved, and synthetic-data-only remains binding. The reconciliation doc is respected on phase status, CI blocked-not-passed, existing verification contracts and the separation of local-model versus future runner concurrency; no code change, test weakening or activation claim was found.

**Verdict: needs major rework.** The draft has strong boundary-preservation language and accurately defers actual runner execution, but the classification default, absent explicit job-approval contract, artifact/classification gap and unresolved runner identity/credential model must be corrected before it is a safe ADR basis. Resolve the sequencing and import-boundary issues as well. No reviewed code/document other than this progress file was modified.
