"""Live, project-scoped delegation grant regressions."""

import json
import time

import pytest
from fastapi import HTTPException
from test_api import ORIGIN, client_for, login


def _owner(service, client):
    login(client, "alice", "02")
    service.assign("alice", "project-a", "project_lead")
    actor = service.authenticate(client.cookies.get("locus_session"))
    with service.db() as db:
        db.execute(
            "INSERT INTO project_owners (project_id,user_id) VALUES (?,?)",
            ("project-a", actor.id),
        )
    return actor


def _empty_role(service, name):
    admin_client = client_for(service)
    login(admin_client, "admin", "01")
    admin = service.authenticate(admin_client.cookies.get("locus_session"))
    return service.create_role(admin, "project-a", name, [])


def _grant(client, recipient_id, permissions=("read",), **extra):
    return client.post(
        "/api/admin/delegations",
        headers=ORIGIN,
        json={
            "project_id": "project-a",
            "recipient_id": recipient_id,
            "permissions": list(permissions),
            **extra,
        },
    )


def test_delegation_ui_options_are_project_scoped_and_list_uses_display_names(service) -> None:
    owner_client, recipient_client = client_for(service), client_for(service)
    owner = _owner(service, owner_client)
    login(recipient_client, "bob", "03")
    recipient = service.authenticate(recipient_client.cookies.get("locus_session"))

    options = owner_client.get("/api/admin/delegations/options", headers=ORIGIN)
    assert options.status_code == 200, options.text
    assert options.json()["projects"] == [
        {
            "id": "project-a",
            "name": "研究プロジェクト",
            "recipients": [{"id": recipient.id, "username": "bob"}],
            "permission_ceiling": ["publish", "read", "retrieve", "upload"],
        }
    ]
    assert "project-b" not in json.dumps(options.json())

    grant = _grant(owner_client, recipient.id, ("read",))
    assert grant.status_code == 201
    listed = owner_client.get("/api/admin/delegations", headers=ORIGIN)
    assert listed.status_code == 200
    assert listed.json()[0]["recipient_username"] == "bob"
    assert listed.json()[0]["grantor_username"] == "alice"
    assert recipient_client.get("/api/admin/delegations/options", headers=ORIGIN).json() == {
        "projects": []
    }
    received = recipient_client.get("/api/admin/delegations", headers=ORIGIN)
    assert received.status_code == 200
    assert received.json()[0]["grantor_username"] == "alice"
    assert received.json()[0]["recipient_id"] == recipient.id
    assert owner.id != recipient.id


def test_owner_grants_live_subset_and_expiry_denies(service, monkeypatch) -> None:
    owner_client, recipient_client = client_for(service), client_for(service)
    _owner(service, owner_client)
    login(recipient_client, "bob", "03")
    recipient = service.authenticate(recipient_client.cookies.get("locus_session"))
    empty = _empty_role(service, "delegation-empty")
    service.assign("bob", "project-a", empty["id"])
    grant = _grant(owner_client, recipient.id, ("read",))
    assert grant.status_code == 201, grant.text
    result = grant.json()
    assert result["version"] == 1
    assert result["deduplicated"] is False
    with service.db() as db:
        assert "read" in service._permissions(db, recipient, "project-a")
        assert "retrieve" not in service._permissions(db, recipient, "project-a")
        expiry = result["expires"]
        with pytest.raises(Exception, match="immutable"):
            db.execute("UPDATE delegation_grants SET expires=expires+1 WHERE id=?", (result["id"],))
    service._delegation_now = lambda: expiry
    service.assign("bob", "project-a", empty["id"])
    with service.db() as db:
        assert "read" not in service._permissions(db, recipient, "project-a")
        event = db.execute(
            "SELECT event_type FROM delegation_events WHERE grant_id=?", (result["id"],)
        ).fetchone()
        assert event["event_type"] == "expire"


def test_expiry_blocks_document_chat_retrieval_history_and_attachments(
    service, monkeypatch
) -> None:
    owner_client, recipient_client = client_for(service), client_for(service)
    owner = _owner(service, owner_client)
    login(recipient_client, "bob", "03")
    recipient = service.authenticate(recipient_client.cookies.get("locus_session"))
    empty = _empty_role(service, "delegated-document-reader")
    service.assign("bob", "project-a", empty["id"])
    document = service.seed_synthetic("alice", "project-a", "shared")
    service.publish(owner, document, [{"role": empty["id"], "operations": ["read", "retrieve"]}])
    grant = _grant(owner_client, recipient.id, ("read", "retrieve", "upload"))
    assert grant.status_code == 201
    conversation = recipient_client.post(
        "/api/conversations", headers=ORIGIN, json={"project_id": "project-a"}
    ).json()["id"]
    sent = recipient_client.post(
        f"/api/conversations/{conversation}/messages",
        headers=ORIGIN,
        json={"text": "180", "scope": "all", "attachment_ids": []},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["citations"]
    attachment = service.upload(
        recipient, "project-a", "attachment.txt", "attached sample", "attachment", conversation
    )["id"]

    class ApprovedScanner:
        def scan(self, content: str) -> bool:
            return True

    service.scanner = ApprovedScanner()
    service.process_next()
    assert (
        recipient_client.get(
            f"/api/documents/{attachment}/chunks?conversation_id={conversation}"
        ).status_code
        == 200
    )
    expiry = grant.json()["expires"]
    monkeypatch.setattr(service, "_delegation_now", lambda: expiry)
    assert recipient_client.get(f"/api/documents/{document}").status_code == 404
    assert recipient_client.get(f"/api/documents/{document}/chunks").status_code == 404
    assert recipient_client.get(f"/api/documents/{document}/related").status_code == 404
    assert (
        recipient_client.get(
            f"/api/documents/{attachment}/chunks?conversation_id={conversation}"
        ).status_code
        == 404
    )
    with service.db() as db:
        live_actor = service._authenticate(db, recipient_client.cookies.get("locus_session"))
        assert not service._can_read(
            db,
            live_actor,
            db.execute("SELECT * FROM documents WHERE id=?", (document,)).fetchone(),
            "retrieve",
        )
    history = recipient_client.get(f"/api/conversations/{conversation}")
    assert history.status_code == 403
    with service.db() as db:
        assert "read" not in service._permissions(db, recipient, "project-a")


def test_owner_and_project_org_admin_grants_are_authorized(service) -> None:
    owner_client, recipient_client = client_for(service), client_for(service)
    _owner(service, owner_client)
    login(recipient_client, "bob", "03")
    recipient = service.authenticate(recipient_client.cookies.get("locus_session"))
    service.assign("bob", "project-a", "organization_admin")
    owner_id = service.authenticate(owner_client.cookies.get("locus_session")).id
    issued = _grant(recipient_client, owner_id, ("read",))
    assert issued.status_code == 201, issued.text
    service.assign("bob", "project-a", "researcher")
    service.assign("bob", "project-a", "viewer")
    with service.db() as db:
        event = db.execute(
            "SELECT event_type FROM delegation_events WHERE grant_id=?", (issued.json()["id"],)
        ).fetchone()
        assert event["event_type"] == "invalidate"
    assert _grant(owner_client, recipient.id, ("manage_roles",)).status_code == 422


def test_self_escalation_subset_family_scope_and_no_revival(service, monkeypatch) -> None:
    owner_client, recipient_client = client_for(service), client_for(service)
    owner = _owner(service, owner_client)
    login(recipient_client, "bob", "03")
    recipient = service.authenticate(recipient_client.cookies.get("locus_session"))
    assert _grant(owner_client, owner.id, ("read",)).status_code == 403
    service.assign("alice", "project-a", "researcher")
    assert _grant(owner_client, recipient.id, ("upload", "publish")).status_code == 403
    service.assign("alice", "project-a", "project_lead")
    first = _grant(owner_client, recipient.id, ("read",), ttl_seconds=3600)
    assert first.status_code == 201, first.text
    duplicate = _grant(owner_client, recipient.id, ("read",), ttl_seconds=3600)
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == first.json()["id"]
    assert duplicate.json()["deduplicated"] is True
    revoked = owner_client.delete(f"/api/admin/delegations/{first.json()['id']}", headers=ORIGIN)
    assert revoked.status_code == 200 and revoked.json()["changed"] is True
    again = owner_client.delete(f"/api/admin/delegations/{first.json()['id']}", headers=ORIGIN)
    assert again.status_code == 200 and again.json()["changed"] is False
    renewed = _grant(owner_client, recipient.id, ("read",), ttl_seconds=3600)
    assert renewed.status_code == 201 and renewed.json()["version"] == 2
    assert renewed.json()["id"] != first.json()["id"]
    monkeypatch.setattr(service, "_delegation_now", lambda: renewed.json()["expires"])
    widened = _grant(owner_client, recipient.id, ("read", "retrieve"), ttl_seconds=3600)
    assert widened.status_code == 201
    assert widened.json()["family_id"] != first.json()["family_id"]
    with service.db() as db:
        versions = db.execute(
            "SELECT version FROM delegation_grants WHERE family_id=? ORDER BY version",
            (first.json()["family_id"],),
        ).fetchall()
        assert [row["version"] for row in versions] == [1, 2]
        old_events = db.execute(
            "SELECT event_type FROM delegation_events WHERE grant_id=?", (first.json()["id"],)
        ).fetchall()
        assert {row["event_type"] for row in old_events} == {"revoke"}


def test_recipient_cancel_and_membership_remains_independent(service) -> None:
    owner_client, recipient_client = client_for(service), client_for(service)
    _owner(service, owner_client)
    login(recipient_client, "bob", "03")
    recipient = service.authenticate(recipient_client.cookies.get("locus_session"))
    empty = _empty_role(service, "membership-empty")
    service.assign("bob", "project-a", empty["id"])
    grant = _grant(owner_client, recipient.id, ("read",))
    assert grant.status_code == 201
    service.assign("bob", "project-a", None)
    with service.db() as db:
        with pytest.raises(HTTPException):
            service.require(db, recipient, "project-a", "read")
    service.assign("bob", "project-a", empty["id"])
    with service.db() as db:
        service.require(db, recipient, "project-a", "read")
    cancelled = recipient_client.delete(
        f"/api/admin/delegations/{grant.json()['id']}/cancel", headers=ORIGIN
    )
    assert cancelled.status_code == 200 and cancelled.json()["changed"] is True
    again = recipient_client.delete(
        f"/api/admin/delegations/{grant.json()['id']}/cancel", headers=ORIGIN
    )
    assert again.status_code == 200 and again.json()["changed"] is False
    with service.db() as db:
        with pytest.raises(HTTPException):
            service.require(db, recipient, "project-a", "read")


def test_grantor_authority_loss_invalidates_and_deny_wins(service) -> None:
    owner_client, recipient_client = client_for(service), client_for(service)
    _owner(service, owner_client)
    login(recipient_client, "bob", "03")
    recipient = service.authenticate(recipient_client.cookies.get("locus_session"))
    empty = _empty_role(service, "authority-empty")
    service.assign("bob", "project-a", empty["id"])
    grant = _grant(owner_client, recipient.id, ("read",))
    assert grant.status_code == 201
    service.assign("alice", "project-a", None)
    service.assign("bob", "project-a", empty["id"])
    with service.db() as db:
        assert "read" not in service._permissions(db, recipient, "project-a")
        event = db.execute(
            "SELECT event_type FROM delegation_events WHERE grant_id=?", (grant.json()["id"],)
        ).fetchone()
        assert event["event_type"] == "invalidate"


def test_revoked_grant_is_absent_during_inflight_chat_recheck(service, monkeypatch) -> None:
    owner_client, recipient_client = client_for(service), client_for(service)
    owner = _owner(service, owner_client)
    login(recipient_client, "bob", "03")
    recipient = service.authenticate(recipient_client.cookies.get("locus_session"))
    empty = _empty_role(service, "inflight-empty")
    service.assign("bob", "project-a", empty["id"])
    grant = _grant(owner_client, recipient.id, ("read", "retrieve"))
    assert grant.status_code == 201
    conversation = service.new_conversation(recipient, "project-a")["id"]
    document = service.seed_synthetic("alice", "project-a", "shared")
    service.publish(owner, document, [{"role": empty["id"], "operations": ["read", "retrieve"]}])

    def revoke_during_generation(text, citations):
        with service.db() as db:
            grant_row = db.execute(
                "SELECT grantor_id FROM delegation_families WHERE id=?",
                (grant.json()["family_id"],),
            ).fetchone()
            db.execute(
                "INSERT INTO delegation_events "
                "(id,grant_id,event_type,actor_id,at) VALUES (?,?,?,?,?)",
                (
                    "inflight-revocation",
                    grant.json()["id"],
                    "revoke",
                    grant_row["grantor_id"],
                    time.time(),
                ),
            )
        return "answer must not be committed", "test-model"

    with pytest.raises(HTTPException):
        service.send(
            recipient,
            conversation,
            "180",
            "all",
            [],
            generate=revoke_during_generation,
            token=recipient_client.cookies.get("locus_session"),
        )
    with service.db() as db:
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


def test_explicit_deny_overrides_delegation_and_role_union(service) -> None:
    owner_client, recipient_client = client_for(service), client_for(service)
    owner = _owner(service, owner_client)
    login(recipient_client, "bob", "03")
    recipient = service.authenticate(recipient_client.cookies.get("locus_session"))
    grant = _grant(owner_client, recipient.id, ("upload",))
    assert grant.status_code == 201
    with service.db() as db:
        assert "upload" in service._permissions(db, recipient, "project-a")
    service.set_membership_denials(owner, "project-a", "bob", ["upload"])
    with service.db() as db:
        assert "upload" not in service._permissions(db, recipient, "project-a")
        with pytest.raises(HTTPException):
            service.require(db, recipient, "project-a", "upload")


def test_ttl_bounds_api_and_audit_is_metadata_only(service) -> None:
    owner_client, recipient_client = client_for(service), client_for(service)
    _owner(service, owner_client)
    login(recipient_client, "bob", "03")
    recipient = service.authenticate(recipient_client.cookies.get("locus_session"))
    for ttl in (899, 604801):
        assert _grant(owner_client, recipient.id, ("read",), ttl_seconds=ttl).status_code == 422
    created = _grant(owner_client, recipient.id, ("read",))
    assert created.status_code == 201
    assert created.json()["expires"] - time.time() == pytest.approx(86400, abs=1)
    with service.db() as db:
        audit = db.execute(
            "SELECT actor_id,operation,target_id,outcome FROM audit "
            "WHERE operation='delegation.grant' AND target_id=?",
            (created.json()["id"],),
        ).fetchone()
        assert audit["actor_id"] != recipient.id
        assert audit["operation"] == "delegation.grant"
        assert audit["target_id"] == created.json()["id"]
        assert "read" not in json.dumps(dict(audit))
        with pytest.raises(Exception, match="retained"):
            db.execute("DELETE FROM delegation_grants WHERE id=?", (created.json()["id"],))


def test_non_authorized_org_role_and_project_scope_denied(service) -> None:
    bob = client_for(service)
    login(bob, "bob", "03")
    recipient = service.provision("other-recipient", "Temporary-password-05!")
    assert _grant(bob, recipient, ("read",)).status_code == 403
    assert (
        bob.post(
            "/api/admin/delegations",
            headers=ORIGIN,
            json={
                "project_id": "missing-project",
                "recipient_id": recipient,
                "permissions": ["read"],
            },
        ).status_code
        == 404
    )
