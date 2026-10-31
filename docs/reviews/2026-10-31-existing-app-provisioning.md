# Existing App provisioning and policy observation

The operator supplied public App/installation IDs and explicitly approved
ADR0008's repo-only Merge App Administration read scope. Review permissions are
unchanged. This approval does not activate signing services, change main
protection, migrate the Goal or authorize an unverified merge.

Both exact local vault targets and both named process-environment variables
were checked for presence only; none contained a key. The operator confirmed
the keys were stored in GitHub Actions Secrets. Their values were not requested
in chat, downloaded, logged, exposed through a workflow or written to files.

Implementation adds masked local `app-provision` adoption and a read-only
`app-policy` observer. Authentication precedes key storage. Only public IDs and
scopes are recorded, with activation false. Existing keys/metadata are not
silently replaced. The observer always reports merge authorization and atomic
binding false, including when all inspected policy prerequisites match.

## Validation

- Full engine verifier/advisory audit: 175 passed, 6 opt-in Docker skips;
  lint/format, strict native and Python3.11/Linux types, secret scanning,
  dependency consistency and advisory checks passed.
- 29 focused provision/policy/App tests passed. Authentication and policy APIs
  are simulated; no actual App private key/token was used. Negative cases cover
  noninteractive input, forbidden getpass fallback, failed authentication,
  conflicting metadata/key replacement, untrusted check publishers, review
  bypass, writer-rule changes/missing rules and moving main.
- Assistant-side interactive TTY smoke could not start because the execution
  tool's Windows process creation was denied. Actual local masked import remains
  owner-performed and unverified; no plaintext fallback was attempted.
- One fresh independent read-only security reviewer accepted the implementation
  without blocking findings or fix cycles. It inspected source and tests only;
  no runtime state, credentials, network, tests, writes or further agents were
  accessed. A stale proposal heading was corrected editorially.

Actual App authentication, returned installation permissions, policy observation,
credential isolation, signing publication and merging are not claimed proven.
The existing source-only QA image remains valid because dependencies/recipe did
not change; runtime source receipt must be refreshed after these code changes.
