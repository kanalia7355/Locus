"""Synthetic concurrency and configuration checks for the model execution slots."""

import threading
from typing import Any

import httpx
import pytest
from app.local_model import MAX_SLOTS, LocalModel
from app.main import create_app
from app.model_catalog import ModelCatalog
from app.service import Service
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_api import ORIGIN, login

ANSWER = "合成資料からの提案"


def response() -> dict:
    return {
        "model": "fixture:latest",
        "done": True,
        "message": {"role": "assistant", "content": ANSWER},
    }


def admin_client(service: Service, handler) -> tuple[TestClient, LocalModel]:
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
    admin = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    login(admin, "admin", "01")
    return admin, runtime


def generate_in_thread(runtime: LocalModel, results: list[tuple[str, Any]]) -> threading.Thread:
    def run() -> None:
        try:
            answer, _model = runtime.generate("fixture:latest", "question", [])
            results.append(("ok", answer))
        except HTTPException as exc:
            results.append(("error", exc.status_code))

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def gated_handler(arrivals: threading.Semaphore, proceed: threading.Semaphore):
    def handler(request):
        arrivals.release()
        proceed.acquire(timeout=5)
        return httpx.Response(200, json=response())

    return handler


def test_one_slot_is_the_default_and_refuses_the_second_call():
    # No configuration at all: the default pool must behave like the former
    # single Lock, and LocalModel must report exactly one total slot.
    assert LocalModel().slot_usage() == {"busy": 0, "total": 1}
    arrivals, proceed = threading.Semaphore(0), threading.Semaphore(0)
    runtime = LocalModel(transport=httpx.MockTransport(gated_handler(arrivals, proceed)))
    results: list[tuple[str, Any]] = []
    first = generate_in_thread(runtime, results)
    try:
        assert arrivals.acquire(timeout=5)
        with pytest.raises(HTTPException) as busy:
            runtime.generate("fixture:latest", "question", [])
        assert busy.value.status_code == 429 and busy.value.detail == "モデルは処理中です"
    finally:
        proceed.release()
        first.join(timeout=5)
    assert results == [("ok", ANSWER)]


def test_two_slots_run_two_answers_and_only_the_third_is_refused():
    arrivals, proceed = threading.Semaphore(0), threading.Semaphore(0)
    runtime = LocalModel(transport=httpx.MockTransport(gated_handler(arrivals, proceed)))
    runtime.configure(None, False, slots=2)
    results: list[tuple[str, Any]] = []
    threads = [generate_in_thread(runtime, results) for _ in range(2)]
    try:
        assert arrivals.acquire(timeout=5)
        assert arrivals.acquire(timeout=5)
        assert runtime.slot_usage() == {"busy": 2, "total": 2}
        with pytest.raises(HTTPException) as busy:
            runtime.generate("fixture:latest", "question", [])
        assert busy.value.status_code == 429 and busy.value.detail == "モデルは処理中です"
    finally:
        for _ in threads:
            proceed.release()
        for thread in threads:
            thread.join(timeout=5)
    assert results == [("ok", ANSWER), ("ok", ANSWER)]
    assert runtime.slot_usage() == {"busy": 0, "total": 2}


def test_failing_answers_return_their_slots():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) <= 2:
            # Use the pool up while failing, so a leaked slot would surface.
            raise httpx.ReadTimeout("synthetic")
        return httpx.Response(200, json=response())

    runtime = LocalModel(transport=httpx.MockTransport(handler))
    runtime.configure(None, False, slots=2)
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            runtime.generate("fixture:latest", "question", [])
        assert error.value.status_code == 502
    assert runtime.slot_usage() == {"busy": 0, "total": 2}
    # The failed generations must not have kept any slot occupied.
    assert runtime.generate("fixture:latest", "question", [])[1] == "fixture:latest"


def test_invalid_slot_values_are_refused_and_change_nothing(service: Service):
    admin, runtime = admin_client(service, lambda _: httpx.Response(200, json=response()))
    version = runtime.version
    for value in [0, -1, 2.5, "2", True, MAX_SLOTS + 1]:
        result = admin.put("/api/admin/models/runtime", json={"slots": value}, headers=ORIGIN)
        assert result.status_code == 422, value
    assert runtime.version == version and runtime.slot_usage() == {"busy": 0, "total": 1}


def test_slot_counts_are_reported_to_the_admin_load_view(service: Service):
    def handler(_):
        return httpx.Response(200, json=response())

    admin, runtime = admin_client(service, handler)
    # Before any configuration the display states the unchanged default pool.
    before = admin.get("/api/admin/load").json()["model_slot"]
    assert before == {"enabled": False, "busy": 0, "total": 1}
    result = admin.post("/api/admin/models/discover", json={"sources": ["ollama"]}, headers=ORIGIN)
    candidate = result.json()["models"][0]["id"]
    configured = admin.put(
        "/api/admin/models/runtime",
        json={"candidate_id": candidate, "local_only_confirmed": True, "slots": 2},
        headers=ORIGIN,
    )
    assert configured.status_code == 200
    # One occupied slot is reported as a count, not as a boolean.
    assert runtime.lock.acquire(blocking=False)
    try:
        observed = admin.get("/api/admin/load").json()["model_slot"]
        assert observed == {"enabled": True, "busy": 1, "total": 2}
    finally:
        runtime.lock.release()
    after = admin.get("/api/admin/load").json()["model_slot"]
    assert after == {"enabled": True, "busy": 0, "total": 2}
