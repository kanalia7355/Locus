# Dedicated App / Broker implementation

ADR-0007 was approved for implementation on 2026-10-31. **It is not activated.**
The existing Controller still delivers PRs and refuses atomic-base claims.
Do not enable native queued auto-merge or replace its false atomic-base gate.

The complete requirements/status matrix is [UNATTENDED_READINESS.md](UNATTENDED_READINESS.md).
New inactive review-publication and remote-gate/merge transport cores have mock
integration coverage. Versioned source/policy migration now has an explicitly
approved apply/recovery CLI and synthetic crash/concurrent-edit coverage.
No real migration was applied. Production signer/Controller wiring, Review-to-Merge
communication and live merge proofs are still incomplete. Prepare services and
operator-to-Merge policy reads are verified separately below.
Use `loop activation-readiness --live --pull 6` for read-only current facts;
approval cannot turn those missing components into a deployed system.

For the existing operator-created Apps and keys currently in GitHub Actions
Secrets, use [existing App provisioning](APP_PROVISIONING.md), not a second App
registration. Keys must be entered locally through the masked import command;
GitHub Secrets values are not extracted through CI.

## Implemented foundation

- `loop app-register review` and `loop app-register merge`: bounded local
  manifest registration with unpredictable state, exact loopback Host/path,
  suppressed HTTP logging, fixed GitHub HTTPS conversion and no redirects or
  ambient proxies. Keys go directly to Windows Credential Manager. No token/key
  file, environment-variable handoff or chat input is used. Existing credentials
  are not deliberately overwritten. A failed/uncertain conversion is not replayed;
  inspect GitHub's App settings before starting another session.
- Review App permissions: Contents read, Checks/Pull requests write. Merge App:
  Contents/Pull requests write and Administration read, explicitly approved in
  ADR0008. Administration write is not requested. Both are private to the owner. Install each on
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

The mutex/journal components currently have **local/mock** evidence. They do not
establish live exclusive-writer enforcement, trusted review publication or safe
merging. App authentication and read-only policy access now have separate live
evidence, recorded below.

## Live provisioning observation — 2026-11-01

Both existing Apps were successfully provisioned locally. A subsequent read-only
probe using Windows Credential Manager authenticated Review App 5555922 /
installation 177234377 and Merge App 5556060 / installation 177236244. Each read
main and its check-runs endpoint at
`e3db371e0cb60634f251b25f5649a6c07373b20d`. Merge App also successfully read classic
branch protection and repository rulesets using its approved Administration read
permission. No extra Checks permission was needed for these observed reads.

The policy observer still reports `app_bound_independent_review` and both missing
broker writer rulesets. The existing user-created ruleset 26268631 is disabled;
it was preserved. Required CI remains bound to GitHub Actions App 15368.
`merge_authorized` and `atomic_base_binding` remain false. No review/check was
published, protection changed, lock created or PR merged by these probes.

Successful provisioning does not establish the cause of the earlier HTTP401,
trusted service-account isolation, write access behavior or activation. Keys,
JWTs and installation tokens were not printed or exported.

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

## Preparation deployed; production activation gates remain

The two prepare-only Windows services are now deployed under separate identities.
Actual SCM denied-mutation, source/state isolation, per-role authentication and
restart persistence evidence is recorded in
[preparation-services-live](reviews/2026-11-01-preparation-services-live.md).
This proves preparation, not fresh model-review execution or production authority.
Operator App-vault/GitHub Secrets copies are retained pending custody reconciliation.

1. Preparation packaging/account isolation/source pinning are verified. Actual fresh
   independent review invocation and App review/check publication. Check binding
   must include exact source, base, policy and QA identity; no caller-supplied
   `passed=true` or implementer-published success substitutes for review.
2. Live installation identity validation and an independently reviewed remote
   gate reader/merge adapter. Every gate must be re-read while holding the global
   lock. The protocol's injected transport is a trusted-service interface, not an
   API exposed to model tasks. No production transport is wired to the Controller.
   GitHub's classic branch-protection REST read requires Administration read,
   now approved for the Merge App in ADR0008. The read-only policy observer
   reports exact classic protection and writer ruleset facts, but does not
   establish activation or atomic-base proof. Do not silently expand permissions,
   copy the owner's OAuth credential into a service, or accept worker-supplied
   protection booleans. The existing authenticated `gh` reader is not proof that
   an isolated App service can make the same read.
   [ADR0008](architecture/ADR-0008-merge-policy-read-permission-proposal.md)
   records the approved repo-only Merge App Administration read permission.
   The App owner must update its GitHub settings/accept the installation update;
   local requested scopes are not evidence that GitHub has granted them.
3. Apply/read back both writer rulesets alongside existing classic protection;
   pin the real Review App ID to its required check. Test rejection of UI/API
   merges, direct pushes, other identities and native queued requests. Personal
   repository support and App approval behavior remain live-test questions.
4. Cross-process/host race and crash tests against a disposable test repository,
   including uncertain writes, key rotation/revocation and emergency recovery.
   Never delete a lock merely because a process died or a timeout elapsed.
5. Apply the approved versioned main/policy state migration preserving Goal, attempt counters,
   decisions, source snapshots, review evidence and events. Existing frozen
   `.loop/config.yaml` and database have not been rewritten or reset.
6. Independent final audit, explicit operator activation, then one complete live
   implementation → review → PR → CI repair → broker merge → next-task cycle.

If any gate fails, continue authorized independent PR work and retain merge hold.
This document does not claim that the unattended environment is complete.

## Controller readiness observation — 2026-11-01

`loop status` reports a stopped Controller, TASK-001 completed at its retained
3/3 attempts, and Development not evaluated. The frozen runtime configuration
still targets `feat/unattended-runtime`, uses PR-only delivery with auto-merge
off, and disables Development with an empty allowed-path list. Do not simply
edit that frozen configuration: migrate the approved main/policy and reconcile
superseded decisions with explicit provenance while preserving earlier records.
The next task must come from the approved Goal evaluation, not a reset of
TASK-001 or an assertion that product development has already been authorized.

`loop doctor` reports readiness for the verified source-proposal/container-QA
execution boundary, separately from its explicit PR-only merge hold. This
execution readiness is not completion of the activation gates above. Time,
resume, stagnation and completion modules already exist; their complete live
path through App publication and Broker merge remains to be demonstrated.

PR6's failed `verify` run 41229058508 reached browser E2E after passing Python,
frontend unit/build and secret checks. The attachment scenario submitted before
its asynchronous removal completed. Its test now explicitly waits for the
dropped attachment to disappear before submitting; all original assertions,
timeouts, retry settings and CI checks are retained. Five fresh-fixture focused
runs and the complete five-test browser suite passed locally, as did ESLint.

References: [GitHub App manifest flow](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest),
[ruleset API](https://docs.github.com/en/rest/repos/rules),
[classic branch-protection read permissions](https://docs.github.com/en/rest/branches/branch-protection#get-branch-protection).
