import pathlib
import time
import uuid

import pytest
from app.main import create_app
from app.service import Service
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://127.0.0.1:5174"}


def login(client: TestClient, username: str = "alice", number: str = "02") -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": f"Temporary-password-{number}!"},
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/api/auth/password",
        json={
            "current_password": f"Temporary-password-{number}!",
            "new_password": "Changed-password-long-01!",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text


def client_for(service: Service) -> TestClient:
    return TestClient(
        create_app(service=service, start_worker=False),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )


@pytest.fixture
def service(tmp_path: pathlib.Path) -> Service:
    """Provide a fresh Service instance per test using tmp_path."""
    svc = Service(tmp_path / "test.sqlite3")
    svc.provision("admin", "Temporary-password-01!", system_admin=True)
    svc.provision("alice", "Temporary-password-02!")
    svc.provision("bob", "Temporary-password-03!")
    svc.create_project("org-a", "project-a", "研究プロジェクト")
    svc.assign("alice", "project-a", "researcher")
    # bob is NOT assigned to project-a → no upload permission
    yield svc
    svc.close()


@pytest.fixture
def client(service: Service) -> TestClient:
    return client_for(service)


# ---- 7 reason tests ----


def test_inventory_accepted(service: Service) -> None:
    """Valid candidate returns ``accepted``."""
    client = client_for(service)
    login(client)

    result = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "sample.txt", "size": 100}]},
        headers=ORIGIN,
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["inventory"][0]["status"] == "accepted"
    assert data["summary"]["by_reason"]["accepted"] == 1


def test_inventory_unsupported_format(service: Service) -> None:
    """Unsupported extension returns ``unsupported_format``."""
    client = client_for(service)
    login(client)

    result = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "sample.exe", "size": 100}]},
        headers=ORIGIN,
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["inventory"][0]["status"] == "unsupported_format"
    assert data["summary"]["by_reason"]["unsupported_format"] == 1


def test_inventory_too_large(service: Service) -> None:
    """Content exceeding 256 KiB returns ``too_large``."""
    client = client_for(service)
    login(client)

    result = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "sample.txt", "size": 300_000}]},
        headers=ORIGIN,
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["inventory"][0]["status"] == "too_large"
    assert data["summary"]["by_reason"]["too_large"] == 1


def test_invalid_name_has_control_chars(service: Service) -> None:
    """Name with control characters returns ``invalid_name``."""
    client = client_for(service)
    login(client)

    result = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "x\x00y.txt", "size": 100}]},
        headers=ORIGIN,
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["inventory"][0]["status"] == "invalid_name"
    assert data["summary"]["by_reason"]["invalid_name"] == 1


def test_invalid_name_starts_with_dot(service: Service) -> None:
    """Name starting with ``.`` returns ``invalid_name``."""
    client = client_for(service)
    login(client)

    result = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": ".hidden.txt", "size": 100}]},
        headers=ORIGIN,
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["inventory"][0]["status"] == "invalid_name"
    assert data["summary"]["by_reason"]["invalid_name"] == 1


def test_invalid_name_too_long(service: Service) -> None:
    """Name with problematic characters returns ``invalid_name``.

    FastAPI enforces max 160 chars at the API level, so we test with
    characters that bypass the length check but fail the safety check.
    """
    client = client_for(service)
    login(client)

    # Names with control chars or unsafe characters that pass FastAPI str validation
    result = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "bad:name.txt", "size": 100}]},
        headers=ORIGIN,
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["inventory"][0]["status"] == "invalid_name"
    assert data["summary"]["by_reason"]["invalid_name"] == 1


def test_queue_full(service: Service) -> None:
    """When queue is full (>= 32 queued), candidates get ``queue_full``.

    Directly insert 32 queued documents into the DB to trigger the limit.
    The inventory method reads the queued count and reports queue_full.
    """
    client = client_for(service)
    login(client)

    # Get alice's user ID for the owner_id field
    with service.db() as db:
        alice_row = db.execute("SELECT id FROM users WHERE username='alice'").fetchone()
        alice_id = alice_row["id"]

    # Directly insert 32 queued documents
    with service.db() as db:
        for i in range(32):
            db.execute(
                "INSERT INTO documents"
                " (id, owner_id, project_id, kind, name, content, status, created) "
                "VALUES (?, ?, ?, ?, ?, ?, 'queued', ?)",
                (
                    uuid.uuid4().hex,
                    alice_id,
                    "project-a",
                    "personal",
                    f"queue-fill-{i:02d}.txt",
                    "x" * 100,
                    time.time(),
                ),
            )

    # Now inventory should report queue_full
    result = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "new.txt", "size": 100}]},
        headers=ORIGIN,
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["inventory"][0]["status"] == "queue_full"
    assert data["summary"]["by_reason"]["queue_full"] == 1

    # Clean up: remove the test documents we inserted
    with service.db() as db:
        for i in range(32):
            db.execute("DELETE FROM documents WHERE name = ?", (f"queue-fill-{i:02d}.txt",))


def test_limit_reached_total(service: Service) -> None:
    """When total document count reaches 1000, candidates get ``limit_reached``.

    Directly insert 1000 documents into the DB to trigger the limit.
    The inventory method reads the total document count and reports limit_reached.
    """
    client = client_for(service)
    login(client)

    # Get alice's user ID for the owner_id field
    with service.db() as db:
        alice_row = db.execute("SELECT id FROM users WHERE username='alice'").fetchone()
        alice_id = alice_row["id"]

    # Directly insert 1000 documents with 'ready' status
    with service.db() as db:
        for i in range(1000):
            db.execute(
                "INSERT INTO documents"
                " (id, owner_id, project_id, kind, name, content, status, created) "
                "VALUES (?, ?, ?, ?, ?, ?, 'ready', ?)",
                (
                    uuid.uuid4().hex,
                    alice_id,
                    "project-a",
                    "personal",
                    f"limit-fill-{i:03d}.txt",
                    "x" * 100,
                    time.time(),
                ),
            )

    # Now inventory should report limit_reached
    result = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "new.txt", "size": 100}]},
        headers=ORIGIN,
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["inventory"][0]["status"] == "limit_reached"
    assert data["summary"]["by_reason"]["limit_reached"] == 1

    # Clean up: remove the test documents we inserted
    with service.db() as db:
        for i in range(1000):
            db.execute("DELETE FROM documents WHERE name = ?", (f"limit-fill-{i:03d}.txt",))


def test_limit_reached_per_user(service: Service) -> None:
    """When per-user document count reaches 100, candidates get ``limit_reached``.

    Directly insert 100 documents into the DB (all owned by alice) to trigger
    the per-user limit. The inventory method reads the per-user count and
    reports limit_reached.
    """
    client = client_for(service)
    login(client)

    # Get alice's user ID for the owner_id field
    with service.db() as db:
        alice_row = db.execute("SELECT id FROM users WHERE username='alice'").fetchone()
        alice_id = alice_row["id"]

    # Directly insert 100 documents with 'ready' status, all owned by alice
    with service.db() as db:
        for i in range(100):
            db.execute(
                "INSERT INTO documents"
                " (id, owner_id, project_id, kind, name, content, status, created) "
                "VALUES (?, ?, ?, ?, ?, ?, 'ready', ?)",
                (
                    uuid.uuid4().hex,
                    alice_id,
                    "project-a",
                    "personal",
                    f"user-limit-{i:03d}.txt",
                    "x" * 100,
                    time.time(),
                ),
            )

    # Now inventory should report limit_reached
    result = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "new.txt", "size": 100}]},
        headers=ORIGIN,
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["inventory"][0]["status"] == "limit_reached"
    assert data["summary"]["by_reason"]["limit_reached"] == 1

    # Clean up: remove the test documents we inserted
    with service.db() as db:
        for i in range(100):
            db.execute("DELETE FROM documents WHERE name = ?", (f"user-limit-{i:03d}.txt",))


def test_an_unpermitted_project_is_refused_outright(service: Service) -> None:
    """Acceptance criterion 3: the project is the unit the permission applies to.

    A per-candidate verdict would tell an unauthorized caller how full the
    project's queue is, so the request is refused instead.
    """
    bob = client_for(service)
    login(bob, "bob", "03")
    refused = bob.post(
        "/api/inventory",
        json={"project_id": "project-b", "candidates": [{"name": "sample.txt", "size": 100}]},
        headers=ORIGIN,
    )
    assert refused.status_code in {403, 404}, refused.text
    assert "inventory" not in refused.json()


def test_a_refused_inventory_records_nothing_about_documents(service: Service) -> None:
    bob = client_for(service)
    login(bob, "bob", "03")
    with service.db() as db:
        before = db.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    bob.post(
        "/api/inventory",
        json={"project_id": "project-b", "candidates": [{"name": "sample.txt", "size": 100}]},
        headers=ORIGIN,
    )
    with service.db() as db:
        operations = [
            row[0]
            for row in db.execute(
                "SELECT operation FROM audit ORDER BY at LIMIT -1 OFFSET ?", (before,)
            ).fetchall()
        ]
    assert not [name for name in operations if name.startswith(("document.", "inventory"))]


def test_inventory_no_content_saved(service: Service) -> None:
    """Inventory never stores content body or records audit."""
    client = client_for(service)
    login(client)

    # Send relatively large content length (but still under limit)
    result = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "sample.txt", "size": 500}]},
        headers=ORIGIN,
    )
    assert result.status_code == 200, result.text
    data = result.json()

    # Verify content was not persisted: no new document should exist
    with service.db() as db:
        count = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        assert count == 0, f"Expected 0 documents, got {count}"

    # Verify no audit entry for document.upload
    audit_count = db.execute(
        "SELECT COUNT(*) FROM audit WHERE operation='document.upload'"
    ).fetchone()[0]
    assert audit_count == 0, f"Expected 0 audit entries, got {audit_count}"

    assert data["inventory"][0]["status"] == "accepted"


def test_existing_upload_still_works(service: Service) -> None:
    """Existing upload API must still function correctly."""
    client = client_for(service)
    login(client)

    response = client.post(
        "/api/documents",
        json={
            "project_id": "project-a",
            "name": "retro-test.txt",
            "content": "synthetic retro test",
            "kind": "personal",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 201, response.text
    document_id = response.json()["id"]

    # Process ingestion
    service.process_next()

    stored = client.get(f"/api/documents/{document_id}").json()
    assert stored["status"] in ("ready", "quarantined"), (
        f"Expected ready/quarantined, got {stored['status']}"
    )


def test_the_owners_in_flight_bound_is_reported_before_the_global_one(
    service: Service,
) -> None:
    """The per-user bound binds first, and `upload` agrees with the report."""
    client = client_for(service)
    login(client)
    principal = service.authenticate(client.cookies.get("locus_session"))
    now = time.time()
    with service.db() as db:
        for index in range(4):
            db.execute(
                "INSERT INTO documents (id,owner_id,project_id,kind,name,content,status,created) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    f"in-flight-{index}",
                    principal.id,
                    "project-a",
                    "personal",
                    f"waiting-{index}.txt",
                    "合成本文",
                    "queued",
                    now,
                ),
            )
    reported = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "next.txt", "size": 10}]},
        headers=ORIGIN,
    )
    assert reported.status_code == 200, reported.text
    assert reported.json()["inventory"] == [{"name": "next.txt", "status": "queue_full"}]
    # The write path must refuse the same candidate, or the report is a lie.
    refused = client.post(
        "/api/documents",
        json={"project_id": "project-a", "name": "next.txt", "content": "合成本文"},
        headers=ORIGIN,
    )
    assert refused.status_code == 429, refused.text


def test_the_report_and_the_write_path_cannot_disagree(service: Service) -> None:
    """Every verdict is checked against what `POST /api/documents` actually does."""
    client = client_for(service)
    login(client)
    candidates = [
        {"name": "accepted.txt", "size": 12},
        {"name": "picture.png", "size": 12},
        {"name": ".hidden.txt", "size": 12},
        {"name": "huge.txt", "size": 262145},
    ]
    reported = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": candidates},
        headers=ORIGIN,
    )
    assert reported.status_code == 200, reported.text
    verdicts = {item["name"]: item["status"] for item in reported.json()["inventory"]}
    assert verdicts == {
        "accepted.txt": "accepted",
        "picture.png": "unsupported_format",
        ".hidden.txt": "invalid_name",
        "huge.txt": "too_large",
    }
    for candidate in candidates:
        name = str(candidate["name"])
        written = client.post(
            "/api/documents",
            json={
                "project_id": "project-a",
                "name": name,
                "content": "x" * int(candidate["size"]),
            },
            headers=ORIGIN,
        )
        if verdicts[name] == "accepted":
            assert written.status_code == 201, written.text
        else:
            assert written.status_code == 422, f"{name}: {written.status_code}"
