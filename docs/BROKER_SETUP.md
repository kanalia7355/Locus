# Dedicated App / Broker implementation

ADR-0007 was approved for implementation on 2026-10-31. **It is not activated.**
The existing Controller still delivers PRs and refuses atomic-base claims.
Do not enable native queued auto-merge or replace its false atomic-base gate.

## Implemented foundation

- `loop app-register review` and `loop app-register merge`: bounded local
  manifest registration with unpredictable state, exact loopback Host/path,
  suppressed HTTP logging, fixed GitHub HTTPS conversion and no redirects or
  ambient proxies. Keys go directly to Windows Credential Manager. No token/key
  file, environment-variable handoff or chat input is used. Existing credentials
  are not deliberately overwritten. A failed/uncertain conversion is not replayed;
  inspect GitHub's App settings before starting another session.
- Review App permissions: Contents read, Checks/Pull requests write. Merge App:
  Contents/Pull requests write. Both are private to the owner. Install each on
  **kanalia7355/Locus only**, not all repositories. Registration does not install
  an App, approve a PR, change protection, start a service or activate merging.
- `github_app.py`: RSA-signed short-lived App JWTs and repo-scoped installation
  credentials, held in memory. Wrong owner, installation privileges, suspended
  installations and non-Locus operation paths are rejected.
- `broker_policy.py`: proposed independent writer rulesets, with separate main
  PR-only update admission and broker-lock ref ownership. These proposals contain
  no check/review rules and must not replace/bypass classic CI/review protection.
- `github_mutex.py`: GitHub atomic reference creation, immutable owner/binding
  commit, no TTL or lock stealing. It is not a merge authorization by itself.
- `merge_broker.py`: durable acquisition/merge/release intent, exact head/base/
  policy/review/verification identity, ownership checks and conservative recovery.
  Unknown writes retain exclusivity. A late definitive merge is reconciled
  without issuing another merge. Incomplete acquisition, rejected preflight and
  uncertain release require explicit recovery, never a timer-based unlock.

These components currently have **local/mock** evidence. They do not establish
live exclusive-writer enforcement, trusted review publication or safe merging.

## One-time operator registration

After the source and tests are independently reviewed, run in a local terminal:

```powershell
.venv\Scripts\python.exe -m loop_engine.cli app-register review
.venv\Scripts\python.exe -m loop_engine.cli app-register merge
```

Open the temporary localhost URL printed by each command, create its App using
your existing GitHub login, then open the returned installation URL and select
Locus only. Keep only the public App/installation IDs. Never paste keys/tokens
into chat, source, `.env`, CI or command arguments. No raw key download is needed.
The receiver expires after ten minutes. A key too large for the supported vault
is rejected rather than written to a file.

Credential Manager protects storage, **not processes running as the same user**.
Before activation the signer needs a reviewed/pinned runtime and an isolated
service account whose credentials cannot be read by untrusted source/QA/model
execution. Registration under the development account is provisioning only;
it is not evidence of that production boundary.

## Remaining activation gates (not implemented or proven by this foundation)

1. Trusted service packaging/account isolation and source pinning; actual fresh
   independent review invocation and App review/check publication. Check binding
   must include exact source, base, policy and QA identity; no caller-supplied
   `passed=true` or implementer-published success substitutes for review.
2. Live installation identity validation and an independently reviewed remote
   gate reader/merge adapter. Every gate must be re-read while holding the global
   lock. The protocol's injected transport is a trusted-service interface, not an
   API exposed to model tasks. No production transport is wired to the Controller.
3. Apply/read back both writer rulesets alongside existing classic protection;
   pin the real Review App ID to its required check. Test rejection of UI/API
   merges, direct pushes, other identities and native queued requests. Personal
   repository support and App approval behavior remain live-test questions.
4. Cross-process/host race and crash tests against a disposable test repository,
   including uncertain writes, key rotation/revocation and emergency recovery.
   Never delete a lock merely because a process died or a timeout elapsed.
5. Versioned main/policy state migration preserving Goal, attempt counters,
   decisions, source snapshots, review evidence and events. Existing frozen
   `.loop/config.yaml` and database have not been rewritten or reset.
6. Independent final audit, explicit operator activation, then one complete live
   implementation → review → PR → CI repair → broker merge → next-task cycle.

If any gate fails, continue authorized independent PR work and retain merge hold.
This document does not claim that the unattended environment is complete.

References: [GitHub App manifest flow](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest),
[ruleset API](https://docs.github.com/en/rest/repos/rules).
