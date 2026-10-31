# Merge App 401 observation

The operator requested more precise Merge authentication diagnostics after an
installation-stage HTTP401. The reported status alone does not prove a wrong
key, revoked key, wrong issuer ID or clock issue. Successful auth is not claimed.

Implementation compares the candidate RSA public identity with only the exact
saved Review key in local memory; no credential enumeration, private material,
fingerprint or alternate-App authentication is output. A match fails before API
calls. On401, only fixed comparison and server-clock classifications can be
included. HTTP Date parsing never emits the raw header or body. No system clock,
key assignment, scope predicate, token constraint or activation gate is changed.

40 focused cases passed. New simulations cover PKCS1/PKCS8 same-key detection,
different/missing reference, first and protection-read401 paths without storage,
clock classification and arbitrary diagnostic-value redaction. The complete
engine suite passed with193 tests and6 explicit opt-in live skips; lint/format,
native and Python3.11 strict typing, secret scan and dependency checks passed.

A fresh read-only security reviewer found one low reporting gap: the second
protected-branch read lacked comparison annotation on401. Fix/re-review cycle1
covered both reads and passed without remaining findings. No runtime, vault,
credentials, network, test execution, writes or delegation were performed by
the reviewer. Actual Merge auth and the original cause were unverified at that
review checkpoint.

## Subsequent live observation

The operator subsequently reported successful Merge provisioning with the exact
approved repository and permissions, `authenticated=true` and `activated=false`.
A separate read-only probe using the saved local credentials authenticated both
Apps and read main plus check-runs. The Merge policy observer also successfully
read branch protection and rulesets. Its authorization and atomic-base results
remain false; no remote mutation was performed. This establishes current
authentication success, without identifying the cause of the earlier HTTP401.
