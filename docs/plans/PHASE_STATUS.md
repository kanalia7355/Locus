# Phase status — local synthetic-data prototype

Date: 2026-10-31. This tracks implementation progress, not production approval. Roadmap phase numbers are used below; PRODUCT_SPEC's MVP slice numbers differ.

| Phase | Implemented development slice | Remaining product work |
|---|---|---|
| 0 Bootstrap | Python/FastAPI and React/TS/Vite/Tailwind, locked dependencies, lint/types/unit/integration/browser checks, offline secret scan, package audits, CI files, local scripts, ADR/risk/usage records | Remote CI/branch protection/trusted review integration; host-enforced reviewer restrictions unavailable |
| 1 Authentication | Interactive local provisioning, unique IDs, Argon2id, expiring single-use temporary credentials, enforced first-login rotation, opaque digested sessions, idle/absolute expiry, revocation on change/logout, rate limits; admin-issued digest-only single-use recovery (24-hour expiry, all sessions revoked on redemption); web user provisioning (generated temporary password shown once, forced first-login rotation); web enable/disable (disabling purges sessions) | MFA; production TLS/session deployment policy approval and actual deployment validation |
| 2 Scoped authorization | Project and organization identity, backend permission templates, per-project membership, private documents/history/attachments, live document-role grants, deny-by-default API tests, concurrent role holdings (兼任 union) with explicit deny override (PH2-B `10ee9c4`), admin project/member/storage/load screens (P4B `b8bae86`) with combined-role/denial/effective-permission management UI (PH2-E `9738ca2`), owner-approved time-limited delegation grants with live expiry enforcement replacing the 409 placeholder (PH2-D `55d1c39`→`3150f6b`), storage-destination ACL research note (PH2-C `0e06107`) | **Historical snapshot (2026-11-09), superseded by the post-integration declaration below:** delegation grant/revoke UI screens were not yet implemented at this snapshot; org-wide delegation deferred by owner decision (project-scoped only); 元保存先ACL対応 implementation planning open/要決定 (research delivered); production data model/deployment items deferred per owner decisions and tracked in FINAL_ACCEPTANCE_CRITERIA.md |
| 3 Ingestion and retrieval | Bounded text ingestion, source/page/chunk metadata, queue/cancel, scanner default quarantine, synthetic-only successful seed path, lexical search, live permission checks, derived-data deletion | Approved scanner/parser sandbox, PDF/OCR, storage connectors, approved DB/vector/model adapters, resumable distributed jobs |
| 4 Researcher/admin UI | Approved sidebar/chat/composer/icon baseline, accessible navigation, IME handling, file/drop shared path, status/removal, project/reference scope, actual source viewer, owner history, mobile checks; all five owner-approved Phase-4 remainder priorities integrated (running-question cancellation `5a7848c`; project/storage settings + load display `b8bae86`; structured comparison tables `c381023`; destructive-operation confirmations `a30ec52`) | Phase 4 is NOT declared complete. Actual local LLM streaming, representative-user usability and accessibility audit beyond current checks, measured representative concurrency/capacity, priority/fairness, and other original requirements remain. Production items stay deferred as recorded. |
| 5 Roles/audit and optional extensions | Project role template cloning with permission ceiling, chips and scope preview, document publication preview, metadata-only audit, user listing. **Historical Phase-2 snapshot (2026-11-09), superseded by the post-integration declaration below:** time-limited delegation was implemented in the backend (PH2-D); its grant/revoke UI screens were then still tracked as remaining | GraphRAG, plots and cloud adapter deferred until their data/model/provider requirements are approved |

## Phase-4 remainder integration and review evidence — 2026-11-08

All five owner-approved Phase-4 remainder priorities are implemented and
integrated with these source commits: (1) running-question cooperative
cancellation `5a7848c`; (2) project/storage settings and (3) load display
`b8bae86`; (4) structured comparison tables `c381023`; (5) destructive-operation
target confirmations `a30ec52`. The independent aggregate review PH4-RV returned
**accept after minor fixes**. Its conditions are reconciled in this fix cycle;
this is not a claim that all Phase-4 product requirements or production work are
complete.

Integrated HEAD `183ccc31211f18570229dbb94985b7c3c26a7f6c` passed Prototype
quality (run `42444300133`), Loop engine checks (run `42444300019`, all four
matrix jobs), and PR title convention (run `42444300016`). P4D integrated HEAD
`a30ec5227b754f7d0d480d5a8ed3307e4d0d51b6` passed Prototype quality
(`42443623239`), Loop engine checks (`42443623273`, all four matrix jobs), and
PR title convention (`42443623262`). The P4D feature branch at
`5d779b316bdcb9a12b6b7d38b70566c400692f62` passed Prototype quality
(`42441474907`), title convention (`42441474829`), and Loop engine checks on
attempt 2 (`42441474871`). The first Windows/3.11 racing-controller failure
was a transient flake; the same-SHA rerun passed without a code change. This is
not a repair-based pass or an inferred result from a different SHA.

The PH4-FIX fix-cycle implementation `6d03c7ab1a5a70eb9fa2758741f9c32697d7bccd`
passed local QA (pytest 1145 passed/18 skipped; Ruff check/format; mypy; secret
scan 0; frontend lint, 63 Vitest tests, build, and 12 Playwright tests). Its exact
branch-head CI passed Prototype quality (`42446611321`), Loop engine checks
(`42446611336`, all four matrix jobs), and PR title convention (`42446611259`).
The display-only regression leaves server-facing data unchanged. A fully
recreated Python 3.13 QA venv imported `_cffi_backend` and ran Playwright
successfully.

Production deployment, production storage, real-data validation, broader
security/operations acceptance, and remaining product requirements stay
deferred/open. No production or full Phase-4 completion claim is made.

## Phase 2 completion declaration (verified scope) — 2026-11-09

> **Superseded snapshot, dated 2026-11-09:** this first declaration records the PH2-CA state before delegation-UI integration. The post-integration declaration below is the current Phase-2 record; history and original evidence are retained here.

Phase 2 (認可・管理) is declared COMPLETE within the owner-approved prototype
scope, based on the PH2-CA completion audit (2026-11-09). Evidence:

- Features integrated into `loop/local-development`: concurrent role holdings
  (union) and explicit deny (`10ee9c4`), admin project/member/storage/load
  screens (`b8bae86`), combined-role/denial/effective-permission management UI
  (`9738ca2`), storage-destination ACL research note (`0e06107`), and
  owner-approved time-limited delegation grants with live expiry enforcement
  (`55d1c39`, integrated `3150f6b`), replacing the disabled 409 placeholder.
- Owner decisions recorded 2026-11-09: all 12 delegation-spec items approved
  with binding conditions (TTL 24h default/7d max/15m min, live revalidation;
  grantors = project owner + org admin; family/version re-grant; org-wide
  grants deferred); MFA confirmed required for the final product with the
  prototype deferral standing; post-phase automatic main integration adopted.
- Audit verification at base `a473bf6` — identical to `5dceb62` except for
  that commit's docs-only ledger addition (qa-venv Python 3.13):
  full pytest **1156 passed / 18 skipped** (1174 collected) in the PH2-CA Python 3.13 QA environment, where the pinned native CLI fixture was not provisioned; this is the 18-skip environment result, not the later PH2-RV local run described below. Ruff check clean;
  Ruff format check 128 files already formatted; mypy `backend/app` 9 files
  clean; offline secret scan 0 findings. New regressions cover delegation
  (grant/expiry/subset/self-escalation/revocation/family rules/membership
  gate), concurrent-roles union + deny precedence, and the admin UI flows
  (`tests/test_delegations.py` 10 test functions at this Phase-2 audit baseline; the later delegation-UI integration added one API test, bringing the current file to 11; `tests/test_concurrent_roles.py` 8,
  `tests/test_admin_project_storage_load.py` additions).
- Hosted CI at the exact integrated heads: `a473bf6`
  (quality 42461797597, engine 42461797637, title 42461797601) and `5dceb62`
  (quality 42461848831, engine 42461848837 four-matrix, title 42461848840) —
  all green; each feature branch was CI-green at its own implementation SHA
  before integration (evidence in the per-task files).

NOT claimed / explicitly remaining at this superseded snapshot: the delegation grant/revoke UI screens were
NOT yet implemented (backend APIs existed; tracked remaining Phase-2 web item);
org-wide delegation is deferred by owner decision; 元保存先ACL対応
implementation planning remains open/要決定 (research note only); production
items (TLS, MFA, LAN deployment, production DB, delegation retention) remain
deferred per owner decisions and tracked in FINAL_ACCEPTANCE_CRITERIA.md.
Observation: prior local full-suite runs showed a recurring load-flake in
`tests/integration/test_trial_input_native_v2.py` (with
`test_notification_native.py`); those tests pass in isolation and in the hosted
four-matrix CI, and in this audit's local run they were collected but skipped
as environment-gated (pinned native CLI not provisioned). This is recorded as
an observation, not a pass/fail claim.

Historical NEXT GATE at this snapshot: aggregate independent review of the
integrated Phase-2 state before main integration. This gate was subsequently
completed and the Phase-2 main integration recorded below; the original
statement is retained as history, not as the current gate.

## Acceptance interpretation

2026-11-06: the optional local provenance slice exposes
`GET /api/documents/{id}/related` (optional `conversation_id`). It returns up to ten
currently readable/retrievable same-project documents, ranked by shared lexical
terms, with up to ten actual source/target chunk IDs and page references per link.
Japanese character bigrams support non-whitespace-delimited text. This is an
explainable lexical relationship, not a semantic graph or model-generated finding.
Private documents and conversation-bound attachments retain their live ACLs.
Requests are rate-limited; authorized chunks are still scanned under the prototype
transaction lock, so this is not a production capacity claim. The existing source
dialog can load these relationships on demand, show common terms and page
references, and open the related original through a fresh authorized chunk read.
Pending retrieval is cancelled when its view is discarded. An optional native SVG
diagram displays only the fetched source-to-target lexical relationships (at most
ten) alongside the unchanged accessible list and page/chunk evidence. Toggling
the diagram makes no additional request. Refresh starts by removing both prior
list and diagram. A persistent graph index and semantic GraphRAG remain unimplemented.

Citation links and related-document links open the exact indexed chunk, show the
document name, and focus/scroll to the referenced page and chunk. A removed or
reindexed target is reported as unavailable rather than silently substituted.
The source heading and Close control remain visible while reading long documents.

Publication UI now explicitly chooses read-only (the default) or read plus
retrieval, previews that choice with the role and project scope, and warns that
saving replaces existing grants. Failed saves retain the input. Browser tests
use a second user to verify that read-only grants allow source reads but not
chat retrieval or related-document exploration; backend policy is unchanged.

Publication now accepts existing custom role IDs from the document's own project,
matching assignment and effective-permission resolution. Role editors can select
read-capable custom roles using the existing role catalog endpoint; catalog access
still requires `manage_roles`. Read-only roles cannot acquire retrieval through a
document grant, and foreign-project IDs are rejected even within the same organization.

Custom role configuration now supports project-scoped name/permission updates
through the existing role editor. Saving immediately affects existing assignees,
while role IDs, memberships and document grants remain stable. The complete result
must stay within the editor's current non-administrative permission ceiling;
built-in templates cannot be edited. Updates and metadata-only audit records are
transactional. This completes configuration within the approved prototype scope,
not production delegation or web-based identity/membership administration.

The administrator model page now supports explicit, read-only discovery of Ollama
registration metadata and GGUF/Safetensors candidates in configured local model
folders, including the Hugging Face cache suggestion. Candidate selection does
not enable model loading, import, downloads or inference. Default chat remains lexical
retrieval; the separately approved optional Ollama adapter can generate answers after
an explicit administrator runtime setting and local-only confirmation. See [LOCAL_MODELS.md](../LOCAL_MODELS.md) for activation scope, limits
and the distinction between synthetic verification and actual model operation.

Isolation and citation tests verify the implemented local paths. They do not prove every path of an unimplemented vector/graph/model subsystem. The default path emits quoted source excerpts; optional Ollama output is marked as unverified suggestions, not research findings. Quarantined uploads are not called indexed/read. Queue limits are development safety limits, not tested user capacity.

The remaining production decisions are not silently resolved. No production/LAN deployment, GitHub operation or external AI call is part of this delivery.

## Local-model execution evidence — 2026-11-06

The optional Ollama RAG adapter and answer persistence are implemented. Mock QA
covers live session/source/settings revocation, partial-source history hiding,
no tool execution, bounded HTTP, no automatic retries and browser activation.
At code commit `2ca2c14`, application CI and all Windows/Linux Python 3.11/3.13
engine jobs passed. This is not evidence of successful real model inference.

The owner-authorized single `gemma3:4b` request with synthetic content stopped at
30.008 seconds without a validated response. It remains failed/indeterminate;
its one attempt was consumed, not retried. A later separately authorized read-only
`/api/ps` check returned no loaded models about 74 minutes after that trial.
This delayed observation does not establish why the original request timed out.
A separately approved new synthetic question completed through the existing
`gemma3:4b` adapter in 39.089 seconds with a validated 17-character answer that
mentioned the expected 20-minute duration. The preceding `/api/ps` was empty and
the following response reported the model loaded. This proves one real adapter
connection, not normal application RAG end-to-end quality or capacity. The trial
used a process-local 120-second deadline and did not change normal application
configuration. The separately approved offline runtime setting adds an explicit
administrator choice of 30 or 120 seconds, default/reset 30, bound to the same
configuration version as the model. No production rollout, completed
Phase audit, main merge, release version/tag or 30-minute Loop run is claimed.

Local ownership administration now records project creation and membership
assignment/removal through the existing metadata-only audit table in the same
transaction as the change. The `unassign` CLI exposes existing membership removal;
its regression tests confirm immediate document/conversation denial for existing
sessions and rollback when an audit record cannot be written. No actual account
or membership was changed by this development task. Web delegation stays disabled.

A subsequent owner-authorized synthetic backend-API trial at code `452bb47`
returned a validated real gemma3:4b answer in 10.543 seconds, including the expected
180/200 temperature values. SQLite reopen preserved the answer and citations;
source-grant revocation hid the whole answer and model, administrator access to
another user's history was denied, and the new runtime reset to disabled/30s.
The preparation initially misclassified the correct conversation-creation 201,
before any model dispatch. Continuation reused the confirmed inventory checkpoint
without another inventory request; total real traffic remained one inventory GET
and one model POST. Both original and continuation records were retained.
This proves the bounded synthetic backend path, not production data handling,
real-browser/model integration, crash recovery, capacity or all-Phase completion.
A separate mock regression now reopens the same SQLite and verifies that losing
just one shared input source hides the whole answer while other citations remain.

The ingestion worker now applies the same live owner/project/attachment checks
both before calling a scanner adapter and before publishing indexed chunks.
Previously only the publication check was present: already revoked queued work
could still pass its content to the scanner. Regression tests first reproduced
that call for membership/upload revocation, disabled accounts, forced rotation,
and lost attachment retrieval permission; all now cancel without a scanner call.
Revocation during scanning still prevents publication. No real scanner is enabled;
the unavailable default continues to quarantine uploads rather than mark them clean.

The optional ClamAV adapter is now implemented under owner-approved offline scope.
Only explicit server-side LOCUS_SCANNER=clamav selects fixed loopback INSTREAM;
construction does not connect, and the unavailable default remains unchanged.
Mock transport covers framing, strict EOF response, deadlines, limits and cleanup.
Real daemon identity, signature freshness, deployment isolation and detection remain
unverified and require separate owner-authorized operational validation.

## Ingestion progress refinement — 2026-11-06

The ingestion screen now summarizes only currently visible project documents,
separating queued/scanning/ready/quarantined/failed/cancelled and unknown states.
Pending work triggers sequential status GETs after a two-second delay; each GET
has a ten-second deadline. Navigation/project changes abort the poll, terminal
states stop it, and failures/expiry stop automatic requests with a stale-state
notice. Manual refresh remains available. This is not global request exclusion,
a completion ETA, folder inventory, durable notification history or a fair model queue.
Frontend unit43, lint/build, and browser10 passed; the strengthened narrow-width
case also passed after waiting for sidebar animation completion. Independent
review findings about deadline/stopped-state wording were fixed in one cycle.

## Phase-1 auth-slice consolidation evidence — 2026-11-07

This records implemented development-slice evidence only; it is not a Phase-1
completion claim. MFA and production TLS/session deployment remain unresolved.

- Recovery: admin-issued, digest-only, single-use code with 24-hour expiry;
  redemption changes the credential and revokes all sessions. `loop/PH1-recovery`
  implementation/CI-repair `bd9f2cf` (CI-green
  branch head `93d1633`), integrated into `loop/local-development` as `1056021`.
  Branch QA: pytest **1101 passed, 18 skipped**, Ruff check/format, mypy, and
  secret scan passed (0 findings).
- Web account enable/disable: administrator UI toggle; disabling deletes live
  sessions and enabling does not recreate them. `loop/PH1-account-toggle`
  `a31d570`, integrated
  as `b7adb42`; CI repair `ed11f73`. QA: pytest **1098 passed, 18 skipped**,
  toggle tests 8, frontend tests 49, Playwright 10, lint/typecheck/build and
  Ruff/mypy/secret scan passed. The integrated push `c28a280` completed all
  workflows successfully, including the Windows engine matrix.
- Web user provisioning: administrator-created users receive a generated
  temporary password once and must rotate it on first login. `loop/PH1-web-provisioning`
  final code `a355efb`
  (CI-green branch head `76ba39a`), integrated as `2610b70`. QA: pytest
  **1094 passed, 18 skipped**, frontend tests 49, Playwright 10, lint/build,
  Ruff/mypy and secret scan (0 findings) passed. The integrated push after
  provisioning (`590f40a`) completed all workflows successfully.
- Cross-job regression at the consolidation worktree's code base `fa6e7c5`:
  pytest **1113 passed, 18 skipped**; Ruff check passed and format check found
  117 files already formatted; mypy passed for 7 source files; offline secret
  scan found 0 issues; frontend lint and production build passed; Vitest
  **52 tests / 13 files passed**; Playwright **10 passed**. No test-level
  collisions surfaced; tests were not changed.
- Unresolved cross-slice security finding (medium; reproduced locally): an
  already-authenticated system-admin `Principal` can still provision a user
  after another admin disables that actor and revokes its sessions. The
  `POST /api/admin/users` route resolves `Actor` before calling
  `Service.provision_web_user`, which trusts the cached `system_admin` flag and
  does not revalidate the session in the mutation transaction. A temporary-DB
  reproduction confirmed the stale session itself now returns 401, yet
  `provision_web_user(stale_principal, ...)` still creates the user. No feature
  code or tests were changed in PH1-G; recommend session revalidation inside
  the provisioning transaction plus a regression test. Independent review and
  authorized implementation should resolve/assess this before treating
  immediate disable as applying to in-flight admin mutations.

This local regression is not CI evidence for the later PH1-G documentation
commit. The aggregate still requires independent review and all required CI
checks green at its exact pushed HEAD, before any Phase-1 completion decision.

## Phase 1 completion declaration (prototype scope) — 2026-11-07

Phase 1 is declared COMPLETE within the owner-approved prototype scope. Evidence:
- Features integrated into `loop/local-development`: recovery flow (`1056021`),
  account enable/disable (`b7adb42`), web user provisioning (`2610b70`),
  provisioning race fix (`0365a6a`), consolidation docs (`a55d856`).
- Independent review: aggregate review PH1-K verdict "accept after minor fixes";
  its condition (re-review of the integrated race fix) closed by PH1-K2 with
  verdict "accept" (no unresolved findings, no weakening, secret scan 0).
- Owner decisions recorded 2026-11-07: MFA intentionally out of scope for the
  LAN-limited prototype; production TLS/session deployment deferred to the
  production-deployment phase; LAN deployment verification separated from code
  completion and mandatory at the later deployment gate (never claimed as
  verified); admin-read revocation reflects at the next authorization check with
  revalidation in long operations.
- QA at the completion HEAD: full pytest 1114 passed / 18 skipped; ruff check +
  format; mypy backend/app (7 files); offline secret scan 0 findings; branch CI
  all green at every integrated source HEAD; exact-HEAD CI green on the completion
  push (all three workflows, four-matrix engine).
- Version bumped 0.1.0 -> 0.2.0 (pyproject, frontend package, loop_engine).

NOT claimed: production deployment, LAN host verification, MFA, TLS/session
production configuration. These remain tracked in the backlog and the
production-deployment phase's completion conditions (never silently resolved).

## Phase 2 completion declaration (verified scope) — 2026-11-09

Phase 2 (認可・管理) is declared COMPLETE within the owner-approved prototype
scope, per the adopted main-integration mechanism. Integrated and verified:
- Concurrent role holdings (兼任, union permissions) with per-role intersection
  ceilings and legacy migration (`10ee9c4`, PH2-B).
- Explicit deny permissions with deny-overrides-allow, deny-by-default
  preserved, cross-scope deny containment (`10ee9c4`).
- Time-limited delegation grants per the owner-approved specification:
  family/version scheme, TTL 15min–7days (default 24h), live revalidation at
  every authorization point, grantor-authority-loss live invalidation
  (fail-closed), recipient cancellation, membership-gate independence,
  dedup/no-revival/no-coexistence (`3150f6b`, PH2-D). The disabled 409
  placeholder was replaced by the real fail-closed implementation.
- Combined-roles/deny management UI (`9738ca2`, PH2-E).
- Storage-destination ACL research + implementation plan (`0e06107`, `acdbf2c`
  — implementation planning remains open/要決定 as recorded).
- Admin project/storage/load screens (`b8bae86`, PH1-P4B).

Evidence: independent aggregate review PH2-RV verdict "accept after minor
fixes" with NO critical/high authorization defects (14 authorization paths
spot-checked); the review's integration condition (full-suite rerun in a
supported environment) is satisfied by the hosted CI four-matrix runs (all
success at db33ff8) — the local Windows pinned-CLI fixture was lost in this
environment and those loop_engine native-launch tests pass in the hosted
matrix and in isolation when the fixture is present (recorded as an
environment observation, not a code defect). The PH2-RV local run was 1156
passed, 9 skipped, and 9 failed (1174 collected); the failures were the
environment-dependent native-CLI tests, not passing or skipped tests.

The delegation grant/revoke UI is implemented and integrated into
`loop/local-development`: feature commit `c1c5f4c`, integration commit
`a445b3f`, and integration/CI record `84dc1eb`. The earlier Phase-2 core
main integration is `c307939`; this UI integration does not claim it is in main.
The UI covers grant creation, grant history/state, revoke confirmation, and
recipient cancellation; delegation tests increased from 10 to 11 functions.
Remaining, explicitly tracked (NOT silently resolved): delegation recipient-side
UI refinement and any org-level management surface remain future work pending
the org-model decisions; storage-destination ACL implementation planning
(要決定 items in PHASE2_STORAGE_ACL_IMPLEMENTATION_PLAN.md); MFA (required for
the final product, prototype-deferred per owner decision); production
TLS/session/LAN-deployment verification (deployment gate).

Skipped/failure counts reflect different local environments and are not
interchangeable: PH2-CA recorded **1156 passed / 18 skipped** (1174 collected)
in its Python 3.13 QA environment, where the pinned native CLI fixture was not
provisioned. PH2-RV later recorded **1156 passed / 9 skipped / 9 failed** in a
different local environment; the nine failures were environment-dependent
native-CLI tests because the pinned `gpt-6.1-sol` model entry was absent. Those
failures are not passes or skips. The Phase-2 review's full-suite condition was
instead met by the recorded hosted four-matrix CI at `db33ff8` (all success).

Version bumped 0.2.0 -> 0.3.0.
