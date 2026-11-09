# R-ISO-2 — Isolation engineering details classified ENGINEERING_DETAIL

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Docs-only task:
do NOT modify code, specs, tests, or the OWNER_DECISION_QUEUE. Never push to
`main` or `loop/local-development`; no subagents of your own. NEVER touch the shared
`.venv`; use `.loop/runtime/qa-venv` if needed.

## Task

Produce comparison, test-inventory, evidence-binding, and profile-conformance details
ONLY for isolation items explicitly classified as `ENGINEERING_DETAIL` in
`docs/plans/OWNER_QUEUE_CLASSIFICATION_2026-11-09.md`. The owner's formal decisions
Q1–Q7 are recorded in `docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md`.

**Scope:**
- Work only the isolation details classified `ENGINEERING_DETAIL` that do NOT depend on
  an unresolved owner choice.
- Do NOT decide unresolved trust/enrollment/key custody, support authorization, provider
  credential supply, endpoint/egress, or risk acceptance for an unverified profile.
- Do NOT decide numerical bounds for any item classified OWNER_DECISION_REQUIRED.
- Produce comparison tables, test-inventory criteria, evidence-binding contracts, and
  profile-conformance checklists for the engineering-detail items only.
- Explicitly mark any emerging policy/scope choice as 【要決定】 and split it out.

**Owner decision relied on:** Q3's approved per-environment verified-profile direction;
Q4's official CLI preference (describes adapter constraints only, does NOT authorize
provider authentication or credentials).

**Safety boundary that must not change:** independent proof for the exact environment;
unverified profiles unavailable; no host fallback; no dispatch before the receipt and
ADR-0012 gates; no egress or credentials.

**Output:** Create `docs/plans/HYBRID_ISOLATION_ENGINEERING_DETAIL.md` (the design
package). This is documentation/design only, not product code.

**Completion gate:** reviewed comparison/test criteria are reproducible, evidence-bound
to the claimed environment, and do not claim profile activation. Any unresolved
authority, trust or policy item remains explicitly gated.

## Process

Read AGENTS.md + docs/governance/DEVELOPMENT_POLICY.md, then the owner decisions
(docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md), then the classification record
(docs/plans/OWNER_QUEUE_CLASSIFICATION_2026-11-09.md) to identify exactly which
isolation rows are ENGINEERING_DETAIL, then the isolation profile design
(docs/plans/HYBRID_ISOLATION_PROFILES.md) and the trust proposals
(docs/plans/HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md). Self-review adversarially;
run the docs-applicable verification subset (ruff check + ruff format --check +
scripts/secret_scan.py via the qa-venv if needed). Conventional Commit
(`docs(plans): ...`); push origin loop/riso2-isolation-engineering; repeat the fix
cycle until all applicable checks pass. Append progress + SHA + CI evidence to this
file under ## Progress at each step end and at task end, and push.

Conventional Commit subject suggestion: `docs(plans): author isolation engineering detail design`

## Progress

- **Source review and scope classification complete (2026-11-10 JST).** Read the required governance, Q1–Q7 owner decisions, isolation profile and trust proposals, and relevant ADR-0012/step-2/receipt/threat-model sources. The only isolation rows in scope are DP-033, DP-042, DP-044–049, DP-051, DP-052 and DP-053a, all classified `ENGINEERING_DETAIL`. DP-031/032, DP-034b, DP-035–041 and DP-043b remain owner-gated; DP-024–030 and DP-053b are resolved/existing constraints, not reopened. Loop status/decisions commands returned `ValueError` (“Loop command blocked”); this does not authorize bypass or alter the docs-only task. **SHA:** `f252d0d76ef7eafd15219a0a89aa65c5e96cdd16` (starting HEAD). **CI evidence:** not yet run / none for this SHA.
- **Design package authored (2026-11-10 JST).** Created `docs/plans/HYBRID_ISOLATION_ENGINEERING_DETAIL.md` with row-bounded comparison tables, test-inventory criteria, evidence-binding contract, per-profile conformance lists and explicit owner gates. Adversarial self-review is in §7; no independent review or profile activation is claimed. **SHA:** `f252d0d76ef7eafd15219a0a89aa65c5e96cdd16` (changes currently uncommitted). **CI evidence:** not yet run.
- **Local QA complete (2026-11-10 JST).** Created isolated `.loop/runtime/qa-venv` (shared `.venv` untouched) and ran Ruff 0.17.3 `ruff check` (**PASS**), repo-wide `ruff format --check` (**FAIL outside task scope**: existing `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315` would be reformatted), targeted `ruff format --check` on both changed Markdown files (**PASS**), `scripts/secret_scan.py` (**PASS**, 0 findings), and `git diff --check` (**PASS**). Did not alter the unrelated existing document. **SHA:** `f252d0d76ef7eafd15219a0a89aa65c5e96cdd16` (pre-commit source). **CI evidence:** no CI run yet.
- **Task implementation committed (2026-11-10 JST).** `docs(plans): author isolation engineering detail design` committed as `7e0e7181aa7940473c607affb658bdf88d421111`. Re-ran post-commit `ruff check` (**PASS**), targeted changed-file `ruff format --check` (**PASS**, 2 files), `scripts/secret_scan.py` (**PASS**, 0 findings), `git diff --check` (**PASS**). Repository-wide format check still has the unrelated baseline failure noted above; no fix was made outside the allowed scope. **CI evidence:** GitHub CI runs for progress commit `b10f3bf1c2f7928e0d9e19de8fe51f6b940e028d`: PR title convention **success** [run 42654732057](https://github.com/kanalia7355/Locus/actions/runs/42654732057); Prototype quality **success** [run 42654732058](https://github.com/kanalia7355/Locus/actions/runs/42654732058); Loop engine checks **success** across Ubuntu 3.11/3.13 and Windows 3.11/3.13 [run 42654732181](https://github.com/kanalia7355/Locus/actions/runs/42654732181). A later CI rerun for progress SHA `cad000d14d878f43cff8fbe5979aae1a2cabddd5` reported PR title **success** [42656138493], Loop engine checks **success** [42656138555], but Prototype quality **failure** [42656138686]: the `tests-quality-remaining` pytest group exceeded its configured 120-second deadline (124), despite 53 passed/18 skipped in its displayed suite output; no failing assertion from the documented changes was reported. No code/tests/CI settings were changed. The progress-only follow-up for SHA `beae870f499f9e4df832cb9b428195f55b8b5ab7` then passed: PR title [42657767925], Prototype quality [42657767514], and Loop engine checks [42657767369], including Ubuntu 3.11/3.13 and Windows 3.11/3.13. No profile execution or independent profile review performed/claimed.
- **Task-end record (2026-11-10 JST).** The design deliverable is committed at `7e0e7181aa7940473c607affb658bdf88d421111`; the latest full-check/CI-green source state before this final log update is `beae870f499f9e4df832cb9b428195f55b8b5ab7`, pushed to `origin/loop/riso2-isolation-engineering`. Local changed-file Ruff format, Ruff check, secret scan (0 findings) and diff check pass. Repo-wide Ruff format check retains the unrelated pre-existing formatting discrepancy at `docs/requirements/AUTONOMOUS_LOOP_SPEC.md:315`; it was left untouched. CI is green for the source state above; final evidence commit will get its own CI run. Profiles remain inactive/unverified; no dispatch, credentials, egress or real data. **CI evidence:** runs 42657767925, 42657767514, 42657767369 (all success; links above).
