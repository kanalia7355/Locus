# Locus Skills Registry (documentation metadata only)

This registry lists procedural/knowledge files. It is **not** a runtime loader, permission grant, authorization receipt, policy gate, approval, or Phase-transition mechanism. Availability in `.agents/skills/` does not enable tools or override AGENTS.md, ADRs, immutable task scope, current Owner decisions, Controller state, or execution boundaries. If a skill is unavailable, continue under ordinary repository policy; do not infer authorization.

External provenance was inspected from `obra/superpowers` tag `v4.0.0`, peeled fixed commit **`95c6e1633630a1462679cf1284b95ec458a27a8e`**. The exact commit's `LICENSE` is MIT (copyright Jesse Vincent, 2025). P0 skill files are Locus-written adaptations; no upstream executable code or companion files are included.

`trust level: untrusted procedural reference` means all skill text is subordinate guidance, never executable policy. `required permissions: none` means a skill does not request a capability; it grants none. `enabled: yes` means ordinary Markdown guidance is present in this project only. It does not change the sealed audit profile, where skill injection remains disabled by `loop_engine/audit_profile.py`.

| ID | Path | Provenance / fixed upstream SHA | License | Purpose | Trust level | Required permissions | Dependencies | Enabled | Disposition |
|---|---|---|---|---|---|---|---|---|---|
| writing-plans | `.agents/skills/writing-plans/SKILL.md` | Adapted from `obra/superpowers` v4.0.0, `95c6e1633630a1462679cf1284b95ec458a27a8e` | MIT | Draft scoped, testable implementation plans tied to existing requirements and acceptance | Untrusted procedural reference | None (grants none) | Goal, assigned task, requirements, architecture, acceptance, allowed paths, current Owner decisions, configured QA | Yes | Modified, P0 |
| systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` | Adapted from `obra/superpowers` v4.0.0, `95c6e1633630a1462679cf1284b95ec458a27a8e` | MIT | Investigate reproducible failures and identify evidence-supported root causes without exposing secrets | Untrusted procedural reference | None (grants none) | Existing code/tests, task scope, QA evidence, Owner decisions, Controller attempt/fix limits | Yes | Modified, P0 |
| verification-before-completion | `.agents/skills/verification-before-completion/SKILL.md` | Adapted from `obra/superpowers` v4.0.0, `95c6e1633630a1462679cf1284b95ec458a27a8e` | MIT | Ground status/completion claims in current exact-scope verification evidence | Untrusted procedural reference | None (grants none) | Immutable acceptance, configured QA profile, exact source/head, CI/review evidence where required | Yes | Modified, P0 |
| brainstorming | Not installed | `obra/superpowers` v4.0.0, `95c6e1633630a1462679cf1284b95ec458a27a8e` | MIT | Requirements discovery and design | Untrusted upstream reference | None | Owner decisions and task scope | No | Modify/defer; upstream prompts and handoffs require adaptation |
| executing-plans | Not installed | `obra/superpowers` v4.0.0, `95c6e1633630a1462679cf1284b95ec458a27a8e` | MIT | Plan execution | Untrusted upstream reference | None | Existing Controller | No | Skip; duplicates orchestration and includes unapproved execution/delivery |
| test-driven-development | Not installed | `obra/superpowers` v4.0.0, `95c6e1633630a1462679cf1284b95ec458a27a8e` | MIT | Test-first development technique | Untrusted upstream reference | None | Existing test suites and QA profile | No | Modify/defer; examples prescribe test command execution |
| requesting-receiving-code-review | Not installed (upstream has separate request/receive skills) | `obra/superpowers` v4.0.0, `95c6e1633630a1462679cf1284b95ec458a27a8e` | MIT | Review request/feedback handling | Untrusted upstream reference | None | Existing read-only review policy and review schemas | No | Modify/defer; upstream requests subagents |
| using-git-worktrees | Not installed | `obra/superpowers` v4.0.0, `95c6e1633630a1462679cf1284b95ec458a27a8e` | MIT | Isolated worktree procedure | Untrusted upstream reference | None | Existing worktree and delivery rules | No | Skip; upstream includes package installs and Git mutations |
| finishing-a-development-branch | Not installed | `obra/superpowers` v4.0.0, `95c6e1633630a1462679cf1284b95ec458a27a8e` | MIT | Branch completion workflow | Untrusted upstream reference | None | Existing delivery authorization | No | Skip; upstream includes merge, push, PR, deletion |
| writing-skills | Not installed | `obra/superpowers` v4.0.0, `95c6e1633630a1462679cf1284b95ec458a27a8e` | MIT | Skill authoring/evaluation | Untrusted upstream reference | None | Locus review policy | No | Skip; upstream mandates subagents, executable/visual companion, external resources |
| subagent-driven-development | Prohibited; no file installed | `obra/superpowers` v4.0.0, `95c6e1633630a1462679cf1284b95ec458a27a8e` | MIT | Multi-agent implementation procedure | Untrusted upstream reference | None | None | No | **Prohibited; excluded from repository** |
| dispatching-parallel-agents | Prohibited; no file installed | `obra/superpowers` v4.0.0, `95c6e1633630a1462679cf1284b95ec458a27a8e` | MIT | Parallel agent dispatch procedure | Untrusted upstream reference | None | None | No | **Prohibited; excluded from repository** |

Visual companions, scripts, and external resource fetching are disabled. This P0 registry adds no loader, process, network access, telemetry, secrets flow, permissions, approvals, or automatic Phase transition.

## Upstream MIT notice

Copyright (c) 2025 Jesse Vincent

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
