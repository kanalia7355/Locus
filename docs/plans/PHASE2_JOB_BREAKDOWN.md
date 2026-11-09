# Phase 2 job breakdown — scoped authorization & delegated admin

Date: 2026-11-07. Prepared by the orchestrator from `docs/plans/PHASE_SPEC_RECONCILIATION.md`
Phase-2 row, `docs/requirements/PRODUCT_SPEC.md`, `docs/architecture/ARCHITECTURE.md`,
and the current integrated code (`loop/local-development` @ main-reconciled HEAD,
includes the Phase-4 remainder jobs in flight: P4A cancellation, P4B admin screens).

## 1. 前提仕様 (what already exists — verified implementation)

| 領域 | 既存実装 | 根拠 |
|---|---|---|
| 組織/project境界 | organizations, projects, membership, per-project scoping | `backend/app/service.py` (projects/memberships), `tests/test_api.py` |
| private履歴/添付 | conversations/attachments owner-scoped; live ACL rechecks | `backend/app/service.py` (send/history/attachments), `tests/test_security.py` |
| 資料grant (live) | publication preview + read/read+retrieval grants, same-project custom role IDs | `backend/app/service.py` (publish), `tests/test_custom_role_publication.py` |
| custom role作成/更新 | role editor within non-administrative ceiling, built-ins immutable, transactional audit | `tests/test_role_updates.py` |
| subset制限 | permission subsets enforced at creation/update; no elevation | `backend/app/service.py` roles |
| 監査 | metadata-only `_audit` in-transaction | `backend/app/service.py`, `tests/test_administration_audit.py` |
| (Phase 4で着手済み) Web所属/project管理 | P4B: admin project list/create + member assign/remove screens & endpoints (in flight) | `docs/plans/agent-work/PH1-P4B-admin-screens.md` |

## 2. 実装差分 (remaining deltas per the reconciliation doc)

| # | 差分 | 現状 | 分解後ジョブ |
|---|---|---|---|
| D1 | 期限付き委任が409で無効 | delegation grant path exists but disabled | PH2-A (spec) → PH2-D (impl) |
| D2 | 期限・取消仕様が未確定 | no agreed semantics | PH2-A (spec draft; owner decisions marked) |
| D3 | 兼任 (multiple concurrent role holdings) semantics undecided | single role per membership? (verify) | PH2-B (impl) |
| D4 | 明示deny permissions undecided/unimplemented | allow-list-only permission model | PH2-B (impl) |
| D5 | 元保存先ACL対応 (ACL for original storage destinations) semantics unclear | local bounded storage; meaning to be pinned down | PH2-C (research/design) |
| D6 | Web所属/project管理の残り | P4B covers project+members; role-level web management may remain | assessed after P4B integration |
| D7 | 委任subset/scope/expiryと自己昇格拒否の回帰 | not implementable before PH2-A | PH2-D (impl) |

## 3. ジョブ単位のタスク定義

### PH2-A — Delegation specification (design-only, no code)
Deliverable `docs/plans/PHASE2_DELEGATION_SPEC.md`: expiry model (absolute TTL?
max window? renewal?), subset/scope narrowing rules (delegator's ceiling is the
hard cap; delegate can only receive a subset), revocation/cancellation semantics
(immediate revocation → live-session/data recheck mirroring the Phase-1 pattern),
self-privilege-escalation denial rules, grant data model (immutable versioned
grants? audit), interaction with document grants and custom roles, and the
regression-test plan for 「異なる利用者/組織/権限変更中の全データ経路」. Every
undecidable point is marked 【要決定】 (e.g. default max expiry, whether delegates
may re-delegate). Reuses existing conventions only; weakens nothing.

### PH2-B — Concurrent role holdings + explicit deny (implementation, backend+role model)
Investigate current membership/role cardinality, then implement 兼任 (a user may
hold multiple roles within a project/organization with union semantics and the
existing subset ceiling) and 明示deny (explicit deny entries that override
allow within the same scope, deny-by-default preserved). Full regression suite
must prove no elevation path (owner's verification column: 自己昇格拒否). Depends
on nothing from PH2-A; independent data-model work.

### PH2-C — 元保存先ACL 対応 research + design (read-mostly, docs only)
Pin down the meaning of 元保存先ACL対応 (ACL semantics for original storage
destinations: where documents came from, how deletion/moves propagate, how the
existing quarantine/local storage behaves) against `docs/INGESTION_SCANNER.md`,
`backend/app/scanner.py`, service storage paths. Deliver a short design note
with findings and a proposal; no code.

### PH2-D — Delegation implementation (after PH2-A + owner answers)
Time-limited delegation grants per the approved spec: grant/revoke endpoints,
expiry enforcement at every authorization check (live recheck, no long-lived
caches), subset validation (never exceeds delegator ceiling), self-escalation
denial, transactional audit, regressions for the full verification column.
NOT dispatched until PH2-A lands and its 【要決定】 items are answered.

### PH2-E — Web role/membership management completion (assessed after P4B lands)
Whatever P4B does not already cover from the Phase-2 web-management delta.

## 4. Dispatch status

- Now running: PH2-A (design, slot D), PH2-B (implementation, slot E).
- Queued: PH2-D (blocked on PH2-A + owner answers), PH2-E (assessed post-P4B).
- In flight (other tracks): PH1-2A (slice 2a), PH1-P4A delivery relaunch, PH1-P4B relaunch.

Completion conditions for Phase 2 (per owner rules): all deltas resolved or
explicitly deferred with owner decisions recorded, independent review of the
aggregate, all-CI-green at the exact HEAD, then squash merge to main + version bump.
