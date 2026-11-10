# P2-TRUST — Runner trust foundation design (instance ID, enrollment, keystore, TLS/rotation)

Agent: append your progress under "## Progress" below every time you complete a step.
Work ONLY in your own worktree/branch. Docs-only task: do NOT modify code.
Never push to `main` or `loop/local-development`; no subagents.

## Task

Author the Runner trust, enrollment, and key-management design document per the
owner-approved Entry 5 (`docs/plans/OWNER_DECISIONS_2026-11-10-ENTRIES.md`).

**Approved design (Entry 5):**
- OS keystore-protected per-instance Runner identity
- Vetted standard TLS
- Authenticated administrator one-time challenge enrollment
- Strict binding of Runner instance to enrolled ID
- Revocable Runner ID
- Measured/verified key rotation
- Revoke-then-re-enroll on key loss/compromise
- Audit of enrollment/update/revocation/recovery operations
- NOT required initially: custom CA, dedicated hardware auth, multi-admin quorum

**Verification conditions (owner-required):**
1. Verify OS keystore availability and protection characteristics per platform
2. Demonstrate key/credential protection
3. Map Runner enrollment/revocation authority to existing RBAC
4. Verify no privilege escalation during key update/revocation/recovery
5. Define compromise-response procedures (job stop, result hold, re-enrollment)
6. Confirm cipher, key lifetime, rotation period from standard methods + measurements
7. Complete independent review

**Output:** Create `docs/plans/HYBRID_RUNNER_TRUST_DESIGN.md` covering:
- Per-platform (Windows/Linux) keystore comparison
- Enrollment ceremony design (one-time challenge, admin authority, RBAC binding)
- Key rotation/recovery procedures with security properties
- Compromise-response runbook
- Audit event taxonomy for trust operations
- 【要決定】 markers only for genuinely new choices (e.g. cipher suite details)

**Safety boundaries:** ADR-0011/0012, B6, no-egress, fail-closed; design-only (no key
generation, no enrollment execution, no Runner activation).

**Process:** Read AGENTS.md + DEVELOPMENT_POLICY.md + owner Entry 5 + HYBRID_ISOLATION_PROFILES.md +
HYBRID_ISOLATION_ENGINEERING_DETAIL.md. Conventional Commit (`docs(plans): ...`);
push origin loop/p2-trust-design; repeat until checks pass.
Conventional Commit subject: `docs(plans): author the runner trust and key-management design`

## Progress
- 2026-11-11: Read AGENTS.md, DEVELOPMENT_POLICY.md, PRODUCT_SPEC.md, ARCHITECTURE.md, owner Entry 1–6 (Entry 5 authority), Q1–Q7, OWNER_QUEUE_CLASSIFICATION Entry 5 cluster (DP-035–041, DP-043b), ADR-0012 (B1–B7, esp. B5/B6), ADR-0011, step-2 registry design (E2/E4/E5), step-3 trust proposals §3–5, HYBRID_ISOLATION_PROFILES.md, HYBRID_ISOLATION_ENGINEERING_DETAIL.md, hybrid threat model (T-S1/T-T1/T-I3), and `backend/app/service.py` role/RBAC structure (`system_admin` flag, ROLE_PERMISSIONS). `.bootstrap/complete.json` present; no bootstrap needed.
- 2026-11-11: Authored `docs/plans/HYBRID_RUNNER_TRUST_DESIGN.md` (522 lines) covering the owner-approved Entry 5 design: per-platform Windows/Linux keystore comparison (Windows CNG/NCrypt non-exportable vs Linux file-based under a dedicated service account, DPAPI/kernel-keyring/secret-service rejected with reasons, per-platform residual-risk statements); enrollment ceremony (authenticated-admin one-time challenge, two-surface fingerprint confirmation, fail-closed rejection inventory); trust anchor without a custom CA product (single Control-Plane issuer, vetted standard TLS, mTLS rules conditional on Entry 3); RBAC mapping of enrollment/revocation authority to the existing `system_admin` authority with no new permission (Entry 2 precedent); privilege-escalation analysis for key operations; measured rotation procedure with proof-of-possession cutover and bounded overlap; revoke-then-re-enroll under the same instance ID with generation counters and full lineage; issuer/anchor-compromise recovery (DP-043b) with DP-043a held-output semantics; compromise-response runbook (detect/contain/assess/recover/close with job stop and result hold); audit event taxonomy for trust operations (B7); owner 7-condition verification mapping (§11); parameter register with all numeric/cipher values as 【要決定】 set only by vetted standards + measurement (§12, no values invented); adversarial self-review (§14). Docs-only: no key generated, no enrollment executed, no network path, no Runner activation; B6 unchanged.
- 2026-11-11: QA in isolated `.loop/runtime/qa-venv` (Python 3.13, Ruff 0.17.3), shared `.venv` untouched: `ruff check backend tests scripts` PASS; `ruff format --check backend tests scripts` PASS (128 files, the CI-scoped surface per `scripts/verify.py`); offline `scripts/secret_scan.py` PASS (0 findings). Note: a repo-wide `ruff format --check .` also flags `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315` (markdown code block), which is pre-existing on `origin/loop/local-development` (verified on base commit `62e1d8c`), outside the CI check surface, and not touched by this task.
- 2026-11-11: Commit `a6adfda` (`docs(plans): author the runner trust and key-management design`) pushed to `origin loop/p2-trust-design` (branch created at this push, first commit on it). CI evidence to be recorded when runs complete. Coordination: peer notifications received from slots P1 (receipt implementation), P3 (communication design), P4 (adapter research) — each owns a distinct deliverable file (`HYBRID_STEP2_RECEIPT_CONTRACT.md` §7, `HYBRID_RUNNER_COMMUNICATION_DESIGN.md`, `HYBRID_AGENT_ADAPTER_DESIGN.md`) in its own worktree; no file overlap with this task. Independent review (owner condition 7) was NOT performed: task instructions prohibit subagent delegation; it remains a pre-implementation/pre-activation gate, as recorded in §11 and §14 of the design document.
