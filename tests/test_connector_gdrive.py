from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.connector_gdrive import (
    DOCUMENT_MIME,
    KEY_FILE_ENV,
    LIST_FIELDS,
    REASON_EXPORT_UNAVAILABLE,
    REASON_FOLDER,
    REASON_INVALID_SOURCE,
    REASON_SOURCE_UNREACHABLE,
    REASON_UNSUPPORTED_FORMAT,
    REASON_UNSUPPORTED_NATIVE,
    SCOPE,
    SPREADSHEET_MIME,
    TOKEN_URL,
    GoogleDriveConnector,
    GoogleDriveError,
    GoogleDriveUnavailable,
)
from app.service import Principal, Service
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ACCOUNT_EMAIL = "locus-sync@example.iam.gserviceaccount.com"


@pytest.fixture(scope="session")
def account_key() -> tuple[Any, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return key, pem


def key_file(tmp_path: Path, pem: str) -> Path:
    path = tmp_path / "service-account.json"
    path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "client_email": ACCOUNT_EMAIL,
                "private_key": pem,
            }
        ),
        encoding="utf-8",
    )
    return path


def connector_for(
    path: Path,
    handler: Any,
    *,
    source: str = "folder-1",
    now: Any = None,
) -> GoogleDriveConnector:
    kwargs: dict[str, Any] = {}
    if now is not None:
        kwargs["now"] = now
    return GoogleDriveConnector(
        source,
        env={KEY_FILE_ENV: str(path)},
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def token_response(value: str = "bearer-1", expires_in: int = 3600) -> httpx.Response:
    return httpx.Response(200, json={"access_token": value, "expires_in": expires_in})


def decode_segment(segment: str) -> dict[str, Any]:
    padded = segment + "=" * (-len(segment) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(padded))
    assert isinstance(decoded, dict)
    return decoded


def decode_signature(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def admin_actor(service: Service) -> Principal:
    with service.db() as db:
        row = db.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    return Principal(row["id"], row["username"], bool(row["system_admin"]), False)


def drive_file(
    file_id: str,
    name: str,
    mime_type: str = "text/plain",
    *,
    revision: str = "rev-1",
    size: str = "5",
    modified: str = "2026-01-02T03:04:05.000Z",
) -> dict[str, str]:
    return {
        "id": file_id,
        "name": name,
        "mimeType": mime_type,
        "headRevisionId": revision,
        "size": size,
        "modifiedTime": modified,
    }


def test_token_request_signs_a_readonly_jwt(tmp_path: Path, account_key: tuple[Any, str]) -> None:
    key, pem = account_key
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url) == TOKEN_URL:
            return token_response()
        return httpx.Response(200, json={"files": []})

    connector = connector_for(key_file(tmp_path, pem), handler)
    items, cursor = connector.list_items()

    assert items == []
    assert cursor is None
    assert SCOPE == "https://www.googleapis.com/auth/drive.readonly"
    token_request = requests[0]
    assert str(token_request.url) == TOKEN_URL
    form = dict(httpx.QueryParams(token_request.content.decode("ascii")))
    assert form["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    header_segment, claims_segment, signature_segment = form["assertion"].split(".")
    assert decode_segment(header_segment) == {"alg": "RS256", "typ": "JWT"}
    claims = decode_segment(claims_segment)
    assert claims["scope"] == SCOPE
    assert claims["iss"] == ACCOUNT_EMAIL
    assert claims["aud"] == TOKEN_URL
    assert claims["exp"] - claims["iat"] == 3600
    key.public_key().verify(
        decode_signature(signature_segment),
        f"{header_segment}.{claims_segment}".encode("ascii"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


def test_list_items_pages_and_uses_head_revision(
    tmp_path: Path, account_key: tuple[Any, str]
) -> None:
    _, pem = account_key
    file_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        file_requests.append(request)
        if request.url.params.get("pageToken") is None:
            return httpx.Response(
                200,
                json={
                    "files": [drive_file("file-a", "a.txt", revision="rev-a")],
                    "nextPageToken": "page-2",
                },
            )
        return httpx.Response(
            200,
            json={"files": [drive_file("file-b", "b.md", revision="rev-b", size="7")]},
        )

    connector = connector_for(key_file(tmp_path, pem), handler)
    first, cursor = connector.list_items()
    second, last_cursor = connector.list_items(cursor)

    assert [item.external_id for item in first] == ["file-a"]
    assert first[0].revision == "rev-a"
    assert first[0].size == 5
    assert first[0].content_hash == ""
    assert first[0].modified_at > 0
    assert [item.external_id for item in second] == ["file-b"]
    assert second[0].revision == "rev-b"
    assert cursor == "page-2"
    assert last_cursor is None
    assert file_requests[0].url.params["q"] == "'folder-1' in parents and trashed=false"
    assert file_requests[0].url.params["fields"] == LIST_FIELDS
    assert file_requests[1].url.params["pageToken"] == "page-2"
    assert file_requests[0].headers["Authorization"] == "Bearer bearer-1"


def test_google_native_items_are_exported_and_others_skipped(
    tmp_path: Path, account_key: tuple[Any, str]
) -> None:
    _, pem = account_key
    downloads: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        if request.url.path == "/drive/v3/files":
            return httpx.Response(
                200,
                json={
                    "files": [
                        drive_file("doc-1", "Meeting notes", DOCUMENT_MIME),
                        drive_file("sheet-1", "Budget", SPREADSHEET_MIME),
                        drive_file(
                            "slide-1",
                            "Deck",
                            "application/vnd.google-apps.presentation",
                        ),
                        drive_file("pdf-1", "scan.pdf", "application/pdf"),
                        drive_file("dir-1", "Sub", "application/vnd.google-apps.folder"),
                        drive_file("file-1", "note.txt"),
                    ]
                },
            )
        downloads.append(request)
        if request.url.path == "/drive/v3/files/doc-1/export":
            return httpx.Response(200, content=b"exported notes")
        if request.url.path == "/drive/v3/files/sheet-1/export":
            return httpx.Response(200, content=b"a,b")
        return httpx.Response(200, content=b"plain text")

    connector = connector_for(key_file(tmp_path, pem), handler)
    items, cursor = connector.list_items()

    assert cursor is None
    assert [(item.external_id, item.name) for item in items] == [
        ("doc-1", "Meeting notes.txt"),
        ("sheet-1", "Budget.csv"),
        ("file-1", "note.txt"),
    ]
    reasons = {(rejection.external_id, rejection.reason) for rejection in connector.rejections}
    assert ("slide-1", REASON_UNSUPPORTED_NATIVE) in reasons
    assert ("pdf-1", REASON_UNSUPPORTED_FORMAT) in reasons
    assert ("dir-1", REASON_FOLDER) in reasons

    assert connector.fetch_content("doc-1") == b"exported notes"
    assert downloads[-1].url.path == "/drive/v3/files/doc-1/export"
    assert downloads[-1].url.params["mimeType"] == "text/plain"
    assert connector.fetch_content("sheet-1") == b"a,b"
    assert downloads[-1].url.path == "/drive/v3/files/sheet-1/export"
    assert downloads[-1].url.params["mimeType"] == "text/csv"
    assert connector.fetch_content("file-1") == b"plain text"
    assert downloads[-1].url.path == "/drive/v3/files/file-1"
    assert downloads[-1].url.params["alt"] == "media"


def test_401_refreshes_the_token_once(tmp_path: Path, account_key: tuple[Any, str]) -> None:
    _, pem = account_key
    token_calls = 0
    file_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls, file_calls
        if str(request.url) == TOKEN_URL:
            token_calls += 1
            return token_response(f"token-{token_calls}")
        file_calls += 1
        if file_calls == 1:
            return httpx.Response(401, json={"error": "invalid_token"})
        return httpx.Response(200, json={"files": []})

    connector = connector_for(key_file(tmp_path, pem), handler)
    items, cursor = connector.list_items()

    assert items == []
    assert cursor is None
    assert token_calls == 2
    assert file_calls == 2


def test_a_second_401_is_not_retried_again(tmp_path: Path, account_key: tuple[Any, str]) -> None:
    _, pem = account_key
    token_calls = 0
    file_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls, file_calls
        if str(request.url) == TOKEN_URL:
            token_calls += 1
            return token_response(f"token-{token_calls}")
        file_calls += 1
        return httpx.Response(401, json={"error": "invalid_token"})

    connector = connector_for(key_file(tmp_path, pem), handler)
    with pytest.raises(GoogleDriveError):
        connector.list_items()

    assert token_calls == 2
    assert file_calls == 2


def test_token_is_reused_until_it_expires(tmp_path: Path, account_key: tuple[Any, str]) -> None:
    _, pem = account_key
    clock = [1000.0]
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if str(request.url) == TOKEN_URL:
            token_calls += 1
            return token_response(f"token-{token_calls}")
        return httpx.Response(200, json={"files": []})

    connector = connector_for(key_file(tmp_path, pem), handler, now=lambda: clock[0])
    connector.list_items()
    connector.list_items()
    assert token_calls == 1

    clock[0] += 3600
    connector.list_items()
    assert token_calls == 2


def test_key_material_never_appears_in_errors_or_state(
    tmp_path: Path, account_key: tuple[Any, str]
) -> None:
    _, pem = account_key
    secret_line = pem.splitlines()[1]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    connector = connector_for(key_file(tmp_path, pem), handler)
    with pytest.raises(GoogleDriveError) as caught:
        connector.list_items()

    assert secret_line not in str(caught.value)
    assert secret_line not in repr(caught.value)
    assert secret_line not in repr(connector.rejections)
    assert secret_line not in repr(vars(connector))


def test_unconfigured_connector_is_unavailable(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected without credentials")

    connector = GoogleDriveConnector("folder-1", env={}, transport=httpx.MockTransport(handler))
    assert connector.configured is False
    with pytest.raises(GoogleDriveUnavailable):
        connector.list_items()
    with pytest.raises(KeyError):
        connector.fetch_content("file-a")

    path = key_file(tmp_path, "unused")
    no_source = GoogleDriveConnector(
        "", env={KEY_FILE_ENV: str(path)}, transport=httpx.MockTransport(handler)
    )
    assert no_source.configured is True
    with pytest.raises(GoogleDriveUnavailable):
        no_source.list_items()


def test_invalid_folder_id_is_refused(tmp_path: Path, account_key: tuple[Any, str]) -> None:
    _, pem = account_key

    def handler(request: httpx.Request) -> httpx.Response:
        return token_response()

    connector = connector_for(key_file(tmp_path, pem), handler, source="bad'id")
    with pytest.raises(GoogleDriveError):
        connector.list_items()

    assert any(rejection.reason == REASON_INVALID_SOURCE for rejection in connector.rejections)


def test_forbidden_listing_revokes_existing_origins(
    service: Service, tmp_path: Path, account_key: tuple[Any, str]
) -> None:
    _, pem = account_key
    deny = [False]

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        if request.url.path == "/drive/v3/files":
            if deny[0]:
                return httpx.Response(403, json={"error": {"code": 403}})
            return httpx.Response(200, json={"files": [drive_file("file-a", "a.txt")]})
        return httpx.Response(200, content=b"hello")

    connector = connector_for(key_file(tmp_path, pem), handler)
    service.register_sync_connector("google_drive", connector, configured=connector.configured)
    actor = admin_actor(service)

    first = service.sync_connector(actor, "google_drive", "project-a", "folder-1")
    assert first["registered"] == 1
    origin = service.get_document_origin("google_drive", "file-a")
    assert origin is not None

    deny[0] = True
    second = service.sync_connector(actor, "google_drive", "project-a", "folder-1")

    assert second["registered"] == 0
    assert second["failed"] == 0
    revoked = service.get_document_origin("google_drive", "file-a")
    assert revoked is not None
    assert revoked["revoked"] is True
    assert service.is_document_origin_revoked(origin["document_id"]) is True
    assert any(rejection.reason == REASON_SOURCE_UNREACHABLE for rejection in connector.rejections)


def test_forbidden_listing_on_later_page_fails_without_partial_revocation(
    service: Service, tmp_path: Path, account_key: tuple[Any, str]
) -> None:
    _, pem = account_key
    deny_second_page = [False]

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        if request.url.path == "/drive/v3/files":
            if request.url.params.get("pageToken") is None:
                return httpx.Response(
                    200,
                    json={
                        "files": [drive_file("file-a", "a.txt")],
                        "nextPageToken": "page-2",
                    },
                )
            if deny_second_page[0]:
                return httpx.Response(403, json={"error": {"code": 403}})
            return httpx.Response(200, json={"files": [drive_file("file-b", "b.txt")]})
        return httpx.Response(200, content=b"hello")

    connector = connector_for(key_file(tmp_path, pem), handler)
    service.register_sync_connector("google_drive", connector, configured=connector.configured)
    actor = admin_actor(service)

    first = service.sync_connector(actor, "google_drive", "project-a", "folder-1")
    assert first["registered"] == 2

    deny_second_page[0] = True
    second = service.sync_connector(actor, "google_drive", "project-a", "folder-1")
    assert second["failed"] == 1
    origin_a = service.get_document_origin("google_drive", "file-a")
    origin_b = service.get_document_origin("google_drive", "file-b")
    assert origin_a is not None and origin_a["revoked"] is False
    assert origin_b is not None and origin_b["revoked"] is False
    assert any(rejection.reason == REASON_SOURCE_UNREACHABLE for rejection in connector.rejections)


def test_transport_error_is_sanitized_and_not_retried(
    tmp_path: Path, account_key: tuple[Any, str]
) -> None:
    _, pem = account_key
    secret_line = pem.splitlines()[1]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("network down")

    connector = connector_for(key_file(tmp_path, pem), handler)
    with pytest.raises(GoogleDriveError) as caught:
        connector.list_items()

    assert calls == 1
    assert secret_line not in str(caught.value)
    assert secret_line not in repr(caught.value)


def test_oversized_google_native_export_is_skipped_by_sync_engine(
    service: Service, tmp_path: Path, account_key: tuple[Any, str]
) -> None:
    _, pem = account_key

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        if request.url.path == "/drive/v3/files":
            return httpx.Response(
                200,
                json={
                    "files": [
                        drive_file("doc-1", "Large Doc", DOCUMENT_MIME, size="9999999"),
                    ]
                },
            )
        return httpx.Response(200, content=b"small export")

    connector = connector_for(key_file(tmp_path, pem), handler)
    service.register_sync_connector("google_drive", connector, configured=connector.configured)
    result = service.sync_connector(admin_actor(service), "google_drive", "project-a", "folder-1")

    assert result["registered"] == 1
    assert result["skipped"] == 0


def test_unexportable_google_native_item_is_skipped_with_reason(
    service: Service, tmp_path: Path, account_key: tuple[Any, str]
) -> None:
    _, pem = account_key

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        if request.url.path == "/drive/v3/files":
            return httpx.Response(
                200,
                json={"files": [drive_file("doc-bad", "Unexportable", DOCUMENT_MIME)]},
            )
        return httpx.Response(403, json={"error": {"reason": "cannotExportFile"}})

    connector = connector_for(key_file(tmp_path, pem), handler)
    service.register_sync_connector("google_drive", connector, configured=connector.configured)
    result = service.sync_connector(admin_actor(service), "google_drive", "project-a", "folder-1")

    assert result["registered"] == 0
    assert result["skipped"] == 1
    assert result["failed"] == 0
    assert any(
        rejection.external_id == "doc-bad" and rejection.reason == REASON_EXPORT_UNAVAILABLE
        for rejection in connector.rejections
    )


def test_sync_imports_a_folder_and_revision_controls_updates(
    service: Service, tmp_path: Path, account_key: tuple[Any, str]
) -> None:
    _, pem = account_key
    state = {"revision": "rev-1", "content": b"hello drive", "fetches": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        if request.url.path == "/drive/v3/files":
            return httpx.Response(
                200,
                json={
                    "files": [
                        drive_file(
                            "file-a",
                            "note.txt",
                            revision=state["revision"],
                            size=str(len(state["content"])),
                        )
                    ]
                },
            )
        state["fetches"] += 1
        return httpx.Response(200, content=state["content"])

    connector = connector_for(key_file(tmp_path, pem), handler)
    service.register_sync_connector("google_drive", connector, configured=connector.configured)
    actor = admin_actor(service)

    first = service.sync_connector(actor, "google_drive", "project-a", "folder-1")
    first_origin = service.get_document_origin("google_drive", "file-a")
    assert first["registered"] == 1
    assert first_origin is not None
    assert state["fetches"] == 1

    second = service.sync_connector(actor, "google_drive", "project-a", "folder-1")
    assert second["skipped"] == 1
    assert state["fetches"] == 1
    second_origin = service.get_document_origin("google_drive", "file-a")
    assert second_origin is not None
    assert second_origin["document_id"] == first_origin["document_id"]

    state["revision"] = "rev-2"
    state["content"] = b"hello drive again"
    third = service.sync_connector(actor, "google_drive", "project-a", "folder-1")
    third_origin = service.get_document_origin("google_drive", "file-a")
    assert third["updated"] == 1
    assert state["fetches"] == 2
    assert third_origin is not None
    assert third_origin["document_id"] != first_origin["document_id"]
    assert third_origin["external_revision"] == "rev-2"

    with service.db() as db:
        docs = db.execute(
            "SELECT content FROM documents WHERE name='note.txt' ORDER BY created"
        ).fetchall()
    assert [row["content"] for row in docs] == ["hello drive", "hello drive again"]
