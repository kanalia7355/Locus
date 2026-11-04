"""Single derived prefix ID, exact public text, unchanged v1/v2 and replay rules."""

import copy
import hashlib
from uuid import NAMESPACE_DNS, NAMESPACE_OID, uuid5

import pytest
from test_trial_input_binding import journal_fixture, uuid7
from test_trial_input_binding_v2 import check
from test_trial_input_binding_v2 import fixture as v2_fixture

from loop_engine.security import SafetyError
from loop_engine.trial_input_binding import (
    APPROVAL,
    APPROVAL2,
    APPROVAL3,
    VERSION,
    VERSION2,
    VERSION3,
    contract,
)


def fixture():
    spec, body, headers, ctx = v2_fixture()
    text = "Public synthetic base instructions only."
    thread = body["client_metadata"]["thread_id"]
    first = {
        "type": "message",
        "role": "developer",
        "id": "msg_" + str(uuid5(uuid5(NAMESPACE_OID, thread), text)),
        "content": [{"type": "input_text", "text": text}],
        "internal_chat_message_metadata_passthrough": {
            "content_item_kinds": ["model.base_instructions"],
            "content_item_metadata": [{"provenance": {"type": "harness", "hook": False}}],
        },
    }
    body["input"].insert(0, copy.deepcopy(first))
    spec["body"]["input"].insert(0, copy.deepcopy(first))
    for slot in spec["slots"]:
        if slot["path"][:2] == ["body", "input"]:
            slot["path"][2] += 1
    spec.update(version=VERSION3, approval=APPROVAL3)
    slot = {
        "path": ["body", "input", 0, "id"],
        "kind": "base_instruction_id",
        "group": "base-instructions",
        "thread_group": "thread",
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }
    spec["body"]["input"][0]["id"] = {"$slot": len(spec["slots"])}
    spec["slots"].append(slot)
    return spec, body, headers, ctx


def test_exact_derived_id_preserves_packet_and_enters_durable_replay_ledger(tmp_path):
    spec, body, headers, ctx = fixture()
    original = copy.deepcopy(body)
    result = check(spec, body, headers, ctx)
    assert body == original
    _, journal, identifier = journal_fixture(tmp_path, result)
    journal.bind_trial_input(identifier, result)
    assert journal.trial_binding(identifier, "request_validated") == result
    with pytest.raises(SafetyError):
        journal.bind_trial_input(identifier, result)


@pytest.mark.parametrize(
    "change",
    ["prefix", "upper", "namespace", "old_thread", "other_text", "version7", "format5only"],
)
def test_shape_is_never_sufficient(change):
    spec, body, headers, ctx = fixture()
    text = body["input"][0]["content"][0]["text"]
    thread = body["client_metadata"]["thread_id"]
    if change == "prefix":
        value = body["input"][0]["id"].replace("msg_", "at_")
    elif change == "upper":
        value = body["input"][0]["id"].upper()
    elif change == "namespace":
        value = "msg_" + str(uuid5(uuid5(NAMESPACE_DNS, thread), text))
    elif change == "old_thread":
        value = "msg_" + str(uuid5(uuid5(NAMESPACE_OID, uuid7(ctx["utc"] - 30, 10)), text))
    elif change == "other_text":
        value = "msg_" + str(uuid5(uuid5(NAMESPACE_OID, thread), text + "changed"))
    elif change == "version7":
        value = "msg_" + uuid7(ctx["now"], 100)
    else:
        value = "msg_" + str(uuid5(NAMESPACE_OID, "arbitrary"))
    body["input"][0]["id"] = value
    with pytest.raises(SafetyError):
        check(spec, body, headers, ctx)


@pytest.mark.parametrize(
    "change",
    ["text", "role", "content", "provenance", "hook", "kind", "type", "model", "permission"],
)
def test_static_instruction_and_execution_fields_remain_exact(change):
    spec, body, headers, ctx = fixture()
    first = body["input"][0]
    if change == "text":
        first["content"][0]["text"] += "changed"
    elif change == "role":
        first["role"] = "user"
    elif change == "content":
        first["content"].append({"type": "input_text", "text": "extra"})
    elif change == "provenance":
        first["internal_chat_message_metadata_passthrough"]["content_item_metadata"] = [
            {"provenance": {"type": "user"}}
        ]
    elif change == "hook":
        first["internal_chat_message_metadata_passthrough"]["content_item_metadata"][0][
            "provenance"
        ]["hook"] = True
    elif change == "kind":
        first["internal_chat_message_metadata_passthrough"]["content_item_kinds"] = ["unapproved"]
    elif change == "type":
        first["type"] = "additional_tools"
    elif change == "model":
        body["model"] = "other-model"
    else:
        ctx["launch"] = {"permissions": "write"}
    with pytest.raises(SafetyError):
        check(spec, body, headers, ctx)


@pytest.mark.parametrize(
    "change", ["hash", "index", "uuid_version", "missing", "dynamic_text", "v1", "v2"]
)
def test_no_general_uuid5_or_old_contract_upgrade(change):
    spec, _, _, _ = fixture()
    slot = spec["slots"][-1]
    if change == "hash":
        slot["text_sha256"] = "0" * 64
    elif change == "index":
        slot["path"][2] = 1
    elif change == "uuid_version":
        slot["uuid_version"] = 5
    elif change == "missing":
        spec["slots"].pop()
    elif change == "dynamic_text":
        spec["body"]["input"][0]["content"][0]["text"] = {"$slot": 99}
    elif change == "v1":
        spec.update(version=VERSION, approval=APPROVAL)
    else:
        spec.update(version=VERSION2, approval=APPROVAL2)
    with pytest.raises(SafetyError):
        contract(spec)


@pytest.mark.parametrize(
    "permit_version,contract_version",
    [
        (VERSION, VERSION2),
        (VERSION, VERSION3),
        (VERSION2, VERSION),
        (VERSION2, VERSION3),
        (VERSION3, VERSION),
        (VERSION3, VERSION2),
    ],
)
def test_explicit_permit_version_must_match_contract(
    tmp_path, monkeypatch, permit_version, contract_version
):
    from test_c_min_trial import fixture as trial_fixture
    from test_trial_input_binding import fixture as v1_fixture

    from loop_engine.approval import ApprovalQueue
    from loop_engine.c_min_trial import authorize
    from loop_engine.security import fingerprint

    state, work, _, permit, _ = trial_fixture(tmp_path, monkeypatch)
    spec = {VERSION: v1_fixture, VERSION2: v2_fixture, VERSION3: fixture}[contract_version]()[0]
    state.set_metadata("c_min_trial_input_contract", spec)
    permit.update(input_version=permit_version, input_hash=fingerprint(spec))
    state.set_metadata("c_min_trial_permit", permit)
    queue = ApprovalQueue(state)
    decision = queue.request(None, "scope", fingerprint(permit), "Synthetic mismatched version")
    queue.resolve(
        [
            {
                "id": decision,
                "action": "approve",
                "target_hash": fingerprint(permit),
                "reason": "Synthetic authorization regression only",
            }
        ],
        "fixture",
    )
    with pytest.raises(SafetyError, match="versioned trial input contract"):
        authorize(tmp_path, state, work, "artifact", decision)
    with state.connect() as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='c_min_trials'").fetchone()
