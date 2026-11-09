# HYB-A2-isolation-trust-proposals

Agent: append your progress under "## Progress" below every time you complete a step.
Do not edit other agents' files. Work ONLY in your own worktree/branch. Use the isolated
QA venv `.loop/runtime/qa-venv` (recreate if missing: Python313 venv +
`pip install -e ".[dev]" -r backend/requirements.lock`); NEVER touch the shared
`.venv` (broken). Never push to `main` or `loop/local-development`; no subagents.

Full process: read `AGENTS.md` + governance docs first; create your worktree with
`git -C C:/Users/hirot/Locus worktree add .loop/runtime/worktrees/<SLUG> -b loop/<SLUG> origin/loop/local-development`;
implement; self-review adversarially; run the full QA cycle until ALL green
(full pytest tests -q --ignore=tests/e2e, ruff check + format --check, mypy
backend/app, secret scan; plus frontend lint/test/build/playwright when UI
touched); Conventional Commit; push; wait branch CI; fix/re-push until green
(bounded); append progress + SHA + CI evidence here. Branch deleted after
integration.

---

# HYB-A2 — Isolation technology + runner trust root proposals (docs only)

Deliverable: `docs/plans/HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md` —
owner decision items 4/5 (isolation technology; runner trust root/enrollment)
require evidence-backed proposals BEFORE hybrid implementation step 3 starts
(owner policy B-5/B-6/B-10: design comparison + verification plans are
authorized; production exposure/real data remain forbidden). Content:
(1) per-platform isolation options comparison (OS job objects/containment on
Windows, containers/namespaces on Linux, existing `loop_engine/docker_boundary.py`
and `windows_tcp_peer.py` as dev-loop precedents — what they do and do NOT
prove), with a recommended option and its verification plan (what tests would
prove the isolation claim); (2) runner trust root/enrollment/rotation/revocation
options (ADR-0009/0010 precedent is narrow per the threat model) with a
recommended design and its test plan; (3) job identity/freshness signing
contract options (threat T-T1). Everything undecidable → 【要決定】; no
activation claims; ground claims in real files (cite paths). Commit
`docs(plans): draft the isolation and runner trust-root proposals`; push branch
`loop/HYB-A2-isolation-trust`; wait branch CI until green.

## Progress

- 2026-11-09: Read the assigned brief, required governance/product/architecture/bootstrap documents, hybrid step-2 design, owner decision register including B-5/B-6/B-10 resolution, threat model, Docker/Windows peer/process/pipe precedents, ADR-0006, ADR-0009 and ADR-0010. Fetched origin and created the requested isolated worktree/branch from `origin/loop/local-development`; bootstrap completion record is present. Drafted `docs/plans/HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md`. No code or runtime boundary changed.
- Self-review: verified cited repository paths exist and checked the recommendation stays proposal-only, distinguishes development-loop evidence from product isolation/enrollment, includes Windows/Linux option comparisons, fail-closed isolation verification, separate trust-root enrollment/rotation/revocation, and T-T1 signed-envelope/freshness/replay/race tests. Unresolved platform, key-custody, cryptographic, lifecycle and deployment details are marked 【要決定】. Path-citation check: no missing cited paths; 30 undecided markers.
- Verification in isolated `.loop/runtime/qa-venv` (Python 3.13): Ruff check PASS; Ruff format check PASS (128 files); mypy `backend/app` PASS; offline secret scan PASS (0 findings). Full `pytest tests -q --ignore=tests/e2e`: 1156 passed, 9 skipped, 9 failed. The failures are existing Windows native CLI conformance cases requiring model slug `gpt-6.1-sol`, absent from the available user `models_cache.json` (`test_loop_c_min_native.py`, `test_notification_native.py`, `test_trial_input_native_v2.py`). Tests were not changed or weakened. Docker live tests skipped because opt-in; do not count those as live boundary evidence.
- Commit `0455478718b1e05b275bdce9530cb018471f636b` (`docs(plans): draft the isolation and runner trust-root proposals`) pushed to `loop/HYB-A2-isolation-trust`. Branch CI for that SHA: Prototype quality run `42534797135` PASS; Loop engine checks run `42534797124` PASS (Ubuntu and Windows, Python 3.11/3.13); PR title convention run `42534797125` PASS. CI validates code/workflows; the local test failures above remain reported and were not repaired by weakening tests.
