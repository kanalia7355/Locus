# HYB-A1-job-approval-adr

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Use the isolated
QA venv `.loop/runtime/qa-venv` (recreate if missing: Python313 venv +
`pip install -e ".[dev]" -r backend/requirements.lock`); NEVER touch the shared
`.venv` (broken). Never push to `main` or `loop/local-development`; no subagents.

Full process: read `AGENTS.md` + governance docs first; create your worktree with
`git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/<SLUG> -b loop/<SLUG> origin/loop/local-development`;
implement; self-review adversarially; run the full QA cycle until ALL green
(full pytest tests -q --ignore=tests/e2e, ruff check + format --check, mypy
backend/app, secret scan; plus frontend lint/test/build/playwright when UI
touched); Conventional Commit; push; wait branch CI; fix/re-push until green
(bounded); append progress + SHA + CI evidence here. Branch deleted after
integration.

---

# HYB-A1 — Job-approval/authorization ADR draft (docs only)

Deliverable: `docs/architecture/decisions/` ADR DRAFT (next number, follow the
existing format; likely 0013) for the Phase-2/Plane-R **job approval and
authorization receipt** mechanism — the hard prerequisite for any
dispatch-capable Plane-R code (slice 2b) per
`docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md` sections 2.6/E1-E2 and its
owner-resolved item 11 (`docs/plans/OWNER_DECISION_REGISTER.md` RESOLVED
2026-11-09; also `docs/plans/PHASE2_DELEGATION_SPEC.md`).

Requirements for the draft: receipt content (actor, approver, workspace,
policy version, adapter/destination, operation, expiry), authoritative issuer
and revocation mechanism, recheck points at enqueue AND runner execution,
denial/revocation/stale-approval semantics and their regression tests,
actor/approver scopes, approval-expiry policy, and integration with the
existing role/permission ceilings (NON_ADMIN) and audit conventions. Mark
everything undecidable as 【要決定】; do NOT approve activation; status DRAFT.
Ground every claim in the real repository (cite files). Self-review against
ADR-0012 (ACCEPTED), the threat model, and the step-2 design's E1/E2. Commit
`docs(adr): draft the job approval and authorization receipt ADR`; push your
branch `loop/HYB-A1-job-approval-adr`; wait branch CI until green.

## Progress

- 2026-11-09 (HYB-A1): Read brief + governance sources. Read step-2 design S2.6
  (authoritative job-level approval receipt), S3.2 E1/E2, S6.11 slice-2a
  acceptance, S8 resolution banner; OWNER_DECISION_REGISTER RESOLVED 2026-11-09
  (delegation conditions A; sequencing constraints reaffirmed); ADR-0012
  (ACCEPTED) S4.1 and open item (11); threat model T-T1/T-S1/T-R1/T-E1/T-E2 and
  follow-up 3. Verified code state: backend/app/agents/registry.py (B6
  dispatch_attempt rejection ~L716, immutable versioned workspace_policies,
  egress_mode CHECK local_only only, presence-only adapter_credentials) and
  backend/app/service.py PH2-D delegation model (families/grants/events +
  immutability triggers, _delegation_authority, TTL 900-604800s in
  create_delegation, NON_ADMIN ceilings ~L25/L2696/L2738, audit table ~L418).
- Created worktree .loop/runtime/worktrees/HYB-A1-job-approval-adr on branch
  loop/HYB-A1-job-approval-adr from origin/loop/local-development (951c3cf).
- Wrote docs/architecture/decisions/0013-job-approval-authorization-receipt.md
  (DRAFT): receipt content table (receipt/job/actor/approver/workspace/exact
  policy version/adapter/destination/operation/decision/issued/expiry/
  revocation + runner-instance binding [YOTEI-KETTEI]); authoritative-issuer
  properties with candidate architectures [YOTEI-KETTEI]; revocation mechanism
  options with fail-closed offline semantics [YOTEI-KETTEI]; mandatory
  E1-enqueue + E2-execution independent rechecks (B6 gate preserved);
  denial/revocation/expired/stale-policy/binding-mismatch/unavailable-authority/
  replay semantics + the S6.11 regression matrix (E1 and E2, incl. revocation
  between enqueue and execution); actor/approver scopes tied to the 2026-11-09
  grantor/ceiling conditions; expiry policy oriented on the delegation TTL
  without selecting values; audit/role-ceiling integration (agent.receipt.*
  naming [YOTEI-KETTEI], immutable receipt rows, no new NON_ADMIN permission
  without owner approval). 23 [YOTEI-KETTEI] markers; 8-item owner-decision
  inventory; explicit no-activation status. Self-review fixed two overclaims
  (threat-model follow-up 3 scope; added PHASE2_DELEGATION_SPEC citation).
  Docs only; no code touched.
- Commit 315778c77838b1cb8e4e58fbbc9e61e25eb3558e - "docs(adr): draft the job
  approval and authorization receipt ADR" - pushed to
  origin/loop/HYB-A1-job-approval-adr (new branch; never touched main or
  loop/local-development).
- Branch CI evidence (run set on head 315778c, 2026-11-09): PR title convention
  run 42533517562 SUCCESS; Prototype quality run 42533517636 SUCCESS; Loop
  engine checks run 42533517548 SUCCESS. All three green on first push; no
  fix/re-push cycles needed. Docs-only change; the branch CI run is the
  verification evidence.
- Peer-agent notifications observed (PH2-RV review, HYB-A2, PH2-C2, PH2-UI on
  separate branches/briefs): no file or branch overlap with HYB-A1; no action
  taken on their behalf.
