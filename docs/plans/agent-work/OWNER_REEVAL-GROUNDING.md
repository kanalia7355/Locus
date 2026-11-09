# Owner re-evaluation grounding — DP-001…072 vs the initial Locus design

This file is the SHARED grounding pack for the owner's 2026-11-09 directive
「Locus初期設計との整合性を優先したOwner判断方針」. Every re-evaluation slot must read
this file first and follow it exactly.

## The owner's directive (verbatim digest)

Do NOT decide the 72 queue items piecemeal. Re-evaluate them with ONE priority:
**consistency with the initial Locus design**. Ground every evaluation in the initial
requirements, approved ADRs, the master roadmap and the requirements traceability
matrix, and confirm each decision serves the ORIGINAL vision.

Seven priorities (highest authority in this re-evaluation):
1. Do not impair the research-support-AI functionality.
2. Realize the local/server hybrid operation.
3. Reconcile administrator control with personal-workspace flexibility.
4. Agents may act autonomously WITHIN the pre-approved scope.
5. Unnecessary owner confirmations must not stop autonomous development.
6. Preserve the existing safety boundaries of ADR-0011 and ADR-0012.
7. Do not add constraints or complexity that the initial design does not contain,
   without grounding.

## Hard guardrails (apply to every recommendation)

- **Design recommendations ≠ execution permission.** Nothing here activates an
  unapproved safety boundary: dispatch (B6) stays disabled, no egress activation,
  no Runner/isolation activation, no credential schemes, no production exposure.
  Every proposal that touches a ⚠ SAFETY BOUNDARY row must state this explicitly.
- Do NOT re-open already-approved owner decisions (OWNER_DECISION_REGISTER RESOLVED
  items, the delegation-spec §8 binding conditions, phase completion declarations).
- Do NOT weaken ADR-0011 (model-facing zero-tool gate) or ADR-0012 (dual-plane
  model gate / agent runtime) or any existing test/spec.
- For technical details absent from the initial design: compare the realistic
  implementation options and recommend the MINIMAL configuration that satisfies the
  ORIGINAL functional requirement (anti-over-engineering rule).
- Keep every item's 【要決定】 status intact in the OWNER_DECISION_QUEUE — this
  re-evaluation produces a recommendation layer; only the owner records decisions.

## Per-item evaluation format (mandatory, all 7 fields)

For EACH assigned DP item:
1. **初期設計要件IDと原典** — the requirement ID(s) (REQUIREMENT_ID_SCHEME /
   REQUIREMENTS_TRACEABILITY_MATRIX) and the exact source (PRODUCT_SPEC §, ARCHITECTURE
   §, ADR §, roadmap row). If NO initial-design requirement covers the item, say so
   explicitly — that is itself a finding (rootless constraint candidate).
2. **当初想定されていた動作** — what the initial design assumed.
3. **現在提示されている選択肢** — the options in the queue/source doc (do not invent new
   option framings; you may note an option set is incomplete).
4. **初期設計に最も整合する推奨案** — the recommendation, or "初期設計では未規定 →
   最小構成推奨" with the minimal configuration spelled out.
5. **自律性・利便性・安全性への影響** — impact on autonomy (owner priority 4/5),
   usability (1/3), safety (6).
6. **推奨案を採用した場合の制約** — what the choice constrains later.
7. **Ownerが新たに決定する必要がある事項** — what genuinely remains owner-decidable
   after the initial-design grounding (should shrink for most items).

Plus a FLAG line per item when applicable:
- `🚫初期設計反` — an offered option (or the framing itself) contradicts the initial design.
- `⚠根拠不足制約` — a proposed constraint lacks grounding in the initial design.
- `📈過剰設計疑` — complexity beyond what the original functional requirement needs.

## Special verifications (owner's list, mapped to groups)

- Does the job-approval mechanism unnecessarily obstruct autonomous execution?
  → Group A (receipt) primary; all groups consider it.
- Is the Runner isolation practical on BOTH local and server?
  → Group B (isolation/trust) primary.
- Can the Agent Adapter use existing AI agents as-is?
  → Group A and B (adapter/receipt interaction), grounding in
  HYBRID_STEP2_AGENT_REGISTRY_DESIGN and ADR-0012.
- Are admin approval and personal-workspace permissions properly separated?
  → All groups; grounding in PRODUCT_SPEC roles model + PH2 delegation decisions.
- Does the storage ACL unnecessarily restrict research-material search/citation/analysis?
  → Group C (storage-ACL) primary; grounding in PRODUCT_SPEC research flows.
- Extensibility for future features → all groups.

## Source inventory (read before evaluating)

- docs/requirements/PRODUCT_SPEC.md (the product's initial requirements)
- docs/architecture/ARCHITECTURE.md; ADR-0011, ADR-0012 (docs/architecture/);
  ADR-0006 (source-only runtime) as background
- docs/plans/REQUIREMENTS_TRACEABILITY_MATRIX.md + REQUIREMENT_ID_SCHEME.md
- docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md; PHASE_SPEC_RECONCILIATION.md
- docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md (step-2 design, review-cleared)
- docs/plans/OWNER_DECISION_QUEUE_2026-11-09.md (the 72 items — the object under evaluation)
- The three decision source docs (ADR-0013; HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS;
  PHASE2_STORAGE_ACL_IMPLEMENTATION_PLAN) — but their INTERNAL recommendations are
  NOT privileged over the initial design; where they conflict with the initial design,
  the initial design wins and the conflict is flagged.
- docs/plans/OWNER_DECISION_REGISTER.md (RESOLVED items — do not re-open)

## Output convention

Each slot writes its own file docs/plans/OWNER_REEVAL-<GROUP>.md with one numbered
entry per DP item (all 7 fields + flag). The consolidation slot later merges the
three files into docs/plans/OWNER_DECISION_PROPOSAL_2026-11-09.md and runs the
coherence check. Keep entries compact (target ≤ 12 lines per item; prefer tables for
options).
