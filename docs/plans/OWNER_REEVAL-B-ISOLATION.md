# Owner re-evaluation B — DP-024…053: isolation and Runner trust

**Basis:** the 2026-11-09 initial-design-first directive and `OWNER_REEVAL-GROUNDING.md`.
Recommendations only; this file does not alter the queue or authorize implementation,
credentials, dispatch, egress, Runner/isolation activation, real-data use, or production
exposure. Every DP remains 【要決定】 in the queue.

**Source distinction:** `PRODUCT_SPEC.md` Purpose/Core/MVP, `ARCHITECTURE.md`
Deployment/uploads, and the stable catalog establish the original research assistant,
local/private-network operation, ACLs, and local-only egress boundaries. They do not
specify a product Runner, VM-per-job, rootless containers, trust roots, signing
algorithms, or enrollment/rotation ceremonies. HBR-001…015 are additional owner-added
hybrid requirements in `locus-hybrid-agent-requirements.md` (catalog §E), not claims
that these technical choices were in the earlier Product Spec. Applicable mandatory
hybrid semantics are from accepted ADR-0012, especially B1–B7 and §4; nothing here
weakens them. ADR-0011's Plane-M zero-tool gate remains unchanged. For every entry:
**B6 dispatch rejection remains; no dispatch, Runner/isolation, credentials, or egress
is activated by this design recommendation.**

## Evaluations

### DP-024 — supported Windows editions and Runner targets
1. **初期設計要件IDと原典:** HBR-001/004 (owner-added hybrid requirements, Must #1/#4); original `PRODUCT_SPEC.md` Purpose/Core does not select an OS or edition.
2. **当初想定されていた動作:** usable local/Desktop and on-prem/server research workflows, within authorization and isolation policy; no universal Windows support promise.
3. **現在提示されている選択肢:** Desktop/Server targets are named; editions/features remain open; VM-first where supported and verifiable.
4. **初期設計に最も整合する推奨案:** publish only a small, explicitly tested Windows support set; enable a target only where the required OS-enforced boundary and isolation proof work. Do not require every edition to run VMs.
5. **自律性・利便性・安全性への影響:** practical tested Desktop and Server options support hybrid use; an unsupported platform remains unavailable, not host-executed. ADR-0011/0012 boundaries stay intact.
6. **推奨案を採用した場合の制約:** users need a supported OS/build; future platforms can be added through the same conformance contract.
7. **Ownerが新たに決定する必要がある事項:** initial support matrix and risk profile per target; not a decision on activation.
**フラグ:** 📈過剰設計疑 — requiring Hyper-V on every local Windows edition has no initial-design basis.
**境界:** Design only; B6 remains; no execution, isolation, credential, or egress activation.

### DP-025 — Windows isolation technology and lifecycle
1. **初期設計要件IDと原典:** HBR-004 (Must #4: OS/container enforcement); original `PRODUCT_SPEC.md` Core/MVP does not prescribe a sandbox technology.
2. **当初想定されていた動作:** authorized research/agent work remains usable across personal and server environments; no VM-per-job requirement.
3. **現在提示されている選択肢:** Job Objects; AppContainer/restricted token; Hyper-V Sandbox/disposable VM; Windows containers; VM-first proposal.
4. **初期設計に最も整合する推奨案:** phased, capability-tested isolation: a least-privilege native OS boundary plus process-tree containment and explicit filesystem/network restrictions may serve local use only if it passes HBR-004 tests; use disposable VMs where server threat/capacity profile justifies them. Job Objects alone are insufficient; never treat a Windows container label as proof.
5. **自律性・利便性・安全性への影響:** graded deployment preserves local/server choice without relaxing actual enforcement; no proof means no execution. Preserve B6 and both ADR gates.
6. **推奨案を採用した場合の制約:** each supported profile needs platform-specific proof and honest scope labels; stronger profiles remain extensible.
7. **Ownerが新たに決定する必要がある事項:** accepted local/server threat profiles and tested mechanisms; not permission to activate either.
**フラグ:** 📈過剰設計疑 — VM-per-job as the universal Windows minimum exceeds the functional requirement; no-VM execution must still meet HBR-004.
**境界:** Design only; B6 remains; no execution, isolation, credential, or egress activation.

### DP-026 — Windows image, transfer, and no-VM behavior
1. **初期設計要件IDと原典:** HBR-004/007 (Must #4/#7); `PRODUCT_SPEC.md` Core/Acceptance requires bounded safe uploads and authorized data paths, not a guest-image/broker architecture.
2. **当初想定されていた動作:** research inputs are scoped and access-controlled; a Runner must not escape its allowed workspace.
3. **現在提示されている選択肢:** image integrity, bounded transfer, shutdown/cleanup, broker; unavailable VM means unavailable execution unless a tested risk profile is explicitly accepted; no silent downgrade.
4. **初期設計に最も整合する推奨案:** transfer only the authorized job workspace through a narrow, bounded interface, using existing data-size/access rules and integrity verification; no user profile or unrestricted host mounts. If a verified OS-enforced profile is unavailable, reject execution. A VM is one profile, not the only possible profile.
5. **自律性・利便性・安全性への影響:** scoped transfer supports local work without broad host exposure; fail-closed behavior preserves B6 and ADR-0012 artifact/ACL checks.
6. **推奨案を採用した場合の制約:** no arbitrary host-path access; revalidate authorization and source ACL/classification at output release.
7. **Ownerが新たに決定する必要がある事項:** supported transfer profile and applicable existing size bounds; no new data-retention period inferred.
**フラグ:** ⚠根拠不足制約 — a dedicated broker and VM-image supply-chain process are implementation choices, not original requirements; 📈過剰設計疑 if mandated for every valid OS sandbox.
**境界:** Design only; B6 remains; no execution, isolation, credential, or egress activation.

### DP-027 — Linux platform support matrix
1. **初期設計要件IDと原典:** HBR-001/004 (hybrid selection and OS/container enforcement); original `PRODUCT_SPEC.md` and `ARCHITECTURE.md` choose no Linux distribution/kernel.
2. **当初想定されていた動作:** local/on-prem research operation, without a promise to support every distribution or kernel.
3. **現在提示されている選択肢:** supported distribution/kernel matrix is open; proposal gives VM-first direction.
4. **初期設計に最も整合する推奨案:** start with only the Linux host/kernel combinations that pass the required process, filesystem, network, and cleanup tests; expand by conformance, not a broad theoretical matrix.
5. **自律性・利便性・安全性への影響:** a small verified matrix is practical and extensible; unverified systems fail closed and do not weaken B6 or ADR-0012.
6. **推奨案を採用した場合の制約:** unsupported kernels cannot host execution until verified.
7. **Ownerが新たに決定する必要がある事項:** initial tested targets and minimum version/support policy.
**フラグ:** 📈過剰設計疑 — exhaustive distro/kernel coverage is not required by the initial design.
**境界:** Design only; B6 remains; no execution, isolation, credential, or egress activation.

### DP-028 — Linux VM/microVM technology
1. **初期設計要件IDと原典:** HBR-004 requires OS/container enforcement; no initial source requires a separate guest kernel.
2. **当初想定されていた動作:** isolated, authorized work on local and server targets, with implementation technology left replaceable.
3. **現在提示されている選択肢:** disposable hardware VM/microVM; exact technology/host support open; VM-first for untrusted work.
4. **初期設計に最も整合する推奨案:** treat VM/microVM as a stronger server profile where justified and verified, not a universal local prerequisite. A restricted rootless/container profile is acceptable only if it independently meets the approved threat profile and OS-enforcement tests; otherwise unavailable.
5. **自律性・利便性・安全性への影響:** graded but proven profiles avoid excluding typical local machines; no profile relaxes ADR-0011/0012 or B6.
6. **推奨案を採用した場合の制約:** VM-specific features cannot be assumed by all adapters; conformance separates profile capabilities.
7. **Ownerが新たに決定する必要がある事項:** whether the higher-risk server profile requires VM isolation and which tested platforms implement it.
**フラグ:** 📈過剰設計疑 — making VM/microVM mandatory for every local job is unsupported by the initial functional requirement.
**境界:** Design only; B6 remains; no execution, isolation, credential, or egress activation.

### DP-029 — Linux runtime restrictions and rootless OCI
1. **初期設計要件IDと原典:** HBR-004 (OS/container enforcement); original sources require no rootless runtime, namespaces, seccomp, LSM, or particular capability list.
2. **当初想定されていた動作:** enforce the allowed workspace/process/network boundary; remain replaceable as platforms evolve.
3. **現在提示されている選択肢:** namespaces/cgroups; rootless OCI plus seccomp/LSM; or VM/microVM with layered controls.
4. **初期設計に最も整合する推奨案:** select the smallest verified control set that enforces the approved boundary on the supported host. Require rootless OCI only if evidence shows it is needed for that profile; prohibit privileged mode, broad mounts, and host-control sockets as direct boundary safeguards.
5. **自律性・利便性・安全性への影響:** tested least privilege protects data without asserting a container equals a VM; B6 remains if a control is absent or uncertain.
6. **推奨案を採用した場合の制約:** each runtime/kernel update needs relevant regression evidence; future stronger layers remain addable.
7. **Ownerが新たに決定する必要がある事項:** the minimal per-platform control profile and acceptance evidence, not a rootless mandate by default.
**フラグ:** ⚠根拠不足制約 — rootless OCI as a universal product requirement is not in the initial design; 📈過剰設計疑 for VM + rootless + every named defense layer as an unconditional stack.
**境界:** Design only; B6 remains; no execution, isolation, credential, or egress activation.

### DP-030 — Linux virtualization fallback
1. **初期設計要件IDと原典:** HBR-004; ADR-0012 B6 requires fail-closed execution until isolation is verified; initial sources do not require virtualization specifically.
2. **当初想定されていた動作:** supported local/server execution only within a verified OS-enforced boundary; no host fallback.
3. **現在提示されている選択肢:** unavailable execution, or an explicitly accepted and tested namespace/container risk profile; no silent host downgrade.
4. **初期設計に最も整合する推奨案:** no host execution. If a non-VM profile meets the owner-approved HBR-004 acceptance evidence, use that profile; otherwise keep that target unavailable. Do not infer risk acceptance from technical availability.
5. **自律性・利便性・安全性への影響:** allows viable local isolation without pretending every host supports VMs; preserves B6 and no-egress defaults.
6. **推奨案を採用した場合の制約:** unsupported local environments cannot run jobs; adapter must disclose this rather than silently downgrade.
7. **Ownerが新たに決定する必要がある事項:** which tested non-VM profiles, if any, meet the approved threat profile.
**フラグ:** ⚠根拠不足制約 — an unconditional VM-only rule adds a technology constraint; accepting weaker isolation without proof would contradict HBR-004/B6.
**境界:** Design only; B6 remains; no execution, isolation, credential, or egress activation.

### DP-031 — Runner topology and Control-Plane reachability
1. **初期設計要件IDと原典:** HBR-001/007 and `locus-hybrid-agent-requirements.md` Architecture/Required #1/#7; `PRODUCT_SPEC.md` Core allows LAN/private access but does not define Runner topology.
2. **当初想定されていた動作:** authorized local or on-prem research service, not a publicly reachable Runner service.
3. **現在提示されている選択肢:** Server/Desktop ownership, local-only endpoint, reachability/firewall topology open; proposal says LAN-external Runner reachability is not approved.
4. **初期設計に最も整合する推奨案:** retain workspace-selectable Desktop/Server ownership; default-deny network paths and keep Runner↔Control-Plane traffic private and narrowly authenticated. No LAN-external Runner reachability.
5. **自律性・利便性・安全性への影響:** preserves local/server hybrid utility while respecting owner-recorded scope; no weakening of dual-plane or B6.
6. **推奨案を採用した場合の制約:** deployment must configure an exact private endpoint/firewall path; no public listener implied.
7. **Ownerが新たに決定する必要がある事項:** supported private topology and which endpoint binds to each workspace.
**フラグ:** なし（LAN-external reachability remains explicitly unapproved; not reopened here).
**境界:** Design only; B6 remains; no dispatch, Runner, network, or egress activation.

### DP-032 — Cross-boundary endpoint/protocol
1. **初期設計要件IDと原典:** HBR-002/007; hybrid requirements #2/#7 require policy-controlled network and authenticated Runner communications; `PRODUCT_SPEC.md` local-only mode requires no external egress.
2. **当初想定されていた動作:** private, local-first research and no external send absent explicit policy; no particular endpoint/protocol specified.
3. **現在提示されている選択肢:** exact approved Control-Plane endpoint/protocol only; topology open; unapproved destinations unreachable.
4. **初期設計に最も整合する推奨案:** default deny all network egress; if Runner transport is later authorized, permit only its exact private Control-Plane endpoint/protocol. Keep external provider destinations denied; the approved `allowlisted` placeholder remains non-operative.
5. **自律性・利便性・安全性への影響:** narrowly scoped control traffic can support hybrid operation without authorizing provider egress; preserve B6/ADR-0012 and Plane-M zero-tool gate.
6. **推奨案を採用した場合の制約:** no wildcard/private-subnet allow rule; connectivity depends on the exact approved deployment.
7. **Ownerが新たに決定する必要がある事項:** transport endpoint and protocol when separately authorized; no external-egress activation is implied.
**フラグ:** なし (default-deny/no-egress is grounded; the non-operative placeholder is already decided and not reopened).
**境界:** Design only; B6 remains; no dispatch, Runner, network, or egress activation.

### DP-033 — Host/guest broker, mounts, and bounded transfer
1. **初期設計要件IDと原典:** HBR-004/007/013 and `PRODUCT_SPEC.md` uploads/ACL acceptance; exact broker, bundle format, and host-path policy are not initial-design specifics.
2. **当初想定されていた動作:** research inputs and outputs remain workspace-authorized, bounded, and subject to live ACL/provenance checks.
3. **現在提示されている選択肢:** narrow broker and bounded bundles; no profile/credential directory/control socket/unrestricted path; fail closed if proof is absent.
4. **初期設計に最も整合する推奨案:** expose only files explicitly authorized for the job and a bounded result channel; prefer copy/contract transfer over broad host mounts. Preserve existing size and ACL rules; do not require a bespoke broker if a simpler tested interface provides the same boundary.
5. **自律性・利便性・安全性への影響:** scoped transfer keeps research workflow usable without granting general host access; ADR-0012 artifact and source checks remain mandatory.
6. **推奨案を採用した場合の制約:** no arbitrary path, profile, or socket access; outputs remain unavailable until policy/ACL/classification checks pass.
7. **Ownerが新たに決定する必要がある事項:** exact transfer mechanism and scope; no new size/retention limit inferred.
**フラグ:** ⚠根拠不足制約 — mandating a bespoke broker/guest architecture exceeds the functional requirement when a simpler verified transfer meets it; do not remove the underlying OS/ACL controls.
**境界:** Design only; B6 remains; no execution, isolation, credential, or egress activation.

### DP-034 — Provider authentication and consent
1. **初期設計要件IDと原典:** HBR-005 (owner-added hybrid Must #5); hybrid requirements #5 says use official login, credentials normally on user device, verify provider terms, and do not repurpose auth. Product spec alone has no Runner credential scheme.
2. **当初想定されていた動作:** optional adapters work only with supported, policy-authorized authentication; no Locus credential reuse or implicit provider send.
3. **現在提示されている選択肢:** brokered credentials only after proof/approval; otherwise adapter unavailable; no host-profile mapping or implicit reuse.
4. **初期設計に最も整合する推奨案:** default to no provider credential in a job. Evaluate each official CLI's supported user-device authentication; permit an adapter only through the official CLI and a verified operation-scoped mechanism that keeps raw credential bytes from the tool-executing process (ADR-0012 B5). If that cannot be proven, that adapter/platform remains unavailable. No Locus-side copy or credential repurposing.
5. **自律性・利便性・安全性への影響:** some adapters may remain unavailable, but users retain ordinary local workflows where safe; preserve no-egress, B6, and ADR-0011/0012.
6. **推奨案を採用した場合の制約:** provider auth is per-adapter and cannot be assumed from a registered credential-presence flag.
7. **Ownerが新たに決定する必要がある事項:** provider-specific auth/terms and any broker/consent mechanism; no credential scheme is approved here.
**フラグ:** ⚠根拠不足制約 — a particular non-exportable broker is not a baseline choice; it is one possible way to prove the device-credential boundary.
**境界:** Design only; B6 remains; no credential, provider, execution, or egress activation.

### DP-035 — Installation trust anchor and key layout
1. **初期設計要件IDと原典:** HBR-007 requires authenticated Runner communications; HBR-005 separates provider credentials. No initial source selects PKI, MAC, or root/subordinate keys.
2. **当初想定されていた動作:** identify authorized users and keep local/private services protected; hybrid Runner identity is an added owner requirement, with mechanism open.
3. **現在提示されている選択肢:** shared secret/MAC; TOFU pin; installation-specific asymmetric CA per Runner; enterprise PKI.
4. **初期設計に最も整合する推奨案:** for an authorized deployment, use the smallest standard asymmetric per-instance identity accepted by the Control Plane, protected by the platform OS keystore, with an authenticated server identity and revocation. Reuse deployment PKI if already available; otherwise avoid mandatory enterprise PKI and an offline-root/subordinate hierarchy unless deployment warrants it. Never reuse ADR-0009/0010 audit credentials.
5. **自律性・利便性・安全性への影響:** unique revocable identity supports Desktop and Server without shared-secret blast radius; no effect on model-facing tools or B6.
6. **推奨案を採用した場合の制約:** each instance must enroll and be individually revocable; transport identity is not job approval.
7. **Ownerが新たに決定する必要がある事項:** local trust-anchor and custody option suitable to deployment; no root key creation or credential deployment authorized.
**フラグ:** 📈過剰設計疑 — separate offline root + online subordinate PKI is not a universal initial requirement; ⚠根拠不足制約 — no source requires a dedicated CA service.
**境界:** Design only; B6 remains; no key provisioning, Runner, dispatch, or egress activation.

### DP-036 — Cryptographic algorithms, hardware, and quorum
1. **初期設計要件IDと原典:** HBR-007 authenticated communication; no initial requirement specifies algorithm, key length, HSM/TPM, or compromise quorum.
2. **当初想定されていた動作:** authenticated, revocable identity with secure communication; details intentionally open.
3. **現在提示されている選択肢:** algorithm/key length, hardware requirements, and quorum are unspecified.
4. **初期設計に最も整合する推奨案:** adopt the vetted platform TLS/crypto defaults and supported library profile at implementation time; do not invent custom crypto or mandate hardware/quorum absent a deployment threat analysis. Keep algorithms versioned/configurable for migration.
5. **自律性・利便性・安全性への影響:** avoids excluding ordinary local machines while retaining standard authenticated transport and replaceability; B6 remains independent.
6. **推奨案を採用した場合の制約:** actual values must be selected and reviewed before implementation/activation; this entry chooses none.
7. **Ownerが新たに決定する必要がある事項:** justified crypto profile and whether deployment-specific hardware/custody is needed.
**フラグ:** ⚠根拠不足制約 — mandatory hardware backing or multi-party quorum has no initial-design grounding; 📈過剰設計疑 for imposing both on all local and server deployments.
**境界:** Design only; B6 remains; no keys, credentials, Runner, or egress activation.

### DP-037 — Enterprise PKI availability
1. **初期設計要件IDと原典:** HBR-007; original design does not assume an enterprise PKI or device-management service.
2. **当初想定されていた動作:** private/on-premise operation must work without an unstated enterprise dependency.
3. **現在提示されている選択肢:** installation-specific trust anchor or enterprise PKI/device management.
4. **初期設計に最も整合する推奨案:** make enterprise PKI an optional integration when the deployment already has it; define a small standalone per-installation enrollment path otherwise. Keep protocol/provider interfaces extensible.
5. **自律性・利便性・安全性への影響:** avoids blocking individual/local deployments while allowing managed organizations to integrate existing controls; authenticated/revocable identity remains required by HBR-007.
6. **推奨案を採用した場合の制約:** local trust lifecycle may need separate operations where PKI is absent.
7. **Ownerが新たに決定する必要がある事項:** whether PKI exists in the intended deployment and whether reuse is in scope.
**フラグ:** ⚠根拠不足制約 — requiring enterprise PKI/device management would add an ungrounded dependency.
**境界:** Design only; B6 remains; no enrollment or runtime activation.

### DP-038 — Runner keystore, non-exportability, and attestation
1. **初期設計要件IDと原典:** HBR-007 (Runner identity); HBR-005 (provider credentials); initial design does not require TPM or device attestation.
2. **当初想定されていた動作:** local/server adapters are usable on supported hardware while identity remains distinct from provider/user credentials.
3. **現在提示されている選択肢:** OS/hardware-backed key store, optional attestation, or platform unavailable.
4. **初期設計に最も整合する推奨案:** store an instance key using the platform's protected OS keystore where available; do not expose it to job tools. Require hardware non-exportability/attestation only for a profile whose threat evidence demonstrates need. If software/OS protection cannot meet the selected profile, that profile stays unavailable.
5. **自律性・利便性・安全性への影響:** keeps common local machines viable without weakening verified access controls; distinct key material cannot substitute for Plane-M gate or job receipt.
6. **推奨案を採用した場合の制約:** assurance is platform-specific and must be stated honestly; no attestation claim absent verification.
7. **Ownerが新たに決定する必要がある事項:** minimum OS-keystore profile and any higher-assurance target class.
**フラグ:** ⚠根拠不足制約 — mandatory TPM/attestation/non-exportability on every device is not in the initial design; 📈過剰設計疑 for universal hardware gating.
**境界:** Design only; B6 remains; no keys, enrollment, execution, or egress activation.

### DP-039 — Runner enrollment authority and local confirmation
1. **初期設計要件IDと原典:** HBR-007 requires authenticated Runner connections; original `PRODUCT_SPEC.md` roles/Core provides admin authority but no Runner enrollment ceremony.
2. **当初想定されていた動作:** administrator controls system policy while users select allowed workspaces; no additional manual confirmation step specified.
3. **現在提示されている選択肢:** authenticated authorized administrator plus separate local confirmation; exact roles/channel open; one-use challenge/fingerprint binding recommended.
4. **初期設計に最も整合する推奨案:** use an authenticated administrator with authority for the deployment to approve a one-time challenge bound to the exact instance public key and record the enrollment. Require proof of possession and revocation; do not require a second local channel universally if the existing authenticated enrollment already proves identity.
5. **自律性・利便性・安全性への影響:** avoids repeated owner confirmation for ordinary operations while preventing self-asserted enrollment; preserves admin/user separation and B6.
6. **推奨案を採用した場合の制約:** initial enrollment remains an administrator action; user cannot widen workspace policy.
7. **Ownerが新たに決定する必要がある事項:** which existing admin role enrolls/revokes and whether a particular Desktop deployment needs a separate local check.
**フラグ:** ⚠根拠不足制約 — a mandatory second local confirmation channel per Runner is not grounded in the initial design and may obstruct enrollment.
**境界:** Design only; B6 remains; no enrollment, dispatch, or activation.

### DP-040 — Runner key/certificate lifetime and overlap
1. **初期設計要件IDと原典:** HBR-007 requires authenticated, revocable transport; no initial source specifies certificate lifetime or rotation interval.
2. **当初想定されていた動作:** a Runner can be disabled/revoked by policy; operational cadence is unspecified.
3. **現在提示されている選択肢:** bounded overlap; prove new-key possession before cutover and revoke old key; numeric intervals open.
4. **初期設計に最も整合する推奨案:** support per-instance renewal and immediate compromise revocation; prove possession before cutover, use only the minimum operational overlap, then reject the old key. Do not prescribe a universal calendar period without operational evidence.
5. **自律性・利便性・安全性への影響:** routine renewal need not interrupt all Runner instances; immediate revocation remains available; no offline grace or weakened B6.
6. **推奨案を採用した場合の制約:** renewal and compromise events need audit and recovery; each instance remains separately identifiable.
7. **Ownerが新たに決定する必要がある事項:** a justified renewal cadence and overlap for the actual deployment.
**フラグ:** ⚠根拠不足制約 — fixed numeric lifetimes/overlap have no initial-design basis.
**境界:** Design only; B6 remains; no credential rotation or runtime activation.

### DP-041 — Re-enrollment, identity, recovery, compromise
1. **初期設計要件IDと原典:** HBR-007 authenticated identity and HBR-006 audit (owner-added); original design does not specify reinstall recovery.
2. **当初想定されていた動作:** distinct authorized users/devices and auditable admin control; no hidden identity reuse requirement.
3. **現在提示されている選択肢:** auditable new instance on re-enrollment; detailed recovery authority open; never reuse identity/key to conceal compromise.
4. **初期設計に最も整合する推奨案:** revoke the old instance when its key is lost/compromised; create a new instance after the same authorized enrollment process, preserving an audit link to the superseded record. No silent key regeneration.
5. **自律性・利便性・安全性への影響:** recovery costs an admin step but prevents impersonation; personal workspace content remains governed by existing ACLs.
6. **推奨案を採用した場合の制約:** reinstall may require re-enrollment; old instance identity is not revived.
7. **Ownerが新たに決定する必要がある事項:** which existing administrator handles exceptional recovery and evidence retention, without creating a new organizational authority tier.
**フラグ:** なし (identity/accountability follow HBR-007; no extra recovery authority is proposed).
**境界:** Design only; B6 remains; no enrollment or runtime activation.

### DP-042 — Certificate status and revocation propagation
1. **初期設計要件IDと原典:** HBR-007 and ADR-0012 §4.1 require current authority/revocation checks; no initial source sets an SLA/cache duration.
2. **当初想定されていた動作:** revoked or unauthorized work must not execute; infrastructure details remain open.
3. **現在提示されている選択肢:** online active/revoked status; cache limits/SLA open; proposal says no offline execution grace and fail closed when status unavailable.
4. **初期設計に最も整合する推奨案:** query the authoritative current instance/job state at admission and immediately before execution, as ADR-0012 requires; when it cannot be established, reject. Reuse the same authority for identity revocation rather than adding a separate certificate-status service by default.
5. **自律性・利便性・安全性への影響:** online dependence may deny work during outage but prevents stale authorization; B6 and dispatch rejection stay intact.
6. **推奨案を採用した場合の制約:** offline execution is unavailable; no arbitrary freshness cache.
7. **Ownerが新たに決定する必要がある事項:** operational latency/availability target and any cache bound, not the mandatory fail-closed recheck.
**フラグ:** ⚠根拠不足制約 — separate status transport and numeric propagation SLA are not specified by the initial design; do not weaken ADR-0012 live checks.
**境界:** Design only; B6 remains; no dispatch, Runner, or egress activation.

### DP-043 — Queued/active work on revocation
1. **初期設計要件IDと原典:** HBR-014 and ADR-0012 “Owner decisions deliberately left open” already mandate cancellation/hold semantics; details are not open for weakening.
2. **当初想定されていた動作:** only currently authorized workspace operations may release outputs; explicit cancellation lifecycle is an owner-added hybrid boundary.
3. **現在提示されている選択肢:** cancel queued work; terminate or hold uncertain active work before output release; precise recovery/root-compromise handling open.
4. **初期設計に最も整合する推奨案:** apply ADR-0012: queued revocation prevents dispatch; active work stays held until confirmed termination; do not release results when state is uncertain. Preserve the mandatory semantics, leave mechanisms/limits to the implementation design.
5. **自律性・利便性・安全性への影響:** some results may be lost during uncertainty; no stale/revoked result bypasses ACL or policy; B6 remains.
6. **推奨案を採用した場合の制約:** capacity cannot be reused until termination confirmation; no new SLA is inferred.
7. **Ownerが新たに決定する必要がある事項:** recovery for a root compromise and operational termination mechanism; not whether required fail-closed semantics apply.
**フラグ:** なし (the safety semantics are already binding in ADR-0012; not reopened).
**境界:** Design only; B6 remains; no dispatch, execution, or result release activation.

### DP-044 — Job envelope encoding and schema migration
1. **初期設計要件IDと原典:** HBR-007/013 and ADR-0012 §§3–4 require authenticated communication, authoritative receipt, exact bindings, and reviewed contracts; encoding is unspecified.
2. **当初想定されていた動作:** only the Control Plane authorizes a current, properly bound operation; a particular envelope format is not an initial requirement.
3. **現在提示されている選択肢:** CP signature; online opaque ID; or signature plus online freshness/receipt/policy/revocation checks.
4. **初期設計に最も整合する推奨案:** since execution must recheck authoritative state online, use an opaque one-use job reference over authenticated transport to retrieve the closed, versioned authoritative contract and receipt; reject unknown schema versions. Add a CP signature only if a future offline/intermediary contract demonstrably needs it; no offline execution.
5. **自律性・利便性・安全性への影響:** one online authority avoids duplicating signing roots while retaining freshness and binding; does not change Plane-M or B6.
6. **推奨案を採用した場合の制約:** Runner availability depends on the CP; no signed offline job path.
7. **Ownerが新たに決定する必要がある事項:** serialization/schema version and API behavior; the mandatory ADR-0012 claims/rechecks are not optional.
**フラグ:** ⚠根拠不足制約 — separate job-signing infrastructure is not an initial requirement when online authoritative verification suffices; 📈過剰設計疑 for both signatures and online checks absent a stated need beyond ADR-0012.
**境界:** Design only; B6 remains; no dispatch, signing key, or runtime activation.

### DP-045 — Envelope/signature algorithms and key IDs
1. **初期設計要件IDと原典:** HBR-007/013; no initial-design ID specifies job-signature or digest algorithms.
2. **当初想定されていた動作:** authenticated, current job/policy decisions and integrity; no cryptographic format selected.
3. **現在提示されている選択肢:** algorithms, digest, key IDs, domain separation, and encoding remain open; reject unsupported/noncanonical forms if signatures are used.
4. **初期設計に最も整合する推奨案:** under DP-044's online-authority profile, do not add a second job-signature algorithm/key family by default; use vetted TLS integrity and a closed versioned schema. If a later design requires signatures, use a standard maintained profile selected and independently reviewed then.
5. **自律性・利便性・安全性への影響:** minimizes key and migration burden without replacing authoritative checks; zero-tool and B6 remain unchanged.
6. **推奨案を採用した場合の制約:** online-only; adding a signature later needs versioned review and migration.
7. **Ownerが新たに決定する必要がある事項:** no algorithm now; if a signature is later justified, select current cryptographic parameters before implementation.
**フラグ:** ⚠根拠不足制約 — fixed key algorithms/lengths and separate domain-signing rules are absent from initial requirements; 📈過剰設計疑 if added while online authenticated authority is sufficient.
**境界:** Design only; B6 remains; no key or dispatch activation.

### DP-046 — Job freshness, time, and clock skew
1. **初期設計要件IDと原典:** HBR-013/014 and ADR-0012 §4 require current receipt/revocation and deadlines; no initial source gives time source or numeric skew.
2. **当初想定されていた動作:** expired, stale, or unauthorized operations do not execute; no clock implementation prescribed.
3. **現在提示されている選択肢:** validity window, time authority and skew open; uncertain freshness fails closed.
4. **初期設計に最も整合する推奨案:** use the authoritative Control-Plane time/state for online validity checks and bounded job deadlines; do not grant local/offline grace. If a Runner-side clock comparison is needed, define tolerance from supported-platform measurements, not by guess.
5. **自律性・利便性・安全性への影響:** prevents stale work while avoiding a universal local clock assumption; B6 and ADR-0012 rechecks remain.
6. **推奨案を採用した場合の制約:** no execution when the authority or freshness is uncertain; duration remains a later measured setting.
7. **Ownerが新たに決定する必要がある事項:** actual deadline/expiry and any measured clock tolerance; no numeric value inferred.
**フラグ:** ⚠根拠不足制約 — a universal zero-skew or fixed validity interval is not grounded; fail-closed uncertainty itself remains mandatory.
**境界:** Design only; B6 remains; no dispatch or execution activation.

### DP-047 — Nonce/replay persistence
1. **初期設計要件IDと原典:** HBR-013 and ADR-0012 §4.1 require one authoritative job receipt and recheck; no nonce-retention duration is specified.
2. **当初想定されていた動作:** a job must not run twice or on another Runner after authorization; implementation details are open.
3. **現在提示されている選択肢:** unique nonce and persisted consumption; sequence/retention open; at most one execution begins across restart/retry/instances.
4. **初期設計に最も整合する推奨案:** use the authoritative CP job ID as the one-use idempotency/replay key, atomically mark admission/consumption there, and check it online before execution. Avoid a second distributed nonce store unless tests show the authority pattern insufficient.
5. **自律性・利便性・安全性への影響:** safe retries are identifiable without duplicating protocol state; unauthorized replays reject; B6 remains.
6. **推奨案を採用した場合の制約:** CP state must survive restart and preserve consumed status for the job's relevant lifetime.
7. **Ownerが新たに決定する必要がある事項:** minimal retention linked to job/receipt lifecycle; no sequence counter or extra time period inferred.
**フラグ:** 📈過剰設計疑 — a separate sequence service plus duplicate nonce ledger is unnecessary if the authoritative one-use job state is durable and tested.
**境界:** Design only; B6 remains; no dispatch or execution activation.

### DP-048 — Receipt API and exact bindings
1. **初期設計要件IDと原典:** HBR-013 and ADR-0012 §4.1 mandate current authoritative receipt bound to job, actor, workspace, exact policy version, adapter, destination, and operation; Runner identity is separately checked.
2. **当初想定されていた動作:** approval is job-specific and current at enqueue and immediately before execution; role/UI metadata alone never authorizes.
3. **現在提示されている選択肢:** receipt authority API and claim details open; queue lists required binding fields and live checks at both enforcement points.
4. **初期設計に最も整合する推奨案:** use the existing authoritative Control-Plane source as the single API/state authority; recheck every ADR-0012 binding plus exact enrolled Runner instance. Do not add a second issuer or infer permission from registration/policy alone.
5. **自律性・利便性・安全性への影響:** repeated online verification may reject on outage but preserves current authorization and separation; B6 remains mandatory.
6. **推奨案を採用した場合の制約:** no execution without reachable authority and exact match; Plane-M remains zero-tool.
7. **Ownerが新たに決定する必要がある事項:** concrete receipt endpoint/schema and its resolution of still-open ADR-0013 items; mandatory ADR-0012 semantics are not re-opened.
**フラグ:** なし (binding/recheck semantics are already mandatory; the API mechanism remains open).
**境界:** Design only; B6 remains; no dispatch, execution, or egress activation.

### DP-049 — Completion/result and artifact signing
1. **初期設計要件IDと原典:** HBR-013 and ADR-0012 §4.4 require artifact integrity/identity binding, source ACL/classification inheritance, and live revalidation; original Product Spec requires provenance/citations, not Runner signatures.
2. **当初想定されていた動作:** outputs remain attributable, integrity-checked, ACL/classification-filtered, and advisory; no artifact-signing key architecture specified.
3. **現在提示されている選択肢:** Runner-signed manifest proposed; key custody and version migration open; signature is not authorization/safety.
4. **初期設計に最も整合する推奨案:** bind a bounded result digest/manifest to the authenticated one-use job and enrolled instance, then verify it and revalidate live ACL/classification/source state before persistence/reuse/export/release. Use transport-authenticated provenance where sufficient; add a Runner manifest signature only if artifacts must be verified outside that channel.
5. **自律性・利便性・安全性への影響:** integrity and provenance can be checked without treating signature as approval; preserve ADR-0012 source revocation gates and B6.
6. **推奨案を採用した場合の制約:** a digest proves byte identity, not safe content, policy approval, or source access; independent checks stay mandatory.
7. **Ownerが新たに決定する必要がある事項:** artifact persistence/channel model and whether an additional signature is necessary; if so, key lifecycle and schema versioning.
**フラグ:** ⚠根拠不足制約 — a separate artifact-signing key and signing ceremony are not initial requirements; 📈過剰設計疑 if used while authenticated transport/job binding suffices.
**境界:** Design only; B6 remains; no artifact, execution, credential, or egress activation.

### DP-050 — Artifact and audit retention/deletion
1. **初期設計要件IDと原典:** DATA-005/015 and IAM-015/016; `PRODUCT_SPEC.md` requires deletion propagation and metadata-only audit, but no retention period; ADR-0012 §4.4 leaves artifact retention open.
2. **当初想定されていた動作:** deleted/revoked research sources and derived citations/results are inaccessible; retention and secure deletion require later policy.
3. **現在提示されている選択肢:** follow step-2 design; deletion/retention behavior remains open; revalidate live ACL/classification/source before release.
4. **初期設計に最も整合する推奨案:** inherit the source's existing ACL, deletion, and retention decision; keep only the minimum result/audit metadata needed for operation and accountability. Never release stale derivatives. Do not invent periods or imply secure erasure that is unverified.
5. **自律性・利便性・安全性への影響:** stale material remains hidden after revocation; retention decisions stay separate from agent execution approval; B6 remains.
6. **推奨案を採用した場合の制約:** results may become unavailable when source access is lost; retention/backup operations need evidence.
7. **Ownerが新たに決定する必要がある事項:** artifact/audit periods, backup, deletion and secure-erasure policy in their existing decision tracks.
**フラグ:** ⚠根拠不足制約 — any new fixed retention/deletion period is unsupported; do not treat an artifact as independent of its source ACL.
**境界:** Design only; B6 remains; no persistence, execution, or egress activation.

### DP-051 — Admission, deadlines, cancellation, and bounds
1. **初期設計要件IDと原典:** HBR-014 and ADR-0012 mandatory cancellation semantics; `UI-006` covers product queues, but no Runner numeric capacity targets exist in the initial design.
2. **当初想定されていた動作:** bounded useful research operations with cancellation and no capacity release until confirmed termination; mechanism/values open.
3. **現在提示されている選択肢:** bounded admission/deadline/cancellation guarantees; exact values and guarantees open; timeout/missing ACK holds capacity.
4. **初期設計に最も整合する推奨案:** reuse existing product admission concepts where separable, but implement Runner-specific limits rather than assuming the local-model slot governs it. Measure representative local and server loads before setting values; preserve ADR-0012 cancellation/race/termination semantics exactly.
5. **自律性・利便性・安全性への影響:** bounded work prevents runaway jobs while avoiding arbitrary capacity promises; cancellation cannot bypass B6 or release uncertain work.
6. **推奨案を採用した場合の制約:** a held job may reduce available capacity until safe settlement; users receive truthful status.
7. **Ownerが新たに決定する必要がある事項:** measured queue/deadline/concurrency numbers and cancellation actor/mechanism; not the accepted safety semantics.
**フラグ:** ⚠根拠不足制約 — arbitrary numeric limits or a second general scheduler are not in the initial design; per-Runner admission must still satisfy HBR-014.
**境界:** Design only; B6 remains; no dispatch, execution, or egress activation.

### DP-052 — Platform/adversarial test scope and thresholds
1. **初期設計要件IDと原典:** HBR-004/007/014, GOV-004, and ADR-0012 verification requirements; no source gives numeric thresholds or an exhaustive OS matrix.
2. **当初想定されていた動作:** research capabilities and security controls are evidenced before being claimed; tests are not runtime permission.
3. **現在提示されている選択肢:** exact platform/adversarial inventory and thresholds open; disposable synthetic tests with positive and negative controls proposed.
4. **初期設計に最も整合する推奨案:** for each claimed isolation profile, test actual filesystem/process/network denial, identity/credential separation, cancellation, startup failure, and positive controls on that exact supported host/build. Use synthetic data and a fresh independent security review. Add target platforms only with evidence.
5. **自律性・利便性・安全性への影響:** scope-specific proof supports credible local/server choices; no test pass automatically enables dispatch, egress, or real data.
6. **推奨案を採用した場合の制約:** evidence is valid only for its exact relevant binaries/configuration; changes require targeted re-verification.
7. **Ownerが新たに決定する必要がある事項:** supported target set and documented pass thresholds; unavailable checks stay blocked, never passed.
**フラグ:** 📈過剰設計疑 — exhaustive testing of every distro/host variant or invented universal numeric thresholds is not grounded; ⚠根拠不足制約 — a fixed evidence-expiry interval is likewise unspecified.
**境界:** Design only; B6 remains; tests/evidence do not authorize execution, egress, or activation.

### DP-053 — Evidence binding, reviewer, and activation authority
1. **初期設計要件IDと原典:** GOV-004/GOV-005 require evidence and proposal/permission separation; `DEVELOPMENT_POLICY.md` requires independent review for material security changes; ADR-0012 separates approval from activation.
2. **当初想定されていた動作:** changes are accepted only with verifiable scope/evidence; document approval alone never activates a safety boundary.
3. **現在提示されている選択肢:** evidence validity/binding, independent-verifier identity, and activation authority open; proposal says independently review exact configuration/evidence.
4. **初期設計に最も整合する推奨案:** bind proof to exact Runner build, OS/kernel/hypervisor/runtime, image/config, policy and test results; invalidate it after a relevant change. Require a fresh independent read-only security review and a separate explicit owner activation decision after every gate.
5. **自律性・利便性・安全性への影響:** evidence can be reused while its bound configuration is unchanged; no automatic approval, B6 bypass, or implied dispatch/egress.
6. **推奨案を採用した場合の制約:** relevant updates make prior proof stale; verification and activation remain separate events.
7. **Ownerが新たに決定する必要がある事項:** any numeric evidence-validity window and named deployment approver; independent review and separate activation remain grounded governance requirements.
**フラグ:** ⚠根拠不足制約 — a specific verifier identity scheme or fixed evidence expiry is not specified, although independent review itself is required.
**境界:** Design only; B6 remains; no activation, dispatch, isolation, credential, or egress permission.

## Adversarial self-review

- **Local practicality:** the VM-first proposal does not follow from the initial functional requirement. A graduated profile is recommended, but only profiles that demonstrably enforce HBR-004 may run; “local” is not permission to use a host fallback. VM-per-job remains a possible stronger deployment choice, not a default for typical Desktop machines.
- **Server strength:** a server may choose a disposable VM profile for its threat model, but no extra VM/container/PKI layers are made universal. The same policy, job, ACL, classification, audit, and cancellation contracts apply across profiles.
- **Boundaries:** none of these recommendations changes ADR-0011 zero-tool behavior, ADR-0012's dual-plane/B6/B7/approval and artifact rules, or default-deny external egress. Runner↔Control-Plane connectivity is not external provider permission. No activation is authorized.
- **Trust-root minimality:** ADR-0009/0010 concern a dedicated audit worker and its authentication cache, not general Runner identity. Their separation lessons do not justify copying their accounts, cache, service, or a full CA hierarchy into the product Runner.
- **Residual decisions:** platform risk profiles, exact endpoint/transport, trust/enrollment and crypto details, provider-specific credential feasibility, numerical freshness/admission/retention limits, and evidence windows remain owner-decidable because the initial sources do not specify them. Resolved owner decisions and ADR-0012 mandatory semantics are not reopened.
