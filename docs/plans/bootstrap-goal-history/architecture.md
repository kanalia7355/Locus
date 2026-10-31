# Controller architecture

See docs/architecture/decisions/0003-autonomous-loop-engine.md. Deterministic Python controller -> transactional SQLite state, DAG scheduler, bounded Codex adapter, isolated verifier, independent read-only review, hash-bound human approval, scoped Git worktree, guarded GitHub integration, conservative recovery. CLI init/import/status/decision/report operations work locally. Live model/verifier transport is deliberately unproven and blocked; the gh adapter cannot provide atomic PR-base binding for autonomous merge.
