# Hybrid agent platform: cross-check and threat model

Status: analysis/proposal. 2026-11-07. Basis: `docs/planning/locus-hybrid-agent-requirements.md`
(owner-added specification), the current code at `loop/local-development`, the ADRs
under `docs/architecture/`, and the standing threat model `docs/security/THREAT_MODEL.md`.
This document does not approve any implementation, weaken any existing boundary,
or resolve any owner decision. Findings and gaps are inputs to the phase plan.

## 1. Requirement-to-implementation matrix

Ratings: 満足 (satisfied in the approved prototype scope), 一部 (partial), 未実装
(not implemented). Every row cites files read for this analysis.

| # | 要件 | 現状の根拠 | 評価 |
|---|---|---|---|
| 1 | ハイブリッド実行（ワークスペース単位でServer/Desktop Runner選択） | No workspace concept exists; the product's "workspace" today is project-scoped documents/conversations (`backend/app/service.py` projects/conversations) and no runner selection exists anywhere in `backend/app/`. The Loop engine has executor composition (Controller → CodexRunner → pinned CLI, `loop_engine/codex_runner.py`, `loop_engine/c_min_runtime.py`) but only as a development-loop runtime, not a selectable product runner. | 未実装 |
| 2 | 管理者統制（外部AI・実行先・ネットワーク・送信範囲を組織ポリシーで制限、ユーザー設定は範囲内のみ） | Strong single-tenant precedent: startup refuses cloud settings (`backend/app/main.py` `create_app` rejects `APP_ENV != development`, `ALLOW_CLOUD_EGRESS != false`, `LOCAL_ONLY_MODE != true`); model adapter is local-only with explicit admin opt-in (`backend/app/local_model.py`, `docs/LOCAL_MODELS.md`); org policy object does not exist. Role permissions exist per project (`ROLE_PERMISSIONS`, `backend/app/service.py`). | 一部（単一テナント相当の強制はあり、組織ポリシー層なし） |
| 3 | データ分類（公開/個人/研究共有/機密、派生データへの継承、分類不明・送信禁止は拒否） | Document kinds shared/personal/attachment exist and private-by-default retrieval is enforced in every path including derived citations and generated answers (`backend/app/service.py` `send`, `_citations`, `_generated`; `tests/test_api.py` isolation tests). No 公開/機密 classification levels, no classification propagation into RAG index entries beyond ACL, no unclassifiable-data blocking (uploads default to quarantine only when the scanner is unavailable, `backend/app/scanner.py`). | 一部 |
| 4 | 実行隔離（ファイル/マウント/コマンド/ネットワークをOS・コンテナ等で強制） | For the model path: request/response gates and the zero-tool boundary exist as offline-implemented, reviewed code (`loop_engine/toolless_boundary.py`, `docs/architecture/ADR-0011-model-facing-zero-tool-gate-proposal.md`, `docs/plans/MODEL_BOUNDARY_FINAL_DESIGN.md`). This is NOT verified runtime readiness: `docs/operations/LOCAL_LOOP_STARTUP_REPAIR.md` records readiness as still false, and ADR-0011's acceptance covers design/C-min implementation only — it is neither product Agent Runtime isolation nor evidence that a product runner would be safe. `loop_engine/docker_boundary.py` exists; Docker containment tests are opt-in and skipped locally (`tests/integration/test_live_docker_boundary.py`). Product ingest parsing is bounded plain text without a sandbox (`backend/app/service.py` `_index`, `docs/INGESTION_SCANNER.md`). OS-level enforcement for product agent runtimes: designed, not activated, not verified. | 一部（開発Loop境界は設計・実装済みだが活性化未証明、製品のAgent Runtime隔離は未実装） |
| 5 | 個人認証（公式CLIのログイン方式、認証情報は利用者端末に保持、転用禁止） | Application identity is local: Argon2id accounts, CLI provisioning, session digests (`backend/app/service.py`, `backend/app/cli.py`). Provider credential handling exists only for the Loop audit worker: encrypted audit-only cache with OS-stored key (`docs/architecture/ADR-0010-encrypted-audit-auth-proposal.md`, `loop_engine/app_credentials.py`) and an explicit no-repurposing stance in `docs/plans/MODEL_BOUNDARY_FINAL_DESIGN.md` ("Support, authentication and usage conditions"). Product users cannot yet bind their own official CLI credentials; no per-user credential vault. | 一部 |
| 6 | 監査（利用者/ワークスペース/実行先/モデル/権限判定/操作/外部送信、ログ自体の保護） | Metadata-only audit table for product actions (`backend/app/service.py` `_audit`, admin view); loop engine has extensive audit machinery (`loop_engine/audit_*.py`, spool, bundles). ADR-0010 covers only an encrypted audit **authentication cache** for a dedicated audit identity — it does not protect the product audit log. Today the product audit table has no confidentiality or tamper-evidence control beyond the SQLite transaction; log confidentiality/retention is an open design requirement. Missing: model/execution-destination dimension in product audit, outbound-send audit (nothing external is sent today). | 一部 |
| 7 | 安全な通信（Runnerからの認証済み接続、ジョブ/成果物/ログのポリシー検査） | Loop side has peer-identity groundwork: `loop_engine/windows_tcp_peer.py`, `windows_pipe.py`, service worker/host modules. Product API is loopback-only with host/origin pinning (`backend/app/main.py` middleware). No authenticated runner registration, no job/artifact policy inspection for a product runner. | 一部 |
| 8 | UI（OpenCode風のプロバイダー/モデル/認証状態/実行先/権限設定） | Existing admin UI: model runtime settings page (`frontend/src/ModelSettings.tsx`, `ModelRuntime.tsx`), users/roles/audit/ingestion pages in `frontend/src/App.tsx`. No provider/model catalog management UI, no execution-destination selector, no per-user effective-access screen beyond role editor. | 一部 |

## 2. Threat model (STRIDE) for the target architecture

Scope: Control Plane (Locus Server), Server Runner, Desktop Runner, Agent
Adapter, Locus UI. Assets follow `docs/security/THREAT_MODEL.md` (unpublished
research, identities, ACLs, histories, credentials, audit logs, model prompts)
plus new ones: workspace policies, runner credentials, job payloads, derived
agent artifacts.

### Spoofing
- T-S1 Runner impersonation: a fake Server/Desktop Runner connects to the Control
  Plane. Mitigation direction: mutual, pinned runner identity (potential reuse of
  the TCP-peer/PID/SID verification groundwork in `loop_engine/windows_tcp_peer.py`).
  ADR-0009/0010 are only a NARROW precedent (a dedicated audit worker and its
  authentication cache) — they do not establish a general product-runner
  enrollment/rotation pattern; a dedicated runner/workspace ADR must define
  enrollment, credential rotation and revocation. Open: 【要決定】 enrollment
  ceremony and trust root.
- T-S2 User spoofing via stolen sessions: existing controls (opaque digested
  sessions, expiry, revocation) carry over; hybrid UI must never embed provider
  tokens in the Locus session.
- T-S3 Adapter spoofing of provider identity: a malicious adapter could claim
  "Codex CLI" behavior. Mitigation: pinned binary + version + catalog snapshot
  checks as in `loop_engine/catalog_snapshot.py` / `codex_runner.py`; unknown
  variants stop (existing rule, extend to adapters).

### Tampering
- T-T1 Job/artifact tampering, replay and stale policy: job payloads and
  artifacts need signing plus a policy gate on the Control Plane (requirement 7),
  AND an explicit freshness/binding contract: job identity, expiry, binding to
  the workspace and policy version, a policy recheck at dispatch, and fail-closed
  revocation semantics. None of this exists yet; it belongs in the runner ADR
  together with enrollment.
- T-T2 Workspace policy tampering: policy objects must be admin-writable only,
  versioned, and audited (existing metadata-only audit pattern in
  `backend/app/service.py`).
- T-T3 Derived-data reclassification: prompt-injected or tool-produced output
  must never upgrade classification of stored data (existing rule: documents are
  untrusted content, never policy — `docs/security/THREAT_MODEL.md`).
- T-T4 Audit log tampering: the product audit table (`backend/app/service.py`)
  is transactional metadata only — no tamper evidence, no detection of
  alteration, deletion, rollback or unauthorized reading, and no confidentiality
  control. The Loop worker's spool/bundle design (`loop_engine/audit_spool.py`)
  does NOT cover the product log. Required (open, 【要決定】 where noted): access
  boundaries on audit data, tamper/rollback detection, retention and secure
  erasure, and confidentiality 【要決定】. The agent-runtime audit machinery must
  keep its append-only properties and key separation (ADR-0010 scope: the
  encrypted audit authentication cache only).

### Repudiation
- T-R1 Unattributable model invocation: every agent invocation must record
  who/which workspace/which destination/model (requirement 6). The Loop engine
  already binds role/source/goal per invocation; product agents must inherit the
  same binding or stronger.
- T-R2 Silent external sends: any egress attempt without an audited, explicitly
  allowed policy match must fail closed (today's startup rejects egress entirely;
  future cloud policy needs a positive allowlist + per-send audit record).

### Information disclosure
- T-I1 Sensitive data to external AI: the hardest requirement. Defense layers:
  (a) classification gate on inputs (requirement 3, unclassifiable ⇒ deny),
  (b) technical egress denial for local-only workspaces (`ALLOW_CLOUD_EGRESS`
  startup hold + deployment firewall), (c) provider-side agreements verified per
  provider. RAG results/citations inherit the source ACLs today; classification
  inheritance must be added before any cloud path exists.
- T-I2 Cross-workspace leakage via derived data: existing per-project ACL checks
  and private history isolation carry over; graph/plot paths (Phase 5) must apply
  the same live checks (already recorded as open in the reconciliation doc).
- T-I3 Credentials on user devices: requirement 5 says provider credentials live
  on the user's device; threat is local malware exfiltration. Mitigation: OS
  keystore storage (ADR-0010 pattern), no Locus-side copy, and no telemetry of
  credential material; explicitly no repurposing into Locus API auth.
- T-I4 Prompt leakage through model prompts: retrieval permission checks before
  context assembly exist (`backend/app/service.py` `send`); agent tool inputs
  must pass the same workspace policy filter.

### Denial of service
- T-D1 Runaway agent jobs: bounded queues, deadlines, single-slot serialization
  exist for the chat model (`backend/app/service.py` chat_jobs, `backend/app/local_model.py`);
  agent runtimes need equivalent per-workspace/per-user admission, deadlines and
  cancellation before activation.
- T-D2 Ingestion/scan storms: bounded backlog exists; reuse.

### Elevation of privilege
- T-E1 Tool escape from agent runtimes: the zero-tool boundary
  (ADR-0011 / `loop_engine/toolless_boundary.py`) applies to model-facing
  requests; agent runtimes that legitimately execute files/commands must be a
  separate, OS-isolated module (explicitly stated in the requirements doc) with
  their own approval gates — never a loosening of the current gate.
- T-E2 Delegated-admin escalation: subset-and-ceiling rules exist for roles
  (`NON_ADMIN`, `create_role`/`update_role` ceilings); workspace policies must
  respect the same "cannot invent privileges" rule.
- T-E3 Container/file-mount escape: `loop_engine/docker_boundary.py` plus
  opt-in live tests are the starting point; production runners require verified
  OS enforcement (the ADR-0006 note that the Windows sandbox diagnostic proved
  incomplete remains binding).
- T-E4 Desktop Runner host-boundary risks (specific to running on a user's PC):
  access outside the selected workspace directory, exposure of the user's
  device-held provider credentials (requirement 5), network reach to other
  intranet hosts from a compromised runner, and confusion between user-session
  and runner processes. Required controls (design stage): OS-enforced
  filesystem scope per workspace, process identity separation, credential
  confinement to the OS keystore with no Locus-side copy, and an explicit
  egress allowlist per workspace. The development-loop Docker boundary is NOT
  evidence for Desktop Runner isolation.

## 3. Gap list mapped to phases

Existing phases (ROADMAP). Items marked 【要決定】require an owner decision and
must not be auto-resolved by implementation agents.

- Phase 1/2 (auth/admin): recovery flow and web account administration are in
  flight (see `docs/plans/agent-work/PH1-A/B/D`); 【要決定】recovery ceremony
  scope, 【要決定】MFA, 【要決定】delegation expiry/revocation semantics.
- Hybrid prerequisite (this doc's follow-up): workspace/policy data model,
  runner enrollment and registry — new work package between Phase 2 and 3,
  gated on this threat model's review. 【要決定】runner trust root.
- Phase 3 (ingestion/retrieval): classification levels and propagation into
  index/citation/answer paths; storage-destination credentials remain 【要決定】.
- Phase 4 (UI/multi-user): execution-destination and provider settings UI per
  requirement 8; fairness/cancellation work continues from the dialogue queue
  slice; 【要決定】cloud policy/router activation criteria.
- Phase 5 (extensions): GraphRAG/plots keep ACL-first design; agent adapter
  phases (hybrid 実装順 2–6) are effectively a new track and must not reuse the
  product model slot without the resource-control design in T-D1.
- Agent Runtime isolation (hybrid 実装順 3): OS/container enforcement with live
  verification is a hard gate before any product runner activation. 【要決定】
  approved isolation technology per platform.

## 4. Consistency findings with existing governance

1. **Zero-tool boundary vs. Desktop Runner executing official CLIs.** The
   requirements doc states ADR-0011's boundary stays and tool-executing Agent
   Runtimes are a separate audited module. These are consistent only if the
   Agent Adapter strictly separates (a) model-facing requests (zero tool
   declarations, `loop_engine/toolless_boundary.py`) from (b) runner-side CLI
   execution (OS-enforced). Recommendation: one ADR covering the dual-plane
   boundary before implementation of hybrid 実装順 2.
2. **Local-only mode vs. authenticated runner connections.** Today's product
   rejects any egress at startup; runner↔Control-Plane traffic (requirement 7)
   is intranet loopback/LAN traffic, not cloud egress — but the policy text must
   say so explicitly to avoid future ambiguity between "network" and "external
   send". Recommendation: extend `docs/security/THREAT_MODEL.md` wording when
   runner networking is designed; decision 【要決定】.
3. **Approval-then-activation discipline.** Existing governance activates
   nothing on document approval alone (ADR-0006/0009/0011 pattern, `docs/plans/
   MODEL_BOUNDARY_FINAL_DESIGN.md` verification gates). The hybrid doc's 完了
   conditions should therefore require the same receipt/verification gates per
   step; recommend adding an explicit activation-gate clause.
4. **One model slot vs. agent concurrency.** The single-model serialization
   protects local model capacity only; it does not govern Desktop Runner work,
   which has no shared lock. Admission design must therefore treat workspace/
   user limits and provider/destination limits separately from the model slot
   (extension of `backend/app/service.py` chat_jobs for the local model path,
   plus new admission rules for runner execution) before multi-workspace agent
   execution.
5. **Synthetic-data-only prototype vs. workspace concept.** Hybrid workspaces
   imply real research data handling; the standing risk register forbids real
   data until production data-handling design is approved. Recommendation:
   workspace foundations land on synthetic data like everything else; 【要決定】
   for real-data activation remains with the owner.

## 5. Immediate follow-ups (proposed, none approved by this document)

1. Owner review of this threat model; resolve the 【要決定】 markers or park them.
2. Draft ADR: hybrid dual-plane boundary (model gate vs. agent runtime) — feeds
   hybrid 実装順 2.
3. Draft ADR: runner enrollment, credential rotation/revocation, and job
   identity/freshness/workspace-binding/revocation contract (T-S1/T-T1) —
   precedent value of ADR-0009/0010 is limited to the audit-worker scope.
4. Design item: product audit-log protection (tamper evidence, access
   boundaries, retention, confidentiality) — separate from ADR-0010's
   authentication-cache scope (T-T4).
5. Phase 1 auth jobs continue per `docs/plans/agent-work/ORCHESTRATOR_LOG.md`.

## Review history

- 2026-11-07: independent read-only review (slot E, Luna) verdict "accept after
  minor fixes" — 1 high + 4 medium findings, all applied in this revision
  (runtime-readiness vs. offline-implementation distinction, ADR-0010 scope
  correction, product audit-store threats, runner enrollment precedent narrowed
  with job-binding contract, Desktop Runner host-boundary threats, single-slot
  scope clarification, follow-up list extended).
