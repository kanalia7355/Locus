# P3-COMM — Runner communication topology and isolation profile design

Agent: append your progress under "## Progress" below every time you complete a step.
Work ONLY in your own worktree/branch. Docs-only task: do NOT modify code.
Never push to `main` or `loop/local-development`; no subagents.

## Task

Author the Runner communication topology and isolation profile design per the
owner-approved Entry 3 (`docs/plans/OWNER_DECISIONS_2026-11-10-ENTRIES.md`).

**Approved direction (Entry 3):**
- Authenticated LAN-internal channel as the base communication method
- Authentication, authorization, and encryption required for Runner↔Control-Plane communication
- Explicitly enumerate: endpoints, ports, protocols, communication direction, network boundary
- Each endpoint requires: design → verification → independent review → separate Owner approval
- Communication to non-approved destinations: DENY
- Implicit allowance of internet/cloud/unapproved-LAN/provider-API: PROHIBITED
- Fail-closed if communication path cannot be verified
- **SCOPE:** This is DESIGN APPROVAL of the LAN communication method — NOT firewall change, port opening, or Runner communication activation approval
- Future remote Runner / external network operations: do NOT remove from final requirements; design separate network boundary and safety conditions later

**Output:** Create `docs/plans/HYBRID_RUNNER_COMMUNICATION_DESIGN.md` covering:
- LAN-internal communication topology (authenticated channel design)
- Endpoint approval table (per-endpoint: purpose, port, protocol, direction, verification plan)
- Windows/Linux isolation profile comparison update (incorporating communication boundaries)
- Network, file, and process isolation verification plans
- Activation evidence inventory (what proof is needed before Runner communication activation)
- 【要決定】 markers only for genuinely new choices

**Safety boundaries:** ADR-0011/0012, B6, no-egress, fail-closed, default-deny; design-only
(no firewall change, no port opening, no Runner communication execution, no profile activation).

**Process:** Read AGENTS.md + DEVELOPMENT_POLICY.md + owner Entry 3 + HYBRID_ISOLATION_PROFILES.md +
HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md. Conventional Commit (`docs(plans): ...`);
push origin loop/p3-comm-design; repeat until checks pass.
Conventional Commit subject: `docs(plans): author the runner communication topology and isolation design`
