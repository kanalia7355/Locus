# CI registration wait — live follow-up defect

The first real product task exposed two ordinary failures: unused callback
parameters failed the unchanged frontend lint rules, and a later proposal was
invalid/unavailable. After source/base/process reconciliation, the existing
third and final worker attempt repaired the lint issue using typed mocks. No
counter, acceptance, test or CI gate was reset or weakened. Local container QA
and independent model review passed; PR3 was created at
`182a447fbb5c9d2c551ea216d8b5d22db895cc72`.

The initial CI observation saw five queued/running checks and two active runs,
before `conventional-title` registered. Required-name presence was checked too
early, creating a medium `CI held (missing, unclassified)` condition. All11
checks subsequently passed at the same head, but that stale condition blocked
delivery completion. This is a reproduced runtime defect, not a human decision
about credentials, billing or permissions.

The fix waits when positive active check/run evidence exists. Terminal or
unknown missing checks still hold. A narrowly bound legacy condition may become
`obsolete` only after the same verified source and repository/head/base are
rechecked and every configured context and observed check/run passes. This is
not `approved`; the original question/hash remain stored, the actor is
`system:ci-observation`, and the append-only event explicitly records no human
approval. Concurrent human approval/rejection/revision cannot be overwritten.
Other decisions and all merge gates remain active. No worker is executed again
when delivery resumes at its already-used third attempt.

Independent read-only audit: `/root/ci_registration_audit`, initial review of
this separate follow-up diff from6de191e, pass/no findings. No tests, network,
writes or delegation were performed by the auditor; exact time/usage was not
supplied. This is not a further cycle of the completed runtime boundary audit.
The one-edit-per-file prompt now explicitly describes its existing validator.
Verification and the real resumed-delivery outcome are recorded after execution.

Final evidence: engine verifier123 passed,6 explicitly skipped live cases; lint,
format, Python3.13/3.11 types, secret scan and dependency checks passed. All4
required aggregate checks passed again in the immutable container, including
application/browser verification. Fresh doctor containment receipt passed and
reported ready. The unchanged PR3 delivery then resumed to `completed`, still
at3/3 worker attempts and the same182a447 head. Its stale registration condition
is `obsolete` with the system actor; no human decision was approved. All GitHub
checks passed and every merge remains held. No further worker, commit or PR was
created for the completed product task.
