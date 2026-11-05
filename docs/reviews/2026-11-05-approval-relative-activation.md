# Approval-relative activation: offline security review and validation

Authority: owner instruction 2026-11-05; see
../plans/APPROVAL_RELATIVE_ACTIVATION.md. No live authentication, inference, actual
configuration/ACL change, service operation, main update or Loop launch authorized.

Isolated read-only reviewer /root/approval_relative_activation_review inspected
the final source and synthetic tests. Initial review passed; one final guard
fix/re-review cycle passed, findings=[], blocking=false. The reviewer independently
ran 94 synthetic tests (33.19 seconds), with no credential/config/production-state,
network/service access, writes or delegation.

The review covers atomic owner decision/registration/activation, one immutable
trial expiry from decision+180s, no renewal after restart/expiry/unknown outcomes,
v3 reauthorization before upstream, pre-resume/poll/postresponse/proof consent
checks, exact catalog snapshot admission and original normal-run timestamps.
Normal v3 evidence and separate finite normal-run owner authorization remain gates.

Final local verification: 969 tests passed, 7 existing opt-in real Docker tests
skipped, 552.52 seconds. Lint, formatting, both Python type targets (94 source
files), secret scan and dependency consistency passed. The aggregate verification
command exited1 because the final advisory query timed out at pypi.org. Only that
read-only advisory command was retried with unchanged settings and exited0: no
known vulnerabilities. The failed original log/receipt is retained; it is not
rewritten as a successful command. Required components therefore have successful
results, with separate retry provenance, rather than a fabricated aggregate pass.

The installed pinned CLI against the existing synthetic loopback harness also
completed one capture and two prefrozen validations with the exact trial workspace,
fixed nonsecret installation identity and reviewed catalog. This is synthetic
conformance, not actual ChatGPT connection or native/live profile equivalence.
The initial new activated-adapter fixtures correctly rejected precomputed IDs
issued before approval; only the synthetic decision/issuance chronology was
corrected. Production freshness validation and legacy assertions remain unchanged.

Old frozen plans retain their original absolute-expiry wording. New versioned
requests supersede timing only under the owner's latest instruction; old expired
manifests are never converted. The execution deadline is absent while approval is
pending; actual owner approval remains mandatory and cannot be inferred from an
offline review, this report, a generated packet or a generic $loop command.
Exact-commit remote CI is recorded in the final completion report.
