# Slot AA — Fix Cycle: Trust + Adapter Design Review Findings

Model: GPT-6-Luna (thinking high) | Branch: loop/fix-review-findings1 | Reviewer report: docs/plans/agent-work/REVIEW-HYBRID-DESIGNS.md (integrated)

## Objective
Correct the HIGH findings from the independent review of HYBRID_RUNNER_TRUST_DESIGN.md and HYBRID_AGENT_ADAPTER_DESIGN.md. Docs-only. Do not weaken any safety boundary; do not resolve anything the owner has not decided; keep all activation gates intact.

## Findings to fix
TRUST (HYBRID_RUNNER_TRUST_DESIGN.md):
- HIGH TRUST-01: the Linux private-key-file proposal does not satisfy the owner-approved OS-keystore design nor the stated access-denial test (same-UID processes can read a permissions-restricted file). Replace with an actual supported OS-keystore/key-operation design meeting the process boundary, OR mark Linux enrollment unavailable until a separately identified mechanism passes exact-build positive/negative tests. Never call a permissions-restricted private-key file an OS-keystore substitute.
- TRUST-02: §12 overuses 【要決定】 for measurement/standard-based engineering parameters — reclassify as engineering decisions derivable from standards+measurements, keeping genuinely new policy choices as 【要決定】.
ADAPTER (HYBRID_AGENT_ADAPTER_DESIGN.md):
- HIGH ADAPTER-01: lines ~143-149 describe an actual provider login as an operator action despite Entry 4's prohibition — reword so no sentence is readable as granting credential/activation authority; real login stays behind separate owner approval.
- HIGH ADAPTER-02: BR-3 cannot enforce denial by OS identity when CLI and tool process share that identity — replace or redesign the enforcement mechanism, or mark the claim unverified/unavailable.
- ADAPTER-03: the verification plan's stub-based fixtures cannot substantiate vendor-CLI claims (VT-1/VT-4); separate harness/contract tests (stubs OK) from platform/adapter tests; define how pinned official CLI + actual OS boundary would be assessed AFTER the required separate authorization in an isolated synthetic environment; until then mark adapter credential-boundary claims unverified and the adapter unavailable.

## Rules
- Cross-check consistency with HYBRID_RUNNER_COMMUNICATION_DESIGN.md (passed review) — the trust fix must restore the OS-keystore-backed identity the comm design assumes.
- Preserve B6/E1/E2, ADR-0011/0012, no-egress, no-credential-bytes, all 【要決定】 items not decided by Entries 1-6.
- QA: ruff check + ruff format --check + scripts/secret_scan.py via C:/Users/hirot/Locus/.loop/runtime/qa-venv/Scripts/python.exe (absolute path; NEVER shared .venv). Conventional Commits (docs(plans)); push origin loop/fix-review-findings1 until checks green. Never push main or loop/local-development. Never spawn subagents. Never bypass hooks. Append progress under ## Progress.
