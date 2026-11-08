# AUD-1F — Design/record consistency fixes (owner decision B-1/B-4, docs only)

Agent: append your progress under "## Progress" below every time you complete a
step. Documentation task: NO application code changes.

## Task brief

The owner resolved AUD-1's findings 1 and 4 (see
`docs/plans/OWNER_DECISION_REGISTER.md`, RESOLVED 2026-11-09 section). Apply:

1. **B-1 Phase-number normalization (into the master roadmap)**: update
   `docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md` so the three numbering systems
   — the product ROADMAP phases 0-5, PRODUCT_SPEC MVP slices 1-6, and the
   autonomous Loop spec phases 1-6 — are explicitly cross-walked as NAMESPACED
   ALIASES (e.g. `PH-ROADMAP-2`, `MVP-2`, `LOOP-PHASE-2`), with: which family
   each existing completed phase belongs to, the dependency relationships
   between the families, and the rule that completion in one family never
   implies completion in another. Preserve all existing phase numbers, commit
   history and approval records as evidence — nothing is renumbered or
   deleted. Reference `docs/plans/DESIGN_GAP_ANALYSIS.md` finding 1.
2. **B-4 ADR-0012 wording correction (meaning-preserving)**: fix the internal
   contradiction flagged by AUD-1 — the ADR's §Decision heading/body still says
   "proposed; pending owner approval" while the Status header (correctly) says
   ACCEPTED by owner 2026-11-07. Rewrite ONLY the stale §Decision intro wording
   to match the accepted status (e.g. "Decision — adopted by owner approval on
   2026-11-07; this record approves no runtime activation"). Do NOT widen the
   approval, do not touch any other sentence's meaning; if you find wording
   that would need a semantic change, STOP and record it as a finding instead.
3. Record both fixes in the AUD-1 findings list of `DESIGN_GAP_ANALYSIS.md`
   (finding 1 and 4 → resolved by owner decision, pointer to the register) —
   mark them resolved, do not delete the original findings text.
4. Also verify `docs/plans/STATUS_AND_DECISIONS_2026-11-09.md` §2.3 matches the
   new state (e.g. the "MFA final decision" item is now RESOLVED as
   required-for-final-product per B-3) and update it.

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/AUD-1F-consistency -b loop/AUD-1F-consistency origin/loop/local-development` (reuse if it exists). Work ONLY inside it.

Self-review: no meaning changes beyond the approved wording fix; all cross
references updated consistently. Conventional Commit
(`docs(plans): normalize phase numbering aliases and correct the ADR-0012 wording per owner decision`).
Push `loop/AUD-1F-consistency`; wait branch CI; fix/re-push until ALL green
(bounded). Append progress + SHA + CI evidence to this file's ## Progress.

Boundaries: never push to `main` or `loop/local-development`; docs only; no
subagents.
