import pytest
from app import formats
from app.formats import DocumentFormat
from app.main import create_app
from app.service import Service, unsupported_extension
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


def format_row(extension: str, max_bytes: int = 262144) -> DocumentFormat:
    """A single accepted-format table row, for adding or removing synthetic ones."""
    return DocumentFormat(
        extension=extension, kind="text", max_bytes=max_bytes, extractor="plaintext"
    )


def test_default_table_accepts_exactly_the_original_text_formats() -> None:
    """The shipped table accepts .txt / .md / .csv and nothing else."""
    assert formats.accepted_extensions() == frozenset({".txt", ".md", ".csv"})
    assert formats.accepted_format_names() == ["txt", "md", "csv"]
    assert formats.max_content_bytes() == 262144
    assert unsupported_extension("sample.txt") is False
    assert unsupported_extension("sample.md") is False
    assert unsupported_extension("sample.csv") is False
    assert unsupported_extension("sample.pdf") is True
    assert unsupported_extension("sample.exe") is True


def test_default_formats_api_lists_the_shipped_table(service: Service) -> None:
    """The formats API serves the same default table the write paths enforce."""
    client = client_for(service)
    login(client)
    response = client.get("/api/formats", headers=ORIGIN)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "formats": [
            {"extension": ".txt", "kind": "text", "max_bytes": 262144, "extractor": "plaintext"},
            {"extension": ".md", "kind": "text", "max_bytes": 262144, "extractor": "plaintext"},
            {"extension": ".csv", "kind": "text", "max_bytes": 262144, "extractor": "plaintext"},
        ],
        "accepted_extensions": ["txt", "md", "csv"],
        "max_file_bytes": 262144,
    }
    anonymous = client_for(service)
    assert anonymous.get("/api/formats").status_code == 401


def test_a_single_added_table_row_opens_upload_inventory_and_formats_together(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adding one table row must move all three format-aware paths at once."""
    monkeypatch.setattr(
        formats,
        "SUPPORTED_FORMATS",
        [
            format_row(".txt"),
            format_row(".md"),
            format_row(".csv"),
            format_row(".pdf"),
        ],
    )
    client = client_for(service)
    login(client)
    uploaded = client.post(
        "/api/documents",
        json={
            "project_id": "project-a",
            "name": "sample.pdf",
            "content": "synthetic pdf sample",
            "kind": "personal",
        },
        headers=ORIGIN,
    )
    assert uploaded.status_code == 201, uploaded.text
    inventoried = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "sample.pdf", "size": 100}]},
        headers=ORIGIN,
    )
    assert inventoried.status_code == 200, inventoried.text
    assert inventoried.json()["inventory"] == [{"name": "sample.pdf", "status": "accepted"}]
    catalogued = client.get("/api/formats", headers=ORIGIN)
    assert catalogued.status_code == 200, catalogued.text
    assert catalogued.json()["accepted_extensions"] == ["txt", "md", "csv", "pdf"]


def test_removing_a_table_row_refuses_upload_inventory_and_formats_together(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing one table row must move all three format-aware paths at once."""
    monkeypatch.setattr(
        formats,
        "SUPPORTED_FORMATS",
        [format_row(".txt"), format_row(".md")],
    )
    client = client_for(service)
    login(client)
    refused = client.post(
        "/api/documents",
        json={
            "project_id": "project-a",
            "name": "sample.csv",
            "content": "synthetic csv sample",
            "kind": "personal",
        },
        headers=ORIGIN,
    )
    assert refused.status_code == 422, refused.text
    inventoried = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "sample.csv", "size": 100}]},
        headers=ORIGIN,
    )
    assert inventoried.json()["inventory"] == [
        {"name": "sample.csv", "status": "unsupported_format"}
    ]
    catalogued = client.get("/api/formats", headers=ORIGIN)
    assert catalogued.status_code == 200, catalogued.text
    assert catalogued.json()["accepted_extensions"] == ["txt", "md"]


def test_per_format_max_bytes_apply_to_upload_and_inventory(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The per-format byte bound is enforced by both the write and the report path."""
    monkeypatch.setattr(
        formats,
        "SUPPORTED_FORMATS",
        [format_row(".log", max_bytes=10)],
    )
    client = client_for(service)
    login(client)
    refused = client.post(
        "/api/documents",
        json={
            "project_id": "project-a",
            "name": "sample.log",
            "content": "0123456789A",
            "kind": "personal",
        },
        headers=ORIGIN,
    )
    assert refused.status_code == 422, refused.text
    inventoried = client.post(
        "/api/inventory",
        json={"project_id": "project-a", "candidates": [{"name": "sample.log", "size": 11}]},
        headers=ORIGIN,
    )
    assert inventoried.json()["inventory"] == [{"name": "sample.log", "status": "too_large"}]
    catalogued = client.get("/api/formats", headers=ORIGIN)
    assert catalogued.json()["max_file_bytes"] == 10
