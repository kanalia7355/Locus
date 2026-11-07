"""Synthetic state-machine tests; no service, credential or model access."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from loop_engine.audit_packet import (
    CHUNK_LIMIT,
    FILE_LIMIT,
    PACKET_LIMIT,
    binding,
    canonical,
    decode,
    digest,
    validate_packet,
)
from loop_engine.audit_spool import AuditSpool
from loop_engine.security import SafetyError


def packet(nonce="a" * 64, content="print('synthetic')"):
    metadata = {
        key: {"synthetic": key}
        for key in ("goal", "requirements", "architecture", "acceptance", "task_spec", "qa")
    }
    expected = {key: digest(canonical(item)) for key, item in metadata.items()}
    expected.update(
        policy="b" * 64,
        head="c" * 40,
        base="d" * 40,
        task_id="TASK-001",
        attempt=1,
        scope="security",
        nonce=nonce,
    )
    raw = canonical(
        {
            "protocol": "locus-audit-packet-v1",
            "binding": expected,
            "metadata": metadata,
            "files": [{"path": "src/example.py", "base": None, "head": content}],
        }
    )
    return expected, raw


def transfer(spool, expected, raw):
    spool.reserve(expected, digest(raw), len(raw))
    for index, start in enumerate(range(0, len(raw), CHUNK_LIMIT)):
        spool.append(expected["nonce"], index, raw[start : start + CHUNK_LIMIT])


def findings():
    return {"task_id": "TASK-001", "disposition": "pass", "findings": []}


def test_restart_ack_preserves_result_and_nonce(tmp_path):
    expected, raw = packet(content="x" * 100000)
    spool = AuditSpool(tmp_path)
    transfer(spool, expected, raw)
    spool = AuditSpool(tmp_path)
    assert spool.claim(expected) == raw
    with pytest.raises(SafetyError):
        spool.claim(expected)
    result_hash = spool.finish(expected, findings())
    spool = AuditSpool(tmp_path)
    assert spool.result(expected) == findings()
    with pytest.raises(SafetyError):
        spool.acknowledge(expected, "0" * 64)
    spool.acknowledge(expected, result_hash)
    with sqlite3.connect(spool.path) as db:
        assert db.execute("SELECT payload,state FROM packets").fetchone() == (b"", "settled")
    assert spool.result(expected) == findings()
    with pytest.raises(SafetyError):
        spool.reserve(expected, digest(raw), len(raw))
    with pytest.raises(SafetyError):
        spool.acknowledge(expected, result_hash)


def test_transactional_append_only_transitions_survive_restart(tmp_path):
    expected, raw = packet()
    spool = AuditSpool(tmp_path)
    transfer(spool, expected, raw)
    spool.claim(expected)
    result_hash = spool.finish(expected, findings())
    spool.acknowledge(expected, result_hash)
    spool = AuditSpool(tmp_path)
    with sqlite3.connect(spool.path) as db:
        rows = db.execute(
            "SELECT nonce,binding_hash,event,ordinal,result_hash FROM transitions ORDER BY sequence"
        ).fetchall()
        assert [row[2] for row in rows] == ["reserve", "chunk", "running", "finished", "settled"]
        assert all(row[:2] == (expected["nonce"], digest(canonical(expected))) for row in rows)
        assert rows[1][3] == 0
        assert rows[-1][4] == result_hash
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("DELETE FROM transitions")
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("UPDATE transitions SET event='reserve'")


def test_settled_history_has_hard_storage_bound_without_forgetting_nonces(tmp_path, monkeypatch):
    import loop_engine.audit_spool as module

    monkeypatch.setattr(module, "DATABASE_LIMIT", 64 * 1024)
    spool = AuditSpool(tmp_path)
    large = {
        **findings(),
        "findings": [
            {
                "severity": "info",
                "file": "synthetic.py",
                "finding": "a" * 3000,
                "evidence": "b" * 3000,
                "recommended_action": "c" * 3000,
                "blocking": False,
            }
        ],
    }
    completed = []
    stopped = False
    for index in range(20):
        expected, raw = packet(nonce=f"{index:064x}")
        try:
            transfer(spool, expected, raw)
            spool.claim(expected)
            result_hash = spool.finish(expected, large)
            spool.acknowledge(expected, result_hash)
            completed.append(expected)
        except SafetyError:
            stopped = True
            break
    assert stopped and completed
    assert spool.path.stat().st_size <= module.DATABASE_LIMIT
    spool = AuditSpool(tmp_path)
    assert spool.result(completed[0]) == large
    with pytest.raises(SafetyError):
        spool.reserve(completed[0], digest(raw), len(raw))


@pytest.mark.parametrize("index,data", [(1, b"x"), (True, b"x"), (0, b""), (0, b"x")])
def test_bad_chunk_holds_nonce_permanently(tmp_path, index, data):
    expected, raw = packet()
    spool = AuditSpool(tmp_path)
    spool.reserve(expected, digest(raw), len(raw))
    with pytest.raises(SafetyError):
        spool.append(expected["nonce"], index, data)
    with pytest.raises(SafetyError):
        AuditSpool(tmp_path).append(expected["nonce"], 0, raw)


@pytest.mark.parametrize("failure", ["truncated", "digest", "binding", "metadata"])
def test_invalid_packet_holds_without_retry(tmp_path, failure):
    expected, raw = packet()
    wanted = dict(expected)
    if failure == "binding":
        wanted["head"] = "e" * 40
    elif failure == "metadata":
        document = decode(raw)
        document["metadata"]["qa"] = {"synthetic": "changed"}
        raw = canonical(document)
    spool = AuditSpool(tmp_path)
    if failure == "digest":
        spool.reserve(expected, "0" * 64, len(raw))
        spool.append(expected["nonce"], 0, raw)
    elif failure == "truncated":
        spool.reserve(expected, digest(raw), len(raw))
    else:
        transfer(spool, expected, raw)
    with pytest.raises(SafetyError):
        spool.claim(wanted)
    with pytest.raises(SafetyError):
        AuditSpool(tmp_path).claim(expected)


def test_crashed_runner_cannot_be_replayed_or_overwritten(tmp_path):
    expected, raw = packet()
    spool = AuditSpool(tmp_path)
    transfer(spool, expected, raw)
    spool.claim(expected)
    with pytest.raises(SafetyError):
        AuditSpool(tmp_path).claim(expected)
    with pytest.raises(SafetyError):
        spool.finish(expected, {**findings(), "task_id": "TASK-002"})
    with pytest.raises(SafetyError):
        spool.finish(expected, {**findings(), "extra": True})
    with pytest.raises(SafetyError):
        spool.acknowledge(expected, "0" * 64)
    spool.finish(expected, findings())
    with pytest.raises(SafetyError):
        spool.finish(expected, findings())


def test_concurrent_reservation_has_one_winner(tmp_path):
    spool = AuditSpool(tmp_path)
    expected, raw = packet()

    def reserve(_):
        try:
            spool.reserve(expected, digest(raw), len(raw))
            return True
        except SafetyError:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(reserve, range(4))) == 1


def test_spool_capacity_includes_unknown_outcomes(tmp_path):
    spool = AuditSpool(tmp_path)
    for index in range(8):
        expected, raw = packet(nonce=f"{index:064x}")
        transfer(spool, expected, raw)
        spool.claim(expected)
    expected, raw = packet(nonce="f" * 64)
    with pytest.raises(SafetyError, match="full"):
        spool.reserve(expected, digest(raw), len(raw))


@pytest.mark.parametrize(
    "path", ["../x", "a\\x", "a:stream", ".env", "auth.json", "src/CON.txt", "src/../x", "src/x."]
)
def test_packet_rejects_unsafe_paths(path):
    expected, raw = packet()
    value = decode(raw)
    value["files"][0]["path"] = path
    with pytest.raises(SafetyError):
        validate_packet(canonical(value), expected)


def test_packet_limits_and_no_commands():
    expected, raw = packet(content="x" * (FILE_LIMIT + 1))
    with pytest.raises(SafetyError):
        validate_packet(raw, expected)
    expected, raw = packet()
    value = decode(raw)
    value["command"] = "anything"
    with pytest.raises(SafetyError):
        validate_packet(canonical(value), expected)
    value.pop("command")
    value["files"] *= 257
    with pytest.raises(SafetyError):
        validate_packet(canonical(value), expected)
    with pytest.raises(SafetyError):
        decode(b"x" * (PACKET_LIMIT + 1))
    with pytest.raises(SafetyError):
        decode(b'{"x":1,"x":2}')
    with pytest.raises(SafetyError):
        decode(json.dumps({"x": 1}).encode())


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempt", True),
        ("attempt", 4),
        ("scope", []),
        ("head", "refs/heads/main"),
        ("nonce", "../bad"),
    ],
)
def test_binding_strict_types(field, value):
    expected, _ = packet()
    with pytest.raises(SafetyError):
        binding({**expected, field: value})
