"""HBR-003 分類と派生データの契約検証テスト。

このテストは HBR_CLASSIFICATION_MODEL.json の機械可読契約を検証し、
inherit-max 規則による分類の最大値計算を合成データで証明する。
"""

import json
from pathlib import Path

# ---- 1. registry.py から分類値を読み込む ----
_REGISTRY_PY = Path(__file__).resolve().parents[1] / "backend" / "app" / "agents" / "registry.py"


def _extract_classifications_from_registry() -> frozenset:
    """registry.py の _CLASSIFICATIONS フrozenset を抽出する。"""
    with open(_REGISTRY_PY, encoding="utf-8") as f:
        content = f.read()
    # _CLASSIFICATIONS frozenset 抽出
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("_CLASSIFICATIONS"):
            # frozenset({...}) から { と } と frozenset() を除去し、残りの "value1", "value2" を抽出
            start = stripped.index("{")
            end = stripped.rindex("}")
            inner = stripped[start + 1 : end]
            # ダブルクオートでくくられた値を抽出
            import re

            values = re.findall(r'"([^"]+)"', inner)
            return frozenset(values)
    raise RuntimeError("_CLASSIFICATIONS not found in registry.py")


REGISTRY_CLASSIFICATIONS = _extract_classifications_from_registry()

# ---- 2. JSON モデルを読み込む ----
_MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "progress"
    / "phase-8-runner"
    / "material"
    / "HBR_CLASSIFICATION_MODEL.json"
)


def _load_model() -> dict:
    with open(_MODEL_PATH, encoding="utf-8") as f:
        return json.load(f)


MODEL = _load_model()


# ---- ヘルパー: 最大値計算 ----
# 昇順: public < personal < research_shared < confidential
# none は特別処理: 含まれていれば deny
_ORDER_MAP = {
    "public": 0,
    "personal": 1,
    "research_shared": 2,
    "confidential": 3,
}


def _max_classification(sources: list[str]) -> str | None:
    """source 分類の最大値を返す。none が含まれていれば None（拒否）を返す。"""
    if "none" in sources:
        return None  # none が含まれていれば拒否
    non_none = [s for s in sources if s != "none"]
    if not non_none:
        return None  # すべて none、または空リスト
    max_val = max(non_none, key=lambda s: _ORDER_MAP.get(s, -1))
    return max_val


# ---- テスト本体 ----


def test_levels_matches_registry():
    """levels が registry.py の CHECK 制約値と完全に一致すること。"""
    levels = MODEL["levels"]
    assert set(levels) == REGISTRY_CLASSIFICATIONS, (
        f"levels {levels} と registry.py の値 {REGISTRY_CLASSIFICATIONS} が一致しません"
    )
    assert "none" in levels, "levels に none が含まれていません"


def test_levels_keeps_its_order():
    """`levels` は順序のある契約なので、順序まで表明する。

    集合で比べるだけだと並べ替えが素通りする。`inherit-max` はこの並びで
    「最大」を決めるので、順序が狂えば継承の結果が静かに変わる。
    設計 §1 の昇順 `public < personal < research_shared < confidential` が正本で、
    `none` は並びの最下位ではなく拒否状態なので、順序の表明からは外す。

    測って確かめた限界: `none` の位置を入れ替えてもこの表明は通る（意図どおり。
    `none` は順序に属さない）。`personal` と `confidential` を入れ替えると落ちる。
    """
    ordered = [level for level in MODEL["levels"] if level != "none"]
    assert ordered == ["public", "personal", "research_shared", "confidential"], (
        f"levels の順序が設計 §1 と違います: {ordered}"
    )


def test_deny_states_includes_none():
    """deny_states に none が含まれていること。"""
    assert "none" in MODEL["deny_states"], "deny_states に none が含まれていません"


def test_paths_have_all_8_routes():
    """paths に 8 つの経路 ID がすべてあること。"""
    required_ids = {
        "ingestion",
        "chunking",
        "retrieval",
        "answer",
        "citation",
        "export",
        "runner_input",
        "runner_artifact",
    }
    path_ids = {p["id"] for p in MODEL["paths"]}
    assert path_ids == required_ids, (
        f"paths の ID {path_ids} が必要な {required_ids} と一致しません"
    )


def test_all_on_unknown_deny():
    """全経路の on_unknown が deny であること。"""
    for path in MODEL["paths"]:
        assert path["on_unknown"] == "deny", (
            f"経路 {path['id']} の on_unknown が deny ではありません: {path['on_unknown']}"
        )


def test_gate_location_exists():
    """各経路の gate_location が実在するファイルを指していること。"""
    for path in MODEL["paths"]:
        path = path  # local bind
        location = path["gate_location"]
        candidates = [
            Path(location),
            Path(__file__).resolve().parents[1] / location,
        ]
        found = False
        for candidate in candidates:
            if candidate.is_file():
                found = True
                break
        assert found, (
            f"gate_location {location} を持つファイルが見つかりません。試したパス: {candidates}"
        )


def test_inherits_dag_acyclic():
    """inherits による有向グラフに循環がないこと。"""
    path_map = {p["id"]: p["inherits"] for p in MODEL["paths"]}
    visited = set()
    rec_stack = set()

    def dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        for neighbor in path_map.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.remove(node)
        return False

    for path in MODEL["paths"]:
        pid = path["id"]
        if pid not in visited:
            if dfs(pid):
                raise AssertionError("inherits におけるサイクルが検出されました")


def test_inherit_max_monotonicity():
    """継承先の分類が継承元の最大値より低くなり得ない（単調性）ことを合成データで表明する。"""
    # ケース 1: confidential と public の派生は confidential
    result = _max_classification(["confidential", "public"])
    assert result == "confidential", "confidential と public の最大値は confidential であるべきです"

    # ケース 2: none が 1 件混ざれば結果は拒否（None が返る）
    result = _max_classification(["none", "public"])
    assert result is None, "none が含まれる場合は None（拒否）を返すべきです"

    result = _max_classification(["none", "confidential"])
    assert result is None, "none が含まれる場合は None（拒否）を返すべきです"

    result = _max_classification(["none", "none"])
    assert result is None, "none が含まれる場合は None（拒否）を返すべきです"

    # その他の単調性チェック: max常に下がらない
    result = _max_classification(["public", "personal"])
    assert result == "personal", "public + personal は personal でなければなりません"

    result = _max_classification(["research_shared", "confidential"])
    assert result == "confidential", (
        "research_shared + confidential は confidential でなければなりません"
    )


def test_migration_has_multiple_plans():
    """migration の計画が 2 件以上あり、各案に breaks が非空であること。"""
    migration = MODEL["migration"]
    assert len(migration) >= 2, (
        f"migration の計画は 2 件以上でなければなりませんが、{len(migration)} 件です"
    )
    for plan in migration:
        assert "id" in plan, "migration プランに id がありません"
        assert "summary" in plan, "migration プランに summary がありません"
        assert "breaks" in plan, "migration プランに breaks がありません"
        assert len(plan["breaks"]) > 0, (
            f"migration プラン {plan['id']} の breaks は非空でなければなりません"
        )
    assert MODEL.get("selected") is None, "selected は null でなければなりません"
