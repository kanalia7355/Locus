---
name: security-audit
description: Audit loop authentication, authorization, process boundaries, data access or external communication changes in a separate read-only context.
---
Trace control-plane access, credential inheritance, file/reparse boundaries, subprocess lifetime, approval hash binding, Git administrative state and remote-operation replay. Require negative capability evidence before trusting a sandbox. Inspect protected-check publisher identity and exact head/base binding before merge. Return severity, location, finding, evidence, recommended_action and blocking in the controller review schema. Do not access actual secrets, modify files, spawn agents or use network services.
