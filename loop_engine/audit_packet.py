"""Closed, bounded audit input; no commands, filesystem reads or signing authority.

Only a trusted Review supervisor may construct this input. Validation binds bytes,
not their provenance: authenticated IPC and protected evidence remain mandatory.
"""

import hashlib
import json
import re
from typing import Any

from loop_engine.security import SafetyError, reject_secrets, relative_path, sensitive

PACKET_LIMIT = 2 * 1024 * 1024
METADATA_LIMIT = 128 * 1024
FILE_LIMIT = 128 * 1024
CHUNK_LIMIT = 32 * 1024
FINDINGS_LIMIT = 256 * 1024
BINDING_FIELDS = {
    "goal",
    "requirements",
    "architecture",
    "acceptance",
    "task_spec",
    "qa",
    "policy",
    "head",
    "base",
    "task_id",
    "attempt",
    "scope",
    "nonce",
}


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        raise SafetyError("Invalid audit document encoding") from None


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def hash_value(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise SafetyError("Invalid audit digest")
    return value


def binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != BINDING_FIELDS:
        raise SafetyError("Closed audit binding required")
    for name in BINDING_FIELDS - {"head", "base", "task_id", "attempt", "scope"}:
        hash_value(value[name])
    for name in ("head", "base"):
        if not isinstance(value[name], str) or not re.fullmatch(r"[a-f0-9]{40}", value[name]):
            raise SafetyError("Exact Git commit required")
    if not isinstance(value["task_id"], str) or not re.fullmatch(
        r"TASK-[0-9]{3,6}", value["task_id"]
    ):
        raise SafetyError("Invalid audit task")
    if type(value["attempt"]) is not int or not 1 <= value["attempt"] <= 3:
        raise SafetyError("Audit attempt budget exceeded")
    if not isinstance(value["scope"], str) or value["scope"] not in {
        "task",
        "architecture",
        "security",
        "project",
    }:
        raise SafetyError("Unknown audit scope")
    return dict(value)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in result:
            raise SafetyError("Duplicate audit JSON field")
        result[key] = item
    return result


def decode(raw: bytes, maximum: int = PACKET_LIMIT) -> dict[str, Any]:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= maximum:
        raise SafetyError("Audit document size exceeded")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
        if not isinstance(value, dict) or canonical(value) != raw:
            raise SafetyError("Canonical audit JSON required")
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise SafetyError("Invalid canonical audit document") from None


def validate_packet(raw: bytes, expected: dict[str, Any]) -> dict[str, Any]:
    value = decode(raw)
    if (
        set(value) != {"protocol", "binding", "metadata", "files"}
        or value.get("protocol") != "locus-audit-packet-v1"
    ):
        raise SafetyError("Unsupported audit packet")
    if binding(value["binding"]) != binding(expected):
        raise SafetyError("Audit source/evidence binding changed")
    metadata = value["metadata"]
    if (
        not isinstance(metadata, dict)
        or set(metadata)
        != {"goal", "requirements", "architecture", "acceptance", "task_spec", "qa"}
        or len(canonical(metadata)) > METADATA_LIMIT
    ):
        raise SafetyError("Closed bounded audit metadata required")
    for name, item in metadata.items():
        if digest(canonical(item)) != expected[name]:
            raise SafetyError("Audit metadata hash mismatch")
    files = value["files"]
    if not isinstance(files, list) or len(files) > 256:
        raise SafetyError("Audit file count exceeded")
    names = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "base", "head"}:
            raise SafetyError("Closed audit file record required")
        name = item["path"]
        if not isinstance(name, str):
            raise SafetyError("Invalid audit source path")
        relative_path(name)
        if sensitive(name) or name.casefold() in names:
            raise SafetyError("Sensitive or duplicate audit path rejected")
        names.add(name.casefold())
        for revision in ("base", "head"):
            content = item[revision]
            if content is not None and (
                not isinstance(content, str) or len(content.encode("utf-8")) > FILE_LIMIT
            ):
                raise SafetyError("Audit source file size exceeded")
    reject_secrets(value)
    return value
