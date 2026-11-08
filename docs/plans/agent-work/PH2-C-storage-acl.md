# PH2-C — 元保存先ACL対応: research and design note (docs only)

Agent: append your progress under "## Progress" below every time you complete a
step. Research/documentation task: NO application code changes.

## Task brief

Phase-2 job per `docs/plans/PHASE2_JOB_BREAKDOWN.md` (PH2-C, delta D5). The
reconciliation doc lists 元保存先ACL対応 as 未確定または未実装, but the phrase's
precise meaning must be pinned down from the original design before anything can
be planned. This job researches and proposes; it decides nothing.

Setup: create worktree `git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/PH2-C-storage-acl -b loop/PH2-C-storage-acl origin/loop/local-development` (reuse if it exists). Work ONLY inside it. Use `C:/Users/hirot/Locus/.loop/runtime/qa-venv/Scripts/python.exe` for any verification; the shared `.venv` is broken — do NOT use or modify it.

Investigate (read the real code and docs, cite file paths):
1. What "保存先" (storage destinations) means in the original design: search
   `docs/requirements/PRODUCT_SPEC.md`, `docs/architecture/ARCHITECTURE.md`,
   `docs/planning/ui-and-multiuser-design.md`, `docs/planning/research-app-concept.md`
   (and git history for early requirement docs mentioning 保存先/ストレージ/接続先)
   for the original storage-destination concept (approved DB/storage connectors,
   folder ingestion, etc.).
2. What exists today: local bounded ingestion, quarantine, the scanner path
   (`docs/INGESTION_SCANNER.md`, `backend/app/scanner.py`), storage-related
   admin screens (P4B's in-flight draft is NOT integrated — describe from the
   integrated HEAD only), and how document ACLs currently attach (project/
   publication grants/conversation-bound attachments).
3. Enumerate the plausible interpretations of 元保存先ACL対応 with evidence:
   e.g. (a) ACL semantics for the ORIGINAL file/source location from which a
   document was ingested (does deleting/revoking at the source propagate?),
   (b) ACL configuration of future external storage connectors, (c) retention
   of the original bytes vs derived chunks. For each interpretation: what the
   design says, what exists, what would be needed, and the security
   implications (external egress stays owner-gated).
4. Deliverable `docs/plans/PHASE2_STORAGE_ACL_RESEARCH.md`: findings, the
   recommended interpretation(s), an outline design for the recommended one
   (data model sketch, enforcement points, audit), open 【要決定】 items (do NOT
   decide), and what belongs in which phase/step.
5. Record any contradictions with existing approved documents as findings.

Self-review for evidence quality (no speculation beyond what documents/code
show). Conventional Commit (`docs(plans): research the storage-destination ACL requirements`).
Push `loop/PH2-C-storage-acl`; wait branch CI; fix/re-push until ALL green
(bounded). APPEND progress + SHA + CI evidence to this file's ## Progress.

Boundaries: never push to `main` or `loop/local-development`; no code changes;
no subagents.
