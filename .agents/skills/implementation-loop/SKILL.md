---
name: implementation-loop
description: Implement one assigned Controller task within its isolated worktree and bounded attempt budget.
---
Read task scope, acceptance, architecture, prior attempt evidence, pending decisions and existing code. Modify only allowed paths. Preserve tests, hooks, policies and original requirements. Never launch child agents, access controller state/approvals, commit/push/merge or run unrestricted commands. Request blocked capabilities through structured approval_requests. Return task ID, implemented/failed/blocked status, summary, files_changed, tests_added, issues and approval_requests matching the supplied result schema. Your result is provisional; verification and completion belong to the Controller.
