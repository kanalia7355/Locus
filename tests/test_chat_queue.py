"""Dialogue waiting-line behavior with synthetic documents and mock HTTP only."""

import threading
import time
import traceback
from pathlib import Path

import httpx
import pytest
from app.local_model import LocalModel
from app.main import create_app
from app.model_catalog import ModelCatalog
from app.service import Principal, Service
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_api import ORIGIN, login


def response() -> dict:
    return {
        "model": "fixture:latest",
        "done": True,
        "message": {"role": "assistant", "content": "列待ち後の合成提案 <script>"},
    }


def setup(service: Service):
    """Model-enabled app with a mock daemon whose first response can be held."""
    entered, release = threading.Event(), threading.Event()

    def handler(_request):
        entered.set()
        if not release.wait(10):
            raise AssertionError("holder was not released")
        return httpx.Response(200, json=response())

    runtime = LocalModel(transport=httpx.MockTransport(handler))
    catalog = ModelCatalog(
        {},
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"models": [{"name": "fixture:latest", "size": 1}]})
        ),
    )
    app = create_app(
        service=service, start_worker=False, model_catalog=catalog, local_model=runtime
    )

    def client():
        return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))

    admin, alice = client(), client()
    login(admin, "admin", "01")
    login(alice)
    conversation = alice.post(
        "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
    ).json()["id"]
    service.seed_synthetic("alice", "project-a")
    candidate = admin.post(
        "/api/admin/models/discover", json={"sources": ["ollama"]}, headers=ORIGIN
    ).json()["models"][0]["id"]
    assert (
        admin.put(
            "/api/admin/models/runtime",
            json={"candidate_id": candidate, "local_only_confirmed": True},
            headers=ORIGIN,
        ).status_code
        == 200
    )
    return alice, conversation, runtime, entered, release


def occupy(runtime: LocalModel, entered: threading.Event, release: threading.Event):
    """Hold the single model slot from a separate thread, like a slow answer."""

    def hold():
        try:
            runtime.generate("fixture:latest", "占め", [])
        except BaseException:
            traceback.print_exc()
            raise
        finally:
            entered.set()

    thread = threading.Thread(target=hold)
    thread.start()
    assert entered.wait(5)


def send(client: TestClient, conversation: str):
    return client.post(
        f"/api/conversations/{conversation}/messages",
        json={"text": "成膜条件", "scope": "all"},
        headers=ORIGIN,
    )


def principal_for(client: TestClient, service: Service):
    token = client.cookies.get("locus_session")
    assert token
    return service.authenticate(token), token


def test_occupied_slot_queues_the_question_and_allows_cancel(service: Service):
    alice, conversation, runtime, entered, release = setup(service)
    occupy(runtime, entered, release)
    try:
        result = send(alice, conversation)
        assert result.status_code == 202, result.text
        body = result.json()
        assert body["status"] == "queued"
        job = body["job_id"]
        # Nothing is published before the slot frees.
        assert alice.get(f"/api/conversations/{conversation}").json()["messages"] == []
        status = alice.get(f"/api/chat-jobs/{job}").json()
        assert status["status"] == "queued" and status["message_id"] is None
        # A second question for the same conversation is rejected while waiting.
        assert send(alice, conversation).status_code == 409
        assert alice.delete(f"/api/chat-jobs/{job}", headers=ORIGIN).status_code == 204
        assert alice.get(f"/api/chat-jobs/{job}").json()["status"] == "cancelled"
        assert service.process_next_chat() is False
        assert alice.get(f"/api/conversations/{conversation}").json()["messages"] == []
    finally:
        release.set()


def test_worker_tick_while_slot_is_busy_requeues_the_job(service: Service):
    """A pickup before the slot frees must return to the line, not fail the job."""
    alice, conversation, runtime, entered, release = setup(service)
    occupy(runtime, entered, release)
    try:
        job = send(alice, conversation).json()["job_id"]
        assert service.process_next_chat() is False
        status = alice.get(f"/api/chat-jobs/{job}").json()
        assert status["status"] == "queued"
        release.set()
        assert service.process_next_chat() is True
        status = alice.get(f"/api/chat-jobs/{job}").json()
        assert status["status"] == "done" and status["message_id"]
        assert alice.get(f"/api/conversations/{conversation}").json()["messages"]
    finally:
        release.set()


def test_queued_question_runs_and_persists_after_disconnect(service: Service):
    alice, conversation, runtime, entered, release = setup(service)
    occupy(runtime, entered, release)
    try:
        job = send(alice, conversation).json()["job_id"]
        release.set()
        assert service.process_next_chat() is True
        status = alice.get(f"/api/chat-jobs/{job}").json()
        assert status["status"] == "done" and status["message_id"]
        history = alice.get(f"/api/conversations/{conversation}").json()
        assert history["messages"][0]["answer"].startswith("列待ち後の合成提案")
        assert history["messages"][0]["citations"]
        # Script text stays inert data; the browser tests assert it never executes.
        assert service.process_next_chat() is False
    finally:
        release.set()


def test_waiting_results_are_visible_only_to_the_owner(service: Service):
    alice, conversation, runtime, entered, release = setup(service)
    bob = TestClient(
        create_app(service=service, start_worker=False),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )
    login(bob, "bob", "03")
    occupy(runtime, entered, release)
    try:
        job = send(alice, conversation).json()["job_id"]
        assert bob.get(f"/api/chat-jobs/{job}").status_code == 404
        assert bob.delete(f"/api/chat-jobs/{job}", headers=ORIGIN).status_code == 404
        assert alice.get(f"/api/chat-jobs/{job}").status_code == 200
    finally:
        release.set()


def test_session_loss_while_waiting_fails_the_job_without_sending(service: Service):
    alice, conversation, runtime, entered, release = setup(service)
    occupy(runtime, entered, release)
    try:
        job = send(alice, conversation).json()["job_id"]
        release.set()
        # Rotation deletes all sessions; the queued dispatch re-authenticates.
        alice.post(
            "/api/auth/password",
            json={
                "current_password": "Changed-password-long-01!",
                "new_password": "Rotated-password-long-01!",
            },
            headers=ORIGIN,
        )
        assert service.process_next_chat() is True
        status = alice.get(f"/api/chat-jobs/{job}").json()
        assert status["status"] == "failed"
        assert "ログイン状態" in status["detail"]
        assert alice.get(f"/api/conversations/{conversation}").json()["messages"] == []
    finally:
        release.set()


def test_per_user_waiting_limit_is_reported_with_retry_guidance(service: Service):
    alice, conversation, _runtime, _entered, _release = setup(service)
    principal, token = principal_for(alice, service)
    dispatch = lambda text, citations: ("合成", "fixture:latest")  # noqa: E731
    for _ in range(2):
        cid = service.new_conversation(principal, "project-a")["id"]
        service.enqueue_chat(
            principal,
            cid,
            "上限確認",
            "all",
            [],
            token=token,
            generate=dispatch,
            validate=None,
        )
    third = service.new_conversation(principal, "project-a")["id"]
    with pytest.raises(HTTPException) as exc:
        service.enqueue_chat(
            principal,
            third,
            "上限確認",
            "all",
            [],
            token=token,
            generate=dispatch,
            validate=None,
        )
    assert exc.value.status_code == 429


def test_global_waiting_line_limit_is_reported_with_retry_guidance(service: Service):
    _alice, _conversation, _runtime, _entered, _release = setup(service)
    dispatch = lambda text, citations: ("合成", "fixture:latest")  # noqa: E731
    actors = []
    for index in range(17):
        name = f"cap-{index}"
        service.provision(name, f"Temporary-password-{index:02d}!")
        service.assign(name, "project-a", "researcher")
        with service.db() as db:
            user_id = db.execute("SELECT id FROM users WHERE username=?", (name,)).fetchone()["id"]
        principal = Principal(user_id, name, False, False)
        cid = service.new_conversation(principal, "project-a")["id"]
        actors.append((principal, cid))
    for principal, cid in actors[:16]:
        service.enqueue_chat(
            principal,
            cid,
            "上限確認",
            "all",
            [],
            token="unused",
            generate=dispatch,
            validate=None,
        )
    principal, cid = actors[16]
    with pytest.raises(HTTPException) as exc:
        service.enqueue_chat(
            principal,
            cid,
            "上限確認",
            "all",
            [],
            token="unused",
            generate=dispatch,
            validate=None,
        )
    assert exc.value.status_code == 429


def test_wait_deadline_fails_the_job_visibly(service: Service):
    alice, conversation, _runtime, _entered, _release = setup(service)
    principal, token = principal_for(alice, service)
    job = service.enqueue_chat(
        principal,
        conversation,
        "期限確認",
        "all",
        [],
        token=token,
        generate=lambda text, citations: ("合成", "fixture:latest"),
        validate=None,
    )
    with service.db() as db:
        db.execute("UPDATE chat_jobs SET created=? WHERE id=?", (time.time() - 400, job))
    assert service.process_next_chat() is True
    status = alice.get(f"/api/chat-jobs/{job}").json()
    assert status["status"] == "failed" and "待機上限" in status["detail"]
    assert alice.get(f"/api/conversations/{conversation}").json()["messages"] == []


def test_restart_fails_pending_dialogues_instead_of_hanging(tmp_path: Path):
    path = tmp_path / "restart.sqlite3"
    first = Service(path)
    try:
        first.provision("solo", "Temporary-password-09!")
        first.create_project("org-a", "project-a", "研究プロジェクト")
        first.assign("solo", "project-a", "researcher")
        first.seed_synthetic("solo", "project-a")
        client = TestClient(
            create_app(service=first, start_worker=False),
            base_url="http://127.0.0.1",
            client=("127.0.0.1", 50000),
        )
        login(client, "solo", "09")
        conversation = client.post(
            "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
        ).json()["id"]
        principal, token = principal_for(client, first)
        job = first.enqueue_chat(
            principal,
            conversation,
            "再開確認",
            "all",
            [],
            token=token,
            generate=lambda text, citations: ("合成", "fixture:latest"),
            validate=None,
        )
    finally:
        first.close()
    reopened = Service(path)
    try:
        reopened.recover_jobs()
        status = reopened.chat_job(principal, job)
        assert status["status"] == "failed" and "再起動" in status["detail"]
        assert reopened.process_next_chat() is False
    finally:
        reopened.close()
