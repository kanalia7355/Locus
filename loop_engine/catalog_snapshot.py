"""Exact owner-profile-bound public catalog, never an authentication store."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from loop_engine.security import SafetyError, fingerprint, reparse, within


def load_snapshot(root: Path, policy: Any) -> tuple[Path, str]:
    if (
        not isinstance(policy, dict)
        or set(policy) != {"path", "sha256"}
        or not isinstance(policy["path"], str)
        or not isinstance(policy["sha256"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", policy["sha256"])
    ):
        raise SafetyError("Exact catalog snapshot policy required")
    path = Path(policy["path"])
    folder = within(root, ".loop/runtime/catalogs")
    if path.parent != folder or not re.fullmatch(r"[a-f0-9]{64}\.json", path.name):
        raise SafetyError("Catalog snapshot escaped managed catalog directory")
    if any(reparse(p) for p in (path, *path.parents)) or not path.is_file():
        raise SafetyError("Catalog snapshot path changed")
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if hashlib.sha256(raw).hexdigest() != policy["sha256"] or path.stem != fingerprint(text):
        raise SafetyError("Catalog snapshot bytes changed")
    selected = [x for x in json.loads(text)["models"] if x.get("slug") == "gpt-6.1-sol"]
    required = {
        "use_responses_lite": True,
        "tool_mode": "direct",
        "experimental_supported_tools": [],
        "apply_patch_tool_type": None,
        "shell_type": "disabled",
        "multi_agent_version": None,
    }
    if len(selected) != 1 or any(
        k not in selected[0] or type(selected[0][k]) is not type(v) or selected[0][k] != v
        for k, v in required.items()
    ):
        raise SafetyError("Pinned zero-tool catalog restrictions changed")
    return path, text
