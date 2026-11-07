# C-min owner decision — 2026-11-03 Asia/Tokyo

The owner explicitly approved normal-development ADR0011 C-min adoption and
offline implementation/validation of manifest SHA256
`4c936fec3615b09d2352e1308dee8835bf20ec709ae14585efecd9b4d27ddcb4`.
Before any implementation, that manifest and every referenced file matched its
approved SHA256. The approved manifest/design/proposal/review bytes are preserved.
ADR changes made afterwards are the expressly authorized adoption, not a mismatch
silently accepted before implementation.

Authorized: extend existing AuditRelay; connect Worker/Reviewer/GoalEvaluator;
zero model-facing tool declarations; reject tool calls before execution;
same-PC trusted-memory authorization-header transit to the same official endpoint;
durable send reservations and crash recovery; offline mocks, existing QA/CI and
independent security review. Reuse Controller/Development Loop/local_commit_push.

Not authorized: API-key billing, credential extraction/repurposing, live connection,
authentication recovery, audit-service operations or 30-minute unattended Loop.
Real ChatGPT-path validation and any Loop trial require separate owner permission.
No task, budget, historical trial or decision is reset by this decision.
