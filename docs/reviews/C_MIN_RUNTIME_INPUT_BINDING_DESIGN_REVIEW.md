# Runtime input binding: independent design security review

2026-11-03 Asia/Tokyo. Design only; implementation and live readiness are not
certified. Scope: docs/plans/C_MIN_RUNTIME_INPUT_BINDING_DESIGN.md, relevant
existing trial/runtime/journal/relay/request/peer code, governance and prior
auth-exception/approval documents.

Fresh isolated read-only reviewer runtime_input_binding_design_audit, using
.agents/skills/security-audit/SKILL.md. Initial review: needs_decision, findings=[],
blocking=false. No fix/re-review cycle used (maximum two). Reviewer did not edit,
spawn agents, run tests, use network, read credentials, access auth stores, operate
services or run models. Separate token usage/elapsed measurement unavailable.

Reviewer assessed the closed static content, finite typed slots, exact header
contract, original full-body hash binding, atomic durable uniqueness/reservation,
fail-closed recovery and preserved normal v3/workspace gates as sound within the
explicit trusted pinned-CLI/control-plane assumption. Owner must approve the
changed advance-input guarantee and offline implementation before code changes.

Retained limits: authenticate owned sender, do not infer filesystem creator from
owner/ctime/handles; a malicious same-principal controller is not newly isolated.
Exact native template and producer contracts need offline verification before
any live permit. Both protected historical intents need reconciliation; unavailable
history is not available budget. Separate live permission must scope cumulative
allowance and official CLI arg0/auth lifecycle. Normal v3 receipt, QA, role/task/
workspace/run authorizations and explicit Loop permission remain separate.

Documentation inconsistency recorded: frozen NORMAL_AUTH_STORAGE_DECISION.md
describes the earlier keyring-only validator. Current code supports the explicitly
approved existing-file exception; EXISTING_AUTH_FILE_OFFLINE_IMPLEMENTATION.md
records that supersession. The new design follows current code and does not edit
the approved historical document.

Implementer verification: read-only SQLite mode=ro/query_only and bounded reads
of exactly two fixed nonsecret trial paths. Both protected record reads were
Access Denied; no privilege/ACL/auth/service changes or credential-file access.
The design reports that evidence as unverified. Secret scan: zero findings.
No new implementation tests are represented as run for this documentation task.
