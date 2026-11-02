"""Closed trial-only input contract; no credentials, I/O, rewriting or logging."""

import copy
import hashlib
import html
import math
import re
import xml.etree.ElementTree as ET
from typing import Any
from uuid import UUID

from loop_engine.model_gate import strict_json
from loop_engine.security import SafetyError, fingerprint

VERSION = "c-min-trial-input-contract-v1"
# Public owner-approved design manifest, not authentication material.
# pragma: allowlist nextline secret
APPROVAL = "43bd4b6b8159ec2c7fadef9c9e2f5e305f8d93d019a044af8297c20960c452a0"
HEADERS = {
    "user-agent",
    "originator",
    "openai-beta",
    "session_id",
    "x-client-request-id",
    "x-codex-turn-metadata",
    "x-openai-internal-codex-responses-lite",
}


def reject() -> None:
    raise SafetyError("Trial input binding rejected; no send/replay")


def locate(root: Any, path: list[Any]) -> tuple[Any, Any]:
    if not path or len(path) > 10:
        reject()
    node = root
    for key in path[:-1]:
        node = node[key]
    return node, path[-1]


def allowed_slot(slot: dict[str, Any]) -> bool:
    path, kind = slot["path"], slot["kind"]
    if not isinstance(path, list) or any(type(p) not in {str, int} for p in path):
        return False
    if any(type(p) is int and not 0 <= p < 1024 for p in path):
        return False
    if len(path) == 4 and path[:2] == ["body", "input"] and type(path[2]) is int:
        return bool(kind == "message_id" and path[3] == "id")
    if len(path) == 5 and path[:2] == ["body", "input"] and type(path[2]) is int:
        return bool(
            path[3] == "internal_chat_message_metadata_passthrough"
            and (
                (kind == "turn_id" and path[4] == "turn_id")
                or (kind == "time" and path[4] == "create_time")
            )
        )
    if kind == "arg0":
        return (
            len(path) == 6
            and path[:2] == ["body", "input"]
            and type(path[2]) is int
            and path[3] == "content"
            and type(path[4]) is int
            and path[5] == "text"
        )
    if kind == "session_id":
        if path in [
            ["body", "prompt_cache_key"],
            ["body", "client_metadata", "session_id"],
            ["body", "client_metadata", "thread_id"],
            ["headers", "session_id"],
        ]:
            return True
    if kind == "request_id":
        return path == ["headers", "x-client-request-id"]
    if kind == "turn_id":
        if path in [
            ["body", "client_metadata", "turn_id"],
            ["body", "client_metadata", "root_turn_id"],
        ]:
            return True
    embedded = (
        path[3:]
        if path[:3] == ["body", "client_metadata", "x-codex-turn-metadata"]
        else path[2:]
        if path[:2] == ["headers", "x-codex-turn-metadata"]
        else []
    )
    if len(embedded) == 1:
        return (
            kind == "turn_id"
            and embedded[0] in {"turn_id", "root_turn_id"}
            or kind == "session_id"
            and embedded[0] in {"thread_id", "session_id"}
            or kind == "time_ms"
            and embedded[0] == "turn_started_at_unix_ms"
        )
    return False


def contract(value: Any) -> dict[str, Any]:
    """Reject malformed/unknown descriptors instead of discovering slots at runtime."""
    try:
        if (
            not isinstance(value, dict)
            or set(value) != {"version", "approval", "body", "headers", "slots", "launch"}
            or value["version"] != VERSION
            or value["approval"] != APPROVAL
            or not isinstance(value["body"], dict)
            or not isinstance(value["headers"], dict)
            or set(value["headers"]) - HEADERS
            or not isinstance(value["launch"], dict)
            or not isinstance(value["slots"], list)
            or not 0 < len(value["slots"]) <= 64
        ):
            reject()
        paths = set()
        arg0 = 0
        for i, slot in enumerate(value["slots"]):
            if (
                not isinstance(slot, dict)
                or set(slot)
                != {"path", "kind", "group"}
                | (
                    {"prefix", "suffix"}
                    if slot.get("kind") == "arg0"
                    else {"uuid_version"}
                    if slot.get("kind") in {"message_id", "turn_id", "session_id", "request_id"}
                    else set()
                )
                or not isinstance(slot["group"], str)
                or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", slot["group"])
                or not allowed_slot(slot)
            ):
                reject()
            key = fingerprint(slot["path"])
            if key in paths:
                reject()
            paths.add(key)
            if "uuid_version" in slot and (
                type(slot["uuid_version"]) is not int
                or slot["uuid_version"] not in {4, 7}
                or slot["kind"] in {"message_id", "turn_id"}
                and slot["uuid_version"] != 7
            ):
                reject()
            parent, leaf = locate(value, slot["path"])
            if parent[leaf] != {"$slot": i}:
                reject()
            if slot["kind"] == "arg0":
                arg0 += 1
                if (
                    not isinstance(slot["prefix"], str)
                    or not isinstance(slot["suffix"], str)
                    or not slot["prefix"].endswith('<entry access="read"><path>')
                    or not slot["suffix"].startswith("</path></entry>")
                ):
                    reject()
        if arg0 != 1:
            reject()

        # Every placeholder has a descriptor; no free structural holes.
        def holes(node: Any) -> int:
            if isinstance(node, dict):
                if "$slot" in node:
                    if set(node) != {"$slot"} or type(node["$slot"]) is not int:
                        reject()
                    return 1
                return sum(holes(v) for v in node.values())
            if isinstance(node, list):
                return sum(holes(v) for v in node)
            return 0

        if holes({"body": value["body"], "headers": value["headers"]}) != len(paths):
            reject()
        if len(str(value)) > 4 * 1024 * 1024:
            reject()
        return copy.deepcopy(value)
    except (TypeError, KeyError, IndexError, ValueError, RecursionError):
        reject()
    raise AssertionError("unreachable")


def validate(
    specification: dict[str, Any],
    raw: bytes,
    headers: dict[str, str],
    context: dict[str, Any],
    arg0: Any,
) -> dict[str, Any]:
    """Pure comparison except for the explicitly supplied retained-path checker."""
    try:
        spec = contract(specification)
        if (
            fingerprint(spec["launch"]) != fingerprint(context["launch"])
            or context["active"] is not True
            or type(context["pid"]) is not int
            or context["pid"] <= 0
            or type(context["creation"]) is not int
            or context["creation"] <= 0
        ):
            reject()
        start, now, mono, mono_now, expires = (
            context[k] for k in ("utc", "now", "monotonic", "monotonic_now", "expires")
        )
        if any(
            type(x) not in {int, float} or not math.isfinite(x)
            for x in (start, now, mono, mono_now, expires, context["not_before"])
        ):
            reject()
        if (
            not context["not_before"] <= start <= now < expires
            or not 0 < expires - start <= 180
            or mono_now < mono
            or abs((now - start) - (mono_now - mono)) > 2
        ):
            reject()
        low, high = max(start - 2, context["not_before"]), min(now + 2, expires)
        packet = {"body": strict_json(raw, 4 * 1024 * 1024), "headers": copy.deepcopy(headers)}
        for container in (packet["body"].get("client_metadata", {}), packet["headers"]):
            if "x-codex-turn-metadata" in container:
                encoded = container["x-codex-turn-metadata"]
                if not isinstance(encoded, str):
                    reject()
                container["x-codex-turn-metadata"] = strict_json(encoded.encode())
        groups: dict[str, Any] = {}
        aliases: set[str] = set()
        messages: set[str] = set()
        evidence = []
        for i, slot in enumerate(spec["slots"]):
            parent, leaf = locate(packet, slot["path"])
            value, kind = parent[leaf], slot["kind"]
            if kind in {"time", "time_ms"}:
                scale = 1000 if kind == "time_ms" else 1
                if (
                    type(value) not in ({int} if kind == "time_ms" else {int, float})
                    or not math.isfinite(value)
                    or not low <= value / scale <= high
                ):
                    reject()
            elif kind == "arg0":
                if (
                    not isinstance(value, str)
                    or not value.startswith(slot["prefix"])
                    or not value.endswith(slot["suffix"])
                ):
                    reject()
                if any(marker in value for marker in ("<!", "<?", "xmlns", "xinclude")):
                    reject()
                encoded_path = value[len(slot["prefix"]) : len(value) - len(slot["suffix"])]
                path = html.unescape(encoded_path)
                if encoded_path != path.replace("&", "&amp;").replace("<", "&lt;").replace(
                    ">", "&gt;"
                ):
                    reject()
                # Bounded exact static envelope; declarations/PI/entities rejected above.
                xml = ET.fromstring(value)  # noqa: S314
                matches = [
                    entry
                    for entry in xml.findall(".//file_system/entry")
                    if entry.findtext("path") == path
                ]
                if (
                    xml.tag != "environment_context"
                    or len(matches) != 1
                    or matches[0].attrib != {"access": "read"}
                    or len(matches[0]) != 1
                    or matches[0][0].tag != "path"
                    or matches[0][0].attrib
                    or len(matches[0][0])
                ):
                    reject()
                identity = arg0(path, low, high)
                aliases.add(
                    fingerprint({"domain": "c-min-generated-path-v1", "identity": identity})
                )
            else:
                prefix = "msg_" if kind == "message_id" else ""
                if not isinstance(value, str) or not value.startswith(prefix):
                    reject()
                token = value[len(prefix) :]
                uuid = UUID(token)
                if (
                    str(uuid) != token
                    or uuid.version != slot["uuid_version"]
                    or uuid.variant != "specified in RFC 4122"
                ):
                    reject()
                stamp = (uuid.int >> 80) / 1000
                if uuid.version == 7 and not low <= stamp <= high:
                    reject()
                if kind == "message_id":
                    if value in messages:
                        reject()
                    messages.add(value)
                aliases.add(fingerprint({"domain": "c-min-generated-id-v1", "value": value}))
            if slot["group"] in groups and groups[slot["group"]] != value:
                reject()
            groups[slot["group"]] = value
            evidence.append(fingerprint({"slot": i, "value": value}))
            parent[leaf] = {"$slot": i}
        if fingerprint(packet) != fingerprint({"body": spec["body"], "headers": spec["headers"]}):
            reject()
        return {
            "contract": fingerprint(spec),
            "request": hashlib.sha256(raw).hexdigest(),
            "aliases": sorted(aliases),
            "values": evidence,
            "pid": context["pid"],
            "creation": context["creation"],
            "utc": start,
            "monotonic": mono,
            "expires": expires,
        }
    except (
        TypeError,
        KeyError,
        IndexError,
        ValueError,
        OverflowError,
        RecursionError,
        ET.ParseError,
    ):
        reject()
    raise AssertionError("unreachable")
