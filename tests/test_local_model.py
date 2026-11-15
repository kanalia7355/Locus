"""Synthetic documents and mock HTTP only; never contacts a model daemon."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from app.local_model import LocalModel
from app.main import create_app
from app.model_catalog import ModelCatalog
from app.service import Service
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_api import ORIGIN, login


def response() -> dict:
    return {
        "model": "fixture:latest",
        "done": True,
        "message": {"role": "assistant", "content": "合成資料からの提案 <script>"},
    }


def setup(service: Service, handler: Callable):
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
    result = admin.post("/api/admin/models/discover", json={"sources": ["ollama"]}, headers=ORIGIN)
    candidate = result.json()["models"][0]["id"]
    assert (
        admin.put(
            "/api/admin/models/runtime",
            json={"candidate_id": candidate, "local_only_confirmed": True},
            headers=ORIGIN,
        ).status_code
        == 200
    )
    return admin, alice, conversation, runtime


def send(client, conversation):
    return client.post(
        f"/api/conversations/{conversation}/messages",
        json={"text": "成膜条件", "scope": "all"},
        headers=ORIGIN,
    )


def test_generated_history_live_acl_and_no_previous_answers(service: Service):
    calls = []

    def handler(request):
        assert not service.conn.in_transaction
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        assert "authorization" not in request.headers
        payload = json.loads(request.content)
        assert "tools" not in payload and payload["stream"] is False
        assert len(payload["messages"]) == 2
        assert "合成資料からの提案" not in request.content.decode()
        sources = json.loads(payload["messages"][1]["content"])["sources"]
        assert 0 < len(sources) <= 5
        calls.append(request)
        return httpx.Response(200, json=response())

    admin, alice, conv, runtime = setup(service, handler)
    first = send(alice, conv)
    assert first.status_code == 200, first.text
    assert first.json()["answer"] == response()["message"]["content"]
    assert send(alice, conv).status_code == 200 and len(calls) == 2
    assert alice.get(f"/api/conversations/{conv}").json()["messages"][0]["answer"]
    with service.db() as db:
        db.execute("DELETE FROM chunks")
    hidden = alice.get(f"/api/conversations/{conv}").json()["messages"][0]
    assert hidden["answer"] is None and hidden["answer_hidden"] is True
    assert "合成資料からの提案" not in admin.get("/api/admin/audit").text
    assert admin.get(f"/api/conversations/{conv}").status_code == 404
    alice.delete(f"/api/conversations/{conv}", headers=ORIGIN)
    assert service.conn.execute("SELECT COUNT(*) FROM generated_answers").fetchone()[0] == 0


def test_generated_history_survives_reopen_and_masks_partial_grant_revocation(service: Service):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response())

    admin, alice, conv, _ = setup(service, handler)
    shared = service.seed_synthetic("admin", "project-a", "shared")
    original = send(alice, conv)
    assert original.status_code == 200, original.text
    saved = original.json()
    assert len(saved["citations"]) == 2 and len(calls) == 1
    db_path = Path(service.conn.execute("PRAGMA database_list").fetchone()[2])
    admin_cookie, alice_cookie = (
        admin.cookies.get("locus_session"),
        alice.cookies.get("locus_session"),
    )
    service.close()

    def no_network(request):
        pytest.fail("Reopening history must not perform a model or discovery request")

    transport = httpx.MockTransport(no_network)
    reopened = Service(db_path)
    try:
        app = create_app(
            service=reopened,
            start_worker=False,
            local_model=LocalModel(transport=transport),
            model_catalog=ModelCatalog({}, transport=transport),
        )

        def client(token):
            result = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
            result.cookies.set("locus_session", token)
            return result

        restarted_admin, restarted_alice = client(admin_cookie), client(alice_cookie)
        assert restarted_admin.get("/api/admin/models/runtime").json() == {
            "enabled": False,
            "model": None,
            "timeout_seconds": 30,
        }
        restored = restarted_alice.get(f"/api/conversations/{conv}")
        assert restored.status_code == 200
        restored_message = restored.json()["messages"][0]
        assert restored_message["id"] == saved["id"]
        assert restored_message["answer"] == saved["answer"]
        assert restored_message["model"] == saved["model"]
        assert restored_message["citations"] == saved["citations"]
        assert restarted_admin.get(f"/api/conversations/{conv}").status_code == 404
        revoked = restarted_admin.put(
            f"/api/documents/{shared}/publication",
            headers=ORIGIN,
            json={"grants": [{"role": "viewer", "operations": ["read", "retrieve"]}]},
        )
        assert revoked.status_code == 204
        hidden = restarted_alice.get(f"/api/conversations/{conv}").json()["messages"][0]
        assert len(hidden["citations"]) == 1
        assert (
            hidden["answer"] is None and hidden["model"] is None and hidden["answer_hidden"] is True
        )
        assert len(calls) == 1
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "change", ["session", "source", "settings", "timeout", "conversation", "rotation"]
)
def test_inflight_revocation_never_persists_answer(service: Service, change: str):
    def handler(_):
        if change == "settings":
            runtime.configure(None, False)
        elif change == "timeout":
            runtime.configure(next(iter(runtime.registered)), True, 120)
        else:
            with service.db() as db:
                if change == "session":
                    db.execute(
                        "DELETE FROM sessions WHERE user_id="
                        "(SELECT id FROM users WHERE username='alice')"
                    )
                elif change == "source":
                    db.execute("DELETE FROM chunks")
                elif change == "conversation":
                    db.execute("DELETE FROM conversations WHERE id=?", (conv,))
                else:
                    db.execute("UPDATE users SET must_rotate=1 WHERE username='alice'")
        return httpx.Response(200, json=response())

    _, alice, conv, runtime = setup(service, handler)
    assert send(alice, conv).status_code in {401, 403, 404, 409}
    assert service.conn.execute("SELECT COUNT(*) FROM generated_answers").fetchone()[0] == 0
    assert service.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


@pytest.mark.parametrize(
    "kind",
    [
        "redirect",
        "compression",
        "oversize",
        "json",
        "schema",
        "tools",
        "unfinished",
        "wrong-model",
        "timeout",
        "long-answer",
    ],
)
def test_invalid_responses_fail_without_retry(kind: str):
    calls = []

    def handler(request):
        calls.append(request)
        data = response()
        if kind == "redirect":
            return httpx.Response(307, headers={"location": "https://example.invalid"})
        if kind == "compression":
            return httpx.Response(200, headers={"content-encoding": "unsupported"})
        if kind == "oversize":
            return httpx.Response(200, content=b"x" * 1_048_577)
        if kind == "json":
            return httpx.Response(200, content=b"not-json")
        if kind == "schema":
            return httpx.Response(200, json=[])
        if kind == "timeout":
            raise httpx.ReadTimeout("synthetic")
        if kind == "tools":
            data["message"]["tool_calls"] = [{"function": {"name": "exec"}}]
        if kind == "unfinished":
            data["done"] = False
        if kind == "wrong-model":
            data["model"] = "other"
        if kind == "long-answer":
            data["message"]["content"] = "x" * 20_001
        return httpx.Response(200, json=data)

    runtime = LocalModel(transport=httpx.MockTransport(handler))
    with pytest.raises(HTTPException) as error:
        runtime.generate("fixture:latest", "question", [{"id": "a", "text": "synthetic"}])
    assert error.value.status_code == 502 and len(calls) == 1
    assert runtime.lock.acquire(blocking=False)
    runtime.lock.release()


def test_runtime_authorization_confirmation_and_default_no_model(service: Service):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response())

    admin, alice, conv, runtime = setup(service, handler)
    assert alice.put("/api/admin/models/runtime", json={}, headers=ORIGIN).status_code == 403
    assert (
        admin.put(
            "/api/admin/models/runtime",
            json={"candidate_id": "unknown", "local_only_confirmed": True},
            headers=ORIGIN,
        ).status_code
        == 422
    )
    assert (
        admin.put(
            "/api/admin/models/runtime",
            json={"candidate_id": next(iter(runtime.registered))},
            headers=ORIGIN,
        ).status_code
        == 422
    )
    assert admin.put("/api/admin/models/runtime", json={}, headers=ORIGIN).status_code == 200
    assert send(alice, conv).json()["answer"] is None and calls == []
    assert LocalModel().status() == {"enabled": False, "model": None, "timeout_seconds": 30}


def test_busy_and_cancel_release_without_retry():
    runtime = LocalModel()
    runtime.lock.acquire()
    with pytest.raises(HTTPException) as error:
        runtime.generate("fixture", "question", [])
    assert error.value.status_code == 429
    runtime.lock.release()

    async def cancel(_):
        raise asyncio.CancelledError()

    runtime.transport = httpx.MockTransport(cancel)
    with pytest.raises(asyncio.CancelledError):
        runtime.generate("fixture", "question", [])
    assert runtime.lock.acquire(blocking=False)
    runtime.lock.release()


def test_total_deadline_stops_without_retry(monkeypatch):
    calls = []

    async def slow(request):
        calls.append(request)
        await asyncio.sleep(1)
        return httpx.Response(200, json=response())

    monkeypatch.setattr("app.local_model.REQUEST_SECONDS", 0.01)
    runtime = LocalModel(transport=httpx.MockTransport(slow))
    with pytest.raises(HTTPException) as error:
        runtime.generate("fixture:latest", "question", [])
    assert error.value.status_code == 502 and len(calls) == 1


def test_prompt_isolation_and_partial_source_revocation(service: Service):
    inputs = []

    def handler(request):
        inputs.append(request.content.decode())
        return httpx.Response(200, json=response())

    _, alice, conv, _ = setup(service, handler)
    # Existing sample belongs to alice. A second authorized sample ensures that
    # losing just ONE source hides the whole answer, rather than partial redaction.
    service.seed_synthetic("alice", "project-a")
    service.assign("bob", "project-a", "researcher")
    private = service.seed_synthetic("bob", "project-a")
    with service.db() as db:
        db.execute(
            "UPDATE chunks SET text='成膜条件 other-user-secret' WHERE document_id=?", (private,)
        )
    result = send(alice, conv)
    assert result.status_code == 200 and len(result.json()["citations"]) == 2
    assert "other-user-secret" not in inputs[0]
    lost = result.json()["citations"][0]["id"]
    with service.db() as db:
        db.execute("DELETE FROM chunks WHERE id=?", (lost,))
    message = alice.get(f"/api/conversations/{conv}").json()["messages"][0]
    assert len(message["citations"]) == 1
    assert message["answer"] is None and message["answer_hidden"] is True


def test_timeout_selection_is_strict_and_resets_on_disable(service: Service):
    admin, _, _, runtime = setup(service, lambda _: httpx.Response(200, json=response()))
    candidate = next(iter(runtime.registered))
    assert runtime.status()["timeout_seconds"] == 30
    configured = admin.put(
        "/api/admin/models/runtime",
        headers=ORIGIN,
        json={"candidate_id": candidate, "local_only_confirmed": True, "timeout_seconds": 120},
    )
    assert configured.status_code == 200 and configured.json()["timeout_seconds"] == 120
    assert admin.get("/api/admin/models/runtime").json() == configured.json()
    version = runtime.version
    for value in [0, 60, 121, True, False, "120", 120.0, None, []]:
        assert (
            admin.put(
                "/api/admin/models/runtime",
                headers=ORIGIN,
                json={
                    "candidate_id": candidate,
                    "local_only_confirmed": True,
                    "timeout_seconds": value,
                },
            ).status_code
            == 422
        )
    assert runtime.version == version and runtime.timeout_seconds == 120
    assert admin.put(
        "/api/admin/models/runtime", headers=ORIGIN, json={"timeout_seconds": 120}
    ).json() == {"enabled": False, "model": None, "timeout_seconds": 30}
    assert LocalModel().timeout_seconds == 30


def test_selected_total_deadline_and_http_timeouts_use_same_snapshot(monkeypatch):
    # Scale 1 logical second to 5ms: exercise a 60-second response without
    # lengthening test runs or performing any actual network/model operation.
    original_timeout = asyncio.timeout
    selected = []

    def scaled_timeout(seconds):
        selected.append(seconds)
        return original_timeout(seconds * 0.005)

    monkeypatch.setattr("app.local_model.asyncio.timeout", scaled_timeout)
    calls = []

    async def delayed(request):
        calls.append(request)
        await asyncio.sleep(0.3)
        return httpx.Response(200, json=response())

    runtime = LocalModel(transport=httpx.MockTransport(delayed))
    with pytest.raises(HTTPException):
        runtime.generate("fixture:latest", "question", [], timeout_seconds=30)
    assert (
        runtime.generate("fixture:latest", "question", [], timeout_seconds=120)[1]
        == "fixture:latest"
    )
    assert selected == [30, 120] and len(calls) == 2
    assert set(calls[0].extensions["timeout"].values()) == {30}
    assert set(calls[1].extensions["timeout"].values()) == {120}


def test_120_total_deadline_exceeded_releases_lock_without_retry(monkeypatch):
    original_timeout = asyncio.timeout
    monkeypatch.setattr(
        "app.local_model.asyncio.timeout", lambda seconds: original_timeout(seconds * 0.001)
    )
    calls = []

    async def delayed(request):
        calls.append(request)
        await asyncio.sleep(1)
        return httpx.Response(200, json=response())

    runtime = LocalModel(transport=httpx.MockTransport(delayed))
    with pytest.raises(HTTPException) as error:
        runtime.generate("fixture:latest", "question", [], timeout_seconds=120)
    assert error.value.status_code == 502 and len(calls) == 1
    assert runtime.lock.acquire(blocking=False)
    runtime.lock.release()


def fragments(model: str, parts: list[str]) -> list[bytes]:
    """Ollama streams one JSON object per line and a final completion line."""
    lines = [
        json.dumps({"model": model, "done": False, "message": {"role": "assistant", "content": p}})
        for p in parts
    ]
    lines.append(
        json.dumps({"model": model, "done": True, "message": {"role": "assistant", "content": ""}})
    )
    return [line.encode() + b"\n" for line in lines]


def streamed(client, conversation, text: str = "成膜条件"):
    return client.stream(
        "POST",
        f"/api/conversations/{conversation}/messages/stream",
        json={"text": text, "scope": "all"},
        headers=ORIGIN,
    )


def events(response) -> list[tuple[str, dict]]:
    collected: list[tuple[str, dict]] = []
    name = ""
    for line in response.iter_lines():
        if line.startswith("event: "):
            name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            collected.append((name, json.loads(line.removeprefix("data: "))))
    return collected


def test_streamed_dialogue_arrives_in_fragments_and_commits_one_answer(service: Service):
    parts = ["合成資料", "からの", "提案"]

    def handler(request):
        payload = json.loads(request.content)
        assert payload["stream"] is True and "tools" not in payload
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        assert "authorization" not in request.headers

        async def body():
            for chunk in fragments("fixture:latest", parts):
                yield chunk

        return httpx.Response(200, content=body())

    admin, alice, conv, _ = setup(service, handler)
    with streamed(alice, conv) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("text/event-stream")
        received = events(response)
    names = [name for name, _ in received]
    assert names[0] == "start" and names[-1] == "message"
    assert [data["text"] for name, data in received if name == "delta"] == parts
    job = received[0][1]["job_id"]
    answer = received[-1][1]
    assert answer["answer"] == "".join(parts) and answer["citations"]
    messages = alice.get(f"/api/conversations/{conv}").json()["messages"]
    assert len(messages) == 1 and messages[0]["answer"] == "".join(parts)
    assert alice.get(f"/api/chat-jobs/{job}").json()["status"] == "done"
    assert "".join(parts) not in admin.get("/api/admin/audit").text


def test_cancelled_stream_stops_and_stores_no_answer(service: Service):
    delivered = []

    def handler(request):
        async def body():
            for chunk in fragments("fixture:latest", ["最初の断片", "二番目の断片", "三番目"]):
                delivered.append(chunk)
                yield chunk
                if len(delivered) == 1:
                    # The owner cancels while the reply is still arriving.
                    job = service.conn.execute(
                        "SELECT id,user_id FROM chat_jobs WHERE status='running'"
                    ).fetchone()
                    principal = service.authenticate(alice.cookies.get("locus_session"))
                    assert job["user_id"] == principal.id
                    service.cancel_chat_job(principal, job["id"])
                    # The cancellation check between fragments is throttled.
                    await asyncio.sleep(0.4)

        return httpx.Response(200, content=body())

    admin, alice, conv, _ = setup(service, handler)
    with streamed(alice, conv) as response:
        assert response.status_code == 200
        received = events(response)
    names = [name for name, _ in received]
    assert names[0] == "start" and names[-1] == "cancelled"
    job = received[0][1]["job_id"]
    # Interrupted mid-reply: fragments were shown, and the rest never arrived.
    assert 0 < len([name for name in names if name == "delta"]) < 3
    assert len(delivered) < 4
    assert alice.get(f"/api/conversations/{conv}").json()["messages"] == []
    assert alice.get(f"/api/chat-jobs/{job}").json()["status"] == "cancelled"
    assert service.conn.execute("SELECT COUNT(*) FROM generated_answers").fetchone()[0] == 0


def test_stream_refuses_other_conversations_and_unconfigured_models(service: Service):
    def handler(request):
        pytest.fail("A refused stream must not reach the model")

    admin, alice, conv, runtime = setup(service, handler)
    bob = TestClient(alice.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    login(bob, "bob", "03")
    with streamed(bob, conv) as response:
        assert response.status_code in {403, 404}
        assert not response.headers["content-type"].startswith("text/event-stream")
    assert service.conn.execute("SELECT COUNT(*) FROM chat_jobs").fetchone()[0] == 0
    assert (
        admin.put(
            "/api/admin/models/runtime",
            json={"candidate_id": None, "local_only_confirmed": True},
            headers=ORIGIN,
        ).status_code
        == 200
    )
    with streamed(alice, conv) as response:
        # Without a configured model the caller falls back to the ordinary request.
        assert response.status_code == 409
    assert service.conn.execute("SELECT COUNT(*) FROM chat_jobs").fetchone()[0] == 0


def test_stream_declines_a_busy_slot_so_the_caller_keeps_the_waiting_line(service: Service):
    def handler(request):
        pytest.fail("A declined stream must not reach the model")

    _, alice, conv, runtime = setup(service, handler)
    assert runtime.lock.acquire(blocking=False)
    try:
        with streamed(alice, conv) as response:
            assert response.status_code == 409
    finally:
        runtime.lock.release()
    assert service.conn.execute("SELECT COUNT(*) FROM chat_jobs").fetchone()[0] == 0


def test_stream_degrades_to_one_fragment_for_a_daemon_that_ignores_streaming(service: Service):
    answer = "一括で返す合成回答"

    def handler(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(
            200,
            content=json.dumps(
                {
                    "model": "fixture:latest",
                    "done": True,
                    "message": {"role": "assistant", "content": answer},
                }
            ).encode(),
        )

    _, alice, conv, _ = setup(service, handler)
    with streamed(alice, conv) as response:
        assert response.status_code == 200
        received = events(response)
    assert [data["text"] for name, data in received if name == "delta"] == [answer]
    assert received[-1][0] == "message" and received[-1][1]["answer"] == answer
    assert alice.get(f"/api/conversations/{conv}").json()["messages"][0]["answer"] == answer
