# Responses Lite boundary investigation

Owner completed upgrade settings/SCM switching to audit artifact
cee51f97a79bcdfdd2009f4e9fb889d999baf1b9d3e866e40f934cb18ffc0877.
Authenticated health passed. Exact-record reconcile_auth independently returned
authenticated=true, original_trial_preserved=true, provider_request_sent=false.
The separately permitted diagnostic was invoked once and returned blocked,
upstream_response/policy/HTTP200. No review/check or merge was published. Original
and diagnostic intents remain preserved; no replay/reset or third real trial ran.

The actual response media type was not retained. Same-version source and native
local tests establish that the selected model uses Responses Lite, sends its
explicit marker header and places tool declarations inside additional_tools input
items. The deployed relay dropped that marker and checked only top-level tools.
This establishes interoperability and validation defects, not the exact contents
of the rejected real response. An unauthenticated invalid-model HTTP probe to the
same fixed endpoint returned401 JSON; it used no credential or real inference.

Native CLI0.166.0 synthetic-only local SSE tests completed the review schema but
advertised functions, clock and collaboration namespaces inside Lite. Explicit
code_mode/code_mode_only/multi_agent disabling did not remove them. A diagnostic
copy of the public catalog with tool_mode=direct still declared tools. No deployed
catalog, model policy or real login was changed. Synthetic-only profiles used
invalid credentials, no external inference and no source/model tool invocation.

Earlier zero_tools_verified receipts are insufficient. The audit service was
stopped through its existing operator SCM rights. Both App services remain Running
in preparation mode; credentials, settings, runtime and trial records are retained.

Independent fail-closed source hardening rejects embedded/malformed declarations,
tool-history input and nonstandard JSON constants, and validates/forwards only the
fixed Lite marker. SSE media-type matching is case insensitive. It does not remove
native tools or implement the proposed response filter, and is not deployed.

ADR0011 proposes a model-facing gate with whole-event rejection before native
execution, or a dedicated registry-free executor. Independent consolidated
architecture/security review initially requested a closed pinned request schema.
Fix/re-review cycle1 closed that Medium finding; disposition needs_decision,
findings empty. Reviewer inspected source/cached public source without tests,
network, credentials or deployed-state access. Owner selection, implementation,
adversarial tests, exact deployment and live verification remain separate gates.

Full local `scripts/verify_loop.py --audit` passed 432 tests with 7 existing skips
(Windows symlink privilege / opt-in real Docker), lint/format, native/Python3.11
Linux type checks, secret scanning, dependency consistency and advisory checks.
The unpublished local project has no PyPI advisory record. These checks certify
neither the pending design implementation nor live tool-free behavior.
