# P3-COMM — Runner communication topology and isolation profile design

Agent: append your progress under "## Progress" below every time you complete a step.
Work ONLY in your own worktree/branch. Docs-only task: do NOT modify code.
Never push to `main` or `loop/local-development`; no subagents.

## Progress

- Read the repository instructions, development policy, owner Entry 1–6, this task brief, ADR-0011/0012, the isolation-profile comparison, the step-3 isolation/trust proposal, and the product/architecture context. Confirmed this is documentation-only and the worktree is clean on `loop/p3-comm-design`; bootstrap marker is present.
- Checked current loop status/decisions; the CLI returned `ValueError` diagnostics. No loop launch or product execution was attempted. The requested `.loop/runtime/qa-venv` is absent at initial inspection; verification will use only that dedicated environment if it exists/becomes available and will not use shared `.venv`.
- Authored `docs/plans/HYBRID_RUNNER_COMMUNICATION_DESIGN.md`. It marks all endpoints inactive, proposes Runner-initiated HTTPS/TCP destination port 443 to an exact CP listener (exact target pending; port is subject to verification, independent review, and separate approval), gates conditional DNS separately, isolates job network access, and specifies endpoint-specific verification/review/Owner gates, profile comparison, network/file/process plans, and activation evidence. No network/profile/firewall action was taken.
- Adversarial self-review checked that Entry 3 design approval is not confused with port/firewall/activation approval; bootstrap authentication is fail-closed; TCP source ports/replies and candidate destination ports are distinguished; CP/DNS are exact separately gated endpoint classes; no destination wildcard, implicit provider/cloud route, job-network route, fallback, or skip-as-pass claim is introduced; and remote Runner requirements remain for separate design. No independent reviewer was spawned (explicit task prohibition); independent review and separate Owner approval remain endpoint activation gates.
- QA using the task's isolated `.loop/runtime/qa-venv` (Python 3.13; Ruff 0.17.3; detect-secrets 1.5.0): `ruff check .` PASS; repository-wide `ruff format --check` FAIL on pre-existing unrelated `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315` only; targeted `ruff format --check docs/plans/HYBRID_RUNNER_COMMUNICATION_DESIGN.md docs/plans/agent-work/P3-COMM.md` PASS; `scripts/secret_scan.py` PASS (0 findings); `git diff --check` PASS; design-specific checklist PASS. The unrelated existing formatting issue was not changed.
- Delivered commit `f2d662f0a84d0849dd1f9bf6da65eb093ae8ac89` (`docs(plans): author the runner communication topology and isolation design`) pushed to `origin/loop/p3-comm-design`. CI for this SHA: PR title convention run 42731553954 PASS; Prototype quality run 42731554235 PASS; Loop engine checks run 42731554081 PASS (all four Ubuntu/Windows × Python 3.11/3.13 jobs PASS). Loop status/decisions CLI had returned `ValueError` diagnostics; no loop launch or product execution was attempted.

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
