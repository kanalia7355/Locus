# Acceptance remains unchanged

Use section18 of docs/requirements/AUTONOMOUS_LOOP_SPEC.md without relaxation:

- Generate tasks from a Goal and manage their dependencies.
- Execute implementation tasks through Codex CLI.
- Bound implementation/test/review repair to three total attempts and two review-fix cycles.
- Hold failed/approval-dependent tasks while continuing independent work.
- Persist human decisions and support approval/rejection later.
- Resume across sessions without duplicate effects or state updates.
- Create GitHub PRs and merge only under all safety conditions, never bypass CI.
- Generate progress reports from persistent state.
- Pass externally mocked E2E tests.
- Support limited real Codex/GitHub integration testing.

Unavailable live isolation, remote enforcement and atomic base binding are unfulfilled acceptance gates. They are not marked passed by local/mock tests.
