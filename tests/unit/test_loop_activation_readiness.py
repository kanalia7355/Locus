"""Readiness observations cannot initialize state or approve engineering gaps."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from loop_engine.activation_readiness import assess, frozen_hash
from loop_engine.cli import initialize
from loop_engine.planning import source_snapshot
from loop_engine.security import fingerprint


def test_missing_database_is_not_created_by_observation(tmp_path: Path) -> None:
    (tmp_path / ".loop/runtime").mkdir(parents=True)
    with pytest.raises(sqlite3.OperationalError):
        frozen_hash(tmp_path)
    assert not (tmp_path / ".loop/runtime/state.sqlite3").exists()


def test_legacy_database_schema_stays_read_only(tmp_path: Path) -> None:
    directory = tmp_path / ".loop/runtime"
    directory.mkdir(parents=True)
    path = directory / "state.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO metadata VALUES ('spec_hash',?)", (json.dumps("a" * 64),))
        db.commit()
    before = path.read_bytes()
    assert frozen_hash(tmp_path) == "a" * 64
    assert path.read_bytes() == before


def test_authenticated_remote_facts_do_not_approve_missing_deployment(tmp_path: Path) -> None:
    initialize(tmp_path, "Synthetic local-only Goal")
    spec = fingerprint(source_snapshot(tmp_path))
    report = assess(
        tmp_path,
        spec,
        remote={
            "review_authenticated": True,
            "merge_authenticated": True,
            "policy": {"issues": []},
            "pull_state": {"autoMergeRequest": None},
        },
    )
    gates = {gate["id"]: gate["status"] for gate in report["gates"]}
    assert gates["frozen_specification"] == "passed"
    assert gates["remote_protection"] == "passed"
    assert gates["isolated_signer"] == gates["controller_broker_connection"] == "blocked"
    assert report["ready_for_activation_approval"] is False
    assert report["merge_authorized"] is False and report["controller_started"] is False
