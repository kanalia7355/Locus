# Phase 進捗サマリ: `phase-2-authz`

- **対象 Phase**: `phase-2-authz`（`PH-ROADMAP-2` / 旧 `P2` — Scoped authorization and delegated administration; `docs/plans/MASTER_IMPLEMENTATION_ROADMAP.md` 参照）
- **対象ブランチ**: `phase/2-authz`（ベース: `main` / 現行統合ブランチ `loop/local-development`）
- **最終更新日時**: `2026-11-13T18:36:17+09:00`
- **更新責任者**: オーケストレーター (`gpt-6-luna`) ※ワーカーによる編集禁止

---

## 1. Phase 完了条件（Gate Criteria）

- [ ] 対象要件 ID（`docs/plans/REQUIREMENTS_TRACEABILITY_MATRIX.md` の `PH-ROADMAP-2`: `IAM-006`, `IAM-007`, `IAM-008`, `IAM-009`, `IAM-010`, `IAM-011`, `IAM-012`, `IAM-013`, `IAM-014`, `IAM-015`, `DATA-008`（Phase 2 手動アップロード・即時アクセス拒否範囲）, `DATA-010`, `UI-008`）の全タスクが `status: done` であること（Owner 決定によりゲート付き後続 Phase へ繰り延べられた項目を除く）
- [ ] Phase 節目のフルテストスイート検証が PASS していること
- [ ] `phase/2-authz` ブランチの GitHub Actions CI がすべてグリーン（`success`）であること
- [ ] 未解決の `blocked` タスクや人間判断待ち（Escalation）が残っていないこと

---

## 2. 事前コード・テスト検証で「実装済み」と確認できた要件一覧（2026-11-13 実機検証）

計画書の記載を鵜呑みにせず、`backend/`・`frontend/`・`tests/` の実コードと実機テスト（`.venv313` pytest **86 passed**、Frontend Vitest **6 files / 27 passed**）を照合した結果、以下の要件・スライスは実装済みかつテスト通過を確認した。

| 要件 ID | 要件概要 | 検証結果 | 実装根拠ファイル | テスト根拠・実機検証結果 |
|---|---|---|---|---|
| `IAM-006` | 組織・プロジェクト・利用者分離（Org/project/user isolation） | **実装済み**（プロトタイプ SQLite 範囲） | `backend/app/service.py` (`projects`, `_membership`, `_document`, `_conversation`), `frontend/src/AdminSettings.tsx` (`AdminProjects`) | `tests/test_api.py`, `tests/test_security.py`, `tests/test_admin_project_storage_load.py` (`PASS`) |
| `IAM-007` | 既定拒否とサーバー側強制（Deny by default & server enforcement） | **実装済み** | `backend/app/service.py` (`require`, `_permissions`, `_can_read`), `backend/app/main.py` (`boundary`, `actor`) | `tests/test_security.py`, `tests/test_api.py`, `tests/test_delegations.py`, `tests/test_concurrent_roles.py` (`PASS`) |
| `IAM-008` | 文書 ACL と検索時フィルタ（Document ACL & filtered retrieval） | **実装済み**（手動アップロード・ローカル検索範囲） | `backend/app/service.py` (`publish`, `_can_read`, `documents`, `chunks`, `related`, `send`, `_citations`, `_generated`), `frontend/src/App.tsx` | `tests/test_custom_role_publication.py`, `tests/test_api.py`, `tests/test_delegations.py`, `frontend/src/Publication.test.tsx` (`PASS`) |
| `IAM-009` | 個人会話・添付の非公開性（Private conversations & attachments） | **実装済み** | `backend/app/service.py` (`_conversation`, `conversations`, `send`, `upload` attachment checks) | `tests/test_api.py`, `tests/test_security.py`, `tests/test_delegations.py` (`PASS`) |
| `IAM-010` | ロールテンプレートと上限付きカスタムロール（Role templates & constrained customization） | **実装済み** | `backend/app/service.py` (`roles`, `create_role`, `update_role`, `_permission_ceiling`), `frontend/src/App.tsx` (`RoleEditor`) | `tests/test_role_updates.py`, `tests/test_custom_role_publication.py`, `frontend/src/RoleEditing.test.tsx` (`PASS`) |
| `IAM-012` | 複数ロール兼任（許可の和集合）とプロジェクト単位の明示的拒否優先（Concurrent roles & explicit deny） | **実装済み**（`PH2-B` + `PH2-E`） | `backend/app/service.py` (`membership_roles` テーブル, `_held_roles`, `_role_access`, `add_role_holding`, `remove_role_holding`, `set_membership_denials`), `frontend/src/AdminSettings.tsx` (`AdminProjects`, `MembershipDenials`) | `tests/test_concurrent_roles.py` (`8 passed`), `frontend/src/AdminSettings.test.tsx` (`9 passed`) |
| `IAM-013` | プロジェクト所属（Membership）と委任（Delegation）の独立性 | **実装済み**（`PH2-D`） | `backend/app/service.py` (`_role_access`, `_permissions`, `create_delegation`) | `tests/test_delegations.py` (`test_delegation_requires_project_membership_and_stays_project_scoped` ほか `11 passed`) |
| `IAM-015` | メタデータのみのトランザクション監査（Metadata-only transactional audit） | **実装済み**（`PH1-2A` + `PH2-2AF` 修正込み） | `backend/app/service.py` (`_audit`), `backend/app/agents/registry.py` (`AgentRegistry`), `backend/app/main.py` (`validated_agent_body`) | `tests/test_administration_audit.py`, `tests/test_agents_registry.py` (`12 passed`, 未認証 flood rate-limit・malformed 入力時の1回監査を含む) |
| `DATA-010` | 個人資料・共有資料・会話添付の分離（Personal/shared/attachment separation） | **実装済み** | `backend/app/service.py` (`upload`, `publish`, `documents`, `_can_read`), `frontend/src/App.tsx` | `tests/test_api.py`, `tests/test_security.py`, `frontend/src/Publication.test.tsx` (`PASS`) |
| `UI-008` (管理画面群) | 管理画面（プロジェクト・メンバー兼任/拒否・保存先状態・負荷・削除確認） | **実装済み**（`PH1-P4B`, `PH1-P4D`, `PH2-E`, `R-STORAGE-1/2`） | `frontend/src/AdminSettings.tsx` (`AdminProjects`, `AdminStorage`, `AdminLoad`), `frontend/src/ProvisionUser.tsx`, `frontend/src/App.tsx` (`AdminUsers`, `AdminList`) | `tests/test_admin_project_storage_load.py`, `frontend/src/AdminSettings.test.tsx` (`9 passed`), `frontend/src/ProvisionUser.test.tsx`, `frontend/src/AccountToggle.test.tsx` (`PASS`) |

### 部分実装（残タスクあり）または Owner 決定によりゲート付き繰延の要件

- **`IAM-011` / `UI-008`（管理委任 / 受領側 UI — Owner Entry 6 `DP-071`）**:
  - バックエンド API（`PH2-D`: `GET/POST/DELETE /api/admin/delegations` 等）および基本 UI（`PH2-UI`: `frontend/src/Delegations.tsx`）は実装済み（`tests/test_delegations.py` `11 passed`, `frontend/src/Delegations.test.tsx` `7 passed`）。
  - **未完点**: `docs/plans/OWNER_DECISIONS_2026-11-10-ENTRIES.md` Entry 6 (`DP-071`) で正式決定された「委任を受ける側の UI 改善（権限がない委任作成フォームを一般受領者に実行・操作させない UI 制御、付与元・権限範囲・有効期限・失効状態の明確化）」および `App.tsx` 内の古い文言（「管理権限の委任は無効です」「管理委任…は承認待ちです」）の解消が未完。→ **`T-PH2-001`** として起票。
- **`IAM-014`（実効権限プレビューと管理 UX の整合性）**:
  - `RoleEditor`・公開設定・`AdminProjects` の基本プレビューは実装済み。
  - **未完点**: `AdminProjects`（`frontend/src/AdminSettings.tsx` 303行目）のラベルが「実効権限（各ロールの和集合、拒否を適用後）」と記載されている一方、バックエンド `admin_projects` / `membership_roles` の `effective_permissions` は `self._permissions()`（有効な委任権限を含む）を返しており、ロール由来の権限と一時的な委任権限の区別がプレビュー上で判別できない。→ **`T-PH2-002`** として起票。
- **`IAM-008` / `IAM-011` / `IAM-012` / `IAM-015`（Phase 2 トレーサビリティ・計画書の実態同期）**:
  - `docs/plans/REQUIREMENTS_TRACEABILITY_MATRIX.md` および `docs/plans/PHASE_SPEC_RECONCILIATION.md` 等の計画・追跡文書で、`PH2-UI` が「未実装」、`PH2-2AF` が「未検証」のまま残っている食い違いがある（※ `PROTOCOL.md` §2 により `docs/plans/**` は人間専任パスであるため、ハーネス自動検証テストまたは人間承認下でのみ扱う）。→ **`T-PH2-003`** として Phase 2 横断の回帰検証・受入証跡タスクを起票。
- **`DATA-008`（外部保存先コネクタと元保存先 ACL 同期）**:
  - `docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md` Q5/Q6 および `DEFERRED_WITH_GATES_2026-11-09.md` Gate D-3 により、外部コネクタ（ローカルフォルダ・NAS・オンラインストレージ）は後続の Connector Phase（P3 以降）へゲート付き繰延。手動アップロード・検査状態表示（`R-STORAGE-1`, `R-STORAGE-2`）および権限喪失時の即時アクセス拒否は実装・検証済み。
- **`IAM-016`（監査ログの改ざん防止・長期保持ポリシー）**:
  - `docs/plans/OWNER_DECISIONS_2026-11-09-EVENING.md` Q7 および `DEFERRED_WITH_GATES_2026-11-09.md` Gate D-1 により、本番データベース・監査保護・保持期間（P6）へゲート付き繰延。

---

## 3. タスク一覧と現在状態

| Task ID | タイトル / 要件 ID | Weight | Status | Assignee | Model | Reviewer | Attempts | Worktree / Branch | Updated |
|---|---|---|---|---|---|---|---|---|---|
| `T-PH2-001` | Delegation recipient UI and unauthorized creation guard (`IAM-011`, `UI-008`, `DP-071`) | `medium` | `blocked` | `agy` | `Gemini 4 Argon` | `agy/Claude Sonnet 5.5` | `3` | `task/T-PH2-001` | `2026-11-13T15:02:02+09:00` |
| `T-PH2-002` | プロジェクトメンバー実効権限プレビューにおける委任権限の明示と表示整合 (`IAM-011`, `IAM-012`, `IAM-014`) | `medium` | `done` | `agy` | `Gemini 4 Argon` | `agy/Claude Sonnet 5.5` | `1` | `task/T-PH2-002` | `2026-11-13T13:13:15+09:00` |
| `T-PH2-003` | Phase 2 認可・委任・監査境界の統合回帰テスト補強 (`IAM-006`〜`IAM-015`, `DATA-008`, `DATA-010`) | `medium` | `review` | `agy` | `Gemini 3.8 Flash` | `agy/Gemini 4 Argon (Medium)` | `1` | `task/T-PH2-003` | `2026-11-13T18:36:17+09:00` |

---

## 4. モデル別 QA 通過率集計（OpenCode 無料プール・agy 実績追跡）

`docs/agent/MODEL_ROTATION.md` §3 に基づき、各モデルの割当回数・QA 通過（`done`）回数・差し戻し回数・枠切れ（Quota）発生回数を集計する。

| Runner | Model | 割当回数 | QA 通過 (`done`) | レビュー/QA 差し戻し | 枠切れ切替 (Quota) | QA 通過率 |
|---|---|---|---|---|---|---|
| `agy` | `Gemini 4 Argon` | 2 | 1 | 1 | 0 | 50% |
| `agy` | `Claude Opus 5.5` | 0 | 0 | 0 | 0 | - |
| `agy` | `Claude Sonnet 5.5` | 0 | 0 | 0 | 0 | - |
| `agy` | `Gemini 3.8 Flash` | 1 | 0 | 1 | 0 | 0% |
| `agy` | `GPT-OSS 120B` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/beam-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/big-pickle` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/deepseek-v4.1-flash-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/flint-40b-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/glm-5.3-flash-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/iceman-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/inkling-2-small-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/longcat-2.5-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/mimo-v2.6-flash-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/minimax-m3.1-flash-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/nemotron-3.5-lightning-free` | 0 | 0 | 0 | 0 | - |
| `opencode` | `opencode/nemotron-3.5-super-vl-free` | 0 | 0 | 0 | 0 | - |
| `ollama` | `ollama/gemma3:4b` | 0 | 0 | 0 | 0 | - |

---

## 5. Blocked タスク・計画書と実態の食い違い・人間へのエスカレーション事項

仕様解釈の曖昧さ、設計トレードオフ、試行上限（最大3回 / レビュー最大2周）到達、または全モデル枠枯渇により停止した項目を記録する。

- **計画書とコード実態の食い違い（人間確認・参考記録 — `docs/plans/**` は `PROTOCOL.md` §2 によりワーカー改変禁止）**:
  1. `docs/plans/REQUIREMENTS_TRACEABILITY_MATRIX.md`（28, 31, 57行目）および `docs/plans/PHASE_SPEC_RECONCILIATION.md`（91行目）では「管理委任 UI（`PH2-UI`）は未実装」と記載されているが、実コードには `frontend/src/Delegations.tsx` と `frontend/src/Delegations.test.tsx` が存在し、`App.tsx` に統合済みである。
  2. `docs/plans/REQUIREMENTS_TRACEABILITY_MATRIX.md`（32行目 `IAM-015`）では `PH2-2AF`（AgentRegistry の未認証 flood 制限と監査順序修正）が「未検証」と記載されているが、実コードの `backend/app/agents/registry.py`・`backend/app/main.py`・`tests/test_agents_registry.py`（`12 passed`）にて実装・検証済みである。
  3. `docs/plans/PHASE_STATUS.md`（327〜341行目）では `loop/rstorage1-manual-upload` / `loop/rstorage2-scanner-status-fix` が未マージの進行中ブランチとして記載されているが、現行チェックアウトの `backend/app/scanner.py`・`backend/app/service.py`・`frontend/src/AdminSettings.tsx` には両コミットの変更（`ScanResult` の `clean`/`rejected`/`unavailable` 分離と `scanner_last_outcome` 表示）が既に反映されている。
  4. `main` ブランチ（`ab3db19` 時点）には `loop/local-development` 上の最新コミット群がまだ統合されていないため、Phase 2 完了後に CI グリーンを確認したうえで `main` への統合が必要である。

### QA 更新 (T-PH2-002, 2026-11-13T13:13:15+09:00)
- QA 合格。受入条件・TEST 証跡（backend 15 passed、frontend 11 passed）・別モデルの APPROVED レビューを確認し、許可パス外のタスク差分および指定禁止パスの変更がないことを照合して done に更新。
- exact-branch CI は未実行のため統合ゲートは未完了。CI green を確認するまで統合対象として扱わない。

### Poll reconciliation (2026-11-13T13:21:47+09:00)
- Poll reported T-PH2-002: qa -> missing-or-unreadable; the readable task file is already done with a recorded QA PASS at 2026-11-13T13:13:15+09:00. Left its terminal state unchanged.
- Poll reported T-PH2-003: review -> missing-or-unreadable; the readable task file is doing after Review Cycle 1 CHANGES_REQUESTED at 2026-11-13T13:18:00+09:00. Summary reflects that state and the one review return. High findings remain for the implementer; no QA transition was made.

### Poll reconciliation (2026-11-13T18:24:53+09:00)
- This poll again reports T-PH2-002 as new/done and T-PH2-003 as new/doing. The readable task files and task table already match these terminal/current states; no task frontmatter transition was needed.
- T-PH2-002 remains QA-passed with exact-branch CI pending. T-PH2-003 remains doing after Review Cycle 1 CHANGES_REQUESTED; its implementation worker still needs to address the recorded findings. No Quota/429 stop is recorded.
- Updated model metrics from task history: Gemini 4 Argon has two assigned tasks, one QA pass and one recorded return (50%); Gemini 3.8 Flash has one assigned task, zero QA passes and one recorded return (0%).
### T-PH2-001 — 試行上限による Blocked (2026-11-13T15:12:07+09:00)
- `status: blocked` を維持。受入条件1〜4に対応する実装記録、関連 Vitest 2ファイル・17件 PASS、実装モデルとは別の `agy/Claude Sonnet 5.5` による Cycle 2 `APPROVED`、禁止パスの変更なしがタスク記録にある。
- タスク専用4ファイル差分は識別できると記録されている。現在の作業チェックアウトには他タスク等の変更も混在し、タスクは未コミット。タスク固有ブランチの CI は未実行であり、成功扱いにはできない。CI は統合ゲートの未完了項目として扱う。
- `attempts: 3` およびレビュー周回上限2回に達したため、これ以上の自動差し戻し・再割当はしない。失敗原因はテストや受入条件の不合格ではなく、タスクブランチと CI 成功証跡が未提示のまま上限に達したこと。
- **人間への確認事項**: 次のいずれかを指示してください。(1) タスク専用ブランチ/コミットを提示し CI 成功を確認する、(2) タスク差分を安全に分離する手順を決めてから CI を実行する、(3) タスクスコープまたは納品方法を見直す。確認までは `blocked` のままとする。


### Poll reconciliation (T-PH2-003, 2026-11-13T18:36:17+09:00)
- Reconciled task status to `review`. REPORT / TEST include the implementation summary and scoped pytest/lint evidence; the Cycle 1 findings are documented as addressed. `agy/Gemini 4 Argon (Medium)` remains assigned as reviewer, distinct from implementer `agy/Gemini 3.8 Flash`; `cooldowns` is empty.
- Re-review is pending, so QA was not performed. Keep the model metrics unchanged: one recorded review return and zero QA passes for Gemini 3.8 Flash.

## autoloop run (2026-11-14T01:25:06.262Z)
- stop reason: all remaining tasks blocked (T-PH2-001)
- T-PH2-001: blocked
- T-PH2-002: done
- T-PH2-003: done
- log: T-PH2-003: verdict APPROVED (1.0) -> qa
- log: T-PH2-003: QA FAIL -> doing (attempts+1)
- log: dispatch implement: T-PH2-003 -> agy/Gemini 4 Argon
- log: cooldown: pool:agy:gemini until 2026-11-14T01:13:18.585Z (worker_error)
- log: dispatch implement: T-PH2-003 -> opencode/opencode/deepseek-v4.1-flash-free
- log: T-PH2-003: implement done by opencode/opencode/deepseek-v4.1-flash-free -> review
- log: dispatch review: T-PH2-003 -> agy/Claude Sonnet 5.5
- log: cooldown: pool:agy:claude-gpt until 2026-11-14T01:46:55.803Z (review_error)
- log: dispatch review: T-PH2-003 -> opencode/opencode/mimo-v2.6-flash-free
- log: T-PH2-003: review verdict APPROVED by opencode/opencode/mimo-v2.6-flash-free
- log: T-PH2-003: verdict APPROVED (2.1) -> qa
- log: committed: feat(phase-2-authz): complete T-PH2-003
- log: committed: docs(progress): mark T-PH2-003 done
- log: pushed to origin/loop/local-development
- log: T-PH2-003: done, committed and pushed
