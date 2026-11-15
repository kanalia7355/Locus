"""Admin load display states the configured wait deadline and the observed oldest wait.

Both values are a configuration entry and an observation, not a capacity promise
(``UI-006``): the display must not invent how many users the service supports.
"""

import time

from app.service import (
    CHAT_QUEUE_LIMIT,
    CHAT_USER_QUEUE_LIMIT,
    CHAT_WAIT_SECONDS,
    Service,
)
from test_api import ORIGIN, client_for, login


def test_load_reports_the_configured_wait_deadline_and_limits(service: Service):
    admin = client_for(service)
    login(admin, "admin", "01")
    queue = admin.get("/api/admin/load", headers=ORIGIN).json()["chat_queue"]
    assert queue["wait_deadline_seconds"] == CHAT_WAIT_SECONDS
    assert queue["limit"] == CHAT_QUEUE_LIMIT
    assert queue["per_user_limit"] == CHAT_USER_QUEUE_LIMIT


def test_oldest_queued_wait_seconds_is_zero_without_waiting_jobs(service: Service):
    admin = client_for(service)
    login(admin, "admin", "01")
    queue = admin.get("/api/admin/load", headers=ORIGIN).json()["chat_queue"]
    assert queue["oldest_queued_wait_seconds"] == 0


def test_oldest_queued_wait_seconds_tracks_the_oldest_waiting_question(service: Service):
    admin, alice = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(alice)
    principal = service.authenticate(alice.cookies.get("locus_session"))
    conversation = service.new_conversation(principal, "project-a")["id"]
    now = time.time()
    with service.db() as db:
        db.execute(
            "INSERT INTO chat_jobs "
            "(id,conversation_id,user_id,text,scope,attachments,status,created,updated) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "queued-ten-seconds-ago",
                conversation,
                principal.id,
                "waiting question",
                "all",
                "[]",
                "queued",
                now - 10,
                now,
            ),
        )
    first = admin.get("/api/admin/load", headers=ORIGIN).json()["chat_queue"][
        "oldest_queued_wait_seconds"
    ]
    assert 9.5 <= first < 15
    time.sleep(0.25)
    second = admin.get("/api/admin/load", headers=ORIGIN).json()["chat_queue"][
        "oldest_queued_wait_seconds"
    ]
    assert second > first
    with service.db() as db:
        bob_id = db.execute("SELECT id FROM users WHERE username='bob'").fetchone()[0]
        db.execute(
            "INSERT INTO chat_jobs "
            "(id,conversation_id,user_id,text,scope,attachments,status,created,updated) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "queued-forty-seconds-ago",
                conversation,
                bob_id,
                "older question",
                "all",
                "[]",
                "queued",
                now - 40,
                now,
            ),
        )
    third = admin.get("/api/admin/load", headers=ORIGIN).json()["chat_queue"][
        "oldest_queued_wait_seconds"
    ]
    assert third >= 39.5 and third > second


def test_load_display_adds_no_identities_or_question_text(service: Service):
    admin, alice = client_for(service), client_for(service)
    login(admin, "admin", "01")
    login(alice)
    principal = service.authenticate(alice.cookies.get("locus_session"))
    conversation = service.new_conversation(principal, "project-a")["id"]
    now = time.time()
    with service.db() as db:
        bob_id = db.execute("SELECT id FROM users WHERE username='bob'").fetchone()[0]
        db.execute(
            "INSERT INTO chat_jobs "
            "(id,conversation_id,user_id,text,scope,attachments,status,created,updated) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "queued-secret-a",
                conversation,
                principal.id,
                "secret-alice-question",
                "all",
                "[]",
                "queued",
                now,
                now,
            ),
        )
        db.execute(
            "INSERT INTO chat_jobs "
            "(id,conversation_id,user_id,text,scope,attachments,status,created,updated) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "queued-secret-b",
                conversation,
                bob_id,
                "secret-bob-question",
                "all",
                "[]",
                "queued",
                now - 100,
                now,
            ),
        )
    result = admin.get("/api/admin/load", headers=ORIGIN)
    assert result.status_code == 200
    queue = result.json()["chat_queue"]
    assert isinstance(queue["wait_deadline_seconds"], (int, float))
    assert isinstance(queue["oldest_queued_wait_seconds"], (int, float))
    for secret in ("alice", "bob", "secret-alice-question", "secret-bob-question"):
        assert secret not in result.text
