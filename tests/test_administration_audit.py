"""Synthetic-only local administration audit and transaction regressions."""

import json
import sqlite3
import sys
from pathlib import Path

import pytest
from app import cli
from app.service import Service
from fastapi import HTTPException
from test_api import ORIGIN, client_for, login


def events(service):
    return [dict(row) for row in service.conn.execute("SELECT * FROM audit ORDER BY at,id")]


def test_project_membership_operations_record_ids_without_payloads(service):
    service.create_project("test-org", "new-project", "Nonlogged sensitive display name")
    service.assign("alice", "new-project", "researcher")
    service.assign("alice", "new-project", None)
    recent = events(service)[-3:]
    assert [item["operation"] for item in recent] == [
        "project.create",
        "membership.assign",
        "membership.remove",
    ]
    assert all(item["actor_id"] == "local-cli" and item["outcome"] == "ok" for item in recent)
    user_id = service.conn.execute("SELECT id FROM users WHERE username='alice'").fetchone()[0]
    assert recent[0]["target_id"] == "new-project"
    assert recent[1]["target_id"] == recent[2]["target_id"] == f"new-project:{user_id}"
    assert "Nonlogged sensitive display name" not in json.dumps(recent)
    assert "Temporary-password" not in json.dumps(recent)


@pytest.mark.parametrize("operation", ["project", "assign", "remove"])
def test_administrative_change_rolls_back_when_audit_cannot_be_recorded(
    service, monkeypatch, operation
):
    before = events(service)

    def broken(*args):
        raise sqlite3.OperationalError("synthetic audit unavailable")

    monkeypatch.setattr(service, "_audit", broken)
    with pytest.raises(sqlite3.OperationalError):
        if operation == "project":
            service.create_project("org", "rollback", "test")
        elif operation == "assign":
            service.assign("alice", "project-a", "viewer")
        else:
            service.assign("alice", "project-a", None)
    assert events(service) == before
    if operation == "project":
        assert (
            service.conn.execute("SELECT id FROM projects WHERE id='rollback'").fetchone() is None
        )
    else:
        assert (
            service.conn.execute(
                "SELECT role FROM memberships WHERE user_id="
                "(SELECT id FROM users WHERE username='alice') AND project_id='project-a'"
            ).fetchone()[0]
            == "researcher"
        )


def test_invalid_assignment_records_no_success_event(service):
    before = events(service)
    with pytest.raises(HTTPException):
        service.assign("alice", "project-a", "unknown-role")
    assert events(service) == before


def test_cli_unassign_revokes_existing_conversation_and_document_access(service, monkeypatch):
    alice = client_for(service)
    login(alice)
    doc = service.seed_synthetic("alice", "project-a")
    conv = alice.post(
        "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
    ).json()["id"]
    assert alice.get(f"/api/documents/{doc}/chunks").status_code == 200
    path = service.conn.execute("PRAGMA database_list").fetchone()[2]
    monkeypatch.setattr(cli, "Service", lambda unused: Service(Path(path)))
    monkeypatch.setattr(
        sys, "argv", ["app.cli", "unassign", "--username", "alice", "--project", "project-a"]
    )
    cli.main()
    assert alice.get(f"/api/documents/{doc}/chunks").status_code == 404
    assert alice.get(f"/api/conversations/{conv}").status_code == 404
    assert events(service)[-1]["operation"] == "membership.remove"


def test_delegation_and_authz_audit_records_metadata_without_payloads_or_credentials(
    service,
) -> None:
    owner_client, bob_client = client_for(service), client_for(service)
    login(owner_client, "alice", "02")
    service.assign("alice", "project-a", "project_lead")
    actor = service.authenticate(owner_client.cookies.get("locus_session"))
    with service.db() as db:
        db.execute(
            "INSERT INTO project_owners (project_id,user_id) VALUES (?,?)",
            ("project-a", actor.id),
        )

    login(bob_client, "bob", "03")
    bob = service.authenticate(bob_client.cookies.get("locus_session"))

    # Grant delegation
    grant = owner_client.post(
        "/api/admin/delegations",
        headers=ORIGIN,
        json={
            "project_id": "project-a",
            "recipient_id": bob.id,
            "permissions": ["read", "retrieve"],
        },
    ).json()

    # Bob self-cancels delegation
    cancelled = bob_client.delete(f"/api/admin/delegations/{grant['id']}/cancel", headers=ORIGIN)
    assert cancelled.status_code == 200

    # Owner sets membership denials
    service.set_membership_denials(actor, "project-a", "bob", ["retrieve"])

    # Query all audit events
    audit_events = events(service)
    assert len(audit_events) > 0
    raw_audit = json.dumps(audit_events, ensure_ascii=False)

    # IAM-015: Assert metadata only, no payloads or credentials leak into audit
    assert "Temporary-password" not in raw_audit
    assert bob_client.cookies.get("locus_session") not in raw_audit
    assert owner_client.cookies.get("locus_session") not in raw_audit
    assert "成膜条件" not in raw_audit

    for event in audit_events:
        assert set(event.keys()) == {"id", "at", "actor_id", "operation", "target_id", "outcome"}
        assert event["outcome"] in ("ok", "already_ended", "failed")
