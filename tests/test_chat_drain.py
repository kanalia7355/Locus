"""Dialogue waiting-line drain: parallel pickup for the free model slots."""

import threading

import httpx
import pytest
from app.local_model import LocalModel
from app.main import create_app
from app.model_catalog import ModelCatalog
from app.service import ModelBusy, Principal, Service
from fastapi.testclient import TestClient
from test_api import ORIGIN, login

ANSWER = "列待ち後の合成提案 <script>"


def response() -> dict:
    return {
        "model": "fixture:latest",
        "done": True,
        "message": {"role": "assistant", "content": ANSWER},
    }


def make_app(service: Service, runtime: LocalModel) -> TestClient:
    catalog = ModelCatalog(
        {},
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"models": [{"name": "fixture:latest", "size": 1}]})
        ),
    )
    return TestClient(
        create_app(service=service, start_worker=False, model_catalog=catalog, local_model=runtime),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )


def setup(service: Service, *, slots: int | None = None) -> tuple[LocalModel, TestClient, str]:
    """Model-enabled app with a mock daemon; `slots` shapes the execution pool."""
    runtime = LocalModel(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=response()))
    )
    alice = make_app(service, runtime)
    login(alice, "alice", "02")
    conversation = alice.post(
        "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
    ).json()["id"]
    service.seed_synthetic("alice", "project-a")
    admin = make_app(service, runtime)
    login(admin, "admin", "01")
    candidate = admin.post(
        "/api/admin/models/discover", json={"sources": ["ollama"]}, headers=ORIGIN
    ).json()["models"][0]["id"]
    payload = {"candidate_id": candidate, "local_only_confirmed": True}
    if slots is not None:
        payload["slots"] = slots
    assert admin.put("/api/admin/models/runtime", json=payload, headers=ORIGIN).status_code == 200
    return runtime, alice, conversation


def principal_for(service: Service, client: TestClient) -> tuple[Principal, str]:
    token = client.cookies.get("locus_session")
    assert token
    return service.authenticate(token), token


def new_conversation(client: TestClient) -> str:
    return client.post(
        "/api/conversations", json={"project_id": "project-a"}, headers=ORIGIN
    ).json()["id"]


def enqueue(
    service: Service,
    actor: Principal,
    token: str,
    conversation: str,
    generate,
) -> str:
    return service.enqueue_chat(
        actor,
        conversation,
        "成膜条件",
        "all",
        [],
        token=token,
        generate=generate,
        validate=None,
    )


def generate_answer(runtime: LocalModel, text: str, citations: list[dict]):
    return runtime.generate("fixture:latest", text, citations)


def test_two_queued_dialogues_run_simultaneously_with_two_slots(service: Service) -> None:
    runtime, alice, conversation_a = setup(service, slots=2)
    conversation_b = new_conversation(alice)
    actor, token = principal_for(service, alice)

    def generate(text: str, citations: list[dict]):
        return generate_answer(runtime, text, citations)

    job_a = enqueue(service, actor, token, conversation_a, generate)
    job_b = enqueue(service, actor, token, conversation_b, generate)

    both_inside = threading.Barrier(2, timeout=10)
    observed: list[dict[str, str]] = []
    lock = threading.Lock()

    def handler(_request):
        try:
            both_inside.wait()
        except threading.BrokenBarrierError:
            return httpx.Response(200, json=response())
        # Both queued entries must be observed as running at the same time.
        with service.db() as db:
            rows = db.execute(
                "SELECT id, status FROM chat_jobs WHERE id IN (?, ?)", (job_a, job_b)
            ).fetchall()
        with lock:
            observed.append({row["id"]: row["status"] for row in rows})
        return httpx.Response(200, json=response())

    runtime.transport = httpx.MockTransport(handler)
    started = service.process_next_chat_batch(2)
    assert sorted(started) == sorted({job_a, job_b})
    # The barrier released only when both entries were generating at once.
    assert observed
    assert all(status == "running" for obs in observed for status in obs.values())
    assert service.chat_job(actor, job_a)["status"] == "done"
    assert service.chat_job(actor, job_b)["status"] == "done"
    assert runtime.slot_usage() == {"busy": 0, "total": 2}


def test_third_queued_dialogue_waits_while_two_slots_are_occupied(service: Service) -> None:
    runtime, alice, conversation_a = setup(service, slots=2)
    conversation_b = new_conversation(alice)
    actor, token = principal_for(service, alice)

    def generate(text: str, citations: list[dict]):
        return generate_answer(runtime, text, citations)

    job_a = enqueue(service, actor, token, conversation_a, generate)
    job_b = enqueue(service, actor, token, conversation_b, generate)
    bob = make_app(service, runtime)
    login(bob, "bob", "03")
    bob_actor, bob_token = principal_for(service, bob)
    conversation_c = new_conversation(bob)
    service.seed_synthetic("alice", "project-a", "shared")
    job_c = enqueue(service, bob_actor, bob_token, conversation_c, generate)

    both_inside = threading.Barrier(2, timeout=10)
    entered = threading.Event()
    release = threading.Event()

    def handler(_request):
        if release.is_set():
            return httpx.Response(200, json=response())
        both_inside.wait()
        entered.set()
        release.wait(10)
        return httpx.Response(200, json=response())

    runtime.transport = httpx.MockTransport(handler)
    drain = threading.Thread(target=service.process_next_chat_batch, args=(2,))
    drain.start()
    try:
        assert entered.wait(10)
        # Alice's second entry yields to bob's waiting entry (fair-share pick),
        # so the parallel batch occupies both slots with job_a and job_c and
        # job_b stays queued until one of them finishes.
        assert service.chat_job(actor, job_a)["status"] == "running"
        assert service.chat_job(bob_actor, job_c)["status"] == "running"
        assert service.chat_job(actor, job_b)["status"] == "queued"
        assert alice.get(f"/api/conversations/{conversation_b}").json()["messages"] == []
    finally:
        release.set()
    drain.join(10)
    assert not drain.is_alive()
    assert service.chat_job(actor, job_a)["status"] == "done"
    assert service.chat_job(bob_actor, job_c)["status"] == "done"
    started_again = service.process_next_chat_batch(2)
    assert started_again == [job_b]
    assert service.chat_job(actor, job_b)["status"] == "done"
    assert runtime.slot_usage() == {"busy": 0, "total": 2}


def test_parallel_drain_starts_at_most_the_slot_count(service: Service) -> None:
    runtime, alice, conversation_a = setup(service, slots=2)
    conversation_b = new_conversation(alice)
    actor, token = principal_for(service, alice)
    bob = make_app(service, runtime)
    login(bob, "bob", "03")
    bob_actor, bob_token = principal_for(service, bob)
    conversation_c = new_conversation(bob)

    def generate(text: str, citations: list[dict]) -> tuple[str, str]:
        return "合成", "fixture:latest"

    job_a = enqueue(service, actor, token, conversation_a, generate)
    job_b = enqueue(service, actor, token, conversation_b, generate)
    job_c = enqueue(service, bob_actor, bob_token, conversation_c, generate)
    assert service.process_next_chat_batch(0) == []
    # Alice's entry is oldest, and bob's waiting entry yields to no one: the
    # parallel pickup keeps the same fair-share order as the sequential one.
    started = service.process_next_chat_batch(2)
    assert started == [job_a, job_c]
    assert service.chat_job(actor, job_b)["status"] == "queued"
    assert service.process_next_chat_batch(2) == [job_b]
    assert service.chat_job(actor, job_b)["status"] == "done"


def test_parallel_drain_keeps_creation_order_between_users(service: Service) -> None:
    runtime, alice, conversation_a = setup(service)
    conversation_b = new_conversation(alice)
    bob = make_app(service, runtime)
    login(bob, "bob", "03")
    conversation_bob = new_conversation(bob)
    actor, token = principal_for(service, alice)
    bob_actor, bob_token = principal_for(service, bob)

    def generate(text: str, citations: list[dict]) -> tuple[str, str]:
        return "合成", "fixture:latest"

    service.last_chat_user = None
    job_a = enqueue(service, actor, token, conversation_a, generate)
    job_b = enqueue(service, bob_actor, bob_token, conversation_bob, generate)
    job_c = enqueue(service, actor, token, conversation_b, generate)
    # Older entries first; consecutive entries of one user yield to others.
    assert service.process_next_chat_batch(3) == [job_a, job_b, job_c]


def test_parallel_drain_deprioritizes_the_last_served_user(service: Service) -> None:
    runtime, alice, conversation_a = setup(service)
    conversation_b = new_conversation(alice)
    actor, token = principal_for(service, alice)
    bob = make_app(service, runtime)
    login(bob, "bob", "03")
    bob_actor, bob_token = principal_for(service, bob)
    conversation_bob = new_conversation(bob)

    def generate(text: str, citations: list[dict]) -> tuple[str, str]:
        return "合成", "fixture:latest"

    job_a = enqueue(service, actor, token, conversation_a, generate)
    job_b = enqueue(service, actor, token, conversation_b, generate)
    job_c = enqueue(service, bob_actor, bob_token, conversation_bob, generate)
    # Alice was served most recently, so bob's waiting entry goes first even
    # though alice's entries are older.
    service.last_chat_user = actor.id
    assert service.process_next_chat_batch(3) == [job_c, job_a, job_b]


def test_failed_dialogue_does_not_block_the_other_slot_or_leak_it(service: Service) -> None:
    runtime, alice, conversation_a = setup(service, slots=2)
    conversation_b = new_conversation(alice)
    actor, token = principal_for(service, alice)

    def generate_failing(text: str, citations: list[dict]) -> tuple[str, str]:
        raise RuntimeError("合成に失敗しました")

    def generate_ok(text: str, citations: list[dict]):
        return generate_answer(runtime, text, citations)

    job_a = enqueue(service, actor, token, conversation_a, generate_failing)
    job_b = enqueue(service, actor, token, conversation_b, generate_ok)
    started = service.process_next_chat_batch(2)
    assert sorted(started) == sorted({job_a, job_b})
    assert service.chat_job(actor, job_a)["status"] == "failed"
    assert service.chat_job(actor, job_b)["status"] == "done"
    assert runtime.slot_usage() == {"busy": 0, "total": 2}
    # The slot freed by the failed entry is reusable by the next waiting line.
    bob = make_app(service, runtime)
    login(bob, "bob", "03")
    bob_actor, bob_token = principal_for(service, bob)
    conversation_c = new_conversation(bob)
    job_c = enqueue(service, bob_actor, bob_token, conversation_c, generate_ok)
    assert service.process_next_chat_batch(2) == [job_c]
    assert service.chat_job(bob_actor, job_c)["status"] == "done"


def test_queued_drain_does_not_charge_the_user_twice(service: Service) -> None:
    runtime, alice, conversation = setup(service)
    actor, token = principal_for(service, alice)
    busy = True

    def generate(text: str, citations: list[dict]) -> tuple[str, str]:
        if busy:
            raise ModelBusy()
        return "合成", "fixture:latest"

    with pytest.raises(ModelBusy):
        service.send(
            actor,
            conversation,
            "成膜条件",
            "all",
            [],
            generate=generate,
            validate=None,
            token=token,
            charge_limit=True,
            chat_job_id=None,
        )
    job_id = service.enqueue_chat(
        actor,
        conversation,
        "成膜条件",
        "all",
        [],
        token=token,
        generate=generate,
        validate=None,
    )
    # The busy slot requeues the question without consuming the retry: the
    # waiting-line discharge must not charge the user's budget again.
    assert service.process_next_chat_batch(1) == [job_id]
    assert service.chat_job(actor, job_id)["status"] == "queued"
    busy = False
    assert service.process_next_chat_batch(1) == [job_id]
    assert service.chat_job(actor, job_id)["status"] == "done"
    assert len(service.limits.get("chat:" + actor.id, [])) == 1
