# Existing Locus App provisioning

Operator-provided public identities:

| Role | App ID | Installation ID |
| --- | --- | --- |
| Review | 5555922 | 177234377 |
| Merge | 5556060 | 177236244 |

Administration read for the Merge App was explicitly approved under ADR0008.
In its GitHub App settings, set Repository permissions → Administration →
Read-only, save, and accept the installation permission update if GitHub requests
it. Keep only Locus selected. Review App scopes remain unchanged. No
Administration write or change to main protection is authorized by provisioning.

The keys were placed in GitHub Actions Secrets. GitHub does not return secret
values ([API response contract](https://docs.github.com/en/rest/actions/secrets#get-a-repository-secret));
no workflow is created to extract them. The current Windows vault has no
credential at either supplied App ID. Use the original key locally, without
pasting it into chat, command arguments or files created by this tool. If the
original key is unavailable, the App owner needs to provision a new key.

From an interactive PowerShell terminal in `C:\Users\hirot\Locus`, run:

```powershell
.venv\Scripts\python.exe -m loop_engine.cli app-provision review --app-id 5555922 --installation-id 177234377
.venv\Scripts\python.exe -m loop_engine.cli app-provision merge --app-id 5556060 --installation-id 177236244
```

Wait for `PEM line (hidden):`, then paste the original multiline PEM. Input ends
at its END marker. No key value is displayed. The command refuses noninteractive
input and getpass's plaintext fallback. It authenticates the App, installation,
returned role permissions and repo-scoped token before storing in Windows
Credential Manager. Merge provisioning also reads main protection using the
actual App token. Existing keys are not overwritten; rerunning validates them.

Only public IDs and requested scopes are stored under ignored
`.loop/runtime/app-installations/`. `authenticated=true` means those read-only
operations succeeded, not that automatic merging is activated. Failed or
uncertain authentication does not store the supplied key or declare success.
Do not remove the existing GitHub Secrets copies before local authentication
and a deliberate credential migration decision; this implementation does not
delete or expose them.

After both imports, inspect policy without changing it:

```powershell
.venv\Scripts\python.exe -m loop_engine.cli app-policy --merge-app-id 5556060 --installation-id 177236244 --review-app-id 5555922
```

The observer reports missing/untrusted checks and writer rulesets. It always
reports `merge_authorized=false` and `atomic_base_binding=false`; matching
settings alone do not prove writer exclusion, trusted review, service isolation
or activation. Publisher/Broker wiring, state migration and live merge proofs
remain required under [BROKER_SETUP.md](BROKER_SETUP.md).

## Safe failure diagnostics

The import now reports `authenticated=false`, fixed `stage`/`reason` identifiers
and a numeric `http_status`. No key, JWT, token, response body or arbitrary
exception message is included. Share only this JSON when investigating a failure.
Permission mismatches additionally include `permission_difference`: known
permission labels with finite expected/granted levels. Unknown names are shown
only as a count; arbitrary values are never echoed.

| Diagnostic | Check |
| --- | --- |
| `key / invalid` | Original PEM belongs to the selected App and was pasted completely. |
| `installation / http_rejected / 401` | App/key/installation pairing and local system clock. |
| `installation / repository_selection` | Installation uses **Only select repositories → Locus**, not all repositories. |
| `installation / permissions` | Exact role scopes and accepted installation permission update. |
| `token / repository_scope` | Token did not demonstrate the required repository/permission scope; do not bypass validation. |
| `repository / http_rejected` | Target repository/operation access. |

The reported generic failure did not identify its stage. Diagnostic visibility
does not establish its underlying cause or successful authentication. Input is
not stored after failed authentication, and scope checks remain enforced.

Paste the original multiline PEM. Each hidden prompt collects one line, and
the program joins all lines into one complete key before signing. An observed
`installation / permissions` response means parsing/signing and installation
identity checks passed; it is not a PowerShell newline error. Flattening the
entire key into one line exceeds the per-line limit and now reports
`key / input_line_too_long` without echoing input.
