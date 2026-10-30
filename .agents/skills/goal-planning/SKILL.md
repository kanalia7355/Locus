---
name: goal-planning
description: Convert an approved loop Goal into a proposed requirements and task DAG; use during loop plan, not implementation.
---
Read the provided immutable Goal, existing requirements, architecture and acceptance. Propose requirements, nonfunctional constraints, architecture, risks and human decisions using the controller's plan schema. Do not replace or relax source acceptance. Every task needs concrete acceptance criteria, allowed paths, verification profile and dependencies. Use initial states and zero attempts only. Validate acyclic dependencies. Ambiguous scope/security/cost/publication decisions remain explicit requests. Do not start implementation, external services or subagents.
