"""Retention policy, admin-only expiry summary and manual deletion (DATA-015)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.scanner import CLEAN, ScanResult
from app.service import (
    DEFAULT_RETENTION_DAYS,
    MAX_RETENTION_DAYS,
    MIN_RETENTION_DAYS,
    SECONDS_PER_DAY,
    Service,
)
from fastapi import HTTPException
from test_api import ORIGIN, client_for, login


class AcceptingScanner:
    def scan(self, content: str) -> ScanResult:
        return CLEAN


def test_retention_default_clock_boundary_and_setting_validation(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin, alice = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(alice)
    alice_actor = service.authenticate(alice.cookies.get("locus_session"))
    admin_actor = service.authenticate(admin.cookies.get("locus_session"))

    assert DEFAULT_RETENTION_DAYS == 365
    assert service.retention_days == 365

    # Freshly created fixtures have 0 expired items under the 365-day default.
    initial = admin.get("/api/admin/retention")
    assert initial.status_code == 200, initial.text
    initial_body = initial.json()
    assert initial_body["retention_days"] == 365
    assert initial_body["counts"] == {"documents": 0, "conversations": 0, "audit": 0}
    assert initial_body["items"] == {"documents": [], "conversations": []}

    # Create controlled rows at a fixed base timestamp via DB / upload + conversation.
    base_now = 1_700_000_000.0
    service.scanner = AcceptingScanner()
    doc = service.upload(
        alice_actor,
        "project-a",
        "retention-sample.txt",
        "synthetic retention body",
        "personal",
    )
    assert service.process_next() is True
    conv = service.new_conversation(alice_actor, "project-a")
    service.send(alice_actor, conv["id"], "synthetic retention question", "all", [])

    with service.db() as db:
        db.execute("UPDATE documents SET created=?", (base_now,))
        db.execute("UPDATE conversations SET created=?", (base_now,))
        db.execute("UPDATE audit SET at=?", (base_now,))
        audit_total = db.execute("SELECT COUNT(*) FROM audit").fetchone()[0]

    # 364 days elapsed: strictly before expiry (created + 365d > now) -> 0 expired.
    monkeypatch.setattr(service, "_retention_now", lambda: base_now + 364 * SECONDS_PER_DAY)
    at_364 = admin.get("/api/admin/retention").json()
    assert at_364["counts"] == {"documents": 0, "conversations": 0, "audit": 0}
    assert at_364["items"] == {"documents": [], "conversations": []}

    # 365 days elapsed: exact boundary (created + 365d == now) -> expired (<= includes equality).
    monkeypatch.setattr(service, "_retention_now", lambda: base_now + 365 * SECONDS_PER_DAY)
    at_365 = admin.get("/api/admin/retention").json()
    assert at_365["counts"] == {"documents": 1, "conversations": 1, "audit": audit_total}
    assert [item["id"] for item in at_365["items"]["documents"]] == [doc["id"]]
    assert at_365["items"]["documents"][0] == {
        "id": doc["id"],
        "name": "retention-sample.txt",
        "created": base_now,
        "expires": base_now + 365 * SECONDS_PER_DAY,
    }
    assert [item["id"] for item in at_365["items"]["conversations"]] == [conv["id"]]
    assert at_365["items"]["conversations"][0] == {
        "id": conv["id"],
        "name": conv["id"],
        "created": base_now,
        "expires": base_now + 365 * SECONDS_PER_DAY,
    }

    # 366 days elapsed: past boundary -> expired.
    monkeypatch.setattr(service, "_retention_now", lambda: base_now + 366 * SECONDS_PER_DAY)
    at_366 = admin.get("/api/admin/retention").json()
    assert at_366["counts"] == {"documents": 1, "conversations": 1, "audit": audit_total}

    # Valid configuration update via API and service method.
    configured = admin.put(
        "/api/admin/retention",
        headers=ORIGIN,
        json={"retention_days": 400},
    )
    assert configured.status_code == 200, configured.text
    assert configured.json()["retention_days"] == 400
    assert service.retention_days == 400
    # At 366 days elapsed, a 400-day window means nothing is expired anymore.
    after_raise = admin.get("/api/admin/retention").json()
    assert after_raise["counts"] == {"documents": 0, "conversations": 0, "audit": 0}

    # Invalid values (0, negative, float, string, bool, above max) are rejected with 422
    # and leave the configured setting unchanged at 400.
    invalid_values: list[object] = [
        0,
        -1,
        -365,
        365.5,
        1.0,
        "365",
        "",
        True,
        False,
        None,
        MAX_RETENTION_DAYS + 1,
        MIN_RETENTION_DAYS - 1,
    ]
    for bad in invalid_values:
        resp = admin.put(
            "/api/admin/retention",
            headers=ORIGIN,
            json={"retention_days": bad},
        )
        assert resp.status_code == 422, f"expected 422 for {bad!r}, got {resp.status_code}"
        assert service.retention_days == 400

        with pytest.raises(HTTPException) as exc_info:
            service.set_retention_days(bad, actor=admin_actor)  # type: ignore[arg-type]
        assert exc_info.value.status_code == 422
        assert service.retention_days == 400

    # Non-admin cannot update retention configuration (even when value is also invalid -> 403).
    assert (
        alice.put(
            "/api/admin/retention",
            headers=ORIGIN,
            json={"retention_days": 180},
        ).status_code
        == 403
    )
    assert (
        alice.put(
            "/api/admin/retention",
            headers=ORIGIN,
            json={"retention_days": 0},
        ).status_code
        == 403
    )
    with pytest.raises(HTTPException) as non_admin_exc:
        service.set_retention_days(0, actor=alice_actor)
    assert non_admin_exc.value.status_code == 403
    assert service.retention_days == 400


def test_conversation_expiry_uses_conversation_created_not_subordinate_rows(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice, admin = client_for(service), client_for(service)
    login(alice)
    login(admin, "admin", "01")
    alice_actor = service.authenticate(alice.cookies.get("locus_session"))

    base_now = 1_700_000_000.0
    unexpired_conv = service.new_conversation(alice_actor, "project-a")["id"]
    service.send(alice_actor, unexpired_conv, "古いメッセージを持つ新しい会話", "all", [])

    expired_conv = service.new_conversation(alice_actor, "project-a")["id"]
    service.send(alice_actor, expired_conv, "新しいメッセージを持つ古い会話", "all", [])

    with service.db() as db:
        # unexpired_conv is 364d old, even though its message timestamp is 400d old.
        db.execute(
            "UPDATE conversations SET created=? WHERE id=?",
            (base_now + 1 * SECONDS_PER_DAY, unexpired_conv),
        )
        db.execute(
            "UPDATE messages SET created=? WHERE conversation_id=?",
            (base_now - 35 * SECONDS_PER_DAY, unexpired_conv),
        )
        # expired_conv is 365d old, even though its message timestamp is 1d old.
        db.execute(
            "UPDATE conversations SET created=? WHERE id=?",
            (base_now, expired_conv),
        )
        db.execute(
            "UPDATE messages SET created=? WHERE conversation_id=?",
            (base_now + 364 * SECONDS_PER_DAY, expired_conv),
        )

    monkeypatch.setattr(service, "_retention_now", lambda: base_now + 365 * SECONDS_PER_DAY)
    report = admin.get("/api/admin/retention").json()
    assert [item["id"] for item in report["items"]["conversations"]] == [expired_conv]
    assert report["counts"]["conversations"] == 1


def test_no_unattended_deletion_across_workers_recovery_and_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "unattended.sqlite3"
    svc = Service(db_path, scanner=AcceptingScanner())
    try:
        svc.provision("admin", "Temporary-password-01!", system_admin=True)
        svc.provision("alice", "Temporary-password-02!")
        svc.create_project("org-a", "project-a", "研究プロジェクト")
        svc.assign("alice", "project-a", "researcher")

        alice = client_for(svc)
        login(alice)
        token = alice.cookies.get("locus_session")
        assert token is not None
        actor = svc.authenticate(token)

        # Populate ready document, queued document, conversation, messages, queued chat job.
        ready_doc = svc.upload(actor, "project-a", "ready.txt", "成膜サンプル1", "personal")
        assert svc.process_next() is True
        _queued_doc = svc.upload(actor, "project-a", "queued.txt", "成膜サンプル2", "personal")

        conv1 = svc.new_conversation(actor, "project-a")["id"]
        svc.send(actor, conv1, "成膜の質問", "all", [])

        conv2 = svc.new_conversation(actor, "project-a")["id"]
        svc.enqueue_chat(
            actor,
            conv2,
            "成膜の待機質問",
            "all",
            [],
            token=token,
            generate=lambda _t, _c: ("合成回答", "fixture"),
            validate=None,
        )

        base_now = 1_600_000_000.0
        with svc.db() as db:
            db.execute("UPDATE documents SET created=?", (base_now,))
            db.execute("UPDATE conversations SET created=?", (base_now,))
            db.execute("UPDATE messages SET created=?", (base_now,))
            db.execute("UPDATE audit SET at=?", (base_now,))

            before_doc_ids = {row[0] for row in db.execute("SELECT id FROM documents").fetchall()}
            before_conv_ids = {
                row[0] for row in db.execute("SELECT id FROM conversations").fetchall()
            }
            before_msg_ids = {row[0] for row in db.execute("SELECT id FROM messages").fetchall()}
            before_audit_ids = {row[0] for row in db.execute("SELECT id FROM audit").fetchall()}
            before_docs = len(before_doc_ids)
            before_convs = len(before_conv_ids)
            before_msgs = len(before_msg_ids)
            before_audit = len(before_audit_ids)

        assert before_docs == 2
        assert before_convs == 2
        assert before_msgs == 1
        assert before_audit >= 4

        # Advance retention clock well past 1 year (e.g., 500 days).
        monkeypatch.setattr(svc, "_retention_now", lambda: base_now + 500 * SECONDS_PER_DAY)

        # Run background routines: process_next, process_next_chat, recover_jobs.
        # Processes _queued_doc without deleting expired ready_doc.
        assert svc.process_next() is True
        assert svc.process_next_chat() is True
        svc.recover_jobs()

        with svc.db() as db:
            mid_docs = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            mid_convs = db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            mid_msgs = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            mid_audit = db.execute("SELECT COUNT(*) FROM audit").fetchone()[0]

        assert mid_docs >= before_docs
        assert mid_convs >= before_convs
        assert mid_msgs >= before_msgs
        assert mid_audit >= before_audit
        assert ready_doc["id"] in {
            row[0] for row in svc.conn.execute("SELECT id FROM documents").fetchall()
        }
    finally:
        svc.close()

    # Reopen a fresh Service from the exact same SQLite file and run recover_jobs/workers again.
    reopened = Service(db_path, scanner=AcceptingScanner())
    try:
        monkeypatch.setattr(reopened, "_retention_now", lambda: base_now + 500 * SECONDS_PER_DAY)
        reopened.recover_jobs()
        reopened.process_next()
        reopened.process_next_chat()

        with reopened.db() as db:
            after_doc_ids = {row[0] for row in db.execute("SELECT id FROM documents").fetchall()}
            after_conv_ids = {
                row[0] for row in db.execute("SELECT id FROM conversations").fetchall()
            }
            after_msg_ids = {row[0] for row in db.execute("SELECT id FROM messages").fetchall()}
            after_audit_ids = {row[0] for row in db.execute("SELECT id FROM audit").fetchall()}
            after_docs = len(after_doc_ids)
            after_convs = len(after_conv_ids)
            after_msgs = len(after_msg_ids)
            after_audit = len(after_audit_ids)

        assert before_doc_ids <= after_doc_ids
        assert before_conv_ids <= after_conv_ids
        assert before_msg_ids <= after_msg_ids
        assert before_audit_ids <= after_audit_ids
        assert after_docs == mid_docs
        assert after_convs == mid_convs
        assert after_msgs == mid_msgs
        assert after_audit == mid_audit
    finally:
        reopened.close()


def test_admin_retention_access_control_and_no_content_disclosure(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    unauth, alice, admin = client_for(service), client_for(service), client_for(service)
    # Unauthenticated caller -> 401/403? Wait: let's check AC 3!
    login(alice)
    login(admin, "admin", "01")
    alice_actor = service.authenticate(alice.cookies.get("locus_session"))
    service.scanner = AcceptingScanner()

    doc_body = "成膜条件Aの本文・管理者へ非開示"
    att_body = "添付ノートBの本文・管理者へ非開示"
    msg_body = "対話質問Cの本文・管理者へ非開示"
    ans_body = "生成回答Dの本文・管理者へ非開示"

    conv = service.new_conversation(alice_actor, "project-a")["id"]
    doc = service.upload(alice_actor, "project-a", "visible-title.txt", doc_body, "personal")
    att = service.upload(
        alice_actor, "project-a", "attached-note.txt", att_body, "attachment", conv
    )
    assert service.process_next() is True
    assert service.process_next() is True
    service.send(
        alice_actor,
        conv,
        msg_body,
        "all",
        [att["id"]],
        generate=lambda _t, _c: (ans_body, "fixture-model"),
        token=alice.cookies.get("locus_session"),
    )

    base_now = 1_700_000_000.0
    with service.db() as db:
        db.execute("UPDATE documents SET created=?", (base_now,))
        db.execute("UPDATE conversations SET created=?", (base_now,))
        db.execute("UPDATE audit SET at=?", (base_now,))

    monkeypatch.setattr(service, "_retention_now", lambda: base_now + 366 * SECONDS_PER_DAY)

    # Non-system_admin (general user and unauthenticated) cannot read GET /api/admin/retention.
    assert alice.get("/api/admin/retention").status_code == 403
    assert unauth.get("/api/admin/retention").status_code == 403

    resp = admin.get("/api/admin/retention")
    assert resp.status_code == 200, resp.text
    raw = resp.text
    payload = resp.json()

    assert payload["counts"]["documents"] == 2
    assert payload["counts"]["conversations"] == 1
    assert {item["id"] for item in payload["items"]["documents"]} == {doc["id"], att["id"]}
    assert [item["id"] for item in payload["items"]["conversations"]] == [conv]

    for marker in (
        doc_body,
        att_body,
        msg_body,
        ans_body,
    ):
        assert marker not in raw
        assert marker not in json.dumps(payload, ensure_ascii=False)


def test_manual_retention_delete_cascades_audits_and_spares_other_expired_items(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice, admin = client_for(service), client_for(service)
    login(alice)
    login(admin, "admin", "01")
    alice_actor = service.authenticate(alice.cookies.get("locus_session"))
    admin_actor = service.authenticate(admin.cookies.get("locus_session"))
    service.scanner = AcceptingScanner()

    # Create two expired documents and two expired conversations (with messages, generated answers,
    # attachments, and finished chat_jobs).
    doc_delete = service.upload(
        alice_actor, "project-a", "delete-me.txt", "成膜条件サンプル削除対象", "personal"
    )["id"]
    doc_keep = service.upload(
        alice_actor, "project-a", "keep-me.txt", "成膜条件サンプル保持対象", "personal"
    )["id"]
    assert service.process_next() is True
    assert service.process_next() is True

    conv_delete = service.new_conversation(alice_actor, "project-a")["id"]
    att_in_conv = service.upload(
        alice_actor, "project-a", "conv-att.txt", "添付サンプル", "attachment", conv_delete
    )["id"]
    assert service.process_next() is True
    msg = service.send(
        alice_actor,
        conv_delete,
        "成膜条件",
        "all",
        [att_in_conv],
        generate=lambda _t, _c: ("生成回答サンプル", "fixture"),
        token=alice.cookies.get("locus_session"),
    )
    assert msg is not None
    with service.db() as db:
        db.execute(
            "INSERT INTO chat_jobs "
            "(id,conversation_id,user_id,text,scope,attachments,status,created,updated) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "finished-job-1",
                conv_delete,
                alice_actor.id,
                "完了済み質問",
                "all",
                "[]",
                "done",
                1_700_000_000.0,
                1_700_000_000.0,
            ),
        )

    conv_keep = service.new_conversation(alice_actor, "project-a")["id"]
    service.send(alice_actor, conv_keep, "残す会話の質問", "all", [])

    base_now = 1_700_000_000.0
    with service.db() as db:
        db.execute("UPDATE documents SET created=?", (base_now,))
        db.execute("UPDATE conversations SET created=?", (base_now,))

    monkeypatch.setattr(service, "_retention_now", lambda: base_now + 370 * SECONDS_PER_DAY)

    # Missing or empty targets must be rejected (no "delete all expired" default).
    assert admin.post("/api/admin/retention/delete", headers=ORIGIN, json={}).status_code == 422
    assert (
        admin.post(
            "/api/admin/retention/delete",
            headers=ORIGIN,
            json={"document_ids": [], "conversation_ids": []},
        ).status_code
        == 422
    )

    # Delete 1 expired document and 1 expired conversation explicitly.
    deleted = admin.post(
        "/api/admin/retention/delete",
        headers=ORIGIN,
        json={"document_ids": [doc_delete], "conversation_ids": [conv_delete]},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {
        "deleted": {
            "document_ids": [doc_delete],
            "conversation_ids": [conv_delete],
        }
    }

    with service.db() as db:
        # Deleted document + its chunks are gone.
        assert db.execute("SELECT 1 FROM documents WHERE id=?", (doc_delete,)).fetchone() is None
        assert (
            db.execute("SELECT COUNT(*) FROM chunks WHERE document_id=?", (doc_delete,)).fetchone()[
                0
            ]
            == 0
        )
        # Deleted conversation + messages + generated_answers + chat_jobs + attachment are gone.
        assert (
            db.execute("SELECT 1 FROM conversations WHERE id=?", (conv_delete,)).fetchone() is None
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conv_delete,)
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM generated_answers WHERE message_id=?", (msg["id"],)
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM chat_jobs WHERE conversation_id=?", (conv_delete,)
            ).fetchone()[0]
            == 0
        )
        assert db.execute("SELECT 1 FROM documents WHERE id=?", (att_in_conv,)).fetchone() is None

        # Other expired items remain untouched!
        assert db.execute("SELECT 1 FROM documents WHERE id=?", (doc_keep,)).fetchone() is not None
        assert (
            db.execute("SELECT COUNT(*) FROM chunks WHERE document_id=?", (doc_keep,)).fetchone()[0]
            > 0
        )
        assert (
            db.execute("SELECT 1 FROM conversations WHERE id=?", (conv_keep,)).fetchone()
            is not None
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conv_keep,)
            ).fetchone()[0]
            == 1
        )

        # Audit records retention.delete per deleted target, attributed to admin.
        audit_rows = db.execute(
            "SELECT actor_id, operation, target_id, outcome FROM audit "
            "WHERE operation='retention.delete' ORDER BY rowid"
        ).fetchall()
        assert [(r["actor_id"], r["target_id"], r["outcome"]) for r in audit_rows] == [
            (admin_actor.id, doc_delete, "ok"),
            (admin_actor.id, conv_delete, "ok"),
        ]


def test_unexpired_audit_non_admin_and_in_flight_retention_delete_guards(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    unauth, alice, admin = client_for(service), client_for(service), client_for(service)
    login(alice)
    login(admin, "admin", "01")
    alice_actor = service.authenticate(alice.cookies.get("locus_session"))
    service.scanner = AcceptingScanner()

    base_now = 1_700_000_000.0
    expired_doc = service.upload(
        alice_actor, "project-a", "expired.txt", "expired content", "personal"
    )["id"]
    fresh_doc = service.upload(alice_actor, "project-a", "fresh.txt", "fresh content", "personal")[
        "id"
    ]
    assert service.process_next() is True
    assert service.process_next() is True

    in_flight_doc = service.upload(
        alice_actor, "project-a", "inflight.txt", "queued content", "personal"
    )["id"]

    expired_conv = service.new_conversation(alice_actor, "project-a")["id"]
    fresh_conv = service.new_conversation(alice_actor, "project-a")["id"]
    busy_conv = service.new_conversation(alice_actor, "project-a")["id"]
    att_inflight_conv = service.new_conversation(alice_actor, "project-a")["id"]
    att_inflight_doc = service.upload(
        alice_actor,
        "project-a",
        "att-inflight.txt",
        "queued attachment content",
        "attachment",
        att_inflight_conv,
    )["id"]
    token = alice.cookies.get("locus_session")
    assert token is not None
    service.enqueue_chat(
        alice_actor,
        busy_conv,
        "queued question",
        "all",
        [],
        token=token,
        generate=lambda _t, _c: ("answer", "fixture"),
        validate=None,
    )

    with service.db() as db:
        db.execute(
            "UPDATE documents SET created=? WHERE id IN (?,?,?)",
            (base_now, expired_doc, in_flight_doc, att_inflight_doc),
        )
        db.execute(
            "UPDATE documents SET created=? WHERE id=?",
            (base_now + 100 * SECONDS_PER_DAY, fresh_doc),
        )
        db.execute(
            "UPDATE conversations SET created=? WHERE id IN (?,?,?)",
            (base_now, expired_conv, busy_conv, att_inflight_conv),
        )
        db.execute(
            "UPDATE conversations SET created=? WHERE id=?",
            (base_now + 100 * SECONDS_PER_DAY, fresh_conv),
        )
        db.execute("UPDATE audit SET at=?", (base_now,))
        sample_audit_id = db.execute("SELECT id FROM audit LIMIT 1").fetchone()[0]

    monkeypatch.setattr(service, "_retention_now", lambda: base_now + 366 * SECONDS_PER_DAY)

    # AC 6: Non-admin (and unauthenticated) calling POST /api/admin/retention/delete -> 403.
    assert (
        alice.post(
            "/api/admin/retention/delete",
            headers=ORIGIN,
            json={"document_ids": [expired_doc]},
        ).status_code
        == 403
    )
    assert (
        unauth.post(
            "/api/admin/retention/delete",
            headers=ORIGIN,
            json={"document_ids": [expired_doc]},
        ).status_code
        == 403
    )
    assert service.conn.execute("SELECT 1 FROM documents WHERE id=?", (expired_doc,)).fetchone()

    # AC 5a: Unexpired targets rejected with 422, and nothing is deleted even in mixed batches.
    resp_unexpired_doc = admin.post(
        "/api/admin/retention/delete",
        headers=ORIGIN,
        json={"document_ids": [expired_doc, fresh_doc]},
    )
    assert resp_unexpired_doc.status_code == 422
    assert service.conn.execute("SELECT 1 FROM documents WHERE id=?", (expired_doc,)).fetchone()
    assert service.conn.execute("SELECT 1 FROM documents WHERE id=?", (fresh_doc,)).fetchone()

    resp_unexpired_conv = admin.post(
        "/api/admin/retention/delete",
        headers=ORIGIN,
        json={"conversation_ids": [fresh_conv]},
    )
    assert resp_unexpired_conv.status_code == 422
    assert service.conn.execute("SELECT 1 FROM conversations WHERE id=?", (fresh_conv,)).fetchone()

    # AC 5b: Audit rows cannot be targeted in POST /api/admin/retention/delete -> 422.
    audit_count_before = service.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    for audit_payload in (
        {"audit_ids": [sample_audit_id]},
        {"document_ids": [sample_audit_id]},
        {"conversation_ids": [sample_audit_id]},
    ):
        resp_audit = admin.post(
            "/api/admin/retention/delete",
            headers=ORIGIN,
            json=audit_payload,
        )
        assert resp_audit.status_code == 422
    assert service.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == audit_count_before

    # Detail 7: In-flight ingestion or active chat generation rejected with 409, rows remain.
    resp_inflight_doc = admin.post(
        "/api/admin/retention/delete",
        headers=ORIGIN,
        json={"document_ids": [in_flight_doc]},
    )
    assert resp_inflight_doc.status_code == 409
    assert service.conn.execute("SELECT 1 FROM documents WHERE id=?", (in_flight_doc,)).fetchone()

    resp_busy_conv = admin.post(
        "/api/admin/retention/delete",
        headers=ORIGIN,
        json={"conversation_ids": [busy_conv]},
    )
    assert resp_busy_conv.status_code == 409
    assert service.conn.execute("SELECT 1 FROM conversations WHERE id=?", (busy_conv,)).fetchone()

    resp_att_inflight_conv = admin.post(
        "/api/admin/retention/delete",
        headers=ORIGIN,
        json={"conversation_ids": [att_inflight_conv]},
    )
    assert resp_att_inflight_conv.status_code == 409
    assert service.conn.execute(
        "SELECT 1 FROM conversations WHERE id=?", (att_inflight_conv,)
    ).fetchone()

    # Once in-flight work completes, deletion succeeds cleanly (including at exact 365d boundary).
    assert service.process_next() is True
    assert service.process_next() is True
    assert service.process_next_chat() is True

    # At 364d elapsed, deletion of base_now items is still rejected with 422.
    monkeypatch.setattr(service, "_retention_now", lambda: base_now + 364 * SECONDS_PER_DAY)
    assert (
        admin.post(
            "/api/admin/retention/delete",
            headers=ORIGIN,
            json={"document_ids": [in_flight_doc]},
        ).status_code
        == 422
    )

    # Invalid clock values fail closed with 503 without deleting anything.
    monkeypatch.setattr(service, "_retention_now", lambda: float("nan"))
    assert admin.get("/api/admin/retention").status_code == 503
    assert (
        admin.post(
            "/api/admin/retention/delete",
            headers=ORIGIN,
            json={"document_ids": [in_flight_doc]},
        ).status_code
        == 503
    )

    # At exact 365d elapsed (inclusive boundary), deletion succeeds.
    monkeypatch.setattr(service, "_retention_now", lambda: base_now + 365 * SECONDS_PER_DAY)
    after_complete = admin.post(
        "/api/admin/retention/delete",
        headers=ORIGIN,
        json={
            "document_ids": [in_flight_doc],
            "conversation_ids": [busy_conv, att_inflight_conv],
        },
    )
    assert after_complete.status_code == 200, after_complete.text
    assert (
        service.conn.execute("SELECT 1 FROM documents WHERE id=?", (in_flight_doc,)).fetchone()
        is None
    )
    assert (
        service.conn.execute("SELECT 1 FROM conversations WHERE id=?", (busy_conv,)).fetchone()
        is None
    )
    assert (
        service.conn.execute(
            "SELECT 1 FROM conversations WHERE id=?", (att_inflight_conv,)
        ).fetchone()
        is None
    )
    assert (
        service.conn.execute("SELECT 1 FROM documents WHERE id=?", (att_inflight_doc,)).fetchone()
        is None
    )


def test_admin_retention_delete_of_ready_attachment_in_busy_conversation_returns_409(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC: Deleting a ready attachment in a busy conversation returns 409.

    The guard at service.py:4502-4503 (`if row["conversation_id"]`:
    _retention_inflight_refusal`) refuses deletion while a conversation has
    queued/running chat work, even when the attachment is ready and expired.
    """
    alice, admin = client_for(service), client_for(service)
    login(alice)
    login(admin, "admin", "01")
    alice_actor = service.authenticate(alice.cookies.get("locus_session"))
    service.authenticate(admin.cookies.get("locus_session"))
    service.scanner = AcceptingScanner()

    base_now = 1_700_000_000.0

    # 1. Create a conversation
    conv = service.new_conversation(alice_actor, "project-a")["id"]

    # 2. Enqueue a chat job to make the conversation "busy" (queued status).
    # This is the same pattern used by existing tests (e.g. test_unexpired_audit...).
    service.enqueue_chat(
        alice_actor,
        conv,
        "queued question",
        "all",
        [],
        token=alice.cookies.get("locus_session"),
        generate=lambda _t, _c: ("answer", "fixture"),
        validate=None,
    )

    # 3. Upload a ready attachment to that conversation.
    # The upload inserts with status='queued' and created=time.time().
    # Process to set status to 'ready', then UPDATE created to base_now so the
    # retention expiry check (created + window <= now) works with the monkeypatched clock.
    att = service.upload(
        alice_actor, "project-a", "attached-note.txt", "添付ノートBの本文", "attachment", conv
    )
    assert service.process_next() is True
    with service.db() as db:
        db.execute("UPDATE documents SET created=? WHERE id=?", (base_now, att["id"]))

    # 4. Set retention clock past expiry (beyond the 365-day default window).
    monkeypatch.setattr(service, "_retention_now", lambda: base_now + 366 * SECONDS_PER_DAY)

    # 5. Attempt deletion of just the attachment -> should be 409 refused.
    resp = admin.post(
        "/api/admin/retention/delete",
        headers=ORIGIN,
        json={"document_ids": [att["id"]]},
    )
    assert resp.status_code == 409, f"expected 409, got {resp.status_code}: {resp.text}"

    # 6. Verify the attachment and conversation rows still exist (by identifier,
    #      not by count — the 409 must have prevented the delete).
    with service.db() as db:
        assert db.execute("SELECT 1 FROM documents WHERE id=?", (att["id"],)).fetchone() is not None
        assert db.execute("SELECT 1 FROM conversations WHERE id=?", (conv,)).fetchone() is not None
