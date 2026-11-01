# Dedicated audit service preparation

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
