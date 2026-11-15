"""Deterministic job controller for Locus development.

The controller owns scheduling, verification, attempt accounting and escalation.
Models own only implementation and review text. Nothing here grants credentials,
network egress, main-branch access or approval authority: a job that needs a
judgement call stops and asks the owner.

It drives the existing collaboration contract in `progress/<phase>/tasks/*.md`
(`docs/agent/PROTOCOL.md`) rather than introducing a second source of truth, and
it never writes `.pi/`, `.loop/`, `loop_engine/`, `docs/plans/` or
`docs/planning/`.
"""

VERSION = "0.1.0"
