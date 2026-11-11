# Independent review — Hybrid design packages and UI research

**Review scope:** `HYBRID_RUNNER_TRUST_DESIGN.md`, `HYBRID_RUNNER_COMMUNICATION_DESIGN.md`, `HYBRID_AGENT_ADAPTER_DESIGN.md`, and `UI_OPENCODE_RESEARCH.md`, checked against Owner Decisions Entry 1–6 and Q1–Q7, ADR-0011/0012/0013, B6, E1/E2, fail-closed/no-egress constraints, the approved UI baseline, and the assigned review brief.

**Line references:** 1-based line numbers in the reviewed documents at the reviewed worktree HEAD. The report is a documentation review only; no key, Runner, provider credential, network endpoint, dispatch path, or UI feature was activated or exercised.

## Summary verdicts

| Document | Verdict | Summary |
|---|---|---|
| `docs/plans/HYBRID_RUNNER_TRUST_DESIGN.md` | **findings** | The Linux file-backed key is not the Entry 5 OS-keystore design and cannot support the claimed same-identity denial; technical measurement decisions are incorrectly classified as owner decisions. |
| `docs/plans/HYBRID_RUNNER_COMMUNICATION_DESIGN.md` | **pass** | Candidate endpoints/ports remain design-only, default-deny, individually gated, and separate from operational activation. No communication permission is granted. |
| `docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md` | **findings** | Direct-login wording is too operational for the current no-login decision; BR-3's same-identity access claim is contradictory; stub tests cannot establish real CLI isolation. |
| `docs/plans/UI_OPENCODE_RESEARCH.md` | **pass** | The baseline and React approach are preserved; §7.1 approved work is separated from §7.2 owner decisions; server-side authorization is explicitly required. |

## Findings

### 1. `docs/plans/HYBRID_RUNNER_TRUST_DESIGN.md` — findings

#### HIGH — TRUST-01: Linux private-key file does not satisfy the approved OS-keystore design or the stated access-denial test

**Location:** lines 144–150, 157–163, 431.

The Linux primary candidate is explicitly a PKCS#8/PEM file protected by filesystem mode/ownership (lines 144–147), but the document presents this as the Linux answer to Entry 5's OS-keystore-protected identity (line 431). A `0600` file is not an OS keystore. More importantly, ordinary file permissions grant access by UID: if the CLI/adapter or tool-executing process runs as the dedicated service UID, the file permissions do not distinguish those processes. The table's assertion that the file protects against the job and tool-executing process (line 150) therefore conflicts with its own required denial matrix (lines 157–163) unless a separate, specified process/operation-scoped mechanism exists. The document also acknowledges root can export the key, but that does not resolve the same-UID case.

**Evidence / impact:** Entry 5 requires OS-keystore-protected per-instance identity and verification of key protection; trust design §3.2 requires denial of access/use to the tool-executing adapter process. Communication design line 61 likewise requires proving that no key bytes leave the OS keystore. As written, the Linux path does not meet those requirements and the shared Runner model cannot rely on its asserted protection.

**Recommended action:** Replace the Linux candidate with an actual supported OS-keystore/key-operation design that can meet the required process boundary, or mark Linux enrollment unavailable until a separately identified mechanism passes exact-build positive/negative tests. Do not call a permissions-restricted private-key file an OS-keystore substitute or claim it denies access to same-UID processes.

#### MEDIUM — TRUST-02: Engineering parameters are incorrectly marked as owner decisions

**Location:** lines 446–460, 466–469; especially 449 and 466–469.

The parameter register says **all** listed values are `【要決定】` and later calls every §12 item a new owner choice. Entry 5 condition 6 instead requires cryptographic choices, key lifetime, and rotation period to be settled by standard methods plus verification/measurement. Owner §8 directs technical details to be resolved through verification and independent review within the approved scope. The actual numeric values are not yet established, but their absence does not by itself make each one an owner decision. The document also places items with existing separate governance (for example audit retention/protection, line 461) in the same blanket category.

**Evidence / impact:** This misstates the decision authority and may unnecessarily block technical verification or re-ask the owner for a decision already authorized as an evidence-based engineering detail. It also weakens traceability between Entry 5's seven verification conditions and the parameter register.

**Recommended action:** Label standard/measurement-derived parameters as engineering decisions awaiting their specified evidence, not `【要決定】`; keep explicit owner/activation gates only for genuinely owner-controlled items such as the existing audit-protection/retention track and separately recorded activation authority. Preserve the requirement not to invent values before measurement.

### 2. `docs/plans/HYBRID_RUNNER_COMMUNICATION_DESIGN.md` — pass

No findings. This review treats the endpoint and port values as candidates, not grants of access:

- Lines 3, 9–11 state no endpoint is verified/approved/configured/activated and preserve default deny.
- Lines 41–44 keep the exact LAN identity, enrollment bootstrap, conditional DNS, and remote operation gated.
- Lines 57–67 identify TCP/443 (and conditional DNS/53) as proposed values only; explicitly state no listener/port opening is authorized and prohibit silent substitution.
- Lines 69–79 require, per endpoint, design, isolated verification, independent review, separate Owner approval, then a distinct operational activation authorization.
- B6 and job-sandbox no-network constraints remain explicit (lines 9–11, 37, 62, 81 onward). The document distinguishes host control-channel design from job egress, does not create an implicit LAN/provider exception, and preserves fail-closed behavior.

**Cross-document qualification:** The proposed Linux trust candidate in TRUST-01 prevents its evidence requirement at communication-design line 61 (“no key bytes leave the OS keystore”) from being met as written. This is a trust-design defect, not authorization granted by the communication document; communication remains inactive until corrected and separately approved.

### 3. `docs/plans/HYBRID_AGENT_ADAPTER_DESIGN.md` — findings

#### HIGH — ADAPTER-01: Option 1 describes an actual provider login as an operator action despite the current prohibition

**Location:** lines 141–149, particularly 143–149; compare lines 30–32, 168–172, and 715–729.

Option 1 states, in present operational language, “The operator performs” the provider CLI login and the CLI then reads the credential store at each job. Entry 4 explicitly does not approve actual account login, credential read, transfer, or supply; the document itself repeats that restriction in §1.1 and §12. The later caveat at lines 168–172 does not fully cure the action-like architecture wording.

**Evidence / impact:** The requested review rule treats any sentence readable as granting credential or activation authority as HIGH. A reader could use lines 143–149 as instructions to provision a real account on a Runner, contrary to Entry 4 and the package's own activation gates.

**Recommended action:** Recast this as a strictly hypothetical post-approval design (e.g. “would require a separately approved login and credential-supply decision; neither is authorized now”), and place the current no-login/no-credential-supply restriction directly alongside the option's title/architecture. Do not provide imperative operational steps for login in this design-only package.

#### HIGH — ADAPTER-02: BR-3 cannot enforce denial by OS identity when CLI and tool process share that identity

**Location:** lines 176–182, 193–198, 514–524; especially 523–524.

The document says BR-3 can deny credential access to the tool-executing process through the OS keystore, then states the keystore boundary is per-OS-identity and the CLI and dedicated Runner identity must be the same identity (lines 523–524). Earlier it identifies the CLI's children as tool-executing processes and states they normally share the CLI's principal (lines 82–104). An identity-based keystore ACL that allows the CLI's principal also allows a hostile child running as that same principal; it cannot provide the claimed per-process denial. This also conflicts with the requested negative test against the tool process at lines 516–519.

**Evidence / impact:** The design calls BR-3 the only broker sub-architecture that could meet the non-exportable-bytes requirement (lines 193–198), which is not established under the described identity model. It could lead to false acceptance of a credential boundary that exposes credential use/read capability to the tool process, contrary to the step-2 credential-separation requirement and Entry 4's reject-if-unproven rule.

**Recommended action:** Do not characterize BR-3 as sufficient on identity ACLs alone. Specify a genuinely operation-scoped mechanism that separates the CLI's credential operation from the tool process, or reject that adapter/platform. Require evidence for the actual pinned CLI and OS boundary before asserting BR-3 viability; keep it unselected and unavailable absent evidence and the required independent review/separate Owner approval.

#### MEDIUM — ADAPTER-03: Stub-only tests do not establish the real CLI's sandbox or credential boundary

**Location:** lines 613–640, 646–657, 661–671.

The verification plan defines fake CLI and fake tool binaries (lines 620–630), then uses them to claim “CLI can authenticate” and “CLI's own sandbox denies the credential store” (VT-1/VT-4, lines 636–640). A stub can test the harness or a chosen OS ACL, but cannot demonstrate the pinned official CLI's actual sandbox, store access, token lifecycle, or process-memory boundary. The evidence section then requires pinned CLI/version evidence (lines 661–671), which the listed stub-only fixture cannot supply.

**Evidence / impact:** This makes key acceptance claims untestable by the prescribed plan and risks treating fixture behavior as vendor CLI evidence. The document correctly says no real-account login and synthetic data only; that does not require treating a stub as proof of the official CLI.

**Recommended action:** Separate harness/contract tests using stubs from platform/adapter tests. Define how, after the required separate authorization and in an isolated synthetic environment, the pinned official CLI and actual OS boundary are assessed without real accounts or provider egress. Until such evidence is permitted and produced, mark adapter credential-boundary claims unverified and the adapter unavailable.

### 4. `docs/plans/UI_OPENCODE_RESEARCH.md` — pass

No findings. The package correctly:

- Preserves the selected baseline appearance/interactions and existing React structure (lines 46, 60–63; §3.1 at lines 87 onward), and explicitly adapts OpenCode patterns rather than migrating the application to SolidJS (lines 46, 244–245).
- Separates the approved-scope implementation list in §7.1 (lines 218–224) from the owner-decision list in §7.2 (lines 226–233). In particular, history-sidebar expansion is identified as a baseline deviation (lines 55, 228), while streaming, session model switching, tool loops, loop-state exposure and upload-progress API remain out of scope pending decisions.
- Makes backend authorization mandatory for the proposed admin loop-state endpoint (lines 147–151) and restates that requirement in the general authorization section (lines 162–165, 200). The actual existing admin route guards also check `system_admin` server-side (`backend/app/main.py`, lines 530–562); the proposal does not rely on UI visibility alone.

The distinction between UI affordance hiding and server authorization is substantively clear in context: the UI may hide controls, but the server must authorize access. No execution, communication, credential, or activation authority is implied.

## Cross-document consistency and safety review

- **Runner model:** Trust, communication, and adapter designs consistently distinguish Control Plane from Runner/Plane R and preserve Plane M's zero-tool boundary. Communication keeps the job sandbox without network; its host-side channel remains a future exact-endpoint exception only after independent gates. Trust's Linux file-key proposal is the material cross-document inconsistency because the other packages require an OS-keystore-backed identity and process-denial evidence.
- **B6 / E1 / E2 / fail-closed:** All packages retain the explicit B6 dispatch rejection and do not treat enrollment, transport authentication, credential presence, or a receipt as execution permission. E1/E2 and current-state/revocation checks are described as independent gates. No finding concludes that these documents activate execution.
- **No-egress:** The communication design retains default-deny and no job egress. The adapter design makes provider endpoints a separate approval and blocks adapters without approved egress. Local-model communication is still subject to Entry 3 endpoint enumeration. No implicit external endpoint authorization was found.
- **Credentials:** Adapter design repeats no credential bytes in job inputs, receipts, audit logs, or model context and bars real credential use in this work. ADAPTER-01 is a wording/authority ambiguity; ADAPTER-02/03 are substantive proof/design gaps. No credential material was accessed.
- **Owner markers:** Trust §12 overuses `【要決定】` for measurement/standard-based engineering parameters (TRUST-02). Communication's endpoint identity/bootstrap and conditional resolver markers remain appropriate. Adapter's broker adoption, adapter activation, provider egress, and actual credential supply remain separately gated. UI §7.2 markers correctly denote scope/backend changes not authorized by the baseline or the cited Entry 6.

## Consolidated conclusion

The communication and UI packages pass this review. The trust package needs correction before its Linux trust design can be relied upon, and its measured parameters must be classified consistently with Entry 5. The adapter package has two HIGH findings: operational login wording that could be read as granting prohibited authority, and an OS-identity design that cannot substantiate its claimed broker isolation; its stub-only verification plan is also insufficient for vendor-specific claims.

**Do not use the current Linux key-custody proposal or BR-3 claim as evidence of a verified credential/key boundary.** Keep all Runner enrollment, network communication, provider login/credential supply, dispatch, execution, profile activation, and production use inactive. This review is not an Owner decision or an activation approval. Findings require implementer correction and any required independent re-review before the corresponding later gate; the communication/UI pass verdicts do not certify implementation or runtime behavior.
