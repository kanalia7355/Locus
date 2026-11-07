# C-min offline implementation result — 2026-11-03 Asia/Tokyo

Status: offline implementation/verification complete; **live execution held**.
Owner approval and pre-implementation hash verification are recorded in
[C_MIN_OWNER_APPROVAL.md](C_MIN_OWNER_APPROVAL.md). The approved manifest still
has SHA256 `4c936fec3615b09d2352e1308dee8835bf20ec709ae14585efecd9b4d27ddcb4`.
Frozen proposal/review bytes remain historical records; adoption is recorded
separately in ADR0006/0011. LF attributes preserve the exact approved bytes.

## Delivered

- Existing AuditRelay now has an opt-in C-min closed Lite request/SSE contract.
  Nonzero definitions, history, unknown structures, malformed/oversized/truncated
  frames and tool-call items are rejected. No arbitrary stripping/fallback.
- Authoritative header metadata must match the parsed closed body metadata.
  Continuation and unapproved beta semantics are rejected before provider send.
- The single known owned-CLI WebSocket upgrade is **denied** with HTTP/1.1 426.
  This makes CLI0.166.0 select Lite HTTP without the former four retry errors.
  No WebSocket is established and no GET is forwarded.
- Same-backend HTTPS/ChatGPT header transit stays in trusted memory. No new model
  credentials, paid API integration, login/status/logout/refresh client or store
  migration was added. Actual authorization-header transit was tested only with
  synthetic strings and a fake HTTPS provider object.
- Owned suspended CLI binding checks TCP PID, retained creation identity, job,
  SID and executable path. Invocation state is reserved durably before launch
  and before possible upstream bytes. Prepared recovery preserves ID/deadline;
  uncertain sends/results hold, including against new owners/run IDs.
- Normal Worker/Reviewer/GoalEvaluator use the existing CodexRunner adapter and
  existing caller result commits. Only owner/source references and acknowledgement
  plumbing were added; Controller scheduling and Git delivery were not replaced.
- Production commands use a protected denied log/SQLite-log sink, private SQLite
  metadata directory and private TEMP, with owner/ACL/reparse verification.
  Existing operator CODEX_HOME/storage remain unchanged. No raw model transport
  stderr/exception/input/response is retained as diagnostic evidence.
- Normal startup requires a current C-min v3 receipt, separate exact live/run
  permission and registered nonsecret storage/profile evidence. Old v2 receipts
  cannot activate it. No new success receipt or live permit was issued here.

`.loop/config.yaml`, Goal/acceptance, local_delivery.py, git_manager.py and Actions
definitions were not changed. No main Push, PR, App activation or merge occurred.
Existing audit services and historical intents/attempts were not changed.

## Executed evidence

| Check | Result / limit |
| --- | --- |
| Existing scripts/verify_loop.py --audit | 572 passed, 7 skipped; lint/format, strict types including Linux3.11, secret scan, pip consistency/advisories passed |
| Extra final Windows launch/real wrong-PID test | 2 passed; the additional real wrong-PID case was added after the aggregate run |
| Linux ABI/known public-reference regression targets | 7 passed on Windows; same Windows API ABI explicitly simulated cross-platform |
| C-min targeted suite before final extra wrong-PID case | 88 passed, including five pinned native CLI mock cases |
| Source-only Linux QA container | 82 C-min contract/recovery/kernel tests passed, network-none/read-only mounts/non-root workload |
| Existing real Docker containment suite (explicit opt-in) | 6 passed; aggregate skips are not represented as executed there |
| Immutable QA image | sha256:813ab482ac2e0aece7527eeb0186e8dc4c4efb8076afab77b0f282a8403cae9d; current audit/manifests checked |
| Backend/application static checks | Ruff/format/mypy passed |
| Frontend | ESLint passed; 11 tests; TypeScript/Vite build passed; 5 Playwright E2E passed |
| Packaging | Wheel built with existing pinned tools, no new dependencies |
| Dependencies | pip consistency/advisories passed; npm audit found 0 vulnerabilities; local package is not a PyPI advisory subject |
| Independent security reviews | C-min offline source PASS after two fix/re-review cycles; separate exact-public-hash classification PASS |

The aggregate's one Windows symlink privilege skip remains unverified on this
account. Its six opt-in Docker skips were subsequently executed separately.
The pinned native CLI is not provisioned on hosted CI: those native tests skip
there and cannot be counted as hosted live/model evidence. Local actual CLI
tests use isolated homes, nonfunctional markers and loopback mocks only.

Canary tests inspect every newly created native-test artifact, including private
SQLite/TEMP/home files, for synthetic auth/input/output/reasoning strings across
success, malicious call, unknown response, truncation and cancellation. PID/SID/
job/creation negative logic is tested through Windows API fakes; a separate real
same-SID/wrong-PID TCP rejection and suspended-child non-resume test also pass.
No real other-user login or provider inference was performed.

Initial aggregate attempts are not hidden: an obsolete alias fixture initially
failed after normal C-min probes were held. Its legacy assertions remain intact
with explicit legacy fixture selection, plus a new no-auth normal-hold test.
The next aggregate passed tests but stopped on public SHA/marker false positives.
The manifest was not edited: a narrowly reviewed exact-file/type/position/digest
classifier and exact synthetic-marker pragma resolved them. Changed/unknown
values still fail. No test, assertion or required CI job was disabled/weakened.

## Residual conditions and next owner decision

Offline evidence is not proof of ordinary ChatGPT authentication, entitlement,
provider media/SSE behavior or production-profile persistence. Internal Lite
changes fail closed. Same-user host compromise remains outside the stated trusted
host assumption. Partial/uncertain completion cannot be replayed automatically.
The closed initial response contract intentionally rejects unsupported event
families; a successful synthetic roundtrip does not promise live compatibility.

Before requesting a real connection, prepare one concrete bounded validation
command/packet and artifact hashes; reconcile nonsecret existing storage/profile
identity and all historical real-model permits/counts without reading tokens or
resetting attempts. The present normal-run preflight is intentionally held and
must not be bypassed by editing passed/live flags. A separate diagnostic permit
must distinguish its one-shot evidence from permission to run Controller tasks.

The next approval needs to identify:

1. Exact reviewed source/CLI0.166.0/model/provider/fixed official destination and
   the finite synthetic/public source packet; no research material or credentials.
2. A single bounded real-model attempt and cumulative remaining trial budget,
   shared deadline, result-unknown stop and no automatic resend.
3. Official CLI access to the existing ChatGPT login, with explicit handling of
   ordinary token-refresh traffic outside the inference relay. No custom refresh,
   recovery, export, re-enrolment or storage migration is inferred.
4. Necessary nonsecret profile/storage evidence and resulting receipt validation.
   Missing/changed storage causes reconciliation rather than token/key repair.
5. No service operation or Loop launch. A later30-minute Loop proposal must bind
   Goal/branch/scope/deadline/stop conditions after all prerequisites actually pass.

GitHub Actions results belong to the exact pushed commit's actual run records,
not this offline success table. Push workflows are additional verification;
their outcomes must be observed separately and never inferred from local tests.
