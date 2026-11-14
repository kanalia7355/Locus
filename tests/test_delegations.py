"""Live, project-scoped delegation grant regressions."""

import json
import time

import pytest
from app.scanner import CLEAN, ScanResult
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
        def scan(self, content: str) -> ScanResult:
            return CLEAN

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


def test_delegated_recipient_cannot_redelegate_or_revoke_and_options_empty(service) -> None:
    owner_client, bob_client = client_for(service), client_for(service)
    _owner(service, owner_client)
    login(bob_client, "bob", "03")
    bob = service.authenticate(bob_client.cookies.get("locus_session"))
    eve_client = client_for(service)
    login(eve_client, "eve", "04")
    eve = service.authenticate(eve_client.cookies.get("locus_session"))

    # Alice grants delegations to Eve and Bob
    grant_eve = _grant(owner_client, eve.id, ("read",)).json()
    grant_bob = _grant(owner_client, bob.id, ("read", "retrieve")).json()

    # Recipient Bob (without manage_roles or ownership) sees empty delegation options
    options = bob_client.get("/api/admin/delegations/options", headers=ORIGIN)
    assert options.status_code == 200
    assert options.json() == {"projects": []}

    # Bob attempting redelegation to Eve must be denied with 403
    redelegate = bob_client.post(
        "/api/admin/delegations",
        headers=ORIGIN,
        json={
            "project_id": "project-a",
            "recipient_id": eve.id,
            "permissions": ["read"],
        },
    )
    assert redelegate.status_code == 403
    assert "委任する権限または管理権限がありません" in redelegate.text

    # Bob attempting to revoke another user's delegation must be rejected
    # (_end_delegation returns 404 for non-grantors to prevent grant ID enumeration)
    del_other = bob_client.delete(f"/api/admin/delegations/{grant_eve['id']}", headers=ORIGIN)
    assert del_other.status_code == 404

    # Bob attempting to revoke his own delegation via admin revoke endpoint
    # (instead of cancel) must be rejected with 404 (not grantor)
    del_self_admin = bob_client.delete(f"/api/admin/delegations/{grant_bob['id']}", headers=ORIGIN)
    assert del_self_admin.status_code == 404

    # Verify no revoke event was recorded and both delegations remain active
    with service.db() as db:
        eve_events = db.execute(
            "SELECT event_type FROM delegation_events WHERE grant_id=?", (grant_eve["id"],)
        ).fetchall()
        assert not any(row["event_type"] == "revoke" for row in eve_events)
        bob_events = db.execute(
            "SELECT event_type FROM delegation_events WHERE grant_id=?", (grant_bob["id"],)
        ).fetchall()
        assert not any(row["event_type"] == "revoke" for row in bob_events)

    # Verify audit contains no leakage of unauthorized grant creation
    admin_client = client_for(service)
    login(admin_client, "admin", "01")
    audit_records = admin_client.get("/api/admin/audit", headers=ORIGIN).json()
    # No delegation.grant event with actor_id == bob.id
    assert not any(
        a.get("actor_id") == bob.id and a.get("operation") == "delegation.grant"
        for a in audit_records
    )


def test_delegation_self_cancellation_and_explicit_deny_immediately_mask_citations_and_answers(
    service,
) -> None:
    admin_client, owner_client, bob_client = (
        client_for(service),
        client_for(service),
        client_for(service),
    )
    login(admin_client, "admin", "01")
    admin = service.authenticate(admin_client.cookies.get("locus_session"))
    owner = _owner(service, owner_client)
    login(bob_client, "bob", "03")
    bob = service.authenticate(bob_client.cookies.get("locus_session"))

    # Bob starts with an empty role with no read/retrieve permissions
    empty = service.create_role(admin, "project-a", "delegated-chatter-role", [])
    service.assign("bob", "project-a", empty["id"])
    doc = service.seed_synthetic("alice", "project-a", "shared")
    service.publish(owner, doc, [{"role": empty["id"], "operations": ["read", "retrieve"]}])

    # Owner grants Bob read + retrieve
    grant = _grant(owner_client, bob.id, ("read", "retrieve")).json()

    # Bob creates a conversation and posts a message that generates citations
    conv = bob_client.post(
        "/api/conversations", headers=ORIGIN, json={"project_id": "project-a"}
    ).json()["id"]
    sent = bob_client.post(
        f"/api/conversations/{conv}/messages",
        headers=ORIGIN,
        json={"text": "180", "scope": "all", "attachment_ids": []},
    )
    assert sent.status_code == 200, sent.text
    msg = sent.json()
    assert len(msg["citations"]) > 0

    # Attach generated answer representing synthetic model response
    with service.db() as db:
        db.execute(
            "INSERT INTO generated_answers VALUES (?,?,?)",
            (msg["id"], "成膜条件Aに関する派生回答テキスト", "fixture-model"),
        )

    # Ensure conversation and message with generated answer are visible before revocation
    conv_before = bob_client.get(f"/api/conversations/{conv}")
    assert conv_before.status_code == 200
    first_msg = conv_before.json()["messages"][0]
    assert len(first_msg["citations"]) > 0
    assert first_msg["answer"] == "成膜条件Aに関する派生回答テキスト"
    assert first_msg.get("answer_hidden") is not True

    # Case 1: Bob self-cancels delegation
    cancel_res = bob_client.delete(f"/api/admin/delegations/{grant['id']}/cancel", headers=ORIGIN)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["changed"] is True

    # Immediate access denial upon self-cancellation:
    # 1) Conversation history retrieval endpoint immediately returns 403
    conv_after_cancel = bob_client.get(f"/api/conversations/{conv}")
    assert conv_after_cancel.status_code == 403

    # 2) Document and chunk endpoints immediately return 404
    assert bob_client.get(f"/api/documents/{doc}").status_code == 404
    assert bob_client.get(f"/api/documents/{doc}/chunks").status_code == 404

    # 3) Service-level evaluation immediately masks citations and derived answer
    with service.db() as db:
        live_bob = service._authenticate(db, bob_client.cookies.get("locus_session"))
        msg_row = db.execute("SELECT * FROM messages WHERE id=?", (msg["id"],)).fetchone()
        citations = service._citations(db, live_bob, json.loads(msg_row["citation_ids"]), conv)
        assert citations == []
        generated = service._generated(db, live_bob, msg_row, conv)
        assert generated["answer"] is None
        assert generated["answer_hidden"] is True

    # Case 2: Explicit denial (denied_permissions: ["retrieve"]) overrides delegation
    # Grant new delegation to Bob
    grant2 = _grant(owner_client, bob.id, ("read", "retrieve")).json()
    assert grant2["id"] != grant["id"]

    # Re-verify conversation retrieval is restored with active grant
    conv_restored = bob_client.get(f"/api/conversations/{conv}")
    assert conv_restored.status_code == 200
    assert len(conv_restored.json()["messages"][0]["citations"]) > 0

    # Owner applies explicit denial for "retrieve" to Bob's project membership
    service.set_membership_denials(owner, "project-a", "bob", ["retrieve"])

    # Immediate access denial upon explicit deny:
    # 1) Conversation history retrieval immediately returns 403
    conv_after_deny = bob_client.get(f"/api/conversations/{conv}")
    assert conv_after_deny.status_code == 403

    # 2) Service-level citation retrieval is immediately masked
    with service.db() as db:
        live_bob = service._authenticate(db, bob_client.cookies.get("locus_session"))
        citations_denied = service._citations(
            db, live_bob, json.loads(msg_row["citation_ids"]), conv
        )
        assert citations_denied == []
        generated_denied = service._generated(db, live_bob, msg_row, conv)
        assert generated_denied["answer"] is None
        assert generated_denied["answer_hidden"] is True

    # Verify Audit trail (IAM-015):
    # Audit records for self-cancel and administrative denial must be metadata-only
    audit_data = admin_client.get("/api/admin/audit", headers=ORIGIN).json()
    audit_json = json.dumps(audit_data, ensure_ascii=False)

    # Document contents or prompt texts must not leak into audit
    assert "成膜条件Aは処理温度180°C" not in audit_json
    assert "Temporary-password" not in audit_json
    assert bob_client.cookies.get("locus_session") not in audit_json

    # Audit records contain only expected metadata fields
    for entry in audit_data:
        assert set(entry.keys()) <= {"id", "at", "actor_id", "operation", "target_id", "outcome"}
