# ADR0009 audit worker core evidence

Owner approved the dedicated audit Windows account and its separate Codex login
on2026-11-01. This records design/implementation authorization only. No account,
service, provider login, App permission or deployed binary was changed by this work.

## Implemented source boundary

- `audit_packet.py`: closed canonical JSON, exact Goal/requirements/architecture/
  acceptance/task/QA hashes, immutable head/base/policy/attempt/scope/nonce binding;
  metadata128KiB, source2MiB/256files/128KiB per revision, fixed32KiB chunks.
  No packet command/path-to-open/model/provider selection. Source paths are labels
  only, with traversal/sensitive-path/case-collision and known-secret rejection.
- `audit_spool.py`: exclusive transactional nonce reservation, ordered transfer,
  whole-packet hash validation, execution reservation before model invocation,
  immutable findings, exact Review-side ACK and settled source BLOB removal.
  Unknown outcomes remain reserved across restart. Consumed nonces, binding,
  findings and append-only transitions remain; no age reset or user-file deletion.
  A hard12MiB database page cap includes retained history and leaves ample room
  inside32MiB for rollback recovery; at most8 unsettled requests. Full storage
  holds work rather than discarding required evidence.
- `audit_supervisor.py`: Review-peer-only audit requests, independent protected
  evidence revalidation before work and after model execution/result retrieval,
  shared caller deadline/cancellation, bounded outbound findings frames. Operator
  health conveys no authentication/runtime/activation claim.
- `audit_execution.py`: fixed read-only, ephemeral, keyring CLI invocation with
  authoritative prebuilt local/transport schemas. No contract/failure-log writes,
  Git, QA, Docker or source program invocation. Reject tools, malformed/duplicate
  JSON, failed/incomplete turns, multiple finals, wrong task or invalid schema.
  Raw CLI diagnostics and reasoning are not persisted or returned. Existing
  ProcessRunner supplies owned job lifetime, bounded output and cancellation.

## Evidence and limits

Focused synthetic tests:64 passed across `test_loop_audit_spool.py`,
`test_loop_audit_supervisor.py`, `test_loop_audit_execution.py`.
Full `scripts/verify_loop.py --audit`:371 passed,7 skipped (Windows symlink
privilege and opt-in Docker live tests); Ruff format/lint and native/3.11 Linux
strict types passed. Offline secret scan0 findings; pip consistency passed;
dependency advisory scan found no known vulnerabilities in audited packages.
The local unpublished project itself is outside PyPI advisory lookup.
These tests use temporary storage and a mock model/process, with no credentials,
service registration, real Codex login or external inference.

Fresh read-only security review `/root/audit_worker_protocol_review` initially
found two Medium issues: unbounded settled history and missing append-only
transition records. Fix/re-review cycle1 accepted the storage cap and durable
transactional journal. Final cycle2 reviewed the added model adapter and accepted
the preparatory scope with no findings. Both fix cycles are exhausted for this
scope. Reviewer did not run tests, modify source, use the network or access
deployed state/credentials. Test results are implementer evidence. Agent usage
telemetry was unavailable; invocations were bounded to initial + two re-reviews.

Default model and execution boundaries fail closed. Passing these tests does NOT
prove peer authentication, source provenance, OS isolation, keyring persistence,
safe CLI logging, restricted provider egress, actual model cancellation or a live
review. Protected evidence authority and Windows/runtime adapters are still
required. No engineering gate is replaced by a boolean assertion. The existing
App services remain preparation-only; signing/merge/product execution stay held.

## Remaining implementation in approved ADR0009

1. Sealed Windows audit deployment and actual identity/SCM/filesystem/credential
   negative-capability proof, preserving used App accounts/passwords/vaults.
2. Immutable client/catalog/config/contracts and real zero-tool/logging/egress
   proof under the new identity before enabling owner-only authentication enrolment.
   Installed CLI0.166.0 is approximately372MB; streaming bounded artifact checks
   must handle it rather than reusing the64MB small-source reader.
3. Protected evidence/source assembly authority and authenticated Review-to-Audit
   IPC; caller JSON may not establish its own review authority.
4. Audited administrator deployment, owner's dedicated login, restart proof and
   full service review/publication integration. No login invitation or administrator
   command is issued before those concrete deployment controls are reviewable.

The frozen `.loop/architecture.md` still says main does not exist and `.loop`
configuration still names the old base. Actual main exists. These are preserved
inputs for the separately gated hash-bound migration, not silently corrected here.
