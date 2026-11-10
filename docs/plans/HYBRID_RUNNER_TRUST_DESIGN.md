# Hybrid Agent Runtime — Runner trust, enrollment and key-management design

**Status: design documentation implementing the owner-approved Entry 5.** This package
covers only the trust/key-management cluster classified `OWNER_DECISION_REQUIRED` and
resolved by Entry 5 of [OWNER_DECISIONS_2026-11-10-ENTRIES.md](OWNER_DECISIONS_2026-11-10-ENTRIES.md):
**DP-035, DP-036, DP-037, DP-038, DP-039, DP-040, DP-041 and DP-043b**. It specifies the
approved trust design — OS-keystore-protected per-instance Runner identity, vetted
standard TLS, authenticated-administrator one-time-challenge enrollment, strict
instance-to-ID binding, revocable Runner ID, measured key rotation, revoke-then-re-enroll
on loss/compromise, and audit of enrollment/update/revocation/recovery — as design and
future-verification criteria only. Custom CA hierarchies, dedicated hardware
authentication and multi-administrator quorum are **not required initially** and are not
designed as prerequisites. Owner-controlled unresolved choices remain **【要決定】**.

**This document creates no key, runs no enrollment, activates no Runner, opens no
network path and changes no safety boundary.** B6 remains in force for every dispatch
and enqueue attempt; every isolation, receipt and ADR-0012 gate is unchanged and
independent of enrollment state. Runner trust channel design is not transport topology
approval: the network reachability of any Runner↔Control-Plane channel remains governed
by owner Entry 3 (`docs/plans/OWNER_DECISIONS_2026-11-10-ENTRIES.md`, Entry 3) and no
endpoint, port, firewall rule or connection is authorized here. An enrolled Runner is a
precondition for future operation, never an execution permission.

## 1. Authority, scope and safety boundaries

### 1.1 Authority

- Owner Entry 5 (2026-11-10): the trust/key-management cluster DP-035–041 and DP-043b is
  resolved to the recommended configuration; the seven verification conditions in §11 are
  owner-mandated. The decision approves the **design direction**, not key generation,
  enrollment execution, communication connection or execution activation.
- [ADR-0012](../architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md),
  especially B1–B7: B5 requires an immutable, revocable `runner_instance_id` bound to the
  enrolled OS principal, pinned binary identity and transport identity, distinct from
  Control-Plane and model-gate identities; B7 requires trust operations to reach the
  Control-Plane audit path; §4 requires fail-closed receipt/binding checks that this
  design must not weaken.
- [ADR-0011](../architecture/ADR-0011-model-facing-zero-tool-gate-proposal.md): unaffected.
  Enrollment adds no model-facing tool and does not touch Plane M.
- [Step-2 registry design](HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md) (E2/E4/E5) and
  [step-3 proposals](HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md) §3: design inputs;
  their unresolved trust items are resolved by Entry 5 within the scope of this document.
- [Hybrid threat model](../security/HYBRID_AGENT_THREAT_MODEL.md): T-S1 (Runner
  impersonation — mutual, pinned identity), T-T1 (envelope freshness/binding — unchanged,
  receipt track), T-I3 (credential separation — identity keys are never provider
  credentials), T-E3/T-E4 (isolation — unaffected; enrollment is not isolation evidence).
- Owner Q-decisions: Q7 requires production TLS/crypto choices to rest on comparison and
  verification, not assumption; this design therefore fixes **methods and procedures**
  and leaves numeric parameters to vetted standards plus measurement (§12).

### 1.2 Non-negotiable invariants

1. **Enrollment is not authorization.** An enrolled, healthy Runner still executes
   nothing while B6 is active. Receipts, policy versions, isolation evidence and the
   separate activation decision are independent conditions per ADR-0012 §4 and
   [HYBRID_ISOLATION_PROFILES.md](HYBRID_ISOLATION_PROFILES.md) §8.
2. **Fail closed on trust uncertainty.** Unavailable, stale, contradictory or unknown
   revocation/enrollment status denies the operation. No offline grace period for job
   execution, no permissive retry, no host fallback.
3. **No egress, no topology.** This design names no endpoint. Whether and how a Runner
   may reach the Control Plane is Entry 3 scope and remains separately approved.
4. **Credential separation.** Runner identity keys are not provider login credentials,
   Locus user sessions, job-authorization signing keys or receipt keys. Provider
   credential supply is Entry 4 scope and stays unapproved; identity-key custody must
   make such reuse structurally impossible (§2.4).
5. **Plane separation.** Enrollment machinery lives in the Control Plane's trust plane;
   it creates no dispatch-capable behavior, no Plane-M path, no job envelope.
6. **No evidence inflation.** No keystore comparison, checklist or design below proves a
   platform's protection; §3 specifies future demonstrations. Design claims stop at
   "specified"; runtime claims require the evidence packages of §11.

## 2. Identity model (DP-035, DP-038, B5)

### 2.1 Identity records and keys

- **`runner_instance_id`:** a stable, immutable Control-Plane record identity, unique per
  Runner installation, created at enrollment and never silently replaced. Revocation
  status, generation counter, bindings and audit lineage attach to it. This satisfies
  B5's "immutable, revocable" requirement: the record is immutable in its bindings,
  revocable in its status.
- **Per-instance identity key pair:** an asymmetric key pair generated **on the Runner
  host** inside the platform keystore, where the platform can protect it per §3. The
  private key never leaves the keystore boundary in any approved design path; only the
  public key (or CSR) and a fingerprint are exported. Where a platform cannot meet the
  required protection characteristics of §3.3, enrollment is **unavailable on that
  platform** — fail closed, no downgrade to file-based custody justified by convenience.
- **Identity generation counter:** every key lifecycle event (initial enrollment, planned
  rotation, compromise re-enrollment) increments a per-instance generation counter kept
  in the Control-Plane enrollment record. Strict instance-to-ID binding is to the
  `(runner_instance_id, generation)` pair; superseded generations are revoked, never
  valid, and their history is preserved.

### 2.2 Binding set

A certificate is issued only against the full binding set; a certificate proves none of
these properties by itself — the Control Plane verifies them from authoritative records
at every enforcement point (step-2 design E2; ADR-0012 §4):

| Binding | Content | Authority |
|---|---|---|
| `runner_instance_id` + generation | Exact enrolled record | Control-Plane enrollment store |
| installation/audience | The single Locus installation | Issuer certificate |
| OS principal reference | Dedicated Runner service identity (not interactive user) | Enrollment evidence (§5) |
| pinned Runner binary identity | Digest + version of the approved Runner build | Enrollment evidence; later change forces re-verification per DP-053a rules |
| platform profile | `W-D`/`W-S`/`L-D`/`L-S` class of the exact host | Isolation-profile evidence, when that profile's own gates run |
| transport identity | The keystore-backed key + issued certificate | mTLS handshake (§4) |

### 2.3 What is explicitly not required initially (Entry 5)

- **Custom CA hierarchy:** no bespoke offline-root/subordinate CA product is built
  initially. The Control Plane acts as the single installation-level issuer using
  standard X.509 through a vetted, platform-supported library (§4.1). If a future
  deployment already operates an enterprise PKI (DP-037), integrating it is a separately
  reviewed design change, not a default assumption.
- **Dedicated hardware authentication:** TPM/secure-enclave-backed keys are an optional
  hardening only where the platform demonstrates them (§3.2); their absence blocks no
  platform and their presence confers no approval.
- **Multi-administrator quorum:** all trust operations use single-administrator
  authority within the RBAC mapping of §6, with audit and fail-closed checks. Quorum is
  introduced only if a documented threat demonstrates need (a separate owner decision).

### 2.4 Key separation invariants

Each key family is distinct and non-repurposeable by construction:

| Key family | Holder | Role |
|---|---|---|
| Runner identity key | Runner host keystore | mTLS client authentication only |
| Control-Plane issuer key | Control-Plane host keystore | Issues Runner certificates only |
| Job-authorization signing key | Control Plane | Signs job envelopes; Runners hold public verification keys only |
| Receipt/authorization keys | Control Plane | Per step-2 receipt contract; untouched here |
| Provider credentials | CLI's own device store (Entry 4, unapproved) | Never enters any key above, any envelope, any audit record |

A Runner identity key can never mint a job, sign a receipt, approve itself, impersonate
another instance, or add a Plane-M tool declaration. This separation is verified in the
future trust test plan (§11, condition 4).

## 3. Per-platform keystore comparison (DP-038; conditions 1–2)

### 3.1 Comparison table

| Dimension | Windows | Linux |
|---|---|---|
| Primary candidate store | CNG/NCrypt persistent keys held by a dedicated Runner service account; non-exportable key generation where CNG supports it | File-based PKCS#8/PEM private keys with `0600` permissions under a dedicated unprivileged service account; standard TLS stack custody |
| Non-exportability | OS-enforced non-exportable keys are available through CNG on supported builds — must be demonstrated per exact build, not assumed | Not claimable: any local root can read a file-based key; documented as a residual TCB assumption (§3.3) |
| Cross-process isolation | Key ACLs restrict use to the Runner service account; interactive user and other services denied by ACL — must be demonstrated | File ownership + directory permissions restrict to the service UID; same-root/host processes are outside the guarantee |
| Persistence/restart | Keys persist in the keystore across restart; restore semantics must be demonstrated without exporting key bytes | Files persist; restart behavior trivial but must verify permissions survive service updates |
| Vendor/OS keystore services rejected as primary | DPAPI blobs: same-user processes (including a hostile job under a confused session) can decrypt — insufficient as sole protection; rejected | Kernel keyrings and session-bound secret services (gnome-keyring/KWallet): session/headless dependence and unlock semantics defeat unattended service use; rejected for this role |
| Optional hardening (not required) | TPM-backed CNG keys where the exact build demonstrates them | TPM2 via PKCS#11 where the exact distribution demonstrates them |
| Honest limitation | Host administrator and kernel remain TCB (as in the isolation profiles); CNG protection does not contain a host admin | Host administrator is squarely able to read/export file-based keys; the protection claim is against non-admin processes, other Runner instances, the job process and the tool-executing process only |

### 3.2 Protection-demonstration requirements (owner condition 2)

Before any platform's custody claim may be relied on, a future, separately authorized
evaluation must demonstrate on the exact build, using synthetic test keys only:

1. **Generation:** the key is generated inside the keystore; no private-key bytes appear
   in process memory dumps of the tool-executing process, job workspace, logs, or the
   CSR/protocol traffic (positive control: public key export works).
2. **Denial matrix:** access/use denied to the interactive user, a second Runner
   instance, a synthetic hostile job process, the tool-executing adapter process, and
   Control-Plane job code; allowed only to the dedicated Runner service identity.
3. **Non-exportability (where claimed):** CNG export API fails for a non-exportable key;
   the failing path is observed, not assumed. On Linux, no non-exportability claim is
   made and §3.3's limitation is recorded instead.
4. **Restart and update:** the key survives service restart and OS patching without
   re-enrollment; permissions/ACLs are not silently relaxed by upgrades.
5. **Backup semantics:** no backup/restore path exports private-key bytes; a restored
   host without its key re-enrolls rather than restoring key material.
6. **No secrets in observability:** fingerprints and key IDs are public-identity data;
   no audit, log or evidence artifact ever contains private key bytes or provider
   credentials (T-I3, B2).

### 3.3 Residual-risk statement per platform

The Windows claim is conditional on CNG behavior of the exact build; the Linux claim is
inherently narrower — file-based custody defends against unprivileged same-host
processes but not against the host administrator or kernel, which the isolation profile
documents as TCB. Neither platform's keystore evidence substitutes for isolation
evidence, and no platform's claim extends family-wide from one tested build
(HYBRID_ISOLATION_PROFILES.md §2.2 rule). Whether the narrower Linux residual risk is
acceptable for a given deployment class is part of that class's separate activation
decision, not of this document.

## 4. Trust anchor and transport (DP-035, DP-036)

### 4.1 Issuance without a custom CA product

- The Control Plane holds a single installation-level issuer key pair (standard X.509,
  vetted platform-supported crypto library) protected in the Control-Plane host keystore
  with service-account restriction; it issues per-instance Runner certificates and
  nothing else. The Runner pins the issuer's public certificate as its sole trust anchor.
- No offline root, no sub-CA tree, no bespoke PKI service initially (Entry 5 "not
  required"). Issuer compromise is a total-trust event handled by the DP-043b runbook
  (§9.4), not by hierarchy redundancy.
- **Crypto profile:** standard algorithms only — a vetted signature algorithm for Runner
  keys and envelopes, standard digest for fingerprints, standard TLS version floor.
  Specific algorithm, key size and suite selections are **【要決定】** (§12): they are set
  from current vetted standards and measurement, never invented here.
- If the enterprise deployment operates an organizational PKI (DP-037), adopting it is a
  separately reviewed change; this design does not assume its existence.

### 4.2 Transport rules (conditional on Entry 3 authorization)

- Mutual TLS using the platform-standard TLS stack (Schannel on Windows; the
  distribution-supported OpenSSL on Linux). No custom protocol, no second signature
  family on job payloads (step-3 §2.2 DP-045 rule), no bearer secrets.
- Server identity is validated against the pinned issuer anchor; client identity is the
  enrolled `(instance, generation)` certificate. Revocation status is resolved live from
  the same Control-Plane authority at connection, job preflight, immediately before
  execution, and before result acceptance/release (DP-042 rule; fail closed on
  uncertainty).
- Transport authentication is never job authorization: a valid mTLS session proves only
  that the peer is the enrolled Runner instance.

## 5. Enrollment ceremony design (DP-039)

### 5.1 Ceremony (one-time challenge, authenticated administrator)

Preconditions: the exact Runner binary identity and platform profile are known; the
dedicated OS service principal exists on the Runner host; B6 still rejects execution
regardless of ceremony outcome.

1. **Request:** an authenticated administrator (§6) creates a *pending enrollment* in
   the Control Plane, stating the proposed instance ID, platform profile and the exact
   Runner binary digest.
2. **Challenge:** the Control Plane issues a short-lived, one-time challenge bound to
   the installation, proposed instance ID, public-key fingerprint (once the Runner has
   generated its key pair) and platform profile. The challenge is single-use and expires
   quickly; expired or replayed challenges are rejected and audited. Challenge lifetime
   is **【要決定】** (measured, §12).
3. **Two-surface fingerprint confirmation:** the Runner host displays the public-key
   fingerprint on its local console; the administrator compares it with the fingerprint
   shown in the authenticated admin session before approving. This binds approval to the
   exact key without introducing a new privilege or channel — it uses the existing
   authenticated admin surface plus local observation, within the approved
   "one-time-challenge enrollment".
4. **Approval and issuance:** on approval, the Control Plane verifies the challenge,
   fingerprint match, administrator authority, absence of duplicate instance ID/key
   fingerprint, and the platform/binary bindings, then issues the certificate and
   records the immutable enrollment evidence (§2.2) with the generation set to 1.
5. **Completion:** the Runner stores nothing but the certificate and keystore key;
   enrollment evidence lives only in the Control Plane.

### 5.2 Fail-closed rejection cases (future verification inventory)

Expired, replayed, or reused challenge; fingerprint mismatch; approval by an
unauthorized or unauthenticated administrator; duplicate instance ID or duplicate key
fingerprint; unknown binary digest; unsupported platform profile; weak or nonstandard
key algorithm; self-signed or foreign-issuer clients; interrupted enrollment with
uncertain key creation (the Runner must never silently auto-regenerate and retry — it
surfaces the uncertain state and holds); issuance when the enrollment record or issuer
is unavailable. Each rejection is audited with a non-sensitive reason (§10).

### 5.3 What enrollment does not do

Enrollment never grants job execution, never issues receipts, never relaxes isolation or
network policy, never registers an adapter capability, and never authorizes the
Runner↔Control-Plane network path (Entry 3). A freshly enrolled instance is an identity,
not an activated system component.

## 6. RBAC mapping for enrollment/revocation authority (owner condition 3)

**No new permission is introduced.** Consistent with the Entry 2 precedent (no dedicated
job-approval permission; authority derives from existing roles), trust operations map to
the **existing installation-administration authority**:

- **Who may enroll, rotate, revoke, and recover:** users holding the existing
  `system_admin` flag (`backend/app/service.py`: user-level `system_admin` grants
  installation-scope administration such as `admin_projects` and admin provisioning).
  Runner trust is installation/infrastructure scope, not project scope.
- **Who may not:** `organization_admin` (`manage_roles`/`manage_members`), `project_lead`
  and all project-scoped roles are outside the mapping; no role combination reaches
  trust authority because no role permission is consulted. Delegation cannot create
  trust authority: delegated permissions are subsets of delegable project permissions
  and never touch the `system_admin` flag.
- **No self-escalation:** a `system_admin` enrolling a Runner performs no privilege
  change to any user, role, project or policy; the mapping grants no new permission on
  any object. Trust operations cannot issue or expand receipts, and receipts cannot
  alter trust state (§8.2).
- **Fail-closed:** any operation attempted outside the mapping is denied and audited.
- Future option, explicitly out of scope: finer-grained per-environment trust
  administrators would require a new backend permission, which owner Entry 2 style
  decisions reserve; if evidence later demonstrates need, that is a separate owner
  decision. Per-user self-enrollment of desktop Runners likewise stays out of scope.

## 7. Privilege-escalation analysis of key operations (owner condition 4)

Design-level argument, to be verified by the future test inventory and independent
review:

1. **Fixed authority surface:** every trust operation requires the `system_admin` flag;
   no operation path (including rotation, revocation, re-enrollment and recovery)
   consults, grants or revokes any role permission, receipt, policy version or
   delegation.
2. **Runner-side ceiling:** the Runner identity key performs exactly one cryptographic
   role (mTLS client authentication). It cannot sign job envelopes (§2.4), cannot modify
   its own bindings (Control-Plane authoritative), cannot re-enroll itself (ceremony
   requires an administrator), and cannot extend its own validity.
3. **Recovery cannot mint authorization:** revoke-then-re-enroll creates a new
   generation of the *same* identity record with the *same* zero authorization state; it
   does not inherit receipts, approvals or jobs.
4. **Revocation cannot be weaponized:** revoking an instance denies service to that
   instance only; it changes no other principal's permissions. Uncertain or partial
   revocation state denies both the target and the operation (fail closed).
5. **Admin-side ceiling:** a `system_admin` performing trust operations remains subject
   to existing audit, rate limits and the standing rule that administrators cannot
   invent backend privileges; these operations create none.
6. **Audit closure:** every trust operation, success or failure, is recorded (§10) under
   B7, attributed to the acting administrator, instance and reason, so escalation
   attempts are observable even when denied.

## 8. Key rotation and recovery procedures (DP-040, DP-041)

### 8.1 Planned rotation (measured, no invented interval)

Ordered procedure per instance, all states audited:

1. **Register next generation:** generate a new key pair in the keystore; submit the
   public key/fingerprint under the existing enrollment record; increment the generation
   counter in a pending state.
2. **Prove possession:** the Runner demonstrates possession of the new key (standard
   TLS proof-of-possession during a session authenticated by the old generation) before
   any cutover.
3. **Validate:** the Control Plane re-checks the full §2.2 binding set against the new
   generation.
4. **Cutover with bounded overlap:** the new generation becomes current; the old
   generation remains valid only for a bounded, measured transition window, then is
   revoked automatically. Overlap duration and the rotation interval itself are
   **【要決定】**: fixed from vetted standards plus measured operational data (DP-040),
   never assumed (Q7).
5. **Revoke old generation:** the old key becomes permanently invalid; stale-generation
   connections fail closed with an audited reason.

Properties: no key reuse across generations; no offline execution window; no grace
period after the overlap expires; interruption at any step leaves the previous
generation authoritative or leaves the instance without a valid key — never an
ambiguous dual-valid state beyond the measured window.

### 8.2 Revocation and revoke-then-re-enroll (loss/compromise)

1. **Revoke first:** on key loss, suspected compromise, host decommissioning or
   unexplained generation anomaly, the administrator immediately revokes the affected
   `(instance, generation)`. Revocation is authoritative in the Control Plane, takes
   effect at every live check with no offline grace, and denies new connections and
   jobs immediately.
2. **Job effects per ADR-0012 cancellation semantics:** queued jobs for that instance
   are canceled; running jobs are terminated or held — uncertain termination keeps the
   work fenced and held (DP-043a existing semantics); results are **not** released while
   status is uncertain; output release revalidation (step-2 E-checks) applies
   regardless of identity state.
3. **Then re-enroll:** a compromised-but-retained instance re-enrolls through the §5
   ceremony under the **same `runner_instance_id`** with an incremented generation,
   preserving the full audit lineage. The instance ID is not silently replaced: fresh
   IDs would erase lineage and are reserved for genuinely new installations.
4. **Never reuse key material:** the compromised generation's key is never valid again,
   including for re-enrollment; enrollment rejects its fingerprint permanently.

### 8.3 Recovery of interrupted operations

Interrupted rotation, uncertain key generation, issuer outage, stale clocks and partial
revocation leave an explicitly *held* audited state. Recovery authority is the §6
mapping. No automatic regeneration, no enrollment retry under a different identity, no
silent fallback to unauthenticated transport (step-3 §3.3 rule 6).

### 8.4 Issuer/anchor compromise (DP-043b)

1. Revoke **all** instances and generations (fail closed globally for Runner trust —
   this revokes transport trust only; it does not alter receipts, permissions or
   anything else).
2. Re-key the Control-Plane issuer; pin the new anchor.
3. Re-enroll every instance through the §5 ceremony.
4. Held-output disposition follows existing DP-043a cancellation/hold semantics: outputs
   remain held pending their own release gates; nothing is auto-released because trust
   was re-established. Retention/deletion of anything stays on its existing deferred
   track.

## 9. Compromise-response runbook (owner condition 5)

**Trigger classes:** confirmed key exfiltration, hostile-process access to the keystore,
binary/config integrity change (DP-053a invalidation), unexplained generation anomaly,
administrator-reported compromise, issuer compromise. **Standing rule:** detection
failure is not a design defense — the runbook is for cases that reach an administrator,
and the audit taxonomy (§10) is the detection surface.

| Phase | Actions | Trust-plane effects | Job/output effects |
|---|---|---|---|
| 1. Detect & record | Verify the report against audit evidence; open a response record with non-sensitive reason | None yet | None yet |
| 2. Contain | Revoke the affected `(instance, generation)` immediately (§8.2) | Connections and new jobs denied live; no grace | Queued jobs canceled; running jobs terminated or held; results held, never released on uncertain state |
| 3. Assess | Determine scope: one instance, several instances, or issuer; inspect Runner host binary/config per DP-053a rules; check for binding tampering | Additional revocations as evidence warrants; B6 unaffected (already blocking) | Held outputs remain held; no disposition decisions here |
| 4. Recover | For a retained host: inspect, re-image/re-verify if needed, then revoke-then-re-enroll under the same instance ID, new generation; for a retired host: revocation is final | Enrollment ceremony with full evidence (§5); lineage preserved | Held outputs re-enter their independent release gates only after the instance is re-enrolled and every other current gate passes |
| 5. Close | Record root cause, evidence references, and any process change in the audit trail; no silent fixes | Generation history preserved; old generations remain revoked | Release decisions remain independent of trust recovery success |

Runbook boundaries: response actions never change isolation profiles, never widen
network policy (any future connectivity is Entry 3 scope), never issue receipts, and
never bypass B6 or ADR-0012 gates. If response requires access to credential stores or
real data, stop and escalate — such access is not authorized.

## 10. Audit event taxonomy for trust operations (DP-043; B7)

All events carry: event class, timestamp (trusted source — **【要決定】**), acting
administrator ID, `runner_instance_id`, generation, key fingerprint (public identity
data only), platform profile, and outcome with a non-sensitive reason. Events are
append-only in the Control-Plane audit path; no private key bytes, no provider
credentials, no job payloads. Retention and audit-log protection are existing separate
gates (ADR-0012 B7 notes audit-log protection is unresolved) and are **【要決定】** if the
trust plane needs a stricter class.

| Event class | Meaning | Failure/fraud cases it must expose |
|---|---|---|
| `trust.enrollment.requested` | Pending enrollment created | Enrollment without authority (denied, still audited) |
| `trust.enrollment.challenge_issued` / `.expired` / `.replayed` | Challenge lifecycle | Replay attempts, challenge farming |
| `trust.enrollment.approved` / `.rejected` | Administrator decision | Approval of mismatched fingerprint; rejection without reason |
| `trust.enrollment.completed` | Certificate issued, bindings recorded | Duplicate instance ID/key; issuance outside §5 order |
| `trust.key.rotation.started` / `.possession_proven` / `.cutover_completed` / `.old_revoked` | §8.1 lifecycle | Overlap outside the measured window; cutover without possession proof |
| `trust.instance.revoked` | Per-instance/generation revocation with reason | Revocation storm, revocation of wrong instance |
| `trust.instance.re_enrolled` | Same-ID new generation after compromise (§8.2) | Lineage breaks, fingerprint reuse of a revoked generation |
| `trust.issuer.rekeyed` / `.anchor_pinned` | DP-043b recovery events | Uncoordinated issuer change |
| `trust.recovery.held` / `.completed` | Interrupted-operation hold/recovery | Silent auto-regeneration, retry-as-different-identity |
| `trust.access.denied` | Any trust operation outside the §6 mapping | Privilege-escalation attempts (§7.6) |
| `trust.transport.cert_status_stale` / `.authority_unavailable` | Fail-closed status resolution | Attempts to run jobs on stale/unknown trust state |

Taxonomy note: these event classes describe the trust plane only. Job-dispatch, receipt
and isolation events keep their own existing taxonomies; this design does not merge or
reclassify them.

## 11. Owner verification conditions — mapping and status

| # | Owner condition (Entry 5) | Design answer | Status |
|---|---|---|---|
| 1 | OS keystore availability per platform | §3 comparison (Windows CNG/NCrypt; Linux file-based under dedicated service account) | Specified; exact-build availability is a future demonstration (§3.2), not yet performed |
| 2 | Key/credential protection demonstration | §3.2 demonstration inventory + §3.3 residual-risk statements | Future, separately authorized evaluation; design claims stop at "specified" |
| 3 | RBAC mapping for enrollment/revocation authority | §6 mapping to existing `system_admin` authority; no new permission | Design complete; enforcement is future implementation work |
| 4 | No privilege escalation on update/revocation/recovery | §7 argument + §10 audit closure | Design-level argument; verified by future test inventory and independent review |
| 5 | Compromise-response procedures (job stop, result hold, re-enrollment) | §8.2 + §9 runbook, aligned to ADR-0012 cancellation semantics and DP-043a holds | Specified; runtime behavior is future implementation/testing |
| 6 | Cipher, key lifetime, rotation period from standard methods + measurements | §4.1/§12: methods fixed to vetted standards; all numeric values from standards + measurement | **【要決定】** per parameter (§12); no value invented |
| 7 | Independent review | Required before any implementation or activation of this design | **Not performed in this task** (task instructions prohibit subagent delegation); remains a pre-implementation gate, as in R-ISO-1 |

Conditions 1, 2, 4 and 5 are owner-required *verification obligations*: this document
supplies the procedures and criteria they will verify; it does not report them as
satisfied. No keystore probe, key generation, enrollment, or network connection was
performed for this documentation deliverable.

## 12. Parameter register — standard-method + measurement decisions

Every numeric/cryptographic parameter below is fixed only by the stated process: adopt
the current vetted standard unless measurement justifies deviation; record the
measurement and the standard citation with the decision. Owner condition 6 governs all
of them. **All are 【要決定】** and none may be inferred from this document, prior
proposals, CI, or development-loop values:

| Parameter | Set by | Notes |
|---|---|---|
| TLS version floor and cipher suites (both platforms) | Vetted platform-standard policy + measurement | §4.1; identical suite floor on Windows/Linux where stacks allow, otherwise the stricter common floor |
| Runner key algorithm and size | Vetted standard | Keystore-generatable on both platforms (§3) |
| Certificate/issuer key profile and validity | Vetted standard + measured rotation data | Validity need not equal rotation interval (§8.1) |
| Rotation interval and overlap window | Measurement (DP-040) | §8.1; single decision, both platforms |
| Enrollment challenge TTL and one-use window | Measured operational need | §5.1 |
| Revocation propagation / status SLA | Measurement | No offline grace regardless of value (§1.2) |
| Trusted time source and skew rule | Standard practice + measurement | Affects §8.1/§10 timestamps |
| Audit retention and protection class for trust events | Existing audit-protection track (ADR-0012 B7) + owner | §10 |
| Evidence freshness/expiry for §11 condition 2 results | Existing DP-053a binding rules + verifier appointment (separately 【要決定】 in the isolation track) | §3.2 |

## 13. Explicitly gated choices and non-claims

**Genuinely new owner choices opened by this design (【要決定】):** every parameter in
§12. Beyond §12, no new owner decision is opened: trust model, ceremony, RBAC mapping,
rotation/recovery procedures, runbook and audit taxonomy are design-complete under Entry
5's approval.

**Non-claims:** this document claims no keystore protection evidence, no enrollment
rehearsal, no TLS interoperability test, no RBAC enforcement test, no runbook exercise,
no audit record, and no activated Runner. It does not authorize: key generation, enrollment
execution, any network path or endpoint (Entry 3), provider credential supply (Entry 4),
dispatch or execution (B6), real data use, or production exposure. Isolation profiles
remain INACTIVE/UNVERIFIED independently of trust design.

## 14. Adversarial self-review

- **Trust-channel creep:** §4.2 describes mTLS conditional on Entry 3. It could be read
  as authorizing a Runner↔Control-Plane connection; the doc states repeatedly that
  topology/endpoints are separately gated and names none.
- **Enrollment-as-activation creep:** a certificate could be mistaken for permission to
  execute. §1.2.1, §5.3 and §11 state the independence of enrollment, B6, receipts and
  isolation evidence.
- **RBAC under-mapping risk:** mapping trust authority to `system_admin` is the
  narrowest existing authority; §6 rejects project-scoped roles and delegation paths.
  The residual risk — a single administrator can both enroll and revoke — is accepted by
  Entry 5's explicit non-requirement of quorum, and is audited (§7.6); introducing quorum
  without threat evidence would violate Entry 5.
- **Key reuse temptation:** reusing a compromised key after re-keying the OS account
  would be operationally convenient and would erase lineage; §8.2.4 rejects it.
  Same-ID re-enrollment is preserved deliberately for audit lineage; the doc resists the
  opposite convenience (fresh ID per compromise), which would hide recurrence.
- **DPAPI overreach:** Windows designs often reach for DPAPI; §3.1 rejects it as sole
  protection with the same-user-process rationale (T-I3's own lesson).
- **Linux overclaim:** the doc resists presenting Linux file-based custody as
  "keystore-protected" in the hardware sense; §3.3 states the narrower claim and defers
  residual-risk acceptance to the deployment class's activation decision.
- **Numeric creep:** §12 refuses every concrete value (TTLs, suites, intervals), per Q7
  and DP-040. The parameter register is a decision framework, not a decision.
- **Audit taxonomy scope creep:** §10 could be misread as defining audit for jobs or
  receipts; the closing note keeps taxonomies separate.
- **Verification-condition overclaim:** §11 marks conditions 1/2/4/5 as future
  verification, never as satisfied by authorship; condition 7 is explicitly not claimed.
- **Independent-review limitation:** as with R-ISO-1, the task prohibits subagent
  delegation, so no independent reviewer was invoked; required independent review remains
  a gate, not a pass recorded here.

## References

- [Owner formal decisions Entry 1–6](OWNER_DECISIONS_2026-11-10-ENTRIES.md) — Entry 5 (trust), Entry 3 (transport topology), Entry 1 (receipts), Entry 4 (credentials)
- [Owner formal decisions Q1–Q7](OWNER_DECISIONS_2026-11-09-EVENING.md)
- [Owner queue classification — Entry 5 cluster](OWNER_QUEUE_CLASSIFICATION_2026-11-09.md) (DP-035–041, DP-043b)
- [ADR-0012 — dual-plane model gate and Agent Runtime](../architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md)
- [ADR-0011 — model-facing zero-tool gate](../architecture/ADR-0011-model-facing-zero-tool-gate-proposal.md)
- [Hybrid isolation profiles](HYBRID_ISOLATION_PROFILES.md) and [engineering detail](HYBRID_ISOLATION_ENGINEERING_DETAIL.md)
- [Hybrid step-2 agent registry design](HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md) (E2/E4/E5) and [receipt contract](HYBRID_STEP2_RECEIPT_CONTRACT.md)
- [Hybrid step-3 isolation and trust proposals](HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md) §3–5
- [Hybrid Agent Runtime threat model](../security/HYBRID_AGENT_THREAT_MODEL.md) — T-S1, T-T1, T-I3
- [ADR-0010 — encrypted audit authentication cache](../architecture/ADR-0010-encrypted-audit-auth-proposal.md) (keystore-precedent caveat, §1.1 of step-3)
- `backend/app/service.py` — `ROLE_PERMISSIONS` and the `system_admin` flag (RBAC mapping source)
