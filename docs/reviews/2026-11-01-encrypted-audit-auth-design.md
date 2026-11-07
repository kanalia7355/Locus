# Restricted audit authentication storage — design review

Scope: proposed ADR0010 only, not deployment or runtime certification.

An isolated read-only architecture reviewer examined ADR0010, ADR0009 and cached
public Codex 0.166.0 authentication/secrets source. No credentials or deployed
service state were accessed, no external services contacted and no code edited.

Initial result: one blocking Medium recovery ambiguity. Authentication status can
create a missing encryption key; save/logout can remove existing authentication;
an interrupted Windows ciphertext replacement can leave only a temporary file.
Holding activation alone does not prevent destructive pre-activation operations.

Fix: ADR0010 now requires protected nonsecret lifecycle and key/artifact consistency
checks before any authentication CLI invocation, including status. Interrupted or
inconsistent state stops for explicit reconciliation, without reset, deletion,
regeneration or cleanup. Fault-injection tests are required before real enrolment.

Fix/re-review cycle 1: disposition `pass`, findings `[]`. One of the maximum two
fix/re-review cycles was used. The owner subsequently approved the narrow storage
exception on 2026-11-01. Implementation audit and actual-role validation remain required.
This review does not approve or certify the uncommitted deployment implementation.

Local compatibility evidence: synthetic-only direct-keyring values of 1,536,
3,072 and 6,144 characters failed; a short value succeeded. With standard encrypted
storage, a 6,144-character invalid value saved, loaded from a fresh process and
logged out successfully. Ciphertext had an age header; no plaintext auth.json or
synthetic plaintext in generated files was found. These tests used unique operator
diagnostic homes, not the future audit SID, existing authentication or real OAuth.

The preparatory direct-keyring preflight now probes an oversized synthetic value,
so small-key success cannot admit real enrolment. No new audit account/service has
been installed and no real login attempted. PR6 remains open: its published head
53f84637c6f441fd18223bae78be0abb446ff5e3 has successful CI but requires review.

Current local preparatory source verification: `scripts/verify_loop.py --audit`
passed lint, formatting, native/Python3.11 type checks, 394 tests, secret scanning,
dependency consistency and dependency advisory checks. Seven tests skipped:
one unavailable Windows symlink privilege and six opt-in real Docker tests.
The local project package has no PyPI advisory record; dependency auditing does
not certify the project's own source. These checks do not prove live service
isolation, real OAuth, App review publication or merge readiness.
