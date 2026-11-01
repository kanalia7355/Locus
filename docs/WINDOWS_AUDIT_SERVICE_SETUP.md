# Dedicated audit service preparation

Current hold2026-11-02: Responses Lite native tests invalidated the old top-level
zero-tool receipt. The audit service is intentionally stopped. Do not restart,
re-enrol or rerun model trials using these earlier preparation steps. Credentials
and records are preserved. ADR0011 requires an owner-selected boundary and new
implementation/deployment proof before resuming. App preparation services remain
Running; automatic review/merge is not active.

This adds the owner-approved ADR0009 audit account and ADR0010 encrypted model
login storage. It does not replace either deployed App service or enable merging.
Use only an independently reviewed package built from a clean committed tree.
Do not run the older App installers, recovery or completion commands again.

## Changes made by the new installer

Create only `locus_loop_audit`, `LocusLoopAuditV1` and
`C:\ProgramData\LocusLoopAuditV1`. Refuse existing or partial audit installations;
preserve them for diagnosis. Do not reset existing accounts/passwords, import
App keys, copy operator model authentication or change branch protection.

The service uses sealed Python/source/client files, a separate private state
directory, an empty model workspace and no model tools. Its Codex home is sealed
except nonsecret lock/installation files and the private `secrets` directory.
Only standard encrypted `codex_auth.age` and ciphertext temporary files are
permitted there. The encryption passphrase stays in that account's OS keyring.
Operator/Review/Merge cannot read the directory. The audit identity cannot sign
GitHub reviews or merges. The installer starts a Manual preparation service.

## Owner operations after package review

The agent supplies one exact generated `admin-command.txt` and manifest hash.
Read that block and execute it in a fresh administrator 64-bit PowerShell under
the same Windows owner account. No secret input is required. Return only the final
JSON. If it fails, preserve the installation and return the JSON; do not rerun.
The agent then verifies registration, ACLs, denied access and synthetic capability
probes. Do not begin real login until those checks pass.

For the subsequent private login, run in your own ordinary interactive console:

```powershell
.venv\Scripts\python.exe -m loop_engine.audit_client enroll
```

Use the official device link and one-use code displayed only in that console.
Never send the code, tokens, keys or authentication files to the agent/chat.
Return only the terminal JSON. Device login must be enabled for the account;
there is no paid API-key fallback. The enrolment window is bounded to five minutes.

The agent runs `audit_client auth_status` and the fixed synthetic `self_test`
afterward. A real model test is labelled separately from mocked tests and cannot
publish an approval by itself. App review publication, exact-head merge policy,
Controller wiring and final live integration remain separate readiness gates.

## Interrupted authentication

A protected nonsecret lifecycle record precedes every authentication mutation.
Missing key/ciphertext, replaced key metadata, leftover temporary files, plaintext
authentication, unexpected direct-keyring entries or an interrupted operation stop
before further CLI invocation. Never delete files, reset the lifecycle, regenerate
the key or run logout as a recovery shortcut. Preserve state for a scoped repair.
Successful synthetic probe cleanup applies only to that exact known probe, not
to real authentication. No real-authentication cleanup is automated by this setup.

## Pre-authentication installer failure

The first audit package stopped after creating the account and empty state
workspace: its feature-name validator rejected the digit in the fixed
`responses_websockets_v2` setting. Syntax/native compilation tests had not
exercised that runtime branch. The fixed installer validates versioned capability
names before creating anything; a regression test executes the actual PowerShell
guard with all fixed names and rejects unsafe names.

For this exact partial state, use only the separately audited completion package
provided by the agent. It verifies the original deployed manifest/inventory and
private ACLs, exact unused SID, no profile/group/service use, exact service/deny
logon rights and state containing only the empty workspace. Any difference stops
before password change. It records an exclusive intent, regenerates only the
unused audit account's lost service password, creates missing profiles/settings
and registers/starts the preparation service. It neither recopies runtime files
nor changes the two existing App accounts, keys, passwords or services. Existing
files and the old installation intent remain preserved. A completion intent or
any subsequent authentication state prevents replay; do not rerun either script.

## Held real-model trial

If a real model trial leaves active_use and a started intent, retain both. A
read-only metadata diagnostic does not prove provider completion. Do not run the
old self_test or enrolment again, delete state or re-enter credentials.

Use only an independently reviewed, exact-hash audit-runtime upgrade/reconciliation
package supplied for that observed state. It retains the existing account and
SCM password, encrypted cache/keyring, original profile policy, old runtime,
trial and state records. Administrator execution permits a specific nonsecret
state reconciliation and one separate synthetic diagnostic task; it is not a
general retry/reset permission or automatic-merge activation.

After upgrade, the agent verifies health, calls `audit_client reconcile_auth`
once under the protected permit, then may call `audit_client diagnose_transport`
once. Neither operation accepts owner-supplied commands, paths, model results or
credentials. The agent reports sanitized stage/status on failure and preserves
uncertain intents. A diagnostic success is labelled separately from original
trial completion, independent review publication and full loop readiness.

If this update stopped at settings_and_binary with both settings and SCM still
pointing at the old runtime, never rerun the upgrade. Its code/settings/permit may
already be staged. Use only the exact-hash completion helper supplied after
verification. It performs the pending settings/SCM switch using the corrected
PowerShell null-string binding, with all staged artifacts revalidated. It does
not redeploy code, reset authentication, recreate accounts or rotate passwords.
