# Owner re-evaluation C — storage-ACL DP-054…065 + housekeeping DP-066…072

Status: recommendation layer for owner review only; recommendations are NOT execution
permission. Every 【要決定】 row keeps its status unchanged in OWNER_DECISION_QUEUE.
Authority: docs/plans/agent-work/OWNER_REEVAL-GROUNDING.md — consistency with the initial
Locus design takes priority.

Per-item format (mandatory 7 fields + flag line where applicable):

1 初期設計要件IDと原典 / 2 当初想定されていた動作 / 3 現在提示されている選択肢 /
4 推奨案（初期設計で未規定なら「最小構成推奨」）/ 5 自律性・利便性・安全性への影響 /
6 制約 / 7 残るOwner判断事項。

Flags: 🚫 = offered option or framing contradicts the initial design; ⚠ = proposed
constraint lacks grounding in it; 📈 = complexity beyond what the original functional
requirement needs.

## Part I — storage-ACL decisions DP-054…DP-065

### DP-054 — D5 scope confirmation (A/A2 vs B vs C/D)

1. 初期設計要件IDと原典: DATA-008（research-app-concept.md §8; PHASE_SPEC_RECONCILIATION.md Phase 3; PHASE2_JOB_BREAKDOWN.md D5）。初期設計では「元資料の権限との対応」を設計で確認する範疇に置き、接続方式は未確定（ui-and-multiuser-design.md「元保存先の権限との対応は未確定。実装前に決める」）。初期設計自身が開放点として認めた項目であり、矛盾ではない。
2. 当初想定されていた動作: 権限の対応は、接続方式が確定してから個別に設計する（ローカル・NASが最初の接続先候補、オンラインDriveはその後）。取り込みは分析・索引パイプラインと分離する。
3. 現在提示されている選択肢: A/A2（ソースACLの伝播）／B（コネクタの設定）／C/D（ローカルストレージACL/保持）／これらの組合せ。
4. 初期設計に最も整合する推奨案: A/A2をコアとし、C/Dを連結した保持の入力として扱う。Bは接続方式の個別設計フェーズとする。初期設計自身が「接続方式は未確定」として開放点として認めた項目であり、初期設計に整合する推奨案は、接続方式の個別設計を保留する。
5. 自律性・利便性・安全性への影響: Owner priority 1: 未連結の文書（手動アップロード・添付・チャット）は現行の権限動作を保持する。priority 3: 「共有の保存先への接続・対象ディレクトリ・公開範囲は管理者が設定する」対「個人資料は初期状態で本人のみ参照可能」の分離が保たれる。priority 6: no egress, no credential scheme, no connector enabled.
6. 採用した場合の制約: 保存先ACLの意味は初期設計では未確定であり、接続方式の個別設計フェーズまで保留する。
7. Ownerが新たに決定すべき事項: D5 scope confirmation（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none. 📈 none — the initial design's own open question is preserved.

### DP-055 — first source types/access modes; whether any connector exists in this phase

1. 初期設計要件IDと原典: DATA-008（research-app-concept.md §8「保存先との接続管理」の対象ディレクトリ・接続方式は未確定; ui-and-multiuser-design.md「個人資料の追加・参照」）。初期設計では「ローカル・NAS」を最初の接続先候補とし、オンラインDriveは「保存先が確定してから個別に設計」。
2. 当初想定されていた動作: 管理者は共有の保存先への接続・対象ディレクトリ・公開範囲を設定する。各利用者は自分のファイルを追加し、共有資料と併せて参照できる。個人資料は初期状態で本人のみ参照可能。個人のオンラインDriveへの継続接続や、個人資料を共有へ移す手順は未決定。
3. 現在提示されている選択肢: 手動アップロード／サーバーローカルフォルダ／NAS／オンラインDrive（コネクタ）／コネクタなし。
4. 初期設計に最も整合する推奨案（最小構成）: コネクタなし。初期設計はコネクタを承認していない（「接続方式は未確定」）。このフェーズでは手動アップロード（既に実装済み）が唯一のソースモードである。初期設計の「ローカル・NASが最初の接続先候補」は、接続方式の個別設計フェーズが承認された後に実装される将来のソースタイプの候補として保留する。
5. 自律性・利便性・安全性への影響: Owner priority 1: 手動アップロード（既に実装済み）は現行の権限動作を保持する。priority 3: 「個人資料を共有へ移す手順は未決定」の境界が保たれる。priority 6: no egress, no credential scheme, no connector enabled.
6. 採用した場合の制約: 個人オンラインDrive接続は未決定であり、接続方式の個別設計フェーズまで保留する。
7. Ownerが新たに決定すべき事項: コネクタなしの確認; 接続方式の個別設計フェーズが承認された後に実装される将来のソースタイプの候補（ローカル・NASが最初の接続先候補）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-056 — live vs snapshot source-permission checks; identity mapping; freshness/source of truth

1. 初期設計要件IDと原典: DATA-004（すべての検索パスで現在のACLを強制）; DATA-005（削除・ACL変更・移動またはソース損失は派生データすべてを後続アクセスより前に無効化）。ARCHITECTURE.md「Use shared policy enforcement in every data path」。ui-and-multiuser-design.md「元保存先の権限との対応は未確定。実装前に決める」「取り込み時のアクセス資格情報だけで全利用者への公開を決めず、会話時にも資料の利用権限を適用する」。
2. 当初想定されていた動作: 「取り込み時のアクセス資格情報だけで全利用者への公開を決めず、会話時にも資料の利用権限を適用する」 — the initial design requires conversation-time permission application. The initial design's 「元保存先の権限との対応は未確定」 leaves the exact freshness/identity mapping undecided.
3. 現在提示されている選択肢: ライブチェック／境界付き・バージョン管理されたスナップショット／Locus IDマッピング／分離承認されたLocusグラント。
4. 初期設計に最も整合する推奨案（最小構成）: ライブチェック。初期設計の「会話時にも資料の利用権限を適用する」境界は、ソース権限を取り込み時のみでなく会話時にも確認する必要があることを意味する。初期設計の「元保存先の権限との対応は未確定」は、正確な新鮮度/識別マッピングを未確定のままにする。
5. 自律性・利便性・安全性への影響: Owner priority 1: 既に実装済みの共有強制表面（_can_read family）でのライブチェックは制限されない。priority 3: no change. priority 6: stale/unverifiable source stateでのfail-closedが保たれる。
6. 採用した場合の制約: 数値的な新鮮度SLAは初期設計では根拠がない。初期設計は「元保存先の権限との対応は未確定」であり、正確な新鮮度/識別マッピングを未確定のままにする。
7. Ownerが新たに決定すべき事項: 正確な新鮮度/遅延境界と信頼源（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none — a numeric freshness SLA is not grounded in the initial design. 📈 none.

### DP-057 — combination rule with project membership, explicit deny, publication grants, personal ownership, attachment ACLs

1. 初期設計要件IDと原典: DATA-005（削除・ACL変更・移動またはソース損失は派生データすべてを後続アクセスより前に無効化）。research-app-concept.md §8「取り込み時のアクセス資格情報だけで全利用者への公開を決めず、会話時にも資料の利用権限を適用する」。PRODUCT_SPEC core: 「Document-level ACLs and permission-filtered retrieval」。
2. 当初想定されていた動作: Locus文書の「公開」はロール・範囲・操作で指定する方式と、ソースACLの「伝播」は接続方式が確定してから個別に設計する。初期設計では、ソースACLがLocusのACLを置き換えることはない。
3. 現在提示されている選択肢: research note §3 proposes intersection/additional gate; other combinations open.
4. 初期設計に最も整合する推奨案（最小構成）: 交差点/追加ゲート。初期設計の「取り込み時のアクセス資格情報だけで全利用者への公開を決めず、会話時にも資料の利用権限を適用する」境界は、additive second gate semantics rather than a replacementを必要とする。既存の実装では、explicit deny winsのまま保たれる。
5. 自律性・利便性・安全性への影響: Owner priority 1: 未連結の文書には制限がない。priority 3: 個人資料の分離が保たれる（公開グラントは、取り込み時の資格情報ではなく、別途決定される）。priority 6: fail-closedが保たれる。
6. 採用した場合の制約: 交差点ルールは、すべてのパスで両方のゲートをライブに保つ将来の接続方式の個別設計フェーズを拘束する。
7. Ownerが新たに決定すべき事項: 交差点ルールの確認（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-058 — source revocation/unavailability/disconnect/move/missed-sync behavior

1. 初期設計要件IDと原典: DATA-005（削除・ACL変更・移動またはソース損失は派生データすべてを後続アクセスより前に無効化）。ui-and-multiuser-design.md「共有資料から生成した会話を後から開く際の権限再確認は未確定」。
2. 当初想定されていた動作: 「取り込み時のアクセス資格情報だけで全利用者への公開を決めず、会話時にも資料の利用権限を適用する」。初期設計は、ソース権限の取消・利用不可・切断・移動・未確認の同期の正確な動作を未確定のままにする。
3. 現在提示されている選択肢: hide/quarantine/delete/retain-but-unavailable。
4. 初期設計に最も整合する推奨案（最小構成）: 非表示（fail closed）。DATA-005は、初期設計の「削除・ACL変更・移動またはソース損失…後続アクセスより前に無効化」の要件を根拠とする。削除は、初期設計の「原本の複製や一時保存の有無・期間は未確定」の境界を保持する。
5. 自律性・利便性・安全性への影響: Owner priority 1: hide/quarantineは手動アップロードを制限しない。priority 3: no change. priority 6: fail-closedが保たれる。
6. 採用した場合の制約: 「共有資料から生成した会話を後から開く際の権限再確認は未確定」の境界は、会話再オープン時の正確な動作を未確定のままにする。
7. Ownerが新たに決定すべき事項: ソース権限の取消・利用不可・切断・移動・未確認の同期の正確な動作（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-059 — source deletion semantics

1. 初期設計要件IDと原典: DATA-005（削除・ACL変更・移動またはソース損失は派生データすべてを後続アクセスより前に無効化）。ARCHITECTURE.md「Document uploads need … deletion propagation」。research-app-concept.md §8「基本は原本を保存先に残し、検索に必要な本文抽出・分割・検索索引・出典情報を管理する構想。原本の複製や一時保存の有無・期間は未確定」。初期設計には上流削除権限が含まれない。
2. 当初想定されていた動作: 取り込みは読み取り専用であり、Locus側の無効化（バインディング＋派生データ）のみが適用される。既存のdelete_documentはdocument/chunksを削除する。初期設計は、上流ソースの削除について言及していない。
3. 現在提示されている選択肢: binding only／Locus copies/derivatives／upstream request／combination。
4. 初期設計に最も整合する推奨案（最小構成）: バインディング＋ローカル派生データのクリーンアップ。初期設計の「原本の複製や一時保存の有無・期間は未確定」の境界が保たれる。上流書き込みには根拠がなく、初期設計に含まれない。
5. 自律性・利便性・安全性への影響: Owner priority 1: 手動アップロードを制限しない。priority 3: no change. priority 6: fail-closedが保たれる。
6. 採用した場合の制約: 上流書き込みには根拠がなく、初期設計に含まれない。
7. Ownerが新たに決定すべき事項: 上流削除権限が必要かどうか（初期設計に含まれない項目）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-060 — original bytes: copy / cache / link / fetch-on-demand; retention and backup

1. 初期設計要件IDと原典: DATA-008（research-app-concept.md §8「原本の複製や一時保存の有無・期間は未確定」）。DATA-008は、承認されたストレージサービスまたは保持ポリシーを指定していない。
2. 当初想定されていた動作: 「基本は原本を保存先に残し、検索に必要な本文抽出・分割・検索索引・出典情報を管理する構想。原本の複製や一時保存の有無・期間は未確定」。
3. 現在提示されている選択肢: copy / cache / link / fetch-on-demand; retention and backup periods/policy are open.
4. 初期設計に最も整合する推奨案（最小構成）: copy / cache / link / fetch-on-demandの選択は保留する。初期設計の「原本の複製や一時保存の有無・期間は未確定」の境界が保たれる。初期設計は、保持ポリシーを承認していない。
5. 自律性・利便性・安全性への影響: Owner priority 1: 手動アップロードを制限しない。priority 3: no change. priority 6: no egress, no credential scheme, no connector enabled.
6. 採用した場合の制約: 原本の複製や一時保存の有無・期間の選択は Owner判断で開放点とし、この再評価では新たな制約を追加しない。
7. Ownerが新たに決定すべき事項: 原本の複製や一時保存の有無・期間の選択（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-061 — multi-source documents: cardinality, revocation rule, duplicate handling, stable identity across moves

1. 初期設計要件IDと原典: DATA-008（research-app-concept.md §8「保存先との接続管理」の対象ディレクトリ・接続方式は未確定）; DATA-005（削除・ACL変更・移動またはソース損失は派生データすべてを後続アクセスより前に無効化）。初期設計では、各文書は1つのソースから派生する。初期設計は、複数のソースから派生する文書を扱う概念を含まない。
2. 当初想定されていた動作: 「接続方式の個別設計」＋「保存先への接続管理」は別の後続設計フェーズで、その場で決める。初期設計では、各文書は1つのソースから派生する。
3. 現在提示されている選択肢: カーディナリティを明示的にモデル化するか、1:1を仮定するか。ソースが取消された場合のアクセスルールは開放点である。
4. 初期設計に最も整合する推奨案（最小構成）: 1:1バインディングを既定のスキーマとし、スキーマはN:1の拡張を許容する。初期設計では、複数のソースから派生する文書を扱う概念は含まれない。ソースが取消された場合のアクセスルールは、初期設計のfail-closed原則に基づく。
5. 自律性・利便性・安全性への影響: Owner priority 1: 手動アップロードを制限しない。priority 3: no change. priority 6: fail-closedが保たれる。
6. 採用した場合の制約: 複数のソースから派生する文書は、初期設計に含まれない項目である。
7. Ownerが新たに決定すべき事項: 複数のソースから派生する文書を扱う概念が必要かどうか（初期設計に含まれない項目）。

Flags: 🚫 none. ⚠ none — the initial design has no multi-source concept. 📈 none.

### DP-062 — source configuration authority: who configures roots/scopes, sees paths/credentials/status; credential protection; egress allowlist

1. 初期設計要件IDと原典: DATA-008（research-app-concept.md §8「接続管理と個人資料の担当」の「共有の保存先への接続・対象ディレクトリ・公開範囲は管理者が設定する」）; DATA-008（「個人のオンラインDriveへの継続接続や、個人資料を共有へ移す手順は未決定」）。初期設計は「取り込み時のアクセス資格情報だけで全利用者への公開を決めず、会話時にも資料の利用権限を適用する」。
2. 当初想定されていた動作: 管理者は共有の保存先への接続・対象ディレクトリ・公開範囲を設定する。個人資料は初期状態で本人のみ参照可能。個人資料を共有へ移す手順は未決定。
3. 現在提示されている選択肢: configuration/view authority, credential controls and egress allowlist are open.
4. 初期設計に最も整合する推奨案（最小構成）: 管理者は共有の保存先への接続・対象ディレクトリ・公開範囲を設定する。初期設計の「共有の保存先への接続・対象ディレクトリ・公開範囲は管理者が設定する」の根拠に基づく。初期設計の「個人資料は初期状態で本人のみ参照可能」の境界が保たれる。初期設計の「個人のオンラインDriveへの継続接続や、個人資料を共有へ移す手順は未決定」の境界が保たれる。初期設計の「取り込み時のアクセス資格情報だけで全利用者への公開を決めず、会話時にも資料の利用権限を適用する」の根拠に基づく（資格情報は公開を決めない）。
5. 自律性・利便性・安全性への影響: Owner priority 1: 手動アップロードを制限しない。priority 3: 「共有の保存先への接続・対象ディレクトリ・公開範囲は管理者が設定する」対「個人資料は初期状態で本人のみ参照可能」の分離が保たれる。priority 6: no egress, no credential scheme, no connector enabled.
6. 採用した場合の制約: 個人オンラインDrive接続は未決定であり、接続方式の個別設計フェーズまで保留する。個人資料を共有へ移す手順は未決定であり、接続方式の個別設計フェーズまで保留する。
7. Ownerが新たに決定すべき事項: 個人オンラインDrive接続や個人資料を共有へ移す手順の確認（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-063 — sync failure/concurrency/retry/race semantics; authorization linearization point

1. 初期設計要件IDと原典: DATA-005（削除・ACL変更・移動またはソース損失は派生データすべてを後続アクセスより前に無効化）。ui-and-multiuser-design.md「元保存先の権限との対応は未確定。実装前に決める」「共有資料から生成した会話を後から開く際の権限再確認は未確定」。
2. 当初想定されていた動作: 「取り込み時のアクセス資格情報だけで全利用者への公開を決めず、会話時にも資料の利用権限を適用する」。初期設計は、競合/線形化の詳細を未確定のままにする。
3. 現在提示されている選択肢: sync failure/concurrency/retry/race semantics; authorization linearization point are open.
4. 初期設計に最も整合する推奨案（最小構成）: ライブチェック at every read boundary（既に実装済みの_can_read family）を拡張する。取り込みの2-check patternを拡張する。既存の実装では、競合/線形化の詳細を未確定のままにする。
5. 自律性・利便性・安全性への影響: Owner priority 1: 未連結の文書には制限がない。priority 3: no change. priority 6: fail-closedが保たれる。
6. 採用した場合の制約: 「元保存先の権限との対応は未確定」の境界は、正確な競合/線形化の詳細を未確定のままにする。
7. Ownerが新たに決定すべき事項: 正確な競合/線形化の詳細（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-064 — source metadata in audit; retention/access/privacy restrictions for connector administrators

1. 初期設計要件IDと原典: DATA-008（research-app-concept.md §8「接続管理と個人資料の担当」）; DATA-015（承認されたbaseline: metadata-only audit; do not log content, credentials, sensitive paths or ACL payloads）。
2. 当初想定されていた動作: 接続方式の個別設計フェーズで、ソース権限の変更・削除・移動等の監査を記録する。初期設計は、監査の保持ポリシーを承認していない。
3. 現在提示されている選択肢: whether source identity is sensitive; retention/access/privacy restrictions remain open.
4. 初期設計に最も整合する推奨案（最小構成）: metadata-only audit（DATA-015に根拠あり）。初期設計は、監査の保持ポリシーを承認していない。
5. 自律性・利便性・安全性への影響: Owner priority 1: no change. priority 3: no change. priority 6: fail-closedが保たれる。
6. 採用した場合の制約: 監査の保持ポリシーは初期設計では未確定であり、接続方式の個別設計フェーズまで保留する。
7. Ownerが新たに決定すべき事項: ソースメタデータの保持ポリシー（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-065 — source permission independent of external-AI policy; separate owner approval before sending source-derived content externally

1. 初期設計要件IDと原典: DATA-012（classification fail-closed; derived answers, citations, logs and artifacts inherit source ACLs and maximum classification; classification does not itself authorize destination/egress）。PRODUCT_SPEC core: 「Cloud APIs only for explicitly allowed data and administrator-authorized egress」。
2. 当初想定されていた動作: 「取り込み時のアクセス資格情報だけで全利用者への公開を決めず、会話時にも資料の利用権限を適用する」。初期設計は、ソース読み取り権限を外部モデルのイグレスに同意させることはない。
3. 現在提示されている選択肢: §7 describes the policies as confirmed independent while retaining the item in its undecided inventory.
4. 初期設計に最も整合する推奨案（最小構成）: ソース読み取り権限は外部モデルのイグレスに同意させることはない。初期設計の「取り込み時のアクセス資格情報だけで全利用者への公開を決めず」境界が保たれる。外部モデルのイグレスは、別途Ownerが承認する。
5. 自律性・利便性・安全性への影響: Owner priority 1: no change. priority 3: no change. priority 6: no egress, no credential scheme, no connector enabled.
6. 採用した場合の制約: ソース読み取り権限は外部モデルのイグレスに同意させることはない（DATA-012に根拠あり）。
7. Ownerが新たに決定すべき事項: ソース読み取り権限を外部モデルのイグレスに同意させるかどうか（初期設計に含まれない項目）。

Flags: 🚫 none. ⚠ none. 📈 none.

## Part II — housekeeping DP-066…DP-072

### DP-066 — production database, vector/search and optional graph technologies

1. 初期設計要件IDと原典: PROD-005（「Keep stack replaceable until selected」; ARCHITECTURE.md「Initial stack proposal: PostgreSQL+pgvector, optional local graph engine」; decisions/0002）。
2. 当初想定されていた動作: 初期設計は、本番DB/ベクトル/グラフ技術を承認していない。初期設計は、技術の実測・評価・承認が必要とする。
3. 現在提示されている選択肢: evidence-backed comparison and verification plans.
4. 初期設計に最も整合する推奨案（最小構成）: Owner decision deferred to the production-deployment phase, after evidence-backed comparison and verification plans. 初期設計の「Keep stack replaceable until selected」の境界が保たれる。
5. 自律性・利便性・安全性への影響: Owner priority 1: no research-support restriction. priority 2: no change. priority 6: no egress, no credential scheme, no connector enabled.
6. 採用した場合の制約: 本番DB/ベクトル/グラフ技術の選択は、evidence-backed proposalの後にOwnerが決定する。初期設計の「Keep stack replaceable until selected」の境界が保たれる。
7. Ownerが新たに決定すべき事項: 本番DB/ベクトル/グラフ技術の選択（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-067 — production deployment, TLS/session lifecycle and LAN/private-network verification policy

1. 初期設計要件IDと原典: PROD-002（「LAN membership alone never grants authorization」）; PROD-003（「Final deployment must use appropriate private-interface/firewall/allowlist, TLS where applicable, VPN for remote access」）; IAM-017（「Production TLS/session deployment deferred to production-deployment phase」）。
2. 当初想定されていた動作: 初期設計は、プロトタイプの完了後の本番運用の生産要素をOwnerが明示的に決める必要があるとする。
3. 現在提示されている選択肢: prototype loopback-only versus eventual authenticated private-network deployment; exact production policy and validation are not specified.
4. 初期設計に最も整合する推奨案（最小構成）: Owner decision deferred to the production-deployment phase. 初期設計の「LAN membership alone never grants authorization」の境界が保たれる。
5. 自律性・利便性・安全性への影響: Owner priority 1: no research-support restriction. priority 2: no change. priority 6: no egress, no credential scheme, no connector enabled.
6. 採用した場合の制約: 本番運用の生産要素は、production-deployment phaseまで保留する（初期設計の「TLS/session lifecycle」の境界が保たれる）。
7. Ownerが新たに決定すべき事項: 本番運用の生産要素の具体的な要件（TLS, LAN, VPN, etc.）

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-068 — audit confidentiality, access control, tamper/rollback evidence, retention and secure erasure

1. 初期設計要件IDと原典: DATA-015（metadata-only audit; do not log content, credentials, sensitive paths or ACL payloads）; IAM-016（「Final operation needs appropriate confidentiality, access control, tamper/rollback evidence, retention and secure erasure for audit records」）。
2. 当初想定されていた動作: 初期設計は、監査の保持ポリシーを承認していない。
3. 現在提示されている選択肢: protection, access, tamper/rollback, retention, secure erasure are open.
4. 初期設計に最も整合する推奨案（最小構成）: Owner decision deferred to the production-deployment phase, after evidence-backed proposals. 初期設計は、監査の保持ポリシーを承認していない。
5. 自律性・利便性・安全性への影響: Owner priority 1: no change. priority 3: no change. priority 6: no egress, no credential scheme, no connector enabled.
6. 採用した場合の制約: 監査の保持ポリシーは、production-deployment phaseまで保留する（初期設計には根拠がない）。
7. Ownerが新たに決定すべき事項: 監査の保持ポリシー（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-069 — production storage retention, backup/restore and secure-deletion policy and periods

1. 初期設計要件IDと原典: DATA-008（research-app-concept.md §8「原本の複製や一時保存の有無・期間は未確定」）; DATA-015（metadata-only audit; do not log content, credentials, sensitive paths or ACL payloads）。
2. 当初想定されていた動作: 初期設計は、本番運用の生産要素をOwnerが明示的に決める必要があるとする。
3. 現在提示されている選択肢: retention, backup/restore, secure-deletion policy and periods are open.
4. 初期設計に最も整合する推奨案（最小構成）: Owner decision deferred to the production-deployment phase. 初期設計は、保持ポリシーを承認していない。
5. 自律性・利便性・安全性への影響: Owner priority 1: no research-support restriction. priority 2: no change. priority 6: no egress, no credential scheme, no connector enabled.
6. 採用した場合の制約: 保持ポリシーは、production-deployment phaseまで保留する（初期設計に根拠がない）。
7. Ownerが新たに決定すべき事項: 保持ポリシー（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-070 — production provider/model scope and representative capacity targets

1. 初期設計要件IDと原典: PROD-005（「Keep stack replaceable until selected」; research-app-concept.md「LLMの処理先は未確定」）; DATA-015（「production capacity claims must follow measurement」）。
2. 当初想定されていた動作: 初期設計は、本番のプロバイダ/モデルスコープを承認していない。性能目標は、実測に基づく。
3. 現在提示されている選択肢: production provider/model scope; representative capacity targets are open.
4. 初期設計に最も整合する推奨案（最小構成）: Owner decision deferred to the production-deployment phase, after evidence and provider-term review. 初期設計の「Keep stack replaceable until selected」の境界が保たれる。
5. 自律性・利便性・安全性への影響: Owner priority 1: no research-support restriction. priority 2: no change. priority 6: no egress, no credential scheme, no connector enabled.
6. 採用した場合の制約: プロバイダ/モデルスコープは、evidence-backed proposalの後にOwnerが決定する。初期設計の「Keep stack replaceable until selected」の境界が保たれる。
7. Ownerが新たに決定すべき事項: プロバイダ/モデルスコープ（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-071 — org-model decision for remaining recipient-side delegation UI refinement and any org-level management surface

1. 初期設計要件IDと原典: PRODUCT_SPEC（「Built-in role templates: system admin, organization admin, assistant admin, project lead, researcher, research assistant, general user, viewer, guest, auditor」）; PHASE_SPEC_RECONCILIATION（「Delegated administration constrained by permission subset, scope and expiration」）。初期設計では、組織全体の委任は、既存のOwnerの決定により後続のフェーズに後続する。
2. 当初想定されていた動作: 組織全体の委任は、既存のOwnerの決定により後続のフェーズに後続する。
3. 現在提示されている選択肢: recipient-side delegation UI refinement and org-level management surface are open.
4. 初期設計に最も整合する推奨案（最小構成）: Owner decision deferred to the production-deployment phase. 初期設計では、組織全体の委任は、既存のOwnerの決定により後続のフェーズに後続する。
5. 自律性・利便性・安全性への影響: Owner priority 1: no research-support restriction. priority 2: no change. priority 6: no egress, no credential scheme, no connector enabled.
6. 採用した場合の制約: 組織全体の委任は、既存のOwnerの決定（PH2-A §A）により後続のフェーズに後続する。再び開くものではない。
7. Ownerが新たに決定すべき事項: 組織全体の委任の管理表面（初期設計自身の開放点）。

Flags: 🚫 none. ⚠ none. 📈 none.

### DP-072 — persistence across service restarts for production sessions; approved session lifecycle

1. 初期設計要件IDと原典: IAM-017（「Production TLS/session deployment deferred to production-deployment phase」）; PROD-003（「Final deployment must use appropriate private-interface/firewall/allowlist, TLS where applicable, VPN for remote access」）。
2. 当初想定されていた動作: 初期設計は、プロトタイプの完了後の本番運用の生産要素をOwnerが明示的に決める必要があるとする。
3. 現在提示されている選択肢: persistence across service restarts; approved session lifecycle are open.
4. 初期設計に最も整合する推奨案（最小構成）: Owner decision deferred to the production-deployment phase. 初期設計は、プロトタイプの完了後の本番運用の生産要素をOwnerが明示的に決める必要があるとする。
5. 自律性・利便性・安全性への影響: Owner priority 1: no research-support restriction. priority 2: no change. priority 6: no egress, no credential scheme, no connector enabled.
6. 採用した場合の制約: プロトタイプの完了後の本番運用の生産要素は、production-deployment phaseまで保留する（初期設計の「TLS/session lifecycle」の境界が保たれる）。
7. Ownerが新たに決定すべき事項: 本番運用のsession lifecycle/persistenceの要件（初期設計自身の開放点）

Flags: 🚫 none. ⚠ none. 📈 none.
