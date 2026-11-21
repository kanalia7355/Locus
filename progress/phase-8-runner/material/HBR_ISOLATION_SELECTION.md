# HBR 隔離プロファイル選定書（HBR-004 判断材料）

- 状態: 判断材料のみ。全候補は `INACTIVE_UNVERIFIED`、`selected: null`、`independent_reviewer: null`。本書は候補を選定・活性化・検証済みとしない。
- 根拠: `docs/plans/HYBRID_ISOLATION_PROFILES.md`（§3 候補行列, §5 共通要件, §6 検証対応表, §7 証跡, §8 未決, §9 文書間の緊張）, `docs/plans/HYBRID_ISOLATION_ENGINEERING_DETAIL.md`（§3.2 テスト族 12 種, §4.1 証跡, §5 チェックリスト）, `docs/plans/HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md`（§2 技術比較）, `docs/plans/HYBRID_RUNNER_TRUST_DESIGN.md`（§3.3 Linux ファイル保管の残余リスク）。

## 文書間の食い違い（profiles が現行）

`HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md` §2.1/§2.2 は Windows・Linux ともに VM 第一の方向を提案している。一方 `HYBRID_ISOLATION_PROFILES.md` §9 は、その提案を普遍的な義務へ昇格させないことを明示し、VM と OS 制限/コンテナ層を比較対象として残し、具体技術・残余リスク受諾は未選定（§8 【要決定】）としている。profiles 側が後発で step3 を設計入力として引用しているため、**本書は profiles 側の立場を現行として扱い、step3 の VM 第一を既定とはしない**。候補の比較・可否は exact-build の独立証跡と別途の活性化判断が揃うまで未確定である。

## 候補別の判断材料

各候補とも、`HYBRID_ISOLATION_ENGINEERING_DETAIL.md` §3.2 の 12 テスト族（`CFG` `FS` `PROC` `NET` `RES` `XFER` `AUTH` `OUT` `CXL` `CLEAN` `B6` `EVID`）が、宣言した exact 構成ごとにすべて必要（共通チェックを含む）。本書ではテスト内容を写さず、**本数と前提**のみ示す。

### W-D — Windows local desktop（対話ワークステーション）

- **必要な実機（OS エディション／ビルド粒度）**: 対話利用者がサインインする Windows ワークステーションの exact エディション（例: Pro/Enterprise 等、候補ごとに特定）、正確な OS ビルド/パッチ/アーキテクチャ、有効なセキュリティ機能。VM 系を評価する場合は Hyper-V 等の有効性・版要件とゲスト/イメージ同一性も対象ホスト上で特定が必要（`HYBRID_ISOLATION_PROFILES.md` §3 W-D, §2.2）。
- **計測・検証の作業（本数と前提）**: 12 テスト族を各 1 回以上、宣言した exact 構成に対して実施（計 12 族）。前提: 使い捨て/隔離された検証環境、合成フィクスチャのみ、独立に観測可能なホスト側テレメトリ、未知/未対応の OS 機能や構成差異は不合格（BLOCKED/FAIL 扱い）とすること。構成・イメージ・ポリシー変更ごとに影響証跡は無効化され再評価が必要（`HYBRID_ISOLATION_ENGINEERING_DETAIL.md` §3.1, §4.2）。
- **残余リスク（1 文）**: 共有カーネル構成やローカル管理者 TCB に依存する場合、ホスト OS カーネル・ローカル管理者・（VM 利用時は）ハイパーバイザ/ファームウェア/管理面は境界外であり、これらの侵害や管理者権限による迂回は隔離主張に含まれない（`HYBRID_ISOLATION_PROFILES.md` §2.1）。
- **成立しないこと**: 対話利用者のプロファイル/セッションが同一ホストに存在する前提では、ジョブによる対話利用者ファイル・セッション・資格情報ストアへの非露出は exact 構成の証跡なしに成立しない。Job Object 等のプロセス拘束のみで FS/NET/カーネル境界は代替できず、開発ループ QA や別プロファイル証跡は本プロファイルの証明にならない（`HYBRID_ISOLATION_PROFILES.md` §3 W-D）。

### W-S — Windows server（管理対象マルチテナント）

- **必要な実機（OS エディション／ビルド粒度）**: Windows Server の exact エディション/ビルド/パッチ/アーキテクチャと有効セキュリティ機能。コンテナ/VM/ランタイムを用いる場合はその exact バージョン・構成・イメージ digest と配置単位（信頼ドメイン/ジョブ）をサーバー構成として特定が必要（`HYBRID_ISOLATION_PROFILES.md` §3 W-S, §2.2）。
- **計測・検証の作業（本数と前提）**: 12 テスト族を各 1 回以上、宣言した exact サーバー構成に対して実施（計 12 族）。前提: 使い捨て評価環境、合成 ID/ワークスペースによる同時テナント条件、ホスト側のプロセス/ネットワーク/マウント観測、サービス再起動・ホスト再起動・後片付け不確実時の隔離/停止確認。変更で証跡は失効（`HYBRID_ISOLATION_ENGINEERING_DETAIL.md` §3.1, §4.2）。
- **残余リスク（1 文）**: サーバー管理者・ホスト OS/ランタイム・（VM 利用時は）ハイパーバイザやゲストイメージ/管理面は TCB に含まれ得て、これらの侵害や管理者権限、共有カーネル構成の残余リスクは exact 証跡と別途の受諾判断なしに除外できない（`HYBRID_ISOLATION_PROFILES.md` §2.1）。
- **成立しないこと**: デスクトップ証跡や単一テナント前提はサーバーのテナント間分離・サービス/管理面分離を成立させない。プロセス分離コンテナや Job Object 単独ではカーネル/ネットワーク/FS 境界の完全代替にならず、未検証プロファイルへの暗黙のフォールバックやホスト直接実行は認められない（`HYBRID_ISOLATION_PROFILES.md` §3 W-S）。

### L-D — Linux local desktop（対話ワークステーション）

- **必要な実機（OS エディション／ビルド粒度）**: Linux ディストリビューション/カーネル/ビルド/アーキテクチャと有効なセキュリティ機能（namespace, seccomp, LSM, cgroups 等）の exact 状態。rootless OCI/namespace 構成または VM/microVM を用いる場合はランタイム・ハイパーバイザ・イメージ/ポリシー同一性を対象ホストで特定が必要（`HYBRID_ISOLATION_PROFILES.md` §3 L-D, §2.2）。
- **計測・検証の作業（本数と前提）**: 12 テスト族を各 1 回以上、宣言した exact 構成に対して実施（計 12 族）。前提: 使い捨て評価環境、合成フィクスチャ、UID/GID・マウント伝播・seccomp/LSM・IPv4/IPv6 フィルタ等の有効性確認、必須カーネル機能欠落は省略理由でなく不合格。変更で証跡は失効（`HYBRID_ISOLATION_ENGINEERING_DETAIL.md` §3.1, §4.2）。
- **残余リスク（1 文）**: 共有カーネル（namespace/コンテナ）構成ではホストカーネル/ローカル管理者が TCB に残り、`HYBRID_RUNNER_TRUST_DESIGN.md` §3.3 のとおり Linux のファイルベース保管はホスト管理者からの読取/エクスポートを防げないため、その残余リスクを別途受諾判断する必要がある。
- **成立しないこと**: 共有カーネル構成は別カーネル境界を意味しない。対話利用者のホーム/資格情報パス、ランタイムソケット、ホスト PID/ネットワーク等の非露出は exact 構成の証跡が必要であり、汎用コンテナ/CI の通過や別環境の証跡で代替できない。必須機能欠落時のホスト直接実行への退行は不可（`HYBRID_ISOLATION_PROFILES.md` §3 L-D）。

### L-S — Linux server（管理対象マルチテナント）

- **必要な実機（OS エディション／ビルド粒度）**: サーバー向け Linux ディストリビューション/カーネル/LSM・seccomp 設定/ビルド/アーキテクチャの exact 状態。rootless OCI・VM/microVM・層状構成を用いる場合はランタイム/ハイパーバイザ、ポリシー、ゲスト/ベースイメージ digest をサーバー構成として特定が必要（`HYBRID_ISOLATION_PROFILES.md` §3 L-S, §2.2）。
- **計測・検証の作業（本数と前提）**: 12 テスト族を各 1 回以上、宣言した exact サーバー構成に対して実施（計 12 族）。前提: 使い捨て評価環境、同時実行の合成テナント/ジョブによる交差攻撃条件、ホスト観測による FS/PROC/NET 拒否確認、資源枯渇・障害・再起動後の後片付け/隔離確認。変更で証跡は失効（`HYBRID_ISOLATION_ENGINEERING_DETAIL.md` §3.1, §4.2）。
- **残余リスク（1 文）**: サーバー管理者・ホストカーネル/ランタイム・（VM 利用時は）ハイパーバイザやイメージ/管理面は TCB に残り、`HYBRID_RUNNER_TRUST_DESIGN.md` §3.3 のとおり Linux のファイルベース保管はホスト管理者からの読取/エクスポートを防げないため、その残余リスクを別途受諾判断する必要がある。
- **成立しないこと**: 他プロファイル（L-D 等）や汎用 Docker QA の証跡はサーバーのマルチテナント分離を成立させない。共有カーネル構成ではカーネル脆弱性や構成誤りの残余が残り、層状化しても各境界と複合障害経路の個別証跡が必要。未検証・不確実時のフォールバックは不可（`HYBRID_ISOLATION_PROFILES.md` §3 L-S）。

## オーナーへ返す問い（3 件）

1. どの隔離候補（W-D/W-S/L-D/L-S）を配備対象として選ぶか。
2. 各候補に残る共有カーネル／ハイパーバイザ／ローカル管理者の残余リスク（L-D/L-S では `HYBRID_RUNNER_TRUST_DESIGN.md` §3.3 のファイル保管リスクを含む）を受諾するか。
3. `HYBRID_ISOLATION_PROFILES.md` §7 項目 4 にある独立検証者（実装・設定の作成者と分離）を誰に任命するか。

## 制約メモ

- 既存の開発ループ QA 実装（`loop_engine/docker_boundary.py`）は製品 Runner の隔離証拠ではない（`HYBRID_ISOLATION_PROFILES.md` §9, `HYBRID_STEP3_ISOLATION_AND_TRUST_PROPOSALS.md` §1.1）。
- 実機プローブは本書の範囲外であり、設計承認まで着手できない（後続 `T-PH8-305`）。
- B6 により未検証プロファイルでの実行は拒否されたままである。
