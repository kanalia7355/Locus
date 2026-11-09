"""Immutable public catalog admission, no operator config or credentials."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from loop_engine.catalog_snapshot import load_snapshot
from loop_engine.security import SafetyError, fingerprint
from loop_engine.toolless_boundary import ToollessBoundary


def fixture(tmp_path):
    value = {
        "models": [
            {
                "slug": "gpt-6.1-sol",
                "use_responses_lite": True,
                "tool_mode": "direct",
                "experimental_supported_tools": [],
                "apply_patch_tool_type": None,
                "shell_type": "disabled",
                "multi_agent_version": None,
                "model_messages": {"instructions_template": "Public synthetic"},
            }
        ]
    }
    raw = json.dumps(value, sort_keys=True)
    path = tmp_path / ".loop/runtime/catalogs" / (fingerprint(raw) + ".json")
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    return path, {"path": str(path), "sha256": hashlib.sha256(raw.encode()).hexdigest()}, value


def test_snapshot_does_not_reload_mutable_background_catalog(tmp_path, monkeypatch):
    path, policy, _ = fixture(tmp_path)
    monkeypatch.setattr(
        "loop_engine.toolless_boundary.NativeBoundary", lambda *_: SimpleNamespace()
    )
    monkeypatch.setattr(
        "loop_engine.toolless_boundary.DockerBoundary", lambda *_: SimpleNamespace()
    )
    # No models_cache.json exists: the exact reviewed snapshot is sufficient.
    boundary = ToollessBoundary(tmp_path, "sha256:" + "a" * 64, [], catalog_policy=policy)
    assert boundary.catalog == path
    assert load_snapshot(tmp_path, policy)[0] == path
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(SafetyError):
        ToollessBoundary(tmp_path, "sha256:" + "a" * 64, [], catalog_policy=policy)


@pytest.mark.parametrize(
    "change", ["hash", "escape", "tools", "model", "missing", "reparse", "policy"]
)
def test_catalog_substitution_and_capability_expansion_fail(tmp_path, change):
    path, policy, value = fixture(tmp_path)
    if change == "hash":
        policy["sha256"] = "b" * 64
    elif change == "escape":
        policy["path"] = str(tmp_path / "outside.json")
    elif change == "missing":
        path.unlink()
    elif change == "policy":
        policy["other"] = True
    elif change == "reparse":
        from unittest.mock import patch

        with patch("loop_engine.catalog_snapshot.reparse", return_value=True):
            with pytest.raises(SafetyError):
                load_snapshot(tmp_path, policy)
        return
    else:
        if change == "tools":
            value["models"][0]["experimental_supported_tools"] = ["shell"]
        else:
            value["models"][0]["slug"] = "other-model"
        raw = json.dumps(value, sort_keys=True)
        path = path.parent / (fingerprint(raw) + ".json")
        path.write_text(raw, encoding="utf-8")
        policy = {"path": str(path), "sha256": hashlib.sha256(raw.encode()).hexdigest()}
    with pytest.raises(SafetyError):
        load_snapshot(tmp_path, policy)
