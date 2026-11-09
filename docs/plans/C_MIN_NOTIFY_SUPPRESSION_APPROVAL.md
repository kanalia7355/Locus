# Assessed notification suppression: limited offline approval request

2026-11-05 Asia/Tokyo. Proposal only; no permission to change actual configuration
or execute credentials, inference, callbacks, services or Loop.

## Confirmed obstacle

The current operator config contains a nonempty root notify string array.
Values were not displayed or copied into this document. The pinned official CLI
schema describes notify as an external notification command. Existing hook
admission missed it. The separate admission fix now rejects nonempty or malformed
notify, rather than silently disabling or executing that command. Other existing
hook checks remain. The read-only artifact check now correctly holds this profile.

## Proposed minimal offline implementation

Reuse existing profile/permit bindings, ToollessBoundary._binding/_command and
mock native CLI harness. Add no executor, service or general callback manager.

1. Add an optional exact notification-suppression policy to the nonsecret
   registered profile. Require this proposal's owner-approved digest and exact
   original config fingerprint. The existing permit must bind the complete
   profile; changing the policy/config invalidates that permit. Older profiles
   remain denied for nonempty notify. No implicit default or wildcard exception.
   The assessed original root value must be a nonempty string array; malformed
   values cannot qualify for this exception.
2. With that explicitly bound policy only, assess the original root notify entry
   as disabled FOR THIS CLI INVOCATION by the final literal override
   `-c notify=[]`. Do not edit/copy the actual config, inspect callback executables,
   execute/approve the original callback, or expose its arguments. Preserve its
   full original config hash in the workspace artifact and recheck before send.
3. Continue rejecting all other hooks and every nonempty/invalid nested notify.
   Suppression does not exempt hooks.json, dotenv, plugins or unknown callbacks
   from existing assessment. A changed config, missing override, wrong profile
   binding or unsupported CLI behavior stops before upstream transmission.
4. Prove on synthetic data that a configured harmless callback is not executed
   under the explicit override on normal completion, failure and cancellation;
   profile/config drift and missing approval are
   rejected, exact argv includes the suppression, and normal tool/input/lifetime/
   single-send/no-replay gates remain. Native evidence must not be substituted by
   a mock if the official CLI behavior cannot be established. Preserve failures,
   then independent review and normal local QA/CI/ordinary development-branch Push.

Approval changes only assessment of this specific, explicitly disabled callback
for an exact profile/invocation. It is a limited hook-policy exception and must
not be implemented before owner approval. If suppressing it needs another safety
exception, broader rights or config edits, stop and report rather than expand.

The separately proposed bounded run/workspace delegation remains a distinct
approval. Neither offline proposal permits real auth/refresh, a model request,
Loop launch, ACL/group changes, protected service operation or main update.
The agent owns internal CLI execution after later explicit real-operation grants;
the operator is not asked to run Python. Normal desktop notifications remain
unchanged outside an explicitly authorized C-min invocation.
