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
