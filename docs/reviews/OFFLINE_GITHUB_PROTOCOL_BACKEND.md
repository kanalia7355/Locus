# Offline GitHub protocol dependency

2026-11-03 (Asia/Tokyo). Implements only the protocol dependency of the approved
MAIN_FF_INTEGRATION_DESIGN.md, SHA-256
34cdd903506410ed45d63d041517776f7a2b0134c08d2166d55c8ad57e5cfb8f.
The existing MainIntegration/LocalDelivery/StateStore remain authoritative.

The new adapter uses the existing GitHubManager process and bounded JSON parser.
It rejects the default real ProcessRunner and requires an injected offline test
process. No CLI/config activation route or production transport is installed.
The offline flag is a trusted test seam, not an OS sandbox or security claim
about arbitrary injected Python objects.

Mock contracts cover repository and actor, exact source/target refs, workflow
contents at the target SHA, complete bounded pagination, run/attempt/job/check
suite/app identity, successful checks, protection/rules and the fixed GraphQL
beforeOid atomic update. The original durable reservation and Controller budget
are checked before any simulated POST; cancelled/expired uncertain outcomes may
be observed in a bounded read-only window, never resent.

Evidence: 23 adapter tests were part of the stable-source full engine run
(692 passed,7 skipped, audit/lint/format/type/secret/dependency checks passed).
Four test-only additions subsequently passed with the full adapter selection:
27 passed in3.06s; lint and format passed. These add changing totals, duplicate
page IDs, changed offline marker and observation-window exhaustion.

Fresh independent read-only audit and test-only follow-up: no findings,
pass_with_limits. Reviewer did not execute tests. Explicit latest-attempt race
and initial-window elapsed-time progression tests remain coverage limits.
Mock evidence does not establish live REST/GQL compatibility or acceptance of
the paired source no-op update. No GitHub mutation was executed by this adapter.

Earlier production proposals describe a missing backend at their earlier source
snapshot. An offline protocol implementation now exists; live transport,
production selection, protection compatibility, whole-range independent review
and exact-SHA CI remain separate production prerequisites. Existing PR protection
still causes a hold; no main update/protection change/PR/merge is authorized here.
