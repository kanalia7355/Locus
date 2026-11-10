# Hybrid agent adapter design — official CLI authentication and credential supply

**Status: design and verification plan only.** This document records the
P4-ADAPTER research/design output for the owner-approved Entry 4
(`docs/plans/OWNER_DECISIONS_2026-11-10-ENTRIES.md`, Entry 4 — DP-034b) and the
Q4 direction (`docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md`, Q4). It
approves **no** adapter activation, no credential read, no credential transfer,
no credential supply, no provider login, no external communication, and no
B6 dispatch. Every activation step remains a separate, audited, evidence-based
Owner decision, exactly as required by ADR-0012
(`docs/architecture/decisions/0012-dual-plane-model-gate-agent-runtime.md`) and
the step-2 design (`docs/plans/HYBRID_STEP2_AGENT_REGISTRY_DESIGN.md`, §2.4–2.5).

## 1. Authority, scope and fixed safety boundaries

### 1.1 What the owner approved (Entry 4 + Q4)

- **Preferred:** officially supported CLI / existing login methods (Codex CLI,
  Claude Code, etc.). Existing subscription usage is used where the provider
  officially permits it. API-key-only is not forced as the sole method.
- **Per-adapter verification required:** authentication method, terms of use,
  isolated-environment behavior, and credential protection method.
- **Broker-mediated supply:** design and compare; adoption requires
  verification evidence + independent review + a **separate** Owner approval.
- **Separation:** credential bytes must never enter job inputs, receipts, audit
  logs, or model context.
- **Reject:** adapters where safe credential supply cannot be demonstrated are
  rejected for that environment.
- **Prohibited:** unofficial auth circumvention and subscription-limit bypass.
- **Scope:** this decision approves the **design and verification** of
  credential supply methods. It does **not** approve actual account login,
  credential read, credential transfer, or credential supply.

### 1.2 Non-negotiable boundaries in this document

1. **No credential bytes anywhere in Locus.** Job inputs, receipts, audit
   logs, and model context never contain credential material. The registry
   records only presence/absence state (`adapter_credentials.state`), never a
   value (step-2 design §2.4). The accepted C-min model gate never reads
   credential stores, exports tokens, or calls login/refresh APIs — this
   document does not amend that clause.
2. **No repurposing.** Provider credentials are never Locus session material,
   never API-key substitutes, never shared into the ADR-0010 audit path.
3. **No unofficial circumvention.** No unofficial auth bypass, no
   subscription-limit circumvention, no undocumented or modified CLI binaries,
   no proxying that impersonates the provider, no scraping of undocumented
   endpoints. Only officially supported methods and documented CLI flags are
   considered.
4. **No egress approval.** This document does not approve any network
   destination. The CLI's own provider endpoint (e.g. `api.openai.com`,
   `api.anthropic.com`, ChatGPT backend endpoints) is a **separate** egress
   approval that must be enumerated per endpoint, per Entry 3's rule that no
   implicit allowance for provider-API communication exists. Credential supply
   and provider egress are **two independent gates**; both must pass before any
   provider-authenticated adapter is dispatchable.
5. **Fail-closed.** If the isolated environment, the credential boundary, or
   the provider-egress boundary cannot be verified, the adapter stays
   unavailable. There is no host fallback, and no downgrade of isolation
   (Q3, step-3 design §1.2). B6 remains in force: a Runner present, a registry
   entry, or this document's approval is not activation authority.
6. **Design-only.** No credential read, no credential transfer, no provider
   login, no real credential bytes anywhere in this work, and no execution of
   any provider-authenticated CLI. Verification runs use mock/stub credentials
   and stub CLI binaries only (§9).

## 2. Research method and evidence provenance

**Honesty note.** This work was performed in a no-egress environment; no
official documentation site was fetched, and no provider CLI was executed
against real accounts. All vendor claims below are recorded from the
implementer's knowledge of the official CLIs and their public documentation and
are **unverified in this environment**. Every vendor claim is therefore marked
with a verification requirement (§5.1–5.4 and §9), and **no adapter may be
enabled on the basis of this document alone**. The verification evidence
receipts required by step-2 §2.4 ("registry cannot enable an adapter without a
recorded verification receipt") must be produced against the pinned CLI
version, the pinned OS build, and the approved isolation profile, and they
expire or become stale after any change.

Terminology used throughout:

- **CLI process** — the official provider CLI (or its agent runtime) that must
  possess the credential to make its provider request.
- **Tool-executing process** — any child process the CLI spawns to execute
  tools in the workspace. A compromised tool-executing process is the primary
  threat to the credential (threat model T-E3/T-E4).
- **Credential store** — the CLI's own supported credential storage on its
  device (e.g. its config/auth file, OS keyring, or an OS keystore the CLI
  officially supports).
- **Dedicated runner identity** — the enrolled, per-instance OS principal a
  runner job executes under (step-2 design §2.1; Entry 5 trust design).
- **Positive / negative test** — a positive test shows the intended
  authentication operation works; a negative test shows the credential is
  denied to the Control Plane, the interactive user, other runner instances,
  and the tool-executing process (step-2 design §2.5).

## 3. The credential supply problem, stated precisely

The official CLI must authenticate, and the tool-executing process must not be
able to obtain credential bytes. Both requirements are hard:

- The CLI process and its tool-executing children normally share the same OS
  principal. If the CLI reads its credential store from a file, the store is
  usually readable by the children too.
- The CLI's own sandbox (e.g. its built-in filesystem/network sandboxing) may
  deny the tool-executing process access to the credential directory — but
  Locus must treat the CLI's sandbox as an **unverified** boundary until the
  per-adapter verification proves it (OS-level evidence, not a flag).
- The owner's design requirement (step-2 §2.4) is: the selected OS mechanism
  must provide a non-exportable, operation-scoped integration that denies
  credential read/export to the tool-executing process while allowing only the
  official CLI authentication operation. If the official CLI requires exposing
  exportable secret bytes to the tool-executing process's identity, that
  platform/adapter is **not activatable**.

Therefore the design must be evaluated per adapter per platform, and the
default is **no-supply** (Option 0) until a per-adapter verification passes.

## 4. Credential supply design options

### 4.1 Option 0 — no-supply (local models only; default, safest)

**Architecture.** The adapter runs entirely against local LLM runtimes (e.g.
Ollama, LM Studio, llama.cpp) with no provider credentials at all. No provider
credential exists in the runner environment, so there is nothing to protect:
no credential bytes can leak into job inputs, receipts, audit logs, or model
context, and no provider egress is needed.

**Properties.**

- No credential exposure at all; no credential bytes exist in the environment.
- No provider egress approval required (local model inference is a LAN-internal
  service, which is still subject to the Entry 3 endpoint enumeration).
- No subscription terms to verify (local model licenses are separate).
- Model quality/capability is bounded by the local model; local-LLM adapter
  conformance is a separate conformance item (実装順 5, step-2 design).

**Status:** this is the **default** for any adapter until a credential supply
method passes verification for that adapter + platform.

### 4.2 Option 1 — per-adapter direct (CLI-native login, CLI's own store)

**Architecture.** The operator performs the provider's official CLI login once
on the runner device, in the dedicated runner identity's profile, using the
CLI's official login command (e.g. `codex login`, `claude login`, `gemini`).
The CLI stores its credential in its own supported store in that profile. The
CLI then reads its own store natively at each job. Locus never touches the
credential: no read, no transfer, no copy, no vault entry. The registry records
only presence/absence state.

**Security analysis.**

- The credential never leaves the CLI's own store; Locus processes never see
  credential bytes by construction.
- **The open risk is the tool-executing process.** If the CLI and its children
  share the dedicated runner identity, the children can read the same store
  unless the CLI's own sandbox denies it, or the store is protected by an OS
  mechanism the tool-executing process cannot access. The per-adapter
  verification (§5.1–5.4, §9) must prove, at the OS level, that the
  tool-executing process cannot read/export the credential:
  - positive test: the CLI can authenticate in the dedicated runner identity;
  - negative test: the tool-executing process (and any other identity) cannot
    read the credential store, the process environment, or the CLI's memory.
- If the CLI's sandbox cannot be proven to deny the credential store to the
  tool-executing process, and no OS mechanism can provide the denial, the
  adapter is **rejected for that platform** (per Entry 4's reject rule).

**Status:** this is the **preferred** option per Q4 (official CLI login, no
Locus-side credential machinery). It is only viable where the per-adapter
verification proves the credential-store denial boundary. This document does
not perform the login itself — the actual login is an activation step that
requires separate Owner approval.

### 4.3 Option 2 — broker-mediated supply (design + comparison only)

**Architecture.** A credential broker service — a separate OS identity that
holds or manages the CLI's credential material in a dedicated OS keystore —
provides the CLI's authentication operation to the CLI process without exposing
credential bytes to the runner, the tool-executing process, the Control Plane,
or the operator. The broker is a new, separately approved component; its
adoption requires verification evidence + independent review + a **separate**
Owner approval, per Entry 4.

**Broker sub-architectures compared in §7:**

| ID | Broker architecture | Summary |
|----|---------------------|---------|
| BR-1 | CLI-store broker | Broker materializes the CLI's own credential artifact into the CLI's expected store path, with OS ACLs, so the CLI reads natively. |
| BR-2 | Short-lived credential file injection | Broker materializes a per-job, short-lived credential file into the CLI's expected path, then removes it. |
| BR-3 | OS-keystore broker | Broker uses an OS keystore (Windows Credential Manager, macOS Keychain, Linux secret service) that the CLI officially supports, so no file bytes are involved. |
| BR-4 | Local proxy/token broker | Broker acts as a local endpoint that the CLI authenticates through. |

**Status:** BR-3 is the only sub-architecture that could satisfy the
non-exportable-bytes requirement without relying on the CLI's own sandbox; BR-1
and BR-2 still expose bytes to the tool-executing process unless the CLI's
sandbox denies access; BR-4 requires unofficial modification of the CLI and is
**rejected** by Q4. Broker adoption requires its own approval and is not
selected by this document (§7).

### 4.4 Rejected options

| Option | Why rejected |
|--------|--------------|
| Locus-side credential vault that stores provider credentials | Violates "No Locus-side copy" (step-2 §2.4); duplicates the credential's exposure surface; Locus already accepted the OS-vault-only stance for its own audit-worker cache (`loop_engine/app_credentials.py`, ADR-0010), which is not provider credential storage. |
| Passing API keys as job environment variables / CLI flags | Puts credential bytes into the job's process environment; the tool-executing process can read them; the bytes also risk appearing in job inputs, receipts, and logs. Fails the separation rule. |
| Proxying the provider's API through Locus, or injecting credentials into the CLI's HTTP requests | Requires unofficial modification of the CLI's client behavior or an undocumented endpoint; prohibited by Q4 (no unofficial circumvention). |
| Reusing the user's interactive-session credential store | Violates the identity separation rule (step-2 §2.4: the dedicated runner identity may not read the interactive user's store); the runner is not the user's session. |
| Undocumented CLI flags, modified binaries, or scraping undocumented endpoints | Prohibited by Q4 (no unofficial circumvention). |

## 5. Per-adapter research

> **Evidence provenance.** All claims below are recorded from the
> implementer's knowledge of the official CLIs and their public documentation,
> and are **unverified in this environment**. Every claim is marked with a
> verification requirement that must be satisfied before any adapter is
> enabled. No vendor term is accepted as fact; the verification evidence
> receipt is the authority.

### 5.1 Codex CLI (OpenAI)

**Official auth methods (knowledge-recorded).**

- `codex login` — the official ChatGPT sign-in flow (browser OAuth). The CLI
  stores its OAuth tokens in its own config/auth directory (e.g. `~/.codex/`
  with a `auth.json` file, filesystem permissions intended to be user-only).
- `codex login --api-key` / `OPENAI_API_KEY` — the official API-key method.
- `codex login status` / `codex logout` — official status/logout commands.
- **Verification requirement:** confirm the exact commands, the store location
  and its permissions, the token-refresh behavior, and whether the CLI supports
  an OS keystore on Windows/Linux at the pinned version.

**Subscription terms (knowledge-recorded; verification required).**

- ChatGPT Plus/Pro/Team/Enterprise plans include Codex usage; the CLI
  authenticates with the ChatGPT account. Team/Enterprise plans advertise
  data-exclusion defaults for training. Verify the current terms of use, the
  acceptable-use policy, and whether the intended usage (programmatic runner
  execution of a Codex CLI job) is permitted by the plan's terms.
- **Verification requirement:** confirm the plan terms, the single-user/seat
  requirements, and whether programmatic/headless execution is permitted. If
  the terms do not permit the intended usage, the adapter is rejected.

**Isolated environment compatibility (knowledge-recorded; verification required).**

- Codex CLI has built-in sandbox modes (read-only, workspace-write,
  danger-full-access) and approval modes. The sandbox modes are the intended
  way to run Codex CLI jobs without human approval; `danger-full-access` and
  the bypass flag are prohibited here.
- **Verification requirement:** confirm the sandbox modes' behavior on Windows
  and Linux, whether the CLI supports native Windows execution without WSL,
  whether the sandbox is OS-enforced (not a flag), whether the CLI's own
  sandbox denies the tool-executing process access to the credential store, and
  whether the CLI's headless mode (`codex exec`) is suitable for the runner
  job contract. Also verify the CLI's own outbound provider endpoints, which
  are a separate egress approval (§1.2 boundary 4).

**Execution constraints (summary; full table in §8).**

- Headless mode: `codex exec` (non-interactive). Verify the exact flags and
  their behavior at the pinned version.
- Sandbox: `workspace-write` (or read-only) with network disabled by default
  is the only acceptable mode; `danger-full-access` / bypass modes are
  prohibited.
- Credential: `codex login` store in the dedicated runner identity's profile.
- No unofficial circumvention: no modified binaries, no undocumented flags, no
  proxying of the provider's API.

### 5.2 Claude Code (Anthropic)

**Official auth methods (knowledge-recorded).**

- `claude login` — the official Claude subscription login (browser OAuth).
- Claude Code CLI stores OAuth tokens in the OS keyring on macOS (Keychain) and
  in a file in its own config directory on Linux/Windows (historically
  `~/.claude/.credentials.json`); on Windows, verify whether the CLI uses the
  Windows Credential Manager or a file. **Verification required.**
- `claude setup-token` — the official long-lived OAuth token for headless/CI
  use. This token is a credential; the CLI supports this token as an
  alternative to the interactive login. **Verification required.**
- `ANTHROPIC_API_KEY` — the official API-key method (Console account).
- `CLAUDE_CODE_USE_BEDROCK` / `CLAUDE_CODE_USE_VERTEX` — enterprise cloud
  gateway options; these require AWS/GCP credentials, which are out of scope
  here (they are separate credentials, not provider credentials, and are not
  considered in this design).
- `apiKeyHelper` — a documented setting that runs a script to produce the
  API key; this is a **potential broker integration point** (§7 BR-1/BR-2
  could be implemented as an `apiKeyHelper` script), but it is a *credential
  producer* hook, so it must be evaluated as a broker integration point, not
  as a direct credential supply.
- **Verification requirement:** confirm the exact commands, the store location
  and its permissions on Windows/Linux, whether the CLI supports an OS
  keystore on Linux, and whether the `apiKeyHelper` hook is usable as a
  broker integration point (the hook produces a credential value, so it is
  a bytes-exposure point and must be verified as such).

**Subscription terms (knowledge-recorded; verification required).**

- Claude Code is included in Claude Pro/Max plans; Max plans have higher
  usage limits. Team/Enterprise plans have their own terms. Verify the
  current terms, the acceptable-use policy, and whether the intended usage
  (programmatic runner execution of a Claude Code job) is permitted by the
  plan's terms.
- **Verification requirement:** confirm the plan terms, the single-user/seat
  requirements, and whether programmatic/headless execution is permitted. If
  the terms do not permit the intended usage, the adapter is rejected.

**Isolated environment compatibility (knowledge-recorded; verification required).**

- Claude Code has built-in sandboxing (bash sandboxing with filesystem/network
  restrictions) and a permission system. The sandboxing is the intended way to
  run Claude Code jobs without human approval; `--dangerously-skip-permissions`
  is prohibited here.
- **Verification requirement:** confirm the sandbox behavior on Windows and
  Linux, whether the CLI supports native Windows execution, whether the
  sandbox is OS-enforced, whether the CLI's own sandbox denies the
  tool-executing process access to the credential store, and whether the CLI's
  headless mode (`claude -p`) is suitable for the runner job contract. Also
  verify the CLI's own outbound provider endpoints, which are a separate
  egress approval (§1.2 boundary 4).

**Execution constraints (summary; full table in §8).**

- Headless mode: `claude -p` (print mode). Verify the exact flags and their
  behavior at the pinned version.
- Sandbox: the CLI's built-in sandboxing with filesystem/network restrictions
  is the only acceptable mode; `--dangerously-skip-permissions` is prohibited.
- Credential: `claude login` (or `claude setup-token`) store in the dedicated
  runner identity's profile.
- No unofficial circumvention: no modified binaries, no undocumented flags, no
  proxying of the provider's API.

### 5.3 Gemini CLI (Google)

**Official auth methods (knowledge-recorded).**

- `gemini` — the official Gemini CLI; `gemini` login (OAuth with a Google
  account) or `GEMINI_API_KEY` / `GOOGLE_API_KEY` (API key). Vertex AI
  enterprise options are also available (`GOOGLE_CLOUD_PROJECT` etc.).
- The CLI stores OAuth tokens in its own config directory (e.g.
  `~/.gemini/oauth_creds.json`); **Verification required.**
- **Verification requirement:** confirm the exact commands, the store location
  and its permissions, whether the CLI supports an OS keystore, and whether
  the CLI's headless/sandboxed mode is suitable for the runner job contract.

**Subscription terms (knowledge-recorded; verification required).**

- The Gemini CLI's free tier is included with a personal Google account (with
  usage quotas); the Gemini Code Assist free tier and the paid tiers have their
  own terms. Verify the current terms, the acceptable-use policy, and whether
  the intended usage (programmatic runner execution of a Gemini CLI job) is
  permitted by the plan's terms.
- **Verification requirement:** confirm the plan terms, the quotas, and
  whether programmatic/headless execution is permitted. If the terms do not
  permit the intended usage, the adapter is rejected.

**Isolated environment compatibility (knowledge-recorded; verification required).**

- Gemini CLI has a built-in sandboxed mode (`--sandbox`) that runs the agent
  in a container (Docker/Podman). Verify the sandbox behavior on Windows and
  Linux, whether the CLI's sandbox is OS-enforced, whether the CLI's own
  sandbox denies the tool-executing process access to the credential store,
  and whether the CLI's headless mode is suitable for the runner job contract.
- **Verification requirement:** confirm the sandbox behavior, the CLI's
  outbound provider endpoints, and whether the CLI's headless mode is
  suitable. Also verify the CLI's outbound provider endpoints, which are a
  separate egress approval (§1.2 boundary 4).

**Execution constraints (summary; full table in §8).**

- Headless mode: `gemini` (non-interactive) with the appropriate flags at the
  pinned version.
- Sandbox: `--sandbox` (container) or the CLI's built-in sandboxing; verify
  that the sandbox is OS-enforced and that the credential store is denied to
  the tool-executing process.
- Credential: `gemini` login (or `GEMINI_API_KEY`) store in the dedicated
  runner identity's profile.
- No unofficial circumvention: no modified binaries, no undocumented flags, no
  proxying of the provider's API.

### 5.4 Local LLM runtimes (Ollama, LM Studio, llama.cpp)

**Official auth methods.** None required — no provider credentials exist.

**Subscription terms.** Local model licenses are separate (model licenses, not
provider terms); the model licenses are verified per model, per the local-LLM
adapter conformance item (実装順 5, step-2 design).

**Isolated environment compatibility.** The local model inference is a
LAN-internal service, which is subject to the Entry 3 endpoint enumeration
(the endpoint list is a separate approval, not this document's). No credential
bytes exist in the environment; the credential boundary is trivially satisfied
by construction.

**Status:** this is the **default no-supply** adapter class (Option 0). No
credential work is required; the model quality/capability is bounded by the
local model.

### 5.5 Rejected / unsupported adapters

| Adapter | Reason | Status |
|---------|--------|--------|
| Any adapter requiring unofficial auth circumvention | Prohibited by Q4/Entry 4 | Rejected |
| Any adapter whose plan terms do not permit the intended usage | Rejected by the terms check (§5.1–5.3) | Rejected |
| Any adapter where safe credential supply cannot be demonstrated | Rejected by Entry 4 | Rejected for that environment |
| Bedrock/Vertex gateway variants (Claude/Gemini) | Require separate AWS/GCP credentials; out of scope here | Out of scope |
| Any adapter whose provider egress is not approved | Separate egress approval required (§1.2 boundary 4) | Blocked (egress) |

## 6. Credential supply design — per-adapter option selection

### 6.1 Selection rule

For each adapter × platform, the design must be evaluated in this order:

1. **Option 0 (no-supply)** — always available; the default.
2. **Option 1 (per-adapter direct)** — preferred per Q4; viable only where the
   per-adapter verification proves that the tool-executing process cannot
   read/export the credential (CLI's own sandbox or OS mechanism).
3. **Option 2 (broker-mediated)** — only if Option 1 fails and the broker
   design passes the evidence + independent review + separate Owner approval
   gate. BR-4 (local proxy) is rejected by Q4; BR-1/BR-2 are viable only
   where the CLI's own sandbox denies the credential store to the
   tool-executing process; BR-3 (OS-keystore) is the only sub-architecture
   that could satisfy the non-exportable-bytes requirement without relying
   on the CLI's own sandbox.
4. **Reject** — if neither Option 1 nor Option 2 can be demonstrated, the
   adapter is rejected for that environment (Entry 4).

### 6.2 Per-adapter × platform selection (design, not activation)

The table below is the **design-level selection**; the verification evidence
(§9) must confirm it before any adapter is enabled. The actual credential
login/transfer/supply is not authorized by this document.

| Adapter | Platform | Preferred option | Credential boundary to verify | Notes |
|---------|----------|------------------|-------------------------------|-------|
| Codex CLI | Windows (native) | Option 1 (direct) | CLI's own sandbox denies the credential store to the tool-executing process | Verify native Windows sandbox; no WSL requirement if possible |
| Codex CLI | Windows (WSL) | Option 1 (direct) | CLI's own sandbox (Linux) denies the credential store | Verify WSL sandbox; WSL is a separate host profile |
| Codex CLI | Linux | Option 1 (direct) | CLI's own sandbox (Landlock/seccomp) denies the credential store | Verify the CLI's Linux sandbox |
| Claude Code | Windows (native) | Option 1 (direct) | CLI's own sandbox denies the credential store to the tool-executing process | Verify Windows credential store location and permissions |
| Claude Code | Linux | Option 1 (direct) | CLI's own sandbox denies the credential store | Verify the CLI's Linux sandbox; file store may be plaintext — verify |
| Gemini CLI | Windows / Linux | Option 1 (direct) | CLI's `--sandbox` container denies the credential store | Verify container sandbox; the container is a separate runtime |
| Local LLM (Ollama/LM Studio/llama.cpp) | Windows / Linux | Option 0 (no-supply) | No credential exists | Default adapter class |
| Any adapter | Any | Option 2 (broker) | Only if Option 1 fails and the broker passes its own gate | Not selected by this document |

## 7. Broker comparison (design + comparison only; not selected)

### 7.1 BR-1 — CLI-store broker

**Architecture.** A broker service (separate OS identity) manages the CLI's
own credential artifact in the CLI's own store path, with OS ACLs, so the CLI
reads natively. The broker may be implemented as an `apiKeyHelper` script for
Claude Code (a documented hook) or as a store-path writer for other CLIs.

**Security properties.**

- The credential bytes never pass through Locus processes; the broker is the
  only writer.
- The tool-executing process can still read the store if the CLI's sandbox does
  not deny it — the same risk as Option 1. The broker reduces the exposure
  window only if it can inject short-lived tokens (BR-2).
- The broker is a new, trusted component; its own identity, keystore, and
  access control must be verified (Entry 5's OS-keystore pattern).

**Evidence requirements.**

- Positive: the CLI can authenticate through the broker's store path.
- Negative: the tool-executing process, the Control Plane, the interactive
  user, and another runner instance cannot read/export the credential.
- The broker's own identity cannot be impersonated by the runner.

**Risks.** A new trusted component; the store path is a file; the broker's
write path must be race-free with the CLI's own refresh writes.

### 7.2 BR-2 — short-lived credential file injection

**Architecture.** The broker materializes a per-job, short-lived credential
file into the CLI's expected path with restrictive ACLs, then removes it after
the job.

**Security properties.**

- The credential bytes are still present in a file during the job window, so
  the tool-executing process can read them unless the CLI's sandbox denies
  access. The exposure window is bounded by the job's duration.
- The broker must be able to revoke the file (delete it) and to prove that the
  file was removed after the job.

**Evidence requirements.** Same as BR-1, plus the file-lifetime and removal
evidence.

**Risks.** The file bytes are readable by the tool-executing process during
the job window (unless the CLI's sandbox denies access); the file's lifetime
must be bounded; the broker's removal must be provable.

### 7.3 BR-3 — OS-keystore broker

**Architecture.** The broker uses an OS keystore (Windows Credential Manager,
macOS Keychain, Linux secret service) that the CLI officially supports, so no
file bytes are involved. The CLI reads its credential from the OS keystore
through the CLI's own supported integration.

**Security properties.**

- This is the only sub-architecture that could satisfy the non-exportable
  bytes requirement without relying on the CLI's own sandbox: the OS keystore
  denies the credential to the tool-executing process's identity if the CLI
  reads the keystore in its own process and the tool-executing process's
  identity is denied access to the keystore.
- The CLI's own support for the OS keystore is the binding requirement —
  the CLI must officially support the keystore on the target platform.

**Evidence requirements.**

- Positive: the CLI can authenticate from the OS keystore in the dedicated
  runner identity.
- Negative: the tool-executing process, the Control Plane, the interactive
  user, and another runner instance cannot read/export the credential from the
  keystore or from the CLI's memory.
- The keystore's access control must be verified at the OS level (not a flag).

**Risks.** The CLI's OS-keystore support is the binding constraint; if the
CLI does not support the keystore on the target platform, this sub-architecture
is unavailable. The keystore's access control is per-OS-identity, so the
dedicated runner identity and the CLI's own process must be the same identity.

### 7.4 BR-4 — local proxy / token broker

**Architecture.** The broker acts as a local endpoint that the CLI
authenticates through.

**Security properties.** The CLI would need to be pointed at the broker's
local endpoint instead of the provider's official endpoint — this requires
unofficial modification of the CLI's client behavior or an undocumented
endpoint, and is prohibited by Q4 (no unofficial circumvention).

**Status:** **rejected** by Q4.

### 7.5 Broker comparison summary

| Sub-architecture | Bytes exposure to tool-executing process | Depends on CLI's own sandbox | New trusted component | Official CLI support required | Q4 compatible |
|------------------|------------------------------------------|------------------------------|-----------------------|-------------------------------|---------------|
| BR-1 CLI-store broker | Yes, unless the CLI's sandbox denies it | Yes | Yes (broker) | Store path is the CLI's own store | Yes |
| BR-2 Short-lived file injection | Yes, during the job window | Yes | Yes (broker) | Store path is the CLI's own store | Yes |
| BR-3 OS-keystore broker | No (keystore denies it, if the CLI supports it) | No (keystore is the boundary) | Yes (broker) | CLI must officially support the OS keystore | Yes |
| BR-4 Local proxy/token broker | Not applicable | No | Yes (broker) | No — requires unofficial modification | **No** (rejected) |

**Broker adoption gate.** Per Entry 4, adopting a broker requires:
1. verification evidence for the broker sub-architecture (positive + negative
   tests at §9), 2. independent review, and 3. a separate Owner approval.
This document does not select a broker; the broker is a design alternative
for adapters where Option 1 fails.

## 8. Per-adapter execution constraints and terms-of-use inventory

> **Verification requirement.** All constraints below are recorded from the
> implementer's knowledge and must be re-verified against the official CLI
> documentation at the pinned version before adapter enablement. The exact
> flags, modes, and store locations are the verification evidence's authority.

### 8.1 Codex CLI

| Constraint | Knowledge-recorded value | Verification required |
|------------|--------------------------|----------------------|
| Headless mode | `codex exec` (non-interactive) | Confirm flags and behavior at the pinned version |
| Sandbox modes | read-only, workspace-write, danger-full-access | Confirm OS-enforced sandbox behavior; `danger-full-access` prohibited |
| Approval modes | auto-approval, full-auto, bypass | Bypass modes prohibited |
| Auth methods | `codex login` (ChatGPT OAuth); `codex login --api-key`; `OPENAI_API_KEY` | Confirm store location and permissions |
| Credential store | `~/.codex/auth.json` (file, user-only permissions) | Confirm whether the CLI supports an OS keystore on Windows/Linux |
| Token refresh | Automatic (CLI-managed) | Confirm refresh behavior; does not require Locus-side renewal |
| Native Windows | Historically recommended WSL; native Windows support added over time | Confirm native Windows support at the pinned version |
| Provider endpoints | ChatGPT backend / `api.openai.com` | Separate egress approval (§1.2 boundary 4) |
| Subscription terms | ChatGPT Plus/Pro/Team/Enterprise include Codex usage | Confirm terms, single-user/seat rules, programmatic execution permission |
| Unofficial circumvention | Bypass flags, modified binaries, undocumented endpoints | Prohibited |

### 8.2 Claude Code

| Constraint | Knowledge-recorded value | Verification required |
|------------|--------------------------|----------------------|
| Headless mode | `claude -p` (print mode) | Confirm flags and behavior at the pinned version |
| Sandbox | Built-in bash sandboxing (filesystem/network restrictions) | Confirm OS-enforced behavior; `--dangerously-skip-permissions` prohibited |
| Auth methods | `claude login` (OAuth); `claude setup-token` (long-lived OAuth token); `ANTHROPIC_API_KEY` | Confirm store location and permissions |
| Credential store | macOS Keychain; Linux/Windows file in `~/.claude/` | Confirm whether the CLI uses Windows Credential Manager on Windows, or an OS keystore on Linux |
| Token refresh | CLI-managed | Confirm refresh behavior |
| `apiKeyHelper` | Documented hook producing the API key | Confirm as a broker integration point (BR-1/BR-2); the hook produces bytes, so it is a bytes-exposure point |
| Native Windows | Native Windows support (with Git for Windows for some features) | Confirm native Windows support at the pinned version |
| Provider endpoints | `api.anthropic.com` (or the subscription's endpoint) | Separate egress approval (§1.2 boundary 4) |
| Subscription terms | Claude Pro/Max include Claude Code; Max has higher limits | Confirm terms, single-user/seat rules, programmatic execution permission |
| Unofficial circumvention | `--dangerously-skip-permissions`, modified binaries, undocumented endpoints | Prohibited |

### 8.3 Gemini CLI

| Constraint | Knowledge-recorded value | Verification required |
|------------|--------------------------|----------------------|
| Headless mode | Non-interactive CLI with appropriate flags | Confirm flags and behavior at the pinned version |
| Sandbox | `--sandbox` (container-based) | Confirm OS-enforced behavior; container runtime is a separate component |
| Auth methods | `gemini` login (OAuth); `GEMINI_API_KEY`; `GOOGLE_API_KEY` | Confirm store location and permissions |
| Credential store | `~/.gemini/oauth_creds.json` (file) | Confirm whether the CLI supports an OS keystore |
| Native Windows | Native Windows support | Confirm native Windows support at the pinned version |
| Provider endpoints | Google's provider endpoints | Separate egress approval (§1.2 boundary 4) |
| Subscription terms | Free tier with quotas; Gemini Code Assist free/paid tiers | Confirm terms, quotas, programmatic execution permission |
| Unofficial circumvention | `--yolo`-class flags, modified binaries, undocumented endpoints | Prohibited |

### 8.4 Local LLM runtimes

| Constraint | Value | Verification required |
|------------|-------|----------------------|
| Headless mode | Runtime-specific (Ollama/LM Studio/llama.cpp APIs) | Confirm per-runtime conformance (実装順 5) |
| Sandbox | No provider credential; no provider egress | LAN-internal service endpoints are subject to Entry 3 enumeration |
| Auth methods | None (no provider credentials) | — |
| Subscription terms | Local model licenses (model licenses, not provider terms) | Verify per model license |
| Unofficial circumvention | Not applicable | — |

## 9. Safe verification test plan (mock/stub credentials only)

**No real credentials.** This plan uses only mock/stub credentials (synthetic
tokens like `MOCK-0000`) and stub CLI binaries. No real credential is read,
written, transferred, or supplied; no provider login is performed; no external
communication is performed. The test environment is isolated and disposable.

### 9.1 Test fixtures

| Fixture | Purpose |
|---------|---------|
| Mock credential file / keystore entry | Synthetic token bytes (`MOCK-0000`) in the CLI's expected store path, or in the OS keystore, for the fixture |
| Stub CLI binary (`fake-codex`, `fake-claude`, `fake-gemini`) | A stub that records: whether it could read the credential store, whether it could read job inputs, and whether it could read the environment; it never contacts a provider |
| Stub tool-executing process (`fake-tool`) | A stub that attempts to read the credential store, the environment, and job inputs; it records the results |
| Stub Control Plane identity | A stub that attempts to read the credential store; it records the results |
| Stub interactive user identity | A stub that attempts to read the credential store; it records the results |
| Stub other runner instance identity | A stub that attempts to read the credential store; it records the results |
| Mock audit log / receipt / job input / model context fixtures | Synthetic structures that record the bytes that appear in them |

### 9.2 Positive tests

| ID | Test | Pass criteria |
|----|------|--------------|
| VT-1 | The CLI can authenticate (Option 1) in the dedicated runner identity | The stub CLI reads the credential store; the CLI reports success |
| VT-2 | The CLI can authenticate through the broker (Option 2, BR-3) | The stub CLI authenticates through the broker's OS-keystore integration |
| VT-3 | Credential presence is recorded in the registry | The registry records `adapter_credentials.state` without any credential bytes |
| VT-4 | The CLI's own sandbox denies the credential store (Option 1) | The stub CLI's sandbox denies the store to the tool-executing process |
| VT-5 | The broker's OS-keystore denies the credential (Option 2, BR-3) | The stub CLI authenticates from the keystore; the tool-executing process cannot read the keystore |

### 9.3 Negative tests

| ID | Test | Pass criteria |
|----|------|--------------|
| NV-1 | The tool-executing process cannot read the credential store | The stub tool records "denied" for the store path, the environment, and the CLI's memory |
| NV-2 | The Control Plane cannot read the credential store | The stub Control Plane identity records "denied" |
| NV-3 | The interactive user cannot read the credential store | The stub interactive user identity records "denied" |
| NV-4 | Another runner instance cannot read the credential store | The stub other instance identity records "denied" |
| NV-5 | Credential bytes never appear in job inputs | The mock job inputs are scanned for the mock credential bytes; zero matches |
| NV-6 | Credential bytes never appear in receipts | The mock receipts are scanned for the mock credential bytes; zero matches |
| NV-7 | Credential bytes never appear in audit logs | The mock audit logs are scanned for the mock credential bytes; zero matches |
| NV-8 | Credential bytes never appear in model context | The mock model context is scanned for the mock credential bytes; zero matches |
| NV-9 | No egress | The stub CLI attempts no outbound connection; the test environment has no egress; the test records zero outbound attempts |
| NV-10 | Fail-closed | If the credential boundary or the provider-egress boundary cannot be verified, the adapter stays unavailable; no host fallback; no downgrade |
| NV-11 | No unofficial circumvention | No modified binaries, no undocumented flags, no proxying of the provider's API in the fixtures |
| NV-12 | The CLI's own sandbox denies the credential store (Option 1, negative direction) | The stub tool-executing process inside the CLI's own sandbox cannot read the store |

### 9.4 Evidence requirements

- The test evidence must bind to: the exact pinned CLI version, the exact OS
  build, the exact approved isolation profile, the exact runner build, and the
  exact broker build (if any).
- The evidence expires or becomes stale after any of those changes.
- The evidence must be produced by a runner-side, Locus-defined benign command
  whose result is a boolean (or a structured result) and whose execution never
  surfaces credential material to the Control Plane, to logs, or to any model
  input (step-2 §2.4).
- A successful unit test or a CI skip is not live proof.
- The evidence must be produced in an isolated disposable verification
  environment with synthetic data only.

## 10. Adapter availability matrix

> The matrix is the **design-level** availability; actual availability is
> determined by the verification evidence (§9) and the egress approval
> (§1.2 boundary 4). No adapter is enabled by this document.

| Adapter | Platform | Auth method | Credential supply | Subscription terms | Isolated env compat | Credential boundary verifiable | Status |
|---------|----------|-------------|-------------------|--------------------|--------------------|-------------------------------|--------|
| Codex CLI | Windows native | ChatGPT OAuth (`codex login`) | Option 1 (direct) | To verify | To verify | To verify (CLI sandbox) | Pending verification + egress |
| Codex CLI | Windows native | API key (`codex login --api-key`) | Option 1 (direct) | To verify | To verify | To verify | Pending verification + egress |
| Codex CLI | Windows WSL | ChatGPT OAuth | Option 1 (direct) | To verify | To verify (WSL) | To verify | Pending verification + egress |
| Codex CLI | Linux | ChatGPT OAuth | Option 1 (direct) | To verify | To verify (CLI sandbox) | To verify | Pending verification + egress |
| Codex CLI | Linux | API key | Option 1 (direct) | To verify | To verify | To verify | Pending verification + egress |
| Claude Code | Windows native | Claude OAuth (`claude login`) | Option 1 (direct) | To verify | To verify | To verify (CLI sandbox) | Pending verification + egress |
| Claude Code | Windows native | `claude setup-token` | Option 1 (direct) | To verify | To verify | To verify | Pending verification + egress |
| Claude Code | Windows native | `ANTHROPIC_API_KEY` | Option 1 (direct) | To verify | To verify | To verify | Pending verification + egress |
| Claude Code | Linux | Claude OAuth | Option 1 (direct) | To verify | To verify | To verify (file store) | Pending verification + egress |
| Claude Code | Linux | `claude setup-token` | Option 1 (direct) | To verify | To verify | To verify (file store) | Pending verification + egress |
| Claude Code | Linux | `ANTHROPIC_API_KEY` | Option 1 (direct) | To verify | To verify | To verify (file store) | Pending verification + egress |
| Gemini CLI | Windows / Linux | Google OAuth (`gemini`) | Option 1 (direct) | To verify | To verify (`--sandbox`) | To verify | Pending verification + egress |
| Gemini CLI | Windows / Linux | `GEMINI_API_KEY` | Option 1 (direct) | To verify | To verify | To verify | Pending verification + egress |
| Claude Code | Any | `CLAUDE_CODE_USE_BEDROCK` / `CLAUDE_CODE_USE_VERTEX` | Out of scope | Separate AWS/GCP credentials | Out of scope | Out of scope | Out of scope |
| Gemini CLI | Any | Vertex AI enterprise | Out of scope | Separate GCP credentials | Out of scope | Out of scope | Out of scope |
| Local LLM (Ollama/LM Studio/llama.cpp) | Windows / Linux | None (no provider credentials) | Option 0 (no-supply) | Local model licenses | Per-runtime conformance | Trivially satisfied | Default adapter class |
| Any adapter | Any | Broker-mediated (BR-1/BR-2/BR-3) | Option 2 (broker) | To verify | To verify | To verify | Broker adoption gate: evidence + independent review + separate Owner approval |
| Any adapter | Any | Unofficial circumvention | — | — | — | — | **Rejected** |

## 11. 【要決定】 decision items

These are genuinely new permission or policy choices that this document does
not decide. The owner's decision is required before any of them is resolved.

| ID | Decision | Why it is a new choice |
|----|----------|------------------------|
| AD-1 | Whether credential-presence/health verification is performed at all, and its acceptance form | Step-2 §2.4/§2.5 left "whether to verify at all" and the acceptance form of the verification receipt 【要決定】 |
| AD-2 | Whether the CLI's own sandbox counts as a credential boundary, or whether an OS-level mechanism is required | Step-2 §2.4 states a required design property but does not decide whether the CLI's own sandbox is sufficient evidence |
| AD-3 | Which broker sub-architecture (BR-1/BR-2/BR-3), if any, is adopted | Entry 4 requires a separate Owner approval for broker adoption |
| AD-4 | Whether API-key methods are acceptable at all, given they are exportable bytes | Q4 does not force API-key; whether API-key supply is acceptable in the dedicated runner identity is a new policy choice |
| AD-5 | The adapter enablement list (which adapters are approved for which environment) | Entry 4 requires per-adapter approval before enablement |
| AD-6 | Credential lifetime/rotation policy for the broker (if adopted) | Entry 5's rotation pattern is for Runner trust; provider credential rotation is a new policy |
| AD-7 | Whether the CLI's own outbound provider endpoints are approved for egress | Entry 3's provider-API rule requires a separate endpoint approval |

## 12. Activation gates (what this document does NOT approve)

Per Entry 4, ADR-0012, B6, and the owner's §2 scope:

1. No actual account login, credential read, credential transfer, or
   credential supply.
2. No provider login, no external communication, no provider egress.
3. No B6 dispatch; no job execution; no Runner registration/activation.
4. No isolation profile activation; no unverified isolation profile.
5. No change to existing safety boundaries, permission ceilings, or
   fail-closed behavior.
6. No adoption of a broker; the broker requires its own evidence + independent
   review + separate Owner approval (AD-3).
7. No real credential bytes anywhere in this work, including in the mock
   fixtures (the fixtures use synthetic tokens only).

## 13. Risks and open questions

- **CLI's own sandbox as the credential boundary.** The strongest risk is that
  the CLI's own sandbox does not deny the credential store to the
  tool-executing process, and no OS mechanism can provide the denial. In that
  case the adapter is rejected for that platform (Entry 4), and the broker
  BR-3 (OS-keystore) is the only remaining design option — but only if the
  CLI officially supports the OS keystore on the target platform.
- **Plaintext credential stores.** If the CLI's credential store is a plaintext
  file (e.g. `~/.claude/.credentials.json` on Linux), the tool-executing
  process can read it unless the CLI's own sandbox denies it. The
  verification must confirm the store's permissions and the CLI's sandbox
  behavior at the OS level.
- **Terms of use.** The provider's subscription terms must permit the intended
  usage (programmatic runner execution of a CLI job). If the terms do not
  permit it, the adapter is rejected regardless of the technical boundary.
- **Provider egress.** The CLI's own outbound provider endpoints are a separate
  egress approval (Entry 3's provider-API rule). Credential supply and
  provider egress are two independent gates; both must pass before any
  provider-authenticated adapter is dispatchable.
- **Token refresh.** The CLI's own token refresh is a CLI-managed process; the
  Locus side must not need to renew the credential. If the CLI's refresh
  requires a renewal that the broker or the CLI's own sandbox cannot provide,
  the adapter may become unavailable; the verification must confirm the
  refresh behavior.
- **Knowledge freshness.** All vendor claims are knowledge-recorded and
  unverified; the pinned CLI version at verification time may differ from the
  knowledge-recorded version. The verification evidence must re-verify every
  claim at the pinned version.

## 14. Review history

- **2026-11-10 (P4-ADAPTER, this worktree):** initial design authored per
  Entry 4 and Q4. No external verification performed in this environment;
  all vendor claims are knowledge-recorded and marked with verification
  requirements. No adapter activation, no credential read, no credential
  transfer, no credential supply, no provider login, no external
  communication, no B6 dispatch approved.
