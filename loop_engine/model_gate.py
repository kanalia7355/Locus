"""C-min v3 closed Lite contracts; no I/O, credentials or content diagnostics."""

import json
from typing import Any

from jsonschema import Draft202012Validator

from loop_engine.security import SafetyError

VERSION = 3
FRAME_LIMIT = 1024 * 1024
TOTAL_LIMIT = 16 * FRAME_LIMIT
TEXT = {"type": "string", "maxLength": FRAME_LIMIT}
BOOL = {"type": "boolean"}
INDEX = {"type": "integer", "minimum": 0, "maximum": 10000}


def obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
        "required": required if required is not None else list(properties),
    }


def arr(item: Any, maximum: int = 10000) -> dict[str, Any]:
    return {"type": "array", "items": item, "maxItems": maximum}


def literal(value: Any) -> dict[str, Any]:
    return {"const": value}


class ContractError(SafetyError):
    def __init__(self, path: tuple[Any, ...], details: list[Any]):
        super().__init__("C-min contract rejected")
        self.schema_path = path
        self.schema_details = details


def check(schema: dict[str, Any], value: Any) -> None:
    error = next(Draft202012Validator(schema).iter_errors(value), None)
    if error is not None:
        raise ContractError(
            tuple(error.absolute_schema_path),
            [tuple(x.absolute_schema_path) for x in error.context],
        )


def strict_json(raw: bytes, limit: int = FRAME_LIMIT) -> Any:
    if not 0 < len(raw) <= limit:
        raise SafetyError("C-min size rejected")
    try:
        # Check depth before allocating a recursive JSON tree, ignoring quoted data.
        depth, quoted, escaped = 0, False, False
        for char in raw.decode("utf-8", errors="strict"):
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > 64:
                    raise ValueError()
            elif char in "]}":
                depth -= 1

        def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in items:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result

        def invalid(_: str) -> Any:
            raise ValueError()

        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
        json.dumps(value, ensure_ascii=False).encode("utf-8", errors="strict")
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise SafetyError("C-min JSON rejected") from None


PART = obj({"type": literal("input_text"), "text": TEXT})
PROVENANCE = {
    "oneOf": [
        obj({"type": literal("harness"), "hook": literal(False)}),
        obj({"type": literal("user")}),
    ]
}
ATTRIBUTION = obj(
    {
        "content_item_kinds": arr(TEXT, 256),
        "content_item_metadata": arr(obj({"provenance": PROVENANCE}), 256),
        "turn_id": TEXT,
        "create_time": {"type": ["string", "number"]},
    },
    [],
)
MESSAGE = obj(
    {
        "type": literal("message"),
        "role": {"enum": ["developer", "system", "user"]},
        "id": TEXT,
        "content": {"oneOf": [TEXT, arr(PART, 256)]},
        "internal_chat_message_metadata_passthrough": ATTRIBUTION,
    },
    ["role", "content"],
)
REASONING_CONFIG = obj(
    {
        "effort": {"enum": ["low", "medium", "high", "xhigh", "max", "ultra"]},
        "summary": {"enum": ["none", "auto", "concise", "detailed"]},
        "context": literal("all_turns"),
    },
    [],
)
TURN_FIELDS: dict[str, Any] = {
    k: TEXT
    for k in (
        "installation_id",
        "session_id",
        "thread_id",
        "agent_name",
        "turn_id",
        "window_id",
        "context_window_id",
        "request_kind",
        "history_initialization",
        "root_turn_id",
        "thread_source",
        "turn_trigger",
        "sandbox",
        "sandbox_mode",
        "model",
        "reasoning_effort",
    )
}
TURN_FIELDS.update(
    {
        k: BOOL
        for k in (
            "auto_review_enabled",
            "node_repl_auto_review_required",
            "node_repl_disabled",
            "analytics_enabled",
        )
    }
)
TURN_FIELDS.update(
    {
        "window_number": INDEX,
        "turn_started_at_unix_ms": {"type": "integer"},
        "workspaces": {
            "type": "object",
            "maxProperties": 8,
            "additionalProperties": obj(
                {
                    "associated_remote_urls": obj({"origin": TEXT}, []),
                    "latest_git_commit_hash": TEXT,
                    "has_changes": BOOL,
                },
                [],
            ),
        },
    }
)


def validate_request(raw: bytes, model: str, schema: dict[str, Any], roots: set[str]) -> Any:
    """No transformations: authoritative metadata is parsed, never trusted as opaque JSON."""
    value = strict_json(raw, 4 * FRAME_LIMIT)
    metadata = obj(
        {
            **{
                k: TEXT
                for k in (
                    "x-codex-window-id",
                    "x-codex-installation-id",
                    "turn_id",
                    "session_id",
                    "root_turn_id",
                    "thread_id",
                    "x-codex-turn-metadata",
                )
            },
            "mcp_attribution": {"oneOf": [TEXT, obj({"status": TEXT})]},
        },
        [],
    )
    request = obj(
        {
            "model": literal(model),
            "input": arr(
                {
                    "oneOf": [
                        MESSAGE,
                        obj(
                            {"type": literal("configuration_update"), "reasoning": REASONING_CONFIG}
                        ),
                        obj(
                            {
                                "type": literal("additional_tools"),
                                "role": literal("developer"),
                                "id": TEXT,
                                "tools": literal([]),
                            },
                            ["type", "role", "tools"],
                        ),
                    ]
                },
                1024,
            ),
            "stream": literal(True),
            "store": literal(False),
            "tools": literal([]),
            "tool_choice": {"enum": ["auto", "none"]},
            "parallel_tool_calls": literal(False),
            "reasoning": REASONING_CONFIG,
            "text": obj(
                {
                    "format": literal(
                        {
                            "type": "json_schema",
                            "name": "codex_output_schema",
                            "strict": True,
                            "schema": schema,
                        }
                    ),
                    "verbosity": {"enum": ["low", "medium", "high"]},
                },
                ["format"],
            ),
            "include": arr({"enum": ["reasoning.encrypted_content"]}, 1),
            "prompt_cache_key": TEXT,
            "client_metadata": metadata,
        },
        ["model", "input", "stream", "store", "text"],
    )
    check(request, value)
    mcp = value.get("client_metadata", {}).get("mcp_attribution")
    if isinstance(mcp, str):
        check(obj({"status": TEXT}), strict_json(mcp.encode("utf-8")))
    if not value["input"]:
        raise SafetyError("C-min empty input rejected")
    encoded = value.get("client_metadata", {}).get("x-codex-turn-metadata")
    if encoded is not None:
        turn = strict_json(encoded.encode("utf-8"))
        check(obj(TURN_FIELDS, []), turn)
        if set(turn.get("workspaces", {})) - roots:
            raise SafetyError("C-min metadata root rejected")
    return value


OUTPUT_TEXT = obj({"type": literal("output_text"), "text": TEXT, "annotations": literal([])})
OUTPUT_MESSAGE = obj(
    {
        "type": literal("message"),
        "id": TEXT,
        "role": literal("assistant"),
        "status": {"enum": ["in_progress", "completed"]},
        "content": arr(OUTPUT_TEXT, 1),
    }
)
OUTPUT_REASONING = obj(
    {
        "type": literal("reasoning"),
        "id": TEXT,
        "summary": arr(obj({"type": literal("summary_text"), "text": TEXT}), 32),
        "encrypted_content": TEXT,
        "status": {"enum": ["in_progress", "completed"]},
    },
    ["type", "id", "summary"],
)
OUTPUT_ITEM = {"oneOf": [OUTPUT_MESSAGE, OUTPUT_REASONING]}
TOKENS = {"type": "integer", "minimum": 0, "maximum": 2147483647}
USAGE = obj(
    {
        "input_tokens": TOKENS,
        "output_tokens": TOKENS,
        "total_tokens": TOKENS,
        "input_tokens_details": obj({"cached_tokens": TOKENS}, []),
        "output_tokens_details": obj({"reasoning_tokens": TOKENS}, []),
    },
    ["input_tokens", "output_tokens", "total_tokens"],
)


class ResponseGate:
    """Bounded incremental parser. A rejected frame is never returned to its caller."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.buffer = bytearray()
        self.total = self.frames = 0
        self.response_id: str | None = None
        self.items: dict[int, Any] = {}
        self.finished: dict[int, Any] = {}
        self.deltas: dict[tuple[int, int], str] = {}
        self.text_done: set[tuple[int, int]] = set()
        self.completed = False
        self.in_progress = False

    def feed(self, data: bytes) -> list[bytes]:
        self.total += len(data)
        if self.total > TOTAL_LIMIT or self.completed and data.strip():
            raise SafetyError("C-min stream limit/order rejected")
        self.buffer.extend(data)
        safe = []
        while True:
            end = self.buffer.find(b"\n\n")
            if end < 0:
                if len(self.buffer) > FRAME_LIMIT:
                    raise SafetyError("C-min frame limit exceeded")
                break
            raw = bytes(self.buffer[: end + 2])
            del self.buffer[: end + 2]
            if len(raw) > FRAME_LIMIT or self.completed:
                raise SafetyError("C-min frame limit/order rejected")
            self.frames += 1
            if self.frames > 10000:
                raise SafetyError("C-min frame count exceeded")
            lines = raw[:-2].split(b"\n")
            if (
                len(lines) != 2
                or not lines[0].startswith(b"event: ")
                or not lines[1].startswith(b"data: ")
            ):
                raise SafetyError("C-min SSE framing rejected")
            event = lines[0][7:].decode("ascii", errors="strict")
            value = strict_json(lines[1][6:])
            self.event(event, value)
            safe.append(raw)
        return safe

    def event(self, kind: str, value: Any) -> None:
        base: dict[str, Any] = {"type": literal(kind)}
        if kind in {"response.created", "response.in_progress", "response.completed"}:
            response = obj(
                {
                    "id": TEXT,
                    "object": literal("response"),
                    "status": literal("completed" if kind.endswith("completed") else "in_progress"),
                    "model": literal(self.model),
                    "output": arr(OUTPUT_ITEM, 64),
                    "usage": USAGE,
                },
                ["id", "object", "status", "output"],
            )
            check(obj({**base, "response": response}), value)
            result = value["response"]
            if kind == "response.created":
                if self.response_id is not None or result["output"]:
                    raise SafetyError("C-min duplicate creation rejected")
                self.response_id = result["id"]
            elif self.response_id != result["id"]:
                raise SafetyError("C-min response binding rejected")
            if kind == "response.in_progress":
                if result["output"] or self.items or self.in_progress:
                    raise SafetyError("C-min early/repeated progress rejected")
                self.in_progress = True
            if kind == "response.completed":
                if not self.finished or self.items != self.finished:
                    raise SafetyError("C-min incomplete output rejected")
                outputs = [self.finished[i] for i in sorted(self.finished)]
                if outputs != result["output"] or sum(x["type"] == "message" for x in outputs) != 1:
                    raise SafetyError("C-min terminal output rejected")
                self.completed = True
            return
        if self.response_id is None:
            raise SafetyError("C-min missing creation rejected")
        if kind in {"response.output_item.added", "response.output_item.done"}:
            check(obj({**base, "output_index": INDEX, "item": OUTPUT_ITEM}), value)
            index, item = value["output_index"], value["item"]
            if kind.endswith("added"):
                if item["type"] == "message" and (
                    item["status"] != "in_progress" or item["content"]
                ):
                    raise SafetyError("C-min streamed message must start empty")
                if (
                    index in self.items
                    or index != len(self.items)
                    or any(x["id"] == item["id"] for x in self.items.values())
                ):
                    raise SafetyError("C-min duplicate output rejected")
                self.items[index] = item
            else:
                if index not in self.items and index == len(self.items):
                    if any(x["id"] == item["id"] for x in self.items.values()):
                        raise SafetyError("C-min duplicate output rejected")
                    self.items[index] = item
                if index not in self.items or index in self.finished:
                    raise SafetyError("C-min unknown/duplicate completion rejected")
                original = self.items[index]
                if original["type"] == "reasoning" and {
                    key: value for key, value in original.items() if key != "status"
                } != {key: value for key, value in item.items() if key != "status"}:
                    raise SafetyError("C-min reasoning snapshot changed without supported deltas")
                if original["type"] == "message" and original["content"]:
                    if original["content"] != item["content"] and not any(
                        key[0] == index for key in self.deltas
                    ):
                        raise SafetyError("C-min contradictory output snapshot")
                    if original["status"] == "completed" and original != item:
                        raise SafetyError("C-min completed item changed")
                if item["type"] == "message" and (
                    item["status"] != "completed" or len(item["content"]) != 1
                ):
                    raise SafetyError("C-min final message rejected")
                if (original["id"], original["type"]) != (item["id"], item["type"]):
                    raise SafetyError("C-min output binding rejected")
                for key, text in self.deltas.items():
                    if key[0] == index and (
                        key not in self.text_done
                        or item["type"] != "message"
                        or item["content"][key[1]]["text"] != text
                    ):
                        raise SafetyError("C-min text binding rejected")
                self.items[index] = self.finished[index] = item
            return
        if kind in {"response.output_text.delta", "response.output_text.done"}:
            field = "delta" if kind.endswith("delta") else "text"
            check(
                obj(
                    {
                        **base,
                        "item_id": TEXT,
                        "output_index": INDEX,
                        "content_index": literal(0),
                        field: TEXT,
                    }
                ),
                value,
            )
            index = value["output_index"]
            if (
                index not in self.items
                or index in self.finished
                or self.items[index]["type"] != "message"
                or self.items[index]["id"] != value["item_id"]
            ):
                raise SafetyError("C-min text order rejected")
            key = (index, value["content_index"])
            if key in self.text_done:
                raise SafetyError("C-min duplicate text completion rejected")
            if field == "delta":
                self.deltas[key] = self.deltas.get(key, "") + value[field]
                if len(self.deltas[key].encode()) > FRAME_LIMIT:
                    raise SafetyError("C-min text size exceeded")
            else:
                if self.deltas.get(key, "") != value[field]:
                    raise SafetyError("C-min text differs")
                self.text_done.add(key)
            return
        # No prefix-based acceptance. Unknown reasoning/event variants stay held.
        raise SafetyError("C-min event rejected")

    def finish(self) -> None:
        if self.buffer or not self.completed:
            raise SafetyError("C-min truncated stream rejected")
