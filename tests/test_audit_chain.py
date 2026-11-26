"""Audit chain append-only, tamper detection, and integrity endpoint regressions (T-PH7-214)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from app.service import AUDIT_CHAIN_GENESIS, Principal, Service, _audit_hash_payload
from test_api import ORIGIN, client_for, login


def _raw(db_path: Path) -> sqlite3.Connection:
    """Open a separate raw connection that can bypass service-managed triggers.

    The bypass is intentional: tamper tests must mutate committed rows in ways
    the append-only triggers correctly forbid on the normal path.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


def _db_path(service: Service) -> Path:
    return Path(service.conn.execute("PRAGMA database_list").fetchone()[2])


def _drop_append_only_triggers(raw: sqlite3.Connection) -> None:
    # Explicit bypass of the append-only guards so the test exercises the
    # verification routine, not the trigger rejection path.
    for name in (
        "audit_no_update",
        "audit_no_delete",
        "audit_chain_no_update",
        "audit_chain_no_delete",
        "audit_chain_head_no_delete",
    ):
        raw.execute(f"DROP TRIGGER IF EXISTS {name}")


def _admin(service: Service) -> Principal:
    row = service.conn.execute(
        "SELECT id, username, system_admin, must_rotate FROM users WHERE username='admin'"
    ).fetchone()
    return Principal(
        id=row["id"],
        username=row["username"],
        system_admin=bool(row["system_admin"]),
        must_rotate=bool(row["must_rotate"]),
    )


def _audit_ids(service: Service) -> list[str]:
    rows = service.conn.execute("SELECT id FROM audit ORDER BY at ASC, id ASC").fetchall()
    return [row["id"] for row in rows]


def _middle_audit_id(service: Service) -> str:
    ids = _audit_ids(service)
    assert len(ids) >= 3
    return ids[len(ids) // 2]


def test_audit_chain_ok_and_legitimate_append(service: Service) -> None:
    actor = _admin(service)
    result = service.verify_audit_chain(actor)
    assert result["ok"] is True
    assert result["first_bad_id"] is None
    assert result["reason"] == "ok"
    assert (
        result["checked"] == service.conn.execute("SELECT COUNT(*) AS c FROM audit").fetchone()["c"]
    )

    # Legitimate append through the normal service path keeps the chain valid.
    service.create_project("org-a", "chain-project", "Chain project")
    after = service.verify_audit_chain(actor)
    assert after["ok"] is True
    assert after["checked"] == result["checked"] + 1


def test_audit_chain_detects_middle_row_tamper(service: Service) -> None:
    actor = _admin(service)
    target = _middle_audit_id(service)
    path = _db_path(service)

    raw = _raw(path)
    try:
        _drop_append_only_triggers(raw)
        # Explicit bypass: mutate a committed audit row directly.
        raw.execute("UPDATE audit SET outcome='denied' WHERE id=?", (target,))
        raw.commit()
    finally:
        raw.close()

    result = service.verify_audit_chain(actor)
    assert result["ok"] is False
    assert result["first_bad_id"] == target
    assert (
        result["checked"] < service.conn.execute("SELECT COUNT(*) AS c FROM audit").fetchone()["c"]
    )


def test_audit_chain_detects_middle_row_deletion(service: Service) -> None:
    actor = _admin(service)
    target = _middle_audit_id(service)
    path = _db_path(service)

    raw = _raw(path)
    try:
        _drop_append_only_triggers(raw)
        # Explicit bypass: delete a committed middle row directly.
        raw.execute("DELETE FROM audit_chain WHERE audit_id=?", (target,))
        raw.execute("DELETE FROM audit WHERE id=?", (target,))
        raw.commit()
    finally:
        raw.close()

    result = service.verify_audit_chain(actor)
    assert result["ok"] is False


def test_audit_chain_detects_tail_row_deletion_by_head_count(service: Service) -> None:
    actor = _admin(service)
    ids = _audit_ids(service)
    target = ids[-1]
    path = _db_path(service)

    raw = _raw(path)
    try:
        _drop_append_only_triggers(raw)
        # Explicit bypass: remove the tail row; head row_count is now stale.
        raw.execute("DELETE FROM audit_chain WHERE audit_id=?", (target,))
        raw.execute("DELETE FROM audit WHERE id=?", (target,))
        raw.commit()
    finally:
        raw.close()

    result = service.verify_audit_chain(actor)
    assert result["ok"] is False
    assert result["reason"] == "tail truncation"


def test_audit_chain_detects_middle_insertion(service: Service) -> None:
    actor = _admin(service)
    path = _db_path(service)
    now = service.conn.execute("SELECT MAX(at) AS at FROM audit").fetchone()["at"]

    raw = _raw(path)
    try:
        _drop_append_only_triggers(raw)
        # Explicit bypass: drop the chain trigger too, so the forged row is
        # inserted without a matching audit_chain entry.
        raw.execute("DROP TRIGGER IF EXISTS audit_chain_insert")
        raw.execute(
            "INSERT INTO audit (id, at, actor_id, operation, target_id, outcome) "
            "VALUES (?,?,?,?,?,?)",
            ("forged-audit-row", now, "system", "delegation.invalidate", "grant-forged", "ok"),
        )
        raw.commit()
    finally:
        raw.close()

    result = service.verify_audit_chain(actor)
    assert result["ok"] is False


def test_audit_update_and_delete_rejected_on_normal_path(service: Service) -> None:
    target = _audit_ids(service)[0]
    with pytest.raises(sqlite3.DatabaseError):
        service.conn.execute("UPDATE audit SET outcome='denied' WHERE id=?", (target,))
    with pytest.raises(sqlite3.DatabaseError):
        service.conn.execute("DELETE FROM audit WHERE id=?", (target,))
    with pytest.raises(sqlite3.DatabaseError):
        service.conn.execute("UPDATE audit_chain SET row_hash='bad' WHERE audit_id=?", (target,))
    with pytest.raises(sqlite3.DatabaseError):
        service.conn.execute("DELETE FROM audit_chain WHERE audit_id=?", (target,))


def test_trigger_originated_audit_row_is_chained(service: Service) -> None:
    alice_client, bob_client = client_for(service), client_for(service)
    login(alice_client, "alice", "02")
    login(bob_client, "bob", "03")

    service.assign("alice", "project-a", "project_lead")
    alice = service.authenticate(alice_client.cookies.get("locus_session"))
    with service.db() as db:
        db.execute(
            "INSERT OR IGNORE INTO project_owners (project_id, user_id) VALUES (?,?)",
            ("project-a", alice.id),
        )
    bob = service.authenticate(bob_client.cookies.get("locus_session"))

    grant = alice_client.post(
        "/api/admin/delegations",
        headers=ORIGIN,
        json={
            "project_id": "project-a",
            "recipient_id": bob.id,
            "permissions": ["read", "retrieve"],
        },
    ).json()

    # Trigger-originated path: removing grantor membership invalidates delegation,
    # and the SQL trigger inserts delegation.invalidate into audit.
    service.assign("alice", "project-a", None)

    row = service.conn.execute(
        "SELECT id, actor_id, operation, target_id, outcome FROM audit "
        "WHERE operation='delegation.invalidate' AND target_id=? ORDER BY at DESC LIMIT 1",
        (grant["id"],),
    ).fetchone()
    assert row is not None
    assert row["actor_id"] == "system"

    chain = service.conn.execute(
        "SELECT audit_id FROM audit_chain WHERE audit_id=?", (row["id"],)
    ).fetchone()
    assert chain is not None

    actor = _admin(service)
    result = service.verify_audit_chain(actor)
    assert result["ok"] is True

    # Tampering with this trigger-originated row is also detected.
    path = _db_path(service)
    raw = _raw(path)
    try:
        _drop_append_only_triggers(raw)
        raw.execute("UPDATE audit SET outcome='denied' WHERE id=?", (row["id"],))
        raw.commit()
    finally:
        raw.close()
    tampered = service.verify_audit_chain(actor)
    assert tampered["ok"] is False
    assert tampered["first_bad_id"] == row["id"]


def test_audit_chain_migration_backfills_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    raw = sqlite3.connect(path)
    try:
        raw.execute(
            "CREATE TABLE audit (id TEXT PRIMARY KEY, at REAL NOT NULL, actor_id TEXT NOT NULL, "
            "operation TEXT NOT NULL, target_id TEXT NOT NULL, outcome TEXT NOT NULL)"
        )
        raw.executemany(
            "INSERT INTO audit VALUES (?,?,?,?,?,?)",
            [
                ("a1", 100.0, "system", "project.create", "p1", "ok"),
                ("a2", 200.0, "admin", "membership.assign", "p1:u1", "ok"),
                ("a3", 300.0, "admin", "membership.remove", "p1:u1", "ok"),
            ],
        )
        raw.commit()
    finally:
        raw.close()

    svc = Service(path)
    try:
        admin = Principal(id="admin-id", username="admin", system_admin=True, must_rotate=False)
        result = svc.verify_audit_chain(admin)
        assert result["ok"] is True
        assert result["checked"] == 3
        chain_count = svc.conn.execute("SELECT COUNT(*) AS c FROM audit_chain").fetchone()["c"]
        assert chain_count == 3
    finally:
        svc.close()

    reopened = Service(path)
    try:
        admin = Principal(id="admin-id", username="admin", system_admin=True, must_rotate=False)
        again = reopened.verify_audit_chain(admin)
        assert again["ok"] is True
        assert again["checked"] == 3
        assert reopened.conn.execute("SELECT COUNT(*) AS c FROM audit_chain").fetchone()["c"] == 3
    finally:
        reopened.close()


def test_audit_integrity_endpoint_requires_system_admin(service: Service) -> None:
    anon = client_for(service)
    assert anon.get("/api/admin/audit/integrity").status_code == 401

    user = client_for(service)
    login(user)
    assert user.get("/api/admin/audit/integrity").status_code == 403

    admin = client_for(service)
    login(admin, "admin", "01")
    response = admin.get("/api/admin/audit/integrity")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_audit_rows_still_have_only_original_six_keys(service: Service) -> None:
    admin = client_for(service)
    login(admin, "admin", "01")
    rows = admin.get("/api/admin/audit").json()
    assert rows
    assert all(
        set(row.keys()) == {"id", "at", "actor_id", "operation", "target_id", "outcome"}
        for row in rows
    )


def test_full_recompute_forgery_is_not_detected(service: Service) -> None:
    """Document a known limitation: a writer who can rewrite every chain row and
    the head can forge a consistent chain. This test pins the limitation so a
    future external-anchor change is noticed.
    """
    actor = _admin(service)
    path = _db_path(service)

    raw = _raw(path)
    try:
        _drop_append_only_triggers(raw)
        # Explicit bypass: attacker rewrites a row, then recomputes the whole
        # chain and head from genesis, producing a consistent but forged chain.
        target = raw.execute(
            "SELECT id FROM audit ORDER BY at ASC, id ASC LIMIT 1 OFFSET 1"
        ).fetchone()["id"]
        raw.execute("UPDATE audit SET outcome='denied' WHERE id=?", (target,))

        rows = raw.execute(
            "SELECT id, at, actor_id, operation, target_id, outcome "
            "FROM audit ORDER BY at ASC, id ASC"
        ).fetchall()
        prev_hash = AUDIT_CHAIN_GENESIS
        for seq, row in enumerate(rows, start=1):
            row_hash = _audit_hash_payload(
                prev_hash,
                row["id"],
                row["at"],
                row["actor_id"],
                row["operation"],
                row["target_id"],
                row["outcome"],
            )
            raw.execute(
                "UPDATE audit_chain SET seq=?, prev_hash=?, row_hash=? WHERE audit_id=?",
                (seq, prev_hash, row_hash, row["id"]),
            )
            prev_hash = row_hash
        raw.execute(
            "UPDATE audit_chain_head SET row_count=?, head_hash=? WHERE id=1",
            (len(rows), prev_hash),
        )
        raw.commit()
    finally:
        raw.close()

    # Limitation: no external anchor means this forged-but-consistent chain passes.
    result = service.verify_audit_chain(actor)
    assert result["ok"] is True


def test_unregistered_audit_sha256_function_causes_insert_failure(tmp_path: Path) -> None:
    # A connection without the registered UDF must fail closed on audit INSERT
    # rather than silently appending an unchained row.
    path = tmp_path / "raw.sqlite3"
    svc = Service(path)
    svc.close()

    raw = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="audit_sha256"):
            raw.execute(
                "INSERT INTO audit (id, at, actor_id, operation, target_id, outcome) "
                "VALUES (?,?,?,?,?,?)",
                ("x", 1.0, "system", "op", "t", "ok"),
            )
    finally:
        raw.close()
