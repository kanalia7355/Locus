# Synthetic ACL rehearsal and Windows CI repair evidence

2026-11-04 Asia/Tokyo. Actual profile/ACL/auth/model/service/Loop/main operations
were not performed. Only newly created managed synthetic fixture ACLs were changed.

## Executed checks

- Stable-source full engine QA before the final two added regression cases:
  826 passed, 7 skipped, 424.31 seconds; lint/format, native/Linux3.11 types,
  PowerShell cold/warm, secret scan and dependency/advisory checks passed.
- Final focused synthetic diagnostic/ACL suites: 11 passed in 12.72 seconds.
  The independent reviewer separately ran the same suites: 11 passed in 11.90s.
- Existing mock-only native CLI and Arg0 tests were run with the related suites;
  the earlier focused run passed 21 cases. Totals overlap and must not be added.
- No added/removed skip, timeout change, CI configuration change or production
  validator modification. Hosted native-CLI skips remain explicit when the pinned
  CLI/catalog is absent; local mock-native execution is distinct from live inference.

Current exact-commit full QA and hosted CI are checked after the reviewed commit
is published. Their final results must refer to that commit, not the old failed CI.

## Windows timeout investigation and repair

The old c6da9cf Windows3.13 job timed out at the unchanged 20-second diagnostic
process limit with no stdout/stderr; Windows3.11 was matrix-cancelled. The older
legacy test explicitly loaded inbox Utility/Management modules, while the new
connection-preparation case used -File and relied on automatic discovery of
Get-Acl/Security and other commands. The old log cannot establish the exact
internal stall, so no unsupported timing diagnosis is claimed.

Both tests now use the same fixed system module loader, explicitly import inbox
Utility/Management/Security, disable subsequent automatic loading in that child
process, and emit finite host/modules-start/modules-ready markers. The 20-second
limit and all original assertions/negative cases remain. A shadow-module-path
regression test proves that an untrusted module search location is not loaded.
This removes that discovery dependency; it does not promise that a future slow
host cannot exceed a deadline. Such a timeout still fails, with stage evidence.

## ACL results and critical distinction

The native test helper reuses existing Native, ProcessRunner, private_acl and
Arg0Guard. Fresh fixtures are restricted to .loop/runtime/probes/acl-compat-UUID;
a synthetic SID is never provisioned as an account. A restricted token derived
from the current process reads ONLY fixed synthetic canaries, reverts immediately
and closes handles. No LogonUser, real sandbox secret, account/group operation,
actual auth/config data, network or provider is used.

Non-propagating directory SetSecurityInfo plus metadata-only FILE handles proves
bounded object changes, unchanged non-target ACLs and bytes, exact rollback,
known-partial rollback and no-write rejection for unknown acknowledgement,
ACL drift, replacement identity and out-of-fixture targets. Ordinary propagation
is shown to remove inherited helper access; official-style group regrant is
shown to force admission HOLD rather than a silent exception.

The strict five-object candidate preserves old helpers but makes fresh PATH
apply_patch.bat unreadable to the sandbox group. Pinned source and a valid harmless
owner-run batch establish that this candidate is NOT normal sandbox compatibility.
It must not be applied. The separate native zero-tool CLI test alone cannot prove
this normal-tool path works.

The ACL-only three-object alternative protects auth/config and retains root group
RX with NO inheritance flags, keeping existing nonsecret runtime child rights.
Fresh batch shims are group-readable; auth/config and recreated replacements are
not. Rollback remains exact; changed identity remains held. Current production
private_acl/Arg0Guard intentionally reject this shape. Thus synthetic ACL/access
compatibility PASS is not runtime-boundary adoption or live-readiness PASS.

See ../plans/C_MIN_ACL_REPAIR_OWNER_APPROVAL.md for the exact candidate, before
fingerprints, guarantees lost/substituted, required retained-handle/adoption tests
and limited next owner approval. No executable real repair block is issued.

## Independent review

Initial medium finding: fresh shim compatibility unproven. Fixed by tracing the
pinned public source, reproducing the conflict and rejecting the five-object plan.
Cycle1 medium finding: two-file protection does not prevent inherited credential
exposure after recreation. Fixed by the non-inheriting root candidate, positive
recreation test and explicit future full-lifetime no-delete metadata-handle gate.
Cycle2: no findings; both fix/re-review cycles used. Reviewer did not access actual
profile/credential/protected state, SAM, services, network or models. Resource
usage/elapsed review time was not instrumented. Approval of real ACL changes,
auth lifecycle, actual connection and Loop remains absent.
