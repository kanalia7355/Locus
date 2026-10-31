# Development Loop — user requirements, 2026-10-31

Add an outer loop to the existing implementation/QA/PR/CI-repair/safe-merge
controller. This Bootstrap does not authorize Locus product development.

1. After every observed PR merge, fetch the latest intended repository main and
   reassess immutable Goal, requirements, design and acceptance.
2. Detect missing features, bugs, insufficient tests, security, performance and
   maintainability problems.
3. Every improvement needs severity, concrete evidence, reproduction, expected
   effect and testable acceptance; no cosmetic churn or meaningless refactoring.
4. Deduplicate findings, update dependencies/priorities, select executable work
   and hand it to the existing implementation loop.
5. Repeat implementation, local and independent QA, PR, Checks, bounded repair,
   safe merge, then project assessment.
6. Complete only when every Goal criterion is met, current-head mandatory QA
   passes and no major issue, blocking finding or pending decision remains.
7. Detect repeated failures and quality stagnation; hold or stop rather than
   creating endless replacement tasks.
8. Preserve `$loop 2h` / `$loop resume 2h`: save state at deadline, explicitly
   resume in a new bounded time window, retain task attempts and safety caps.
9. Continue independent work while human decisions block other tasks.
10. Reuse the existing gh-authenticated user for PRs; merge only under all safe
    merge conditions. Do not weaken tests/CI to obtain a pass.
11. Never automatically accept Goal changes, relaxed acceptance or major
    architecture changes. Maintain sandbox, runtime, retry and stop restrictions.

Required modules: `goal_evaluator.py`, `gap_analyzer.py`,
`improvement_planner.py`, `progress_evaluator.py`, `completion_gate.py`.

Acceptance: a test repository continuously exercises implementation → PR → CI
failure → repair → safe conditional merge → next improvement generation.
External stages unavailable on real GitHub may be mocked, but reports must
distinguish them. Prepare the next `$loop` invocation without starting the
Locus product loop or performing a main validation merge.
