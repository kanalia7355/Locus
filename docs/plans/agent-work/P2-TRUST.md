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
