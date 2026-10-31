# Permission observation and PEM input diagnostics

Scope: a new read-only observation capability requested after repeated live
permission mismatch despite operator configuration changes. Existing exact
authorization predicates are unchanged. This does not waive the completed
provisioning scope's two-cycle review cap or claim successful authentication.

- Safe error output now compares seven fixed permission names using only
  read/write/absent/unrecognized values. Unknown names become a capped count.
  Neither unknown strings nor raw response/exception content is copied.
- PEM line collection remains unchanged: all lines are joined into one key.
  An ephemeral RSA regression proves byte equality and successful reconstruction.
  A flattened oversized line gets a fixed safe diagnostic, not plaintext output.
- 33 focused tests passed; the complete engine verifier/advisory audit passed
  with 186 tests and 6 opt-in Docker skips. Lint/format, native and Python3.11
  strict types, dependency consistency, offline secrets and advisory checks passed.
- A fresh independent read-only security reviewer accepted the observation
  scope with no blocking findings. A diagnostic docstring was clarified. It
  inspected source/tests only, with no runtime, credentials, network, execution,
  edits or delegation. No fix/re-review cycle was needed for this scope.

The operator's stage/reason proves key signing and installation identity passed
but does not identify the differing field. Actual permission comparison and
successful provisioning remain pending operator execution. No scope was added
or accepted automatically, and no key was stored after failed authentication.
