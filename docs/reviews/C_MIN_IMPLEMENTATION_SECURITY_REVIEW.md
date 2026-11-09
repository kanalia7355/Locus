# C-min implementation security review — 2026-11-03 Asia/Tokyo

Disposition: **PASS for offline implementation scope only**. Initial review and
two bounded fix/re-review cycles completed. No unresolved blocking findings in
the reviewed C-min source. No further core review cycle was used.

Reviewer: isolated read-only `/root/c_min_implementation_security_audit`, using
`.agents/skills/security-audit/SKILL.md`. Local source/test inspection only: no
edits, tests, credentials, models, network, services or delegation. The reviewer
did not rerun the implementer's verification. Reliable per-agent token/elapsed
counters were unavailable. All nine supplied source hashes matched at final review.

| Source | Reviewed SHA-256 |
| --- | --- |
| model_gate.py | b503960328823c5f87551a606d45dd1cb45983b5b37f86a90e06185b6985d9cd |
| model_invocations.py | fcf3568f4a3403471a0635e5f3904afe36d904bbffec984cecf338fed532595a |
| c_min_runtime.py | b7da5c3103e7f120cee676b60f6f0abb7c56c74bb1fa000a7362dd051545e5af |
| audit_transport.py | a7acf15fea7b4dc549d4ffbc250575c9a7c5679e4418b7ca1a46b81c15e1d3f2 |
| process.py | 6182031d5b47680c92390af4be195a955f3a7dc43114d95598e960d753337b3e |
| windows_tcp_peer.py | cd3af9823d1d2f610e7b18869c9549ee93d76f1cb6a7bb5017eb4b09471f02c9 |
| codex_runner.py | 9b81a79d0ecae489e9371b1387d1409355a95c101af1cf56fac6cf62c8358507 |
| toolless_boundary.py | 7d36187fab6da606dbee3bb9ea689b3ed3eb70502c88386e79735ed3d705bc10 |
| controller.py | 4769066c7df5cac6ee0d8c0e86c87b1477acbfb32842cdc067f949b970bf9175 |

Resolved findings:

- **High:** authoritative headers bypassed body metadata validation. C-min now
  requires canonical header/body equality, rejects continuation and unknown beta
  semantics, and has tests proving no provider construction/reservation on rejection.
- **High:** native test privacy differed from production. Actual command generation
  now pins a protected write-denied log/SQLite-log sink and private metadata storage;
  native tests exercise that command and inspect all newly created artifacts.
- **Medium:** profile normalization hid reparse points; owner checks only compared
  process identity. Raw paths/ancestors and actual filesystem owner/access stamps
  are now checked before any real auth load (still separately unapproved).
- **Medium:** output snapshots/progress could contradict accumulated state.
  Streamed messages must start empty; unsupported reasoning snapshot changes and
  out-of-order/repeated progress fail before CLI dispatch.
- **Medium follow-up:** invocation TEMP inherited unverified permissions. Existing
  private-directory helper now protects/validates owner and exact ACL, including
  the C-min parent and pre-resume recheck.

The final reviewer assessed real-checker kernel API fakes, durable-commit/send/
caller-rollback tests and native synthetic artifact canaries as useful offline
evidence. Exception-propagation-only tests are retained with narrower meaning.
Synthetic Windows TCP tables explicitly use the Windows32-bit ABI on Linux CI.

The fixed built-in provider tries a WebSocket upgrade. Rejecting the single
recognized owned-CLI GET with HTTP/1.1 426 makes the pinned client select Lite
HTTP without retry errors. No101, WebSocket frames or GET reach the provider.
The reviewer explicitly judged this denial-only behavior within approved GET
rejection scope; it is not WebSocket inference support or provider substitution.

Residual limits: no ordinary ChatGPT auth/entitlement/live Lite/deployed-artifact
proof; same-user host compromise and protocol drift remain stated assumptions.
Final aggregate QA is the implementer's responsibility. Separate live permission,
nonsecret auth-profile reconciliation, current runtime receipts and later Loop
permission remain mandatory. Old receipts were not promoted to success.

## Separate public-reference scanner adjunct review

After aggregate QA identified public-hash false positives, a fresh read-only
`/root/public_reference_scan_audit` reviewed only that new narrow classifier. It
did not reopen or restart C-min's two-cycle review. Disposition: **PASS**, no
findings. It independently read/Get-FileHash verified the approved manifest
`4c936fec3615b09d2352e1308dee8835bf20ec709ae14585efecd9b4d27ddcb4`.

The classifier exempts only that exact path, detector type, five public-reference
positions and full approved bytes. Changed bytes, other paths/lines/types remain
findings. The synthetic environment marker pragma covers only the nonfunctional
local mock marker. Regression assertions cover all mismatch cases. The scanner
and tests were not run by that reviewer; implementer results are separate.
