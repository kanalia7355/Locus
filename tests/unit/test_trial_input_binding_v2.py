"""Approved v2 only; no operator profile, actual authentication or provider."""

import copy
import hashlib
import json

import pytest
from test_trial_input_binding import fixture as base_fixture
from test_trial_input_binding import uuid7

from loop_engine.security import SafetyError
from loop_engine.trial_input_binding import APPROVAL2, VERSION2, contract, locate, validate


def fixture():
    spec, body, ctx = base_fixture()
    thread, context_id = uuid7(ctx["now"], 10), uuid7(ctx["now"], 11)
    turn = body["input"][0]["internal_chat_message_metadata_passthrough"]["turn_id"]
    meta = {
        "session_id": thread,
        "thread_id": thread,
        "turn_id": turn,
        "root_turn_id": turn,
        "window_id": thread + ":0",
        "window_number": 0,
        "context_window_id": context_id,
    }
    body["prompt_cache_key"] = thread
    body["client_metadata"] = {
        "session_id": thread,
        "thread_id": thread,
        "x-codex-window-id": thread + ":0",
        "x-codex-turn-metadata": json.dumps(meta),
    }
    headers = {
        "session-id": thread,
        "thread-id": thread,
        "version": "0.166.0",
        "x-codex-beta-features": "remote_compaction_v2",
        "x-codex-window-id": thread + ":0",
        "x-codex-turn-metadata": json.dumps(meta),
    }
    spec.update(version=VERSION2, approval=APPROVAL2)
    # Build this synthetic template BEFORE validate(), not from an accepted request.
    spec["body"]["prompt_cache_key"] = thread
    spec["body"]["client_metadata"] = {
        **body["client_metadata"],
        "x-codex-turn-metadata": copy.deepcopy(meta),
    }
    spec["headers"] = {**headers, "x-codex-turn-metadata": copy.deepcopy(meta)}

    def slot(path, kind, group):
        value = {"path": path, "kind": kind, "group": group}
        if kind == "window":
            value["thread_group"] = "thread"
        else:
            value["uuid_version"] = 7
        parent, leaf = locate(spec, path)
        parent[leaf] = {"$slot": len(spec["slots"])}
        spec["slots"].append(value)

    slot(["body", "prompt_cache_key"], "session_id", "thread")
    for key in ("session_id", "thread_id"):
        slot(["body", "client_metadata", key], "session_id", "thread")
    for key in ("session-id", "thread-id"):
        slot(["headers", key], "session_id", "thread")
    slot(["body", "client_metadata", "x-codex-window-id"], "window", "window")
    slot(["headers", "x-codex-window-id"], "window", "window")
    for prefix in (
        ["body", "client_metadata", "x-codex-turn-metadata"],
        ["headers", "x-codex-turn-metadata"],
    ):
        for key in ("session_id", "thread_id"):
            slot([*prefix, key], "session_id", "thread")
        for key in ("turn_id", "root_turn_id"):
            slot([*prefix, key], "turn_id", "turn_id")
        slot([*prefix, "context_window_id"], "context_id", "context")
        slot([*prefix, "window_id"], "window", "window")
    return spec, body, headers, ctx


def check(spec, body, headers, ctx):
    return validate(spec, json.dumps(body).encode(), headers, ctx, lambda *args: {"index": 2})


def test_v2_passes_explicit_relations_and_preserves_original_bytes():
    spec, body, headers, ctx = fixture()
    original = copy.deepcopy((body, headers))
    binding = check(spec, body, headers, ctx)
    assert (body, headers) == original
    assert binding["request"] == hashlib.sha256(json.dumps(body).encode()).hexdigest()


@pytest.mark.parametrize(
    "change",
    [
        "counter",
        "bool_counter",
        "window",
        "context",
        "old_context",
        "collision",
        "thread",
        "literal",
        "extra_header",
        "extra_metadata",
        "downgrade",
        "approval",
        "unknown_slot",
    ],
)
def test_v2_unknown_mismatched_or_stale_values_hold(change):
    spec, body, headers, ctx = fixture()
    meta = json.loads(body["client_metadata"]["x-codex-turn-metadata"])
    if change == "counter":
        meta["window_number"] = 1
    elif change == "bool_counter":
        meta["window_number"] = False
    elif change == "window":
        headers["x-codex-window-id"] = headers["session-id"] + ":1"
    elif change == "context":
        meta["context_window_id"] = uuid7(ctx["now"], 100)
    elif change == "old_context":
        meta["context_window_id"] = uuid7(ctx["utc"] - 30, 11)
    elif change == "collision":
        meta["context_window_id"] = meta["turn_id"]
    elif change == "thread":
        headers["thread-id"] = uuid7(ctx["now"], 100)
    elif change == "literal":
        headers["x-codex-beta-features"] = "other"
    elif change == "extra_header":
        headers["another-header"] = "unknown"
    elif change == "extra_metadata":
        meta["unknown"] = "unknown"
    elif change == "downgrade":
        spec["version"] = "c-min-trial-input-contract-v1"
    elif change == "approval":
        spec["approval"] = "unknown"
    else:
        spec["slots"][0]["path"] = ["body", "client_metadata", "unapproved_id"]
    body["client_metadata"]["x-codex-turn-metadata"] = json.dumps(meta)
    with pytest.raises(SafetyError):
        check(spec, body, headers, ctx)


def test_even_template_cannot_authorize_counter_or_header_literal_change():
    spec, _, _, _ = fixture()
    spec["body"]["client_metadata"]["x-codex-turn-metadata"]["window_number"] = 1
    with pytest.raises(SafetyError):
        contract(spec)
    spec, _, _, _ = fixture()
    spec["headers"]["version"] = "new-version"
    with pytest.raises(SafetyError):
        contract(spec)


@pytest.mark.parametrize("field", ["window_id", "context_window_id"])
def test_static_header_template_cannot_bypass_v2_identity_relations(field):
    spec, body, headers, ctx = fixture()
    path = ["headers", "x-codex-turn-metadata", field]
    spec["slots"] = [s for s in spec["slots"] if s["path"] != path]
    for i, slot in enumerate(spec["slots"]):
        node, leaf = locate(spec, slot["path"])
        node[leaf] = {"$slot": i}
    spec["headers"]["x-codex-turn-metadata"][field] = "fixed-wrong-static-value"
    actual = json.loads(headers["x-codex-turn-metadata"])
    actual[field] = "fixed-wrong-static-value"
    headers["x-codex-turn-metadata"] = json.dumps(actual)
    with pytest.raises(SafetyError):
        check(spec, body, headers, ctx)
