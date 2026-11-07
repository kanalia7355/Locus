"""Synthetic packets only: finite generated slots, durable one-send binding."""

import copy
import hashlib
import json
import time
from uuid import UUID

import pytest

from loop_engine.c_min_trial import PROMPT, SCHEMA, reserve
from loop_engine.model_invocations import InvocationJournal
from loop_engine.security import SafetyError, fingerprint
from loop_engine.state_store import StateStore
from loop_engine.trial_input_binding import APPROVAL, VERSION, contract, validate


def uuid7(stamp, suffix=1):
    return str(UUID(int=(int(stamp * 1000) << 80) | (7 << 76) | (2 << 62) | suffix))


def fixture():
    now = time.time()
    prefix = (
        '<environment_context><filesystem><permission_profile type="managed">'
        '<file_system><entry access="read"><path>'
    )
    suffix = "</path></entry></file_system></permission_profile></filesystem></environment_context>"
    path = "C:\\synthetic\\home\\tmp\\arg0-windows\\codex-arg0ABC123"
    body = {
        "model": "gpt-6.1-sol",
        "stream": True,
        "store": False,
        "tools": [],
        "input": [
            {
                "type": "message",
                "role": "user",
                "id": "msg_" + uuid7(now),
                "content": [
                    {"type": "input_text", "text": prefix + path + suffix},
                    {"type": "input_text", "text": PROMPT},
                ],
                "internal_chat_message_metadata_passthrough": {
                    "turn_id": uuid7(now, 2),
                    "create_time": now,
                },
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "codex_output_schema",
                "strict": True,
                "schema": SCHEMA,
            }
        },
    }
    launch = {"model": "gpt-6.1-sol", "permissions": "read-only"}
    specification = {
        "version": VERSION,
        "approval": APPROVAL,
        "body": copy.deepcopy(body),
        "headers": {},
        "launch": launch,
        "slots": [],
    }
    for kind, pointer in [
        ("message_id", ["input", 0, "id"]),
        ("turn_id", ["input", 0, "internal_chat_message_metadata_passthrough", "turn_id"]),
        ("time", ["input", 0, "internal_chat_message_metadata_passthrough", "create_time"]),
        ("arg0", ["input", 0, "content", 0, "text"]),
    ]:
        slot = {"path": ["body", *pointer], "kind": kind, "group": kind}
        if kind in {"message_id", "turn_id"}:
            slot["uuid_version"] = 7
        if kind == "arg0":
            slot.update(prefix=prefix, suffix=suffix)
        index = len(specification["slots"])
        specification["slots"].append(slot)
        node = specification["body"]
        for key in pointer[:-1]:
            node = node[key]
        node[pointer[-1]] = {"$slot": index}
    context = {
        "launch": launch,
        "active": True,
        "pid": 123,
        "creation": 456,
        "utc": now - 0.5,
        "now": now + 0.1,
        "monotonic": 1.0,
        "monotonic_now": 1.6,
        "expires": now + 60,
        "not_before": now - 60,
    }
    return specification, body, context


def check(spec, body, ctx, headers=None):
    def path(value, low, high):
        assert value.endswith("codex-arg0ABC123")
        return {"volume": 1, "index": 2, "created": 3}

    return validate(spec, json.dumps(body).encode(), headers or {}, ctx, path)


def test_closed_template_keeps_full_original_request_hash():
    spec, body, ctx = fixture()
    original = copy.deepcopy(body)
    binding = check(spec, body, ctx)
    assert body == original
    assert binding["request"] == hashlib.sha256(json.dumps(body).encode()).hexdigest()
    assert binding["contract"] == fingerprint(spec)
    assert len(binding["aliases"]) == 3
    assert len(binding["values"]) == 4


@pytest.mark.parametrize(
    "change", ["model", "text", "schema", "tools", "role", "extra", "order", "headers"]
)
def test_fixed_or_unknown_input_rejected(change):
    spec, body, ctx = fixture()
    headers = {}
    if change == "model":
        body["model"] = "other"
    elif change == "text":
        body["input"][0]["content"][1]["text"] += "!"
    elif change == "schema":
        body["text"]["format"]["strict"] = False
    elif change == "tools":
        body["tools"] = [{"type": "function"}]
    elif change == "role":
        body["input"][0]["role"] = "developer"
    elif change == "extra":
        body["unknown"] = "unassessed"
    elif change == "order":
        body["input"][0]["content"].reverse()
    else:
        headers["unknown"] = "unassessed"
    with pytest.raises(SafetyError):
        check(spec, body, ctx, headers)


@pytest.mark.parametrize(
    "change",
    [
        "old",
        "future",
        "version",
        "uppercase",
        "prefix",
        "bool",
        "nan",
        "time_string",
        "expiry",
        "skew",
        "pid",
        "creation",
        "inactive",
        "launch",
    ],
)
def test_generated_values_and_owned_launch_fail_closed(change):
    spec, body, ctx = fixture()
    item = body["input"][0]
    if change == "old":
        item["id"] = "msg_" + uuid7(ctx["utc"] - 20)
    elif change == "future":
        item["id"] = "msg_" + uuid7(ctx["expires"] + 10)
    elif change == "version":
        item["id"] = "msg_00000000-0000-4000-8000-000000000001"
    elif change == "uppercase":
        item["id"] = item["id"].upper()
    elif change == "prefix":
        item["id"] = "other_" + uuid7(ctx["now"])
    elif change == "bool":
        item["internal_chat_message_metadata_passthrough"]["create_time"] = True
    elif change == "nan":
        item["internal_chat_message_metadata_passthrough"]["create_time"] = float("nan")
    elif change == "time_string":
        item["internal_chat_message_metadata_passthrough"]["create_time"] = str(ctx["now"])
    elif change == "expiry":
        ctx["now"] = ctx["expires"]
    elif change == "skew":
        ctx["monotonic_now"] += 10
    elif change == "pid":
        ctx["pid"] = True
    elif change == "creation":
        ctx["creation"] = 0
    elif change == "inactive":
        ctx["active"] = False
    else:
        ctx["launch"] = {"permissions": "write"}
    with pytest.raises(SafetyError):
        check(spec, body, ctx)


@pytest.mark.parametrize(
    "change", ["wildcard", "unknown", "duplicate", "unlisted", "arg0_count", "placeholder"]
)
def test_manifest_never_learns_new_slots(change):
    spec, _, _ = fixture()
    if change == "wildcard":
        spec["slots"][0]["path"][2] = "*"
    elif change == "unknown":
        spec["slots"][0]["kind"] = "any_string"
    elif change == "duplicate":
        spec["slots"].append(copy.deepcopy(spec["slots"][0]))
    elif change == "unlisted":
        spec["body"]["unknown"] = {"$slot": 0}
    elif change == "arg0_count":
        spec["slots"].pop()
    else:
        spec["body"]["input"][0]["id"] = "unbound"
    with pytest.raises(SafetyError):
        contract(spec)


def journal_fixture(tmp_path, binding):
    state = StateStore(tmp_path / "state.db")
    permit = {"synthetic": True}
    owner = reserve(state, permit, "artifact")
    journal = InvocationJournal(state)
    invocation = journal.claim(owner, "artifact", binding["expires"])
    journal.advance(invocation, "prepared", "launch_reserved")
    return state, journal, invocation


def test_binding_is_atomic_and_duplicate_never_advances_or_sends(tmp_path):
    spec, body, ctx = fixture()
    value = check(spec, body, ctx)
    state, journal, invocation = journal_fixture(tmp_path, value)
    journal.bind_trial_input(invocation, value)
    with pytest.raises(SafetyError):
        journal.bind_trial_input(invocation, value)
    with state.connect() as db:
        assert (
            db.execute("SELECT phase FROM model_invocations").fetchone()[0] == "request_validated"
        )
        assert db.execute("SELECT count(*) FROM trial_input_bindings").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM trial_input_aliases").fetchone()[0] == 3
        document = db.execute("SELECT document FROM trial_input_bindings").fetchone()[0]
        assert PROMPT not in document and "auth" not in document


def test_alias_collision_rolls_back_every_row_and_phase(tmp_path):
    spec, body, ctx = fixture()
    value = check(spec, body, ctx)
    state, journal, invocation = journal_fixture(tmp_path, value)
    with state.connect() as db:
        db.execute("CREATE TABLE trial_input_aliases (identity TEXT PRIMARY KEY, invocation TEXT)")
        db.execute("INSERT INTO trial_input_aliases VALUES (?,?)", (value["aliases"][-1], "older"))
    with pytest.raises(SafetyError):
        journal.bind_trial_input(invocation, value)
    with state.connect() as db:
        assert db.execute("SELECT phase FROM model_invocations").fetchone()[0] == "launch_reserved"
        assert db.execute("SELECT count(*) FROM trial_input_aliases").fetchone()[0] == 1
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='trial_input_bindings'"
        ).fetchone()


@pytest.mark.parametrize(
    "change", ["none", "different_turn", "string_time", "unknown", "duplicate_key"]
)
def test_embedded_metadata_is_closed_and_cross_bound(change):
    spec, body, ctx = fixture()
    turn = body["input"][0]["internal_chat_message_metadata_passthrough"]["turn_id"]
    metadata = {"turn_id": turn, "turn_started_at_unix_ms": int(ctx["now"] * 1000)}
    template = {"turn_id": {"$slot": 4}, "turn_started_at_unix_ms": {"$slot": 5}}
    spec["body"]["client_metadata"] = {"x-codex-turn-metadata": template}
    spec["slots"].extend(
        [
            {
                "path": ["body", "client_metadata", "x-codex-turn-metadata", "turn_id"],
                "kind": "turn_id",
                "group": "turn_id",
                "uuid_version": 7,
            },
            {
                "path": [
                    "body",
                    "client_metadata",
                    "x-codex-turn-metadata",
                    "turn_started_at_unix_ms",
                ],
                "kind": "time_ms",
                "group": "start_time_ms",
            },
        ]
    )
    if change == "different_turn":
        metadata["turn_id"] = uuid7(ctx["now"], 99)
    elif change == "string_time":
        metadata["turn_started_at_unix_ms"] = "1000"
    elif change == "unknown":
        metadata["unknown"] = True
    encoded = json.dumps(metadata)
    if change == "duplicate_key":
        encoded = encoded[:-1] + ',"turn_id":"duplicate"}'
    body["client_metadata"] = {"x-codex-turn-metadata": encoded}
    if change == "none":
        assert check(spec, body, ctx)["request"]
    else:
        with pytest.raises(SafetyError):
            check(spec, body, ctx)


def test_static_equality_does_not_conflate_booleans_and_numbers():
    spec, body, ctx = fixture()
    spec["body"]["store"] = 0
    with pytest.raises(SafetyError):
        check(spec, body, ctx)


def test_concurrent_binding_claim_is_once_and_survives_reopen(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    spec, body, ctx = fixture()
    value = check(spec, body, ctx)
    state, journal, invocation = journal_fixture(tmp_path, value)

    def claim(_):
        try:
            journal.bind_trial_input(invocation, value)
            return "bound"
        except SafetyError:
            return "held"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, range(2))) == ["bound", "held"]
    reopened = InvocationJournal(StateStore(state.path))
    assert reopened.trial_binding(invocation, "request_validated") == value
    with pytest.raises(SafetyError):
        reopened.bind_trial_input(invocation, value)


def test_transaction_failure_after_first_alias_preserves_launch_reservation(tmp_path):
    spec, body, ctx = fixture()
    value = check(spec, body, ctx)
    state, journal, invocation = journal_fixture(tmp_path, value)
    with state.connect() as db:
        db.execute("CREATE TABLE trial_input_aliases (identity TEXT PRIMARY KEY, invocation TEXT)")
        db.execute(
            "CREATE TRIGGER synthetic_abort BEFORE INSERT ON trial_input_aliases "
            "WHEN (SELECT count(*) FROM trial_input_aliases)>0 "
            "BEGIN SELECT RAISE(ABORT,'synthetic disk failure'); END"
        )
    with pytest.raises(SafetyError):
        journal.bind_trial_input(invocation, value)

    with state.connect() as db:
        assert db.execute("SELECT count(*) FROM trial_input_aliases").fetchone()[0] == 0
        assert db.execute("SELECT phase FROM model_invocations").fetchone()[0] == "launch_reserved"
    journal.hold(invocation)
    with pytest.raises(SafetyError):
        journal.bind_trial_input(invocation, value)


@pytest.mark.parametrize("field", ["window_id", "context_window_id", "x-codex-window-id"])
def test_newly_discovered_window_values_remain_fixed_or_rejected(field):
    spec, body, ctx = fixture()
    if field == "x-codex-window-id":
        path = ["body", "client_metadata", field]
        body["client_metadata"] = {field: "changed-value"}
        spec["body"]["client_metadata"] = {field: "original-value"}
    else:
        path = ["body", "client_metadata", "x-codex-turn-metadata", field]
        body["client_metadata"] = {"x-codex-turn-metadata": json.dumps({field: "changed-value"})}
        spec["body"]["client_metadata"] = {"x-codex-turn-metadata": {field: "original-value"}}
    with pytest.raises(SafetyError):
        check(spec, body, ctx)
    spec["slots"].append(
        {"path": path, "kind": "session_id", "group": "unapproved_window", "uuid_version": 7}
    )
    parent = spec
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = {"$slot": len(spec["slots"]) - 1}
    with pytest.raises(SafetyError):
        contract(spec)  # Cannot turn a new producer field into a generic UUID exception.
